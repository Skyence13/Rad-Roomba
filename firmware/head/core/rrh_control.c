/* Housekeeping: analog snapshot, health and fault latching, SiPM bias temperature compensation,
 * gate-aligned heater control.
 *
 * Fault philosophy: conditions that make data or the head unsafe to trust are LATCHED in
 * c->health and stay visible in every frame until FAULT_CLEAR is sent with the cause gone (or the
 * MCU resets). Conditions that are a plain measurement of "now" (temperature window, supply,
 * bias tracking) are evaluated per gate and not latched.
 */
#include "rrh_internal.h"

void rrh_control_init(rrh_core_t *c)
{
    c->control_due_us = 0u;
    c->live_flags = 0u;
    c->bumper_latched = 0u;
    c->bumper_gate = 0u;
    c->bias_cmd_mv = c->setup.bias_ref_mv;
    c->bias_on = false;
    c->bias_settle = 0u;
    c->heater_on = false;
    c->heater_dwell = RRH_HEATER_MIN_DWELL_GATES;
    c->heater_history = 0u;
    rrh_hal_heater_request(false);
    rrh_hal_bias_set(c->bias_cmd_mv, false);
    rrh_hal_analog_read(&c->analog);
}

/* Representative head temperature: mean of the valid SiPM sensors. */
int32_t rrh_control_head_mc(const rrh_core_t *c)
{
    int64_t sum = 0;
    int32_t n = 0;
    for (uint32_t i = 0u; i < RRH_LANES; i++) {
        if (c->analog.sipm_mc[i] != RRH_TEMP_INVALID) {
            sum += c->analog.sipm_mc[i];
            n++;
        }
    }
    return (n == 0) ? RRH_TEMP_INVALID : (int32_t)(sum / n);
}

static uint32_t bias_target_mv(const rrh_core_t *c, int32_t head_mc)
{
    /* V(T) = V_ref + tc * (T - T_ref); tc in uV/degC, T in mdegC -> nV, /1e6 -> mV */
    const int64_t delta_nv = (int64_t)c->setup.bias_tc_uv_per_c * ((int64_t)head_mc - (int64_t)c->setup.t_ref_mc);
    int64_t mv = (int64_t)c->setup.bias_ref_mv + (delta_nv / 1000000);
    if (mv < (int64_t)RRH_BIAS_MIN_MV) {
        mv = (int64_t)RRH_BIAS_MIN_MV;
    }
    if (mv > (int64_t)RRH_BIAS_MAX_MV) {
        mv = (int64_t)RRH_BIAS_MAX_MV;
    }
    return (uint32_t)mv;
}

static void bias_loop(rrh_core_t *c, int32_t head_mc)
{
    if ((c->health & RRH_H_BIAS_TRIP) != 0u) {
        if (c->bias_on) {
            c->bias_on = false;
            rrh_hal_bias_set(c->bias_cmd_mv, false);
        }
        return;
    }
    uint32_t next = c->bias_cmd_mv;
    if (head_mc != RRH_TEMP_INVALID) {
        /* With no usable temperature the last set-point is held (and the frame is flagged). */
        const uint32_t target = bias_target_mv(c, head_mc);
        const uint32_t diff = (target > next) ? (target - next) : (next - target);
        if (diff > RRH_BIAS_DEADBAND_MV) {
            const uint32_t step = (diff > RRH_BIAS_STEP_MV) ? RRH_BIAS_STEP_MV : diff;
            next = (target > next) ? (next + step) : (next - step);
        }
    }
    if ((next != c->bias_cmd_mv) || !c->bias_on) {
        c->bias_cmd_mv = next;
        c->bias_on = true;
        c->bias_settle = 0u;
        rrh_hal_bias_set(next, true);
    } else if (c->bias_settle < UINT32_MAX) {
        c->bias_settle++;
    } else {
        /* saturated counter */
    }
}

/* Take a housekeeping snapshot and evaluate every health condition on it. Called once per
 * control period and again whenever a gate completes, so a frame's flags describe its own gate. */
void rrh_control_sample(rrh_core_t *c)
{
    rrh_hal_analog_read(&c->analog);
    const rrh_analog_t *a = &c->analog;
    c->bumper_latched |= a->bumper_zones;
    c->bumper_gate |= a->bumper_zones;

    const int32_t head_mc = rrh_control_head_mc(c);
    uint8_t live = 0u;
    if ((head_mc == RRH_TEMP_INVALID) || (head_mc < RRH_HEAD_TEMP_MIN_MC) || (head_mc > RRH_HEAD_TEMP_MAX_MC)) {
        live |= RRH_AF_HEAD_TEMP_OUT_OF_RANGE;
    }
    if (!a->supply_valid || (a->supply_mv < RRH_SUPPLY_MIN_MV)) {
        live |= RRH_AF_UNDERVOLTAGE;
    }
    /* Bias: over-current trips and latches; tracking error is a live condition once settled. */
    if (a->bias_valid && (a->bias_ua > RRH_BIAS_CURRENT_MAX_UA)) {
        c->health |= RRH_H_BIAS_TRIP;
    }
    if (!c->bias_on || !a->bias_valid) {
        live |= RRH_AF_BIAS_OUT_OF_RANGE;
    } else if (c->bias_settle >= RRH_BIAS_SETTLE_PERIODS) {
        const uint32_t err = (a->bias_mv > c->bias_cmd_mv) ? (a->bias_mv - c->bias_cmd_mv) : (c->bias_cmd_mv - a->bias_mv);
        if (err > RRH_BIAS_TOLERANCE_MV) {
            live |= RRH_AF_BIAS_OUT_OF_RANGE;
        }
    } else {
        /* settling after a set-point step: not judged yet */
    }
    c->live_flags = live;

    /* Heater safety is checked continuously while heating is enabled, not only at gates. */
    if (c->setup.heater_enable && (c->armed || c->heater_on)) {
        if (a->heater_plate_mc == RRH_TEMP_INVALID) {
            c->health |= RRH_H_HEATER_SENSOR;
        } else if (a->heater_plate_mc > RRH_HEATER_PLATE_MAX_MC) {
            c->health |= RRH_H_HEATER_OVERTEMP;
        } else {
            /* plate temperature plausible */
        }
        if (!a->heater_cutout_ok) {
            c->health |= RRH_H_HEATER_CUTOUT;
        }
    }
    if (((c->health & (RRH_H_HEATER_SENSOR | RRH_H_HEATER_CUTOUT | RRH_H_HEATER_OVERTEMP | RRH_H_HEATER_STUCK)) != 0u) &&
        c->heater_on) {
        rrh_control_heater_off(c);
    }
}

void rrh_control_periodic(rrh_core_t *c, uint64_t now_us)
{
    if (now_us < c->control_due_us) {
        return;
    }
    c->control_due_us = now_us + RRH_CONTROL_PERIOD_US;
    rrh_control_sample(c);
    bias_loop(c, rrh_control_head_mc(c)); /* one slew-limited step per control period */
}

void rrh_control_heater_off(rrh_core_t *c)
{
    c->heater_on = false;
    c->heater_dwell = 0u;
    rrh_hal_heater_request(false);
}

/* Called once per completed gate while armed: decide the heater state for the following gates.
 * The port applies a change on a gate boundary only, so each gate is entirely on or off and the
 * gate that contains the (slew-limited) edge is marked in its record. */
void rrh_control_on_gate(rrh_core_t *c, const rrh_gate_record_t *rec)
{
    const uint16_t heater_faults = RRH_H_HEATER_SENSOR | RRH_H_HEATER_CUTOUT | RRH_H_HEATER_OVERTEMP | RRH_H_HEATER_STUCK;

    /* Commanded off for at least two whole gates but the gate record still shows it on. */
    if (!c->heater_on && (c->heater_dwell >= 2u) && (rec->heater_on_ticks > 0u)) {
        c->health |= RRH_H_HEATER_STUCK;
    }
    c->heater_history = (c->heater_history << 1) | (c->heater_on ? 1u : 0u);
    if (c->heater_dwell < UINT32_MAX) {
        c->heater_dwell++;
    }

    bool want = false;
    if (c->armed && c->setup.heater_enable && ((c->health & heater_faults) == 0u) &&
        (c->analog.heater_plate_mc != RRH_TEMP_INVALID) && c->analog.heater_cutout_ok) {
        const int32_t t = c->analog.heater_plate_mc;
        if (t < (c->setup.heater_setpoint_mc - RRH_HEATER_HYST_MC)) {
            want = true;
        } else if (t > (c->setup.heater_setpoint_mc + RRH_HEATER_HYST_MC)) {
            want = false;
        } else {
            want = c->heater_on;
        }
        /* Duty limit over the last RRH_HEATER_WINDOW_GATES gates. */
        uint32_t on_gates = 0u;
        for (uint32_t i = 0u; i < (RRH_HEATER_WINDOW_GATES - 1u); i++) {
            on_gates += (c->heater_history >> i) & 1u;
        }
        if (((on_gates + 1u) * 100u) > ((uint32_t)c->setup.heater_max_duty_pct * RRH_HEATER_WINDOW_GATES)) {
            want = false;
        }
        /* Minimum dwell in either state limits the number of marked transition gates. */
        if ((want != c->heater_on) && (c->heater_dwell < RRH_HEATER_MIN_DWELL_GATES) && want) {
            want = c->heater_on;
        }
    }
    if (want != c->heater_on) {
        c->heater_on = want;
        c->heater_dwell = 0u;
        rrh_hal_heater_request(want);
    }
}

/* Global ACQ flags for a frame completing now: latched health plus live conditions. */
uint8_t rrh_control_acq_flags(const rrh_core_t *c)
{
    uint8_t f = c->live_flags;
    if ((c->health & (RRH_H_SOURCE | RRH_H_GATE_TIMING | RRH_H_RECORD_LOST | RRH_H_GATE_TIMEOUT | RRH_H_INJECTED)) != 0u) {
        f |= RRH_AF_ACQ_FAULT;
    }
    if ((c->health & (RRH_H_HEATER_SENSOR | RRH_H_HEATER_CUTOUT | RRH_H_HEATER_OVERTEMP | RRH_H_HEATER_STUCK)) != 0u) {
        f |= RRH_AF_HEATER_FAULT;
    }
    if ((c->health & (RRH_H_HEATER_CUTOUT | RRH_H_HEATER_OVERTEMP)) != 0u) {
        f |= RRH_AF_OVERTEMP;
    }
    if ((c->health & RRH_H_BIAS_TRIP) != 0u) {
        f |= RRH_AF_BIAS_OUT_OF_RANGE;
    }
    return f;
}

/* Latched bits whose cause is no longer present (FAULT_CLEAR may clear only these). */
uint16_t rrh_control_clearable(const rrh_core_t *c)
{
    const rrh_analog_t *a = &c->analog;
    uint16_t ok = RRH_H_GATE_TIMING | RRH_H_RECORD_LOST | RRH_H_GATE_TIMEOUT | RRH_H_INJECTED | RRH_H_SOURCE |
                  RRH_H_HEATER_STUCK | RRH_H_ENTROPY | RRH_H_STORAGE | RRH_H_WATCHDOG_RESET;
    if (a->heater_plate_mc != RRH_TEMP_INVALID) {
        ok |= RRH_H_HEATER_SENSOR;
        if (a->heater_plate_mc <= RRH_HEATER_PLATE_MAX_MC) {
            ok |= RRH_H_HEATER_OVERTEMP;
        }
    }
    if (a->heater_cutout_ok) {
        ok |= RRH_H_HEATER_CUTOUT;
    }
    if (!a->bias_valid || (a->bias_ua <= RRH_BIAS_CURRENT_MAX_UA)) {
        ok |= RRH_H_BIAS_TRIP;
    }
    return ok;
}
