/* Regression tests for docs/reviews/REVIEW_traction_inhibit.md (C1, C2, M1, M2, M6, m1, m3, m7) on the
 * emulator's netlist-aligned chain model with the reviewer's fault models. SIMULATED. Each test shows that
 * the firmware fails safe: no DRIVE accepted, ARM_PERMIT withdrawn, the latch (RUN_12V) removed. */
#include <math.h>
#include <string.h>

#include "harness.h"

#define OPM "SURVEY_UNATTENDED"

static int accepted_during(th_t *t, double v, int ms)
{
    int n = 0;
    for (int k = 0; k < ms; k += 20) {
        n += th_drive(t, v, 0, 200, OPM) ? 1 : 0;
        th_run_silent(t, 19);
    }
    return n;
}

static bool fault(th_t *t, uint32_t flag)
{
    return (t->sim.core.faults & flag) != 0;
}

int main(void)
{
    SECTION("C1: K1 seal-in welded during a mission; bumper hit and released with no REARM");
    {
        th_t *t = th_new(901);
        CHECK(th_arm(t, OPM));
        th_drive_for(t, 0.10, 0, 1500, OPM);
        t->sim.k1_fault = 1;
        th_drive_for(t, 0.10, 0, 500, OPM);
        th_env(t, "{\"bumper_l\":true}");
        th_drive_for(t, 0.10, 0, 600, OPM);
        CHECK(!t->sim.latch && t->sim.core.mode == RRCH_MODE_HW_INHIBIT);
        double x1 = t->sim.x;
        th_env(t, "{\"bumper_l\":false}");
        int acc = accepted_during(t, 0.10, 5000);
        printf("  SIMULATED: after release without REARM: %d DRIVE accepted, moved %.1f mm, mode %s\n", acc, (t->sim.x - x1) * 1e3, rrch_mode_names[t->sim.core.mode]);
        CHECK(acc == 0 && fabs(t->sim.x - x1) < 0.002);
        CHECK(fault(t, RRCH_FLT(LATCH_NO_REARM)) || t->sim.n_resets > 0u);
        CHECK(!t->sim.run12 || t->sim.mcu_in_reset || !t->sim.core.out.bridge_awake);
    }
    SECTION("C1: K1 welded / K1_SET shorted to V12_AUX from power-up: never usable, brake test cannot pass it");
    for (int m = 1; m <= 2; m++) {
        th_t *t = th_new(910 + (uint64_t)m);
        t->sim.k1_fault = m;
        th_run_silent(t, 300);
        (void)th_req(t, "HELLO", "{}");
        (void)th_req(t, "SET_OP_MODE", "{\"op_mode\":\"" OPM "\"}");
        th_run(t, 300);
        CHECK(fault(t, RRCH_FLT(LATCH_NO_REARM)) || t->sim.n_resets > 0u);
        (void)th_rearm_sw(t);
        CHECK(!th_req(t, "BRAKE_TEST", "{}") || !th_true(t, "passed"));
        double x0 = t->sim.x;
        int acc = accepted_during(t, 0.10, 3000);
        CHECK(acc == 0 && fabs(t->sim.x - x0) < 1e-4);
    }
    SECTION("M6: RUN_12V shorted to a supply on the board: latch readback high at boot -> FAULT, bridges kept asleep");
    {
        th_t *t = th_new(920);
        t->sim.run12_short = true;
        bool awake = false;
        for (int ms = 0; ms < 400; ms++) {
            th_run_silent(t, 1);
            awake = awake || t->sim.core.out.bridge_awake;
        }
        CHECK(fault(t, RRCH_FLT(LATCH_NO_REARM)) || t->sim.n_resets > 0u);
        CHECK(!awake);
        (void)th_req(t, "HELLO", "{}");
        CHECK(accepted_during(t, 0.10, 1000) == 0);
    }
    SECTION("C2: head-loop comparator stuck healthy, rail pressed while driving -> permit withdrawn, LOOP_FAIL");
    {
        th_t *t = th_new(902);
        CHECK(th_arm(t, OPM));
        th_drive_for(t, 0.10, 0, 1500, OPM);
        t->sim.loop_cmp_stuck = true;
        th_drive_for(t, 0.10, 0, 300, OPM);
        double x0 = t->sim.x;
        t->sim.loop_ohm = 1e9;
        th_run_silent(t, 20);
        CHECK(!t->sim.core.out.arm_permit && fault(t, RRCH_FLT(LOOP_FAIL)) && (t->sim.core.sw_latched & RRCH_SW(STOP_ESCALATED)));
        int acc = accepted_during(t, 0.10, 3000);
        printf("  SIMULATED: rail open with the comparator stuck: travel after the press %.1f mm, %d DRIVE accepted\n", (t->sim.x - x0) * 1e3, acc);
        CHECK(acc == 0 && t->sim.x - x0 < 0.010 && !t->sim.run12);
    }
    SECTION("C2 / m4: a 3 ms rail press (shorter than K1 release) is not filtered out: the latch is fully dropped, no fault");
    {
        th_t *t = th_new(903);
        CHECK(th_arm(t, OPM));
        th_drive_for(t, 0.10, 0, 1500, OPM);
        t->sim.loop_ohm = 1e9;
        th_run_silent(t, 3);
        t->sim.loop_ohm = 1000.0;
        th_run_silent(t, 100);
        /* U21 opens CHAIN_END for 3 ms: RUN_12V dips but K1 (4 ms release) would hold; the firmware sees the dip
         * and keeps ARM_PERMIT low for 50 ms, so K1 really releases and nothing comes back without REARM */
        CHECK(!t->sim.latch && !(t->sim.core.faults & RRCH_FLT_FATAL_MASK) && (t->sim.core.chain.hw_latched & RRCH_HW(HEAD_LOOP_OPEN)));
        CHECK(!th_drive(t, 0.10, 0, 200, OPM));
        /* local REARM brings it back (permit returns 1 s after coming to rest) */
        th_run(t, 1500);
        th_env(t, "{\"press\":\"REARM\"}");
        th_run(t, 400);
        CHECK(th_mode(t, "ARMED_IDLE"));
    }
    SECTION("C2: comparator stuck, rail pressed while the latch is down -> LOOP_DISCREPANCY withholds ARM_PERMIT");
    {
        th_t *t = th_new(904);
        th_run_silent(t, 400);
        t->sim.loop_cmp_stuck = true;
        t->sim.loop_ohm = 1e9;
        th_run_silent(t, 300);
        CHECK(fault(t, RRCH_FLT(LOOP_DISCREPANCY)) && !t->sim.core.out.arm_permit);
        th_env(t, "{\"press\":\"REARM\"}");
        th_run_silent(t, 300);
        CHECK(!t->sim.latch);
    }
    SECTION("M1: stage-2 board (C_SET back-feed, chain.backfeed_ms 12 s) - brake test long after REARM and openings give no false fault");
    {
        th_t *t = th_new(905);
        t->sim.cset_diode = false;
        t->sim.core.cfg.v[RRCH_CFG_CHAIN_BACKFEED_MS] = 12000.0f;
        CHECK(th_arm(t, OPM));
        th_run(t, 4300);
        CHECK(th_req(t, "BRAKE_TEST", "{}") && th_true(t, "passed"));
        (void)th_req(t, "TIME", "{}");
        CHECK(!(t->sim.core.faults & RRCH_FLT_FATAL_MASK) && t->sim.n_resets == 0u);
        printf("  SIMULATED: C_SET at %.1f V; brake test 4.3 s after arming passed without PERMIT_STUCK_ON\n", t->sim.vc);
        th_env(t, "{\"press\":\"REARM\"}");
        th_run(t, 4000);
        CHECK(th_mode(t, "ARMED_IDLE"));
        th_env(t, "{\"bumper_l\":true}");
        th_run(t, 1500);
        th_env(t, "{\"bumper_l\":false}");
        th_run(t, 300);
        th_env(t, "{\"mode_run\":false}");
        th_run(t, 500);
        th_env(t, "{\"mode_run\":true}");
        th_run(t, 12500);
        CHECK(!(t->sim.core.faults & RRCH_FLT_FATAL_MASK) && t->sim.n_resets == 0u);
        th_env(t, "{\"press\":\"REARM\"}");
        th_run(t, 400);
        CHECK(th_mode(t, "ARMED_IDLE") || th_mode(t, "PROTECTIVE_STOP"));
    }
    SECTION("m3: REARM pressed 100 ms before the chain closes is refused; a later press works");
    {
        th_t *t = th_new(906);
        th_run_silent(t, 400);
        CHECK(th_req(t, "HELLO", "{}"));
        th_env(t, "{\"bumper_r\":true}");
        th_run(t, 300);
        th_env(t, "{\"press\":\"REARM\",\"press_ms\":150}");
        th_run_silent(t, 100);
        th_env(t, "{\"bumper_r\":false}");
        th_run_silent(t, 400);
        CHECK(!t->sim.latch && !(t->sim.core.faults & RRCH_FLT_FATAL_MASK));
        th_env(t, "{\"press\":\"REARM\"}");
        th_run(t, 400);
        CHECK(t->sim.latch && !(t->sim.core.faults & RRCH_FLT_FATAL_MASK));
    }
    SECTION("rows 42/43: REARM held > 2 s -> REARM_HELD, ARM_PERMIT withheld until released");
    {
        th_t *t = th_new(907);
        th_run_silent(t, 400);
        th_env(t, "{\"bumper_r\":true,\"press\":\"REARM\",\"press_ms\":4000}");
        th_run_silent(t, 2500);
        CHECK(fault(t, RRCH_FLT(REARM_HELD)) && !t->sim.core.out.arm_permit);
        th_env(t, "{\"bumper_r\":false}");
        th_run_silent(t, 1700);
        CHECK(!t->sim.latch && !fault(t, RRCH_FLT(REARM_HELD)));
        th_run_silent(t, 200);
        th_env(t, "{\"press\":\"REARM\"}");
        th_run_silent(t, 400);
        CHECK(t->sim.latch);
    }
    SECTION("M2/M3: an expander pin driving a comparator node, or a tap pin with a pull, is a FAULT");
    {
        th_t *t = th_new(908);
        th_run_silent(t, 400);
        th_env(t, "{\"iox_drive_loop\":true}");
        th_run_silent(t, 5);
        CHECK(fault(t, RRCH_FLT(PIN_CONFIG)) && t->sim.core.mode == RRCH_MODE_FAULT && !t->sim.core.out.arm_permit);
        t = th_new(909);
        th_run_silent(t, 400);
        th_env(t, "{\"io_cfg_fault\":true}");
        th_run_silent(t, 5);
        CHECK(fault(t, RRCH_FLT(PIN_CONFIG)));
    }
    SECTION("m7: two failed IOX_B reads while driving do not drop the latch; 80 ms of failures do");
    {
        th_t *t = th_new(930);
        CHECK(th_arm(t, OPM));
        th_drive_for(t, 0.10, 0, 1500, OPM);
        t->sim.iox_b_fail = true;
        th_drive_for(t, 0.10, 0, 25, OPM);
        t->sim.iox_b_fail = false;
        th_drive_for(t, 0.10, 0, 200, OPM);
        CHECK(t->sim.latch && t->sim.core.mode == RRCH_MODE_MOVING);
        t->sim.iox_b_fail = true;
        th_drive_for(t, 0.10, 0, 100, OPM);
        CHECK(!t->sim.core.out.arm_permit && fault(t, RRCH_FLT(IOX_B)));
    }
    SECTION("m1: VMOT bleed with +20 % bulk capacitance from a full pack still passes the brake test");
    {
        th_t *t = th_new(931);
        th_env(t, "{\"vmot_tau_s\":0.992,\"vbat\":14.6}");
        CHECK(th_arm(t, OPM));
        double d = th_num(t, "vmot_decay_ms");
        (void)d;
        CHECK(t->sim.core.bt.passed_since_boot);
        printf("  SIMULATED: VMOT decay to 1 V with tau 0.99 s from 14.6 V: %d ms (limit 3500)\n", (int)t->sim.core.bt.vmot_decay_ms);
    }
    return th_summary("test_review");
}
