/* RR-CHS 1.0 protocol server (interface/chassis_icd.md). Framing, JSON and the reply cache come
 * from firmware/common. Handlers run with the control tick masked (hal.irq_lock) so that a
 * command is applied atomically; the flash write of CONFIG_SET is done outside the lock. */
#include <math.h>
#include <string.h>

#include "rrch.h"

#define V RRCH_PROTO_V

typedef struct {
    rrch_t *c;
    const rrc_json_t *doc;
    int args;
    uint32_t id;
    uint64_t rx_us;
    rrc_jw_t w;
} ctx_t;

static void lock(rrch_t *c)
{
    if (c->hal.irq_lock) {
        c->hal.irq_lock(c->hal.ctx);
    }
}
static void unlock(rrch_t *c)
{
    if (c->hal.irq_unlock) {
        c->hal.irq_unlock(c->hal.ctx);
    }
}

/* ---- small JSON helpers ---- */
static bool tok_num(const rrc_json_t *d, int tok, double *out)
{
    size_t n;
    if (rrc_json_type(d, tok) != RRC_JT_NUMBER) {
        return false;
    }
    const char *s = rrc_json_raw(d, tok, &n);
    size_t i = 0;
    bool neg = false;
    double v = 0.0, scale = 1.0;
    int ex = 0;
    if (i < n && s[i] == '-') {
        neg = true;
        i++;
    }
    for (; i < n && s[i] >= '0' && s[i] <= '9'; i++) {
        v = v * 10.0 + (s[i] - '0');
    }
    if (i < n && s[i] == '.') {
        for (i++; i < n && s[i] >= '0' && s[i] <= '9'; i++) {
            scale *= 0.1;
            v += (s[i] - '0') * scale;
        }
    }
    if (i < n && (s[i] == 'e' || s[i] == 'E')) {
        bool eneg = false;
        i++;
        if (i < n && (s[i] == '+' || s[i] == '-')) {
            eneg = s[i] == '-';
            i++;
        }
        for (; i < n && s[i] >= '0' && s[i] <= '9' && ex < 400; i++) {
            ex = ex * 10 + (s[i] - '0');
        }
        v *= pow(10.0, eneg ? -ex : ex);
    }
    *out = neg ? -v : v;
    return true;
}

static void kf(rrc_jw_t *w, const char *key, double v, uint8_t dec)
{
    static const double p10[7] = {1, 10, 100, 1000, 10000, 100000, 1000000};
    if (key) {
        rrc_jw_key(w, key);
    }
    if (!(v == v) || v > 9e12 || v < -9e12) {
        rrc_jw_null(w);
        return;
    }
    double s = v * p10[dec];
    rrc_jw_fixed(w, (int64_t)(s < 0 ? s - 0.5 : s + 0.5), dec, true);
}

static void kmask(rrc_jw_t *w, const char *key, uint32_t mask, const char *const *names, int n)
{
    rrc_jw_key(w, key);
    rrc_jw_arr_begin(w);
    for (int i = 0; i < n; i++) {
        if (mask & (1u << i)) {
            rrc_jw_str(w, names[i]);
        }
    }
    rrc_jw_arr_end(w);
}

/* like kmask but stops after max_names entries (STATE emergency compaction) */
static void kmask_n(rrc_jw_t *w, const char *key, uint32_t mask, const char *const *names, int n, int max_names)
{
    rrc_jw_key(w, key);
    rrc_jw_arr_begin(w);
    for (int i = 0; i < n && max_names > 0; i++) {
        if (mask & (1u << i)) {
            rrc_jw_str(w, names[i]);
            max_names--;
        }
    }
    rrc_jw_arr_end(w);
}

static const char *const hold_names[2] = {"LOCAL_PAUSE", "HOST_STOP"};
static const char *const led_pat_names[5] = {"OFF", "ON", "BLINK_SLOW", "BLINK_FAST", "BLINK_2"};
static const char *const led_names[RRCH_LED_N] = {"ready", "moving", "hold", "fault", "charge"};
static const char *const panel_names[RRCH_PANEL_N] = {"AUTO", "ARRIVED", "ATTENTION", "LOCATE", "QUIET"};
static const char *const motion_names[4] = {"REST", "ALERT", "RUN", "DECEL"};
static const char *const tof_st_names[5] = {"OK", "NO_TARGET", "INVALID", "STALE", "OFFLINE"};
static const char *const chg_names[8] = {"NONE", "PRECHARGE", "CC", "CV", "DONE", "TEMP_INHIBIT", "FAULT", "UNKNOWN"};
static const char *const rst_names[6] = {"POWER_ON", "BROWNOUT", "PIN", "WATCHDOG", "SOFTWARE", "UNKNOWN"};
static const char *const loop_names[3] = {"OK", "OPEN", "SHORT"};
static const char *const bt_names[4] = {"NONE", "RUNNING", "PASSED", "FAILED"};
static const char *const btf_names[9] = {"PRECOND_VMOT", "PRECOND_RELAY", "LATCH_NOT_DROPPED", "RELAY_L", "RELAY_R", "VMOT_NOT_REMOVED", "BRIDGE_CURRENT_L", "BRIDGE_CURRENT_R", "WHEEL_MOVED"};
static const char *const ev_names[RRCH_EV_KIND_N] = {"BOOT", "BROWNOUT", "CHAIN", "HW_LATCH", "PERMIT", "J1", "J2", "BUTTON", "MODE", "PSTOP", "PSTOP_CLEAR", "HOLD", "REARM_REJECT", "OP_MODE", "CONFIG", "HEAD_POWER", "FAULT", "BRAKE_TEST", "LINK", "TOF"};
static const char *const permit_why[5] = {"NORMAL", "UNCOMMANDED_MOTION", "STOP_ESCALATION", "BRAKE_TEST", "MODE"};
static const char *const hp_why[5] = {"HOST", "PRESENCE", "CHARGE", "EFUSE", "BOOT"};

static int find_name(const rrc_json_t *d, int tok, const char *const *names, int n)
{
    if (rrc_json_type(d, tok) != RRC_JT_STRING) {
        return -1;
    }
    for (int i = 0; i < n; i++) {
        if (rrc_json_str_eq(d, tok, names[i])) {
            return i;
        }
    }
    return -1;
}

static void begin(ctx_t *x, const char *status)
{
    rrc_jw_init(&x->w, (char *)x->c->proto.tx_buf, RRCH_RECORD_MAX - RRC_FRAME_TRAILER_LEN);
    rrc_rsp_begin(&x->w, V, x->id, status);
    rrc_jw_obj_begin(&x->w);
}

static void simple(ctx_t *x, const char *status, const char *reason)
{
    begin(x, status);
    rrc_jw_kstr(&x->w, "reason", reason);
    if (strcmp(status, "REJECTED") == 0) {
        rrc_jw_kstr(&x->w, "mode", rrch_mode_names[x->c->mode]);
    }
}

static void stationary_obj(ctx_t *x)
{
    const rrch_drive_t *d = &x->c->drive;
    rrc_jw_key(&x->w, "stationary");
    rrc_jw_obj_begin(&x->w);
    rrc_jw_kbool(&x->w, "is_stationary", d->is_stationary);
    if (d->stat_run) {
        rrc_jw_ku64(&x->w, "since_us", d->stat_since_us);
    } else {
        rrc_jw_knull(&x->w, "since_us");
    }
    rrc_jw_obj_end(&x->w);
}

static void stops(ctx_t *x)
{
    rrc_jw_key(&x->w, "stops");
    rrc_jw_obj_begin(&x->w);
    kmask(&x->w, "hw", x->c->chain.hw_latched, rrch_hw_names, RRCH_HW_N);
    kmask(&x->w, "sw", x->c->sw_latched, rrch_sw_names, RRCH_SW_N);
    rrc_jw_obj_end(&x->w);
}

/* ---- ops ---- */
static void op_hello(ctx_t *x)
{
    rrch_t *c = x->c;
    const rrch_drive_t *d = &c->drive;
    if (c->boot_done && (d->motion != RRCH_MOTION_REST || (d->cmd_valid && (d->cmd_v != 0.0f || d->cmd_w != 0.0f)))) {
        rrch_pstop(c, RRCH_SW(HOST_LINK_LOST)); /* change of controlling session while moving */
    }
    c->proto.session++;
    c->proto.session_open = true;
    c->drive.seq_valid = false;
    rrc_cache_clear(&c->proto.cache);
    rrch_event(c, RRCH_EV_LINK, 1, (int32_t)c->proto.session, 0);
    begin(x, "OK");
    rrc_jw_t *w = &x->w;
    char serial[16] = "RRC-000000";
    uint32_t sn = (uint32_t)CFG(c, ID_SERIAL_NO);
    for (int i = 9; i >= 4; i--) {
        serial[i] = (char)('0' + sn % 10u);
        sn /= 10u;
    }
    char rev[2] = {(char)('A' + (int)CFG(c, ID_HW_REV) - 1), 0};
    rrc_jw_kstr(w, "fw", RRCH_FW_VERSION RRCH_FW_SUFFIX);
    rrc_jw_kstr(w, "hw_rev", rev);
    rrc_jw_kstr(w, "serial", serial);
    rrc_jw_kstr(w, "boot_id", c->boot_id);
    rrc_jw_kstr(w, "proto", RRCH_PROTO);
    rrc_jw_key(w, "caps");
    rrc_jw_obj_begin(w);
    rrc_jw_ki64(w, "encoder_cpr", RRCH_ENCODER_CPR);
    kf(w, "wheel_radius_nom_m", 0.052, 4);
    kf(w, "track_nom_m", 0.220, 4);
    kf(w, "max_v_mps", RRCH_MAX_V_FWD, 3);
    kf(w, "max_w_radps", RRCH_MAX_W, 3);
    kf(w, "max_rev_mps", RRCH_MAX_V_REV, 3);
    kf(w, "max_accel_mps2", RRCH_MAX_ACCEL, 3);
    rrc_jw_ki64(w, "ttl_ms_max", RRCH_TTL_MAX_MS);
    rrc_jw_ki64(w, "drive_hz", 50);
    rrc_jw_ki64(w, "odom_hz", 100);
    rrc_jw_ki64(w, "record_max", RRCH_RECORD_MAX);
    rrc_jw_ki64(w, "events_retained", RRCH_EVENTS_N);
    rrc_jw_ki64(w, "tof_count", RRCH_TOF_N);
    rrc_jw_obj_end(w);
    rrc_jw_ku64(w, "session", c->proto.session);
    rrc_jw_ku64(w, "uptime_us", c->hal.now_us(c->hal.ctx));
    rrc_jw_key(w, "reset");
    rrc_jw_obj_begin(w);
    rrc_jw_kstr(w, "cause", rst_names[c->reset_cause]);
    rrc_jw_ku64(w, "boot_count", c->boot_count);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "config");
    rrc_jw_obj_begin(w);
    rrc_jw_ku64(w, "gen", c->cfg.gen);
    char hex[9];
    static const char H[] = "0123456789ABCDEF";
    for (int i = 0; i < 8; i++) {
        hex[i] = H[(c->cfg.crc >> (28 - 4 * i)) & 15u];
    }
    hex[8] = 0;
    rrc_jw_kstr(w, "crc", hex);
    rrc_jw_kstr(w, "source", c->cfg.from_flash ? "FLASH" : "DEFAULTS");
    rrc_jw_obj_end(w);
}

static void op_time(ctx_t *x)
{
    begin(x, "OK");
    rrc_jw_ku64(&x->w, "rx_us", x->rx_us);
    rrc_jw_ku64(&x->w, "tx_us", x->c->hal.now_us(x->c->hal.ctx));
}

static const char *mode_reject(const rrch_t *c)
{
    return (c->mode == RRCH_MODE_ARMED_IDLE || c->mode == RRCH_MODE_MOVING) ? NULL : rrch_mode_names[c->mode];
}

static void op_drive(ctx_t *x)
{
    rrch_t *c = x->c;
    rrch_drive_t *d = &c->drive;
    const rrc_json_t *doc = x->doc;
    uint64_t seq = 0, ttl = 0, issued = 0;
    double v = 0, w = 0;
    int opm = find_name(doc, rrc_json_get(doc, x->args, "op_mode"), rrch_opmode_names, RRCH_OP_N);
    int t_issued = rrc_json_get(doc, x->args, "issued_us");
    if (!rrc_json_to_u64(doc, rrc_json_get(doc, x->args, "seq"), &seq) || seq > 0xFFFFFFFFu || !tok_num(doc, rrc_json_get(doc, x->args, "v_mps"), &v) ||
        !tok_num(doc, rrc_json_get(doc, x->args, "w_radps"), &w) || !rrc_json_to_u64(doc, rrc_json_get(doc, x->args, "ttl_ms"), &ttl) || ttl < 1u ||
        ttl > RRCH_TTL_MAX_MS || opm < 0 || fabs(v) > 0.5 || fabs(w) > 1.0 || (t_issued >= 0 && !rrc_json_to_u64(doc, t_issued, &issued)) ||
        (t_issued >= 0 && issued > x->rx_us + 20000u)) {
        simple(x, "BAD_ARG", "DRIVE needs seq, v_mps (|v|<=0.5), w_radps (|w|<=1), ttl_ms (1..250), op_mode [, issued_us]");
        return;
    }
    uint64_t now = c->hal.now_us(c->hal.ctx);
    uint64_t base = (t_issued >= 0) ? issued : x->rx_us;
    float vf, vr, wc;
    rrch_caps(c, &vf, &vr, &wc);
    bool nonzero = v != 0.0 || w != 0.0;
    const char *rej = NULL;
    if (!c->proto.session_open) {
        rej = "NO_SESSION";
    } else if (d->seq_valid && (uint32_t)seq <= d->last_seq) {
        rej = "SEQ";
    } else if (now >= base + ttl * 1000u) {
        rej = "TTL";
    } else if ((rej = mode_reject(c)) != NULL) {
    } else if (opm != (int)c->op_mode) {
        rej = "OP_MODE";
    } else if (v > (double)vf + 1e-6 || v < -(double)vr - 1e-6 || fabs(w) > (double)wc + 1e-6) {
        rej = "LIMIT";
    } else if (nonzero && CFG(c, SAFE_REQUIRE_BRAKE_TEST) >= 0.5f && !c->bt.passed_since_boot) {
        rej = "BRAKE_TEST_REQUIRED";
    } else if (nonzero && (c->fields.inhibit & rrch_drive_dir((float)v, (float)w))) {
        rej = "DIR_INHIBITED";
    }
    if (!rej) {
        d->cmd_v = (float)v;
        d->cmd_w = (float)w;
        d->cmd_expiry_us = base + ttl * 1000u;
        d->cmd_valid = true;
        d->last_seq = (uint32_t)seq;
        d->seq_valid = true;
        if (nonzero && c->mode == RRCH_MODE_ARMED_IDLE) {
            rrch_event(c, RRCH_EV_MODE, (int32_t)c->mode, RRCH_MODE_MOVING, 0);
            c->mode = RRCH_MODE_MOVING;
        }
    }
    begin(x, "OK");
    rrc_jw_t *jw = &x->w;
    rrc_jw_kbool(jw, "accepted", rej == NULL);
    if (rej) {
        rrc_jw_kstr(jw, "reject_reason", rej);
    } else {
        rrc_jw_knull(jw, "reject_reason");
    }
    rrc_jw_kstr(jw, "mode", rrch_mode_names[c->mode]);
    rrc_jw_key(jw, "odom");
    rrc_jw_obj_begin(jw);
    rrc_jw_ku64(jw, "t_us", c->odom.t_us);
    rrc_jw_ki64(jw, "left_ticks", c->odom.l);
    rrc_jw_ki64(jw, "right_ticks", c->odom.r);
    kf(jw, "left_tps", c->odom.l_tps, 1);
    kf(jw, "right_tps", c->odom.r_tps, 1);
    rrc_jw_ku64(jw, "seq", c->odom.seq);
    rrc_jw_obj_end(jw);
    rrc_jw_key(jw, "imu");
    rrc_jw_obj_begin(jw);
    rrc_jw_ku64(jw, "t_us", c->imu.t_us);
    rrc_jw_key(jw, "gyro_rps");
    rrc_jw_arr_begin(jw);
    for (int i = 0; i < 3; i++) {
        kf(jw, NULL, c->imu.gyro[i], 4);
    }
    rrc_jw_arr_end(jw);
    rrc_jw_key(jw, "accel_mps2");
    rrc_jw_arr_begin(jw);
    for (int i = 0; i < 3; i++) {
        kf(jw, NULL, c->imu.accel[i], 3);
    }
    rrc_jw_arr_end(jw);
    rrc_jw_kbool(jw, "ok", c->imu.ok);
    rrc_jw_obj_end(jw);
    stops(x);
    stationary_obj(x);
    rrc_jw_ku64(jw, "event_seq", c->ev_newest);
    rrc_jw_key(jw, "applied");
    rrc_jw_obj_begin(jw);
    kf(jw, "v_mps", d->v_sp, 4);
    kf(jw, "w_radps", d->w_sp, 4);
    rrc_jw_obj_end(jw);
    rrc_jw_kstr(jw, "motion", motion_names[d->motion]);
    rrc_jw_key(jw, "allow");
    rrc_jw_obj_begin(jw);
    rrc_jw_kbool(jw, "fwd", !(c->fields.inhibit & RRCH_DIR_FWD));
    rrc_jw_kbool(jw, "rev", !(c->fields.inhibit & RRCH_DIR_REV));
    rrc_jw_kbool(jw, "pivot", !(c->fields.inhibit & RRCH_DIR_PIVOT));
    rrc_jw_obj_end(jw);
    kf(jw, "v_cap_mps", c->fields.v_cap_fwd, 4);
    kmask(jw, "hold", c->hold, hold_names, 2);
    rrc_jw_ku64(jw, "rearm_nonce", c->rearm_nonce);
}

/* The contract STATE content does not always fit in 2048 bytes when many reasons and flags are
 * set at once. level 0: complete; 1: faults list emptied; 2: protective_stop_reasons cut to 8
 * names as well. Levels 1 and 2 add "truncated":true; DIAG always carries the complete lists.
 * The caller retries with the next level if the record would exceed the limit. */
static void op_state(ctx_t *x, int level)
{
    rrch_t *c = x->c;
    rrc_jw_t *w = &x->w;
    const rrch_chain_t *ch = &c->chain;
    uint32_t st = ch->state;
    begin(x, "OK");
    rrc_jw_kstr(w, "mode", rrch_mode_names[c->mode]);
    rrc_jw_kstr(w, "op_mode", rrch_opmode_names[c->op_mode]);
    rrc_jw_kbool(w, "hw_latch", ch->latch);
    rrc_jw_key(w, "chain");
    rrc_jw_obj_begin(w);
    rrc_jw_kbool(w, "MODE_RUN", (st & RRCH_DI(MODE_RUN)) != 0);
    rrc_jw_kbool(w, "ESTOP", (st & RRCH_DI(ESTOP_A)) && (st & RRCH_DI(ESTOP_B)));
    rrc_jw_kbool(w, "HANDS_ON", (st & RRCH_DI(HANDS_ON)) != 0);
    rrc_jw_kbool(w, "CHG_COVER", (st & RRCH_DI(CHG_COVER)) && (st & RRCH_DI(CHG_PLUG_LINK)));
    rrc_jw_kbool(w, "HEAD_DOCK", (st & RRCH_DI(HEAD_DOCK)) != 0);
    rrc_jw_kbool(w, "HEAD_LOOP", ch->loop_state == 0u);
    rrc_jw_kbool(w, "LAB_KEY_N", !(ch->hw_live & RRCH_HW(LAB_KEY)));
    rrc_jw_kbool(w, "BODY_BUMPER", (st & RRCH_DI(BODY_BUMPER_L)) && (st & RRCH_DI(BODY_BUMPER_R)));
    rrc_jw_kbool(w, "WDG_OK", (st & RRCH_DI(WDG_OK)) != 0);
    rrc_jw_kbool(w, "ARM_PERMIT", c->out.arm_permit);
    rrc_jw_obj_end(w);
    kmask(w, "hw_inhibit_reasons", ch->hw_latched, rrch_hw_names, RRCH_HW_N);
    kmask_n(w, "protective_stop_reasons", c->sw_latched, rrch_sw_names, RRCH_SW_N, level < 2 ? RRCH_SW_N : 8);
    rrc_jw_kstr(w, "head_presence", rrch_pres_names[ch->pres]);
    rrc_jw_kbool(w, "j2_present", (st & RRCH_DI(J2_PRES)) != 0);
    rrc_jw_key(w, "rails");
    rrc_jw_obj_begin(w);
    kf(w, "vbat_v", c->in.vbat_v, 2);
    kf(w, "vmot_v", c->in.vmot_v, 2);
    kf(w, "ibat_a", c->pwr.pmon_ok ? c->pwr.ibat_a : NAN, 2);
    rrc_jw_key(w, "i_drive_a");
    rrc_jw_arr_begin(w);
    kf(w, NULL, c->drive.i_f[0], 2);
    kf(w, NULL, c->drive.i_f[1], 2);
    rrc_jw_arr_end(w);
    kf(w, "i_head_a", c->pwr.i_head_a, 2);
    kf(w, "i_head_htr_a", c->pwr.i_head_htr_a, 2);
    kf(w, "i_chs_htr_a", c->pwr.i_chs_htr_a, 2);
    kf(w, "v5_v", c->in.v5_v, 2);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "battery");
    rrc_jw_obj_begin(w);
    kf(w, "soc_pct", c->pwr.soc_pct < 0.0f ? NAN : c->pwr.soc_pct, 0);
    rrc_jw_key(w, "temp_c");
    rrc_jw_arr_begin(w);
    kf(w, NULL, c->pwr.chg_temp_c, 1);
    kf(w, NULL, c->in.ntc_c[1], 1);
    rrc_jw_arr_end(w);
    rrc_jw_kstr(w, "charge_state", chg_names[c->pwr.charge_state]);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "temps");
    rrc_jw_obj_begin(w);
    kf(w, "board_c", c->in.ntc_c[2], 1);
    kf(w, "bay_c", c->in.ntc_c[0], 1);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "tof");
    rrc_jw_arr_begin(w);
    for (int i = 0; i < RRCH_TOF_N; i++) {
        const rrch_tof_t *s = &c->tof[i];
        uint64_t age = s->seen ? (c->now_us - (s->t_us < c->now_us ? s->t_us : c->now_us)) / 1000u : 9999u;
        rrc_jw_obj_begin(w);
        rrc_jw_kstr(w, "id", rrch_tof_names[i]);
        if (s->valid) {
            rrc_jw_ki64(w, "range_mm", s->range_mm);
        } else {
            rrc_jw_knull(w, "range_mm");
        }
        rrc_jw_kstr(w, "status", tof_st_names[s->eff]);
        rrc_jw_ku64(w, "age_ms", age > 9999u ? 9999u : age);
        rrc_jw_obj_end(w);
    }
    rrc_jw_arr_end(w);
    rrc_jw_key(w, "bumpers");
    rrc_jw_obj_begin(w);
    rrc_jw_kbool(w, "body_l", !(st & RRCH_DI(BODY_BUMPER_L)));
    rrc_jw_kbool(w, "body_r", !(st & RRCH_DI(BODY_BUMPER_R)));
    rrc_jw_kstr(w, "head_loop", loop_names[ch->loop_state]);
    if (ch->loop_ohm > 100000u) {
        rrc_jw_knull(w, "head_loop_ohm");
    } else {
        rrc_jw_ku64(w, "head_loop_ohm", ch->loop_ohm);
    }
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "panel");
    rrc_jw_obj_begin(w);
    rrc_jw_key(w, "buttons");
    rrc_jw_obj_begin(w);
    rrc_jw_kbool(w, "rearm", (st & RRCH_DI(BTN_REARM)) != 0);
    rrc_jw_kbool(w, "pause", (st & RRCH_DI(BTN_PAUSE)) != 0);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "leds");
    rrc_jw_obj_begin(w);
    for (int i = 0; i < RRCH_LED_N; i++) {
        rrc_jw_kstr(w, led_names[i], led_pat_names[c->led_pat[i]]);
    }
    rrc_jw_obj_end(w);
    rrc_jw_kbool(w, "buzzer", c->out.buzzer);
    rrc_jw_kstr(w, "pattern", panel_names[c->panel_pat]);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "heater");
    rrc_jw_obj_begin(w);
    kf(w, "chassis_duty_pct", c->htr_duty * 100.0f, 0);
    kf(w, "chassis_setpoint_c", c->htr_enabled ? c->htr_setpoint_c : NAN, 1);
    rrc_jw_kbool(w, "sensor_ok", c->htr_sensor_ok);
    rrc_jw_obj_end(w);
    kmask(w, "faults", level < 1 ? c->faults : 0u, rrch_flt_names, RRCH_FLT_N);
    if (level > 0) {
        rrc_jw_kbool(w, "truncated", true);
    }
    stationary_obj(x);
    rrc_jw_kbool(w, "rearm_ready", !ch->latch && c->boot_done && ch->hw_live == 0u && c->out.arm_permit);
    rrc_jw_ku64(w, "rearm_nonce", c->rearm_nonce);
    kmask(w, "hold", c->hold, hold_names, 2);
    rrc_jw_ku64(w, "event_seq", c->ev_newest);
    rrc_jw_ku64(w, "uptime_us", c->now_us);
}

/* Additive op: complete reason/flag lists and engineering detail that does not fit in STATE. */
static void op_diag(ctx_t *x)
{
    rrch_t *c = x->c;
    rrc_jw_t *w = &x->w;
    const rrch_chain_t *ch = &c->chain;
    uint32_t st = ch->state;
    begin(x, "OK");
    rrc_jw_kstr(w, "mode", rrch_mode_names[c->mode]);
    kmask(w, "hw_inhibit_reasons", ch->hw_latched, rrch_hw_names, RRCH_HW_N);
    kmask(w, "hw_active", ch->hw_live, rrch_hw_names, RRCH_HW_N);
    kmask(w, "protective_stop_reasons", c->sw_latched, rrch_sw_names, RRCH_SW_N);
    kmask(w, "sw_active", c->sw_active, rrch_sw_names, RRCH_SW_N);
    kmask(w, "sw_acknowledged", c->sw_acked, rrch_sw_names, RRCH_SW_N);
    kmask(w, "faults", c->faults, rrch_flt_names, RRCH_FLT_N);
    rrc_jw_key(w, "estop");
    rrc_jw_obj_begin(w);
    rrc_jw_kbool(w, "a", (st & RRCH_DI(ESTOP_A)) != 0);
    rrc_jw_kbool(w, "b", (st & RRCH_DI(ESTOP_B)) != 0);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "readbacks");
    rrc_jw_obj_begin(w);
    for (int i = 0; i < RRCH_DI_N; i++) {
        rrc_jw_kbool(w, rrch_di_names[i], (st & (1u << i)) != 0);
    }
    rrc_jw_obj_end(w);
    rrc_jw_ku64(w, "pres_ohm", ch->pres_ohm > 999999u ? 999999u : ch->pres_ohm);
    rrc_jw_key(w, "head_power");
    rrc_jw_obj_begin(w);
    rrc_jw_kbool(w, "electronics", c->head_pwr);
    rrc_jw_kbool(w, "heater_enable", c->head_htr);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "brake_test");
    rrc_jw_obj_begin(w);
    rrc_jw_kstr(w, "state", bt_names[c->bt.state]);
    if (c->bt.state == RRCH_BT_PASSED || c->bt.state == RRCH_BT_FAILED) {
        rrc_jw_ku64(w, "age_s", (c->now_us - c->bt.done_us) / 1000000u);
    } else {
        rrc_jw_knull(w, "age_s");
    }
    rrc_jw_kbool(w, "passed_since_boot", c->bt.passed_since_boot);
    rrc_jw_obj_end(w);
    kf(w, "tilt_deg", c->tilt_deg, 1);
    rrc_jw_key(w, "drive");
    rrc_jw_obj_begin(w);
    rrc_jw_key(w, "duty");
    rrc_jw_arr_begin(w);
    kf(w, NULL, c->drive.duty[0], 3);
    kf(w, NULL, c->drive.duty[1], 3);
    rrc_jw_arr_end(w);
    kf(w, "v_meas_mps", c->drive.v_meas, 4);
    kf(w, "w_meas_radps", c->drive.w_meas_body, 4);
    kf(w, "v_cap_fwd_mps", c->fields.v_cap_fwd, 4);
    kf(w, "v_cap_rev_mps", c->fields.v_cap_rev, 4);
    rrc_jw_kbool(w, "bridge_awake", c->out.bridge_awake);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "link");
    rrc_jw_obj_begin(w);
    rrc_jw_ku64(w, "session", c->proto.session);
    rrc_jw_ku64(w, "requests", c->proto.n_req);
    rrc_jw_ku64(w, "discarded", c->proto.n_bad + c->proto.rx.n_discarded);
    rrc_jw_obj_end(w);
}

static void event_detail(rrch_t *c, rrc_jw_t *w, const rrch_event_t *e)
{
    rrc_jw_obj_begin(w);
    switch (e->kind) {
    case RRCH_EV_BOOT:
        rrc_jw_kstr(w, "reset", rst_names[e->a % 6]);
        rrc_jw_ki64(w, "boot_count", e->b);
        rrc_jw_kstr(w, "fw", RRCH_FW_VERSION RRCH_FW_SUFFIX);
        if (e->c >= 0 && e->c < RRCH_MODE_N) {
            rrc_jw_kstr(w, "prev_mode", rrch_mode_names[e->c]);
            kf(w, "prev_uptime_s", e->f, 0);
        } else {
            rrc_jw_knull(w, "prev_mode");
            rrc_jw_knull(w, "prev_uptime_s");
        }
        rrc_jw_kbool(w, "brownout", e->g != 0.0f || e->a == RRCH_RST_BROWNOUT);
        break;
    case RRCH_EV_BROWNOUT: kf(w, "vbat_v", e->f, 2); break;
    case RRCH_EV_CHAIN:
        rrc_jw_kstr(w, "el", rrch_di_names[e->a]);
        rrc_jw_kbool(w, "closed", e->b != 0);
        break;
    case RRCH_EV_HW_LATCH:
        rrc_jw_kbool(w, "set", e->a != 0);
        kmask(w, "reasons", (uint32_t)e->b, rrch_hw_names, RRCH_HW_N);
        break;
    case RRCH_EV_PERMIT:
        rrc_jw_kbool(w, "on", e->a != 0);
        rrc_jw_kstr(w, "why", permit_why[e->b % 5]);
        break;
    case RRCH_EV_J1:
        rrc_jw_kstr(w, "from", rrch_pres_names[e->a]);
        rrc_jw_kstr(w, "to", rrch_pres_names[e->b]);
        rrc_jw_ki64(w, "ohm", e->c);
        break;
    case RRCH_EV_J2: rrc_jw_kbool(w, "present", e->a != 0); break;
    case RRCH_EV_BUTTON:
        rrc_jw_kstr(w, "name", e->a ? "PAUSE" : "REARM");
        rrc_jw_kbool(w, "pressed", e->b != 0);
        break;
    case RRCH_EV_MODE:
        rrc_jw_kstr(w, "from", rrch_mode_names[e->a]);
        rrc_jw_kstr(w, "to", rrch_mode_names[e->b]);
        break;
    case RRCH_EV_PSTOP:
        rrc_jw_kstr(w, "reason", rrch_sw_names[e->a]);
        kf(w, "v_mps", e->f, 3);
        break;
    case RRCH_EV_PSTOP_CLEAR:
        rrc_jw_kstr(w, "by", e->a ? "LOCAL" : "REARM_SW");
        rrc_jw_kstr(w, "operator", e->s);
        kmask(w, "cleared", (uint32_t)e->b, rrch_sw_names, RRCH_SW_N);
        break;
    case RRCH_EV_HOLD:
        rrc_jw_kbool(w, "on", e->a != 0);
        kmask(w, "why", (uint32_t)e->b, hold_names, 2);
        break;
    case RRCH_EV_REARM_REJECT:
        rrc_jw_kstr(w, "why", e->a ? "NONCE" : "CAUSE_ACTIVE");
        rrc_jw_kstr(w, "operator", e->s);
        kmask(w, "active", (uint32_t)e->b, rrch_sw_names, RRCH_SW_N);
        break;
    case RRCH_EV_OP_MODE:
        rrc_jw_kstr(w, "from", rrch_opmode_names[e->a]);
        rrc_jw_kstr(w, "to", rrch_opmode_names[e->b]);
        break;
    case RRCH_EV_CONFIG:
        rrc_jw_kstr(w, "key", e->a >= 0 ? rrch_cfg_desc[e->a].name : "_defaults");
        kf(w, "old", e->f, 4);
        kf(w, "new", e->g, 4);
        rrc_jw_ki64(w, "gen", e->b);
        break;
    case RRCH_EV_HEAD_POWER:
        rrc_jw_kbool(w, "electronics", e->a != 0);
        rrc_jw_kbool(w, "heater_enable", e->b != 0);
        rrc_jw_kstr(w, "why", hp_why[e->c % 5]);
        break;
    case RRCH_EV_FAULT:
        rrc_jw_kstr(w, "flag", rrch_flt_names[e->a]);
        rrc_jw_kbool(w, "on", e->b != 0);
        break;
    case RRCH_EV_BRAKE_TEST:
        rrc_jw_kbool(w, "passed", e->a != 0);
        kmask(w, "fail", (uint32_t)e->b, btf_names, 9);
        break;
    case RRCH_EV_LINK:
        rrc_jw_kbool(w, "up", e->a != 0);
        rrc_jw_ki64(w, "session", e->b);
        break;
    case RRCH_EV_TOF:
        rrc_jw_kstr(w, "id", rrch_tof_names[e->a]);
        rrc_jw_kstr(w, "status", tof_st_names[e->b % 5]);
        break;
    default: break;
    }
    rrc_jw_obj_end(w);
    (void)c;
}

static void op_events(ctx_t *x)
{
    rrch_t *c = x->c;
    uint64_t after = 0;
    if (!rrc_json_to_u64(x->doc, rrc_json_get(x->doc, x->args, "after_seq"), &after) || after > 0xFFFFFFFFu) {
        simple(x, "BAD_ARG", "after_seq (u32) required");
        return;
    }
    uint32_t newest = c->ev_newest;
    uint32_t oldest = newest == 0u ? 0u : (newest > RRCH_EVENTS_N ? newest - RRCH_EVENTS_N + 1u : 1u);
    uint32_t from = (uint32_t)after + 1u;
    bool gap = newest != 0u && from < oldest;
    if (from < oldest) {
        from = oldest;
    }
    begin(x, "OK");
    rrc_jw_t *w = &x->w;
    rrc_jw_ku64(w, "newest_seq", newest);
    rrc_jw_ku64(w, "oldest_seq", oldest);
    rrc_jw_kbool(w, "gap", gap);
    rrc_jw_key(w, "events");
    rrc_jw_arr_begin(w);
    uint32_t s = from;
    for (; newest != 0u && s <= newest && s >= from; s++) {
        if (rrc_jw_len(w) > RRCH_RECORD_MAX - 330u) {
            break; /* leave room for the largest event and the tail */
        }
        const rrch_event_t *e = &c->ev[(s - 1u) % RRCH_EVENTS_N];
        rrc_jw_obj_begin(w);
        rrc_jw_ku64(w, "seq", e->seq);
        rrc_jw_ku64(w, "t_us", e->t_us);
        rrc_jw_kstr(w, "kind", ev_names[e->kind]);
        rrc_jw_key(w, "detail");
        event_detail(c, w, e);
        rrc_jw_obj_end(w);
    }
    rrc_jw_arr_end(w);
    rrc_jw_kbool(w, "more", newest != 0u && s <= newest);
}

static void op_rearm(ctx_t *x)
{
    rrch_t *c = x->c;
    uint64_t nonce = 0;
    char op[33];
    int n = rrc_json_str_copy(x->doc, rrc_json_get(x->doc, x->args, "operator"), op, sizeof op);
    bool ok = n >= 1 && rrc_json_to_u64(x->doc, rrc_json_get(x->doc, x->args, "nonce"), &nonce) && nonce <= 0xFFFFFFFFu;
    for (int i = 0; ok && i < n; i++) {
        ok = op[i] >= 0x20 && op[i] < 0x7F;
    }
    if (!ok) {
        simple(x, "BAD_ARG", "nonce (u32) and operator (1..32 printable ASCII) required");
        return;
    }
    if (!c->proto.session_open || c->mode == RRCH_MODE_BOOT || c->mode == RRCH_MODE_FAULT) {
        simple(x, "REJECTED", !c->proto.session_open ? "NO_SESSION" : rrch_mode_names[c->mode]);
        return;
    }
    if ((uint32_t)nonce != c->rearm_nonce) {
        rrch_event_t *e = rrch_event(c, RRCH_EV_REARM_REJECT, 1, 0, 0);
        rrch_str16(e->s, op);
        simple(x, "REJECTED", "NONCE");
        rrc_jw_ku64(&x->w, "rearm_nonce", c->rearm_nonce);
        return;
    }
    uint32_t blocked, hc;
    uint32_t cleared = rrch_rearm_sw(c, false, op, &blocked, &hc);
    if (blocked) {
        simple(x, "REJECTED", "CAUSE_ACTIVE");
        kmask(&x->w, "active", blocked, rrch_sw_names, RRCH_SW_N);
        rrc_jw_ku64(&x->w, "rearm_nonce", c->rearm_nonce);
        return;
    }
    /* the mode shown is the one the next control tick will compute */
    rrch_mode_t m = c->mode;
    if (m == RRCH_MODE_PROTECTIVE_STOP || m == RRCH_MODE_HOLD) {
        m = c->chain.latch ? RRCH_MODE_ARMED_IDLE : RRCH_MODE_STANDBY;
    }
    begin(x, "OK");
    kmask(&x->w, "cleared", cleared, rrch_sw_names, RRCH_SW_N);
    kmask(&x->w, "hold_cleared", hc, hold_names, 2);
    rrc_jw_kstr(&x->w, "mode", rrch_mode_names[m]);
    rrc_jw_kbool(&x->w, "hw_latch", c->chain.latch);
    rrc_jw_ku64(&x->w, "rearm_nonce", c->rearm_nonce);
}

static void op_stop(ctx_t *x)
{
    rrch_t *c = x->c;
    static const char *const kinds[2] = {"CONTROLLED", "PROTECTIVE"};
    static const uint8_t host_reasons[7] = {RRCH_SWI_HOST_REQUEST, RRCH_SWI_FIELD_FRONT, RRCH_SWI_FIELD_LEFT, RRCH_SWI_FIELD_RIGHT, RRCH_SWI_FIELD_REAR, RRCH_SWI_HEAD_LINK, RRCH_SWI_LOCALIZATION};
    int kind = find_name(x->doc, rrc_json_get(x->doc, x->args, "kind"), kinds, 2);
    int tr = rrc_json_get(x->doc, x->args, "reason");
    int reason = RRCH_SWI_HOST_REQUEST;
    if (tr >= 0) {
        reason = -1;
        for (int i = 0; i < 7; i++) {
            if (rrc_json_str_eq(x->doc, tr, rrch_sw_names[host_reasons[i]])) {
                reason = host_reasons[i];
            }
        }
    }
    if (kind < 0 || reason < 0 || (kind == 0 && tr >= 0)) {
        simple(x, "BAD_ARG", "kind CONTROLLED|PROTECTIVE [, reason (PROTECTIVE only)]");
        return;
    }
    rrch_mode_t m = c->mode;
    bool armed = c->chain.latch && (m == RRCH_MODE_ARMED_IDLE || m == RRCH_MODE_MOVING || m == RRCH_MODE_HOLD || m == RRCH_MODE_PROTECTIVE_STOP);
    if (kind == 1) {
        rrch_pstop(c, 1u << reason);
        if (armed || m == RRCH_MODE_STANDBY) {
            m = RRCH_MODE_PROTECTIVE_STOP;
        }
    } else {
        rrch_hold(c, RRCH_HOLD_HOST_STOP);
        if (armed && m != RRCH_MODE_PROTECTIVE_STOP) {
            m = RRCH_MODE_HOLD;
        }
    }
    begin(x, "OK");
    rrc_jw_kstr(&x->w, "mode", rrch_mode_names[m]);
    stops(x);
    kmask(&x->w, "hold", c->hold, hold_names, 2);
    rrc_jw_ku64(&x->w, "rearm_nonce", c->rearm_nonce);
}

static bool need_session(ctx_t *x)
{
    if (!x->c->proto.session_open) {
        simple(x, "REJECTED", "NO_SESSION");
        return false;
    }
    return true;
}

static bool stationary(const rrch_t *c)
{
    const rrch_drive_t *d = &c->drive;
    return d->motion == RRCH_MOTION_REST && d->at_rest && !(d->cmd_valid && (d->cmd_v != 0.0f || d->cmd_w != 0.0f));
}

static void op_set_op_mode(ctx_t *x)
{
    rrch_t *c = x->c;
    int opm = find_name(x->doc, rrc_json_get(x->doc, x->args, "op_mode"), rrch_opmode_names, RRCH_OP_N);
    if (opm < 0) {
        simple(x, "BAD_ARG", "op_mode must be one of the op_mode enum");
        return;
    }
    if (!need_session(x)) {
        return;
    }
    if (!stationary(c)) {
        simple(x, "REJECTED", "NOT_STATIONARY");
        return;
    }
    if (opm != (int)c->op_mode) {
        rrch_event(c, RRCH_EV_OP_MODE, (int32_t)c->op_mode, opm, 0);
        c->op_mode = (rrch_opmode_t)opm;
    }
    float vf, vr, wc;
    rrch_caps(c, &vf, &vr, &wc);
    begin(x, "OK");
    rrc_jw_kstr(&x->w, "op_mode", rrch_opmode_names[c->op_mode]);
    rrc_jw_key(&x->w, "caps");
    rrc_jw_obj_begin(&x->w);
    kf(&x->w, "v_fwd_mps", vf, 4);
    kf(&x->w, "v_rev_mps", vr, 4);
    kf(&x->w, "w_radps", wc, 4);
    rrc_jw_obj_end(&x->w);
}

static void op_head_power(ctx_t *x)
{
    rrch_t *c = x->c;
    bool el, htr;
    if (!rrc_json_to_bool(x->doc, rrc_json_get(x->doc, x->args, "electronics"), &el) || !rrc_json_to_bool(x->doc, rrc_json_get(x->doc, x->args, "heater_enable"), &htr) || (htr && !el)) {
        simple(x, "BAD_ARG", "electronics and heater_enable (bool) required; heater needs electronics");
        return;
    }
    if (!need_session(x)) {
        return;
    }
    rrch_pres_t p = c->chain.pres;
    if (el || htr) {
        if (c->mode == RRCH_MODE_SERVICE_CHARGE || c->mode == RRCH_MODE_BOOT || c->mode == RRCH_MODE_FAULT) {
            simple(x, "REJECTED", rrch_mode_names[c->mode]);
            return;
        }
        if (p != RRCH_PRES_HEAD_DIRECT && p != RRCH_PRES_HEAD_VIA_LAB_EXTENSION) {
            simple(x, "REJECTED", p == RRCH_PRES_FAULT ? "PRES_FAULT" : "HEAD_ABSENT");
            return;
        }
    }
    rrch_set_head_power(c, el, htr, 0);
    begin(x, "OK");
    rrc_jw_kbool(&x->w, "electronics", c->head_pwr);
    rrc_jw_kbool(&x->w, "heater_enable", c->head_htr);
    rrc_jw_kstr(&x->w, "head_presence", rrch_pres_names[p]);
}

static void op_heater(ctx_t *x)
{
    rrch_t *c = x->c;
    int t = rrc_json_get(x->doc, x->args, "chassis_setpoint_c");
    double sp = 0;
    bool off = rrc_json_is_null(x->doc, t);
    if (!off && (!tok_num(x->doc, t, &sp) || sp < 0.0 || sp > 30.0)) {
        simple(x, "BAD_ARG", "chassis_setpoint_c must be 0..30 or null");
        return;
    }
    if (!need_session(x)) {
        return;
    }
    c->htr_enabled = !off;
    c->htr_setpoint_c = off ? NAN : (float)sp;
    begin(x, "OK");
    kf(&x->w, "chassis_setpoint_c", c->htr_setpoint_c, 1);
    kf(&x->w, "duty_pct", c->htr_duty * 100.0f, 0);
    kf(&x->w, "bay_c", c->in.ntc_c[0], 1);
    rrc_jw_kbool(&x->w, "sensor_ok", c->htr_sensor_ok);
}

static void op_panel(ctx_t *x)
{
    rrch_t *c = x->c;
    int p = find_name(x->doc, rrc_json_get(x->doc, x->args, "pattern"), panel_names, RRCH_PANEL_N);
    if (p < 0) {
        simple(x, "BAD_ARG", "pattern must be AUTO|ARRIVED|ATTENTION|LOCATE|QUIET");
        return;
    }
    if (!need_session(x)) {
        return;
    }
    bool host_ok = c->mode == RRCH_MODE_STANDBY || c->mode == RRCH_MODE_ARMED_IDLE || c->mode == RRCH_MODE_HOLD;
    c->panel_pat = host_ok ? (rrch_panel_pat_t)p : RRCH_PANEL_AUTO;
    if (host_ok && p == RRCH_PANEL_ARRIVED) {
        c->beep_count = 1;
        c->beep_on_ms = c->beep_ms_left = 60;
        c->beep_gap = 0;
    }
    if (c->panel_pat == RRCH_PANEL_ARRIVED) { /* shown at once; the control tick recomputes it every ms */
        c->led_pat[RRCH_LED_READY] = RRCH_LED_BLINK_2;
    } else if (c->panel_pat == RRCH_PANEL_LOCATE) {
        memset(c->led_pat, RRCH_LED_BLINK_FAST, RRCH_LED_N);
    }
    begin(x, "OK");
    rrc_jw_kstr(&x->w, "pattern", panel_names[c->panel_pat]);
    rrc_jw_key(&x->w, "leds");
    rrc_jw_obj_begin(&x->w);
    for (int i = 0; i < RRCH_LED_N; i++) {
        rrc_jw_kstr(&x->w, led_names[i], led_pat_names[c->led_pat[i]]);
    }
    rrc_jw_obj_end(&x->w);
    rrc_jw_kbool(&x->w, "buzzer", c->out.buzzer);
}

static void cfg_crc_hex(rrc_jw_t *w, uint32_t crc)
{
    static const char H[] = "0123456789ABCDEF";
    char hex[9];
    for (int i = 0; i < 8; i++) {
        hex[i] = H[(crc >> (28 - 4 * i)) & 15u];
    }
    hex[8] = 0;
    rrc_jw_kstr(w, "crc", hex);
}

static void op_config(ctx_t *x, bool set)
{
    rrch_t *c = x->c;
    char key[48];
    if (rrc_json_str_copy(x->doc, rrc_json_get(x->doc, x->args, "key"), key, sizeof key) < 1) {
        simple(x, "BAD_ARG", "key (string) required");
        return;
    }
    if (!set && strcmp(key, "_keys") == 0) {
        uint64_t off = 0;
        (void)rrc_json_to_u64(x->doc, rrc_json_get(x->doc, x->args, "offset"), &off);
        begin(x, "OK");
        rrc_jw_key(&x->w, "keys");
        rrc_jw_arr_begin(&x->w);
        for (uint64_t i = off; i < (uint64_t)RRCH_CFG_N && i < off + 24u; i++) {
            rrc_jw_str(&x->w, rrch_cfg_desc[i].name);
        }
        rrc_jw_arr_end(&x->w);
        rrc_jw_ki64(&x->w, "total", RRCH_CFG_N);
        rrc_jw_ku64(&x->w, "offset", off);
        return;
    }
    int k = rrch_cfg_find(key);
    if (k < 0) {
        simple(x, "BAD_ARG", "unknown key");
        return;
    }
    const rrch_cfg_desc_t *d = &rrch_cfg_desc[k];
    if (!set) {
        begin(x, "OK");
        rrc_jw_kstr(&x->w, "key", d->name);
        kf(&x->w, "value", c->cfg.v[k], 4);
        kf(&x->w, "default", d->def, 4);
        kf(&x->w, "min", d->min, 4);
        kf(&x->w, "max", d->max, 4);
        rrc_jw_kstr(&x->w, "unit", d->unit);
        rrc_jw_kbool(&x->w, "rw", true);
        return;
    }
    double val;
    bool bv;
    int tv = rrc_json_get(x->doc, x->args, "value");
    if (rrc_json_to_bool(x->doc, tv, &bv)) {
        val = bv ? 1.0 : 0.0;
    } else if (!tok_num(x->doc, tv, &val)) {
        simple(x, "BAD_ARG", "value (number) required");
        return;
    }
    if (!(val >= (double)d->min - 1e-9 && val <= (double)d->max + 1e-9)) {
        simple(x, "BAD_ARG", "value out of range");
        return;
    }
    if (!need_session(x)) {
        return;
    }
    if (!stationary(c) || c->mode == RRCH_MODE_MOVING) {
        simple(x, "REJECTED", "NOT_STATIONARY");
        return;
    }
    float old = c->cfg.v[k];
    c->cfg.v[k] = (float)val;
    unlock(c); /* flash write outside the lock; the robot is stationary */
    bool ok = rrch_cfg_save(&c->cfg, &c->hal);
    lock(c);
    if (!ok) {
        c->cfg.v[k] = old;
        simple(x, "FAULT", "NV_WRITE");
        return;
    }
    rrch_fault_set(c, RRCH_FLT(CONFIG_DEFAULTED), false);
    rrch_event_t *e = rrch_event(c, RRCH_EV_CONFIG, k, (int32_t)c->cfg.gen, 0);
    e->f = old;
    e->g = (float)val;
    begin(x, "OK");
    rrc_jw_kstr(&x->w, "key", d->name);
    kf(&x->w, "value", c->cfg.v[k], 4);
    kf(&x->w, "old", old, 4);
    rrc_jw_ku64(&x->w, "gen", c->cfg.gen);
    cfg_crc_hex(&x->w, c->cfg.crc);
}

static void bt_body(ctx_t *x)
{
    rrch_t *c = x->c;
    const rrch_brake_test_t *b = &c->bt;
    rrc_jw_t *w = &x->w;
    begin(x, "OK");
    rrc_jw_kbool(w, "passed", b->state == RRCH_BT_PASSED);
    kmask(w, "fail", b->fail, btf_names, 9);
    rrc_jw_ki64(w, "latch_drop_ms", b->latch_drop_ms);
    rrc_jw_ki64(w, "relay_ms", b->relay_ms);
    rrc_jw_ki64(w, "vmot_decay_ms", b->vmot_decay_ms);
    kf(w, "vmot_end_v", b->vmot_end_v, 2);
    rrc_jw_key(w, "probe_i_a");
    rrc_jw_arr_begin(w);
    kf(w, NULL, b->probe_i[0], 3);
    kf(w, NULL, b->probe_i[1], 3);
    rrc_jw_arr_end(w);
    rrc_jw_key(w, "moved_ticks");
    rrc_jw_arr_begin(w);
    rrc_jw_i64(w, b->moved[0]);
    rrc_jw_i64(w, b->moved[1]);
    rrc_jw_arr_end(w);
    rrch_mode_t m = c->mode;
    rrc_jw_kstr(w, "mode", rrch_mode_names[m]);
}

/* ---- transport ---- */
static void send(rrch_t *c, ctx_t *x, uint32_t crc, size_t req_len, bool cache)
{
    rrc_jw_obj_end(&x->w);
    rrc_rsp_end(&x->w);
    size_t n = rrc_jw_ok(&x->w) ? rrc_frame_finish(c->proto.tx_buf, rrc_jw_len(&x->w), sizeof c->proto.tx_buf, RRCH_RECORD_MAX) : 0u;
    if (n == 0u) { /* never expected: answer FAULT rather than nothing */
        simple(x, "FAULT", "REPLY_TOO_LARGE");
        rrc_jw_obj_end(&x->w);
        rrc_rsp_end(&x->w);
        n = rrc_frame_finish(c->proto.tx_buf, rrc_jw_len(&x->w), sizeof c->proto.tx_buf, RRCH_RECORD_MAX);
    }
    if (cache) {
        rrc_cache_store(&c->proto.cache, x->id, crc, req_len, n);
    } else {
        rrc_cache_clear(&c->proto.cache);
    }
    unlock(c);
    (void)c->hal.link_write(c->hal.ctx, c->proto.tx_buf, n);
    lock(c);
}

static void handle(rrch_t *c, size_t json_len, uint32_t crc)
{
    rrch_proto_t *p = &c->proto;
    rrc_jtok_t tok[64];
    rrc_json_t doc;
    static const rrc_json_limits_t lim = {4, 96};
    ctx_t x;
    memset(&x, 0, sizeof x);
    x.c = c;
    x.rx_us = c->hal.now_us(c->hal.ctx);
    if (rrc_json_parse(&doc, (const char *)p->rx_buf, json_len, tok, 64, &lim) != RRC_JSON_OK) {
        p->n_bad++;
        return;
    }
    rrc_req_t req;
    rrc_req_status_t rs = rrc_req_parse(&doc, V, &req);
    if (rs == RRC_REQ_INVALID) {
        p->n_bad++;
        return;
    }
    x.doc = &doc;
    x.id = req.id;
    x.args = req.args;
    lock(c);
    p->n_req++;
    p->last_rx_us = x.rx_us;
    p->any_rx = true;
    bool cache = true;
    if (rs == RRC_REQ_BAD_VERSION) {
        simple(&x, "UNSUPPORTED", "protocol version");
    } else if (rs == RRC_REQ_BAD_SHAPE) {
        simple(&x, "BAD_ARG", "op must be a string and args an object");
    } else if (p->bt_pending && !rrc_json_str_eq(&doc, req.op, "STOP")) {
        begin(&x, "BUSY");
        rrc_jw_kstr(&x.w, "reason", "BRAKE_TEST");
        rrc_jw_kstr(&x.w, "state", "RUNNING");
        cache = false;
    } else if (rrc_cache_hit(&p->cache, req.id, crc, json_len)) {
        size_t n = p->cache.reply_len;
        unlock(c);
        (void)c->hal.link_write(c->hal.ctx, p->tx_buf, n);
        return;
    } else {
        const rrc_json_t *d = &doc;
        int op = req.op;
        if (rrc_json_str_eq(d, op, "DRIVE")) {
            op_drive(&x);
        } else if (rrc_json_str_eq(d, op, "TIME")) {
            op_time(&x);
        } else if (rrc_json_str_eq(d, op, "STATE")) {
            for (int level = 0; level < 3; level++) {
                op_state(&x, level);
                if (rrc_jw_ok(&x.w) && rrc_jw_len(&x.w) + 4u <= RRCH_RECORD_MAX - RRC_FRAME_TRAILER_LEN) {
                    break;
                }
            }
        } else if (rrc_json_str_eq(d, op, "DIAG")) {
            op_diag(&x);
        } else if (rrc_json_str_eq(d, op, "EVENTS")) {
            op_events(&x);
        } else if (rrc_json_str_eq(d, op, "HELLO")) {
            op_hello(&x);
        } else if (rrc_json_str_eq(d, op, "STOP")) {
            op_stop(&x);
        } else if (rrc_json_str_eq(d, op, "REARM_SW")) {
            op_rearm(&x);
        } else if (rrc_json_str_eq(d, op, "SET_OP_MODE")) {
            op_set_op_mode(&x);
        } else if (rrc_json_str_eq(d, op, "HEAD_POWER")) {
            op_head_power(&x);
        } else if (rrc_json_str_eq(d, op, "HEATER")) {
            op_heater(&x);
        } else if (rrc_json_str_eq(d, op, "PANEL")) {
            op_panel(&x);
        } else if (rrc_json_str_eq(d, op, "CONFIG_GET")) {
            op_config(&x, false);
        } else if (rrc_json_str_eq(d, op, "CONFIG_SET")) {
            op_config(&x, true);
        } else if (rrc_json_str_eq(d, op, "BRAKE_TEST")) {
            if (!need_session(&x)) {
            } else if (!rrch_brake_test_start(c)) {
                simple(&x, "REJECTED", "NOT_ARMED_IDLE");
            } else { /* deferred reply: sent by rrch_proto_poll when the test has finished */
                p->bt_pending = true;
                p->bt_id = req.id;
                p->bt_crc = crc;
                p->bt_len = json_len;
                unlock(c);
                return;
            }
        } else {
            simple(&x, "UNSUPPORTED", "unknown op");
        }
    }
    send(c, &x, crc, json_len, cache);
    unlock(c);
}

void rrch_proto_init(rrch_t *c)
{
    rrc_frame_rx_init(&c->proto.rx, c->proto.rx_buf, RRCH_RECORD_MAX);
    rrc_cache_clear(&c->proto.cache);
}

void rrch_proto_poll(rrch_t *c)
{
    rrch_proto_t *p = &c->proto;
    uint8_t buf[128];
    size_t n;
    while ((n = c->hal.link_read(c->hal.ctx, buf, sizeof buf)) > 0u) {
        for (size_t i = 0; i < n; i++) {
            size_t json_len = 0;
            uint32_t crc = 0;
            if (rrc_frame_rx_push(&p->rx, buf[i], &json_len, &crc) == RRC_RX_RECORD) {
                handle(c, json_len, crc);
            }
        }
    }
    if (p->bt_pending && c->bt.result_ready) {
        ctx_t x;
        memset(&x, 0, sizeof x);
        x.c = c;
        x.id = p->bt_id;
        lock(c);
        c->bt.result_ready = false;
        p->bt_pending = false;
        bt_body(&x);
        send(c, &x, p->bt_crc, p->bt_len, true);
        unlock(c);
    }
}
