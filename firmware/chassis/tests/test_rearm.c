/* Round 4 regression tests (docs/reviews/REVIEW_traction_inhibit_followup.md N1/M5, N2, N6, W-018) on the
 * emulator's set-stage model aligned with electronics/analysis/chassis_braking_tables.md T11 (K1 operates above
 * 8.75 mA coil current for the 3 ms operate time, coil +0.393 %/K, C_SET dumped by every press, set gate cut
 * short when the set contact opens). SIMULATED: the emulator is a model of the netlist, not the board. */
#include <math.h>
#include <string.h>

#include "harness.h"

static bool fault(th_t *t, uint64_t flag)
{
    return (t->sim.core.faults & flag) != 0;
}

static int count_ev(th_t *t, uint64_t after, rrch_ev_kind_t kind, int a)
{
    int n = 0;
    const rrch_t *c = &t->sim.core;
    for (uint64_t s = after + 1u; s <= c->ev_newest; s++) {
        const rrch_event_t *e = &c->ev[(s - 1u) % RRCH_EVENTS_N];
        if (e->kind == kind && (a < 0 || e->a == a)) {
            n++;
        }
    }
    return n;
}

/* run until the firmware says a press will set the latch; returns the time waited (ms), -1 if never */
static int wait_ready(th_t *t, int max_ms)
{
    for (int ms = 0; ms <= max_ms; ms++) {
        if (!t->sim.core.chain.latch && t->sim.core.chain.rearm_why == RRCH_RREF_NONE) {
            return ms;
        }
        th_run_silent(t, 1);
    }
    return -1;
}

static void press(th_t *t, int ms)
{
    char j[64];
    snprintf(j, sizeof j, "{\"press\":\"REARM\",\"press_ms\":%d,\"no_wait\":true}", ms);
    th_env(t, j);
}

/* hardware threshold of the emulator: C_SET can drive the must-operate current for the operate time */
static bool hw_can_set(th_t *t)
{
    double tc = isfinite(t->sim.k1_coil_c) ? t->sim.k1_coil_c : t->sim.temp[2];
    double rc = 1028.0 * (1.0 + 0.00393 * (tc - 23.0));
    double tau = rc * t->sim.cset_uf * 1e-6;
    return t->sim.vc * exp(-t->sim.k1_pickup_ms * 1e-3 / tau) / rc > 8.75e-3;
}

#define FATAL (RRCH_FLT_FATAL_MASK)

int main(void)
{
    SECTION("N1: a press at the old 2 s 'ready' point is refused by the T11 set stage; the firmware did not offer it and reports why");
    {
        th_t *t = th_new(1401);
        th_run_silent(t, 2300); /* chain closed ~2 s: C_SET at ~60 % */
        CHECK(!t->sim.core.out.lamp_rearm && t->sim.core.chain.rearm_why == RRCH_RREF_RESERVOIR_LOW && th_req(t, "STATE", "{}") && !th_true(t, "rearm_ready"));
        uint64_t s0 = t->sim.core.ev_newest;
        double vc0 = t->sim.vc;
        press(t, 200);
        th_run_silent(t, 500);
        printf("  SIMULATED: C_SET %.2f V at the press -> latch %d; REARM_REFUSED(RESERVOIR_LOW) events %d\n", vc0, t->sim.latch,
               count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_RESERVOIR_LOW));
        CHECK(!t->sim.latch && count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_RESERVOIR_LOW) == 1 && !(t->sim.core.faults & FATAL));
        CHECK(th_req(t, "STATE", "{}") && th_is(t, "rearm_refusal", "RESERVOIR_LOW") && !th_true(t, "rearm_ready"));
        CHECK(th_req(t, "DIAG", "{}") && th_is(t, "rearm.why", "RESERVOIR_LOW"));

        /* reviewer case: presses every 0.9 s each dump C_SET; none sets, every one is reported */
        s0 = t->sim.core.ev_newest;
        int sets = 0;
        for (int k = 0; k < 8; k++) {
            press(t, 200);
            th_run_silent(t, 900);
            sets += t->sim.latch ? 1 : 0;
        }
        int refused = count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_RESERVOIR_LOW);
        printf("  SIMULATED: 8 presses 0.9 s apart -> %d set, %d reported REARM_REFUSED(RESERVOIR_LOW), C_SET %.2f V\n", sets, refused, t->sim.vc);
        CHECK(sets == 0 && refused == 8 && !(t->sim.core.faults & FATAL));
        int w = wait_ready(t, 15000);
        bool can = hw_can_set(t);
        press(t, 200);
        th_run_silent(t, 400);
        printf("  SIMULATED: then waiting for rearm_ready (%d ms) and one press -> latch %d\n", w, t->sim.latch);
        CHECK(w > 3000 && can && t->sim.latch && !(t->sim.core.faults & FATAL) && th_req(t, "STATE", "{}") && rrc_json_type(&t->doc, th_get(t, "rearm_refusal")) == RRC_JT_NULL);
    }

    SECTION("N1: rearm_ready is never early: pack 11.6-13.4 V x board 0-50 C x C_SET 80-120 uF, press at the first ready ms");
    {
        static const double vb[4] = {11.6, 12.0, 12.8, 13.4}, tb[3] = {0.0, 25.0, 50.0}, cu[3] = {80.0, 100.0, 120.0};
        int ok = 0, n = 0, wmin = 1 << 30, wmax = 0, n_cons = 0;
        for (int i = 0; i < 4; i++) {
            for (int j = 0; j < 3; j++) {
                for (int k = 0; k < 3; k++) {
                    th_t *t = th_new(1410u + (unsigned)(i * 9 + j * 3 + k));
                    char e[128];
                    snprintf(e, sizeof e, "{\"vbat\":%.2f,\"temp_board\":%.1f,\"cset_uf\":%.0f}", vb[i], tb[j], cu[k]);
                    th_env(t, e);
                    int w = wait_ready(t, 30000);
                    bool can = w >= 0 && hw_can_set(t);
                    uint8_t why0 = t->sim.core.chain.rearm_why;
                    press(t, 200);
                    th_run_silent(t, 400);
                    /* not offered at all is allowed only as SUPPLY_LOW (conservative: the model never reaches its need) */
                    bool cons = w < 0 && why0 == RRCH_RREF_SUPPLY_LOW;
                    bool good = ((w >= 0 && can && t->sim.latch) || cons) && !(t->sim.core.faults & FATAL) && t->sim.n_resets == 0u;
                    n_cons += cons ? 1 : 0;
                    if (!good) {
                        printf("  case %s: ready after %d ms, emulator can set %d, latch %d, why %s\n", e, w, can, t->sim.latch, rrch_rref_names[why0]);
                    }
                    ok += good ? 1 : 0;
                    n++;
                    wmin = w >= 0 && w < wmin ? w : wmin;
                    wmax = w > wmax ? w : wmax;
                }
            }
        }
        printf("  SIMULATED: %d/%d cases correct (%d never offered: SUPPLY_LOW, conservative), the rest set at the first ready ms;\n"
               "  rearm_ready came %.1f-%.1f s after the chain closed\n", ok, n, n_cons, wmin / 1e3, wmax / 1e3);
        CHECK(ok == n);
    }

    SECTION("N1: SUPPLY_LOW, CHAIN_OPEN, REARM_HELD reasons; a coil hotter than the model allows is reported SET_FAILED, not silent");
    {
        th_t *t = th_new(1450);
        th_env(t, "{\"vbat\":9.4}");
        th_run_silent(t, 12000);
        uint64_t s0 = t->sim.core.ev_newest;
        CHECK(t->sim.core.chain.rearm_why == RRCH_RREF_SUPPLY_LOW);
        press(t, 200);
        th_run_silent(t, 500);
        CHECK(!t->sim.latch && count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_SUPPLY_LOW) == 1);

        t = th_new(1451);
        th_run_silent(t, 8000);
        th_env(t, "{\"bumper_l\":true}");
        th_run_silent(t, 100);
        s0 = t->sim.core.ev_newest;
        CHECK(t->sim.core.chain.rearm_why == RRCH_RREF_CHAIN_OPEN);
        press(t, 200);
        th_run_silent(t, 500);
        CHECK(!t->sim.latch && count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_CHAIN_OPEN) == 1 && th_req(t, "STATE", "{}") && th_is(t, "rearm_refusal", "CHAIN_OPEN"));
        th_env(t, "{\"bumper_l\":false}");
        th_env(t, "{\"rearm_aux_short\":true,\"rearm_set_short\":true}");
        th_run_silent(t, 2600);
        CHECK(t->sim.core.chain.rearm_why == RRCH_RREF_REARM_HELD && !t->sim.latch && fault(t, RRCH_FLT(REARM_HELD)));

        t = th_new(1452);
        th_env(t, "{\"temp_board\":25,\"k1_coil_c\":85}"); /* coil 60 K above the board: outside the model's +10 K */
        int w = wait_ready(t, 20000);
        s0 = t->sim.core.ev_newest;
        press(t, 200);
        th_run_silent(t, 500);
        printf("  SIMULATED RESIDUAL: coil at 85 C with the board at 25 C: ready after %d ms, latch %d, REARM_REFUSED(SET_FAILED) %d\n", w, t->sim.latch,
               count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_SET_FAILED));
        CHECK(t->sim.latch || count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_SET_FAILED) == 1);
        CHECK(!(t->sim.core.faults & FATAL));
    }

    SECTION("N2: K1 closes on a set pulse but U_HOLD does not take over: K1 released, SET_INCOMPLETE, no K1_WELD");
    {
        th_t *t = th_new(1460);
        th_env(t, "{\"uhold_open\":true}");
        (void)wait_ready(t, 15000);
        uint64_t s0 = t->sim.core.ev_newest;
        press(t, 200);
        bool k1_seen = false;
        for (int k = 0; k < 600; k++) {
            th_run_silent(t, 1);
            k1_seen = k1_seen || t->sim.k1;
        }
        printf("  SIMULATED: U_HOLD open: K1 closed %d, released %d, REARM_REFUSED(SET_INCOMPLETE) %d, K1_WELD %d\n", k1_seen, !t->sim.k1,
               count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_SET_INCOMPLETE), fault(t, RRCH_FLT(K1_WELD)));
        CHECK(k1_seen && !t->sim.k1 && !t->sim.latch && count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_SET_INCOMPLETE) == 1 && !(t->sim.core.faults & FATAL));
        th_env(t, "{\"uhold_open\":false}");
        (void)wait_ready(t, 15000);
        press(t, 200);
        th_run_silent(t, 400);
        CHECK(t->sim.latch && !(t->sim.core.faults & FATAL));
        /* a K1 that really stays operated is still K1_WELD */
        th_env(t, "{\"bumper_r\":true}");
        th_run_silent(t, 200);
        th_env(t, "{\"bumper_r\":false,\"latch_weld\":true}");
        th_run_silent(t, 600);
        CHECK(fault(t, RRCH_FLT(K1_WELD)) || fault(t, RRCH_FLT(LATCH_NO_DROP)) || fault(t, RRCH_FLT(LATCH_NO_REARM)));
    }

    SECTION("N2: REARM tap phase sweep (2-40 ms x 10 phases of the IOX_D read): sets and is recognised, or is refused and reported; never fatal");
    {
        static const int taps[7] = {2, 4, 6, 8, 12, 20, 40};
        for (int mode = 0; mode < 3; mode++) { /* 0: 1 kHz window; 1: 100 Hz only; 2: 100 Hz and K1 at its 4 ms max operate time */
            th_t *t = th_new(1470u + (unsigned)mode);
            if (mode >= 1) {
                th_env(t, "{\"iox_d_period_ms\":10}"); /* the port's 100 Hz read only (no 1 kHz window) */
            }
            if (mode == 2) {
                th_env(t, "{\"k1_pickup_ms\":4}");
            }
            int set_n[7] = {0}, ref_n[7] = {0}, bad = 0;
            for (int i = 0; i < 7; i++) {
                for (int ph = 0; ph < 10; ph++) {
                    if (wait_ready(t, 20000) < 0) {
                        bad++;
                        continue;
                    }
                    th_run_silent(t, ph);
                    uint64_t s0 = t->sim.core.ev_newest;
                    press(t, taps[i]);
                    th_run_silent(t, 500);
                    bool fatal = (t->sim.core.faults & FATAL) != 0 || t->sim.n_resets != 0u; /* a supervisor reset clears the flags */
                    bool latched = t->sim.latch;
                    bool refused = count_ev(t, s0, RRCH_EV_REARM_REFUSED, -1) == 1;
                    if (fatal || latched == refused) {
                        printf("  tap %d ms phase %d (IOX_D %s): latch %d refused %d fatal %d\n", taps[i], ph, mode ? "10 ms" : "fast", latched, refused, fatal);
                        for (uint64_t q = s0 + 1u; q <= t->sim.core.ev_newest; q++) {
                            const rrch_event_t *ev = &t->sim.core.ev[(q - 1u) % RRCH_EVENTS_N];
                            printf("    ev kind %d a %d b %d t %.1f ms\n", ev->kind, (int)ev->a, (int)ev->b, (double)ev->t_us / 1e3);
                        }
                        bad++;
                        if (fatal) {
                            t = th_new(1480u + (unsigned)(mode * 100 + i * 10 + ph));
                            th_env(t, mode >= 1 ? "{\"iox_d_period_ms\":10}" : "{}");
                            th_env(t, mode == 2 ? "{\"k1_pickup_ms\":4}" : "{}");
                            continue;
                        }
                    }
                    set_n[i] += latched ? 1 : 0;
                    ref_n[i] += refused ? 1 : 0;
                    if (latched) {
                        th_env(t, "{\"bumper_r\":true}");
                        th_run_silent(t, 100);
                        th_env(t, "{\"bumper_r\":false}");
                        th_run_silent(t, 100);
                    }
                }
            }
            static const char *const mn[3] = {"IOX_D 1 kHz window, K1 3 ms", "IOX_D 100 Hz only, K1 3 ms", "IOX_D 100 Hz only, K1 4 ms"};
            printf("  SIMULATED (%s): set/refused per tap 2,4,6,8,12,20,40 ms: %d/%d %d/%d %d/%d %d/%d %d/%d %d/%d %d/%d; wrong %d\n", mn[mode], set_n[0], ref_n[0],
                   set_n[1], ref_n[1], set_n[2], ref_n[2], set_n[3], ref_n[3], set_n[4], ref_n[4], set_n[5], ref_n[5], set_n[6], ref_n[6], bad);
            CHECK(bad == 0);
            CHECK(ref_n[0] == 10); /* shorter than the operate time: refused, and reported */
            CHECK(set_n[2] + set_n[3] + set_n[4] + set_n[5] + set_n[6] == 50);
        }
    }

    SECTION("N6: loop resistance between the channel thresholds is HEAD_LOOP_OPEN + LOOP_HIGH_R, not LOOP_FAIL; a channel provably stuck is");
    {
        int bad = 0;
        for (int r = 1600; r <= 3000; r += 100) {
            th_t *t = th_new(1500u + (unsigned)r);
            th_run_silent(t, 400);
            char e[48];
            snprintf(e, sizeof e, "{\"loop_ohm\":%d}", r);
            th_env(t, e);
            th_run_silent(t, 600);
            bool fatal = (t->sim.core.faults & FATAL) != 0;
            bool open = th_req(t, "STATE", "{}") && th_has(t, "hw_inhibit_reasons", "HEAD_LOOP_OPEN");
            bool high = fault(t, RRCH_FLT(LOOP_HIGH_R));
            bool want_high = r > 1650 && r <= 2800; /* 2.9 kOhm: at the edge of the band with the analog noise */
            if (fatal || !open || (r != 2900 && high != want_high)) {
                printf("  loop %d ohm: fatal %d HEAD_LOOP_OPEN %d LOOP_HIGH_R %d\n", r, fatal, open, high);
                bad++;
            }
        }
        CHECK(bad == 0);
        /* while armed: the loop rising into the band drops the latch (not fatal) */
        th_t *t = th_new(1530);
        (void)wait_ready(t, 15000);
        press(t, 200);
        th_run_silent(t, 400);
        CHECK(t->sim.latch);
        th_env(t, "{\"loop_ohm\":2200}");
        th_run_silent(t, 300);
        CHECK(!t->sim.latch && !(t->sim.core.faults & FATAL) && fault(t, RRCH_FLT(LOOP_HIGH_R)));
        /* channel B stuck healthy, loop provably open (3.5 kOhm, channel A open): LOOP_FAIL */
        t = th_new(1531);
        th_run_silent(t, 400);
        th_env(t, "{\"loop_b_stuck_ok\":true,\"loop_ohm\":3500}");
        th_run_silent(t, 300);
        CHECK(fault(t, RRCH_FLT(LOOP_FAIL)));
        /* channel A stuck healthy (comparator), loop at 2 kOhm: LOOP_FAIL */
        t = th_new(1532);
        th_run_silent(t, 400);
        th_env(t, "{\"loop_cmp_stuck\":true,\"loop_ohm\":2000}");
        th_run_silent(t, 300);
        CHECK(fault(t, RRCH_FLT(LOOP_FAIL)) || fault(t, RRCH_FLT(LOOP_DISCREPANCY)));
    }

    SECTION("W-018: normal press-and-hold up to 1.8 s arms and stays armed; held past 2 s after the rise withdraws ARM_PERMIT");
    {
        th_t *t = th_new(1540);
        (void)wait_ready(t, 15000);
        press(t, 1800);
        th_run_silent(t, 2500);
        CHECK(t->sim.latch && !fault(t, RRCH_FLT(REARM_HELD)));
        th_env(t, "{\"bumper_r\":true}");
        th_run_silent(t, 100);
        th_env(t, "{\"bumper_r\":false}");
        (void)wait_ready(t, 15000);
        press(t, 3000);
        th_run_silent(t, 1900);
        bool held_armed = t->sim.latch;
        th_run_silent(t, 300);
        printf("  SIMULATED: REARM held 3 s: armed %d at 1.9 s, dropped %d at 2.2 s, REARM_HELD %d\n", held_armed, !t->sim.latch, fault(t, RRCH_FLT(REARM_HELD)));
        CHECK(held_armed && !t->sim.latch && fault(t, RRCH_FLT(REARM_HELD)) && !(t->sim.core.faults & FATAL));
        th_run_silent(t, 1500);
        (void)wait_ready(t, 15000);
        press(t, 200);
        th_run_silent(t, 400);
        CHECK(t->sim.latch && !fault(t, RRCH_FLT(REARM_HELD)));
    }
    return th_summary("test_rearm");
}
