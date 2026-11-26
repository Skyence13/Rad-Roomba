/* Host tests of the event-capture logic with a synthetic model of the latch hardware:
 * single events of every class, non-retriggering, acceptance window, forced clear, events that
 * straddle a gate boundary, a Poisson rate sweep 10..20000 1/s and service-interrupt jitter.
 * "Truth" is accumulated independently in the hardware model and compared EXACTLY with the
 * gate records (counts per class per gate, busy ticks split at the boundaries). */
#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "rrc_test.h"
#include "rrh_evtcap.h"

#define TICK_HZ 144000000u
#define US 144u                 /* ticks per microsecond */
#define SERVICE (10u * US)      /* 100 kHz */
#define WINDOW (4u * US)
#define MAX_HOLD (1000u * US)
#define GATE (100000u * US)
#define MAX_GATES 700u

/* ---- hardware model ------------------------------------------------------------------------ */
typedef struct {
    bool busy;
    uint64_t start;
    uint64_t ready_at;      /* latch can accept an edge again from this tick */
    uint64_t lld_high_until;
    bool uld, alpha;
    uint64_t accepted, lost;
} chain_t;

static chain_t hw[RRH_EVT_CHAINS];
static rrh_evtcap_t ec;
static uint64_t g_now, g_first_gate;
static uint32_t g_clear_latency = 40u; /* ticks from service entry to the first clear */
static uint64_t truth_busy[MAX_GATES][RRH_EVT_CHAINS];
static uint32_t truth_count[MAX_GATES][RRH_EVT_CHAINS][3];
static uint8_t g_width_mask = 0xFFu;
static uint32_t heater_calls;
static bool heater_level;

static uint32_t class_of(uint32_t ch)
{
    if (ch < 4u) {
        return hw[ch].alpha ? 0u : (hw[ch].uld ? 2u : 1u);
    }
    return hw[ch].uld ? 1u : 0u;
}

static uint64_t clear_cb(void *ctx, uint8_t ch)
{
    (void)ctx;
    const uint64_t t = g_now + g_clear_latency + (20u * ch);
    /* independent bookkeeping: the event belongs to the gate that contains t; its busy
     * interval [start, t) is split at every gate boundary */
    if (t >= g_first_gate) {
        const uint64_t gi = (t - g_first_gate) / GATE;
        if (gi < MAX_GATES) {
            const bool forced = (g_now - hw[ch].start >= MAX_HOLD) &&
                                !((g_now - hw[ch].start >= WINDOW) && (g_now >= hw[ch].lld_high_until));
            if (!forced) {
                truth_count[gi][ch][class_of(ch)]++;
            }
        }
        uint64_t a = (hw[ch].start > g_first_gate) ? hw[ch].start : g_first_gate;
        while (a < t) {
            const uint64_t g = (a - g_first_gate) / GATE;
            const uint64_t end = g_first_gate + ((g + 1u) * GATE);
            const uint64_t b = (t < end) ? t : end;
            if (g < MAX_GATES) {
                truth_busy[g][ch] += b - a;
            }
            a = b;
        }
    }
    hw[ch].busy = false;
    hw[ch].uld = false;
    hw[ch].alpha = false;
    hw[ch].ready_at = t;
    return t;
}

static void heater_cb(void *ctx, bool on)
{
    (void)ctx;
    heater_calls++;
    heater_level = on;
}

/* A pulse on chain ch at tick t: cls as in the firmware (floor 0 alpha, 1 beta, 2 reject;
 * reference 0 count, 1 reject); the comparator stays high for `width` ticks. */
static void pulse(uint32_t ch, uint64_t t, uint32_t cls, uint32_t width)
{
    chain_t *c = &hw[ch];
    if (c->busy || (t < c->ready_at) || (t < c->lld_high_until)) {
        c->lost++; /* non-retriggerable: no new edge, nothing changes */
        return;
    }
    c->busy = true;
    c->start = t;
    c->lld_high_until = t + width;
    if (ch < 4u) {
        c->alpha = cls == 0u;
        c->uld = cls == 2u;
    } else {
        c->uld = cls == 1u;
    }
    c->accepted++;
}

static void service_at(uint64_t t)
{
    rrh_evt_in_t in;
    memset(&in, 0, sizeof in);
    g_now = t;
    for (uint32_t ch = 0; ch < RRH_EVT_CHAINS; ch++) {
        const uint8_t bit = (uint8_t)(1u << ch);
        if (hw[ch].busy) {
            in.busy |= bit;
            in.start_tick[ch] = hw[ch].start;
        }
        if (t >= hw[ch].lld_high_until) {
            in.lld_low |= bit;
            if (hw[ch].busy) {
                /* the port's falling-edge capture: time over threshold of the triggering pulse */
                in.width_valid |= bit;
                in.width_ticks[ch] = (uint32_t)(hw[ch].lld_high_until - hw[ch].start);
            }
        }
        if (hw[ch].uld) {
            in.uld |= bit;
        }
        if (hw[ch].alpha) {
            in.alpha |= bit;
        }
    }
    rrh_evtcap_service(&ec, t, &in);
}

static void setup(uint64_t first_gate)
{
    /* width histogram on all chains, bin edges 150 ns, 400 ns, 2 us */
    const rrh_evt_cfg_t cfg = {TICK_HZ, WINDOW, MAX_HOLD, clear_cb, heater_cb, NULL, g_width_mask,
                               {(150u * US) / 1000u, (400u * US) / 1000u, 2u * US}, {150u, 400u, 2000u}};
    memset(hw, 0, sizeof hw);
    memset(truth_busy, 0, sizeof truth_busy);
    memset(truth_count, 0, sizeof truth_count);
    heater_calls = 0u;
    heater_level = false;
    g_clear_latency = 40u;
    g_first_gate = first_gate;
    rrh_evtcap_init(&ec, &cfg);
    CHECK(rrh_evtcap_start(&ec, first_gate, GATE));
}

static void run_services(uint64_t from, uint64_t to)
{
    for (uint64_t t = from; t <= to; t += SERVICE) {
        service_at(t);
    }
}

/* Compare one popped record with the independent truth of gate index gi. */
static void check_record(const rrh_gate_record_t *r, uint32_t gi)
{
    CHECK(r->gate_start_tick == g_first_gate + ((uint64_t)r->sequence * GATE));
    CHECK((r->gate_ticks == GATE) && (r->tick_hz == TICK_HZ));
    for (uint32_t l = 0; l < RRH_LANES; l++) {
        const rrh_gate_lane_t *g = &r->lane[l];
        CHECK(g->alpha_counts == truth_count[gi][l][0]);
        CHECK(g->beta_counts == truth_count[gi][l][1]);
        CHECK(g->floor_reject_counts == truth_count[gi][l][2]);
        CHECK(g->ref_counts == truth_count[gi][l + 4u][0]);
        CHECK(g->ref_reject_counts == truth_count[gi][l + 4u][1]);
        CHECK((uint64_t)g->floor_live_ticks + truth_busy[gi][l] == GATE);      /* live + busy = span, exactly */
        CHECK((uint64_t)g->ref_live_ticks + truth_busy[gi][l + 4u] == GATE);
    }
}

/* ---- tests ------------------------------------------------------------------------------------ */
static void test_single_events_of_each_class(void)
{
    rrh_gate_record_t r;
    setup(1000u * US);
    const uint64_t t0 = 2000u * US;
    run_services(0u, t0);                     /* idle until just before the events */
    pulse(0u, t0 + 7u, 0u, 300u);            /* floor 0: alpha */
    pulse(1u, t0 + 300u, 1u, 100u);          /* floor 1: beta */
    pulse(2u, t0 + 900u, 2u, 100u);          /* floor 2: reject */
    pulse(4u, t0 + 50u, 0u, 100u);           /* ref 0: count */
    pulse(5u, t0 + 1300u, 1u, 100u);         /* ref 1: reject */
    run_services(t0 + SERVICE, 1000u * US + GATE + SERVICE);
    CHECK(rrh_evtcap_pop(&ec, &r));
    check_record(&r, 0u);
    CHECK(r.sequence == 0u);
    CHECK((r.lane[0].alpha_counts == 1u) && (r.lane[0].beta_counts == 0u) && (r.lane[0].floor_reject_counts == 0u));
    CHECK((r.lane[1].alpha_counts == 0u) && (r.lane[1].beta_counts == 1u) && (r.lane[1].floor_reject_counts == 0u));
    CHECK((r.lane[2].alpha_counts == 0u) && (r.lane[2].beta_counts == 0u) && (r.lane[2].floor_reject_counts == 1u));
    CHECK((r.lane[0].ref_counts == 1u) && (r.lane[0].ref_reject_counts == 0u));
    CHECK((r.lane[1].ref_counts == 0u) && (r.lane[1].ref_reject_counts == 1u));
    CHECK((r.lane[3].beta_counts == 0u) && (r.lane[3].floor_live_ticks == GATE) && (r.lane[3].flags == 0u)); /* a true zero */
    /* pulse widths: 300 ticks = 2.08 us -> last bin; 100 ticks = 694 ns -> bin 2 (400 ns .. 2 us) */
    CHECK((r.width_mask == 0xFFu) && (r.width_edges_ns[0] == 150u) && (r.width_edges_ns[2] == 2000u));
    CHECK((r.width_hist[0][3] == 1u) && (r.width_hist[0][0] + r.width_hist[0][1] + r.width_hist[0][2] == 0u));
    CHECK((r.width_hist[1][2] == 1u) && (r.width_hist[2][2] == 1u) && (r.width_hist[4][2] == 1u) && (r.width_hist[5][2] == 1u));
    CHECK(r.width_hist[3][0] + r.width_hist[3][1] + r.width_hist[3][2] + r.width_hist[3][3] == 0u);
    /* dead time of the alpha event: from the captured start to the measured clear, which is the
     * first service at least one window after the start (+ the model's clear latency) */
    const uint64_t first_service = (((t0 + 7u + WINDOW) + SERVICE - 1u) / SERVICE) * SERVICE;
    CHECK(GATE - r.lane[0].floor_live_ticks == (first_service + 40u) - (t0 + 7u));
    CHECK(ec.total_events == 5u);
}

static void test_non_retriggering_window_and_forced_clear(void)
{
    rrh_gate_record_t r;
    setup(0u);
    /* second and third pulse while BUSY: no effect at all */
    pulse(1u, 500u * US, 1u, 100u);
    pulse(1u, 500u * US + 200u, 2u, 100u);
    pulse(1u, 500u * US + 400u, 0u, 100u);
    CHECK((hw[1].accepted == 1u) && (hw[1].lost == 2u));
    /* not classified before the window has elapsed, however often the service runs */
    service_at(500u * US + 100u);
    service_at(500u * US + WINDOW - 1u);
    CHECK(hw[1].busy && (ec.total_events == 0u));
    service_at(500u * US + WINDOW);
    CHECK(!hw[1].busy && (ec.total_events == 1u));
    service_at(500u * US + WINDOW + 10u);
    CHECK(ec.total_events == 1u); /* one event, one count */
    /* a long pulse (slow alpha tail): classification waits for the comparator to return low */
    pulse(0u, 2000u * US, 0u, 60u * US);
    run_services(2000u * US, 2000u * US + 50u * US);
    CHECK(hw[0].busy && (ec.total_events == 1u));
    run_services(2000u * US + 60u * US, 2000u * US + 70u * US);
    CHECK(!hw[0].busy && (ec.total_events == 2u));
    /* comparator stuck high: forced clear after the maximum hold, flagged, not counted */
    pulse(6u, 5000u * US, 0u, 5000u * US);
    run_services(5000u * US, 5000u * US + 1100u * US);
    CHECK(!hw[6].busy && (ec.total_forced == 1u) && (ec.total_events == 2u));
    run_services(6200u * US, GATE + SERVICE);
    CHECK(rrh_evtcap_pop(&ec, &r));
    check_record(&r, 0u);
    CHECK((r.lane[2].flags & RRH_GF_REF_SATURATED) != 0u);
    CHECK(r.lane[2].ref_counts == 0u);
    CHECK(GATE - r.lane[2].ref_live_ticks >= MAX_HOLD);
    CHECK((r.lane[1].beta_counts == 1u) && (r.lane[0].alpha_counts == 1u) && (r.lane[1].flags == 0u));
    /* blind chain: comparator high, latch not set -> flagged in that gate (never a clean zero) */
    hw[7].lld_high_until = GATE + 50000u * US;
    run_services(GATE + 2u * SERVICE, 2u * GATE + SERVICE);
    CHECK(rrh_evtcap_pop(&ec, &r));
    CHECK((r.lane[3].flags & RRH_GF_REF_SATURATED) != 0u);
    CHECK((r.lane[0].flags == 0u) && (r.lane[2].flags == 0u));
}

static void test_event_straddling_a_gate_boundary(void)
{
    rrh_gate_record_t a, b;
    setup(0u);
    run_services(0u, GATE - 2u * SERVICE);
    /* (1) reference chain 1: ready at the last service BEFORE the boundary, but the clear itself
     *     lands after it (exaggerated clear latency): the boundary is crossed inside one service */
    const uint64_t s2 = GATE - SERVICE - WINDOW - 5u;
    pulse(5u, s2, 0u, 100u);
    g_clear_latency = SERVICE + 300u;
    service_at(GATE - SERVICE);
    g_clear_latency = 40u;
    /* (2) floor chain 1: starts 3 us before the boundary, window still open at the boundary
     *     service, classified by the next one */
    const uint64_t s1 = GATE - 3u * US;
    pulse(1u, s1, 1u, 100u);
    run_services(GATE, 2u * GATE + SERVICE);
    CHECK(rrh_evtcap_pop(&ec, &a) && rrh_evtcap_pop(&ec, &b));
    check_record(&a, 0u);
    check_record(&b, 1u);
    /* counted once, in the gate that contains the clear */
    CHECK((a.lane[1].beta_counts == 0u) && (b.lane[1].beta_counts == 1u));
    CHECK((a.lane[1].ref_counts == 0u) && (b.lane[1].ref_counts == 1u));
    /* busy time split exactly at the boundary */
    CHECK(GATE - a.lane[1].floor_live_ticks == 3u * US);
    CHECK(GATE - b.lane[1].floor_live_ticks == SERVICE + 40u + 20u); /* boundary .. clear at the second service */
    CHECK(GATE - a.lane[1].ref_live_ticks == GATE - s2);
    CHECK(GATE - b.lane[1].ref_live_ticks == (GATE - SERVICE + SERVICE + 300u + 100u) - GATE);
    CHECK((a.sequence == 0u) && (b.sequence == 1u));
    CHECK(b.gate_start_tick == a.gate_start_tick + a.gate_ticks);   /* contiguous, equal gates */
}

static uint64_t rng_state;
static double rnd(void)
{
    rng_state ^= rng_state >> 12;
    rng_state ^= rng_state << 25;
    rng_state ^= rng_state >> 27;
    return ((double)((rng_state * 0x2545F4914F6CDD1DuLL) >> 11) + 0.5) / 9007199254740992.0;
}

/* Poisson arrivals of `rate` per second on all 8 chains for `seconds`; services at 100 kHz with
 * optional jitter (ticks) and occasional late services. Returns via pointers the totals. */
static void poisson_run(double rate, double seconds, uint32_t jitter, bool hiccups, double *counted_rate,
                        double *corrected_rate, double *dead_fraction)
{
    static uint64_t next[RRH_EVT_CHAINS];
    const double mean_gap = (double)TICK_HZ / rate;
    const uint32_t gates = (uint32_t)(seconds * 10.0);
    rrh_gate_record_t r;
    static rrh_gate_record_t prev;
    bool have_prev = false;
    setup(SERVICE * 5u);
    for (uint32_t ch = 0; ch < RRH_EVT_CHAINS; ch++) {
        next[ch] = (uint64_t)(-log(rnd()) * mean_gap);
    }
    uint64_t counts = 0u, live = 0u, popped = 0u;
    const uint64_t end = g_first_gate + ((uint64_t)gates * GATE) + (3u * SERVICE);
    uint64_t t = 0u;
    while (t <= end) {
        uint64_t ts = t;
        if (jitter != 0u) {
            ts += (uint64_t)(rnd() * (double)jitter);
        }
        if (hiccups && (rnd() < 0.001)) {
            ts += 5u * SERVICE; /* a service that comes 50 us late */
            t += 5u * SERVICE;
        }
        for (uint32_t ch = 0; ch < RRH_EVT_CHAINS; ch++) {
            while (next[ch] <= ts) {
                const double u = rnd();
                uint32_t cls;
                uint32_t width;
                if (ch < 4u) {
                    cls = (u < 0.05) ? 0u : ((u < 0.15) ? 2u : 1u);
                    width = (cls == 0u) ? (6u * US) : 40u; /* alpha pulses are long, fast ones ~0.3 us */
                } else {
                    cls = (u < 0.1) ? 1u : 0u;
                    width = 40u;
                }
                pulse(ch, next[ch], cls, width);
                next[ch] += 1u + (uint64_t)(-log(rnd()) * mean_gap);
            }
        }
        service_at(ts);
        while (rrh_evtcap_pop(&ec, &r)) {
            CHECK(r.sequence == popped);
            /* Exact agreement with the hardware model. A record is compared one gate later, when
             * every event that was still open at its closing boundary has been cleared and booked
             * by the model as well. */
            if (have_prev && (prev.sequence < MAX_GATES)) {
                check_record(&prev, prev.sequence);
            }
            prev = r;
            have_prev = true;
            for (uint32_t l = 0; l < RRH_LANES; l++) {
                /* width histogram: every classified event is in exactly one bin; alpha pulses
                 * (6 us) in the last bin, everything else (40 ticks = 278 ns) in bin 1 */
                CHECK(r.width_hist[l][3] == r.lane[l].alpha_counts);
                CHECK(r.width_hist[l][1] == r.lane[l].beta_counts + r.lane[l].floor_reject_counts);
                CHECK(r.width_hist[4u + l][1] == r.lane[l].ref_counts + r.lane[l].ref_reject_counts);
                CHECK((r.width_hist[l][0] == 0u) && (r.width_hist[l][2] == 0u));
                CHECK(r.lane[l].flags == 0u);
                counts += (uint64_t)r.lane[l].alpha_counts + r.lane[l].beta_counts + r.lane[l].floor_reject_counts +
                          r.lane[l].ref_counts + r.lane[l].ref_reject_counts;
                live += (uint64_t)r.lane[l].floor_live_ticks + r.lane[l].ref_live_ticks;
            }
            popped++;
        }
        t += SERVICE;
    }
    CHECK(popped == gates);
    CHECK(ec.lost_gates == 0u);
    /* conservation: every accepted hardware event is in exactly one gate (at most one per chain
     * may still be open or fall into the unfinished gate at the end) */
    uint64_t accepted = 0u;
    for (uint32_t ch = 0; ch < RRH_EVT_CHAINS; ch++) {
        accepted += hw[ch].accepted;
    }
    CHECK((accepted >= counts) && ((accepted - counts) <= 2u * RRH_EVT_CHAINS + (uint64_t)(rate * 8.0 * 1e-4 * 4.0)));
    const double total_s = (double)gates * 0.1 * 8.0; /* chain-seconds */
    *counted_rate = (double)counts / total_s;
    *corrected_rate = (double)counts / ((double)live / (double)TICK_HZ);
    *dead_fraction = 1.0 - (((double)live / (double)TICK_HZ) / total_s);
}

static void test_poisson_rate_sweep(void)
{
    static const double rates[] = {10.0, 100.0, 1000.0, 5000.0, 20000.0};
    static const double secs[] = {60.0, 20.0, 5.0, 2.0, 2.0};
    rng_state = 0x1234567887654321uLL;
    for (size_t i = 0; i < sizeof rates / sizeof rates[0]; i++) {
        double counted, corrected, dead;
        poisson_run(rates[i], secs[i], 0u, false, &counted, &corrected, &dead);
        const double n = rates[i] * secs[i] * 8.0;
        const double tol = (4.0 / sqrt(n)) + 0.002; /* 4 sigma of the Poisson total + 0.2 % */
        printf("    true %8.1f /s  counted %9.2f /s  live-time corrected %9.2f /s  dead %6.3f %%  (tolerance %.2f %%)\n",
               rates[i], counted, corrected, dead * 100.0, tol * 100.0);
        CHECK(fabs((corrected / rates[i]) - 1.0) < tol);       /* measured live time recovers the true rate */
        CHECK(counted <= rates[i] * (1.0 + tol));
        if (rates[i] >= 5000.0) {
            CHECK(counted < rates[i] * 0.97);                  /* losses are real at high rate ... */
            CHECK(dead > 0.03);                                /* ... and visible as dead time */
        }
        /* mean dead time per event stays between the window and window + one service period + clear latency */
        const double per_event_us = (dead / counted) * 1e6;
        CHECK((per_event_us >= 4.0) && (per_event_us <= 4.0 + 10.0 + 2.5 + 6.0));
    }
}

static void test_service_jitter_tolerance(void)
{
    double counted, corrected, dead, counted0, corrected0, dead0;
    rng_state = 0xDEADBEEFCAFEF00DuLL;
    poisson_run(5000.0, 3.0, 0u, false, &counted0, &corrected0, &dead0);
    rng_state = 0xDEADBEEFCAFEF00DuLL;
    /* up to 6 us of jitter on every service and one in a thousand arriving 50 us late */
    poisson_run(5000.0, 3.0, 6u * US, true, &counted, &corrected, &dead);
    printf("    jitter-free: corrected %.1f /s, dead %.3f %%;  jittered: corrected %.1f /s, dead %.3f %%\n", corrected0,
           dead0 * 100.0, corrected, dead * 100.0);
    const double tol = (4.0 / sqrt(5000.0 * 3.0 * 8.0)) + 0.002;
    CHECK(fabs((corrected / 5000.0) - 1.0) < tol);   /* still unbiased: the dead time is measured */
    CHECK(dead > dead0);                             /* jitter only costs live time, and that is accounted */
}

static void test_gates_heater_stop_and_overflow(void)
{
    rrh_gate_record_t r;
    setup(0u);
    /* heater: requested mid-gate, switched only on the boundary; the first gate after the switch is marked */
    run_services(0u, GATE / 2u);
    rrh_evtcap_heater_request(&ec, true);
    CHECK((heater_calls == 0u) && !heater_level);
    run_services(GATE / 2u + SERVICE, GATE + SERVICE);
    CHECK((heater_calls == 1u) && heater_level);
    CHECK(rrh_evtcap_pop(&ec, &r) && (r.heater_on_ticks == 0u) && !r.heater_transition_in_gate);
    run_services(GATE + 2u * SERVICE, 2u * GATE + SERVICE);
    CHECK(rrh_evtcap_pop(&ec, &r) && (r.heater_on_ticks == GATE) && r.heater_transition_in_gate);
    run_services(2u * GATE + 2u * SERVICE, 3u * GATE + SERVICE);
    CHECK(rrh_evtcap_pop(&ec, &r) && (r.heater_on_ticks == GATE) && !r.heater_transition_in_gate);
    /* disabled chain: cleared, never counted, live 0 + INVALID */
    rrh_evtcap_set_chain_enable(&ec, 0xFBu);
    pulse(2u, 3u * GATE + 1000u, 1u, 100u);
    pulse(3u, 3u * GATE + 1000u, 1u, 100u);
    /* stop in the middle of gate 3: that gate is completed, then nothing more; heater off with it */
    run_services(3u * GATE + 2u * SERVICE, 3u * GATE + GATE / 3u);
    CHECK(rrh_evtcap_stop(&ec, 3u * GATE + GATE / 3u));
    CHECK(rrh_evtcap_running(&ec) && heater_level);
    run_services(3u * GATE + GATE / 3u + SERVICE, 5u * GATE);
    CHECK(rrh_evtcap_pop(&ec, &r) && (r.sequence == 3u));
    CHECK((r.lane[2].flags == RRH_GF_FLOOR_INVALID) && (r.lane[2].floor_live_ticks == 0u) && (r.lane[2].beta_counts == 0u));
    CHECK((r.lane[3].flags == 0u) && (r.lane[3].beta_counts == 1u));
    CHECK(!rrh_evtcap_pop(&ec, &r) && !rrh_evtcap_running(&ec));
    CHECK(!heater_level && (heater_calls == 2u));
    CHECK(!hw[2].busy); /* the disabled chain was still cleared */
    /* stop before the first gate started: nothing is delivered */
    CHECK(rrh_evtcap_start(&ec, 6u * GATE, GATE));
    CHECK(!rrh_evtcap_stop(&ec, 5u * GATE + 10u) && !rrh_evtcap_running(&ec));
    /* main loop not popping: after RRH_EVT_FIFO - 1 stored gates further ones are dropped and counted */
    g_first_gate = 10u * GATE;
    CHECK(rrh_evtcap_start(&ec, g_first_gate, GATE));
    run_services(10u * GATE, 16u * GATE + SERVICE);
    CHECK(ec.lost_gates == 6u - (RRH_EVT_FIFO - 1u));
    uint32_t got = 0u, last = 0u;
    while (rrh_evtcap_pop(&ec, &r)) {
        last = r.sequence;
        got++;
    }
    CHECK((got == RRH_EVT_FIFO - 1u) && (last == RRH_EVT_FIFO - 2u));
    run_services(16u * GATE + 2u * SERVICE, 17u * GATE + SERVICE);
    CHECK(rrh_evtcap_pop(&ec, &r) && (r.sequence == 6u)); /* the loss is visible as a sequence skip */
    rrh_evtcap_abort(&ec);
    CHECK(!rrh_evtcap_running(&ec));
    /* a port without width measurement: the record says so and the histogram stays empty */
    g_width_mask = 0u;
    setup(20u * GATE);
    g_width_mask = 0xFFu;
    run_services(20u * GATE, 20u * GATE + 5u * SERVICE);
    pulse(1u, 20u * GATE + 5u * SERVICE + 3u, 1u, 100u);
    run_services(20u * GATE + 6u * SERVICE, 21u * GATE + SERVICE);
    CHECK(rrh_evtcap_pop(&ec, &r) && (r.lane[1].beta_counts == 1u) && (r.width_mask == 0u));
    CHECK(r.width_hist[1][0] + r.width_hist[1][1] + r.width_hist[1][2] + r.width_hist[1][3] == 0u);
    rrh_evtcap_abort(&ec);
    /* without gates a heater request acts at once */
    rrh_evtcap_heater_request(&ec, true);
    CHECK(heater_level);
    rrh_evtcap_heater_request(&ec, false);
    CHECK(!heater_level);
}

int main(void)
{
    RUN(test_single_events_of_each_class);
    RUN(test_non_retriggering_window_and_forced_clear);
    RUN(test_event_straddling_a_gate_boundary);
    RUN(test_poisson_rate_sweep);
    RUN(test_service_jitter_tolerance);
    RUN(test_gates_heater_stop_and_overflow);
    return TEST_SUMMARY();
}
