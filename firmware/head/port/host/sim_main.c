/* rr_head_sim - emulated Rad Roomba detector head.
 *
 * Serial side : TCP server (default 127.0.0.1:5540) and optional PTY carrying exactly the bytes
 *               that would be on the RS-485 pair.
 * Physics side: UDP socket (default 127.0.0.1:5541), one JSON object per datagram: expected
 *               rates, fault injection, identity swap, statistics, manual clock.
 * Protocol reference: firmware/head/README.md, section "Emulator".
 */
#define _DEFAULT_SOURCE
#define _XOPEN_SOURCE 700
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <termios.h>
#include <unistd.h>

#include "sim.h"

static rrh_core_t g_core;
static rrh_identity_t g_ident;
static bool g_strict; /* --strict-placeholders */
static volatile sig_atomic_t g_stop;
static bool g_quiet;

/* link-level fault injection (wall-clock based: these model the cable and the host's view) */
static uint64_t g_link_down_until_ns;   /* bytes in both directions are lost */
static uint64_t g_boot_until_ns;        /* MCU is in reset / booting: deaf and mute */
static uint64_t g_pause_reads_until_ns; /* READ requests get no reply */
static uint32_t g_corrupt_replies;      /* next N replies leave with a damaged CRC */
static uint32_t g_delay_replies;        /* next N replies are delayed ... */
static uint32_t g_delay_ms;             /* ... by this much */
static uint8_t g_pending[RRH_TX_MAX];
static size_t g_pending_len;
static uint64_t g_pending_at_ns;
static int g_pending_fd = -1;
static uint64_t g_tx_bytes, g_rx_bytes, g_tx_records;

static uint8_t g_desc_file[16384];
static char g_setup_override[100], g_fw_override[100];

static void logf_(const char *fmt, ...)
{
    if (g_quiet) {
        return;
    }
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "[rr_head_sim %10.3f] ", (double)rrh_hal_now_us() * 1e-6);
    vfprintf(stderr, fmt, ap);
    fputc('\n', stderr);
    va_end(ap);
}

static void on_signal(int sig)
{
    (void)sig;
    g_stop = 1;
}

static void copy_str(char *dst, size_t cap, const char *src)
{
    snprintf(dst, cap, "%s", src);
}

/* ---- MCU reset -------------------------------------------------------------------------------- */
static void mcu_reset(rrh_reset_cause_t cause, uint32_t boot_ms)
{
    g_sim.reset_cause = cause;
    sim_power_cycle(&g_sim);
    g_boot_until_ns = sim_mono_ns() + ((uint64_t)boot_ms * 1000000u);
    g_sim.boot_mono_ns = g_boot_until_ns; /* the head clock starts when the MCU leaves reset */
    g_pending_len = 0u;
    rrh_core_init(&g_core, &g_ident);
    g_core.rx_gap_timeout_us = 200000u; /* TCP may split a record; RS-485 timing is not emulated */
    logf_("MCU reset #%u: boot_id %s serial %s setup %s", g_sim.boot_count, g_core.boot_id, g_ident.serial,
          g_core.setup_id);
}

/* ---- serial side ------------------------------------------------------------------------------- */
static void send_all(int fd, const uint8_t *buf, size_t len)
{
    size_t off = 0u;
    while (off < len) {
        const ssize_t n = write(fd, &buf[off], len - off);
        if (n > 0) {
            off += (size_t)n;
        } else if ((n < 0) && ((errno == EINTR) || (errno == EAGAIN))) {
            struct pollfd p = {fd, POLLOUT, 0};
            (void)poll(&p, 1, 20);
        } else {
            return; /* peer went away: the bytes are lost, as on a cut cable */
        }
    }
    g_tx_bytes += len;
}

static void transmit(int fd, const rrh_reply_t *reply)
{
    const uint64_t now = sim_mono_ns();
    if (now < g_link_down_until_ns) {
        return;
    }
    memcpy(g_pending, reply->data, reply->len);
    g_pending_len = reply->len;
    g_pending_fd = fd;
    g_pending_at_ns = now;
    if (g_corrupt_replies > 0u) {
        g_corrupt_replies--;
        g_pending[g_pending_len / 2u] ^= 0x01u; /* one flipped bit in the JSON: the CRC no longer matches */
    }
    if (g_delay_replies > 0u) {
        g_delay_replies--;
        g_pending_at_ns = now + ((uint64_t)g_delay_ms * 1000000u);
    }
    g_tx_records++;
}

static void flush_pending(void)
{
    if ((g_pending_len > 0u) && (sim_mono_ns() >= g_pending_at_ns)) {
        if (sim_mono_ns() >= g_link_down_until_ns) {
            send_all(g_pending_fd, g_pending, g_pending_len);
        }
        g_pending_len = 0u;
    }
}

static void serial_input(int fd, const uint8_t *buf, size_t len)
{
    const uint64_t now_ns = sim_mono_ns();
    g_rx_bytes += len;
    if ((now_ns < g_link_down_until_ns) || (now_ns < g_boot_until_ns)) {
        return;
    }
    for (size_t i = 0u; i < len; i++) {
        rrh_reply_t reply;
        if (rrh_core_rx_byte(&g_core, buf[i], rrh_hal_now_us(), &reply)) {
            if ((now_ns < g_pause_reads_until_ns) && (reply.len > 60u) &&
                (strstr((const char *)g_core.rx_buf, "\"op\":\"READ\"") != NULL)) {
                continue; /* injected: READ replies are lost */
            }
            flush_pending();
            transmit(fd, &reply);
        }
    }
}

/* ---- stimulus / control socket ------------------------------------------------------------------ */
static rrc_jtok_t g_tok[512];
static rrc_json_t g_doc;

static bool j_num(int tok, double *out)
{
    size_t n = 0u;
    char tmp[40];
    if (rrc_json_type(&g_doc, tok) != RRC_JT_NUMBER) {
        return false;
    }
    const char *raw = rrc_json_raw(&g_doc, tok, &n);
    if (n >= sizeof tmp) {
        return false;
    }
    memcpy(tmp, raw, n);
    tmp[n] = '\0';
    *out = strtod(tmp, NULL);
    return true;
}

static bool j_u64(const char *key, uint64_t *out)
{
    return rrc_json_to_u64(&g_doc, rrc_json_get(&g_doc, 0, key), out);
}

static bool j_is(const char *key, const char *value)
{
    return rrc_json_str_eq(&g_doc, rrc_json_get(&g_doc, 0, key), value);
}

static bool j_flag(const char *key, bool dflt)
{
    bool v = dflt;
    (void)rrc_json_to_bool(&g_doc, rrc_json_get(&g_doc, 0, key), &v);
    return v;
}

/* "lane" (0..3 or absent = all) and "chain" ("floor" | "ref" | absent = both) -> 8-bit chain mask */
static bool j_chain_mask(uint8_t *mask)
{
    uint64_t lane = 0u;
    const bool one = j_u64("lane", &lane);
    if (one && (lane >= RRH_LANES)) {
        return false;
    }
    uint8_t m = 0u;
    for (uint32_t l = 0u; l < RRH_LANES; l++) {
        if (!one || (l == (uint32_t)lane)) {
            if (!j_is("chain", "ref")) {
                m |= (uint8_t)(1u << l);
            }
            if (!j_is("chain", "floor")) {
                m |= (uint8_t)(1u << (4u + l));
            }
        }
    }
    *mask = m;
    return true;
}

static const char *cmd_rates(void)
{
    static const char *const names[SIM_CH] = {"alpha", "beta", "ref", "floor_reject", "ref_reject", "bright_beta"};
    double pe = 0.0;
    sim_rate_change_t chg;
    uint64_t t = 0u;
    memset(&chg, 0, sizeof chg);
    chg.from_us = rrh_hal_now_us();
    if (j_u64("from_us", &t)) {
        chg.from_us = t;
    } else if (j_u64("from_mono_ns", &t)) {
        if (g_sim.manual) {
            return "from_mono_ns needs --clock real";
        }
        chg.from_us = (t > g_sim.boot_mono_ns) ? ((t - g_sim.boot_mono_ns) / 1000u) : 0u;
    } else {
        /* immediately */
    }
    if (j_num(rrc_json_get(&g_doc, 0, "alpha_pe"), &pe) && (pe > 0.0)) {
        g_sim.alpha_pe = pe;
    }
    if (j_num(rrc_json_get(&g_doc, 0, "bright_pe"), &pe) && (pe > 0.0)) {
        g_sim.bright_pe = pe;
    }
    for (uint32_t ch = 0u; ch < SIM_CH; ch++) {
        const int a = rrc_json_get(&g_doc, 0, names[ch]);
        if (a < 0) {
            continue;
        }
        for (uint32_t l = 0u; l < RRH_LANES; l++) {
            double v = 0.0;
            const int e = (rrc_json_type(&g_doc, a) == RRC_JT_ARRAY) ? rrc_json_at(&g_doc, a, (uint16_t)l) : a;
            if (!j_num(e, &v) || (v < 0.0) || (v > 1.0e7)) {
                return "rates must be numbers 0..1e7 (one value or an array of 4 per channel)";
            }
            chg.rate[l][ch] = v;
            chg.mask |= (uint32_t)1u << ((l * SIM_CH) + ch);
        }
    }
    if (chg.mask == 0u) {
        return "no rates given";
    }
    return sim_add_rate_change(&g_sim, &chg) ? NULL : "rate schedule full";
}

static const char *cmd_analog(void)
{
    double v = 0.0;
    int t = rrc_json_get(&g_doc, 0, "sipm_c");
    if (t >= 0) {
        for (uint32_t l = 0u; l < RRH_LANES; l++) {
            const int e = (rrc_json_type(&g_doc, t) == RRC_JT_ARRAY) ? rrc_json_at(&g_doc, t, (uint16_t)l) : t;
            if (rrc_json_is_null(&g_doc, e)) {
                g_sim.sipm_open[l] = true;
            } else if (j_num(e, &v)) {
                g_sim.sipm_open[l] = false;
                g_sim.analog.sipm_mc[l] = (int32_t)(v * 1000.0);
            } else {
                return "sipm_c";
            }
        }
    }
    t = rrc_json_get(&g_doc, 0, "heater_c");
    if (t >= 0) {
        g_sim.plate_open = rrc_json_is_null(&g_doc, t);
        if (j_num(t, &v)) {
            g_sim.analog.heater_plate_mc = (int32_t)(v * 1000.0);
            g_sim.plate_heat_c = 0.0;
        }
    }
    if (j_num(rrc_json_get(&g_doc, 0, "board_c"), &v)) {
        g_sim.analog.board_mc = (int32_t)(v * 1000.0);
    }
    if (j_num(rrc_json_get(&g_doc, 0, "supply_v"), &v)) {
        g_sim.analog.supply_mv = (uint32_t)(v * 1000.0);
    }
    if (j_num(rrc_json_get(&g_doc, 0, "bias_ua"), &v)) {
        g_sim.analog.bias_ua = (uint32_t)v;
    }
    if (j_num(rrc_json_get(&g_doc, 0, "bumper_zones"), &v)) {
        g_sim.analog.bumper_zones = (uint8_t)((uint32_t)v & 7u);
    }
    g_sim.analog.heater_cutout_ok = j_flag("cutout_ok", g_sim.analog.heater_cutout_ok);
    /* board functions of IB-17 */
    t = rrc_json_get(&g_doc, 0, "imon_ua");
    if (t >= 0) {
        for (uint32_t ch = 0u; ch < RRH_CHAINS; ch++) {
            const int e = (rrc_json_type(&g_doc, t) == RRC_JT_ARRAY) ? rrc_json_at(&g_doc, t, (uint16_t)ch) : t;
            if (!j_num(e, &v) || (v < 0.0)) {
                return "imon_ua";
            }
            g_sim.imon_ua[ch] = v;
        }
    }
    if (j_num(rrc_json_get(&g_doc, 0, "imon_valid"), &v)) {
        g_sim.imon_valid = (uint8_t)((uint32_t)v & 0xFFu);
    }
    if (j_num(rrc_json_get(&g_doc, 0, "imon_offset_uv"), &v)) {
        g_sim.imon_offset_uv = (int32_t)v;
    }
    if (j_num(rrc_json_get(&g_doc, 0, "frame_mv"), &v)) {
        g_sim.frame_mv = v;
    }
    if (j_num(rrc_json_get(&g_doc, 0, "heater_ma"), &v) && (v >= 0.0)) {
        g_sim.heater_ma_model = v;
    }
    if (j_num(rrc_json_get(&g_doc, 0, "vmon_true_ratio_e4"), &v) && (v > 100000.0)) {
        g_sim.vmon_true_ratio_e4 = (uint32_t)v;
    }
    g_sim.width_overwrite = j_flag("width_overwrite", g_sim.width_overwrite);
    if (j_num(rrc_json_get(&g_doc, 0, "pileup_us"), &v) && (v >= 0.0) && (v < 1000.0)) {
        g_sim.pileup_us = v;
    }
    g_sim.exp_present = j_flag("expander", g_sim.exp_present);
    g_sim.lid_open = j_flag("lid_open", g_sim.lid_open);
    g_sim.inhibit = j_flag("inhibit", g_sim.inhibit);
    g_sim.efuse_fault = j_flag("efuse_fault", g_sim.efuse_fault);
    g_sim.analog.zones_available = j_flag("zones_available", g_sim.analog.zones_available);
    if (j_num(rrc_json_get(&g_doc, 0, "hw_rev"), &v)) {
        g_sim.hw_rev = (uint8_t)((uint32_t)v & 3u);
    }
    return NULL;
}

static const char *cmd_fault(void)
{
    uint64_t ms = 0u;
    uint64_t n = 1u;
    uint8_t mask = 0u;
    const bool on = j_flag("on", true);
    (void)j_u64("ms", &ms);
    (void)j_u64("count", &n);
    const uint64_t until = sim_mono_ns() + (ms * 1000000u);
    if (j_is("kind", "mcu_reset")) {
        mcu_reset(j_is("cause", "watchdog") ? RRH_RESET_WATCHDOG
                  : (j_is("cause", "brownout") ? RRH_RESET_BROWNOUT : RRH_RESET_PIN), (uint32_t)ms);
    } else if (j_is("kind", "link_drop")) {
        g_link_down_until_ns = until;
        rrh_core_rx_timeout(&g_core);
    } else if (j_is("kind", "pause_reads")) {
        g_pause_reads_until_ns = until;
    } else if (j_is("kind", "corrupt_crc")) {
        g_corrupt_replies = (uint32_t)n;
    } else if (j_is("kind", "delay_reply")) {
        g_delay_replies = (uint32_t)n;
        g_delay_ms = (uint32_t)ms;
    } else if (j_is("kind", "null_channel")) {
        if (!j_chain_mask(&mask)) {
            return "lane";
        }
        g_sim.analog.frontend_fault = on ? (uint8_t)(g_sim.analog.frontend_fault | mask)
                                         : (uint8_t)(g_sim.analog.frontend_fault & (uint8_t)~mask);
        g_core.control_due_us = 0u; /* the housekeeping scan sees it at the next poll */
    } else if (j_is("kind", "saturate")) {
        if (!j_chain_mask(&mask)) {
            return "lane";
        }
        g_sim.saturate_mask = on ? (uint8_t)(g_sim.saturate_mask | mask) : (uint8_t)(g_sim.saturate_mask & (uint8_t)~mask);
    } else if (j_is("kind", "thermal")) {
        if (j_is("what", "sipm_open")) {
            for (uint32_t l = 0u; l < RRH_LANES; l++) {
                g_sim.sipm_open[l] = on;
            }
        } else if (j_is("what", "heater_sensor_open")) {
            g_sim.plate_open = on;
        } else if (j_is("what", "cutout")) {
            g_sim.analog.heater_cutout_ok = !on;
        } else if (j_is("what", "overtemp")) {
            g_sim.analog.heater_plate_mc = on ? 85000 : 20000;
        } else {
            return "what: sipm_open | heater_sensor_open | cutout | overtemp";
        }
        g_core.control_due_us = 0u;
    } else if (j_is("kind", "lost_gates")) {
        g_sim.skip_gates = (uint32_t)n;
    } else if (j_is("kind", "source_fail")) {
        g_sim.source_fail = on;
    } else {
        return "kind: mcu_reset | link_drop | pause_reads | corrupt_crc | delay_reply | null_channel | saturate | "
               "thermal | lost_gates | source_fail";
    }
    return NULL;
}

static const char *cmd_swap(void)
{
    char serial[49];
    uint64_t ms = 100u;
    if (rrc_json_str_copy(&g_doc, rrc_json_get(&g_doc, 0, "serial"), serial, sizeof serial) <= 0) {
        return "serial";
    }
    (void)j_u64("ms", &ms);
    /* A different physical head: other identity, empty storage, link interrupted while the
     * connectors are open. Any baseline-replica overrides do not survive a swap. */
    rrh_identity_defaults(&g_ident, serial);
    g_ident.rail_5mm = j_is("variant", "concept-e-5mm");
    g_ident.allow_placeholder_thresholds = !g_strict;
    g_ident.gate_min_us = g_core.ident.gate_min_us;
    g_ident.gate_max_us = g_core.ident.gate_max_us;
    g_sim.nv_len = 0u;
    g_link_down_until_ns = sim_mono_ns() + (ms * 1000000u);
    mcu_reset(RRH_RESET_POWER_ON, (uint32_t)ms);
    return NULL;
}

static void manual_advance(uint64_t us)
{
    /* Step the virtual clock so that the core's periodic work runs as on the target. */
    while (us > 0u) {
        const uint64_t step = (us > 10000u) ? 10000u : us;
        g_sim.manual_us += step;
        us -= step;
        rrh_core_poll(&g_core);
    }
}

static size_t control_handle(const char *msg, size_t len, char *out, size_t cap)
{
    static const rrc_json_limits_t lim = {6u, 256u};
    const char *err = NULL;
    char cmd[24] = "?";
    bool quit = false;
    if ((rrc_json_parse(&g_doc, msg, len, g_tok, 512u, &lim) != RRC_JSON_OK) ||
        (rrc_json_type(&g_doc, 0) != RRC_JT_OBJECT) ||
        (rrc_json_str_copy(&g_doc, rrc_json_get(&g_doc, 0, "cmd"), cmd, sizeof cmd) < 0)) {
        err = "expected one JSON object with a string member \"cmd\"";
    } else if (strcmp(cmd, "rates") == 0) {
        err = cmd_rates();
    } else if (strcmp(cmd, "fault") == 0) {
        err = cmd_fault();
    } else if (strcmp(cmd, "analog") == 0) {
        err = cmd_analog();
    } else if (strcmp(cmd, "swap") == 0) {
        err = cmd_swap();
    } else if (strcmp(cmd, "advance") == 0) {
        uint64_t us = 0u;
        if (!g_sim.manual) {
            err = "advance needs --clock manual";
        } else if (!j_u64("us", &us) || (us > 3600000000uLL)) {
            err = "us";
        } else {
            manual_advance(us);
        }
    } else if (strcmp(cmd, "quit") == 0) {
        quit = true;
    } else if ((strcmp(cmd, "stats") != 0) && (strcmp(cmd, "ping") != 0)) {
        err = "cmd: rates | fault | analog | swap | advance | stats | ping | quit";
    } else {
        /* stats / ping: reply only */
    }
    rrc_jw_t w;
    rrc_jw_init(&w, out, cap);
    rrc_jw_obj_begin(&w);
    rrc_jw_kbool(&w, "ok", err == NULL);
    rrc_jw_kstr(&w, "cmd", cmd);
    if (err != NULL) {
        rrc_jw_kstr(&w, "error", err);
    }
    rrc_jw_ku64(&w, "head_us", rrh_hal_now_us());
    rrc_jw_ku64(&w, "boot_count", g_sim.boot_count);
    if (strcmp(cmd, "stats") == 0) {
        static const char *const names[SIM_CH] = {"alpha", "beta", "ref", "floor_reject", "ref_reject", "bright_beta"};
        static const char *const links[3] = {"UNBOUND", "HANDSHAKE", "BOUND"};
        rrc_jw_kstr(&w, "serial", g_ident.serial);
        rrc_jw_kstr(&w, "boot_id", g_core.boot_id);
        rrc_jw_kstr(&w, "setup_id", g_core.setup_id);
        rrc_jw_kstr(&w, "link", links[g_core.link]);
        rrc_jw_kbool(&w, "armed", g_core.armed);
        rrc_jw_ku64(&w, "next_seq", g_core.next_seq);
        rrc_jw_ku64(&w, "gates", g_sim.gates_total);
        rrc_jw_ku64(&w, "pending_rate_changes", g_sim.n_sched);
        rrc_jw_key(&w, "drawn");
        rrc_jw_obj_begin(&w);
        for (uint32_t ch = 0u; ch < SIM_CH; ch++) {
            rrc_jw_key(&w, names[ch]);
            rrc_jw_arr_begin(&w);
            for (uint32_t l = 0u; l < RRH_LANES; l++) {
                rrc_jw_u64(&w, g_sim.drawn[l][ch]);
            }
            rrc_jw_arr_end(&w);
        }
        rrc_jw_obj_end(&w);
        rrc_jw_key(&w, "board");
        rrc_jw_obj_begin(&w);
        rrc_jw_key(&w, "pulser");
        rrc_jw_obj_begin(&w);
        rrc_jw_kbool(&w, "enable", g_sim.fe.pulser_enable);
        rrc_jw_ku64(&w, "channel", g_sim.fe.pulser_channel);
        rrc_jw_ku64(&w, "code", g_sim.fe.pulser_code);
        rrc_jw_ku64(&w, "width_us", g_sim.fe.pulser_width_us);
        rrc_jw_ku64(&w, "charge_fc", rrh_board_pulser_fc(g_sim.fe.pulser_code));
        rrc_jw_obj_end(&w);
        rrc_jw_key(&w, "led");
        rrc_jw_obj_begin(&w);
        rrc_jw_kbool(&w, "enable", g_sim.fe.led_enable);
        rrc_jw_ku64(&w, "code", g_sim.fe.led_code);
        rrc_jw_ku64(&w, "v_led_mv", rrh_board_led_mv(g_sim.fe.led_code));
        rrc_jw_obj_end(&w);
        rrc_jw_ku64(&w, "alpha_hold_us", g_sim.fe.alpha_hold_us);
        rrc_jw_ku64(&w, "alpha_min_tot_ns", g_sim.fe.alpha_min_tot_ns);
        rrc_jw_key(&w, "bias");
        rrc_jw_obj_begin(&w);
        rrc_jw_ku64(&w, "out_mv", g_sim.bias_set_mv);
        rrc_jw_kbool(&w, "hv_en", g_sim.bias_enable);
        rrc_jw_kbool(&w, "permit", g_sim.permit);
        rrc_jw_ku64(&w, "hv_set_code", rrh_board_hv_code(g_sim.bias_set_mv));
        rrc_jw_obj_end(&w);
        rrc_jw_obj_end(&w);
        rrc_jw_ku64(&w, "rx_bytes", g_rx_bytes);
        rrc_jw_ku64(&w, "tx_bytes", g_tx_bytes);
        rrc_jw_ku64(&w, "tx_records", g_tx_records);
    }
    rrc_jw_obj_end(&w);
    if (quit) {
        g_stop = 1;
    }
    return rrc_jw_ok(&w) ? rrc_jw_len(&w) : 0u;
}

/* ---- sockets ------------------------------------------------------------------------------------ */
static bool parse_endpoint(const char *arg, struct sockaddr_in *sa)
{
    char host[64];
    const char *colon = strrchr(arg, ':');
    if ((colon == NULL) || ((size_t)(colon - arg) >= sizeof host)) {
        return false;
    }
    memcpy(host, arg, (size_t)(colon - arg));
    host[colon - arg] = '\0';
    memset(sa, 0, sizeof *sa);
    sa->sin_family = AF_INET;
    sa->sin_port = htons((uint16_t)atoi(colon + 1));
    return inet_pton(AF_INET, host, &sa->sin_addr) == 1;
}

static int open_pty(const char *link_path)
{
    const int fd = posix_openpt(O_RDWR | O_NOCTTY);
    if ((fd < 0) || (grantpt(fd) != 0) || (unlockpt(fd) != 0)) {
        return -1;
    }
    const char *slave = ptsname(fd);
    struct termios tio;
    if ((slave == NULL) || (tcgetattr(fd, &tio) != 0)) {
        return -1;
    }
    cfmakeraw(&tio);
    (void)tcsetattr(fd, TCSANOW, &tio);
    (void)unlink(link_path);
    if (symlink(slave, link_path) != 0) {
        return -1;
    }
    (void)fcntl(fd, F_SETFL, O_NONBLOCK);
    return fd;
}

static void usage(void)
{
    fputs("rr_head_sim [options]\n"
          "  --tcp HOST:PORT        RS-485 byte stream server (default 127.0.0.1:5540)\n"
          "  --stim HOST:PORT       UDP JSON stimulus / fault-injection socket (default 127.0.0.1:5541)\n"
          "  --pty PATH             also serve the byte stream on a PTY; PATH becomes a symlink to it\n"
          "  --seed N               RNG seed: counts and boot ids are reproducible (default: random)\n"
          "  --clock real|manual    manual: the head clock moves only on {\"cmd\":\"advance\",\"us\":N}\n"
          "  --serial S             head serial number (default RRH-SIM-0001)\n"
          "  --variant V            concept-e (default) | concept-e-5mm\n"
          "  --gate-range MIN,MAX   accepted ARM span in microseconds (default 100000,100000)\n"
          "  --descriptor-file F    serve these exact descriptor bytes (baseline replica)\n"
          "  --descriptor-id S --setup-id S --firmware S --boot-id UUID   identifiers for the replica\n"
          "  --tau-floor-us X --tau-ref-us X   dead time per recorded event (default 10, 10)\n"
          "  --truth-log FILE       append one JSON line per generated gate (drawn counts)\n"
          "  --strict-placeholders  refuse ARM until the device type is set and the thresholds are confirmed (target behaviour)\n"
          "  --no-width-hist        emulate a head without pulse-width measurement (no DIAG width fields)\n"
          "  --quiet\n",
          stderr);
}

int main(int argc, char **argv)
{
    const char *tcp_arg = "127.0.0.1:5540";
    const char *stim_arg = "127.0.0.1:5541";
    const char *pty_path = NULL;
    const char *truth_path = NULL;
    const char *desc_path = NULL;
    const char *boot_id = NULL;
    const char *serial = "RRH-SIM-0001";
    uint64_t seed = 0u;
    bool have_seed = false;
    bool manual = false;
    double tau_f = -1.0, tau_r = -1.0;
    uint32_t gate_min = RRH_SPAN_DEFAULT_US, gate_max = RRH_SPAN_DEFAULT_US;
    char desc_id[49] = "";
    bool rail5 = false;
    bool no_width = false;

    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        const char *v = ((i + 1) < argc) ? argv[i + 1] : NULL;
        if (strcmp(a, "--quiet") == 0) {
            g_quiet = true;
            continue;
        }
        if (strcmp(a, "--strict-placeholders") == 0) {
            g_strict = true; /* refuse ARM with an unset device type or unconfirmed thresholds, as the target does */
            continue;
        }
        if (strcmp(a, "--no-width-hist") == 0) {
            no_width = true;
            continue;
        }
        if ((strcmp(a, "--help") == 0) || (v == NULL)) {
            usage();
            return (strcmp(a, "--help") == 0) ? 0 : 2;
        }
        i++;
        if (strcmp(a, "--tcp") == 0) { tcp_arg = v; }
        else if (strcmp(a, "--stim") == 0) { stim_arg = v; }
        else if (strcmp(a, "--pty") == 0) { pty_path = v; }
        else if (strcmp(a, "--seed") == 0) { seed = strtoull(v, NULL, 0); have_seed = true; }
        else if (strcmp(a, "--clock") == 0) { manual = strcmp(v, "manual") == 0; }
        else if (strcmp(a, "--serial") == 0) { serial = v; }
        else if (strcmp(a, "--variant") == 0) { rail5 = strcmp(v, "concept-e-5mm") == 0; }
        else if (strcmp(a, "--gate-range") == 0) {
            if (sscanf(v, "%u,%u", &gate_min, &gate_max) != 2) { usage(); return 2; }
        }
        else if (strcmp(a, "--descriptor-file") == 0) { desc_path = v; }
        else if (strcmp(a, "--descriptor-id") == 0) { copy_str(desc_id, sizeof desc_id, v); }
        else if (strcmp(a, "--setup-id") == 0) { copy_str(g_setup_override, sizeof g_setup_override, v); }
        else if (strcmp(a, "--firmware") == 0) { copy_str(g_fw_override, sizeof g_fw_override, v); }
        else if (strcmp(a, "--boot-id") == 0) { boot_id = v; }
        else if (strcmp(a, "--tau-floor-us") == 0) { tau_f = atof(v); }
        else if (strcmp(a, "--tau-ref-us") == 0) { tau_r = atof(v); }
        else if (strcmp(a, "--truth-log") == 0) { truth_path = v; }
        else { usage(); return 2; }
    }
    if (!have_seed) {
        FILE *f = fopen("/dev/urandom", "rb");
        if ((f == NULL) || (fread(&seed, sizeof seed, 1u, f) != 1u)) {
            seed = sim_mono_ns();
        }
        if (f != NULL) {
            fclose(f);
        }
    }
    sim_init(&g_sim, seed, manual);
    g_sim.width_hist = !no_width;
    if (tau_f >= 0.0) { g_sim.tau_floor_us = tau_f; }
    if (tau_r >= 0.0) { g_sim.tau_ref_us = tau_r; }
    if (truth_path != NULL) {
        g_sim.truth = fopen(truth_path, "a");
        if (g_sim.truth == NULL) {
            perror(truth_path);
            return 2;
        }
    }
    if (boot_id != NULL) {
        unsigned b[16];
        if (sscanf(boot_id, "%2x%2x%2x%2x-%2x%2x-%2x%2x-%2x%2x-%2x%2x%2x%2x%2x%2x", &b[0], &b[1], &b[2], &b[3], &b[4],
                   &b[5], &b[6], &b[7], &b[8], &b[9], &b[10], &b[11], &b[12], &b[13], &b[14], &b[15]) != 16) {
            fputs("--boot-id needs a UUID\n", stderr);
            return 2;
        }
        for (int k = 0; k < 16; k++) {
            g_sim.forced_boot_id[k] = (uint8_t)b[k];
        }
        g_sim.have_forced_boot_id = true;
    }
    rrh_identity_defaults(&g_ident, serial);
    g_ident.rail_5mm = rail5;
    g_ident.allow_placeholder_thresholds = !g_strict;
    g_ident.gate_min_us = gate_min;
    g_ident.gate_max_us = gate_max;
    if (desc_id[0] != '\0') {
        copy_str(g_ident.descriptor_id, sizeof g_ident.descriptor_id, desc_id);
    }
    if (desc_path != NULL) {
        FILE *f = fopen(desc_path, "rb");
        const size_t n = (f != NULL) ? fread(g_desc_file, 1u, sizeof g_desc_file, f) : 0u;
        if ((f == NULL) || (n == 0u) || !feof(f)) {
            fprintf(stderr, "cannot read descriptor file %s (max 16384 bytes)\n", desc_path);
            return 2;
        }
        fclose(f);
        g_ident.descriptor_override = g_desc_file;
        g_ident.descriptor_override_len = n;
    }
    if (g_setup_override[0] != '\0') { g_ident.setup_id_override = g_setup_override; }
    if (g_fw_override[0] != '\0') { g_ident.firmware_override = g_fw_override; }

    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = on_signal;
    (void)sigaction(SIGTERM, &sa, NULL);
    (void)sigaction(SIGINT, &sa, NULL);
    (void)signal(SIGPIPE, SIG_IGN);

    struct sockaddr_in tcp_sa, udp_sa;
    if (!parse_endpoint(tcp_arg, &tcp_sa) || !parse_endpoint(stim_arg, &udp_sa)) {
        usage();
        return 2;
    }
    const int lfd = socket(AF_INET, SOCK_STREAM, 0);
    const int ufd = socket(AF_INET, SOCK_DGRAM, 0);
    const int one = 1;
    (void)setsockopt(lfd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    if ((lfd < 0) || (ufd < 0) || (bind(lfd, (struct sockaddr *)&tcp_sa, sizeof tcp_sa) != 0) || (listen(lfd, 1) != 0) ||
        (bind(ufd, (struct sockaddr *)&udp_sa, sizeof udp_sa) != 0)) {
        perror("rr_head_sim: socket/bind");
        return 2;
    }
    int pfd = -1;
    if (pty_path != NULL) {
        pfd = open_pty(pty_path);
        if (pfd < 0) {
            perror("rr_head_sim: pty");
            return 2;
        }
    }
    mcu_reset(RRH_RESET_POWER_ON, 0u);
    logf_("serial stream tcp %s%s%s, stimulus udp %s, seed %llu, clock %s", tcp_arg, (pty_path != NULL) ? ", pty " : "",
          (pty_path != NULL) ? pty_path : "", stim_arg, (unsigned long long)seed, manual ? "manual" : "real");
    /* Readiness marker for scripts (always printed, also with --quiet). */
    printf("rr_head_sim ready tcp=%s stim=%s seed=%llu\n", tcp_arg, stim_arg, (unsigned long long)seed);
    fflush(stdout);

    int cfd = -1;
    while (!g_stop) {
        struct pollfd fds[4];
        nfds_t n = 0;
        fds[n++] = (struct pollfd){lfd, POLLIN, 0};
        fds[n++] = (struct pollfd){ufd, POLLIN, 0};
        const nfds_t ci = n;
        if (cfd >= 0) { fds[n++] = (struct pollfd){cfd, POLLIN, 0}; }
        const nfds_t pi = n;
        if (pfd >= 0) { fds[n++] = (struct pollfd){pfd, POLLIN, 0}; }
        (void)poll(fds, n, (g_pending_len > 0u) ? 1 : 2);

        if (sim_mono_ns() >= g_boot_until_ns) {
            rrh_core_poll(&g_core);
        }
        flush_pending();

        if ((fds[0].revents & POLLIN) != 0) {
            const int nfd = accept(lfd, NULL, NULL);
            if (nfd >= 0) {
                if (cfd >= 0) {
                    close(cfd); /* a new host connection replaces the old one */
                }
                cfd = nfd;
                (void)setsockopt(cfd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
                (void)fcntl(cfd, F_SETFL, O_NONBLOCK);
                rrh_core_rx_timeout(&g_core);
                logf_("host connected");
            }
        }
        if ((fds[1].revents & POLLIN) != 0) {
            char msg[4096], out[2048];
            struct sockaddr_in from;
            socklen_t fl = sizeof from;
            const ssize_t len = recvfrom(ufd, msg, sizeof msg, 0, (struct sockaddr *)&from, &fl);
            if (len > 0) {
                const size_t ol = control_handle(msg, (size_t)len, out, sizeof out);
                (void)sendto(ufd, out, ol, 0, (struct sockaddr *)&from, fl);
            }
        }
        if ((cfd >= 0) && (ci < n) && (fds[ci].fd == cfd) && ((fds[ci].revents & (POLLIN | POLLHUP | POLLERR)) != 0)) {
            uint8_t buf[4096];
            const ssize_t len = read(cfd, buf, sizeof buf);
            if (len > 0) {
                serial_input(cfd, buf, (size_t)len);
            } else if ((len == 0) || ((errno != EAGAIN) && (errno != EINTR))) {
                close(cfd);
                cfd = -1;
                rrh_core_rx_timeout(&g_core);
                logf_("host disconnected");
            } else {
                /* spurious wake-up */
            }
        }
        if ((pfd >= 0) && (pi < n) && ((fds[pi].revents & POLLIN) != 0)) {
            uint8_t buf[4096];
            const ssize_t len = read(pfd, buf, sizeof buf);
            if (len > 0) {
                serial_input(pfd, buf, (size_t)len);
            }
        }
    }
    logf_("shutting down: %llu gates, %llu records sent", (unsigned long long)g_sim.gates_total,
          (unsigned long long)g_tx_records);
    if (cfd >= 0) { close(cfd); }
    close(lfd);
    close(ufd);
    if (pfd >= 0) {
        close(pfd);
        (void)unlink(pty_path);
    }
    if (g_sim.truth != NULL) {
        fclose(g_sim.truth);
    }
    return 0;
}
