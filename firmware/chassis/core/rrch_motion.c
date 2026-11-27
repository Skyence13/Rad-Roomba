/* Protective fields from the ToF sensors and the drive controller (command TTL, caps, ramps,
 * wheel speed loops, current limit, stall / encoder-consistency supervision, stop escalation). */
#include <math.h>
#include <string.h>

#include "rrch.h"

#define TWO_PI 6.28318530718f
#define RAD_PER_TICK (TWO_PI / (float)RRCH_ENCODER_CPR)

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

/* ------------------------------------------------------------------ stop model (contract) */
float rrch_stop_distance(const rrch_cfg_t *cfg, float v)
{
    float t = cfg->v[RRCH_CFG_STOP_T_DELAY_MS] * 0.001f, a = cfg->v[RRCH_CFG_STOP_A_MIN];
    v = fabsf(v);
    return v * t + v * v / (2.0f * a) + cfg->v[RRCH_CFG_STOP_MARGIN_M];
}

/* largest speed that stops within dist_m */
float rrch_stop_vcap(const rrch_cfg_t *cfg, float dist_m)
{
    float t = cfg->v[RRCH_CFG_STOP_T_DELAY_MS] * 0.001f, a = cfg->v[RRCH_CFG_STOP_A_MIN];
    float d = dist_m - cfg->v[RRCH_CFG_STOP_MARGIN_M];
    if (!(d > 0.0f)) {
        return 0.0f;
    }
    return -a * t + sqrtf(a * a * t * t + 2.0f * a * d);
}

/* ------------------------------------------------------------------ protective fields */
void rrch_tof_update(rrch_t *c, int idx, int32_t range_mm, rrch_tof_status_t st, uint64_t t_us)
{
    if (idx < 0 || idx >= RRCH_TOF_N) {
        return;
    }
    rrch_tof_t *s = &c->tof[idx];
    s->range_mm = range_mm;
    s->status = st;
    s->t_us = t_us;
    s->seen = true;
}

void rrch_fields_step(rrch_t *c)
{
    rrch_fields_t *f = &c->fields;
    const float max_age_us = CFG(c, TOF_MAX_AGE_MS) * 1000.0f;
    uint8_t inhibit = 0;
    uint32_t cause = 0, confirmed = 0, dc[3] = {0, 0, 0};
    float vf, vr, wcap;
    rrch_caps(c, &vf, &vr, &wcap);
    float cap_f = vf, cap_r = vr;

    for (int i = 0; i < RRCH_TOF_N; i++) {
        rrch_tof_t *s = &c->tof[i];
        if (!s->seen) {
            s->eff = RRCH_TOF_ST_OFFLINE;
        } else if ((float)(c->now_us - (s->t_us < c->now_us ? s->t_us : c->now_us)) > max_age_us) {
            s->eff = RRCH_TOF_ST_STALE;
        } else {
            s->eff = s->status;
        }
        s->valid = s->eff == RRCH_TOF_ST_OK;
        if (s->ev_ms < 1000u) {
            s->ev_ms++;
        }
        if (s->valid != s->ev_valid && s->ev_ms >= 1000u && c->boot_done) {
            s->ev_valid = s->valid;
            s->ev_ms = 0;
            rrch_event(c, RRCH_EV_TOF, i, (int32_t)s->eff, 0);
        }
    }

    /* cliff sensors 0..3: FL, FR guard forward + pivot; RL, RR guard reverse + pivot */
    for (int i = 0; i < 4; i++) {
        rrch_tof_t *s = &c->tof[i];
        uint8_t dirs = (i < 2) ? (RRCH_DIR_FWD | RRCH_DIR_PIVOT) : (RRCH_DIR_REV | RRCH_DIR_PIVOT);
        uint32_t reason = 0;
        bool stale = s->eff == RRCH_TOF_ST_STALE || s->eff == RRCH_TOF_ST_OFFLINE;
        bool drop = (s->valid && (float)s->range_mm > CFG(c, CLIFF_DROP_MM)) || s->eff == RRCH_TOF_ST_NO_TARGET;
        bool blocked = s->valid && (float)s->range_mm < CFG(c, CLIFF_FLOOR_MIN_MM);
        if (stale) {
            reason |= RRCH_SW(TOF_STALE);
            s->drop_n = 0;
        } else if (drop || s->eff == RRCH_TOF_ST_INVALID) {
            reason |= (1u << (RRCH_SWI_CLIFF_FL + i));
        }
        if (!stale && s->t_us != s->last_count_t) { /* count each new sample once */
            s->last_count_t = s->t_us;
            if (drop) {
                if (s->drop_n < 250u) {
                    s->drop_n++;
                }
            } else {
                s->drop_n = 0;
            }
        }
        if (drop && (float)s->drop_n >= CFG(c, CLIFF_CONFIRM_N)) {
            confirmed |= (1u << (RRCH_SWI_CLIFF_FL + i));
        }
        if (blocked) {
            reason |= RRCH_SW(TOF_DISAGREE); /* inhibit at once; latch needs it to persist */
        }
        bool blk_t = timer_run(&f->t_blocked[i], blocked, (uint16_t)CFG(c, TOF_DISAGREE_MS));
        if (reason) {
            inhibit |= dirs;
            cause |= reason;
            uint32_t lr = reason;
            if (blocked && !blk_t) {
                lr &= ~RRCH_SW(TOF_DISAGREE);
            }
            for (int d = 0; d < 3; d++) {
                if (dirs & (1u << d)) {
                    dc[d] |= lr;
                }
            }
        }
    }

    /* oblique look sensors (IB-34). The grip-cheek pair LOOK_FL/LOOK_FR guards forward travel, the tail pair
     * LOOK_RL/LOOK_RR guards reverse travel. A pair caps and stops only motion in its own direction; the
     * other pair is still checked every tick (stale / invalid / abnormal floor) and inhibits its own
     * direction unlatched, so a reversal onto a bad sensor is refused. Reasons: LOOKAHEAD_L / LOOKAHEAD_R =
     * robot-left (+y) / robot-right sensor of the pair in the direction of travel.
     * No pair cross-comparison (TOF_DISAGREE): from mechanical/common/frames.yaml the floor spots of the
     * partners are 0.286 m (forward) / 0.217 m (rear) apart laterally against spot diameters of about
     * 0.17 m / 0.09 m (18 deg full field), so their fields do not overlap and a real edge seen by one
     * only is legitimate. Each sensor is checked against its own expected floor range instead. */
    static const struct { uint8_t idx; uint8_t rev; uint32_t side; } look[4] = {
        {RRCH_TOF_LOOK_FL, 0, RRCH_SW(LOOKAHEAD_L)}, {RRCH_TOF_LOOK_FR, 0, RRCH_SW(LOOKAHEAD_R)},
        {RRCH_TOF_LOOK_RL, 1, RRCH_SW(LOOKAHEAD_L)}, {RRCH_TOF_LOOK_RR, 1, RRCH_SW(LOOKAHEAD_R)}};
    for (int k = 0; k < 4; k++) {
        rrch_tof_t *s = &c->tof[look[k].idx];
        bool rev = look[k].rev != 0;
        uint8_t dir = rev ? RRCH_DIR_REV : RRCH_DIR_FWD;
        int di = rev ? 1 : 0;
        float nominal = rev ? CFG(c, LOOK_REV_NOMINAL_MM) : CFG(c, LOOK_FWD_NOMINAL_MM);
        float tol = rev ? CFG(c, LOOK_REV_TOL_MM) : CFG(c, LOOK_FWD_TOL_MM);
        float ahead = rev ? CFG(c, LOOK_REV_AHEAD_M) : CFG(c, LOOK_FWD_AHEAD_M);
        float cosf_ = rev ? CFG(c, LOOK_REV_COS) : CFG(c, LOOK_FWD_COS);
        if (s->eff == RRCH_TOF_ST_STALE || s->eff == RRCH_TOF_ST_OFFLINE) {
            inhibit |= dir;
            cause |= RRCH_SW(TOF_STALE);
            dc[di] |= RRCH_SW(TOF_STALE);
            f->look_active[k] = false;
            continue;
        }
        float r = (float)s->range_mm;
        if (s->valid && fabsf(r - nominal) <= tol) {
            f->look_active[k] = false;
            continue;
        }
        float dist;
        if (s->valid && r < nominal) { /* something stands on the floor in the field: measured each sample */
            dist = ahead - (nominal - r) * 0.001f * cosf_;
            f->look_active[k] = false;
        } else { /* floor ends or cannot be seen: track the remaining distance by odometry */
            if (!f->look_active[k]) {
                f->look_active[k] = true;
                f->look_dist0[k] = ahead;
                f->look_s0[k] = c->drive.odometer_m;
            }
            float travelled = (float)(c->drive.odometer_m - f->look_s0[k]);
            if (rev) {
                travelled = -travelled;
            }
            dist = f->look_dist0[k] - (travelled > 0.0f ? travelled : 0.0f);
        }
        float cap = rrch_stop_vcap(&c->cfg, dist);
        if (rev) {
            cap_r = cap < cap_r ? cap : cap_r;
        } else {
            cap_f = cap < cap_f ? cap : cap_f;
        }
        cause |= look[k].side;
        if (cap <= 0.0f) {
            inhibit |= dir;
            dc[di] |= look[k].side;
        }
    }

    /* rear proximity 8..10: guard reverse. NO_TARGET = nothing within range = clear. */
    for (int i = 8; i < RRCH_TOF_N; i++) {
        rrch_tof_t *s = &c->tof[i];
        if (s->eff == RRCH_TOF_ST_STALE || s->eff == RRCH_TOF_ST_OFFLINE || s->eff == RRCH_TOF_ST_INVALID) {
            inhibit |= RRCH_DIR_REV;
            cause |= RRCH_SW(TOF_STALE);
            dc[1] |= RRCH_SW(TOF_STALE);
        } else if (s->valid) {
            float r = (float)s->range_mm;
            if (r < CFG(c, REAR_STOP_MM)) {
                inhibit |= RRCH_DIR_REV;
                cause |= RRCH_SW(FIELD_REAR);
                dc[1] |= RRCH_SW(FIELD_REAR);
                cap_r = 0.0f;
            } else if (r < CFG(c, REAR_SLOW_MM)) {
                float cap = rrch_stop_vcap(&c->cfg, (r - CFG(c, REAR_STOP_MM)) * 0.001f + CFG(c, STOP_MARGIN_M));
                if (cap < cap_r) {
                    cap_r = cap;
                }
            }
        }
    }
    if (c->sw_acked != 0u) { /* retreat after an acknowledged, still-present cause */
        float rv = CFG(c, SAFE_RETREAT_V);
        cap_f = cap_f < rv ? cap_f : rv;
        cap_r = cap_r < rv ? cap_r : rv;
    }
    f->inhibit = inhibit;
    f->cause_now = cause;
    f->confirmed = confirmed;
    memcpy(f->dir_cause, dc, sizeof dc);
    f->v_cap_fwd = cap_f;
    f->v_cap_rev = cap_r;
}

/* ------------------------------------------------------------------ drive */
void rrch_caps(const rrch_t *c, float *vf, float *vr, float *w)
{
    int base;
    switch (c->op_mode) {
    case RRCH_OP_COMMISSIONING: base = RRCH_CFG_CAP_COM_VF; break;
    case RRCH_OP_SURVEY_SHARED: base = RRCH_CFG_CAP_SSH_VF; break;
    case RRCH_OP_SURVEY_UNATTENDED: base = RRCH_CFG_CAP_SUN_VF; break;
    case RRCH_OP_GUIDED: base = RRCH_CFG_CAP_GUI_VF; break;
    default:
        *vf = *vr = *w = 0.0f;
        return;
    }
    *vf = fminf(c->cfg.v[base], RRCH_MAX_V_FWD);
    *vr = fminf(c->cfg.v[base + 1], RRCH_MAX_V_REV);
    *w = fminf(c->cfg.v[base + 2], RRCH_MAX_W);
}

uint8_t rrch_drive_dir(float v, float w)
{
    if (v > 1e-4f) {
        return RRCH_DIR_FWD;
    }
    if (v < -1e-4f) {
        return RRCH_DIR_REV;
    }
    return (fabsf(w) > 1e-4f) ? RRCH_DIR_PIVOT : 0u;
}

void rrch_drive_stop(rrch_t *c, float decel, bool brake_now)
{
    rrch_drive_t *d = &c->drive;
    d->cmd_valid = false;
    d->cmd_v = d->cmd_w = 0.0f;
    if (brake_now) {
        d->brake_now = true;
    }
    if (!d->stop_req || decel > d->stop_decel) {
        d->stop_decel = decel;
    }
    if (!d->stop_req) {
        d->stop_req = true;
        d->alert_force = true;
        d->stop_ms = 0;
        float half_track = CFG(c, CAL_TRACK) * 0.5f;
        float vmax = fabsf(d->v_meas) + fabsf(d->w_meas_body) * half_track;
        float vsp = fabsf(d->v_sp) + fabsf(d->w_sp) * half_track;
        vmax = vmax > vsp ? vmax : vsp;
        d->stop_deadline_ms = (uint32_t)(vmax / decel * 1000.0f + CFG(c, STOP_ESCALATE_MS));
    }
}

static float ramp(float cur, float tgt, float up_per_tick, float down_per_tick)
{
    /* "down" = magnitude decreasing or sign change */
    if (cur == tgt) {
        return cur;
    }
    bool same = (cur >= 0.0f && tgt >= 0.0f) || (cur <= 0.0f && tgt <= 0.0f);
    if (same && fabsf(tgt) > fabsf(cur)) {
        float n = cur + (tgt > cur ? up_per_tick : -up_per_tick);
        return (tgt > cur) ? fminf(n, tgt) : fmaxf(n, tgt);
    }
    float goal = same ? tgt : 0.0f; /* pass through zero before accelerating the other way */
    float n = cur + (goal > cur ? down_per_tick : -down_per_tick);
    return (goal > cur) ? fminf(n, goal) : fmaxf(n, goal);
}

void rrch_drive_step(rrch_t *c)
{
    rrch_drive_t *d = &c->drive;
    const rrch_in_t *in = &c->in;
    const float r_w[2] = {CFG(c, CAL_RADIUS_L), CFG(c, CAL_RADIUS_R)};
    const float half_track = CFG(c, CAL_TRACK) * 0.5f;
    bool latch = c->chain.latch;
    bool armed = latch && (c->mode == RRCH_MODE_ARMED_IDLE || c->mode == RRCH_MODE_MOVING || c->mode == RRCH_MODE_HOLD || c->mode == RRCH_MODE_PROTECTIVE_STOP);

    /* --- encoders (16-bit counters extended), speed estimate --- */
    float dth[2];
    for (int i = 0; i < 2; i++) {
        int16_t delta = (int16_t)(uint16_t)(in->enc[i] - d->enc_prev[i]);
        if (c->ms == 0) {
            delta = 0;
        }
        d->enc_prev[i] = in->enc[i];
        d->ticks[i] += delta;
        d->win[i][d->win_i] = delta;
        int32_t sum = 0;
        for (int k = 0; k < 10; k++) {
            sum += d->win[i][k];
        }
        d->tps[i] += ((float)sum * 100.0f - d->tps[i]) * 0.05f;
        d->w_meas[i] = d->tps[i] * RAD_PER_TICK;
        dth[i] = (float)delta * RAD_PER_TICK;
        d->i_f[i] += (in->i_mot_a[i] - d->i_f[i]) * 0.2f;
    }
    /* stationarity evidence for scaler counts: zero encoder ticks on both wheels and a quiet gyro */
    {
        float gmax = CFG(c, STAT_GYRO_MAX);
        bool quiet = in->imu_ok && fabsf(in->gyro[0]) < gmax && fabsf(in->gyro[1]) < gmax && fabsf(in->gyro[2]) < gmax;
        if (dth[0] == 0.0f && dth[1] == 0.0f && quiet) {
            if (!d->stat_run) {
                d->stat_run = true;
                d->stat_since_us = c->now_us;
            }
        } else {
            d->stat_run = false;
        }
        d->is_stationary = d->stat_run && (float)(c->now_us - d->stat_since_us) >= CFG(c, STAT_MIN_MS) * 1000.0f;
    }
    d->win_i = (uint8_t)((d->win_i + 1u) % 10u);
    d->odometer_m += 0.5 * (double)(dth[0] * r_w[0] + dth[1] * r_w[1]);
    d->v_meas = 0.5f * (d->w_meas[0] * r_w[0] + d->w_meas[1] * r_w[1]);
    d->w_meas_body = (d->w_meas[1] * r_w[1] - d->w_meas[0] * r_w[0]) / (2.0f * half_track);
    bool slow = fabsf(d->tps[0]) < 40.0f && fabsf(d->tps[1]) < 40.0f;
    d->at_rest = timer_run(&d->t_rest, slow, 100);

    /* --- command time-to-live --- */
    if (d->cmd_valid && c->now_us >= d->cmd_expiry_us) {
        bool nonzero = d->cmd_v != 0.0f || d->cmd_w != 0.0f;
        d->cmd_valid = false;
        d->cmd_v = d->cmd_w = 0.0f;
        if (nonzero && armed) {
            rrch_pstop(c, RRCH_SW(CMD_TIMEOUT));
        }
    }

    /* --- stop enforcement --- */
    bool run_ok = armed && (c->mode == RRCH_MODE_ARMED_IDLE || c->mode == RRCH_MODE_MOVING) && c->bt.state != RRCH_BT_RUNNING;
    if (!run_ok) {
        float dec = (c->mode == RRCH_MODE_HOLD) ? CFG(c, DRV_DECEL) : CFG(c, DRV_PSTOP_DECEL);
        rrch_drive_stop(c, dec, !latch);
    } else if (d->stop_req && d->motion == RRCH_MOTION_REST) {
        d->stop_req = false;
        d->brake_now = false;
    }

    /* --- target after field caps --- */
    float tv = 0.0f, tw = 0.0f;
    if (run_ok && !d->stop_req && d->cmd_valid) {
        tv = d->cmd_v;
        tw = d->cmd_w;
        float cap = tv > 0.0f ? c->fields.v_cap_fwd : c->fields.v_cap_rev;
        if (fabsf(tv) > cap) {
            float k = (cap > 0.0f) ? cap / fabsf(tv) : 0.0f;
            tv *= k;
            tw *= k; /* keep the commanded curvature */
        }
        if (c->fields.inhibit & rrch_drive_dir(d->cmd_v, d->cmd_w)) {
            tv = tw = 0.0f;
        }
    }
    bool want = tv != 0.0f || tw != 0.0f;

    /* --- motion phase and ramps --- */
    if (d->motion == RRCH_MOTION_REST) {
        if (d->rest_ms < 0x7FFFFFFFu) {
            d->rest_ms++;
        }
        if (want) {
            if ((float)d->rest_ms >= CFG(c, ALERT_REST_MS) || d->alert_force) {
                d->motion = RRCH_MOTION_ALERT;
                d->alert_ms = 0;
            } else {
                d->motion = RRCH_MOTION_RUN; /* short hop inside the idle time: no delay, one chirp */
                c->beep_count = 1;
                c->beep_on_ms = c->beep_ms_left = 120;
                c->beep_gap = 0;
            }
        }
    } else if (d->motion == RRCH_MOTION_ALERT) {
        if (!want) {
            d->motion = RRCH_MOTION_REST;
        } else if ((float)++d->alert_ms >= CFG(c, ALERT_PREMOTION_MS)) {
            d->motion = RRCH_MOTION_RUN;
            d->alert_force = false;
        }
    }
    if (d->motion == RRCH_MOTION_RUN || d->motion == RRCH_MOTION_DECEL) {
        float dec = d->stop_req ? d->stop_decel : CFG(c, DRV_DECEL);
        float ydec = fmaxf(CFG(c, DRV_YAW_ACCEL), dec / half_track * 0.3f);
        if (d->brake_now) {
            d->v_sp = d->w_sp = 0.0f;
        } else {
            d->v_sp = ramp(d->v_sp, tv, CFG(c, DRV_ACCEL) * 0.001f, dec * 0.001f);
            d->w_sp = ramp(d->w_sp, tw, CFG(c, DRV_YAW_ACCEL) * 0.001f, ydec * 0.001f);
        }
        bool sp_zero = d->v_sp == 0.0f && d->w_sp == 0.0f;
        d->motion = want ? RRCH_MOTION_RUN : RRCH_MOTION_DECEL;
        if (!want && sp_zero && d->at_rest) {
            d->motion = RRCH_MOTION_REST;
            d->rest_ms = 0;
            d->rest_ticks[0] = d->ticks[0];
            d->rest_ticks[1] = d->ticks[1];
        }
    }

    /* --- wheel loops --- */
    float w_ref[2] = {(d->v_sp - d->w_sp * half_track) / r_w[0], (d->v_sp + d->w_sp * half_track) / r_w[1]};
    bool driving = armed && !d->brake_now && (d->motion == RRCH_MOTION_RUN || d->motion == RRCH_MOTION_DECEL);
    float vmot = in->vmot_v > 6.0f ? in->vmot_v : 6.0f;
    for (int i = 0; i < 2; i++) {
        if (!driving) {
            d->duty[i] = 0.0f;
            d->th_err[i] = 0.0f;
            d->lim[i] = 1.0f;
            d->t_stall[i] = d->t_enc[i] = 0;
            continue;
        }
        if (d->v_sp == 0.0f && d->w_sp == 0.0f && fabsf(d->tps[i]) < 150.0f) {
            /* zero-speed clamp: set-point at rest and the wheel below 5 mm/s -> brake (both low sides on) instead
             * of letting the position integrator creep against friction */
            d->duty[i] = 0.0f;
            d->th_err[i] = 0.0f;
            continue;
        }
        float inc = w_ref[i] * 0.001f - dth[i];
        d->th_err[i] += inc;
        float u = CFG(c, DRV_MOTOR_KE) * w_ref[i] / vmot + CFG(c, DRV_KP) * (w_ref[i] - d->w_meas[i]) + CFG(c, DRV_KI) * d->th_err[i];
        float lim = d->lim[i];
        if (u > lim || u < -lim) { /* anti-windup: do not integrate further into saturation */
            if ((u > 0.0f) == (inc > 0.0f)) {
                d->th_err[i] -= inc;
            }
            u = u > 0.0f ? lim : -lim;
        }
        if (d->th_err[i] > 0.6f) {
            d->th_err[i] = 0.6f;
        } else if (d->th_err[i] < -0.6f) {
            d->th_err[i] = -0.6f;
        }
        /* current limit: fold the duty ceiling back while the measured current exceeds the limit */
        float over = d->i_f[i] - CFG(c, DRV_I_LIMIT);
        if (over > 0.0f) {
            d->lim[i] -= 0.02f * over;
            if (d->lim[i] < 0.05f) {
                d->lim[i] = 0.05f;
            }
        } else if (d->lim[i] < 1.0f) {
            d->lim[i] += 0.001f;
        }
        d->duty[i] = u;

        /* stall: at the current limit with (almost) no speed */
        bool stall = fabsf(w_ref[i]) > 0.3f && fabsf(d->w_meas[i]) < 0.1f * fabsf(w_ref[i]) && d->i_f[i] > 0.8f * CFG(c, DRV_I_LIMIT);
        if (timer_run(&d->t_stall[i], stall, (uint16_t)CFG(c, DRV_STALL_MS))) {
            rrch_pstop(c, RRCH_SW(STALL));
        }
        /* encoder consistency: the motor model says the wheel turns but no counts arrive, or it turns the wrong way */
        float w_est = (fabsf(u) * vmot - d->i_f[i] * CFG(c, DRV_MOTOR_R)) / CFG(c, DRV_MOTOR_KE);
        bool nocount = w_est > 1.0f && fabsf(d->w_meas[i]) < 0.15f * w_est && !stall;
        bool wrongway = fabsf(w_ref[i]) > 0.3f && fabsf(d->w_meas[i]) > 0.5f && (w_ref[i] * d->w_meas[i]) < 0.0f;
        if (timer_run(&d->t_enc[i], nocount || wrongway, (uint16_t)CFG(c, DRV_ENC_FAULT_MS))) {
            rrch_pstop(c, RRCH_SW(ENCODER_FAULT));
            d->brake_now = true;
        }
    }
    for (int i = 0; i < 2; i++) { /* overspeed, in any armed state */
        bool over = fabsf(d->w_meas[i] * r_w[i]) > 1.5f * RRCH_MAX_V_FWD + 0.03f;
        if (timer_run(&d->t_over[i], armed && over, 50)) {
            rrch_pstop(c, RRCH_SW(ENCODER_FAULT));
            d->brake_now = true;
        }
    }
    /* uncommanded motion while armed and at rest */
    if (armed && d->motion == RRCH_MOTION_REST && c->bt.state != RRCH_BT_RUNNING) {
        for (int i = 0; i < 2; i++) {
            int64_t dt = d->ticks[i] - d->rest_ticks[i];
            if ((float)(dt < 0 ? -dt : dt) > CFG(c, DRV_UNCMD_TICKS)) {
                d->rest_ticks[i] = d->ticks[i];
                rrch_pstop(c, RRCH_SW(ENCODER_FAULT));
                if (!c->permit_withdrawn) {
                    c->permit_withdrawn = true;
                    rrch_event(c, RRCH_EV_PERMIT, 0, 1, 0);
                }
            }
        }
    } else if (!armed) {
        d->rest_ticks[0] = d->ticks[0];
        d->rest_ticks[1] = d->ticks[1];
    }
    /* stop escalation: a demanded stop that does not come to rest in time */
    if (d->stop_req && latch) {
        if (d->stop_ms < 0x7FFFFFFFu) {
            d->stop_ms++;
        }
        if (!d->at_rest && d->stop_ms > d->stop_deadline_ms && !c->permit_withdrawn) {
            c->permit_withdrawn = true;
            rrch_event(c, RRCH_EV_PERMIT, 0, 2, 0);
        }
    }
    if (!latch) { /* relays have isolated the motors: nothing to drive, nothing to integrate */
        d->v_sp = d->w_sp = 0.0f;
        if (d->at_rest) {
            d->motion = RRCH_MOTION_REST;
        } else if (d->motion != RRCH_MOTION_REST) {
            d->motion = RRCH_MOTION_DECEL;
        }
    }
    c->out.duty[0] = d->duty[0];
    c->out.duty[1] = d->duty[1];
    /* bridges wake only after both brake relays have been read back "connected" with the bridges asleep (CCR-E03 e) */
    c->out.bridge_awake = armed && c->chain.relays_ok && c->bt.state != RRCH_BT_RUNNING;

    /* --- odometry sample, 100 Hz --- */
    if (c->ms % 10u == 0u) {
        c->odom.t_us = c->now_us;
        c->odom.l = d->ticks[0];
        c->odom.r = d->ticks[1];
        c->odom.l_tps = d->tps[0];
        c->odom.r_tps = d->tps[1];
        c->odom.seq++;
    }
}
