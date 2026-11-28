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

static bool fault(th_t *t, uint64_t flag)
{
    return (t->sim.core.faults & flag) != 0;
}

int main(void)
{
    SECTION("C1 / stage 3: K1 seal-in welded during a mission; bumper hit and released with no REARM");
    {
        th_t *t = th_new(901);
        CHECK(th_arm(t, OPM));
        th_drive_for(t, 0.10, 0, 1500, OPM);
        t->sim.k1_fault = 1;
        th_drive_for(t, 0.10, 0, 500, OPM);
        th_env(t, "{\"bumper_l\":true}");
        th_drive_for(t, 0.10, 0, 600, OPM);
        CHECK(!t->sim.latch && fault(t, RRCH_FLT(K1_WELD))); /* LATCH_NC_RB stays low with the latch down */
        double x1 = t->sim.x;
        th_env(t, "{\"bumper_l\":false}");
        int acc = accepted_during(t, 0.10, 5000);
        printf("  SIMULATED: after release without REARM: K1 re-closed=%d, RUN_HD=%d (U_HOLD), %d DRIVE accepted, moved %.1f mm, mode %s\n", t->sim.k1, t->sim.run_hd, acc,
               (t->sim.x - x1) * 1e3, rrch_mode_names[t->sim.core.mode]);
        CHECK(acc == 0 && fabs(t->sim.x - x1) < 0.002 && !t->sim.run_hd);
    }
    SECTION("C1 / stage 3: K1 welded from power-up: ARM_PERMIT never raised, K1_WELD; REARM set line shorted: REARM_DISCREPANCY");
    {
        th_t *t = th_new(911);
        t->sim.k1_fault = 1;
        th_run_silent(t, 300);
        (void)th_req(t, "HELLO", "{}");
        (void)th_req(t, "SET_OP_MODE", "{\"op_mode\":\"" OPM "\"}");
        th_run(t, 300);
        CHECK(fault(t, RRCH_FLT(K1_WELD)) && !t->sim.core.out.arm_permit && !t->sim.latch);
        CHECK(accepted_during(t, 0.10, 1000) == 0);
        t = th_new(912);
        th_run_silent(t, 400);
        th_env(t, "{\"rearm_set_short\":true}"); /* W-018 short / welded set contact: one edge, then a held line */
        th_run_silent(t, 400);
        CHECK(fault(t, RRCH_FLT(REARM_DISCREPANCY)) && !t->sim.latch && !t->sim.core.out.arm_permit);
        th_env(t, "{\"press\":\"REARM\"}");
        th_run_silent(t, 400);
        CHECK(!t->sim.latch); /* no edge on the shorted set line: the set stage cannot fire */
    }
    SECTION("M6 / stage 3: RUN_12V shorted to a supply: relays stay off (U_LS), RUN_SHORT, bridges asleep");
    {
        th_t *t = th_new(920);
        t->sim.run12_short = true;
        bool awake = false, relay = false;
        for (int ms = 0; ms < 600; ms++) {
            th_run_silent(t, 1);
            awake = awake || (t->sim.core.out.bridge_awake && t->sim.run_hd);
            relay = relay || t->sim.relay[0] || t->sim.relay[1];
        }
        CHECK(fault(t, RRCH_FLT(RUN_SHORT)) && !awake && !relay && t->sim.vmot < 1.0);
        (void)th_req(t, "HELLO", "{}");
        CHECK(accepted_during(t, 0.10, 1000) == 0);
    }
    SECTION("C2 / stage 3: channel A stuck healthy, rail pressed while driving -> channel B drops the latch, LOOP_FAIL");
    {
        th_t *t = th_new(902);
        CHECK(th_arm(t, OPM));
        th_drive_for(t, 0.10, 0, 1500, OPM);
        t->sim.loop_cmp_stuck = true;
        th_drive_for(t, 0.10, 0, 300, OPM);
        double x0 = t->sim.x;
        t->sim.loop_ohm = 1e9;
        th_run_silent(t, 60);
        /* stage 3: channel B (U46/U21B) opens the chain in hardware; A (stuck healthy) vs B disagreement with the
         * analog copy reading open is LOOP_FAIL */
        CHECK(!t->sim.latch && !t->sim.core.out.arm_permit && fault(t, RRCH_FLT(LOOP_FAIL)));
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
    SECTION("stage 3 F1-F6: IOX_D pattern, K1 pole B weld, REARM line discrepancy, channel B stuck open, U_HOLD short (not visible)");
    {
        th_t *t = th_new(950);
        th_run_silent(t, 400);
        CHECK(t->sim.core.out.arm_permit && !fault(t, RRCH_FLT(IOX_D)));
        th_env(t, "{\"iox_d_bad_pattern\":true}"); /* P4..P7 not 1,0,0,0: IOX_D unknown -> arming withheld */
        th_run_silent(t, 100);
        CHECK(fault(t, RRCH_FLT(IOX_D)) && !t->sim.core.out.arm_permit);
        th_env(t, "{\"iox_d_bad_pattern\":false}");
        th_run_silent(t, 200);
        CHECK(!fault(t, RRCH_FLT(IOX_D)) && t->sim.core.out.arm_permit);
        th_env(t, "{\"k1_run_short\":true}"); /* K1_RUN live with the latch down (pole B welded / K1_RUN fed) */
        th_run_silent(t, 100);
        CHECK(fault(t, RRCH_FLT(K1_WELD)) && !t->sim.core.out.arm_permit);

        t = th_new(951);
        th_run_silent(t, 400);
        th_env(t, "{\"rearm_aux_short\":true}");
        th_run_silent(t, 400);
        CHECK(fault(t, RRCH_FLT(REARM_DISCREPANCY)) && !t->sim.core.out.arm_permit && !(t->sim.core.faults & RRCH_FLT_FATAL_MASK));

        t = th_new(952); /* channel B stuck open: fails safe (chain open), LOOP_DISCREPANCY, not fatal */
        th_run_silent(t, 400);
        th_env(t, "{\"loop_b_stuck_open\":true}");
        th_run_silent(t, 300);
        CHECK(fault(t, RRCH_FLT(LOOP_DISCREPANCY)) && !fault(t, RRCH_FLT(LOOP_FAIL)) && !t->sim.core.out.arm_permit);

        t = th_new(953); /* U_HOLD shorted: not observable by firmware (latent); K1 still holds the barrier */
        CHECK(th_arm(t, OPM));
        th_env(t, "{\"uhold_short\":true}");
        th_run(t, 500);
        CHECK(t->sim.latch && !(t->sim.core.faults & RRCH_FLT_FATAL_MASK));
        th_env(t, "{\"bumper_r\":true}");
        th_run(t, 300);
        CHECK(!t->sim.latch);
        printf("  SIMULATED: U_HOLD shorted: no firmware indication (latent); the latch still drops through K1\n");
    }
    SECTION("thermal policy (contract power.thermal_policy): -10 C floor on pack power, +5 C on external power, HEATER -10..30");
    {
        th_t *t = th_new(960);
        th_env(t, "{\"temp_bay\":-15,\"temp_pack\":-15}");
        th_run(t, 3000);
        CHECK(t->sim.core.htr_active_sp == -10.0f && t->sim.core.htr_duty > 0.0f);
        th_env(t, "{\"temp_bay\":-8,\"temp_pack\":-8}");
        th_run(t, 2500);
        CHECK(t->sim.core.htr_duty == 0.0f);
        th_env(t, "{\"chg_plug\":true}"); /* external supply present: charging pre-heat to +5 C */
        th_run(t, 2500);
        CHECK(t->sim.core.htr_active_sp == 5.0f && t->sim.core.htr_duty > 0.0f);
        CHECK(th_req(t, "HELLO", "{}") && th_req(t, "HEATER", "{\"chassis_setpoint_c\":-10}"));
        CHECK(!th_req(t, "HEATER", "{\"chassis_setpoint_c\":-11}") && th_status(t, "BAD_ARG"));
        CHECK(th_req(t, "HEATER", "{\"chassis_setpoint_c\":12}"));
        th_run(t, 100);
        CHECK(th_req(t, "STATE", "{}") && th_num(t, "heater.active_setpoint_c") == 12.0);
    }
    SECTION("section 6.1 residual single faults (stage 3): what still gets through - documents a limit, not a safety claim");
    {
        /* 1. welded head-rail switch, 3. LOOP_SNS leakage: the loop reads healthy on every channel */
        static const char *const loopf[2] = {"{\"rail_weld\":true}", "{\"loop_sns_leak\":true}"};
        static const char *const loopn[2] = {"welded rail switch", "LOOP_SNS leakage"};
        for (int k = 0; k < 2; k++) {
            th_t *t = th_new(940 + (uint64_t)k);
            CHECK(th_arm(t, OPM));
            th_drive_for(t, 0.10, 0, 1500, OPM);
            th_env(t, loopf[k]);
            double x0 = t->sim.x;
            t->sim.loop_ohm = 1e9; /* rail pressed */
            th_drive_for(t, 0.10, 0, 2000, OPM);
            printf("  SIMULATED RESIDUAL (%s): rail pressed for 2 s, latch %d, mode %s, moved %.0f mm - no barrier at the chassis\n", loopn[k], t->sim.latch,
                   rrch_mode_names[t->sim.core.mode], (t->sim.x - x0) * 1e3);
            CHECK(t->sim.latch && t->sim.core.mode == RRCH_MODE_MOVING && t->sim.x - x0 > 0.15);
        }
        /* 2. welded body bumper switch */
        {
            th_t *t = th_new(942);
            CHECK(th_arm(t, OPM));
            th_drive_for(t, -0.05, 0, 1500, OPM);
            th_env(t, "{\"bumper_l_weld\":true,\"bumper_l\":true}");
            double x0 = t->sim.x;
            th_drive_for(t, -0.05, 0, 2000, OPM);
            printf("  SIMULATED RESIDUAL (welded bumper L): pressed for 2 s while reversing, moved %.0f mm - only the rear ToF remains\n", (x0 - t->sim.x) * 1e3);
            CHECK(t->sim.latch && x0 - t->sim.x > 0.05);
        }
        /* 4a. RUN_HD shorted to a supply: relays, VMOT and the U9 gate are live without a latch */
        {
            th_t *t = th_new(943);
            t->sim.run_hd_short = true;
            bool awake = false;
            for (int ms = 0; ms < 1500; ms++) {
                th_run_silent(t, 1);
                awake = awake || (t->sim.core.out.bridge_awake && t->sim.run_hd);
            }
            printf("  SIMULATED RESIDUAL (RUN_HD short): relays %d/%d, VMOT %.1f V, firmware %s (RUN_SHORT %d), bridges ever awake %d - only E-stop pole B and DRV_NSLEEP remain\n",
                   t->sim.relay[0], t->sim.relay[1], t->sim.vmot, rrch_mode_names[t->sim.core.mode], fault(t, RRCH_FLT(RUN_SHORT)), awake);
            CHECK(t->sim.relay[0] && t->sim.vmot > 10.0 && !awake && (fault(t, RRCH_FLT(RUN_SHORT)) || fault(t, RRCH_FLT(LATCH_NO_REARM))));
            th_env(t, "{\"estop\":true}");
            th_run_silent(t, 30);
            CHECK(!t->sim.relay[0]); /* E-stop pole B still removes the relay coil return */
        }
        /* 4b. CHAIN_END shorted to a supply during a mission: a bumper hit no longer drops the latch */
        {
            th_t *t = th_new(944);
            CHECK(th_arm(t, OPM));
            th_drive_for(t, 0.10, 0, 2500, OPM);
            th_env(t, "{\"chain_end_short\":true}");
            double x0 = t->sim.x;
            th_env(t, "{\"bumper_l\":true}");
            th_drive_for(t, 0.10, 0, 1000, OPM);
            printf("  SIMULATED RESIDUAL (CHAIN_END short): bumper hit, latch still %d (no hardware barrier), firmware %s (CHAIN_IMPLAUSIBLE %d, LATCH_NO_DROP %d), bridges asleep -> moved %.1f mm\n",
                   t->sim.latch, rrch_mode_names[t->sim.core.mode], fault(t, RRCH_FLT(CHAIN_IMPLAUSIBLE)), fault(t, RRCH_FLT(LATCH_NO_DROP)), (t->sim.x - x0) * 1e3);
            CHECK(t->sim.latch && (t->sim.core.faults & RRCH_FLT_FATAL_MASK) && !t->sim.core.out.bridge_awake && t->sim.x - x0 < 0.05);
        }
        /* 5. W-018 crush: a supply on both REARM contact lines at once arms the robot once, like a press */
        {
            th_t *t = th_new(945);
            th_run_silent(t, 300);
            (void)th_req(t, "HELLO", "{}");
            (void)th_req(t, "SET_OP_MODE", "{\"op_mode\":\"" OPM "\"}");
            th_run(t, 6500); /* C_SET charged */
            th_env(t, "{\"rearm_aux_short\":true,\"rearm_set_short\":true}");
            th_run(t, 400);
            bool armed_once = t->sim.latch;
            /* a REARM contact still closed 5 s after the latch rose withdraws ARM_PERMIT (REARM_HELD; stage 5 H6) */
            th_run(t, 4400); /* stage 5 H6: dropped 5 s after the rise */
            bool still = t->sim.latch;
            th_run(t, 400);
            CHECK(armed_once && still && !t->sim.latch && fault(t, RRCH_FLT(REARM_HELD)) && th_req(t, "STATE", "{}") && th_has(t, "hw_inhibit_reasons", "REARM_HELD"));
            th_env(t, "{\"bumper_r\":true}");
            th_run(t, 200);
            th_env(t, "{\"bumper_r\":false}");
            th_run(t, 3500);
            printf("  SIMULATED RESIDUAL (W-018 crush, both REARM lines live): armed by itself %d; after a bumper drop re-armed %d, REARM_HELD %d\n", armed_once, t->sim.latch,
                   fault(t, RRCH_FLT(REARM_HELD)));
            CHECK(armed_once && !t->sim.latch && fault(t, RRCH_FLT(REARM_HELD)));
        }
    }
    return th_summary("test_review");
}
