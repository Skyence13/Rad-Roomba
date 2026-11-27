/* Core glue: init, 1 kHz control tick, 100 Hz supervision (watchdog strobe), mode state machine,
 * software protective-stop latch, hold, re-arm, IMU/tilt, battery, heater, head power, panel,
 * stationary brake test, event log. */
#include <math.h>
#include <string.h>

#include "rrch.h"

#define RETAINED_MAGIC 0x52524348u
#define FLOW_ALL 0x7u

static bool timer_run(uint16_t *t, bool cond, uint16_t limit_ms)
{
    if (!cond) {
        *t = 0;
        return false;
    }
    if (*t < limit_ms) {
        (*t)++;
    }
    return *t >= limit_ms;
}

uint32_t rrch_rand(rrch_t *c)
{
    uint32_t x = c->rng;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    c->rng = x ? x : 0x1234567u;
    return c->rng;
}

static void new_nonce(rrch_t *c)
{
    uint32_t n = rrch_rand(c);
    c->rearm_nonce = n ? n : 1u;
}

/* ------------------------------------------------------------------ events and faults */
rrch_event_t *rrch_event(rrch_t *c, rrch_ev_kind_t kind, int32_t a, int32_t b, int32_t d)
{
    c->ev_newest++;
    rrch_event_t *e = &c->ev[(c->ev_newest - 1u) % RRCH_EVENTS_N];
    memset(e, 0, sizeof *e);
    e->seq = c->ev_newest;
    e->t_us = c->now_us;
    e->kind = (uint8_t)kind;
    e->a = a;
    e->b = b;
    e->c = d;
    return e;
}

void rrch_fault_set(rrch_t *c, uint64_t bit, bool on)
{
    bool was = (c->faults & bit) != 0;
    if (was == on || (!on && (bit & RRCH_FLT_FATAL_MASK))) {
        return; /* fatal flags are never cleared before a reset */
    }
    c->faults = on ? (c->faults | bit) : (c->faults & ~bit);
    for (int i = 0; i < RRCH_FLT_N; i++) {
        if (bit == (1ull << i)) {
            rrch_event(c, RRCH_EV_FAULT, i, on, 0);
        }
    }
}

static void beep(rrch_t *c, uint32_t n, uint32_t on_ms)
{
    c->beep_count = n;
    c->beep_on_ms = on_ms;
    c->beep_ms_left = on_ms;
    c->beep_gap = 0;
}

/* ------------------------------------------------------------------ software stop, hold, re-arm */
void rrch_pstop(rrch_t *c, uint32_t bits)
{
    uint32_t fresh = bits & ~c->sw_latched;
    if (!fresh) {
        return;
    }
    c->sw_latched |= fresh;
    new_nonce(c);
    for (int i = 0; i < RRCH_SW_N; i++) {
        if (fresh & (1u << i)) {
            rrch_event(c, RRCH_EV_PSTOP, i, 0, 0)->f = c->drive.v_meas;
        }
    }
    beep(c, 3, 120);
    rrch_drive_stop(c, CFG(c, DRV_PSTOP_DECEL), false);
}

void rrch_hold(rrch_t *c, uint32_t why)
{
    if ((c->hold & why) == why) {
        return;
    }
    c->hold |= why;
    new_nonce(c);
    rrch_event(c, RRCH_EV_HOLD, 1, (int32_t)why, 0);
    beep(c, 1, 150);
    rrch_drive_stop(c, CFG(c, DRV_DECEL), false);
}

#define RETREAT_MASK (RRCH_SW(CLIFF_FL) | RRCH_SW(CLIFF_FR) | RRCH_SW(CLIFF_RL) | RRCH_SW(CLIFF_RR) | RRCH_SW(LOOKAHEAD_L) | RRCH_SW(LOOKAHEAD_R) | RRCH_SW(FIELD_REAR) | RRCH_SW(TOF_STALE) | RRCH_SW(TOF_DISAGREE))

uint32_t rrch_rearm_sw(rrch_t *c, bool by_local, const char *op, uint32_t *blocked, uint32_t *hold_cleared)
{
    uint32_t active = c->sw_active & c->sw_latched;
    *blocked = 0;
    *hold_cleared = 0;
    if (CFG(c, SAFE_ALLOW_RETREAT) >= 0.5f) {
        c->sw_acked |= active & RETREAT_MASK;
        active &= ~RETREAT_MASK;
    }
    if (active) {
        *blocked = active;
        rrch_event_t *e = rrch_event(c, RRCH_EV_REARM_REJECT, 0, (int32_t)active, by_local);
        rrch_str16(e->s, op);
        new_nonce(c);
        return 0;
    }
    uint32_t cleared = c->sw_latched;
    *hold_cleared = c->hold;
    if (cleared) {
        rrch_event_t *e = rrch_event(c, RRCH_EV_PSTOP_CLEAR, by_local, (int32_t)cleared, 0);
        rrch_str16(e->s, op);
    }
    if (c->hold) {
        rrch_event_t *e = rrch_event(c, RRCH_EV_HOLD, 0, (int32_t)c->hold, 0);
        rrch_str16(e->s, op);
    }
    c->sw_latched = 0;
    c->hold = 0;
    if (cleared || *hold_cleared || !by_local) {
        new_nonce(c);
    }
    return cleared;
}

void rrch_set_head_power(rrch_t *c, bool el, bool htr, int why)
{
    if (el == c->head_pwr && htr == c->head_htr) {
        return;
    }
    c->head_pwr = el;
    c->head_htr = htr;
    rrch_event(c, RRCH_EV_HEAD_POWER, el, htr, why);
}

void rrch_power_update(rrch_t *c, const rrch_power_t *p)
{
    c->pwr = *p;
}

/* ------------------------------------------------------------------ init */
static uint32_t retained_crc(const rrch_retained_t *r)
{
    return rrc_crc32((const uint8_t *)r, offsetof(rrch_retained_t, crc));
}

void rrch_init(rrch_t *c, const rrch_hal_t *hal)
{
    memset(c, 0, sizeof *c);
    c->hal = *hal;
    c->chain.rearm_why = RRCH_RREF_FAULT_OR_MODE; /* nothing evaluated yet: a press would not be offered */
    c->now_us = hal->now_us(hal->ctx);
    uint8_t seed[4] = {1, 2, 3, 4};
    if (hal->entropy) {
        (void)hal->entropy(hal->ctx, seed, sizeof seed);
    }
    memcpy(&c->rng, seed, 4);
    if (!c->rng) {
        c->rng = 0xA5A5A5A5u;
    }
    if (!hal->entropy || !rrc_uuid4_generate(hal->entropy, hal->ctx, c->boot_id)) {
        uint8_t r16[16];
        for (int i = 0; i < 16; i++) {
            r16[i] = (uint8_t)rrch_rand(c);
        }
        rrc_uuid4_format(r16, c->boot_id);
    }
    c->reset_cause = hal->reset_cause ? hal->reset_cause(hal->ctx) : RRCH_RST_UNKNOWN;
    bool cfg_ok = rrch_cfg_load(&c->cfg, hal);

    /* persistent boot counter */
    uint8_t bl[8];
    size_t len = 0;
    if (hal->nv_read && hal->nv_read(hal->ctx, RRCH_NV_SLOT_BOOTLOG, bl, sizeof bl, &len) && len == 8u) {
        uint32_t cnt, crc;
        memcpy(&cnt, bl, 4);
        memcpy(&crc, bl + 4, 4);
        if (crc == rrc_crc32(bl, 4)) {
            c->boot_count = cnt;
        }
    }
    c->boot_count++;
    if (hal->nv_write) {
        uint32_t crc;
        memcpy(bl, &c->boot_count, 4);
        crc = rrc_crc32(bl, 4);
        memcpy(bl + 4, &crc, 4);
        (void)hal->nv_write(hal->ctx, RRCH_NV_SLOT_BOOTLOG, bl, 8);
    }

    /* record of the previous run from reset-surviving RAM */
    rrch_event_t *e = rrch_event(c, RRCH_EV_BOOT, (int32_t)c->reset_cause, (int32_t)c->boot_count, -1);
    rrch_retained_t *ret = hal->retained ? hal->retained(hal->ctx, sizeof(rrch_retained_t)) : NULL;
    if (ret && ret->magic == RETAINED_MAGIC && ret->crc == retained_crc(ret) && c->reset_cause != RRCH_RST_POWER_ON) {
        e->c = (int32_t)ret->mode;
        e->f = (float)ret->uptime_s;
        e->g = (float)ret->brownout;
        if (ret->brownout) {
            rrch_event(c, RRCH_EV_BROWNOUT, 0, 0, 0)->f = (float)ret->brownout * 0.001f;
        }
    }
    if (ret) {
        memset(ret, 0, sizeof *ret);
    }
    if (!cfg_ok) {
        c->faults |= RRCH_FLT(CONFIG_DEFAULTED);
        rrch_event(c, RRCH_EV_CONFIG, -1, 0, 0);
    }
    c->mode = RRCH_MODE_BOOT;
    c->op_mode = RRCH_OP_SERVICE;
    c->htr_setpoint_c = NAN;
    c->htr_sensor_ok = true;
    c->drive.alert_force = true;
    c->pwr.soc_pct = -1.0f;
    c->pwr.chg_temp_c = c->pwr.i_head_a = c->pwr.i_head_htr_a = c->pwr.i_chs_htr_a = NAN;
    c->pwr.charge_state = RRCH_CHG_UNKNOWN;
    c->grav[2] = 9.81f;
    for (int i = 0; i < RRCH_TOF_N; i++) {
        c->tof[i].ev_ms = 1000;
        c->tof[i].eff = RRCH_TOF_ST_OFFLINE;
    }
    rrch_proto_init(c);
    beep(c, 1, 60);
    c->hal.write_outputs(c->hal.ctx, &c->out); /* everything off, ARM_PERMIT low */
}

/* ------------------------------------------------------------------ brake test */
bool rrch_brake_test_start(rrch_t *c)
{
    rrch_brake_test_t *b = &c->bt;
    bool ok = c->mode == RRCH_MODE_ARMED_IDLE ||
              (c->mode == RRCH_MODE_PROTECTIVE_STOP && c->sw_latched == RRCH_SW(BRAKE_TEST_FAIL) && c->chain.latch);
    if (!ok || !c->drive.at_rest || b->state == RRCH_BT_RUNNING) {
        return false;
    }
    bool passed = b->passed_since_boot;
    memset(b, 0, sizeof *b);
    b->passed_since_boot = passed;
    b->state = RRCH_BT_RUNNING;
    b->latch_drop_ms = b->relay_ms = b->vmot_decay_ms = -1;
    b->t0_ticks[0] = c->drive.ticks[0];
    b->t0_ticks[1] = c->drive.ticks[1];
    return true;
}

static void bt_finish(rrch_t *c)
{
    rrch_brake_test_t *b = &c->bt;
    for (int i = 0; i < 2; i++) {
        int64_t m = c->drive.ticks[i] - b->t0_ticks[i];
        b->moved[i] = (int32_t)m;
        if (m > 10 || m < -10) {
            b->fail |= RRCH_BTF_WHEEL_MOVED;
        }
    }
    b->vmot_end_v = c->in.vmot_v;
    b->state = b->fail ? RRCH_BT_FAILED : RRCH_BT_PASSED;
    b->done_us = c->now_us;
    b->result_ready = true;
    if (b->fail) {
        b->passed_since_boot = false;
        rrch_pstop(c, RRCH_SW(BRAKE_TEST_FAIL));
    } else {
        b->passed_since_boot = true;
    }
    rrch_event(c, RRCH_EV_BRAKE_TEST, b->fail == 0, (int32_t)b->fail, 0);
}

/* runs after the drive step and overrides the bridge outputs while RUNNING. Returns the
 * ARM_PERMIT demand of the test (false = hold the permit low). */
static bool bt_step(rrch_t *c)
{
    rrch_brake_test_t *b = &c->bt;
    if (b->state != RRCH_BT_RUNNING) {
        return true;
    }
    uint32_t st = c->chain.state;
    bool bl = (st & RRCH_DI(BRAKE_L)) != 0, br = (st & RRCH_DI(BRAKE_R)) != 0;
    c->out.duty[0] = c->out.duty[1] = 0.0f;
    c->out.bridge_awake = false;
    b->ms++;
    switch (b->step) {
    case 0: /* preconditions */
        if (b->ms >= 20u) {
            if (c->in.vmot_v < CFG(c, BRK_VMOT_MIN_V)) {
                b->fail |= RRCH_BTF_PRECOND_VMOT;
            }
            if (!bl || !br || !c->chain.latch) {
                b->fail |= RRCH_BTF_PRECOND_RELAY;
            }
            if (b->fail) {
                bt_finish(c);
                return true;
            }
            b->step = 1;
            b->ms = 0;
        }
        return true;
    case 1: /* ARM_PERMIT low: latch, relays and VMOT must follow */
        if (b->latch_drop_ms < 0 && !(c->in.di & RRCH_DI(HW_LATCH))) {
            b->latch_drop_ms = (int32_t)b->ms;
        }
        if (b->relay_ms < 0 && !(c->in.di & RRCH_DI(BRAKE_L)) && !(c->in.di & RRCH_DI(BRAKE_R))) {
            b->relay_ms = (int32_t)b->ms;
        }
        if (b->vmot_decay_ms < 0 && c->in.vmot_v < CFG(c, BRK_VMOT_OFF_V)) {
            b->vmot_decay_ms = (int32_t)b->ms;
        }
        if ((b->latch_drop_ms >= 0 && b->relay_ms >= 0 && b->vmot_decay_ms >= 0 && b->ms >= 60u) || (float)b->ms >= CFG(c, BRK_VMOT_DECAY_MAX_MS)) {
            float lim = CFG(c, BRK_LATCH_DROP_MAX_MS);
            if (b->latch_drop_ms < 0 || (float)b->latch_drop_ms > lim) {
                b->fail |= RRCH_BTF_LATCH_NOT_DROPPED;
            }
            if (b->relay_ms < 0 || (float)b->relay_ms > lim) {
                b->fail |= (c->in.di & RRCH_DI(BRAKE_L)) ? RRCH_BTF_RELAY_L : 0u;
                b->fail |= (c->in.di & RRCH_DI(BRAKE_R)) ? RRCH_BTF_RELAY_R : 0u;
                if (!(b->fail & (RRCH_BTF_RELAY_L | RRCH_BTF_RELAY_R))) {
                    b->fail |= RRCH_BTF_RELAY_L | RRCH_BTF_RELAY_R; /* too slow */
                }
            }
            if (b->vmot_decay_ms < 0) {
                b->fail |= RRCH_BTF_VMOT_NOT_REMOVED;
            }
            if (c->in.di & RRCH_DI(HW_LATCH)) { /* never probe with the latch still set */
                bt_finish(c);
                return false;
            }
            b->step = 2;
            b->ms = 0;
        }
        return false;
    case 3: /* stage 3 (F2, F3): ARM_PERMIT back high with every element closed and NO REARM: K1 must read
             * released (LATCH_NC_RB high) and neither LATCH_RUN_RB nor HW_LATCH_RB may rise for 100 ms */
        if (b->ms == 1u && !(c->chain.iox_d_known && c->chain.k1_nc)) {
            b->fail |= RRCH_BTF_K1_NOT_RELEASED;
        }
        if (b->ms > 20u && (c->chain.k1_run || (c->in.di & RRCH_DI(HW_LATCH)))) {
            b->fail |= RRCH_BTF_K1_WELDED;
        }
        if (b->ms >= 120u) {
            bt_finish(c);
        }
        return true;
    default: /* probe: the bridges must be unable to move the motors */
        c->out.bridge_awake = true;
        c->out.duty[0] = c->out.duty[1] = CFG(c, BRK_PROBE_DUTY) * 0.01f;
        for (int i = 0; i < 2; i++) {
            if (b->ms > 10u && c->in.i_mot_a[i] > b->probe_i[i]) {
                b->probe_i[i] = c->in.i_mot_a[i];
            }
        }
        if (b->ms >= 100u) {
            c->out.duty[0] = c->out.duty[1] = 0.0f;
            c->out.bridge_awake = false;
            if (b->probe_i[0] > CFG(c, BRK_PROBE_I_MAX)) {
                b->fail |= RRCH_BTF_BRIDGE_CURRENT_L;
            }
            if (b->probe_i[1] > CFG(c, BRK_PROBE_I_MAX)) {
                b->fail |= RRCH_BTF_BRIDGE_CURRENT_R;
            }
            b->step = 3;
            b->ms = 0;
            return true;
        }
        return false;
    }
}

/* ------------------------------------------------------------------ monitors feeding the software latch */
static void monitors_step(rrch_t *c)
{
    const rrch_in_t *in = &c->in;
    uint32_t cond = 0, active = c->fields.cause_now;

    /* IMU window (10 ms mean) and tilt */
    if (c->imu_n == 0) {
        c->imu_t0 = c->now_us;
    }
    if (in->imu_ok) {
        for (int i = 0; i < 3; i++) {
            c->imu_acc[i] += in->gyro[i];
            c->imu_acc[3 + i] += in->accel[i];
            c->grav[i] += (in->accel[i] - c->grav[i]) * 0.002f;
        }
        c->imu_n++;
    }
    if (c->ms % 10u == 9u) {
        c->imu.ok = c->imu_n > 0;
        if (c->imu_n > 0) {
            for (int i = 0; i < 3; i++) {
                c->imu.gyro[i] = c->imu_acc[i] / (float)c->imu_n;
                c->imu.accel[i] = c->imu_acc[3 + i] / (float)c->imu_n;
            }
            c->imu.t_us = c->now_us >= 4500u ? c->now_us - 4500u : 0u;
        }
        memset(c->imu_acc, 0, sizeof c->imu_acc);
        c->imu_n = 0;
    }
    float gn = sqrtf(c->grav[0] * c->grav[0] + c->grav[1] * c->grav[1] + c->grav[2] * c->grav[2]);
    bool imu_bad = timer_run(&c->t_imu_missing, !in->imu_ok, 20);
    imu_bad |= timer_run(&c->t_imu_norm, in->imu_ok && (gn < 5.0f || gn > 15.0f), 1000);
    if (imu_bad) {
        cond |= RRCH_SW(IMU_FAULT);
    }
    float cz = gn > 1.0f ? c->grav[2] / gn : 1.0f;
    c->tilt_deg = acosf(cz > 1.0f ? 1.0f : (cz < -1.0f ? -1.0f : cz)) * 57.29578f;
    float tmax = CFG(c, IMU_TILT_MAX_DEG);
    if (timer_run(&c->t_tilt, in->imu_ok && c->tilt_deg > tmax, (uint16_t)CFG(c, IMU_TILT_MS))) {
        cond |= RRCH_SW(TILT);
    }
    if (c->tilt_deg > tmax - 2.0f && (c->sw_latched & RRCH_SW(TILT))) {
        active |= RRCH_SW(TILT);
    }

    /* battery */
    bool charger = (c->chain.hw_live & RRCH_HW(CHARGER)) != 0;
    bool low = timer_run(&c->t_batt_low, in->vbat_v < CFG(c, BATT_STOP_V), 5000);
    low |= c->pwr.soc_pct >= 0.0f && c->pwr.soc_pct < CFG(c, BATT_STOP_SOC);
    if (low) {
        cond |= RRCH_SW(BATTERY_LOW);
    }
    if ((c->sw_latched & RRCH_SW(BATTERY_LOW)) && in->vbat_v < CFG(c, BATT_STOP_V) + 0.4f) {
        active |= RRCH_SW(BATTERY_LOW);
    }
    rrch_fault_set(c, RRCH_FLT(BATTERY_WARN), in->vbat_v < CFG(c, BATT_WARN_V) && !charger);
    if (in->vbat_v < CFG(c, BATT_BROWNOUT_V) && c->boot_done) {
        if (!c->brownout_seen) {
            c->brownout_seen = true;
            rrch_event(c, RRCH_EV_BROWNOUT, 0, 0, 0)->f = in->vbat_v;
        }
    } else if (in->vbat_v > CFG(c, BATT_BROWNOUT_V) + 0.5f) {
        c->brownout_seen = false;
    }

    /* temperatures (NaN = sensor fault, handled by the heater logic) */
    float tmin = CFG(c, TEMP_MIN_C), tmx = CFG(c, TEMP_MAX_C), hy = (c->sw_latched & RRCH_SW(TEMP_RANGE)) ? 2.0f : 0.0f;
    bool trange = false;
    for (int i = 0; i < 2; i++) {
        if (in->ntc_c[i] < tmin + hy || in->ntc_c[i] > tmx - hy) {
            trange = true;
        }
    }
    if (in->ntc_c[2] > 85.0f - hy) {
        trange = true;
    }
    if (trange) {
        cond |= RRCH_SW(TEMP_RANGE);
    }

    /* host link supervision */
    bool link_ok = c->proto.any_rx && (c->now_us - c->proto.last_rx_us) < (uint64_t)(CFG(c, LINK_TIMEOUT_MS) * 1000.0f);
    if (c->hal.link_up && !c->hal.link_up(c->hal.ctx)) {
        link_ok = false;
    }
    if (!link_ok) {
        cond |= RRCH_SW(HOST_LINK_LOST);
    }
    if (c->drive.t_rest < 100u && (c->sw_latched & (RRCH_SW(STALL) | RRCH_SW(ENCODER_FAULT)))) {
        active |= c->sw_latched & (RRCH_SW(STALL) | RRCH_SW(ENCODER_FAULT));
    }
    if (c->bt.state == RRCH_BT_FAILED) {
        active |= RRCH_SW(BRAKE_TEST_FAIL);
    }
    c->sw_active = active | cond;

    /* latch only while the hardware latch is set */
    bool armed = c->boot_done && c->chain.latch &&
                 (c->mode == RRCH_MODE_ARMED_IDLE || c->mode == RRCH_MODE_MOVING || c->mode == RRCH_MODE_HOLD || c->mode == RRCH_MODE_PROTECTIVE_STOP);
    c->sw_acked &= c->fields.cause_now;
    if (armed && c->bt.state != RRCH_BT_RUNNING) {
        const rrch_drive_t *d = &c->drive;
        uint8_t dirs = d->cmd_valid ? rrch_drive_dir(d->cmd_v, d->cmd_w) : 0u;
        if (!d->at_rest) {
            if (d->v_meas > 0.005f) {
                dirs |= RRCH_DIR_FWD;
            } else if (d->v_meas < -0.005f) {
                dirs |= RRCH_DIR_REV;
            } else if (fabsf(d->w_meas_body) > 0.03f) {
                dirs |= RRCH_DIR_PIVOT;
            }
        }
        uint32_t fld = c->fields.confirmed;
        for (int k = 0; k < 3; k++) {
            if (dirs & (1u << k)) {
                fld |= c->fields.dir_cause[k];
            }
        }
        rrch_pstop(c, cond | (fld & ~c->sw_acked));
    }
}

/* ------------------------------------------------------------------ heater, head power */
static void aux_step(rrch_t *c)
{
    const rrch_in_t *in = &c->in;
    float bay = in->ntc_c[0], pack = in->ntc_c[1];
    bool ok = bay == bay && bay > -45.0f && bay < 90.0f; /* NaN-safe */
    if (c->ms % 1000u == 0u) {
        bool dis = ok && pack == pack && fabsf(bay - pack) > CFG(c, HTR_DISAGREE_C);
        c->t_htr_disagree_s = dis ? c->t_htr_disagree_s + 1u : 0u;
    }
    if (c->t_htr_disagree_s >= 60u) {
        ok = false;
    }
    c->htr_sensor_ok = ok;
    rrch_fault_set(c, RRCH_FLT(HEATER_SENSOR), !ok);
    /* Thermal policy (contract power.thermal_policy, DEC-045): with no host set-point the bay heater holds the
     * pack at or above heater.min_discharge_c (-10 C) on pack power, and at heater.precharge_c (+5 C) while an
     * external supply is present (charging pre-heat). A host set-point (-10..30 C) can only raise that floor.
     * Regulation input: the colder of the bay and pack NTCs. The hardware cold-charge inhibit is unchanged. */
    bool charger = c->mode == RRCH_MODE_SERVICE_CHARGE || (c->pwr.charger_ok && c->pwr.chg_input);
    float floor_c = charger ? CFG(c, HTR_PRECHARGE_C) : CFG(c, HTR_MIN_DISCHARGE_C);
    float sp = c->htr_enabled ? fmaxf(c->htr_setpoint_c, floor_c) : floor_c;
    float tctl = (pack == pack && pack < bay) ? pack : bay;
    c->htr_active_sp = sp;
    bool allow = ok && bay < CFG(c, HTR_MAX_C) && c->mode != RRCH_MODE_BOOT && c->mode != RRCH_MODE_FAULT &&
                 !(c->pwr.efuse_fault & 4u) && (charger || in->vbat_v >= CFG(c, BATT_WARN_V));
    float duty = 0.0f;
    if (allow) {
        duty = (sp - tctl) / CFG(c, HTR_BAND_C);
        duty = duty < 0.0f ? 0.0f : (duty > 1.0f ? 1.0f : duty);
        duty *= CFG(c, HTR_MAX_DUTY) * 0.01f;
    }
    c->htr_duty = duty;
    c->out.chs_htr_on = duty > 0.0f && (float)(c->ms % 2000u) < duty * 2000.0f;

    /* head branches: mode rules and presence */
    rrch_pres_t p = c->chain.pres;
    bool present = p == RRCH_PRES_HEAD_DIRECT || p == RRCH_PRES_HEAD_VIA_LAB_EXTENSION;
    if (c->head_pwr || c->head_htr) {
        if (c->mode == RRCH_MODE_SERVICE_CHARGE || c->mode == RRCH_MODE_FAULT || c->mode == RRCH_MODE_BOOT) {
            rrch_set_head_power(c, false, false, 2);
        } else if (!present) {
            rrch_set_head_power(c, false, false, 1);
        } else if (c->pwr.efuse_fault & 1u) {
            rrch_set_head_power(c, false, false, 3);
        } else if (c->head_htr && (c->pwr.efuse_fault & 2u)) {
            rrch_set_head_power(c, c->head_pwr, false, 3);
        }
    }
    static const uint32_t ef[5] = {RRCH_FLT(EFUSE_HEAD_PWR), RRCH_FLT(EFUSE_HEAD_HTR), RRCH_FLT(EFUSE_CHS_HTR), RRCH_FLT(EFUSE_LIDAR), RRCH_FLT(EFUSE_V5)};
    for (int i = 0; i < 5; i++) {
        rrch_fault_set(c, ef[i], (c->pwr.efuse_fault & (1u << i)) != 0);
    }
    rrch_fault_set(c, RRCH_FLT(PMON_COMM), c->boot_done && c->ms > 2000u && !c->pwr.pmon_ok);
    rrch_fault_set(c, RRCH_FLT(CHARGER_COMM), c->boot_done && c->ms > 2000u && !c->pwr.charger_ok);
    rrch_fault_set(c, RRCH_FLT(TOF_BUS), c->boot_done && c->ms > 2000u && !c->pwr.tof_bus_ok);
    c->out.head_pwr_en = c->head_pwr;
    c->out.head_htr_en = c->head_htr;
}

/* ------------------------------------------------------------------ panel */
static bool blink(const rrch_t *c, uint8_t pat)
{
    switch (pat) {
    case RRCH_LED_ON: return true;
    case RRCH_LED_BLINK_SLOW: return (c->ms % 1000u) < 500u;
    case RRCH_LED_BLINK_FAST: return (c->ms % 250u) < 125u;
    case RRCH_LED_BLINK_2: { uint32_t p = c->ms % 2000u; return p < 150u || (p >= 300u && p < 450u); }
    default: return false;
    }
}

static void panel_step(rrch_t *c)
{
    uint8_t *p = c->led_pat;
    memset(p, 0, RRCH_LED_N);
    bool alert = c->drive.motion == RRCH_MOTION_ALERT;
    switch (c->mode) {
    case RRCH_MODE_BOOT: memset(p, RRCH_LED_ON, RRCH_LED_N); break;
    case RRCH_MODE_STANDBY: p[RRCH_LED_READY] = RRCH_LED_BLINK_SLOW; break;
    case RRCH_MODE_ARMED_IDLE: p[RRCH_LED_READY] = RRCH_LED_ON; break;
    case RRCH_MODE_MOVING: p[RRCH_LED_READY] = RRCH_LED_ON; p[RRCH_LED_MOVING] = alert ? RRCH_LED_BLINK_FAST : RRCH_LED_ON; break;
    case RRCH_MODE_HOLD: p[RRCH_LED_HOLD] = RRCH_LED_ON; break;
    case RRCH_MODE_PROTECTIVE_STOP: p[RRCH_LED_HOLD] = RRCH_LED_BLINK_FAST; break;
    case RRCH_MODE_HW_INHIBIT: p[RRCH_LED_HOLD] = RRCH_LED_BLINK_2; break;
    case RRCH_MODE_FAULT: p[RRCH_LED_FAULT] = RRCH_LED_ON; break;
    case RRCH_MODE_SERVICE_CHARGE:
        p[RRCH_LED_CHARGE] = (c->pwr.charge_state == RRCH_CHG_PRECHARGE || c->pwr.charge_state == RRCH_CHG_CC || c->pwr.charge_state == RRCH_CHG_CV) ? RRCH_LED_BLINK_SLOW : RRCH_LED_ON;
        break;
    case RRCH_MODE_LAB: p[RRCH_LED_CHARGE] = RRCH_LED_BLINK_2; break;
    default: break;
    }
    bool host_ok = c->mode == RRCH_MODE_STANDBY || c->mode == RRCH_MODE_ARMED_IDLE || c->mode == RRCH_MODE_HOLD;
    if (!host_ok) {
        c->panel_pat = RRCH_PANEL_AUTO;
    }
    if (c->panel_pat == RRCH_PANEL_ARRIVED) {
        p[RRCH_LED_READY] = RRCH_LED_BLINK_2;
    } else if (c->panel_pat == RRCH_PANEL_LOCATE) {
        memset(p, RRCH_LED_BLINK_FAST, RRCH_LED_N);
    }
    if (c->mode != RRCH_MODE_FAULT && c->mode != RRCH_MODE_BOOT && (c->faults & ~RRCH_FLT_FATAL_MASK) && p[RRCH_LED_FAULT] == RRCH_LED_OFF) {
        p[RRCH_LED_FAULT] = RRCH_LED_BLINK_SLOW;
    }
    uint8_t leds = 0;
    for (int i = 0; i < RRCH_LED_N; i++) {
        if (blink(c, p[i])) {
            leds |= (uint8_t)(1u << i);
        }
    }
    c->out.leds = leds;

    /* buzzer: pre-motion alert has priority and cannot be suppressed */
    bool bz = false;
    if (c->beep_count > 0u) {
        if (c->beep_ms_left > 0u) {
            c->beep_ms_left--;
            bz = !c->beep_gap;
        } else if (!c->beep_gap) {
            c->beep_gap = 1;
            c->beep_ms_left = 120;
        } else {
            c->beep_gap = 0;
            c->beep_count--;
            c->beep_ms_left = c->beep_on_ms;
        }
    }
    if (c->panel_pat == RRCH_PANEL_ATTENTION || c->panel_pat == RRCH_PANEL_LOCATE) {
        uint32_t ph = c->ms % 5000u;
        bz |= ph < 100u || (ph >= 250u && ph < 350u);
    }
    if (alert) {
        bz = (c->ms % 250u) < 125u;
    }
    c->out.buzzer = bz;
    bool ready = !c->chain.latch && c->chain.rearm_why == RRCH_RREF_NONE; /* round 4 N1: a press will set the latch */
    bool clearable = (c->sw_latched || c->hold) && !(c->sw_active & c->sw_latched);
    c->out.lamp_rearm = (ready || clearable) && (c->ms % 500u) < 250u;
    if (!c->chain.latch && c->chain.refused_us != 0u && c->now_us - c->chain.refused_us < 2000000u) {
        c->out.lamp_rearm = (c->ms % 250u) < 125u; /* refused press: fast blink for 2 s (stage 4 G3) */
    }
    c->out.lamp_pause = c->mode == RRCH_MODE_MOVING;
}

/* ------------------------------------------------------------------ mode */
static rrch_mode_t mode_eval(const rrch_t *c)
{
    const rrch_chain_t *ch = &c->chain;
    if (c->faults & RRCH_FLT_FATAL_MASK) {
        return RRCH_MODE_FAULT;
    }
    if (!c->boot_done) {
        return RRCH_MODE_BOOT;
    }
    if (ch->hw_live & RRCH_HW(CHARGER)) {
        return RRCH_MODE_SERVICE_CHARGE;
    }
    if (ch->hw_live & RRCH_HW(LAB_KEY)) {
        return RRCH_MODE_LAB;
    }
    if (!ch->latch) {
        if (ch->hw_latched) {
            return RRCH_MODE_HW_INHIBIT;
        }
        return c->sw_latched ? RRCH_MODE_PROTECTIVE_STOP : RRCH_MODE_STANDBY;
    }
    if (c->sw_latched) {
        return RRCH_MODE_PROTECTIVE_STOP;
    }
    if (c->hold) {
        return RRCH_MODE_HOLD;
    }
    const rrch_drive_t *d = &c->drive;
    if ((d->cmd_valid && (d->cmd_v != 0.0f || d->cmd_w != 0.0f)) || d->motion != RRCH_MOTION_REST) {
        return RRCH_MODE_MOVING;
    }
    return RRCH_MODE_ARMED_IDLE;
}

/* ------------------------------------------------------------------ ticks */
void rrch_tick_1khz(rrch_t *c)
{
    c->wd_ctl_count++;
    c->wd_flow = 1u;
    c->now_us = c->hal.now_us(c->hal.ctx);
    c->hal.read_inputs(c->hal.ctx, &c->in);

    /* the control tick checks the supervisor (and so the strobe source) */
    if (c->wd_sup_count != c->wd_sup_seen_by_ctl) {
        c->wd_sup_seen_by_ctl = c->wd_sup_count;
        c->wd_sup_age = 0;
    } else if (++c->wd_sup_age > 50u) {
        rrch_fault_set(c, RRCH_FLT(TIMING), true);
    }

    if (c->wd_high && c->ms - c->wd_strobe_ms >= 5u) {
        if (c->hal.wdg_low) {
            c->hal.wdg_low(c->hal.ctx);
        }
        c->wd_high = false;
    }
    rrch_chain_step(c);
    if (!c->boot_done && c->ms >= 200u && c->chain.primed) {
        c->boot_done = true;
        c->chain.hw_latched = c->chain.latch ? 0u : (c->chain.hw_live & ~RRCH_HW(MCU_NOT_READY));
    }
    rrch_fields_step(c);
    monitors_step(c);
    c->wd_flow |= 2u;

    rrch_mode_t m = mode_eval(c);
    if (m != c->mode) {
        rrch_event(c, RRCH_EV_MODE, (int32_t)c->mode, (int32_t)m, 0);
        if (m == RRCH_MODE_FAULT) {
            beep(c, 1, 800);
        }
        c->mode = m;
    }
    rrch_drive_step(c);
    bool bt_permit = bt_step(c);

    /* ARM_PERMIT: firmware permissives only. Low can only open the chain. */
    if (c->permit_withdrawn) {
        bool rest = !c->chain.latch && c->drive.at_rest;
        c->permit_rest_ms = rest ? c->permit_rest_ms + 1u : 0u;
        if (c->permit_rest_ms >= 1000u) {
            c->permit_withdrawn = false;
            c->permit_rest_ms = 0;
        }
    }
    /* IB-01: no permit while its readback (CHAIN_END_RB on IOX_B) cannot be read, so the ARM_PERMIT
     * element is never closed unsupervised */
    bool permit = c->boot_done && m != RRCH_MODE_FAULT && m != RRCH_MODE_BOOT && m != RRCH_MODE_SERVICE_CHARGE && m != RRCH_MODE_LAB &&
                  !c->permit_withdrawn && bt_permit && c->chain.pres != RRCH_PRES_FAULT && !(c->chain.hw_live & RRCH_HW(VMOT_FAULT)) &&
                  c->chain.chain_end_known && !rrch_rearm_blocked(c) && c->chain.drop_ms >= 50u && !(c->faults & RRCH_FLT(LOOP_DISCREPANCY));
    /* once withdrawn, ARM_PERMIT stays low for at least 50 ms: K1 releases 4 ms after its coil loses
     * CHAIN_END; a shorter dip would let RUN_12V (HW_LATCH_RB) come back without REARM */
    if (!c->out.arm_permit && c->permit_low_ms < 50u) {
        c->permit_low_ms++;
        permit = false;
    }
    if (permit != c->out.arm_permit) {
        if (!permit) {
            c->permit_low_ms = 0;
        }
        if (permit || !c->permit_withdrawn) {
            rrch_event(c, RRCH_EV_PERMIT, permit, permit ? 0 : (bt_permit ? 4 : 3), 0);
        }
        c->out.arm_permit = permit;
    }
    if (m == RRCH_MODE_FAULT || m == RRCH_MODE_BOOT) {
        c->out.duty[0] = c->out.duty[1] = 0.0f;
        c->out.bridge_awake = false;
    }
    aux_step(c);
    panel_step(c);
    c->hal.write_outputs(c->hal.ctx, &c->out);

    /* breadcrumb for the next boot */
    if (c->ms % 1000u == 0u && c->hal.retained) {
        rrch_retained_t *r = c->hal.retained(c->hal.ctx, sizeof *r);
        if (r) {
            r->magic = RETAINED_MAGIC;
            r->mode = (uint32_t)c->mode;
            r->uptime_s = c->ms / 1000u;
            r->brownout = c->brownout_seen ? (uint32_t)(c->in.vbat_v * 1000.0f) : r->brownout;
            r->crc = retained_crc(r);
        }
    }
    c->ms++;
    c->wd_flow |= 4u;
}

void rrch_supervise_100hz(rrch_t *c)
{
    uint32_t n = c->wd_ctl_count - c->wd_ctl_seen;
    c->wd_ctl_seen = c->wd_ctl_count;
    bool flow = c->wd_flow == FLOW_ALL;
    c->wd_flow = 0;
    if (c->wd_bg_count != c->wd_bg_seen) {
        c->wd_bg_seen = c->wd_bg_count;
        c->wd_bg_age = 0;
    } else if (c->wd_bg_age < 1000u) {
        c->wd_bg_age++;
    }
    bool first = c->wd_sup_count == 0u;
    c->wd_sup_count++;
    bool ok = first || (n >= 8u && n <= 12u && flow && c->wd_bg_age <= 50u);
    if (c->faults & RRCH_FLT_NO_STROBE_MASK) {
        ok = false; /* TIMING; PERMIT_STUCK_ON: open the chain at WDG_OK, upstream of the suspect ARM_PERMIT element */
    }
    if (ok && !c->wd_inhibit_strobe && !c->wd_high) {
        /* review m2: WDI is a 5 ms high pulse every 10 ms (the control tick takes it low again), so the
         * TPS3430 sees one counted edge per 10 ms whether it counts rising, falling or both edges
         * (both: 5 ms apart, inside the 2.2-23.4 ms window). A dead control tick leaves WDI high. */
        c->hal.wdg_strobe(c->hal.ctx);
        c->wd_high = true;
        c->wd_strobe_ms = c->ms;
    }
}

void rrch_background(rrch_t *c)
{
    c->wd_bg_count++;
    rrch_proto_poll(c);
}
