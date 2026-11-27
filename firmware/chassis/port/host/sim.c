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

/* Chain node voltages (live/dead) from the element states. A node shorted to a live conductor
 * (fault injection) is live whatever its upstream. */
static void chain_nodes(sim_t *s)
{
    bool loop_ok = s->loop_ohm >= 600.0 && s->loop_ohm <= 1600.0;
    bool lab_n = !(s->pres_ohm >= 900.0 && s->pres_ohm <= 2500.0);
    bool e[SIM_NODES] = {false};
    e[SIM_N1] = s->mode_run;
    e[SIM_N2] = !s->estop || s->estop_a_stuck;
    e[SIM_N3] = !s->hands_on;
    e[SIM_N4A] = !s->chg_cover_open;
    e[SIM_N4] = !s->chg_plug;
    e[SIM_N5] = s->head_docked;
    e[SIM_N6] = loop_ok;
    e[SIM_N7] = lab_n;
    e[SIM_N8A] = !s->bumper_l;
    e[SIM_N8] = !s->bumper_r;
    e[SIM_N9] = s->wdg_ok;
    e[SIM_NEND] = (s->core.out.arm_permit || s->permit_short) && !s->permit_open;
    bool up = true; /* CH_N0: VBAT_SW through the chain PTC */
    for (int k = SIM_N1; k < SIM_NODES; k++) {
        up = (up && e[k]) || s->chain_short == k;
        s->node[k] = up;
    }
    s->pole_b = !s->estop;
}

static void h_read(void *ctx, rrch_in_t *in)
{
    sim_t *s = ctx;
    uint32_t di = 0;
    chain_nodes(s);
    bool loop_ok = s->loop_ohm >= 600.0 && s->loop_ohm <= 1600.0;
    /* BRAKE_x_RB: OR over both poles, valid only with the bridges asleep; during PWM / braking the
     * bridge outputs toggle and the comparators read garbage (CCR-E03 e) */
    bool asleep = !(s->core.out.bridge_awake && s->latch);
#define SET(n, v) if (v) { di |= RRCH_DI(n); }
    SET(MODE_RUN, s->node[SIM_N1])
    SET(ESTOP_A, s->node[SIM_N2])
    SET(ESTOP_B, s->pole_b)
    SET(HANDS_ON, s->node[SIM_N3])
    SET(CHG_COVER, s->node[SIM_N4A])
    SET(CHG_PLUG_LINK, s->node[SIM_N4])
    SET(HEAD_DOCK, s->node[SIM_N5])
    SET(HEAD_LOOP_OK, loop_ok)
    SET(HEAD_LOOP_SHORT, s->loop_ohm < 600.0)
    SET(LAB_KEY_N, !(s->pres_ohm >= 900.0 && s->pres_ohm <= 2500.0))
    SET(BODY_BUMPER_L, s->node[SIM_N8A])
    SET(BODY_BUMPER_R, s->node[SIM_N8])
    SET(WDG_OK, s->node[SIM_N9])
    SET(BRAKE_L, asleep ? s->rstate[0] == 1 : rnd(s) > 0.0)
    SET(BRAKE_R, asleep ? s->rstate[1] == 1 : rnd(s) > 0.0)
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
        double ia = connected ? fabs(s->i[k]) + 0.01 * fabs(rnd(s)) : 0.005 * fabs(rnd(s));
        in->i_mot_a[k] = (float)(ia > s->p.ipropi_fs_a ? s->p.ipropi_fs_a : ia); /* IPROPI saturates at VREF+ */
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

/* IB-03 / IB-24: plant constants from electronics/analysis/chassis_braking.py (Pololu #2828 37D 150:1,
 * 104 mm wheel, 12 kg). Ground-referred values there are converted to the wheel shaft with r = 0.052 m:
 *   R      = 12 V / 5.5 A = 2.18 ohm                         R_M
 *   Ke     = 31.7 V per m/s x r = 1.648 V s/rad              KE
 *   Kt     nominal = power-balance constant = Ke             KF_IDEAL (31.7 N/A)
 *          conservative = catalogue stall constant 17.4 N/A  KF_DRIVE
 *   J      rotor 1e-6 (nominal) / 2e-6 (conservative) kg m2 x 150^2 = 8.3 / 16.6 kg reflected per motor
 *   friction 3.5 N rolling + 2 x 0.2 A x 31.7 = 16.2 N total (nominal); none (conservative)
 *   brake loop R + 1.0 ohm resistor + 0.04 ohm contacts/leads = 3.22 ohm
 * Inductance 2.3 mH is an assumption of this emulator (circuit_description.md assumes 2.5 mH). */
static void params_common(sim_params_t *p)
{
    const double r = 0.052, v_nl = 67.0 / 60.0 * 2.0 * 3.141592653589793 * r;
    p->r = r;
    p->R = 12.0 / 5.5;
    p->Ke = (12.0 - 0.2 * p->R) / v_nl * r;
    p->L = 2.3e-3;
    p->mass = 12.0;
    p->Iz = 0.30;
    p->track = 0.270; /* Rev E body (contract frames.wheel) */
    p->R_brake = 1.0;
    p->R_path = 0.04;
    p->b_visc = 0.0;
    p->i_trip = 2.68;
    p->ipropi_fs_a = 3.000 / 1.1205;
}

void sim_params_nominal(sim_params_t *p)
{
    params_common(p);
    p->Kt = p->Ke;
    p->J = 1.0e-6 * 150.0 * 150.0;
    p->tau_c = (3.5 + 2.0 * 0.2 * p->Ke / p->r) * 0.5 * p->r;
}

void sim_params_conservative(sim_params_t *p)
{
    params_common(p);
    p->Kt = 49.0 * 9.80665 / 100.0 / (5.5 - 0.2);
    p->J = 2.0e-6 * 150.0 * 150.0;
    p->tau_c = 0.0;
}

void sim_init(sim_t *s, uint64_t seed)
{
    memset(s, 0, sizeof *s);
    s->rng = seed * 2654435761u + 0x9E3779B97F4A7C15ull;
    sim_params_nominal(&s->p);
    s->mode_run = true;
    s->head_docked = true;
    s->j2 = true;
    s->pres_ohm = 4700.0;
    s->loop_ohm = 1000.0;
    s->vbat = 13.0;
    s->soc = 80.0;
    s->temp[0] = s->temp[1] = 20.0;
    s->temp[2] = 25.0;
    for (int k = 0; k < RRCH_TOF_N; k++) { /* nominal floor ranges (defaults of look.* / cliff from frames.yaml) */
        s->tof_mm[k] = k < 4 ? 30 : 150;
        s->tof_st[k] = k < 8 ? RRCH_TOF_ST_OK : RRCH_TOF_ST_NO_TARGET;
    }
    s->tof_mm[RRCH_TOF_LOOK_FL] = s->tof_mm[RRCH_TOF_LOOK_FR] = 524;
    s->tof_mm[RRCH_TOF_LOOK_RL] = s->tof_mm[RRCH_TOF_LOOK_RR] = 267;
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

    /* hardwired chain, latch relay, brake relays (work without the firmware). Timing from
     * chassis_braking_tables.md T2: K1 releases 4 ms after its coil supply goes [U]; the brake relay
     * coils are fed from CHAIN_END through K1 pole B and lose supply at once; their NO contacts open
     * at 7.5 ms and the NC contacts close on the brake resistor at 10.5 ms; VMOT eFuse off and bridges
     * asleep 1 ms after K1 (RUN_12V). Pick-up: K1 10 ms of REARM, relays 8 ms. */
    chain_nodes(s);
    bool ok = s->node[SIM_NEND] && s->pole_b;
    if (!s->latch) {
        if (ok && s->rearm_ms > 0) {
            if (++s->latch_set_ms >= 10) {
                s->latch = true;
                s->k1_off_s = 0;
            }
        } else {
            s->latch_set_ms = 0;
        }
    } else {
        s->latch_set_ms = 0;
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
        /* K1 and brake relays at 0.1 ms resolution */
        bool coil = ok && s->latch; /* K2/K3 coils: CHAIN_END -> K1 pole B -> RUN_12V, return through E-stop pole B */
        if (s->latch && !ok && !s->latch_weld) {
            s->k1_off_s += DT;
            if (s->k1_off_s >= 4.0e-3 - 1e-9) {
                s->latch = false;
            }
        } else {
            s->k1_off_s = 0;
        }
        for (int k = 0; k < 2; k++) {
            if (coil) {
                if (s->rstate[k] != 1) {
                    s->relay_t_s[k] += DT;
                    if (s->relay_t_s[k] >= 8.0e-3 - 1e-9) {
                        s->rstate[k] = 1;
                        s->relay_t_s[k] = 0;
                    }
                } else {
                    s->relay_t_s[k] = 0;
                }
            } else if (s->rstate[k] != 0) {
                s->relay_t_s[k] += DT;
                if (s->relay_t_s[k] >= 10.5e-3 - 1e-9) {
                    s->rstate[k] = 0;
                    s->relay_t_s[k] = 0;
                } else if (s->relay_t_s[k] >= 7.5e-3 - 1e-9) {
                    s->rstate[k] = 2;
                }
            } else {
                s->relay_t_s[k] = 0;
            }
            s->relay[k] = s->rstate[k] == 1;
        }
        /* VMOT: eFuse on with RUN_12V (soft start ~5 ms); off: 1 kOhm bleed on 810 uF (tau 0.81 s) */
        s->vmot += (s->latch ? (s->vbat - s->vmot) / 0.005 : -s->vmot / 0.81) * DT;
        bool awake = s->latch && o->bridge_awake; /* U9: nSLEEP = DRV_NSLEEP AND RUN_12V */
        double tau[2];
        for (int k = 0; k < 2; k++) {
            double di;
            if (s->rstate[k] == 1) {
                if (awake) {
                    double d = o->duty[k] > 1.0f ? 1.0 : (o->duty[k] < -1.0f ? -1.0 : (double)o->duty[k]);
                    /* hardware current chop (DRV8874 ITRIP from VREF+ and RIPROPI, 2.68 A): slow decay
                     * while the current is at the trip level and the drive would raise it */
                    if (fabs(s->i[k]) >= p->i_trip && d * s->vmot * s->i[k] > 0.0) {
                        d = 0.0;
                    }
                    di = (d * s->vmot - p->R * s->i[k] - p->Ke * s->w[k]) / p->L;
                } else {
                    di = -s->i[k] / 2e-4; /* bridge asleep: outputs high-Z, back-EMF below VMOT, current dies */
                }
            } else if (s->rstate[k] == 0) {
                di = (-(p->R + p->R_brake + p->R_path) * s->i[k] - p->Ke * s->w[k]) / p->L; /* across the brake resistor */
            } else {
                di = -s->i[k] / 2e-4; /* both contacts open */
            }
            s->i[k] += di * DT;
            if (s->rstate[k] == 1 && awake && fabs(s->i[k]) > p->i_trip) {
                s->i[k] = s->i[k] > 0.0 ? p->i_trip : -p->i_trip; /* chop: the trip level is not exceeded */
            }
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
    if (s->plant_only) {
        return;
    }
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
    if (s->plant_only) {
        return;
    }
    if (ms % 10u == 0u) { /* IOX_B input P17 = CHAIN_END_RB, read over I2C by the background loop */
        chain_nodes(s);
        rrch_iox_b_update(&s->core, !s->iox_b_fail, s->node[SIM_NEND], s->t_us - s->boot_us);
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
        pw.chg_input = s->chg_plug; /* a fitted plug carries the 24 V inlet in this model */
        pw.vbat_pmon_v = (float)s->vbat;
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
    B("freeze_background", freeze_background) B("nv_fail", nv_fail) B("iox_b_fail", iox_b_fail) B("permit_short", permit_short) B("permit_open", permit_open)
    N("pres_ohm", pres_ohm) N("loop_ohm", loop_ohm) N("vbat", vbat) N("soc", soc) N("temp_bay", temp[0]) N("temp_pack", temp[1])
    N("temp_board", temp[2]) N("tilt_deg", tilt_deg)
#undef B
#undef N
    if ((t = rrc_json_get(&d, 0, "chain_short")) >= 0) { /* "CH_N1".."CH_N9", "CH_N4A", "CH_N8A", "CHAIN_END", "NONE" */
        static const char *const nn[SIM_NODES] = {"NONE", "CH_N1", "CH_N2", "CH_N3", "CH_N4A", "CH_N4", "CH_N5", "CH_N6", "CH_N7", "CH_N8A", "CH_N8", "CH_N9", "CHAIN_END"};
        s->chain_short = 0;
        for (int k = 1; k < SIM_NODES; k++) {
            if (rrc_json_str_eq(&d, t, nn[k])) {
                s->chain_short = k;
            }
        }
    }
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
