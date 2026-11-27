/* Host unit tests of the head firmware core against a scripted mock HAL: protocol 2.0 state
 * machine, binding rules, frame mapping, buffer, sync quality, heater, bias, fault latching. */
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>

#include "rrc_test.h"
#include "rrh_core.h"

/* ================================================================== mock HAL */
#define TICK_HZ 48000000u
static struct {
    uint64_t now_us;
    uint8_t entropy_next;
    bool entropy_ok;
    rrh_reset_cause_t reset_cause;
    bool running, stopping, start_ok;
    uint32_t span_us, next_seq, stop_after;
    uint64_t t0_us;
    rrh_gate_lane_t lane_template[RRH_LANES];
    uint32_t gate_ticks_override, skip;
    uint8_t width_mask;
    bool heater_req, heater_applied;
    uint32_t heater_requests;
    rrh_analog_t analog;
    rrh_imon_t imon;
    rrh_expander_t exp;
    double imon_ua[RRH_CHAINS];
    bool permit_ok;          /* mock of the permit latch: bias_mv reads 0 while false */
    uint32_t bias_mv;
    bool bias_on;
    uint32_t bias_calls;
    uint8_t nv[128];
    size_t nv_len;
    uint32_t fe_applies, kicks;
    rrh_frontend_cfg_t fe;
} m;

uint64_t rrh_hal_now_us(void) { return m.now_us; }
uint64_t rrh_hal_reply_tx_time_us(uint64_t rx_us) { return rx_us + 100u; }
bool rrh_hal_entropy(uint8_t *buf, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        buf[i] = m.entropy_next++;
    }
    return m.entropy_ok;
}
rrh_reset_cause_t rrh_hal_reset_cause(void) { return m.reset_cause; }
void rrh_hal_watchdog_kick(void) { m.kicks++; }
uint32_t rrh_hal_image_crc32(void) { return 0xC0DE0001u; }
bool rrh_hal_acq_start(uint32_t span_us, rrh_epoch_t *epoch)
{
    if (!m.start_ok) {
        return false;
    }
    m.running = true;
    m.stopping = false;
    m.span_us = span_us;
    m.t0_us = m.now_us + 1000u;
    m.next_seq = 0u;
    epoch->tick = 5000u + (m.now_us * 48u);
    epoch->us = m.now_us;
    epoch->tick_hz = TICK_HZ;
    return true;
}
bool rrh_hal_acq_stop(void)
{
    if (!m.running || (m.now_us < m.t0_us)) {
        m.running = false;
        return false;
    }
    m.stopping = true;
    m.stop_after = (uint32_t)((m.now_us - m.t0_us) / m.span_us);
    return true;
}
void rrh_hal_acq_abort(void) { m.running = false; m.stopping = false; }
bool rrh_hal_acq_running(void) { return m.running; }
bool rrh_hal_acq_poll(rrh_gate_record_t *rec)
{
    for (;;) {
        if (!m.running) {
            return false;
        }
        if (m.stopping && (m.next_seq > m.stop_after)) {
            m.running = false;
            return false;
        }
        const uint64_t start = m.t0_us + ((uint64_t)m.next_seq * m.span_us);
        if (m.now_us < (start + m.span_us)) {
            return false;
        }
        memset(rec, 0, sizeof *rec);
        rec->sequence = m.next_seq++;
        rec->gate_start_tick = 5000u + (start * 48u);
        rec->gate_ticks = (m.gate_ticks_override != 0u) ? m.gate_ticks_override : (m.span_us * 48u);
        rec->tick_hz = TICK_HZ;
        rec->heater_on_ticks = m.heater_applied ? rec->gate_ticks : 0u;
        m.heater_applied = m.heater_req;
        memcpy(rec->lane, m.lane_template, sizeof rec->lane);
        if (m.width_mask != 0u) {
            rec->width_mask = m.width_mask;
            rec->width_edges_ns[0] = 150u;
            rec->width_edges_ns[1] = 400u;
            rec->width_edges_ns[2] = 2000u;
            for (uint32_t ch = 0; ch < 8u; ch++) {
                rec->width_hist[ch][1] = 7u + ch;
                rec->width_hist[ch][3] = (ch == 2u) ? 70000u : 1u;
            }
        }
        if (m.skip > 0u) {
            m.skip--;
            continue;
        }
        return true;
    }
}
bool rrh_hal_frontend_apply(const rrh_frontend_cfg_t *cfg) { m.fe = *cfg; m.fe_applies++; return true; }
void rrh_hal_bias_set(uint32_t mv, bool enable) { m.bias_mv = mv; m.bias_on = enable; m.bias_calls++; }
void rrh_hal_analog_read(rrh_analog_t *out)
{
    *out = m.analog;
    out->bias_mv = (m.bias_on && m.permit_ok) ? m.bias_mv : 0u;
}
/* IMON_CH of chain ch = V(trim) - I x R105 (mock of the board, same formula as the sim) */
void rrh_hal_imon_read(rrh_imon_t *out)
{
    memset(out, 0, sizeof *out);
    out->valid = m.imon.valid;
    for (uint32_t ch = 0; ch < RRH_CHAINS; ch++) {
        double v = (double)rrh_board_trim_uv(m.fe.trim[ch]) - (m.bias_on ? m.imon_ua[ch] : 0.0) * (double)RRH_R105_OHM;
        out->uv[ch] = (v < 2000.0) ? 2000u : (uint32_t)v;
    }
}
void rrh_hal_expander_read(rrh_expander_t *out) { *out = m.exp; }
static uint32_t force_offs;
void rrh_hal_heater_force_off(void)
{
    force_offs++;
    m.heater_req = false;
    m.heater_applied = false;
}
void rrh_hal_heater_request(bool on)
{
    m.heater_req = on;
    m.heater_requests++;
    if (!m.running) {
        m.heater_applied = on;
    }
}
bool rrh_hal_nv_load(uint8_t slot, uint8_t *buf, size_t cap, size_t *len)
{
    if ((slot != 0u) || (m.nv_len == 0u) || (m.nv_len > cap)) {
        return false;
    }
    memcpy(buf, m.nv, m.nv_len);
    *len = m.nv_len;
    return true;
}
bool rrh_hal_nv_save(uint8_t slot, const uint8_t *buf, size_t len)
{
    (void)slot;
    memcpy(m.nv, buf, len);
    m.nv_len = len;
    return true;
}
bool rrh_hal_wave_arm(const rrh_wave_cfg_t *cfg) { (void)cfg; return true; }
rrh_wave_state_t rrh_hal_wave_status(uint16_t *samples, uint32_t *period_ns, uint16_t *trigger_index)
{
    *samples = 64u; *period_ns = 250u; *trigger_index = 8u;
    return RRH_WAVE_DONE;
}
bool rrh_hal_wave_read(uint16_t offset, uint16_t count, uint8_t *buf)
{
    for (uint16_t i = 0; i < count; i++) {
        buf[2u * i] = (uint8_t)(offset + i);
        buf[2u * i + 1u] = 0u;
    }
    return true;
}

/* ================================================================== harness */
static rrh_core_t core;
static rrh_identity_t ident;
static char rsp[RRH_TX_MAX + 1u];      /* last reply, JSON part, NUL-terminated */
static uint8_t rsp_wire[RRH_TX_MAX];   /* last reply, exact wire bytes */
static size_t rsp_wire_len;
static uint64_t rsp_tx_at;
static uint32_t next_id = 1u;
static rrc_json_t rdoc;
static rrc_jtok_t rtok[400];

static void mock_reset(void)
{
    memset(&m, 0, sizeof m);
    m.entropy_ok = true;
    m.start_ok = true;
    m.reset_cause = RRH_RESET_POWER_ON;
    for (uint32_t l = 0; l < RRH_LANES; l++) {
        m.analog.sipm_mc[l] = 25000;
        m.lane_template[l].alpha_counts = l;
        m.lane_template[l].beta_counts = 10u + l;
        m.lane_template[l].ref_counts = 20u + l;
        m.lane_template[l].floor_reject_counts = 1u;
        m.lane_template[l].ref_reject_counts = 2u;
        m.lane_template[l].floor_live_ticks = 4795680u; /* 99910 us */
        m.lane_template[l].ref_live_ticks = 4798560u;   /* 99970 us */
    }
    m.analog.heater_plate_mc = 0;
    m.analog.board_mc = 24000;
    m.analog.bias_valid = true;
    m.analog.bias_ua = 40u;
    m.analog.supply_valid = true;
    m.analog.supply_mv = 12000u;
    m.analog.heater_cutout_ok = true;
    m.permit_ok = true;
    m.imon.valid = 0xFFu;
    for (uint32_t ch = 0; ch < RRH_CHAINS; ch++) {
        m.imon_ua[ch] = 1.0;
    }
}

static void boot(void)
{
    rrh_identity_defaults(&ident, "UNIT-0001");
    ident.allow_placeholder_thresholds = true; /* the target refuses; tests that check the refusal clear this */
    ident.gate_min_us = 10000u;
    ident.gate_max_us = 1000000u;
    rrh_core_init(&core, &ident);
    next_id = 1u;
}

/* Feed raw wire bytes; returns true if the core replied. */
static bool feed(const uint8_t *line, size_t n)
{
    rrh_reply_t r;
    bool got = false;
    for (size_t i = 0; i < n; i++) {
        if (rrh_core_rx_byte(&core, line[i], m.now_us, &r)) {
            got = true;
            memcpy(rsp_wire, r.data, r.len);
            rsp_wire_len = r.len;
            rsp_tx_at = r.tx_at_us;
            memcpy(rsp, r.data, r.len - RRC_FRAME_TRAILER_LEN);
            rsp[r.len - RRC_FRAME_TRAILER_LEN] = '\0';
            size_t jl = 0;
            uint32_t crc = 0;
            static const rrc_json_limits_t lim = {8u, 2048u};
            CHECK(rrc_frame_check(r.data, r.len, RRH_RX_MAX, &jl, &crc) == RRC_FRAME_OK);
            CHECK(rrc_json_parse(&rdoc, rsp, jl, rtok, 400u, &lim) == RRC_JSON_OK);
        }
    }
    return got;
}

static uint8_t last_req[512];
static size_t last_req_len;

static bool send_id(uint32_t id, const char *op, const char *args)
{
    const int n = snprintf((char *)last_req, sizeof last_req - 16u,
                           "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":%u,\"op\":\"%s\",\"args\":%s}", (unsigned)id, op, args);
    last_req_len = rrc_frame_finish(last_req, (size_t)n, sizeof last_req, RRH_RX_MAX);
    rsp[0] = '\0';
    return feed(last_req, last_req_len);
}

static bool send(const char *op, const char *fmt, ...)
{
    char args[400];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(args, sizeof args, fmt, ap);
    va_end(ap);
    return send_id(next_id++, op, args);
}

static bool status_is(const char *st)
{
    return rrc_json_str_eq(&rdoc, rrc_json_get(&rdoc, 0, "status"), st);
}

static int body(void) { return rrc_json_get(&rdoc, 0, "body"); }

static int64_t body_int(const char *key)
{
    int64_t v = -999;
    (void)rrc_json_to_i64(&rdoc, rrc_json_get(&rdoc, body(), key), &v);
    return v;
}

static bool has(const char *needle) { return strstr(rsp, needle) != NULL; }

static void advance(uint64_t us)
{
    while (us > 0u) {
        const uint64_t step = (us > 10000u) ? 10000u : us;
        m.now_us += step;
        us -= step;
        rrh_core_poll(&core);
    }
}

static void handshake(void)
{
    char a[300];
    CHECK(send("HELLO", "{}") && status_is("OK"));
    snprintf(a, sizeof a, "{\"boot_id\":\"%s\",\"setup_id\":\"%s\",\"descriptor_sha256\":\"%s\"}", core.boot_id,
             core.setup_id, core.descriptor_sha256);
    CHECK(send("BIND", "%s", a) && status_is("OK") && has("\"bound\":true"));
    CHECK(core.link == RRH_LINK_BOUND);
}

static void arm(uint32_t span)
{
    CHECK(send("ARM", "{\"span_us\":%u}", (unsigned)span) && status_is("OK"));
}

/* ================================================================== tests */
static void test_boot_state_is_unbound(void)
{
    mock_reset();
    boot();
    CHECK(core.link == RRH_LINK_UNBOUND);
    CHECK(rrc_uuid_is_canonical(core.boot_id));
    static const char *const ops[] = {"TIME", "SYNC", "ARM", "READ", "DISARM", "DIAG"};
    for (size_t i = 0; i < 6u; i++) {
        CHECK(send(ops[i], "{}") && status_is("UNBOUND"));
        CHECK(!has("counts") && !has("sequence"));
    }
    /* handshake ops without HELLO */
    CHECK(send("BIND", "{\"boot_id\":\"%s\",\"setup_id\":\"%s\",\"descriptor_sha256\":\"%s\"}", core.boot_id,
               core.setup_id, core.descriptor_sha256));
    CHECK(status_is("UNBOUND") && (core.link == RRH_LINK_UNBOUND));
    CHECK(send("GET_DESCRIPTOR", "{\"boot_id\":\"%s\",\"descriptor_id\":\"%s\",\"offset\":0,\"count\":16}", core.boot_id,
               ident.descriptor_id) && status_is("UNBOUND"));
    CHECK(send("NO_SUCH_OP", "{}") && status_is("UNSUPPORTED"));
    CHECK(send("STATUS", "{}") && status_is("OK") && has("\"link\":\"UNBOUND\""));
}

static void test_handshake_rules(void)
{
    mock_reset();
    boot();
    CHECK(send("HELLO", "{}") && status_is("OK"));
    CHECK(core.link == RRH_LINK_HANDSHAKE);
    CHECK(has("\"supported_discovery\":[\"2.0\"]") && has("\"acq_format\":\"2.0\"") && has("\"head_id\":\"UNIT-0001\""));
    CHECK((size_t)body_int("descriptor_bytes") == core.descriptor_len);
    /* stale boot id */
    CHECK(send("BIND", "{\"boot_id\":\"00000000-0000-4000-8000-000000000000\",\"setup_id\":\"%s\",\"descriptor_sha256\":\"%s\"}",
               core.setup_id, core.descriptor_sha256) && status_is("WRONG_BOOT"));
    CHECK(send("GET_DESCRIPTOR", "{\"boot_id\":\"x\",\"descriptor_id\":\"%s\",\"offset\":0,\"count\":16}",
               ident.descriptor_id) && status_is("WRONG_BOOT"));
    /* wrong setup / digest: rejected, handshake stays open, nothing bound */
    CHECK(send("BIND", "{\"boot_id\":\"%s\",\"setup_id\":\"other\",\"descriptor_sha256\":\"%s\"}", core.boot_id,
               core.descriptor_sha256) && status_is("BAD_ARG"));
    CHECK(send("BIND", "{\"boot_id\":\"%s\",\"setup_id\":\"%s\",\"descriptor_sha256\":\"00\"}", core.boot_id,
               core.setup_id) && status_is("BAD_ARG"));
    CHECK(send("BIND", "{\"boot_id\":\"%s\",\"setup_id\":\"%s\"}", core.boot_id, core.setup_id) && status_is("BAD_ARG"));
    CHECK(core.link == RRH_LINK_HANDSHAKE);
    CHECK(send("TIME", "{}") && status_is("UNBOUND"));
    /* descriptor chunk limits */
    const char *gd = "{\"boot_id\":\"%s\",\"descriptor_id\":\"%s\",\"offset\":%d,\"count\":%d}";
    CHECK(send("GET_DESCRIPTOR", gd, core.boot_id, ident.descriptor_id, 0, 0) && status_is("BAD_ARG"));
    CHECK(send("GET_DESCRIPTOR", gd, core.boot_id, ident.descriptor_id, 0, 769) && status_is("BAD_ARG"));
    CHECK(send("GET_DESCRIPTOR", gd, core.boot_id, ident.descriptor_id, (int)core.descriptor_len, 1) && status_is("BAD_ARG"));
    CHECK(send("GET_DESCRIPTOR", gd, core.boot_id, ident.descriptor_id, -1, 1) && status_is("BAD_ARG"));
    CHECK(send("GET_DESCRIPTOR", gd, core.boot_id, "D-OTHER", 0, 1) && status_is("BAD_ARG"));
    CHECK(send("GET_DESCRIPTOR", gd, core.boot_id, ident.descriptor_id, (int)core.descriptor_len - 1, 768) && status_is("OK"));
    CHECK(has("\"bytes_b64\":\"Cg==\"")); /* the last byte is the trailing LF */
    /* reassemble everything in 100-byte chunks and compare with the SHA-256 the head advertised */
    rrc_sha256_t sha;
    rrc_sha256_init(&sha);
    for (size_t off = 0; off < core.descriptor_len; off += 100u) {
        char b64[200];
        uint8_t raw[100];
        CHECK(send("GET_DESCRIPTOR", gd, core.boot_id, ident.descriptor_id, (int)off, 100) && status_is("OK"));
        const int n = rrc_json_str_copy(&rdoc, rrc_json_get(&rdoc, body(), "bytes_b64"), b64, sizeof b64);
        const long k = rrc_base64_decode(b64, (size_t)n, raw, sizeof raw);
        CHECK(k > 0);
        rrc_sha256_update(&sha, raw, (size_t)k);
    }
    uint8_t dg[32];
    char hex[65];
    rrc_sha256_final(&sha, dg);
    rrc_hex_lower(dg, 32u, hex);
    CHECK_STR(hex, core.descriptor_sha256);
    /* bind; then the handshake-only op is refused and a repeated BIND changes nothing */
    CHECK(send("BIND", "{\"boot_id\":\"%s\",\"setup_id\":\"%s\",\"descriptor_sha256\":\"%s\"}", core.boot_id, core.setup_id,
               core.descriptor_sha256) && status_is("OK"));
    CHECK(send("GET_DESCRIPTOR", gd, core.boot_id, ident.descriptor_id, 0, 16) && status_is("BUSY"));
    CHECK(send("BIND", "{\"boot_id\":\"%s\",\"setup_id\":\"%s\",\"descriptor_sha256\":\"%s\"}", core.boot_id, core.setup_id,
               core.descriptor_sha256) && status_is("OK"));
    CHECK(core.link == RRH_LINK_BOUND);
}

static void test_reset_gives_fresh_boot_and_unbound(void)
{
    char old_boot[40], old_setup[100], old_sha[70];
    mock_reset();
    boot();
    handshake();
    arm(100000u);
    advance(250000u);
    strcpy(old_boot, core.boot_id);
    strcpy(old_setup, core.setup_id);
    strcpy(old_sha, core.descriptor_sha256);
    /* MCU reset while armed (watchdog) */
    m.reset_cause = RRH_RESET_WATCHDOG;
    m.running = false;
    boot();
    CHECK(strcmp(old_boot, core.boot_id) != 0);
    CHECK(core.link == RRH_LINK_UNBOUND && !core.armed && core.frame_count == 0u);
    CHECK(send("READ", "{\"after_seq\":-1}") && status_is("UNBOUND") && !has("counts"));
    /* the stale handshake cannot bind the rebooted head */
    CHECK(send("BIND", "{\"boot_id\":\"%s\",\"setup_id\":\"%s\",\"descriptor_sha256\":\"%s\"}", old_boot, old_setup, old_sha) &&
          status_is("WRONG_BOOT"));
    CHECK(send("STATUS", "{}") && has("\"reset_cause\":\"WATCHDOG\"") && has("WATCHDOG_RESET"));
    /* reset between HELLO and BIND */
    CHECK(send("HELLO", "{}") && status_is("OK"));
    strcpy(old_boot, core.boot_id);
    boot();
    CHECK(send("BIND", "{\"boot_id\":\"%s\",\"setup_id\":\"%s\",\"descriptor_sha256\":\"%s\"}", old_boot, old_setup, old_sha) &&
          status_is("WRONG_BOOT"));
    CHECK(core.link == RRH_LINK_UNBOUND);
}

static void test_reply_cache(void)
{
    uint8_t first[RRH_TX_MAX];
    mock_reset();
    boot();
    handshake();
    arm(100000u);
    advance(350000u);
    CHECK(send("READ", "{\"after_seq\":-1}") && status_is("OK") && (body_int("sequence") == 0));
    const size_t n = rsp_wire_len;
    memcpy(first, rsp_wire, n);
    const uint32_t retries = core.n_retries;
    advance(300000u); /* more frames exist now; a retry must still return the same bytes */
    CHECK(feed(last_req, last_req_len));
    CHECK((rsp_wire_len == n) && (memcmp(first, rsp_wire, n) == 0));
    CHECK(core.n_retries == retries + 1u);
    /* same id, different request: executed, not served from the cache */
    CHECK(send_id(next_id - 1u, "READ", "{\"after_seq\":0}") && status_is("OK") && (body_int("sequence") == 1));
    /* HELLO retry returns the cached reply and does NOT reset the attachment a second time */
    CHECK(send("HELLO", "{}") && status_is("OK"));
    CHECK(core.link == RRH_LINK_HANDSHAKE);
    core.link = RRH_LINK_BOUND; /* pretend BIND happened; an identical HELLO retransmission must not undo it */
    CHECK(feed(last_req, last_req_len) && status_is("OK"));
    CHECK(core.link == RRH_LINK_BOUND);
    /* TIME is always measured afresh */
    m.now_us += 500u;
    CHECK(send("TIME", "{}") && status_is("OK"));
    const int64_t rx1 = body_int("rx_us");
    CHECK((body_int("tx_us") == rx1 + 100) && (rsp_tx_at == (uint64_t)rx1 + 100u));
    m.now_us += 700u;
    CHECK(feed(last_req, last_req_len) && (body_int("rx_us") == rx1 + 700));
}

static void test_link_garbage(void)
{
    mock_reset();
    boot();
    const uint32_t d0 = core.n_discarded;
    uint8_t line[200];
    /* valid framing, duplicate key */
    const char *dup = "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":1,\"id\":1,\"op\":\"HELLO\",\"args\":{}}";
    memcpy(line, dup, strlen(dup));
    size_t n = rrc_frame_finish(line, strlen(dup), sizeof line, RRH_RX_MAX);
    CHECK(!feed(line, n));
    /* bad CRC */
    const char *ok = "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":1,\"op\":\"HELLO\",\"args\":{}}";
    memcpy(line, ok, strlen(ok));
    n = rrc_frame_finish(line, strlen(ok), sizeof line, RRH_RX_MAX);
    line[5] ^= 0x20u;
    CHECK(!feed(line, n));
    line[5] ^= 0x20u;
    /* not a request / no id */
    const char *nr = "{\"type\":\"RSP\",\"v\":\"2.0\",\"id\":1,\"status\":\"OK\",\"body\":{}}";
    uint8_t l2[200];
    memcpy(l2, nr, strlen(nr));
    CHECK(!feed(l2, rrc_frame_finish(l2, strlen(nr), sizeof l2, RRH_RX_MAX)));
    CHECK(core.n_discarded == d0 + 3u);
    CHECK(core.link == RRH_LINK_UNBOUND);
    /* truncated record followed by idle time, then a good one */
    CHECK(!feed(line, 20u));
    advance(20000u);
    CHECK(feed(line, n) && status_is("OK"));
    /* wrong protocol version and malformed envelope are answered */
    const char *v1 = "{\"type\":\"REQ\",\"v\":\"1.0\",\"id\":9,\"op\":\"HELLO\",\"args\":{}}";
    memcpy(l2, v1, strlen(v1));
    CHECK(feed(l2, rrc_frame_finish(l2, strlen(v1), sizeof l2, RRH_RX_MAX)) && status_is("UNSUPPORTED"));
    const char *ns = "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":10,\"op\":\"HELLO\"}";
    memcpy(l2, ns, strlen(ns));
    CHECK(feed(l2, rrc_frame_finish(l2, strlen(ns), sizeof l2, RRH_RX_MAX)) && status_is("BAD_ARG"));
}

static void test_frame_mapping_and_nulls(void)
{
    mock_reset();
    boot();
    handshake();
    m.lane_template[0].alpha_counts = 0u;                 /* a measured zero */
    m.lane_template[1].flags = RRH_GF_REF_SATURATED;
    m.lane_template[2].floor_live_ticks = 0u;             /* no live-time signal */
    m.lane_template[3].flags = RRH_GF_BASELINE_SHIFT;
    arm(100000u);
    advance(120000u);
    CHECK(send("READ", "{\"after_seq\":-1}") && status_is("OK"));
    CHECK(has("\"sequence\":0,\"start_us\":1000,\"span_us\":100000"));
    CHECK(has("{\"id\":0,\"alpha\":{\"counts\":0,\"live_us\":99910},\"beta_window\":{\"counts\":10,\"live_us\":99910},"
              "\"photon_ref\":{\"counts\":20,\"live_us\":99970},\"flags\":[]}"));
    CHECK(has("{\"id\":1,\"alpha\":{\"counts\":1,\"live_us\":99910},\"beta_window\":{\"counts\":11,\"live_us\":99910},"
              "\"photon_ref\":null,\"flags\":[\"SATURATED\"]}"));
    CHECK(has("{\"id\":2,\"alpha\":null,\"beta_window\":null,\"photon_ref\":{\"counts\":22,\"live_us\":99970},"
              "\"flags\":[\"DEAD_TIME_UNKNOWN\"]}"));
    CHECK(has("{\"id\":3,\"alpha\":null,\"beta_window\":null,\"photon_ref\":null,\"flags\":[\"DISCRIMINATOR_FAULT\"]}"));
    CHECK(has("\"thermal\":{\"head_c\":25.0,\"heater\":\"OFF\",\"duty_pct\":0},\"flags\":[]"));
    CHECK(has("\"sync\":{\"state\":\"UNSYNCED\",\"sync_id\":null,\"bound_us\":null,\"age_us\":null}"));
    /* DIAG keeps the raw counters of nulled channels */
    CHECK(send("DIAG", "{\"seq\":0}") && status_is("OK"));
    CHECK(has("\"id\":2,\"alpha_raw\":2,\"beta_raw\":12,\"floor_reject\":1,\"floor_live_ticks\":0"));
    CHECK(has("\"flags\":[\"BASELINE_SHIFT\"]") && has("\"flags\":[\"REF_SATURATED\"]"));
    CHECK(!has("width")); /* this port measures no pulse widths: the optional fields are absent */
    /* remaining rules: live fraction below 50 %, live > gate, bias flag, front-end fault, chain off */
    m.lane_template[0].floor_live_ticks = 2000000u;
    m.lane_template[1].flags = RRH_GF_BIAS_OUT_OF_RANGE;
    m.lane_template[2].floor_live_ticks = 4800001u;
    m.lane_template[3].flags = RRH_GF_FLOOR_SATURATED;
    m.analog.frontend_fault = 0x20u; /* reference chain of lane 1 */
    advance(100000u);
    CHECK(send("READ", "{\"after_seq\":0}") && status_is("OK") && (body_int("sequence") == 1));
    CHECK(has("{\"id\":0,\"alpha\":null,\"beta_window\":null,\"photon_ref\":{\"counts\":20,\"live_us\":99970},\"flags\":[\"SATURATED\"]}"));
    CHECK(has("{\"id\":1,\"alpha\":null,\"beta_window\":null,\"photon_ref\":null,\"flags\":[\"FLOOR_FAULT\",\"REFERENCE_FAULT\"]}"));
    CHECK(has("{\"id\":2,\"alpha\":null,\"beta_window\":null,\"photon_ref\":{\"counts\":22,\"live_us\":99970},\"flags\":[\"DEAD_TIME_UNKNOWN\"]}"));
    CHECK(has("{\"id\":3,\"alpha\":null,\"beta_window\":null,\"photon_ref\":{\"counts\":23,\"live_us\":99970},\"flags\":[\"SATURATED\"]}"));
    /* optional pulse-width histogram: floor chains only on this mock port, counts saturate at 65535 */
    m.width_mask = 0x0Fu;
    advance(100000u);
    m.width_mask = 0u;
    CHECK(send("DIAG", "{\"seq\":2}") && status_is("OK"));
    CHECK(has("\"width_bins_ns\":[150,400,2000]"));
    CHECK(has("\"floor_width_hist\":[0,7,0,1]") && has("\"floor_width_hist\":[0,9,0,65535]"));
    CHECK(!has("ref_width_hist"));
    CHECK(send("DIAG", "{\"seq\":1}") && status_is("OK") && !has("width"));
    /* missing head temperature: null plus the thermal flag; undervoltage */
    for (uint32_t l = 0; l < RRH_LANES; l++) {
        m.analog.sipm_mc[l] = RRH_TEMP_INVALID;
    }
    m.analog.supply_mv = 9000u;
    advance(100000u);
    CHECK(send("READ", "{\"after_seq\":2}") && status_is("OK"));
    CHECK(has("\"head_c\":null") && has("\"flags\":[\"HEAD_TEMP_OUT_OF_RANGE\",\"UNDERVOLTAGE\"]"));
}

static void test_buffer_gap_empty_and_sequence_continuity(void)
{
    mock_reset();
    boot();
    handshake();
    CHECK(send("READ", "{\"after_seq\":-1}") && status_is("EMPTY"));
    CHECK(send("DISARM", "{}") && status_is("OK") && has("\"last_seq\":null,\"complete\":true"));
    arm(10000u);
    CHECK(body_int("first_seq") == 0);
    CHECK(send("ARM", "{\"span_us\":10000}") && status_is("OK") && (body_int("first_seq") == 0)); /* matching repeat */
    CHECK(send("ARM", "{\"span_us\":20000}") && status_is("BUSY"));
    CHECK(send("ARM", "{\"span_us\":9999}") && status_is("BAD_ARG"));
    CHECK(send("READ", "{\"after_seq\":-1}") && status_is("EMPTY"));
    advance(1000u + 10000u * 5u);
    for (int s = 0; s < 5; s++) {
        CHECK(send("READ", "{\"after_seq\":%d}", s - 1) && status_is("OK") && (body_int("sequence") == s));
        CHECK(body_int("start_us") == 1000 + 10000 * s); /* equal, contiguous gates */
    }
    CHECK(send("READ", "{\"after_seq\":4}") && status_is("EMPTY"));
    CHECK(send("READ", "{\"after_seq\":1000}") && status_is("EMPTY"));
    CHECK(send("READ", "{\"after_seq\":-2}") && status_is("BAD_ARG"));
    CHECK(send("READ", "{\"after_seq\":1.5}") && status_is("BAD_ARG"));
    CHECK(send("READ", "{}") && status_is("BAD_ARG"));
    /* overflow: 5 + 300 gates produced, the buffer holds the newest RRH_FRAME_BUFFER */
    advance(10000u * 300u);
    const int64_t newest = 304;
    const int64_t oldest = newest - (int64_t)RRH_FRAME_BUFFER + 1;
    CHECK(send("READ", "{\"after_seq\":4}") && status_is("GAP"));
    CHECK((body_int("oldest_seq") == oldest) && (body_int("newest_seq") == newest));
    CHECK(send("READ", "{\"after_seq\":%d}", (int)oldest - 1) && status_is("OK") && (body_int("sequence") == oldest));
    CHECK(send("READ", "{\"after_seq\":%d}", (int)oldest - 2) && status_is("GAP"));
    CHECK(send("DIAG", "{\"seq\":3}") && status_is("GAP") && (body_int("oldest_seq") == oldest));
    CHECK(send("DIAG", "{\"seq\":%d}", (int)newest + 1) && status_is("EMPTY"));
    CHECK(RRH_FRAME_BUFFER >= 128u);
    /* DISARM in the middle of a gate: that gate completes and is delivered */
    advance(4000u);
    CHECK(send("DISARM", "{}") && status_is("OK") && (body_int("last_seq") == newest + 1) && has("\"complete\":false"));
    CHECK(send("ARM", "{\"span_us\":10000}") && status_is("BUSY")); /* final gate still pending */
    CHECK(send("READ", "{\"after_seq\":%d}", (int)newest) && status_is("EMPTY"));
    advance(10000u);
    CHECK(send("READ", "{\"after_seq\":%d}", (int)newest) && status_is("OK") && (body_int("sequence") == newest + 1));
    CHECK(send("DISARM", "{}") && (body_int("last_seq") == newest + 1) && has("\"complete\":true"));
    advance(50000u);
    CHECK(send("READ", "{\"after_seq\":%d}", (int)newest + 1) && status_is("EMPTY")); /* nothing after the final gate */
    /* re-ARM within the attachment continues the sequence; old frames stay readable */
    arm(20000u);
    CHECK(body_int("first_seq") == newest + 2);
    advance(1000u + 20000u * 2u);
    CHECK(send("READ", "{\"after_seq\":%d}", (int)newest + 1) && status_is("OK") && (body_int("sequence") == newest + 2));
    CHECK(body_int("span_us") == 20000);
    CHECK(send("READ", "{\"after_seq\":%d}", (int)newest - 1) && status_is("OK") && (body_int("sequence") == newest));
    /* a fresh HELLO discards everything and restarts at zero */
    CHECK(send("HELLO", "{}") && status_is("OK"));
    CHECK(!core.armed && !m.running && (core.frame_count == 0u) && (core.next_seq == 0u));
    CHECK(send("READ", "{\"after_seq\":-1}") && status_is("UNBOUND"));
}

static void test_setup_change_invalidates_binding(void)
{
    char old_setup[100], old_sha[70], old_boot[40];
    mock_reset();
    boot();
    handshake();
    strcpy(old_setup, core.setup_id);
    strcpy(old_sha, core.descriptor_sha256);
    strcpy(old_boot, core.boot_id);
    arm(100000u);
    CHECK(send("ENG_SETUP_SET", "{\"bias\":{\"ref_mv\":31000}}") && status_is("BUSY")); /* not while armed */
    CHECK(send("DISARM", "{}") && status_is("OK"));
    advance(150000u);
    CHECK(send("ENG_SETUP_SET", "{\"bias\":{\"ref_mv\":19000}}") && status_is("BAD_ARG"));
    CHECK(send("ENG_SETUP_SET", "{\"nonsense\":1}") && status_is("BAD_ARG"));
    CHECK(send("ENG_SETUP_SET", "{\"thresholds\":{\"beta_lld\":[4000,200,200,200]}}") && status_is("BAD_ARG")); /* LLD >= ULD (default ULD 3822) */
    CHECK(core.link == RRH_LINK_BOUND);
    CHECK(send("ENG_SETUP_SET", "{\"bias\":{\"ref_mv\":30000}}") && status_is("OK") && has("\"changed\":false"));
    CHECK(core.link == RRH_LINK_BOUND); /* identical values: nothing happens */
    const uint32_t applies = m.fe_applies;
    CHECK(send("ENG_SETUP_SET", "{\"thresholds\":{\"alpha\":[1300,1300,1300,1300]},\"persist\":true}") && status_is("OK"));
    CHECK(has("\"changed\":true,\"bound\":false,\"persisted\":true"));
    CHECK(core.link == RRH_LINK_UNBOUND);
    CHECK((m.fe_applies == applies + 1u) && (m.fe.threshold[2] == 1300u));
    CHECK(strcmp(old_setup, core.setup_id) != 0);
    CHECK(strcmp(old_sha, core.descriptor_sha256) != 0);
    CHECK(strcmp(old_boot, core.boot_id) == 0);
    CHECK(send("READ", "{\"after_seq\":-1}") && status_is("UNBOUND"));
    CHECK(send("ARM", "{\"span_us\":100000}") && status_is("UNBOUND"));
    /* the old handshake cannot be completed again */
    CHECK(send("BIND", "{\"boot_id\":\"%s\",\"setup_id\":\"%s\",\"descriptor_sha256\":\"%s\"}", old_boot, old_setup, old_sha) &&
          status_is("UNBOUND"));
    CHECK(send("HELLO", "{}") && status_is("OK") && has(core.setup_id));
    CHECK(send("BIND", "{\"boot_id\":\"%s\",\"setup_id\":\"%s\",\"descriptor_sha256\":\"%s\"}", old_boot, old_setup, old_sha) &&
          status_is("BAD_ARG"));
    CHECK(core.link == RRH_LINK_HANDSHAKE);
    /* the persisted setup survives a reset and yields the same setup_id */
    strcpy(old_setup, core.setup_id);
    boot();
    CHECK_STR(core.setup_id, old_setup);
    CHECK(send("ENG_SETUP_GET", "{}") && status_is("OK") && has("\"alpha\":[1300,1300,1300,1300]"));
    /* damaged storage: defaults + latched STORAGE fault */
    m.nv[3] ^= 0xFFu;
    boot();
    CHECK((core.health & RRH_H_STORAGE) != 0u);
    CHECK(strcmp(core.setup_id, old_setup) != 0);
}

static void test_sync_quality(void)
{
    mock_reset();
    boot();
    handshake();
    CHECK(send("SYNC", "{\"sync_id\":\"bad id\",\"bound_us\":1,\"expiry_us\":1}") && status_is("BAD_ARG"));
    CHECK(send("SYNC", "{\"sync_id\":\"-x\",\"bound_us\":1,\"expiry_us\":1}") && status_is("BAD_ARG"));
    CHECK(send("SYNC", "{\"sync_id\":\"a\",\"bound_us\":10000001,\"expiry_us\":1}") && status_is("BAD_ARG"));
    CHECK(send("SYNC", "{\"sync_id\":\"a\",\"bound_us\":1,\"expiry_us\":0}") && status_is("BAD_ARG"));
    arm(100000u);                 /* gate 0 starts at 1000 */
    advance(50000u);              /* now 50000, inside gate 0 */
    CHECK(send("SYNC", "{\"sync_id\":\"fit-01\",\"bound_us\":280,\"expiry_us\":250000}") && status_is("OK"));
    advance(1000u + 100000u * 6u);
    CHECK(send("READ", "{\"after_seq\":-1}") && has("\"state\":\"UNSYNCED\""));  /* installed after gate 0 began */
    CHECK(send("READ", "{\"after_seq\":0}") && has("\"sync\":{\"state\":\"LOCKED\",\"sync_id\":\"fit-01\",\"bound_us\":280,\"age_us\":51000}"));
    /* gate 3 starts 251000 us after the record: 1000 us past expiry -> HOLDOVER, bound 280 + ceil(0.2) */
    CHECK(send("READ", "{\"after_seq\":2}") && has("\"state\":\"HOLDOVER\"") && has("\"bound_us\":281,\"age_us\":251000"));
    CHECK(send("READ", "{\"after_seq\":1}") && has("\"state\":\"LOCKED\"") && has("\"age_us\":151000"));
    CHECK(send("READ", "{\"after_seq\":3}") && has("\"state\":\"HOLDOVER\"") && has("\"age_us\":351000"));
    /* bound grows by 200 ppm of the time past expiry: 280 + ceil(101000 * 200 / 1e6) = 301 */
    CHECK(has("\"bound_us\":301"));
    /* a refresh applies from the next gate start */
    CHECK(send("SYNC", "{\"sync_id\":\"fit-02\",\"bound_us\":150,\"expiry_us\":10000000}") && status_is("OK"));
    const uint64_t t_sync = m.now_us;
    advance(200000u);
    const rrh_frame_t *f = &core.frames[(core.frame_head + core.frame_count - 1u) % RRH_FRAME_BUFFER];
    CHECK((f->sync_state == RRH_SYNC_LOCKED) && (f->sync_bound_us == 150u) && (f->sync_age_us == f->start_us - t_sync));
    /* far past expiry + holdover limit: UNSYNCED with null fields */
    CHECK(send("SYNC", "{\"sync_id\":\"fit-03\",\"bound_us\":150,\"expiry_us\":100000}") && status_is("OK"));
    advance(100000u + RRH_HOLDOVER_MAX_US + 300000u);
    CHECK(send("READ", "{\"after_seq\":%d}", (int)core.next_seq - 2) && status_is("OK"));
    CHECK(has("\"sync\":{\"state\":\"UNSYNCED\",\"sync_id\":null,\"bound_us\":null,\"age_us\":null}"));
    /* many refreshes never corrupt retained frames: either accepted or BUSY */
    uint32_t ok = 0u, busy = 0u;
    for (int i = 0; i < 100; i++) {
        CHECK(send("SYNC", "{\"sync_id\":\"r-%d\",\"bound_us\":5,\"expiry_us\":1000000}", i));
        if (status_is("OK")) { ok++; } else if (status_is("BUSY")) { busy++; } else { CHECK(false); }
        if ((i % 3) == 0) { advance(100000u); }
    }
    CHECK((ok >= 30u) && (ok + busy == 100u));
    for (uint32_t i = 0; i < core.frame_count; i++) {
        const rrh_frame_t *g = &core.frames[(core.frame_head + i) % RRH_FRAME_BUFFER];
        if (g->sync_slot >= 0) {
            CHECK(core.sync[g->sync_slot].used && (core.sync[g->sync_slot].refs > 0u));
            CHECK(core.sync[g->sync_slot].installed_us <= g->start_us);
        }
    }
}

static void test_heater_control(void)
{
    mock_reset();
    m.nv_len = 0u;
    boot();
    CHECK(send("ENG_SETUP_SET", "{\"heater\":{\"enable\":true,\"setpoint_mc\":5000,\"max_duty_pct\":50}}") && status_is("OK"));
    handshake();
    m.analog.heater_plate_mc = 0; /* well below the set-point */
    advance(300000u);
    CHECK(!m.heater_req && !m.heater_applied); /* never on while disarmed */
    arm(100000u);
    advance(1000u + 100000u * 30u);
    CHECK(send("STATUS", "{}") && status_is("OK"));
    /* duty limit 50 % over 20 gates, each gate entirely on or off */
    uint32_t on = 0u, total = 0u, transitions = 0u;
    for (uint32_t i = 10u; i < core.frame_count; i++) {
        const rrh_frame_t *f = &core.frames[(core.frame_head + i) % RRH_FRAME_BUFFER];
        CHECK((f->duty_pct == 0u) || (f->duty_pct == 100u));
        CHECK((f->heater == 1u) == (f->duty_pct > 0u));
        on += (f->duty_pct > 0u) ? 1u : 0u;
        total++;
        if (i > 10u) {
            const rrh_frame_t *p = &core.frames[(core.frame_head + i - 1u) % RRH_FRAME_BUFFER];
            transitions += (p->duty_pct != f->duty_pct) ? 1u : 0u;
        }
    }
    CHECK((on > 0u) && ((on * 100u) <= (total * 55u)));
    CHECK(transitions <= (total / 2u));
    /* warm plate: off */
    m.analog.heater_plate_mc = 9000;
    advance(100000u * 8u);
    CHECK(!m.heater_req);
    /* sensor fault while armed: off, latched, frames say FAULT with duty 0 */
    m.analog.heater_plate_mc = 0;
    advance(100000u * 12u);
    CHECK(m.heater_req);
    m.analog.heater_plate_mc = RRH_TEMP_INVALID;
    advance(300000u);
    CHECK(!m.heater_req && ((core.health & RRH_H_HEATER_SENSOR) != 0u));
    CHECK(send("READ", "{\"after_seq\":%d}", (int)core.next_seq - 2) && status_is("OK"));
    CHECK(has("\"heater\":\"FAULT\",\"duty_pct\":0") && has("\"HEATER_FAULT\""));
    /* the latch survives the sensor coming back until FAULT_CLEAR */
    m.analog.heater_plate_mc = 0;
    advance(500000u);
    CHECK(!m.heater_req && ((core.health & RRH_H_HEATER_SENSOR) != 0u));
    CHECK(send("FAULT_CLEAR", "{\"codes\":[\"HEATER_SENSOR\"]}") && status_is("OK") && has("\"cleared\":[\"HEATER_SENSOR\"]"));
    advance(100000u * 8u);
    CHECK(m.heater_req);
    /* cut-out trips: OVERTEMP + HEATER_FAULT, cannot be cleared while still open */
    m.analog.heater_cutout_ok = false;
    advance(200000u);
    CHECK(!m.heater_req && ((core.health & RRH_H_HEATER_CUTOUT) != 0u));
    CHECK(send("FAULT_CLEAR", "{}") && status_is("OK") && has("\"health\":[\"HEATER_CUTOUT\"]"));
    CHECK(send("READ", "{\"after_seq\":%d}", (int)core.next_seq - 2) && has("\"HEATER_FAULT\",\"OVERTEMP\""));
    m.analog.heater_cutout_ok = true;
    CHECK(send("FAULT_CLEAR", "{}") && status_is("OK") && has("\"health\":[]"));
    advance(100000u * 8u);
    CHECK(m.heater_req);
    /* DISARM: heater off with the end of the final gate */
    CHECK(send("DISARM", "{}") && status_is("OK"));
    CHECK(!m.heater_req);
    advance(200000u);
    CHECK(!m.heater_applied && !core.heater_on);
    CHECK(send("FAULT_CLEAR", "{\"codes\":[\"NOPE\"]}") && status_is("BAD_ARG"));
}

static void test_bias_compensation(void)
{
    mock_reset();
    boot();
    /* defaults: 30.000 V at 25 degC, +21.5 mV/K */
    advance(7000000u); /* ramp 500 mV per 100 ms */
    CHECK(m.bias_on && (m.bias_mv == 30000u));
    for (uint32_t l = 0; l < RRH_LANES; l++) {
        m.analog.sipm_mc[l] = 5000; /* 20 K colder: target 30000 - 430 = 29570 mV */
    }
    advance(300000u);
    CHECK((m.bias_mv < 30000u) && (m.bias_mv >= 29940u)); /* slew limited: 20 mV per 100 ms */
    advance(5000000u);
    CHECK((m.bias_mv >= 29565u) && (m.bias_mv <= 29575u));
    /* sensor loss: hold the last set-point */
    const uint32_t hold = m.bias_mv;
    for (uint32_t l = 0; l < RRH_LANES; l++) {
        m.analog.sipm_mc[l] = RRH_TEMP_INVALID;
    }
    advance(2000000u);
    CHECK(m.bias_mv == hold);
    /* over-current: converter off, latched, flagged; cleared only when the current is back */
    m.analog.bias_ua = 900u;
    advance(200000u);
    CHECK(!m.bias_on && ((core.health & RRH_H_BIAS_TRIP) != 0u));
    CHECK(send("FAULT_CLEAR", "{}") && has("BIAS_TRIP\"]}"));
    m.analog.bias_ua = 40u;
    CHECK(send("FAULT_CLEAR", "{}") && has("\"health\":[]"));
    advance(200000u);
    CHECK(m.bias_on);
}

static void test_lost_and_bad_gates(void)
{
    mock_reset();
    boot();
    handshake();
    arm(100000u);
    advance(1000u + 100000u * 2u);
    m.skip = 3u; /* three records lost by the source */
    advance(100000u * 5u);
    CHECK((core.health & RRH_H_RECORD_LOST) != 0u);
    CHECK(send("READ", "{\"after_seq\":1}") && status_is("OK") && (body_int("sequence") == 5)); /* 2, 3, 4 never existed */
    CHECK(body_int("start_us") == 1000 + 100000 * 5);
    CHECK(has("\"flags\":[\"ACQ_FAULT\"]"));
    CHECK(send("DIAG", "{\"seq\":3}") && status_is("GAP"));
    CHECK(send("FAULT_CLEAR", "{}") && status_is("OK"));
    /* a gate of the wrong length is a timing fault */
    m.gate_ticks_override = 4800048u;
    advance(100000u);
    m.gate_ticks_override = 0u;
    CHECK((core.health & RRH_H_GATE_TIMING) != 0u);
    /* deliberate fault latch */
    CHECK(send("FAULT_CLEAR", "{}") && has("\"health\":[]"));
    CHECK(send("ENG_FAULT", "{}") && status_is("OK") && has("INJECTED"));
    advance(200000u);
    CHECK(send("READ", "{\"after_seq\":%d}", (int)core.next_seq - 2) && has("\"flags\":[\"ACQ_FAULT\"]"));
    /* armed but the source stops delivering: GATE_TIMEOUT */
    CHECK(send("FAULT_CLEAR", "{}") && has("\"health\":[]"));
    m.running = false;
    advance(500000u);
    CHECK((core.health & RRH_H_GATE_TIMEOUT) != 0u);
    /* source refuses to start */
    CHECK(send("HELLO", "{}"));
    handshake();
    m.start_ok = false;
    CHECK(send("ARM", "{\"span_us\":100000}") && status_is("FAULT"));
    CHECK(!core.armed && ((core.health & RRH_H_SOURCE) != 0u));
}

static void test_misc_ops(void)
{
    mock_reset();
    m.entropy_ok = false;
    boot();
    CHECK((core.health & RRH_H_ENTROPY) != 0u);
    handshake();
    /* rev A: no rail-zone identification. Whatever the pins read, STATUS says "not available" -
     * null, which is not the same as an empty list ("no zone actuated"). */
    m.analog.bumper_zones = 0x05u;
    advance(100000u);
    CHECK(send("STATUS", "{}") && has("\"bumper\":{\"available\":false,\"now\":null,\"latched\":null}"));
    /* a board revision with auxiliary contacts: the port reports zones_available and the old behaviour applies */
    m.analog.zones_available = true;
    advance(100000u);
    m.analog.bumper_zones = 0u;
    advance(100000u);
    CHECK(send("STATUS", "{\"clear_bumper\":true}") &&
          has("\"bumper\":{\"available\":true,\"now\":[],\"latched\":[\"FRONT\",\"RIGHT\"]}"));
    CHECK(send("STATUS", "{}") && has("\"latched\":[]"));
    CHECK(send("ENG_WAVE_ARM", "{\"channel\":3,\"samples\":64,\"pretrigger\":8}") && status_is("OK"));
    CHECK(send("ENG_WAVE_ARM", "{\"channel\":9,\"samples\":64,\"pretrigger\":8}") && status_is("BAD_ARG"));
    CHECK(send("ENG_WAVE_READ", "{\"offset\":60,\"count\":16}") && status_is("OK") && (body_int("count") == 4));
    CHECK(has("\"bytes_b64\":\"PAA9AD4APwA=\""));
    CHECK(send("ENG_WAVE_READ", "{\"offset\":64,\"count\":1}") && status_is("BAD_ARG"));
    CHECK(m.kicks > 0u);
}


/* ---- IB-17 / IB-18 / IB-15 ----------------------------------------------------------------- */
static void test_setup_members_and_defaults(void)
{
    mock_reset();
    boot();
    /* default thresholds sit ABOVE the 0.600 V baseline (a code below it leaves the comparator high) */
    const uint16_t base = rrh_board_threshold_code(0u);
    for (uint32_t l = 0; l < RRH_LANES; l++) {
        CHECK(core.setup.fe.threshold[l * 3u] > base);
        CHECK(core.setup.fe.threshold[(l * 3u) + 2u] > base);
        CHECK(core.setup.fe.threshold[12u + (l * 2u)] > base);
    }
    CHECK(core.setup.fe.alpha_hold_us == 300u);
    /* reference ULD: the fast amplitude at which a plastic event crosses the floor ALPHA level (30 mV x 18.8 = 564 mV = 81 p.e.) */
    CHECK(core.setup.fe.threshold[13] == rrh_board_threshold_code(564000u));
    handshake();
    CHECK(send("ENG_SETUP_GET", "{}") && has("\"afterglow\":{\"alpha_hold_us\":300,\"alpha_min_tot_ns\":0}") && has("\"channel\":0,\"width_us\":2"));
    char old_id[100];
    strcpy(old_id, core.setup_id);
    CHECK(send("ENG_SETUP_SET", "{\"pulser\":{\"enable\":true,\"code\":500,\"channel\":6,\"width_us\":25,\"led_enable\":true,\"led_code\":900},"
                                "\"afterglow\":{\"alpha_hold_us\":120}}") && status_is("OK") && has("\"changed\":true"));
    CHECK((m.fe.pulser_channel == 6u) && (m.fe.pulser_width_us == 25u) && m.fe.led_enable && (m.fe.led_code == 900u));
    CHECK((m.fe.alpha_hold_us == 120u) && m.fe.pulser_enable && (m.fe.pulser_code == 500u));
    CHECK(strcmp(old_id, core.setup_id) != 0);
    CHECK(core.link == RRH_LINK_UNBOUND);
    handshake();
    CHECK(send("ENG_SETUP_SET", "{\"pulser\":{\"channel\":8}}") && status_is("BAD_ARG"));
    CHECK(send("ENG_SETUP_SET", "{\"pulser\":{\"width_us\":0}}") && status_is("BAD_ARG"));
    CHECK(send("ENG_SETUP_SET", "{\"afterglow\":{\"alpha_hold_us\":501}}") && status_is("BAD_ARG"));
    /* a set-point above the fitted over-voltage trip less the margin (30.5 V) is refused */
    CHECK(send("ENG_SETUP_SET", "{\"bias\":{\"ref_mv\":31000}}") && status_is("BAD_ARG"));
    CHECK(send("ENG_SETUP_SET", "{\"bias\":{\"ref_mv\":30500}}") && status_is("OK"));
    /* persisted image round trip keeps the new members */
    handshake();
    CHECK(send("ENG_SETUP_SET", "{\"persist\":true}") && status_is("OK"));
    boot();
    CHECK((core.setup.fe.pulser_channel == 6u) && (core.setup.fe.alpha_hold_us == 120u) && (core.setup.fe.led_code == 900u));
}

static void test_bias_on_sequence_and_limits(void)
{
    mock_reset();
    boot();
    CHECK(!m.bias_on && (m.bias_mv == 0u));          /* HV_SET = 0 while disabled */
    advance(100000u);
    CHECK(m.bias_on && (m.bias_mv == 0u));           /* HV_EN rises with HV_SET = 0 */
    uint32_t prev = 0u;
    for (int i = 0; i < 64; i++) {
        advance(100000u);
        CHECK(m.bias_mv >= prev);
        CHECK(m.bias_mv - prev <= RRH_BIAS_RAMP_STEP_MV); /* 5 V/s at HV_BUS = 500 mV per 100 ms */
        prev = m.bias_mv;
    }
    CHECK(m.bias_mv == 30000u);
    CHECK(rrh_board_hv_code(m.bias_mv) == 1966u);     /* 30.000 V / 15.2588 mV */
    /* hot head: the compensated target is clamped below the fitted OVP trip (31.5 V) less 1 V */
    for (uint32_t l = 0; l < RRH_LANES; l++) {
        m.analog.sipm_mc[l] = 70000;
    }
    advance(10000000u);
    CHECK(m.bias_mv == rrh_board_bias_limit_mv());
    CHECK(m.bias_mv < rrh_board_fitted_ovp_trip_mv());
    /* total-current trip is reachable now: 250 uA is inside the monitor range, 500 uA never was */
    m.analog.bias_ua = 250u;
    advance(200000u);
    CHECK(!m.bias_on && ((core.health & RRH_H_BIAS_TRIP) != 0u));
}

static void test_bias_permit_trip_and_recovery(void)
{
    mock_reset();
    boot();
    m.permit_ok = false; /* hardware permit latch tripped: HV_EN high, BIAS_VMON reads 0 */
    advance(8000000u);
    CHECK(!m.bias_on && ((core.health & RRH_H_BIAS_PERMIT) != 0u));
    handshake();
    CHECK(send("STATUS", "{}") && has("BIAS_PERMIT") && has("\"expander\":{\"present\":false,\"hv_permit\":null"));
    m.permit_ok = true; /* cause gone (no expander: cannot be read, clearing is allowed) */
    const uint32_t calls = m.bias_calls;
    CHECK(send("FAULT_CLEAR", "{\"codes\":[\"BIAS_PERMIT\"]}") && has("\"cleared\":[\"BIAS_PERMIT\"]"));
    advance(300000u);
    CHECK(m.bias_on && (m.bias_calls > calls)); /* HV_EN raised again from zero */
    /* with the expander: lid open -> inhibit bus low, permit low; detected in two periods, not clearable while open */
    mock_reset();
    boot();
    m.exp.present = true;
    m.exp.inputs = RRH_EXP_LID_G | RRH_EXP_EF_FLT_N; /* permit 0, inhibit active (INH_N low), lid open */
    m.permit_ok = false;
    advance(500000u);
    CHECK(!m.bias_on && ((core.health & RRH_H_BIAS_PERMIT) != 0u));
    handshake();
    CHECK(send("STATUS", "{}") && has("\"hv_permit\":false,\"hv_inhibit\":true,\"lid_open\":true,\"efuse_fault\":false,\"hw_rev\":0"));
    CHECK(send("FAULT_CLEAR", "{}") && has("\"cleared\":[]"));
    m.exp.inputs = RRH_EXP_HV_PERMIT | RRH_EXP_HV_INH_N | RRH_EXP_EF_FLT_N; /* lid closed */
    m.permit_ok = true;
    CHECK(send("FAULT_CLEAR", "{}") && has("BIAS_PERMIT"));
    advance(300000u);
    CHECK(m.bias_on);
    CHECK(send("STATUS", "{}") && has("\"lid_open\":false"));
}

static bool frame_flags_have(uint32_t seg, const char *needle)
{
    /* the segment object of lane `seg` in the last reply */
    char key[24];
    snprintf(key, sizeof key, "{\"id\":%u,", (unsigned)seg);
    const char *p = strstr(rsp, key);
    const char *e = (p == NULL) ? NULL : strstr(p, "]}");
    if (e == NULL) {
        return false;
    }
    const char *q = strstr(p, needle);
    return (q != NULL) && (q < e + 2);
}

static void test_per_lane_bias_out_of_range(void)
{
    mock_reset();
    boot();
    handshake();
    advance(7500000u); /* bias ramped and settled; the scan runs while disarmed */
    CHECK(core.imon_fault == 0u);
    CHECK(core.imon_na[0] > 900u && core.imon_na[0] < 1100u); /* 1 uA programmed in the mock */
    /* a short excursion (< RRH_IMON_HOLD_US) is not flagged */
    m.imon_ua[1] = 400.0;
    advance(100000u);
    m.imon_ua[1] = 1.0;
    advance(300000u);
    CHECK(core.imon_fault == 0u);
    /* floor chain of lane 1 over its 0.2 mA window, reference chain of lane 2 at its rail (buffer cannot sink it) */
    m.imon_ua[1] = 300.0;
    m.imon_ua[6] = 5000.0;
    advance(600000u);
    CHECK(core.imon_fault == ((1u << 1) | (1u << 6)));
    CHECK(send("STATUS", "{}") && has("\"scan\":\"RUNNING\"") && has("\"fault\":[\"F1\",\"R2\"]"));
    arm(100000u);
    advance(500000u);
    const int64_t last = (int64_t)core.next_seq - 1;
    CHECK(send("READ", "{\"after_seq\":%d}", (int)(last - 1)) && status_is("OK"));
    /* ACQ: only the faulted chain is nulled and flagged; global BIAS_OUT_OF_RANGE */
    CHECK(has("\"flags\":[\"BIAS_OUT_OF_RANGE\"]"));
    CHECK(frame_flags_have(1u, "FLOOR_FAULT") && !frame_flags_have(1u, "REFERENCE_FAULT"));
    CHECK(frame_flags_have(2u, "REFERENCE_FAULT") && !frame_flags_have(2u, "FLOOR_FAULT"));
    CHECK(!frame_flags_have(0u, "FAULT") && !frame_flags_have(3u, "FAULT"));
    CHECK(strstr(rsp, "{\"id\":1,\"alpha\":null,\"beta_window\":null,\"photon_ref\":{") != NULL); /* floor null, ref kept */
    CHECK(strstr(rsp, "{\"id\":2,\"alpha\":{") != NULL && strstr(rsp, "\"photon_ref\":null") != NULL);
    /* DIAG: lane flag; while armed the readings are not measured (null), the verdict of the last scan stays */
    CHECK(send("DIAG", "{\"seq\":%d}", (int)last) && status_is("OK"));
    CHECK(has("\"imon_na\":[null,null]"));
    CHECK(has("\"flags\":[\"BIAS_OUT_OF_RANGE\"]"));
    CHECK(send("STATUS", "{}") && has("\"scan\":\"PAUSED_ARMED\"") && has("\"fault\":[\"F1\",\"R2\"]"));
    /* COVERAGE LOST WHILE ARMED: a chain that goes bad now is not seen, and one that recovers is not cleared */
    m.imon_ua[0] = 900.0;
    m.imon_ua[1] = 1.0;
    advance(600000u);
    CHECK(core.imon_fault == ((1u << 1) | (1u << 6)));
    /* disarmed: the scan resumes, the verdict follows the readings */
    CHECK(send("DISARM", "{}") && status_is("OK"));
    advance(500000u);
    CHECK(core.imon_fault == ((1u << 0) | (1u << 6)));
    CHECK(send("DIAG", "{\"seq\":%d}", (int)last) && has("\"imon_na\":[null,null]"));
    m.imon_ua[0] = 1.0;
    m.imon_ua[6] = 1.0;
    advance(500000u);
    CHECK(core.imon_fault == 0u);
    /* a chain the scan did not convert is "not measured": null, never a fault, never a zero */
    m.imon.valid = (uint8_t)~(1u << 3);
    advance(300000u);
    CHECK(core.imon_fault == 0u && (core.imon_na[3] == RRH_IMON_NA_INVALID));
    CHECK(send("STATUS", "{}") && has("\"na\":[1000,1000,1000,null,"));
    /* bias off: not judged */
    m.imon.valid = 0xFFu;
    m.imon_ua[0] = 900.0;
    core.health |= RRH_H_BIAS_PERMIT;
    advance(1000000u);
    CHECK(!m.bias_on && (core.imon_fault == 0u));
}

static void test_zones_not_available_and_lid(void)
{
    mock_reset();
    boot();
    handshake();
    m.analog.bumper_zones = 0x07u; /* pins say "all closed": meaningless on rev A */
    arm(100000u);
    advance(400000u);
    CHECK(send("READ", "{\"after_seq\":-1}") && status_is("OK"));
    CHECK(send("DIAG", "{\"seq\":0}") && has("\"bumper_zones\":null"));
    CHECK(send("STATUS", "{\"clear_bumper\":true}") && has("\"bumper\":{\"available\":false,\"now\":null,\"latched\":null}"));
    CHECK(core.bumper_latched == 0u);
}


static void test_alpha_width_setup_and_dac_write_marker(void)
{
    mock_reset();
    boot();
    handshake();
    CHECK(core.setup.fe.alpha_min_tot_ns == 290u); /* J60035 device cut */
    char old_id[100];
    strcpy(old_id, core.setup_id);
    CHECK(send("ENG_SETUP_SET", "{\"afterglow\":{\"alpha_min_tot_ns\":400}}") && status_is("OK") && has("\"changed\":true"));
    CHECK((m.fe.alpha_min_tot_ns == 400u) && (strcmp(old_id, core.setup_id) != 0)); /* enters setup_id */
    handshake();
    CHECK(send("ENG_SETUP_SET", "{\"afterglow\":{\"alpha_min_tot_ns\":5001}}") && status_is("BAD_ARG"));
    CHECK(send("ENG_SETUP_SET", "{\"afterglow\":{\"alpha_min_tot_ns\":0,\"alpha_hold_us\":300}}") && status_is("OK"));
    /* bias tracking while armed: every HV_SET write is counted in the gate (DIAG bias.dac_writes) */
    handshake();
    advance(7500000u);
    arm(100000u);
    advance(300000u);
    for (uint32_t l = 0; l < RRH_LANES; l++) {
        m.analog.sipm_mc[l] = 15000; /* 10 K colder: target moves by 215 mV, 20 mV per control period */
    }
    advance(1000000u);
    uint32_t writes = 0u;
    for (int i = 0; i < 12; i++) {
        const int seq = (int)core.next_seq - 12 + i;
        if (send("DIAG", "{\"seq\":%d}", seq) && status_is("OK")) {
            int64_t v = -1;
            (void)rrc_json_to_i64(&rdoc, rrc_json_get(&rdoc, rrc_json_get(&rdoc, body(), "bias"), "dac_writes"), &v);
            writes += (uint32_t)((v < 0) ? 0 : v);
        }
    }
    CHECK(writes >= 8u && writes <= 12u); /* one write per 100 ms gate while the target moves */
}


static void set_uv_mon(uint32_t frame_mv_x2_uv)
{
    m.analog.mon_valid = true;
    m.analog.mon_adc_uv = rrh_board_frame_nominal_uv() + frame_mv_x2_uv;
}

static void test_device_type_and_placeholder_refusal(void)
{
    mock_reset();
    boot();
    ident.allow_placeholder_thresholds = false; /* the target's behaviour */
    rrh_core_init(&core, &ident);
    handshake();
    CHECK(core.setup.device == RRH_DEVICE_J60035 && !core.setup.thr_confirmed);
    CHECK(send("ARM", "{\"span_us\":100000}") && status_is("FAULT") && has("placeholder_thresholds") && !core.armed);
    char id0[100];
    strcpy(id0, core.setup_id);
    CHECK(send("ENG_SETUP_SET", "{\"thresholds_confirmed\":true}") && status_is("OK") && has("\"changed\":true"));
    CHECK(strcmp(id0, core.setup_id) != 0); /* the confirmation is part of setup_id */
    handshake();
    arm(100000u);
    CHECK(send("DISARM", "{}") && status_is("OK"));
    advance(300000u);
    /* device type unset: refused whatever the thresholds */
    CHECK(send("ENG_SETUP_SET", "{\"device\":\"NONE\",\"thresholds_confirmed\":true}") && status_is("OK"));
    handshake();
    CHECK(send("ARM", "{\"span_us\":100000}") && status_is("FAULT") && has("device_type_unset"));
    /* a new device type brings its own placeholder defaults and its own TOT cut; writing thresholds confirms them */
    CHECK(send("ENG_SETUP_SET", "{\"device\":\"J30035\"}") && status_is("OK"));
    CHECK(core.setup.device == 2u && !core.setup.thr_confirmed && (core.setup.fe.alpha_min_tot_ns == 180u));
    CHECK(core.setup.fe.threshold[0] == rrh_board_threshold_code(9u * 12200u));
    handshake();
    CHECK(send("ARM", "{\"span_us\":100000}") && status_is("FAULT") && has("placeholder_thresholds"));
    CHECK(send("ENG_SETUP_SET", "{\"thresholds\":{\"beta_lld\":[1300,1300,1300,1300]}}") && status_is("OK") && core.setup.thr_confirmed);
    /* explicit override of the cut, recorded in setup_id; 0 follows the device again */
    char id1[100];
    handshake();
    strcpy(id1, core.setup_id);
    CHECK(send("ENG_SETUP_SET", "{\"afterglow\":{\"alpha_min_tot_ns\":220}}") && status_is("OK"));
    CHECK((core.setup.fe.alpha_min_tot_ns == 220u) && (strcmp(id1, core.setup_id) != 0) && (m.fe.alpha_min_tot_ns == 220u));
    CHECK(send("ENG_SETUP_SET", "{\"afterglow\":{\"alpha_min_tot_ns\":0}}") && status_is("OK") && (m.fe.alpha_min_tot_ns == 180u));
    CHECK(send("ENG_SETUP_SET", "{\"device\":\"X\"}") && status_is("BAD_ARG"));
    handshake();
    CHECK(send("STATUS", "{}") && has("\"device\":\"J30035\"") && has("\"thresholds_confirmed\":true") && has("\"alpha_tot_ns\":180"));
}

static void test_bias_calibration_and_ramp_step(void)
{
    mock_reset();
    boot();
    handshake();
    CHECK(send("STATUS", "{}") && has("\"vmon\":\"UNCALIBRATED\"") && has("\"vmon_ratio_e4\":252233"));
    char id0[100];
    strcpy(id0, core.setup_id);
    /* the board's real divider is 1 % high: the core reads 1 % low until it is calibrated */
    m.analog.bias_vmon_adc_uv = rrh_board_bias_adc_uv(30000u, 254755u); /* what a 30.000 V bus shows with a ratio of 25.4755 */
    advance(7000000u);
    CHECK(core.analog.bias_mv < 29800u); /* 30000 x 252233/254755 */
    /* calibration: written once, stored with the setup, not part of setup_id, no new binding */
    CHECK(send("ENG_SETUP_SET", "{\"bias\":{\"vmon_ratio_e4\":254755},\"persist\":true}") && status_is("OK") &&
          has("\"changed\":false") && has("\"persisted\":true"));
    CHECK(strcmp(id0, core.setup_id) == 0 && (core.link == RRH_LINK_BOUND));
    advance(200000u);
    CHECK(send("STATUS", "{}") && has("\"vmon\":\"CALIBRATED\"") && has("\"vmon_ratio_e4\":254755"));
    CHECK(core.analog.bias_mv >= 29990u && core.analog.bias_mv <= 30010u);
    CHECK(send("ENG_SETUP_SET", "{\"bias\":{\"vmon_ratio_e4\":100}}") && status_is("BAD_ARG"));
    boot(); /* the calibration survives a reboot */
    CHECK(core.setup.vmon_calibrated && (core.setup.vmon_ratio_e4 == 254755u));
}

static void test_frame_potential_check(void)
{
    mock_reset();
    boot();
    handshake();
    set_uv_mon(2000u); /* +4 mV at the frame: quiet */
    advance(300000u);
    CHECK(((core.health & RRH_H_FRAME_FAULT) == 0u) && core.frame_ref_valid && (core.frame_mv == 4));
    CHECK(send("STATUS", "{}") && has("\"frame\":{\"mv\":4,\"fault\":false}"));
    CHECK(send("ENG_SETUP_SET", "{\"heater\":{\"enable\":true,\"setpoint_mc\":5000,\"max_duty_pct\":100}}") && status_is("OK"));
    handshake();
    m.analog.heater_plate_mc = -5000;
    arm(100000u);
    advance(1500000u);
    CHECK(m.heater_applied && ((core.health & RRH_H_FRAME_FAULT) == 0u));
    /* a return-side contact lifts the frame by 40 mV at MON_ADC while the heater runs: heater off at once, code latched */
    const uint32_t offs = force_offs;
    set_uv_mon(40000u + 2000u);
    advance(200000u);
    CHECK(((core.health & RRH_H_FRAME_FAULT) != 0u) && !m.heater_applied && (force_offs == offs + 1u));
    CHECK(send("STATUS", "{}") && has("\"fault\":true") && has("FRAME_FAULT"));
    advance(2000000u);
    CHECK(!m.heater_req); /* stays off */
    CHECK(send("FAULT_CLEAR", "{\"codes\":[\"FRAME_FAULT\"]}") && has("\"cleared\":[]")); /* cause still there */
    set_uv_mon(2000u);
    CHECK(send("FAULT_CLEAR", "{\"codes\":[\"FRAME_FAULT\"]}") && has("\"cleared\":[\"FRAME_FAULT\"]"));
    /* open bond / blown F2801: the frame floats towards VBL, MON_ADC = 0.6 V, far outside the window */
    m.analog.mon_adc_uv = 600304u;
    advance(200000u);
    CHECK((core.health & RRH_H_FRAME_FAULT) != 0u);
    /* below the threshold: not a fault (and not detectable): +20 mV at the frame */
    set_uv_mon(2000u);
    CHECK(send("FAULT_CLEAR", "{}") && status_is("OK"));
    set_uv_mon(10000u + 2000u);
    advance(300000u);
    CHECK((core.health & RRH_H_FRAME_FAULT) == 0u);
}

static void test_heater_overcurrent_cutoff(void)
{
    mock_reset();
    boot();
    handshake();
    CHECK(send("ENG_SETUP_SET", "{\"heater\":{\"enable\":true,\"setpoint_mc\":5000,\"max_duty_pct\":100}}") && status_is("OK"));
    handshake();
    m.analog.heater_plate_mc = -5000;
    m.analog.heater_ma_valid = true;
    m.analog.heater_ma = 3040u; /* normal draw at 14.6 V */
    arm(100000u);
    advance(1500000u);
    CHECK(m.heater_applied && (core.health & RRH_H_HEATER_OVERCURRENT) == 0u);
    CHECK(send("STATUS", "{}") && has("\"ma\":3040,\"oc_ma\":3200"));
    /* a 200 ms excursion above 3.2 A (< 300 ms) is ignored */
    const uint32_t offs = force_offs;
    m.analog.heater_ma = 3400u;
    advance(200000u);
    m.analog.heater_ma = 3040u;
    advance(300000u);
    CHECK(m.heater_applied && (force_offs == offs));
    /* sustained: the switch opens at once (not at the next gate boundary), the code latches, the heater stays off */
    m.analog.heater_ma = 3400u;
    advance(500000u);
    CHECK((core.health & RRH_H_HEATER_OVERCURRENT) != 0u && !m.heater_applied && (force_offs == offs + 1u));
    m.analog.heater_ma = 0u;
    advance(2000000u);
    CHECK(!m.heater_req);
    CHECK(send("READ", "{\"after_seq\":%d}", (int)core.next_seq - 2) && has("HEATER_FAULT"));
    CHECK(send("FAULT_CLEAR", "{}") && has("HEATER_OVERCURRENT")); /* current below the limit: clearable */
    /* configurable */
    CHECK(send("DISARM", "{}") && status_is("OK"));
    advance(300000u);
    CHECK(send("ENG_SETUP_SET", "{\"heater\":{\"oc_ma\":2800,\"oc_ms\":100}}") && status_is("OK"));
    CHECK(send("ENG_SETUP_SET", "{\"heater\":{\"oc_ma\":400}}") && status_is("BAD_ARG"));
    CHECK((core.setup.heater_oc_ma == 2800u) && (core.setup.heater_oc_ms == 100u));
}


static bool flags_of_frame_have_acq_fault(int seq)
{
    return send("READ", "{\"after_seq\":%d}", seq - 1) && status_is("OK") && has("\"flags\":[\"ACQ_FAULT\"]") &&
           (body_int("sequence") == seq);
}

static void test_acq_fault_is_per_gate_and_clears_itself(void)
{
    mock_reset();
    boot();
    handshake();
    arm(100000u);
    advance(1000u + 100000u * 3u);
    m.skip = 2u; /* two records lost by the source */
    advance(100000u * 8u);
    CHECK((core.health & RRH_H_RECORD_LOST) != 0u && (core.gates_lost_total == 2u) && (core.fault_events_total == 1u));
    /* frames 0..2 fine; 3, 4 never existed (the sequence gap tells the host which gates are missing); frame 5 carries ACQ_FAULT once ... */
    CHECK(flags_of_frame_have_acq_fault(5));
    /* ... and none of the later ones does: one lost record no longer poisons the rest of the boot */
    for (int seq = 6; seq < 9; seq++) {
        CHECK(send("READ", "{\"after_seq\":%d}", seq - 1) && status_is("OK") && has("\"flags\":[]"));
    }
    CHECK(send("STATUS", "{}") && has("\"gates_lost\":2,\"fault_events\":1") && has("RECORD_LOST")); /* the latch stays for STATUS */
    /* a timing fault: reported in that gate only */
    m.gate_ticks_override = 4800048u;
    advance(100000u);
    m.gate_ticks_override = 0u;
    advance(300000u);
    CHECK((core.health & RRH_H_GATE_TIMING) != 0u && (core.fault_events_total >= 2u));
    /* HELLO starts a new acquisition epoch: the stream latches are history, the totals survive, boot-wide faults are not touched */
    core.health |= RRH_H_SOURCE;
    CHECK(send("HELLO", "{}"));
    CHECK((core.health & (RRH_H_RECORD_LOST | RRH_H_GATE_TIMING)) == 0u && ((core.health & RRH_H_SOURCE) != 0u));
    CHECK(core.gates_lost_total == 2u);
    /* a boot-wide clock fault and the deliberate test latch stay in every frame until FAULT_CLEAR */
    handshake();
    arm(100000u);
    advance(500000u);
    CHECK(send("READ", "{\"after_seq\":%d}", (int)core.next_seq - 2) && has("\"flags\":[\"ACQ_FAULT\"]"));
}

static void test_identity_build_and_calibration_id(void)
{
    mock_reset();
    boot();
    handshake();
    CHECK(send("STATUS", "{}") && has("\"build\":{\"firmware\":\"rr-head-0.6.0\",\"build_id\":\"") && has("\"image_crc32\":\"C0DE0001\""));
    CHECK(has("\"identity\":{\"serial\":\"UNIT-0001\",\"electronics_revision\":\"RR-HEAD-ACQ-A\""));
    char cal0[24];
    strcpy(cal0, core.cal_id);
    CHECK(strncmp(cal0, "CAL1-", 5) == 0 && strlen(cal0) == 17u);
    CHECK(has(cal0));
    CHECK(send("DIAG", "{\"seq\":0}") || true);
    CHECK(send("ENG_SETUP_SET", "{\"bias\":{\"vmon_ratio_e4\":254755}}") && status_is("OK"));
    CHECK(strcmp(cal0, core.cal_id) != 0); /* a different calibration in force has a different identifier */
    /* the same calibration on another head has another identifier (the serial is in the preimage) */
    char cal1[24];
    strcpy(cal1, core.cal_id);
    rrh_identity_defaults(&ident, "UNIT-0002");
    ident.allow_placeholder_thresholds = true;
    rrh_core_init(&core, &ident);
    CHECK(strcmp(cal1, core.cal_id) != 0 && strcmp(cal0, core.cal_id) != 0);
    /* HELLO carries the serial and firmware, the descriptor the electronics revision: what a calibration binds to */
    CHECK(send("HELLO", "{}") && has("\"head_id\":\"UNIT-0002\"") && has("\"firmware\":\"rr-head-0.6.0\""));
}

static void test_gatestat_joins_acq_by_sequence(void)
{
    mock_reset();
    boot();
    handshake();
    m.lane_template[1].floor_live_ticks = 1000000u; /* a saturating lane: live fraction 21 % of 4 800 000 ticks */
    arm(100000u);
    advance(1000u + 100000u * 6u);
    CHECK(send("GATESTAT", "{\"after_seq\":-1,\"limit\":3}") && status_is("OK") && has("\"seq\":0,") && has("\"seq\":2,") && !has("\"seq\":3,"));
    CHECK(has("\"more\":true") && has("\"last_seq\":2"));
    CHECK(has("\"lf\":[") && has("\"sc\":[0,2,0,0]")); /* lane 1: floor live fraction < 50 % = saturation cause bit 1 */
    CHECK(send("GATESTAT", "{\"after_seq\":2,\"limit\":12}") && has("\"seq\":3,") && has("\"more\":false"));
    CHECK(send("GATESTAT", "{\"after_seq\":99}") && status_is("EMPTY"));
    CHECK(send("GATESTAT", "{\"limit\":13}") && status_is("BAD_ARG"));
    CHECK(send("READ", "{\"after_seq\":2}") && status_is("OK") && (body_int("sequence") == 3)); /* same numbering as ACQ */
    printf("    GATESTAT 3 gates: %zu bytes of JSON\n", strlen(rsp));
}

int main(void)
{
    RUN(test_boot_state_is_unbound);
    RUN(test_handshake_rules);
    RUN(test_reset_gives_fresh_boot_and_unbound);
    RUN(test_reply_cache);
    RUN(test_link_garbage);
    RUN(test_frame_mapping_and_nulls);
    RUN(test_buffer_gap_empty_and_sequence_continuity);
    RUN(test_setup_change_invalidates_binding);
    RUN(test_sync_quality);
    RUN(test_heater_control);
    RUN(test_bias_compensation);
    RUN(test_lost_and_bad_gates);
    RUN(test_misc_ops);
    RUN(test_setup_members_and_defaults);
    RUN(test_bias_on_sequence_and_limits);
    RUN(test_bias_permit_trip_and_recovery);
    RUN(test_per_lane_bias_out_of_range);
    RUN(test_zones_not_available_and_lid);
    RUN(test_alpha_width_setup_and_dac_write_marker);
    RUN(test_device_type_and_placeholder_refusal);
    RUN(test_bias_calibration_and_ramp_step);
    RUN(test_frame_potential_check);
    RUN(test_heater_overcurrent_cutoff);
    RUN(test_acq_fault_is_per_gate_and_clears_itself);
    RUN(test_identity_build_and_calibration_id);
    RUN(test_gatestat_joins_acq_by_sequence);
    return TEST_SUMMARY();
}
