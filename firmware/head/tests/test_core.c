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
    bool heater_req, heater_applied;
    uint32_t heater_requests;
    rrh_analog_t analog;
    uint32_t bias_mv;
    bool bias_on;
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
        if (m.skip > 0u) {
            m.skip--;
            continue;
        }
        return true;
    }
}
bool rrh_hal_frontend_apply(const rrh_frontend_cfg_t *cfg) { m.fe = *cfg; m.fe_applies++; return true; }
void rrh_hal_bias_set(uint32_t mv, bool enable) { m.bias_mv = mv; m.bias_on = enable; }
void rrh_hal_analog_read(rrh_analog_t *out)
{
    *out = m.analog;
    out->bias_mv = m.bias_on ? m.bias_mv : 0u;
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
}

static void boot(void)
{
    rrh_identity_defaults(&ident, "UNIT-0001");
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
    /* missing head temperature: null plus the thermal flag; undervoltage */
    for (uint32_t l = 0; l < RRH_LANES; l++) {
        m.analog.sipm_mc[l] = RRH_TEMP_INVALID;
    }
    m.analog.supply_mv = 9000u;
    advance(100000u);
    CHECK(send("READ", "{\"after_seq\":1}") && status_is("OK"));
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
    CHECK(send("ENG_SETUP_SET", "{\"thresholds\":{\"beta_lld\":[2000,200,200,200]}}") && status_is("BAD_ARG")); /* LLD >= ULD */
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
    advance(1000000u);
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
    m.analog.bumper_zones = 0x05u;
    advance(100000u);
    m.analog.bumper_zones = 0u;
    advance(100000u);
    CHECK(send("STATUS", "{\"clear_bumper\":true}") && has("\"bumper\":{\"now\":[],\"latched\":[\"FRONT\",\"RIGHT\"]}"));
    CHECK(send("STATUS", "{}") && has("\"latched\":[]"));
    CHECK(send("ENG_WAVE_ARM", "{\"channel\":3,\"samples\":64,\"pretrigger\":8}") && status_is("OK"));
    CHECK(send("ENG_WAVE_ARM", "{\"channel\":9,\"samples\":64,\"pretrigger\":8}") && status_is("BAD_ARG"));
    CHECK(send("ENG_WAVE_READ", "{\"offset\":60,\"count\":16}") && status_is("OK") && (body_int("count") == 4));
    CHECK(has("\"bytes_b64\":\"PAA9AD4APwA=\""));
    CHECK(send("ENG_WAVE_READ", "{\"offset\":64,\"count\":1}") && status_is("BAD_ARG"));
    CHECK(m.kicks > 0u);
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
    return TEST_SUMMARY();
}
