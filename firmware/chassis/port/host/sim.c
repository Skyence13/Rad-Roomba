/* Plant model and HAL of the chassis emulator. SIMULATION ONLY - see sim.h. */
#include <math.h>
#include <string.h>

#include "sim.h"

#define CPR_PER_RAD ((double)RRCH_ENCODER_CPR / 6.283185307179586)
#define SUBSTEPS 10
#define DT (1e-3 / SUBSTEPS)

/* ---- deterministic noise ---- */
static double rnd(sim_t *s) /* uniform -1..1 */
{
    s->rng ^= s->rng << 13;
    s->rng ^= s->rng >> 7;
    s->rng ^= s->rng << 17;
    return (double)(s->rng >> 11) / 4503599627370496.0 - 1.0;
}

/* ---- HAL ---- */
static uint64_t h_now(void *ctx)
{
    return ((sim_t *)ctx)->t_us - ((sim_t *)ctx)->boot_us;
}

static bool chain_inputs_ok(const sim_t *s)
{
    bool loop_ok = s->loop_ohm >= 600.0 && s->loop_ohm <= 1600.0;
    bool lab_n = !(s->pres_ohm >= 900.0 && s->pres_ohm <= 2500.0);
    return s->mode_run && !s->estop && !s->hands_on && !s->chg_cover_open && !s->chg_plug && s->head_docked && loop_ok && lab_n && !s->bumper_l &&
           !s->bumper_r && s->wdg_ok && s->core.out.arm_permit;
}

static void h_read(void *ctx, rrch_in_t *in)
{
    sim_t *s = ctx;
    uint32_t di = 0;
    bool loop_ok = s->loop_ohm >= 600.0 && s->loop_ohm <= 1600.0;
#define SET(n, v) if (v) { di |= RRCH_DI(n); }
    SET(MODE_RUN, s->mode_run)
    SET(ESTOP_A, !s->estop || s->estop_a_stuck)
    SET(ESTOP_B, !s->estop)
    SET(HANDS_ON, !s->hands_on)
    SET(CHG_COVER, !s->chg_cover_open)
    SET(CHG_PLUG_LINK, !s->chg_plug)
    SET(HEAD_DOCK, s->head_docked)
    SET(HEAD_LOOP_OK, loop_ok)
    SET(HEAD_LOOP_SHORT, s->loop_ohm < 600.0)
    SET(LAB_KEY_N, !(s->pres_ohm >= 900.0 && s->pres_ohm <= 2500.0))
    SET(BODY_BUMPER_L, !s->bumper_l)
    SET(BODY_BUMPER_R, !s->bumper_r)
    SET(WDG_OK, s->wdg_ok)
    SET(BRAKE_L, s->relay[0])
    SET(BRAKE_R, s->relay[1])
    SET(HW_LATCH, s->latch)
    SET(J2_PRES, s->j2)
    SET(BTN_REARM, s->rearm_ms > 0)
    SET(BTN_PAUSE, s->pause_ms > 0)
#undef SET
    memset(in, 0, sizeof *in);
    in->di = di;
    in->iox_ok = !s->iox_fail;
    in->adc_ok = true;
    in->pres_ohm = s->pres_ohm > 999999.0 ? 1000000u : (uint32_t)(s->pres_ohm + 2.0 * rnd(s));
    in->loop_ohm = s->loop_ohm > 999999.0 ? 1000000u : (uint32_t)(s->loop_ohm + 2.0 * rnd(s));
    in->vmot_v = (float)(s->vmot + 0.02 * rnd(s));
    in->vbat_v = (float)(s->vbat + 0.02 * rnd(s));
    in->v5_v = (float)(5.10 + 0.01 * rnd(s));
    for (int k = 0; k < 2; k++) {
        bool connected = s->latch && s->relay[k] && s->core.out.bridge_awake;
        in->i_mot_a[k] = (float)(connected ? fabs(s->i[k]) + 0.01 * fabs(rnd(s)) : 0.005 * fabs(rnd(s)));
        in->enc[k] = s->enc_raw[k];
        in->ntc_c[k] = (float)s->temp[k];
    }
    in->ntc_c[2] = (float)s->temp[2];
    in->imu_ok = !s->imu_off;
    double tilt = s->tilt_deg * 0.017453292519943295;
    in->gyro[0] = (float)(0.002 * rnd(s));
    in->gyro[1] = (float)(0.002 * rnd(s));
    in->gyro[2] = (float)(s->wz + 0.002 * rnd(s));
    in->accel[0] = (float)(s->acc + 9.81 * sin(tilt) + 0.03 * rnd(s));
    in->accel[1] = (float)(s->v * s->wz + 0.03 * rnd(s));
    in->accel[2] = (float)(9.81 * cos(tilt) + 0.03 * rnd(s));
}

static void h_write(void *ctx, const rrch_out_t *out)
{
    (void)ctx;
    (void)out; /* the plant reads s->core.out directly */
}

static void h_strobe(void *ctx)
{
    sim_t *s = ctx;
    if (s->last_strobe_us != 0 && s->t_us - s->last_strobe_us < 3000u) {
        s->wdg_ok = false; /* window violation: strobed too early */
    }
    s->last_strobe_us = s->t_us;
    s->n_strobes++;
}

static size_t h_link_read(void *ctx, uint8_t *buf, size_t cap)
{
    sim_t *s = ctx;
    if (s->usb_stall || s->usb_down) {
        return 0;
    }
    size_t n = s->rx_len < cap ? s->rx_len : cap;
    memcpy(buf, s->rx, n);
    memmove(s->rx, s->rx + n, s->rx_len - n);
    s->rx_len -= n;
    return n;
}

static bool h_link_write(void *ctx, const uint8_t *buf, size_t len)
{
    sim_t *s = ctx;
    if (s->usb_down || s->tx_len + len > sizeof s->tx) {
        return false;
    }
    memcpy(s->tx + s->tx_len, buf, len);
    s->tx_len += len;
    return true;
}

static bool h_link_up(void *ctx)
{
    return !((sim_t *)ctx)->usb_down;
}

static bool h_nv_read(void *ctx, int slot, uint8_t *buf, size_t cap, size_t *len)
{
    sim_t *s = ctx;
    if (slot < 0 || slot > 2 || s->nv_len[slot] == 0 || s->nv_len[slot] > cap) {
        return false;
    }
    memcpy(buf, s->nv[slot], s->nv_len[slot]);
    *len = s->nv_len[slot];
    return true;
}

static bool h_nv_write(void *ctx, int slot, const uint8_t *buf, size_t len)
{
    sim_t *s = ctx;
    if (slot < 0 || slot > 2 || len > RRCH_NV_MAX || s->nv_fail) {
        return false;
    }
    memcpy(s->nv[slot], buf, len);
    s->nv_len[slot] = len;
    return true;
}

static void *h_retained(void *ctx, size_t size)
{
    return size <= sizeof(rrch_retained_t) ? &((sim_t *)ctx)->retained : NULL;
}

static bool h_entropy(void *ctx, uint8_t *buf, size_t len)
{
    sim_t *s = ctx;
    for (size_t k = 0; k < len; k++) {
        buf[k] = (uint8_t)(rnd(s) * 127.0 + 128.0);
    }
    return true;
}

static rrch_reset_cause_t h_reset_cause(void *ctx)
{
    return ((sim_t *)ctx)->reset_cause;
}

static void core_boot(sim_t *s)
{
    rrch_hal_t hal = {s, h_now, h_read, h_write, h_strobe, h_link_read, h_link_write, h_link_up, h_nv_read, h_nv_write, h_retained, h_entropy, h_reset_cause, NULL, NULL};
    rrch_init(&s->core, &hal);
}

void sim_mcu_reset(sim_t *s, rrch_reset_cause_t cause)
{
    s->reset_cause = cause;
    if (cause == RRCH_RST_POWER_ON) {
        memset(&s->retained, 0, sizeof s->retained);
    }
    s->rx_len = 0; /* CDC endpoint is re-enumerated */
    s->n_resets++;
    s->wdg_ok = true;
    s->last_strobe_us = 0;
    s->wdg_arm_us = s->t_us + 300000u;
    s->wdg_reset_ms = 0;
    s->boot_us = s->t_us; /* the chassis clock restarts at 0 */
    core_boot(s);
}

void sim_init(sim_t *s, uint64_t seed)
{
    memset(s, 0, sizeof *s);
    s->rng = seed * 2654435761u + 0x9E3779B97F4A7C15ull;
    s->p = (sim_params_t){.R = 2.2, .L = 2.3e-3, .Ke = 1.65, .Kt = 1.0, .J = 0.012, .mass = 12.0, .Iz = 0.25, .r = 0.052, .track = 0.220, .tau_c = 0.25, .b_visc = 0.02, .R_brake = 4.7};
    s->mode_run = true;
    s->head_docked = true;
    s->j2 = true;
    s->pres_ohm = 4700.0;
    s->loop_ohm = 1000.0;
    s->vbat = 13.0;
    s->soc = 80.0;
    s->temp[0] = s->temp[1] = 20.0;
    s->temp[2] = 25.0;
    for (int k = 0; k < RRCH_TOF_N; k++) {
        s->tof_mm[k] = k < 4 ? 30 : 150;
        s->tof_st[k] = k < 8 ? RRCH_TOF_ST_OK : RRCH_TOF_ST_NO_TARGET;
    }
    s->wdg_ok = true;
    s->wdg_arm_us = 300000u;
    s->reset_cause = RRCH_RST_POWER_ON;
    core_boot(s);
}

/* ---- plant ---- */
static void plant_ms(sim_t *s)
{
    const sim_params_t *p = &s->p;
    const rrch_out_t *o = &s->core.out;

    /* hardwired chain, latch relay, brake relays (work without the firmware) */
    bool ok = chain_inputs_ok(s);
    if (s->latch) {
        if (!ok && !s->latch_weld) {
            if (++s->latch_drop_ms >= 5) {
                s->latch = false;
            }
        } else {
            s->latch_drop_ms = 0;
        }
        s->latch_set_ms = 0;
    } else {
        if (ok && s->rearm_ms > 0) {
            if (++s->latch_set_ms >= 10) {
                s->latch = true;
                s->latch_drop_ms = 0;
            }
        } else {
            s->latch_set_ms = 0;
        }
    }
    for (int k = 0; k < 2; k++) {
        if (s->relay[k] != s->latch) {
            if (++s->relay_ms[k] >= 8) {
                s->relay[k] = s->latch;
            }
        } else {
            s->relay_ms[k] = 0;
        }
    }
    if (s->rearm_ms > 0) {
        s->rearm_ms--;
    }
    if (s->pause_ms > 0) {
        s->pause_ms--;
    }

    double A = p->J + p->r * p->r * (p->mass / 4.0 + p->Iz / (p->track * p->track));
    double B = p->r * p->r * (p->mass / 4.0 - p->Iz / (p->track * p->track));
    double det = A * A - B * B;
    double grav = -p->mass * 9.81 * sin(s->tilt_deg * 0.017453292519943295) * p->r / 2.0;
    double v0 = s->v;
    for (int n = 0; n < SUBSTEPS; n++) {
        s->vmot += (s->latch ? (s->vbat - s->vmot) / 0.005 : -s->vmot / 0.040) * DT;
        double tau[2];
        for (int k = 0; k < 2; k++) {
            double di;
            if (s->latch && s->relay[k]) {
                if (o->bridge_awake) {
                    double d = o->duty[k] > 1.0f ? 1.0 : (o->duty[k] < -1.0f ? -1.0 : (double)o->duty[k]);
                    di = (d * s->vmot - p->R * s->i[k] - p->Ke * s->w[k]) / p->L;
                } else {
                    di = -s->i[k] / 2e-4; /* bridge asleep: outputs high-Z, current dies */
                }
            } else if (!s->relay[k]) {
                di = (-(p->R + p->R_brake) * s->i[k] - p->Ke * s->w[k]) / p->L; /* across the brake resistor */
            } else {
                di = -s->i[k] / 2e-4;
            }
            s->i[k] += di * DT;
            double sat = s->w[k] / 0.02;
            sat = sat > 1.0 ? 1.0 : (sat < -1.0 ? -1.0 : sat);
            tau[k] = p->Kt * s->i[k] - p->tau_c * sat - p->b_visc * s->w[k] + grav;
        }
        double al = (A * tau[0] - B * tau[1]) / det, ar = (A * tau[1] - B * tau[0]) / det;
        s->w[0] += al * DT;
        s->w[1] += ar * DT;
        for (int k = 0; k < 2; k++) {
            if (s->block[k]) {
                s->w[k] = 0.0;
            }
            s->th[k] += s->w[k] * DT;
        }
        double vl = s->w[0] * p->r * (1.0 - s->slip[0]), vr = s->w[1] * p->r * (1.0 - s->slip[1]);
        s->v = 0.5 * (vl + vr);
        s->wz = (vr - vl) / p->track;
        s->x += s->v * cos(s->yaw) * DT;
        s->y += s->v * sin(s->yaw) * DT;
        s->yaw += s->wz * DT;
    }
    s->acc = (s->v - v0) / 1e-3;
    for (int k = 0; k < 2; k++) { /* encoder: quantised wheel angle, 16-bit counter */
        if (!s->enc_dropout[k]) {
            s->enc_frozen[k] = s->th[k];
        }
        s->enc_raw[k] = (uint16_t)(int64_t)floor(s->enc_frozen[k] * CPR_PER_RAD);
    }

    /* external window watchdog */
    if (s->wdg_ok && s->t_us > s->wdg_arm_us && s->t_us - s->last_strobe_us > 35000u) {
        s->wdg_ok = false;
    }
    if (!s->wdg_ok && ++s->wdg_reset_ms >= 50) {
        sim_mcu_reset(s, RRCH_RST_WATCHDOG); /* WDO also pulls NRST */
    }
}

void sim_step_ms(sim_t *s)
{
    s->t_us += 1000u;
    plant_ms(s);
    uint32_t ms = (uint32_t)(s->t_us / 1000u);
    /* background sensor drivers: each ToF delivers a sample every 20 ms, staggered */
    for (int k = 0; k < RRCH_TOF_N; k++) {
        if ((ms + (uint32_t)k * 2u) % 20u == 0u && !s->tof_stale[k]) {
            int32_t r = s->tof_mm[k] + (int32_t)lround(rnd(s));
            rrch_tof_update(&s->core, k, r, s->tof_st[k], s->t_us - s->boot_us);
        }
    }
    if (ms % 100u == 0u) {
        rrch_power_t pw = {0};
        pw.pmon_ok = pw.charger_ok = pw.tof_bus_ok = true;
        pw.ibat_a = (float)(0.9 + fabs(s->i[0]) + fabs(s->i[1]) + (s->core.out.head_pwr_en ? 0.4 : 0.0) + (s->core.out.chs_htr_on ? 2.0 : 0.0));
        pw.soc_pct = (float)s->soc;
        pw.chg_temp_c = (float)s->temp[1];
        pw.charge_state = s->chg_plug ? RRCH_CHG_CC : RRCH_CHG_NONE;
        pw.i_head_a = s->core.out.head_pwr_en ? 0.4f : 0.0f;
        pw.i_head_htr_a = s->core.out.head_htr_en ? 1.2f : 0.0f;
        pw.i_chs_htr_a = s->core.out.chs_htr_on ? 2.0f : 0.0f;
        pw.efuse_fault = s->efuse_fault;
        rrch_power_update(&s->core, &pw);
    }
    if (!s->freeze_control) {
        rrch_tick_1khz(&s->core);
    }
    if (ms % 10u == 0u && !s->freeze_supervisor) {
        rrch_supervise_100hz(&s->core);
    }
    if (!s->freeze_background) {
        rrch_background(&s->core);
    }
}

void sim_host_write(sim_t *s, const uint8_t *buf, size_t len)
{
    if (s->rx_len + len <= sizeof s->rx) {
        memcpy(s->rx + s->rx_len, buf, len);
        s->rx_len += len;
    }
}

size_t sim_host_read(sim_t *s, uint8_t *buf, size_t cap)
{
    size_t n = s->tx_len < cap ? s->tx_len : cap;
    memcpy(buf, s->tx, n);
    memmove(s->tx, s->tx + n, s->tx_len - n);
    s->tx_len -= n;
    return n;
}

/* ---- environment JSON ---- */
static bool num(const rrc_json_t *d, int tok, double *out)
{
    size_t n;
    if (rrc_json_type(d, tok) != RRC_JT_NUMBER) {
        return false;
    }
    const char *t = rrc_json_raw(d, tok, &n);
    char tmp[40];
    if (n >= sizeof tmp) {
        return false;
    }
    memcpy(tmp, t, n);
    tmp[n] = 0;
    double v = 0, sc = 1;
    int k = 0, neg = 0;
    if (tmp[k] == '-') {
        neg = 1;
        k++;
    }
    for (; tmp[k] >= '0' && tmp[k] <= '9'; k++) {
        v = v * 10 + (tmp[k] - '0');
    }
    if (tmp[k] == '.') {
        for (k++; tmp[k] >= '0' && tmp[k] <= '9'; k++) {
            sc *= 0.1;
            v += (tmp[k] - '0') * sc;
        }
    }
    if (tmp[k] == 'e' || tmp[k] == 'E') {
        int e = 0, en = 0;
        k++;
        if (tmp[k] == '-' || tmp[k] == '+') {
            en = tmp[k] == '-';
            k++;
        }
        for (; tmp[k] >= '0' && tmp[k] <= '9'; k++) {
            e = e * 10 + (tmp[k] - '0');
        }
        v *= pow(10.0, en ? -e : e);
    }
    *out = neg ? -v : v;
    return true;
}

static int tof_index(const rrc_json_t *d, int tok)
{
    for (int k = 0; k < RRCH_TOF_N; k++) {
        if (rrc_json_str_eq(d, tok, rrch_tof_names[k])) {
            return k;
        }
    }
    return -1;
}

bool sim_env_apply(sim_t *s, const char *json, size_t len)
{
    rrc_jtok_t tok[160];
    rrc_json_t d;
    static const rrc_json_limits_t lim = {4, 64};
    if (rrc_json_parse(&d, json, len, tok, 160, &lim) != RRC_JSON_OK || rrc_json_type(&d, 0) != RRC_JT_OBJECT) {
        return false;
    }
    int t;
    double v;
    bool b;
#define B(name, field) if ((t = rrc_json_get(&d, 0, name)) >= 0 && rrc_json_to_bool(&d, t, &b)) { s->field = b; }
#define N(name, field) if ((t = rrc_json_get(&d, 0, name)) >= 0 && num(&d, t, &v)) { s->field = v; }
    B("mode_run", mode_run) B("estop", estop) B("hands_on", hands_on) B("chg_cover_open", chg_cover_open) B("chg_plug", chg_plug)
    B("head_docked", head_docked) B("bumper_l", bumper_l) B("bumper_r", bumper_r) B("j2", j2)
    B("usb_stall", usb_stall) B("usb_down", usb_down) B("imu_off", imu_off) B("iox_fail", iox_fail) B("latch_weld", latch_weld)
    B("estop_a_stuck", estop_a_stuck) B("freeze_control", freeze_control) B("freeze_supervisor", freeze_supervisor)
    B("freeze_background", freeze_background) B("nv_fail", nv_fail)
    N("pres_ohm", pres_ohm) N("loop_ohm", loop_ohm) N("vbat", vbat) N("soc", soc) N("temp_bay", temp[0]) N("temp_pack", temp[1])
    N("temp_board", temp[2]) N("tilt_deg", tilt_deg)
#undef B
#undef N
    if ((t = rrc_json_get(&d, 0, "efuse_fault")) >= 0 && num(&d, t, &v)) {
        s->efuse_fault = (uint8_t)v;
    }
    if ((t = rrc_json_get(&d, 0, "tof")) >= 0 && rrc_json_type(&d, t) == RRC_JT_OBJECT) {
        for (int k = 0; k < RRCH_TOF_N; k++) { /* {"CLIFF_FL": 31} | null = NO_TARGET | "INVALID" */
            int e = rrc_json_get(&d, t, rrch_tof_names[k]);
            if (e < 0) {
                continue;
            }
            if (num(&d, e, &v)) {
                s->tof_mm[k] = (int32_t)v;
                s->tof_st[k] = RRCH_TOF_ST_OK;
            } else if (rrc_json_is_null(&d, e)) {
                s->tof_st[k] = RRCH_TOF_ST_NO_TARGET;
            } else {
                s->tof_st[k] = RRCH_TOF_ST_INVALID;
            }
        }
    }
    if ((t = rrc_json_get(&d, 0, "tof_stale")) >= 0 && rrc_json_type(&d, t) == RRC_JT_ARRAY) {
        memset(s->tof_stale, 0, sizeof s->tof_stale); /* the list replaces the previous one */
        for (uint16_t k = 0; k < rrc_json_size(&d, t); k++) {
            int e = rrc_json_at(&d, t, k);
            int idx = tof_index(&d, e);
            if (idx >= 0) {
                s->tof_stale[idx] = true;
            } else if (rrc_json_str_eq(&d, e, "ALL")) {
                memset(s->tof_stale, 1, sizeof s->tof_stale);
            }
        }
    }
    static const char *const lr[2] = {"enc_dropout", "block"};
    for (int f = 0; f < 2; f++) { /* "L" | "R" | "BOTH" | "NONE" */
        if ((t = rrc_json_get(&d, 0, lr[f])) >= 0) {
            bool l = rrc_json_str_eq(&d, t, "L") || rrc_json_str_eq(&d, t, "BOTH"), r = rrc_json_str_eq(&d, t, "R") || rrc_json_str_eq(&d, t, "BOTH");
            bool *dst = f == 0 ? s->enc_dropout : s->block;
            dst[0] = l;
            dst[1] = r;
        }
    }
    if ((t = rrc_json_get(&d, 0, "slip")) >= 0 && rrc_json_type(&d, t) == RRC_JT_ARRAY && rrc_json_size(&d, t) == 2) {
        for (uint16_t k = 0; k < 2; k++) {
            if (num(&d, rrc_json_at(&d, t, k), &v) && v >= 0.0 && v < 0.95) {
                s->slip[k] = v;
            }
        }
    }
    if ((t = rrc_json_get(&d, 0, "pose")) >= 0 && rrc_json_type(&d, t) == RRC_JT_ARRAY && rrc_json_size(&d, t) == 3) {
        double q[3];
        if (num(&d, rrc_json_at(&d, t, 0), &q[0]) && num(&d, rrc_json_at(&d, t, 1), &q[1]) && num(&d, rrc_json_at(&d, t, 2), &q[2])) {
            s->x = q[0];
            s->y = q[1];
            s->yaw = q[2];
        }
    }
    if ((t = rrc_json_get(&d, 0, "press")) >= 0) {
        double ms = 200;
        int tm = rrc_json_get(&d, 0, "press_ms");
        if (tm >= 0) {
            (void)num(&d, tm, &ms);
        }
        if (rrc_json_str_eq(&d, t, "REARM")) {
            s->rearm_ms = (int)ms;
        } else if (rrc_json_str_eq(&d, t, "PAUSE")) {
            s->pause_ms = (int)ms;
        }
    }
    if ((t = rrc_json_get(&d, 0, "mcu_reset")) >= 0) {
        static const char *const names[5] = {"POWER_ON", "BROWNOUT", "PIN", "WATCHDOG", "SOFTWARE"};
        rrch_reset_cause_t cause = RRCH_RST_PIN;
        for (int k = 0; k < 5; k++) {
            if (rrc_json_str_eq(&d, t, names[k])) {
                cause = (rrch_reset_cause_t)k;
            }
        }
        sim_mcu_reset(s, cause);
    }
    return true;
}

size_t sim_truth_json(const sim_t *s, char *buf, size_t cap)
{
    rrc_jw_t w;
    rrc_jw_init(&w, buf, cap);
    rrc_jw_obj_begin(&w);
    rrc_jw_kstr(&w, "type", "TRUTH");
    rrc_jw_ku64(&w, "t_us", s->t_us);
    rrc_jw_ku64(&w, "chassis_us", s->t_us - s->boot_us);
    rrc_jw_kfixed(&w, "x", (int64_t)llround(s->x * 1e6), 6, true);
    rrc_jw_kfixed(&w, "y", (int64_t)llround(s->y * 1e6), 6, true);
    rrc_jw_kfixed(&w, "yaw", (int64_t)llround(s->yaw * 1e6), 6, true);
    rrc_jw_kfixed(&w, "v", (int64_t)llround(s->v * 1e5), 5, true);
    rrc_jw_kfixed(&w, "w", (int64_t)llround(s->wz * 1e5), 5, true);
    rrc_jw_kfixed(&w, "wheel_l_rad", (int64_t)llround(s->th[0] * 1e5), 5, true);
    rrc_jw_kfixed(&w, "wheel_r_rad", (int64_t)llround(s->th[1] * 1e5), 5, true);
    rrc_jw_key(&w, "i_a");
    rrc_jw_arr_begin(&w);
    rrc_jw_fixed(&w, (int64_t)llround(s->i[0] * 1e3), 3, true);
    rrc_jw_fixed(&w, (int64_t)llround(s->i[1] * 1e3), 3, true);
    rrc_jw_arr_end(&w);
    rrc_jw_kfixed(&w, "vmot", (int64_t)llround(s->vmot * 1e2), 2, true);
    rrc_jw_kbool(&w, "latch", s->latch);
    rrc_jw_kbool(&w, "arm_permit", s->core.out.arm_permit);
    rrc_jw_kbool(&w, "wdg_ok", s->wdg_ok);
    rrc_jw_kbool(&w, "bridge_awake", s->core.out.bridge_awake);
    rrc_jw_kbool(&w, "buzzer", s->core.out.buzzer);
    rrc_jw_ki64(&w, "leds", s->core.out.leds);
    rrc_jw_kbool(&w, "head_pwr", s->core.out.head_pwr_en);
    rrc_jw_kbool(&w, "head_htr", s->core.out.head_htr_en);
    rrc_jw_kbool(&w, "chs_htr", s->core.out.chs_htr_on);
    rrc_jw_kstr(&w, "mode", rrch_mode_names[s->core.mode]);
    rrc_jw_kstr(&w, "boot_id", s->core.boot_id);
    rrc_jw_ku64(&w, "mcu_resets", s->n_resets);
    rrc_jw_obj_end(&w);
    return rrc_jw_ok(&w) ? rrc_jw_len(&w) : 0u;
}
