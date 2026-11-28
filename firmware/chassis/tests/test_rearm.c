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
    double tc = isfinite(t->sim.k1_coil_c) ? t->sim.k1_coil_c : t->sim.temp[2] + t->sim.coil_heat_k;
    double rc = 1028.0 * (1.0 + 0.00393 * (tc - 23.0));
    double tau = rc * t->sim.cset_uf * 1e-6;
    return t->sim.vc * exp(-t->sim.k1_pickup_ms * 1e-3 / tau) / rc > 8.75e-3;
}

#define FATAL (RRCH_FLT_FATAL_MASK)

int main(void)
{
    SECTION("N1 / stage 4 G1: a press before SET_READY is refused, reported, and leaves C_SET untouched; the first press after rearm_ready sets");
    {
        th_t *t = th_new(1401);
        th_run_silent(t, 1700); /* chain closed ~1.4 s: C_SET below the 10.8 V SET_READY threshold */
        CHECK(!t->sim.core.out.lamp_rearm && t->sim.core.chain.rearm_why == RRCH_RREF_NOT_READY && th_req(t, "STATE", "{}") && !th_true(t, "rearm_ready"));
        uint64_t s0 = t->sim.core.ev_newest;
        double vc0 = t->sim.vc;
        press(t, 200);
        th_run_silent(t, 500);
        printf("  SIMULATED: C_SET %.2f V at the press (SET_READY low) -> latch %d, C_SET %.2f V after; REARM_REFUSED(NOT_READY) %d\n", vc0, t->sim.latch, t->sim.vc,
               count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_NOT_READY));
        CHECK(!t->sim.latch && t->sim.vc > vc0 && count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_NOT_READY) == 1 && !(t->sim.core.faults & FATAL));
        CHECK(th_req(t, "STATE", "{}") && th_is(t, "rearm_refusal", "NOT_READY") && !th_true(t, "rearm_ready"));
        CHECK(th_req(t, "DIAG", "{}") && th_is(t, "rearm.why", "NOT_READY") && !th_true(t, "rearm.set_ready") && th_is(t, "rearm.loop_test", "PASSED"));
        int edges = 0;
        bool l0 = t->sim.core.out.lamp_rearm;
        for (int k = 0; k < 1000; k++) { /* refused press: REARM lamp blinks fast (4 Hz) for 2 s */
            th_run_silent(t, 1);
            edges += t->sim.core.out.lamp_rearm != l0;
            l0 = t->sim.core.out.lamp_rearm;
        }
        CHECK(edges >= 7);
        th_t *u = th_new(1402); /* reviewer case on a fresh robot: presses every 0.9 s from 0.5 s after the chain closed */
        th_run_silent(u, 800);
        s0 = u->sim.core.ev_newest;
        int presses = 0, refused_ready = 0;
        bool dumped = false, set_on_first_ready = false;
        for (int k = 0; k < 10 && !u->sim.latch; k++) {
            bool ready = u->sim.core.chain.rearm_why == RRCH_RREF_NONE;
            double v0 = u->sim.vc;
            press(u, 200);
            th_run_silent(u, 900);
            presses++;
            dumped = dumped || (!u->sim.latch && u->sim.vc < v0);
            refused_ready += (ready && !u->sim.latch) ? 1 : 0;
            set_on_first_ready = set_on_first_ready || (ready && u->sim.latch);
        }
        int refused = count_ev(u, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_NOT_READY);
        printf("  SIMULATED: presses 0.9 s apart -> set at press %d, %d before reported REARM_REFUSED(NOT_READY), reservoir dumped by a refused press %d\n",
               presses, refused, dumped);
        CHECK(u->sim.latch && refused == presses - 1 && !dumped && refused_ready == 0 && !(u->sim.core.faults & FATAL));
        CHECK(th_req(u, "STATE", "{}") && rrc_json_type(&u->doc, th_get(u, "rearm_refusal")) == RRC_JT_NULL);
        (void)set_on_first_ready;
    }

    SECTION("N1: rearm_ready is never early: pack 11.6-13.4 V x board 0-50 C x C_SET 80-120 uF (coil = board), press at the first ready ms");
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
                    /* not offered at all is allowed only as SUPPLY_LOW (SET_READY never comes) or COIL_HOT (board > 45 C) */
                    bool cons = w < 0 && (why0 == RRCH_RREF_SUPPLY_LOW || why0 == RRCH_RREF_COIL_HOT);
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
        printf("  SIMULATED: %d/%d cases correct (%d never offered: SUPPLY_LOW or COIL_HOT), the rest set at the first ready ms;\n"
               "  rearm_ready came %.1f-%.1f s after the chain closed\n", ok, n, n_cons, wmin / 1e3, wmax / 1e3);
        CHECK(ok == n);
    }

    SECTION("N1: SUPPLY_LOW, CHAIN_OPEN, REARM_HELD reasons; a coil hotter than the board is reported SET_FAILED, not silent");
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

    SECTION("N2: K1 closes on a set pulse but U_HOLD does not take over: K1 released, PARTIAL, no K1_WELD");
    {
        th_t *t = th_new(1460);
        th_env(t, "{\"uhold_open\":true}");
        (void)wait_ready(t, 15000);
        uint64_t s0 = t->sim.core.ev_newest;
        press(t, 200);
        bool k1_seen = false;
        int permit_low = 0;
        double v_dip0 = 0.0, v_dip1 = 0.0;
        int ce_dead_max = 0;
        for (int k = 0; k < 600; k++) {
            th_run_silent(t, 1);
            k1_seen = k1_seen || t->sim.k1;
            if (!t->sim.core.out.arm_permit) {
                v_dip0 = permit_low == 0 ? t->sim.vc : v_dip0;
                permit_low++;
                v_dip1 = t->sim.vc;
            }
            ce_dead_max = t->sim.ce_dead_ms > ce_dead_max ? t->sim.ce_dead_ms : ce_dead_max;
        }
        printf("  SIMULATED: PARTIAL set: ARM_PERMIT low for %d ms (stage 5 H4: 30 ms), CHAIN_END dead at most %d ms (Q_SDIS starts at 41-64 ms), C_SET %.2f -> %.2f V (set-pulse dump)\n", permit_low, ce_dead_max, v_dip0, v_dip1);
        CHECK(permit_low >= 30 && permit_low <= 40 && ce_dead_max < 41);
        printf("  SIMULATED: U_HOLD open: K1 closed %d, released %d, REARM_REFUSED(PARTIAL) %d, K1_WELD %d\n", k1_seen, !t->sim.k1,
               count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_PARTIAL), fault(t, RRCH_FLT(K1_WELD)));
        CHECK(k1_seen && !t->sim.k1 && !t->sim.latch && count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_PARTIAL) == 1 && !(t->sim.core.faults & FATAL));
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

    SECTION("N2 / stage 4 G4: REARM tap phase sweep (2-40 ms x 10 phases of the IOX_D read): sets and is recognised, or is refused and reported; never fatal");
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
            int set_n[7] = {0}, ref_n[7] = {0}, bad = 0, n_short = 0, n_partial = 0, n_other = 0;
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
                    if (refused) {
                        uint8_t r = t->sim.core.chain.rearm_refusal;
                        n_short += r == RRCH_RREF_TOO_SHORT;
                        n_partial += r == RRCH_RREF_PARTIAL;
                        n_other += r != RRCH_RREF_TOO_SHORT && r != RRCH_RREF_PARTIAL;
                    }
                    if (latched) {
                        th_env(t, "{\"bumper_r\":true}");
                        th_run_silent(t, 100);
                        th_env(t, "{\"bumper_r\":false}");
                        th_run_silent(t, 100);
                    }
                }
            }
            static const char *const mn[3] = {"IOX_D as the firmware asks, K1 3 ms", "IOX_D 100 Hz, K1 3 ms", "IOX_D 100 Hz, K1 4 ms"};
            printf("  SIMULATED (%s): set/refused per tap 2,4,6,8,12,20,40 ms: %d/%d %d/%d %d/%d %d/%d %d/%d %d/%d %d/%d; wrong %d\n", mn[mode], set_n[0], ref_n[0],
                   set_n[1], ref_n[1], set_n[2], ref_n[2], set_n[3], ref_n[3], set_n[4], ref_n[4], set_n[5], ref_n[5], set_n[6], ref_n[6], bad);
            printf("    refusals: TOO_SHORT %d, PARTIAL %d, other %d\n", n_short, n_partial, n_other);
            CHECK(bad == 0);
            CHECK(ref_n[0] == 10 && ref_n[1] == 10 && n_other == 0); /* shorter than the set qualification: refused, reported */
            CHECK(set_n[4] + set_n[5] + set_n[6] == 30);             /* >= 12 ms: past the 3.2-11.2 ms qualification */
        }
    }

    SECTION("N6 / stage 4 G7: loop between the channel thresholds (1.65-2.05 kOhm) is HEAD_LOOP_OPEN + LOOP_HIGH_R, not LOOP_FAIL; a channel provably stuck is");
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
            bool want_high = r > 1650 && r <= 2000; /* G7: band up to loop.b_stuck_ohm = 2050 */
            if (fatal || !open || high != want_high) {
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
        th_env(t, "{\"loop_ohm\":1800}");
        th_run_silent(t, 300);
        CHECK(!t->sim.latch && !(t->sim.core.faults & FATAL) && fault(t, RRCH_FLT(LOOP_HIGH_R)));
        /* channel B stuck healthy, loop provably open (2.5 kOhm > 2.05 kOhm, channel A open): LOOP_FAIL */
        t = th_new(1531);
        th_run_silent(t, 400);
        th_env(t, "{\"loop_b_stuck_ok\":true,\"loop_ohm\":2500}");
        th_run_silent(t, 300);
        CHECK(fault(t, RRCH_FLT(LOOP_FAIL)));
        /* channel A stuck healthy (comparator), loop at 2 kOhm: LOOP_FAIL */
        t = th_new(1532);
        th_run_silent(t, 400);
        th_env(t, "{\"loop_cmp_stuck\":true,\"loop_ohm\":2000}");
        th_run_silent(t, 300);
        CHECK(fault(t, RRCH_FLT(LOOP_FAIL)) || fault(t, RRCH_FLT(LOOP_DISCREPANCY)));
    }

    SECTION("N3 / stage 4 G5: loop self-test before every arming; shorted loop photo-MOS U21 / U21B; SET_READY stuck");
    {
        th_t *t = th_new(1550);
        uint32_t n0 = 0;
        bool out_while_latched = false;
        for (int k = 0; k < 3; k++) { /* three armings, each preceded by a passed self-test */
            (void)wait_ready(t, 15000);
            n0 = k == 0 ? t->sim.core.chain.lt_n : n0;
            press(t, 200);
            for (int m = 0; m < 400; m++) {
                th_run_silent(t, 1);
                out_while_latched = out_while_latched || (t->sim.latch && t->sim.iox_d_out != 0u);
            }
            CHECK(t->sim.latch);
            th_env(t, "{\"bumper_r\":true}");
            th_run_silent(t, 100);
            th_env(t, "{\"bumper_r\":false}");
        }
        (void)wait_ready(t, 15000);
        printf("  SIMULATED: loop self-tests passed: %u over 3 armings (+1 pending arming); test outputs asserted while latched: %d\n",
               t->sim.core.chain.lt_n, out_while_latched);
        CHECK(t->sim.core.chain.lt_n >= 4u && n0 >= 1u && !out_while_latched && !(t->sim.core.faults & FATAL));

        t = th_new(1551); /* U21 shorted: TEST_A finds CH_N6A live with channel A open */
        th_env(t, "{\"u21_short\":true}");
        th_run_silent(t, 800);
        CHECK((fault(t, RRCH_FLT(LOOP_FAIL)) || fault(t, RRCH_FLT(LOOP_SW_SHORT))) && !t->sim.core.out.arm_permit && t->sim.core.mode == RRCH_MODE_FAULT);
        t = th_new(1552); /* U21B shorted: TEST_B finds CH_N8A live with channel B open */
        th_env(t, "{\"u21b_short\":true}");
        th_run_silent(t, 800);
        CHECK((fault(t, RRCH_FLT(LOOP_FAIL)) || fault(t, RRCH_FLT(LOOP_SW_SHORT))) && !t->sim.core.out.arm_permit && t->sim.core.mode == RRCH_MODE_FAULT);
        t = th_new(1553); /* U21 shorts while armed; a rail press: channel B drops the latch, the short is found at once */
        (void)wait_ready(t, 15000);
        press(t, 200);
        th_run_silent(t, 400);
        CHECK(t->sim.latch);
        th_env(t, "{\"u21_short\":true}");
        th_run_silent(t, 200);
        CHECK(t->sim.latch && !(t->sim.core.faults & FATAL)); /* latent while the loop is closed */
        th_env(t, "{\"loop_ohm\":1e9}");
        th_run_silent(t, 100);
        printf("  SIMULATED: U21 shorted, rail pressed: latch %d, LOOP_SW_SHORT %d\n", t->sim.latch, fault(t, RRCH_FLT(LOOP_SW_SHORT)));
        CHECK(!t->sim.latch && fault(t, RRCH_FLT(LOOP_SW_SHORT)));
        t = th_new(1554); /* SET_READY comparator stuck high: found once the chain has been open for 1 s; arming withheld, not fatal */
        th_run_silent(t, 400);
        th_env(t, "{\"set_ready_stuck\":true,\"bumper_l\":true}");
        th_run_silent(t, 1300);
        th_env(t, "{\"bumper_l\":false}");
        th_run_silent(t, 6000);
        CHECK(fault(t, RRCH_FLT(SET_STAGE_FAULT)) && !(t->sim.core.faults & FATAL) && t->sim.core.chain.rearm_why == RRCH_RREF_FAULT_OR_MODE && !t->sim.core.out.arm_permit);
    }

    SECTION("stage-4 review S5 / stage 5 H6: a 2.5 s press stays armed; a 6 s press beeps from 1 s and drops at 5 s with REARM_HELD, told to the operator");
    {
        th_t *t = th_new(1560);
        (void)wait_ready(t, 15000);
        press(t, 2500);
        th_run_silent(t, 3000);
        CHECK(t->sim.latch && !fault(t, RRCH_FLT(REARM_HELD)));
        th_env(t, "{\"bumper_r\":true}");
        th_run_silent(t, 1000);
        th_env(t, "{\"bumper_r\":false}");
        (void)wait_ready(t, 15000);
        uint64_t s0 = t->sim.core.ev_newest;
        press(t, 6000);
        th_run_silent(t, 900);
        bool beep_early = false, beep = false;
        for (int k = 0; k < 400; k++) {
            th_run_silent(t, 1);
            beep = beep || t->sim.core.out.buzzer;
        }
        (void)beep_early;
        th_run_silent(t, 3600); /* 4.9 s */
        bool armed = t->sim.latch;
        th_run_silent(t, 300);
        const rrch_event_t *last = NULL;
        for (uint64_t q = s0 + 1u; q <= t->sim.core.ev_newest; q++) {
            const rrch_event_t *e = &t->sim.core.ev[(q - 1u) % RRCH_EVENTS_N];
            last = e->kind == RRCH_EV_REARM_REFUSED ? e : last;
        }
        bool ev_ok = last && last->a == RRCH_RREF_REARM_HELD_AFTER_SET && last->b == 1;
        printf("  SIMULATED: REARM held 6 s: armed at 4.9 s %d, buzzer while held %d, dropped at 5.2 s %d, REARM_REFUSED(REARM_HELD_AFTER_SET, latch_dropped) %d\n", armed, beep, !t->sim.latch, ev_ok);
        CHECK(armed && beep && !t->sim.latch && ev_ok && th_req(t, "STATE", "{}") && th_has(t, "hw_inhibit_reasons", "REARM_HELD") &&
              !th_has(t, "hw_inhibit_reasons", "MCU_NOT_READY") && th_is(t, "rearm_refusal", "REARM_HELD_AFTER_SET") && !(t->sim.core.faults & FATAL));
        th_run_silent(t, 1500);
        (void)wait_ready(t, 15000);
        press(t, 200);
        th_run_silent(t, 400);
        CHECK(t->sim.latch);
    }

    SECTION("stage-4 review S4 / stage 5 H3: a stuck-on Q_LTA is no longer mistaken for channel B");
    {
        th_t *t = th_new(1570); /* stage 5: analog copy from LOOP_SNS: A open, analog OK, B closed */
        th_env(t, "{\"lta_stuck\":true}");
        th_run_silent(t, 800);
        uint8_t c5 = t->sim.core.chain.loop_cause;
        printf("  SIMULATED: Q_LTA stuck on, stage 5 (analog from LOOP_SNS): LOOP_DISCREPANCY %d, LOOP_FAIL %d, cause %s, ARM_PERMIT %d\n", fault(t, RRCH_FLT(LOOP_DISCREPANCY)),
               fault(t, RRCH_FLT(LOOP_FAIL)), rrch_lcause_names[c5], t->sim.core.out.arm_permit);
        CHECK(fault(t, RRCH_FLT(LOOP_DISCREPANCY)) && !(t->sim.core.faults & FATAL) && c5 == RRCH_LC_A_OPEN_OR_TEST_PATH_A && !t->sim.core.out.arm_permit &&
              th_req(t, "DIAG", "{}") && th_is(t, "loop_cause", "A_OPEN_OR_TEST_PATH_A"));
        t = th_new(1573); /* stage-4 option (analog from LOOP_F): the ambiguous case, settled by the LOOP_TEST_B pulse */
        th_env(t, "{\"lta_stuck\":true,\"analog_from_loop_f\":true}");
        th_run_silent(t, 800);
        printf("  SIMULATED: Q_LTA stuck on, stage-4 analog source: LOOP_FAIL %d, cause %s\n", fault(t, RRCH_FLT(LOOP_FAIL)), rrch_lcause_names[t->sim.core.chain.loop_cause]);
        CHECK(fault(t, RRCH_FLT(LOOP_FAIL)) && t->sim.core.chain.loop_cause == RRCH_LC_TEST_PATH_A);
        t = th_new(1571); /* channel B really stuck healthy, loop open at 2.5 kOhm */
        th_run_silent(t, 400);
        th_env(t, "{\"loop_b_stuck_ok\":true,\"loop_ohm\":2500}");
        th_run_silent(t, 400);
        CHECK(fault(t, RRCH_FLT(LOOP_FAIL)) && t->sim.core.chain.loop_cause == RRCH_LC_B_STUCK_HEALTHY);
        t = th_new(1572); /* Q_LTB shorted: B reads open, A and analog closed: fail-safe discrepancy, named so */
        th_env(t, "{\"ltb_stuck\":true}");
        th_run_silent(t, 800);
        CHECK(fault(t, RRCH_FLT(LOOP_DISCREPANCY)) && !(t->sim.core.faults & FATAL) && t->sim.core.chain.loop_cause == RRCH_LC_B_OPEN_OR_TEST_PATH_B && !t->sim.core.out.arm_permit);
    }

    SECTION("stage-4 review S3 / stage 5 H1: clamped GPB6 reads high at any 3V3; with the stage-4 divider a missed high is a readback fault, not fatal; C1 unchanged");
    {
        th_t *t0 = th_new(1579); /* stage 5 default: GPB6 high = 3V3 + 0.2 V */
        th_env(t0, "{\"v3v3\":3.45}");
        (void)wait_ready(t0, 15000);
        press(t0, 200);
        th_run_silent(t0, 400);
        CHECK(t0->sim.latch && !fault(t0, RRCH_FLT(REARM_RB_FAULT)));
        th_t *t = th_new(1580);
        th_env(t, "{\"v3v3\":3.55,\"set_rb_v\":2.80}"); /* stage-4 divider, VIH(max) 2.84 V > GPB6 2.80 V: the set line never reads closed */
        (void)wait_ready(t, 15000);
        press(t, 200);
        th_run_silent(t, 400);
        printf("  SIMULATED: GPB6 below VIH: latch %d, REARM_RB_FAULT %d, LATCH_NO_REARM %d\n", t->sim.latch, fault(t, RRCH_FLT(REARM_RB_FAULT)), fault(t, RRCH_FLT(LATCH_NO_REARM)));
        CHECK(t->sim.latch && fault(t, RRCH_FLT(REARM_RB_FAULT)) && !(t->sim.core.faults & FATAL) && th_req(t, "DIAG", "{}") && th_is(t, "rearm.rb_fault", "SET_LINE_MISSED"));
        th_env(t, "{\"bumper_r\":true}");
        th_run_silent(t, 100);
        th_env(t, "{\"bumper_r\":false}");
        th_run_silent(t, 6000);
        CHECK(!t->sim.latch && t->sim.core.chain.rearm_why == RRCH_RREF_FAULT_OR_MODE && !t->sim.core.out.arm_permit); /* the next arming is withheld */
        t = th_new(1581); /* C1: a rise with no press on either line is still fatal */
        (void)wait_ready(t, 15000);
        th_env(t, "{\"k1_fault\":\"SEAL_WELD\"}");
        th_run_silent(t, 300);
        CHECK(fault(t, RRCH_FLT(LATCH_NO_REARM)) || fault(t, RRCH_FLT(K1_WELD)) || t->sim.n_resets > 0u);
    }

    SECTION("stage-4 review S2 / stage 5 H2: RT1 beside K1 + self-heat term; COIL_HOT is a warning only (press still offered)");
    {
        th_t *t = th_new(1590); /* board 38 C, armed for 10 min: coil self-heating (10 K, tau 300 s) brings the estimate above 45 C */
        th_env(t, "{\"temp_board\":38}");
        (void)wait_ready(t, 15000);
        press(t, 200);
        th_run_silent(t, 400);
        CHECK(t->sim.latch && !fault(t, RRCH_FLT(COIL_HOT)));
        for (int k = 0; k < 600 && t->sim.latch; k++) {
            th_run_silent(t, 1000);
        }
        bool warn = fault(t, RRCH_FLT(COIL_HOT));
        printf("  SIMULATED: board 38 C, armed 10 min: coil %.1f C (emulator), estimate %.1f C, COIL_HOT %d\n", t->sim.temp[2] + t->sim.coil_heat_k, (double)t->sim.core.chain.coil_c, warn);
        CHECK(warn && t->sim.latch);
        th_env(t, "{\"bumper_r\":true}");
        th_run_silent(t, 1000);
        th_env(t, "{\"bumper_r\":false}");
        int w = wait_ready(t, 15000);
        uint64_t s0 = t->sim.core.ev_newest;
        press(t, 200);
        th_run_silent(t, 400);
        printf("  SIMULATED: after the drop: offered after %d ms with the warning, press sets %d (else reported COIL_HOT %d)\n", w, t->sim.latch,
               count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_COIL_HOT));
        CHECK(w >= 0 && (t->sim.latch || count_ev(t, s0, RRCH_EV_REARM_REFUSED, RRCH_RREF_COIL_HOT) == 1));
        t = th_new(1591); /* stage-4 RT1 position (beside the bridges, 15 K high) is selectable; the offset corrects it */
        th_env(t, "{\"temp_board\":35,\"board_ntc_rise_k\":15}");
        th_run_silent(t, 1000);
        CHECK(fault(t, RRCH_FLT(COIL_HOT)));
        t->sim.core.cfg.v[RRCH_CFG_REARM_NTC_OFFSET_K] = 15.0f;
        th_run_silent(t, 100);
        CHECK(!fault(t, RRCH_FLT(COIL_HOT)));
    }

    SECTION("lead item 6: battery approaching the re-arm limit warns first; a SUPPLY_LOW refusal says to charge or swap the pack");
    {
        th_t *t = th_new(1600);
        th_env(t, "{\"vbat\":11.9}");
        th_run_silent(t, 5000);
        CHECK(!fault(t, RRCH_FLT(BATTERY_REARM_LOW))); /* filtered >= 10 s (stage 5 H5) */
        th_run_silent(t, 6000);
        CHECK(fault(t, RRCH_FLT(BATTERY_REARM_LOW)) && !(t->sim.core.faults & FATAL));
        th_env(t, "{\"vbat\":12.6}");
        th_run_silent(t, 100);
        CHECK(!fault(t, RRCH_FLT(BATTERY_REARM_LOW)));
    }

    SECTION("W-018 / stage 5 H6: press-and-hold up to 4.5 s arms and stays armed; held past 5 s after the rise withdraws ARM_PERMIT");
    {
        th_t *t = th_new(1540);
        (void)wait_ready(t, 15000);
        press(t, 4500);
        th_run_silent(t, 5500);
        CHECK(t->sim.latch && !fault(t, RRCH_FLT(REARM_HELD)));
        th_env(t, "{\"bumper_r\":true}");
        th_run_silent(t, 1000);
        th_env(t, "{\"bumper_r\":false}");
        (void)wait_ready(t, 15000);
        press(t, 7000);
        th_run_silent(t, 4900);
        bool held_armed = t->sim.latch;
        th_run_silent(t, 300);
        printf("  SIMULATED: REARM held 7 s: armed %d at 4.9 s, dropped %d at 5.2 s, REARM_HELD %d\n", held_armed, !t->sim.latch, fault(t, RRCH_FLT(REARM_HELD)));
        CHECK(held_armed && !t->sim.latch && fault(t, RRCH_FLT(REARM_HELD)) && !(t->sim.core.faults & FATAL));
        th_run_silent(t, 2500);
        (void)wait_ready(t, 15000);
        press(t, 200);
        th_run_silent(t, 400);
        CHECK(t->sim.latch && !fault(t, RRCH_FLT(REARM_HELD)));
    }
    return th_summary("test_rearm");
}
