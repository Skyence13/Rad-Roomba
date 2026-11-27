/* HAL implementation of the emulated head: seeded Poisson source with a non-paralyzable
 * dead-time model, housekeeping model, in-memory storage. Single-threaded. */
#define _POSIX_C_SOURCE 200809L
#include <math.h>
#include <string.h>
#include <time.h>

#include "sim.h"

sim_t g_sim;

/* ---- deterministic random numbers (xoshiro256**, seeded with splitmix64) --------------------- */
static uint64_t splitmix(uint64_t *x)
{
    uint64_t z = (*x += 0x9E3779B97F4A7C15uLL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9uLL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBuLL;
    return z ^ (z >> 31);
}

static uint64_t rotl(uint64_t x, unsigned k)
{
    return (x << k) | (x >> (64u - k));
}

static uint64_t rng_next(uint64_t s[4])
{
    const uint64_t r = rotl(s[1] * 5u, 7u) * 9u;
    const uint64_t t = s[1] << 17;
    s[2] ^= s[0];
    s[3] ^= s[1];
    s[1] ^= s[2];
    s[0] ^= s[3];
    s[2] ^= t;
    s[3] = rotl(s[3], 45u);
    return r;
}

static double rng_uniform(uint64_t s[4]) /* (0, 1) */
{
    return ((double)(rng_next(s) >> 11) + 0.5) * (1.0 / 9007199254740992.0);
}

/* Poisson variate: inversion by multiplication for small means, PTRS (Hoermann 1993) above. */
static uint32_t rng_poisson(uint64_t s[4], double mean)
{
    if (!(mean > 0.0)) {
        return 0u;
    }
    if (mean > 4.0e9) {
        return 4000000000u;
    }
    if (mean < 30.0) {
        const double limit = exp(-mean);
        double p = rng_uniform(s);
        uint32_t k = 0u;
        while (p > limit) {
            p *= rng_uniform(s);
            k++;
        }
        return k;
    }
    const double b = 0.931 + (2.53 * sqrt(mean));
    const double a = -0.059 + (0.02483 * b);
    const double inv_alpha = 1.1239 + (1.1328 / (b - 3.4));
    const double vr = 0.9277 - (3.6224 / (b - 2.0));
    for (;;) {
        const double u = rng_uniform(s) - 0.5;
        const double v = rng_uniform(s);
        const double us = 0.5 - fabs(u);
        const double kf = floor((((2.0 * a) / us) + b) * u + mean + 0.43);
        if ((us >= 0.07) && (v <= vr)) {
            return (uint32_t)kf;
        }
        if ((kf < 0.0) || ((us < 0.013) && (v > us))) {
            continue;
        }
        if ((log(v) + log(inv_alpha) - log((a / (us * us)) + b)) <= ((-mean) + (kf * log(mean)) - lgamma(kf + 1.0))) {
            return (uint32_t)kf;
        }
    }
}

uint64_t sim_mono_ns(void)
{
    struct timespec ts;
    (void)clock_gettime(CLOCK_MONOTONIC, &ts);
    return ((uint64_t)ts.tv_sec * 1000000000uLL) + (uint64_t)ts.tv_nsec;
}

void sim_init(sim_t *s, uint64_t seed, bool manual)
{
    memset(s, 0, sizeof *s);
    uint64_t x = seed;
    for (int i = 0; i < 4; i++) {
        s->rng[i] = splitmix(&x);
    }
    x = seed ^ 0xB007B007B007B007uLL;
    for (int i = 0; i < 4; i++) {
        s->ent[i] = splitmix(&x);
    }
    s->manual = manual;
    s->turnaround_us = 150u;
    /* Dead time per recorded event of the MCU event capture: 4 us acceptance window + wait for
     * the next 100 kHz service + clear; about 9.7 us in the evtcap rate-sweep test. */
    s->tau_floor_us = 10.0;
    s->tau_ref_us = 10.0;
    s->arm_delay_us = 2000u;
    s->tick_offset = 987654321u;
    s->ambient_c = 20.0;
    s->width_hist = true;
    s->reset_cause = RRH_RESET_POWER_ON;
    for (uint32_t l = 0u; l < RRH_LANES; l++) {
        s->analog.sipm_mc[l] = 20000;
    }
    s->analog.heater_plate_mc = 20000;
    s->analog.board_mc = 24000;
    s->analog.bias_ua = 40u;
    s->analog.bias_valid = true;
    s->analog.supply_mv = 12000u;
    s->analog.supply_valid = true;
    s->analog.heater_cutout_ok = true;
    s->analog.zones_available = false; /* rev A: no rail-zone identification */
    for (uint32_t ch = 0u; ch < RRH_CHAINS; ch++) {
        s->imon_ua[ch] = 1.0;
    }
    s->imon_valid = 0xFFu;
    s->exp_present = true;
    s->boot_mono_ns = sim_mono_ns();
}

void sim_power_cycle(sim_t *s)
{
    s->boot_mono_ns = sim_mono_ns();
    s->manual_us = 0u;
    s->running = false;
    s->stopping = false;
    s->heater_req = false;
    s->heater_applied = false;
    s->bias_enable = false;
    s->bias_enable_prev = false;
    s->permit = false;
    s->wave_state = RRH_WAVE_IDLE;
    s->model_us = 0u;
    s->boot_count++;
}

bool sim_add_rate_change(sim_t *s, const sim_rate_change_t *chg)
{
    if (s->n_sched >= SIM_SCHED_MAX) {
        return false;
    }
    uint32_t i = s->n_sched;
    while ((i > 0u) && (s->sched[i - 1u].from_us > chg->from_us)) {
        s->sched[i] = s->sched[i - 1u];
        i--;
    }
    s->sched[i] = *chg;
    s->n_sched++;
    return true;
}

/* ---- time, entropy, system ------------------------------------------------------------------- */
uint64_t rrh_hal_now_us(void)
{
    if (g_sim.manual) {
        return g_sim.manual_us;
    }
    const uint64_t now = sim_mono_ns();
    return (now > g_sim.boot_mono_ns) ? ((now - g_sim.boot_mono_ns) / 1000u) : 0u;
}

uint64_t rrh_hal_reply_tx_time_us(uint64_t rx_us)
{
    const uint64_t now = rrh_hal_now_us();
    const uint64_t earliest = rx_us + g_sim.turnaround_us;
    return (now > earliest) ? now : earliest;
}

bool rrh_hal_entropy(uint8_t *buf, size_t len)
{
    if (g_sim.have_forced_boot_id && (len == 16u)) {
        memcpy(buf, g_sim.forced_boot_id, 16u);
        g_sim.have_forced_boot_id = false; /* first boot only */
        return true;
    }
    for (size_t i = 0u; i < len; i++) {
        buf[i] = (uint8_t)(rng_next(g_sim.ent) >> 56);
    }
    return true;
}

rrh_reset_cause_t rrh_hal_reset_cause(void)
{
    return g_sim.reset_cause;
}

void rrh_hal_watchdog_kick(void)
{
}

/* ---- acquisition source ---------------------------------------------------------------------- */
static uint64_t us_to_tick(uint64_t us)
{
    return (us * (uint64_t)(SIM_TICK_HZ / 1000000u)) + g_sim.tick_offset;
}

bool rrh_hal_acq_start(uint32_t span_us, rrh_epoch_t *epoch)
{
    sim_t *s = &g_sim;
    if (s->source_fail || (span_us == 0u)) {
        return false;
    }
    const uint64_t now = rrh_hal_now_us();
    s->running = true;
    s->stopping = false;
    s->span_us = span_us;
    s->t0_us = now + s->arm_delay_us; /* recording starts at the next gate boundary */
    s->next_gate = 0u;
    epoch->us = now;
    epoch->tick = us_to_tick(now);
    epoch->tick_hz = SIM_TICK_HZ;
    return true;
}

bool rrh_hal_acq_stop(void)
{
    sim_t *s = &g_sim;
    if (!s->running || s->stopping) {
        return s->running;
    }
    const uint64_t now = rrh_hal_now_us();
    if (now < s->t0_us) {
        s->running = false; /* no gate had started: nothing will be delivered */
        return false;
    }
    s->stopping = true;
    s->stop_after = (uint32_t)((now - s->t0_us) / s->span_us);
    return true;
}

void rrh_hal_acq_abort(void)
{
    g_sim.running = false;
    g_sim.stopping = false;
    g_sim.heater_applied = g_sim.heater_req;
}

bool rrh_hal_acq_running(void)
{
    return g_sim.running;
}

/* Expected counts of every channel over [start, end), honouring scheduled rate changes. */
static void integrate_rates(sim_t *s, uint64_t start, uint64_t end, double mean[RRH_LANES][SIM_CH])
{
    uint64_t t = start;
    memset(mean, 0, sizeof(double) * RRH_LANES * SIM_CH);
    for (;;) {
        const bool have = (s->n_sched > 0u) && (s->sched[0].from_us < end);
        const uint64_t seg_end = have ? ((s->sched[0].from_us > t) ? s->sched[0].from_us : t) : end;
        const double dt = (double)(seg_end - t) * 1e-6;
        for (uint32_t l = 0u; l < RRH_LANES; l++) {
            for (uint32_t ch = 0u; ch < SIM_CH; ch++) {
                mean[l][ch] += s->rate[l][ch] * dt;
            }
        }
        t = seg_end;
        if (!have) {
            break;
        }
        for (uint32_t l = 0u; l < RRH_LANES; l++) {
            for (uint32_t ch = 0u; ch < SIM_CH; ch++) {
                if (((s->sched[0].mask >> ((l * SIM_CH) + ch)) & 1u) != 0u) {
                    s->rate[l][ch] = s->sched[0].rate[l][ch];
                }
            }
        }
        s->n_sched--;
        memmove(&s->sched[0], &s->sched[1], sizeof(s->sched[0]) * s->n_sched);
    }
}

static uint32_t live_ticks(uint32_t gate_ticks, uint64_t events, double tau_us, uint64_t held, double hold_us)
{
    const double dead = (((double)events * tau_us) + ((double)held * hold_us)) * (double)(SIM_TICK_HZ / 1000000u);
    if (dead >= ((double)gate_ticks - 1.0)) {
        return 1u;
    }
    return gate_ticks - (uint32_t)dead;
}

/* Test pulser model (charge injection through C109..C809 into the selected chain, 1 kHz strobe).
 * Amplitude: Q = 100 pF x V(PULSER_AMPL) -> photo-electrons at 0.465 pC each, FAST output 6.9 mV
 * per p.e. above the 0.600 V baseline, compared with the chain's threshold DAC levels. A pulse
 * below LLD is not seen, above ULD it is a reject, otherwise a beta / reference count. The model
 * never produces alpha-class events (no slow-path amplitude model). SIMULATED constants of a 6 mm
 * J-series device (budget 2.2), not measurements. */
static void pulser_add(sim_t *s, double mean[RRH_LANES][SIM_CH], double span_s)
{
    if (!s->fe.pulser_enable) {
        return;
    }
    const uint32_t ch = s->fe.pulser_channel;
    const uint32_t lane = ch & 3u;
    const double pe = (double)rrh_board_pulser_fc(s->fe.pulser_code) / 465.0;
    const double amp_uv = pe * (double)RRH_FAST_UV_PER_PE;
    const uint16_t lld_code = (ch < 4u) ? s->fe.threshold[lane * 3u] : s->fe.threshold[12u + (lane * 2u)];
    const uint16_t uld_code = (ch < 4u) ? s->fe.threshold[(lane * 3u) + 1u] : s->fe.threshold[12u + (lane * 2u) + 1u];
    const double base = (double)rrh_board_baseline_uv();
    const double lld = (double)rrh_board_trim_uv(lld_code) - base; /* same DAC scale as the trim codes */
    const double uld = (double)rrh_board_trim_uv(uld_code) - base;
    const double n = 1000.0 * span_s;
    if (amp_uv < lld) {
        return;
    }
    if (ch < 4u) {
        mean[lane][(amp_uv >= uld) ? 3u : 1u] += n;
    } else {
        mean[lane][(amp_uv >= uld) ? 4u : 2u] += n;
    }
}

bool rrh_hal_acq_poll(rrh_gate_record_t *rec)
{
    sim_t *s = &g_sim;
    for (;;) {
        if (!s->running) {
            return false;
        }
        if (s->stopping && (s->next_gate > s->stop_after)) {
            s->running = false;
            s->stopping = false;
            s->heater_applied = s->heater_req;
            return false;
        }
        const uint64_t start = s->t0_us + ((uint64_t)s->next_gate * s->span_us);
        const uint64_t end = start + s->span_us;
        if (rrh_hal_now_us() < end) {
            return false;
        }
        const double span_s = (double)s->span_us * 1e-6;
        double mean[RRH_LANES][SIM_CH];
        integrate_rates(s, start, end, mean);
        pulser_add(s, mean, span_s);
        memset(rec, 0, sizeof *rec);
        rec->sequence = s->next_gate;
        rec->gate_start_tick = us_to_tick(start);
        rec->gate_ticks = s->span_us * (SIM_TICK_HZ / 1000000u);
        rec->tick_hz = SIM_TICK_HZ;
        if (s->width_hist) {
            rec->width_mask = 0xFFu;
            rec->width_edges_ns[0] = 150u;
            rec->width_edges_ns[1] = 400u;
            rec->width_edges_ns[2] = 2000u;
        }
        /* The heater state was latched at this gate's first tick. */
        rec->heater_on_ticks = s->heater_applied ? rec->gate_ticks : 0u;
        for (uint32_t l = 0u; l < RRH_LANES; l++) {
            rrh_gate_lane_t *g = &rec->lane[l];
            /* Non-paralyzable chain with dead time tau per accepted event: the accepted rate
             * is n / (1 + n * tau). The recorded counts are drawn with that mean, and the live
             * time is the gate minus tau per recorded event. */
            const double floor_n = mean[l][0] + mean[l][1] + mean[l][3];
            const double floor_true = floor_n / span_s;
            /* afterglow hold: each alpha event keeps the chain busy for alpha_hold_us more */
            const double hold_us = (double)s->fe.alpha_hold_us;
            const double tau_eff = s->tau_floor_us + ((floor_n > 0.0) ? ((mean[l][0] / floor_n) * hold_us) : 0.0);
            const double ff = 1.0 / (1.0 + (floor_true * tau_eff * 1e-6));
            const double ref_true = (mean[l][2] + mean[l][4]) / span_s;
            const double fr = 1.0 / (1.0 + (ref_true * s->tau_ref_us * 1e-6));
            g->alpha_counts = rng_poisson(s->rng, mean[l][0] * ff);
            g->beta_counts = rng_poisson(s->rng, mean[l][1] * ff);
            g->ref_counts = rng_poisson(s->rng, mean[l][2] * fr);
            g->floor_reject_counts = rng_poisson(s->rng, mean[l][3] * ff);
            g->ref_reject_counts = rng_poisson(s->rng, mean[l][4] * fr);
            g->floor_live_ticks =
                live_ticks(rec->gate_ticks, (uint64_t)g->alpha_counts + g->beta_counts + g->floor_reject_counts,
                           s->tau_floor_us, g->alpha_counts, hold_us);
            g->ref_live_ticks =
                live_ticks(rec->gate_ticks, (uint64_t)g->ref_counts + g->ref_reject_counts, s->tau_ref_us, 0u, 0.0);
            if ((((uint32_t)s->saturate_mask >> l) & 1u) != 0u) {
                g->flags |= RRH_GF_FLOOR_SATURATED;
            }
            if ((((uint32_t)s->saturate_mask >> (4u + l)) & 1u) != 0u) {
                g->flags |= RRH_GF_REF_SATURATED;
            }
            if ((((uint32_t)s->fe.chain_enable >> l) & 1u) == 0u) {
                g->flags |= RRH_GF_FLOOR_INVALID;
            }
            if ((((uint32_t)s->fe.chain_enable >> (4u + l)) & 1u) == 0u) {
                g->flags |= RRH_GF_REF_INVALID;
            }
            if (s->width_hist) {
                /* Synthetic pulse widths: beta-window and reference events in the 150-400 ns
                 * bin, over-range (reject) events in 0.4-2 us, alpha (slow ZnS light) >= 2 us. */
                rec->width_hist[l][1] = g->beta_counts;
                rec->width_hist[l][2] = g->floor_reject_counts;
                rec->width_hist[l][3] = g->alpha_counts;
                rec->width_hist[4u + l][1] = g->ref_counts;
                rec->width_hist[4u + l][2] = g->ref_reject_counts;
            }
            s->drawn[l][0] += g->alpha_counts;
            s->drawn[l][1] += g->beta_counts;
            s->drawn[l][2] += g->ref_counts;
            s->drawn[l][3] += g->floor_reject_counts;
            s->drawn[l][4] += g->ref_reject_counts;
        }
        /* The gate whose first tick switched the heater contains the slew-limited edge. */
        rec->heater_transition_in_gate = s->heater_applied != s->heater_last_gate;
        s->heater_last_gate = s->heater_applied;
        /* A pending request takes effect on the boundary that ends this gate. */
        s->heater_applied = s->heater_req;
        s->gates_total++;
        s->next_gate++;
        if (s->truth != NULL) {
            fprintf(s->truth, "{\"boot\":%u,\"src_seq\":%u,\"start_us\":%llu,\"span_us\":%u,\"lanes\":[", s->boot_count,
                    rec->sequence, (unsigned long long)start, s->span_us);
            for (uint32_t l = 0u; l < RRH_LANES; l++) {
                const rrh_gate_lane_t *g = &rec->lane[l];
                fprintf(s->truth,
                        "%s{\"alpha\":%u,\"beta\":%u,\"ref\":%u,\"floor_reject\":%u,\"ref_reject\":%u,"
                        "\"floor_live_ticks\":%u,\"ref_live_ticks\":%u,\"flags\":%u}",
                        (l == 0u) ? "" : ",", g->alpha_counts, g->beta_counts, g->ref_counts, g->floor_reject_counts,
                        g->ref_reject_counts, g->floor_live_ticks, g->ref_live_ticks, (unsigned)g->flags);
            }
            fprintf(s->truth, "]}\n");
            fflush(s->truth);
        }
        if (s->skip_gates > 0u) {
            s->skip_gates--; /* injected loss: the record is generated but never delivered */
            continue;
        }
        return true;
    }
}

/* ---- front end, bias, housekeeping ------------------------------------------------------------- */
bool rrh_hal_frontend_apply(const rrh_frontend_cfg_t *cfg)
{
    g_sim.fe = *cfg;
    return true;
}

/* Permit latch (U2205): set by a rising edge of HV_EN while no inhibit is active, cleared by any
 * inhibit (over-voltage comparator, +5V_A supervisor: `inhibit`; lid switch open: `lid_open`). */
static void permit_update(sim_t *s)
{
    if (s->inhibit || s->lid_open) {
        s->permit = false;
    }
}

void rrh_hal_bias_set(uint32_t millivolts, bool enable)
{
    sim_t *s = &g_sim;
    permit_update(s);
    if (enable && !s->bias_enable_prev && !s->inhibit && !s->lid_open) {
        s->permit = true;
    }
    if (!enable) {
        s->permit = false; /* HV_EN low: the latch D input stays high but the converter is off; re-arm needs a new edge */
    }
    s->bias_enable_prev = enable;
    s->bias_set_mv = millivolts;
    s->bias_enable = enable;
}

void rrh_hal_imon_read(rrh_imon_t *out)
{
    sim_t *s = &g_sim;
    memset(out, 0, sizeof *out);
    permit_update(s);
    const bool biased = s->bias_enable && s->permit && (s->bias_set_mv > 0u);
    for (uint32_t ch = 0u; ch < RRH_CHAINS; ch++) {
        /* V(TRIMDRV) = V(trim) - I x R105; the buffer cannot go below its rail (2 mV) */
        const double vt = (double)rrh_board_trim_uv(s->fe.trim[ch]);
        double v = vt - ((biased ? s->imon_ua[ch] : 0.0) * (double)RRH_R105_OHM) + (double)s->imon_offset_uv;
        if (v < 2000.0) {
            v = 2000.0;
        }
        out->uv[ch] = (uint32_t)v;
    }
    out->valid = s->imon_valid;
}

void rrh_hal_expander_read(rrh_expander_t *out)
{
    sim_t *s = &g_sim;
    permit_update(s);
    out->present = s->exp_present;
    out->inputs = 0u;
    if (s->exp_present) {
        out->inputs = (uint8_t)((s->permit ? RRH_EXP_HV_PERMIT : 0u) |
                                ((s->inhibit || s->lid_open) ? 0u : RRH_EXP_HV_INH_N) | (s->lid_open ? RRH_EXP_LID_G : 0u) |
                                (s->efuse_fault ? 0u : RRH_EXP_EF_FLT_N) | ((s->hw_rev & 1u) != 0u ? RRH_EXP_HWREV0 : 0u) |
                                ((s->hw_rev & 2u) != 0u ? RRH_EXP_HWREV1 : 0u));
    }
}

void rrh_hal_analog_read(rrh_analog_t *out)
{
    sim_t *s = &g_sim;
    /* First-order heater plate model: +2 K/s while on, relaxing with a 20 s time constant. */
    const uint64_t now = rrh_hal_now_us();
    const double dt = (double)(now - s->model_us) * 1e-6;
    s->model_us = now;
    if (dt > 0.0) {
        if (s->heater_applied && s->analog.heater_cutout_ok) {
            s->plate_heat_c += 2.0 * dt;
        }
        s->plate_heat_c -= s->plate_heat_c * ((dt > 20.0) ? 1.0 : (dt / 20.0));
    }
    *out = s->analog;
    for (uint32_t l = 0u; l < RRH_LANES; l++) {
        if (s->sipm_open[l]) {
            out->sipm_mc[l] = RRH_TEMP_INVALID;
        }
    }
    if (s->plate_open) {
        out->heater_plate_mc = RRH_TEMP_INVALID;
    } else {
        out->heater_plate_mc = s->analog.heater_plate_mc + (int32_t)(s->plate_heat_c * 1000.0);
    }
    permit_update(s);
    out->bias_mv = (s->bias_enable && s->permit) ? s->bias_set_mv : 0u; /* tripped permit: BIAS_VMON reads ~0 */
}

void rrh_hal_heater_request(bool on)
{
    g_sim.heater_req = on;
    if (!g_sim.running) {
        g_sim.heater_applied = on; /* no gates: immediate */
    }
}

/* ---- storage ----------------------------------------------------------------------------------- */
bool rrh_hal_nv_load(uint8_t slot, uint8_t *buf, size_t cap, size_t *len)
{
    if ((slot != RRH_NV_SLOT_SETUP) || (g_sim.nv_len == 0u) || (g_sim.nv_len > cap)) {
        return false;
    }
    memcpy(buf, g_sim.nv, g_sim.nv_len);
    *len = g_sim.nv_len;
    return true;
}

bool rrh_hal_nv_save(uint8_t slot, const uint8_t *buf, size_t len)
{
    if ((slot != RRH_NV_SLOT_SETUP) || (len > sizeof g_sim.nv)) {
        return false;
    }
    memcpy(g_sim.nv, buf, len);
    g_sim.nv_len = len;
    return true;
}

/* ---- waveform capture: a synthetic pulse on a pedestal, deterministic --------------------------- */
bool rrh_hal_wave_arm(const rrh_wave_cfg_t *cfg)
{
    g_sim.wave = *cfg;
    g_sim.wave_state = RRH_WAVE_DONE; /* the emulated trigger fires at once */
    return true;
}

rrh_wave_state_t rrh_hal_wave_status(uint16_t *samples, uint32_t *period_ns, uint16_t *trigger_index)
{
    *samples = g_sim.wave.samples;
    *period_ns = 250u;
    *trigger_index = g_sim.wave.pretrigger;
    return g_sim.wave_state;
}

bool rrh_hal_wave_read(uint16_t offset, uint16_t count, uint8_t *buf)
{
    const double tau_ns = g_sim.wave.slow_path ? 2000.0 : 60.0;
    for (uint16_t i = 0u; i < count; i++) {
        const int32_t n = (int32_t)offset + (int32_t)i - (int32_t)g_sim.wave.pretrigger;
        double v = 200.0;
        if (n >= 0) {
            const double t = (double)n * 250.0;
            v += 1500.0 * (t / tau_ns) * exp(1.0 - (t / tau_ns));
        }
        const uint16_t code = (uint16_t)v;
        buf[2u * i] = (uint8_t)(code & 0xFFu);
        buf[(2u * i) + 1u] = (uint8_t)(code >> 8);
    }
    return true;
}
