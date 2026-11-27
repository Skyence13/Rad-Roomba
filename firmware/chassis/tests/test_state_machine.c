/* Mode state machine, chain reasons, software protective-stop latch, command acceptance, TTL,
 * re-arm rules, head power, heater, configuration, events, watchdog cross-checks.
 * Everything runs through the real protocol server on the host plant model (SIMULATED). */
#include <math.h>
#include <string.h>

#include "harness.h"

#define OPM "COMMISSIONING"

static bool diag_has(th_t *t, const char *list, const char *name)
{
    return th_req(t, "DIAG", "{}") && th_has(t, list, name);
}

static th_t *armed(uint64_t seed)
{
    th_t *t = th_new(seed);
    CHECK(th_arm(t, OPM));
    return t;
}

static void moving(th_t *t, double v, double w)
{
    for (int k = 0; k < 200 && t->sim.core.drive.motion != RRCH_MOTION_RUN; k++) {
        (void)th_drive(t, v, w, 200, OPM);
        th_run_silent(t, 19);
    }
    th_drive_for(t, v, w, 1000, OPM);
}

/* ------------------------------------------------------------------------------------------ */
static void test_boot_and_hello(void)
{
    SECTION("boot, HELLO, TIME, session rules");
    th_t *t = th_new(1);
    CHECK(t->sim.core.mode == RRCH_MODE_BOOT && !t->sim.core.out.arm_permit && !t->sim.core.out.bridge_awake);
    CHECK(th_req(t, "STATE", "{}") && th_is(t, "mode", "BOOT"));
    CHECK(!th_drive(t, 0, 0, 200, OPM) && th_is(t, "reject_reason", "NO_SESSION"));
    CHECK(!th_req(t, "SET_OP_MODE", "{\"op_mode\":\"GUIDED\"}") && th_status(t, "REJECTED") && th_is(t, "reason", "NO_SESSION"));
    th_run_silent(t, 300);
    CHECK(th_mode(t, "STANDBY") && !th_true(t, "rearm_ready") && th_true(t, "chain.ARM_PERMIT") && !th_true(t, "hw_latch"));
    /* "ready" only once the conservative C_SET model says a press will set K1 (round 4 N1; T11): about 5 s of
     * CHAIN_END live at 12.6 V and 25 C, never before 3 s */
    th_run_silent(t, 3000);
    CHECK(th_mode(t, "STANDBY") && !th_true(t, "rearm_ready") && rrc_json_type(&t->doc, th_get(t, "rearm_refusal")) == RRC_JT_NULL);
    for (int k = 0; k < 80 && !t->sim.core.out.lamp_rearm && t->sim.core.chain.rearm_why != RRCH_RREF_NONE; k++) {
        th_run_silent(t, 100);
    }
    CHECK(th_mode(t, "STANDBY") && th_true(t, "rearm_ready"));
    CHECK(th_is(t, "op_mode", "SERVICE"));
    CHECK(th_req(t, "HELLO", "{}"));
    CHECK(th_is(t, "proto", "RR-CHS 1.0") && th_num(t, "caps.encoder_cpr") == 9600 && th_num(t, "caps.max_v_mps") == 0.2 && th_num(t, "caps.track_nom_m") == 0.27 && th_num(t, "caps.wheel_radius_nom_m") == 0.052 && th_num(t, "session") == 1);
    CHECK(th_is(t, "reset.cause", "POWER_ON") && th_num(t, "reset.boot_count") == 1 && th_is(t, "config.source", "DEFAULTS"));
    char boot[40];
    CHECK(rrc_json_str_copy(&t->doc, th_get(t, "boot_id"), boot, sizeof boot) == 36 && rrc_uuid_is_canonical(boot));
    CHECK(th_req(t, "TIME", "{}"));
    double rx = th_num(t, "rx_us"), tx = th_num(t, "tx_us");
    CHECK(rx > 0 && tx >= rx && tx - rx <= 2000 && (double)t->sim.t_us >= tx && (double)t->sim.t_us - tx <= 2000);
    CHECK(!th_drive(t, 0, 0, 200, OPM) && th_is(t, "reject_reason", "STANDBY"));
    CHECK(!th_req(t, "NOPE", "{}") && th_status(t, "UNSUPPORTED"));
    CHECK(!th_req(t, "DRIVE", "{\"seq\":1}") && th_status(t, "BAD_ARG"));
    CHECK(!th_req(t, "DRIVE", "{\"seq\":9,\"v_mps\":0.1,\"w_radps\":0,\"ttl_ms\":251,\"op_mode\":\"GUIDED\"}") && th_status(t, "BAD_ARG"));
    /* a record with a bad CRC or broken JSON gets no reply at all */
    const char *bad = "{\"type\":\"REQ\",\"v\":\"1.0\",\"id\":77,\"op\":\"TIME\",\"args\":{}}\t00000000\n";
    sim_host_write(&t->sim, (const uint8_t *)bad, strlen(bad));
    th_run_silent(t, 50);
    uint8_t tmp[8];
    CHECK(sim_host_read(&t->sim, tmp, sizeof tmp) == 0);
}

/* ------------------------------------------------------------------------------------------ */
static void chain_case(const char *open_env, const char *close_env, const char *reason, const char *mode_while_open)
{
    th_t *t = armed(100);
    moving(t, 0.10, 0.0);
    double x_before;
    th_env(t, open_env);
    th_run(t, 150);
    CHECK(th_req(t, "STATE", "{}"));
    if (!th_is(t, "mode", mode_while_open) || !th_has(t, "hw_inhibit_reasons", reason)) {
        printf("  (case %s: mode/reason not as documented)\n", reason);
    }
    CHECK(th_is(t, "mode", mode_while_open));
    CHECK(th_has(t, "hw_inhibit_reasons", reason));
    CHECK(!th_true(t, "hw_latch") && !th_true(t, "rearm_ready"));
    CHECK(diag_has(t, "hw_active", reason));
    CHECK(!th_drive(t, 0.1, 0, 200, OPM) && th_is(t, "reject_reason", mode_while_open) && th_has(t, "stops.hw", reason));
    th_run(t, 600);
    CHECK(fabs(t->sim.v) < 1e-3 && !t->sim.core.out.bridge_awake);
    /* cause removed: nothing clears by itself */
    th_env(t, close_env);
    th_run(t, 6500); /* C_SET model: a press will set only after ~5 s of closed chain (round 4 N1) */
    CHECK(th_req(t, "STATE", "{}") && th_is(t, "mode", "HW_INHIBIT") && th_has(t, "hw_inhibit_reasons", reason));
    CHECK(th_true(t, "rearm_ready") && !th_true(t, "hw_latch"));
    CHECK(!diag_has(t, "hw_active", reason));
    /* REARM_SW cannot set the hardware latch */
    CHECK(th_rearm_sw(t) && !th_true(t, "hw_latch"));
    th_run(t, 300);
    CHECK(th_mode(t, "HW_INHIBIT") && !t->sim.latch);
    CHECK(!th_drive(t, 0.1, 0, 200, OPM) && th_is(t, "reject_reason", "HW_INHIBIT"));
    /* only the local button re-arms; no queued motion follows */
    x_before = t->sim.x;
    th_env(t, "{\"press\":\"REARM\"}");
    th_run(t, 400);
    CHECK(th_mode(t, "ARMED_IDLE") && th_true(t, "hw_latch") && th_len(t, "hw_inhibit_reasons") == 0);
    th_run(t, 800);
    CHECK(fabs(t->sim.x - x_before) < 1e-4 && th_mode(t, "ARMED_IDLE"));
}

static void test_chain_elements(void)
{
    SECTION("every chain element: documented mode and reason, nothing auto-clears, REARM_SW cannot set the latch");
    chain_case("{\"mode_run\":false}", "{\"mode_run\":true}", "MODE_NOT_RUN", "HW_INHIBIT");
    chain_case("{\"estop\":true}", "{\"estop\":false}", "ESTOP", "HW_INHIBIT");
    chain_case("{\"hands_on\":true}", "{\"hands_on\":false}", "HANDS_ON", "HW_INHIBIT");
    chain_case("{\"chg_cover_open\":true}", "{\"chg_cover_open\":false}", "CHARGER", "SERVICE_CHARGE");
    chain_case("{\"chg_plug\":true}", "{\"chg_plug\":false}", "CHARGER", "SERVICE_CHARGE");
    chain_case("{\"head_docked\":false}", "{\"head_docked\":true}", "HEAD_UNDOCKED", "HW_INHIBIT");
    chain_case("{\"loop_ohm\":1e9}", "{\"loop_ohm\":1000}", "HEAD_LOOP_OPEN", "HW_INHIBIT");
    chain_case("{\"loop_ohm\":50}", "{\"loop_ohm\":1000}", "HEAD_LOOP_SHORT", "HW_INHIBIT");
    chain_case("{\"pres_ohm\":1e9,\"loop_ohm\":1e9}", "{\"pres_ohm\":4700,\"loop_ohm\":1000}", "J1_ABSENT", "HW_INHIBIT");
    chain_case("{\"pres_ohm\":1137}", "{\"pres_ohm\":4700}", "LAB_KEY", "LAB");
    chain_case("{\"pres_ohm\":1500}", "{\"pres_ohm\":4700}", "LAB_KEY", "LAB");
    chain_case("{\"bumper_l\":true}", "{\"bumper_l\":false}", "BODY_BUMPER", "HW_INHIBIT");
    chain_case("{\"bumper_r\":true}", "{\"bumper_r\":false}", "BODY_BUMPER", "HW_INHIBIT");

    SECTION("charger has priority over LAB; undocked + LAB code = two independent openings");
    {
        th_t *t = armed(101);
        th_env(t, "{\"pres_ohm\":1137,\"head_docked\":false}");
        th_run(t, 150);
        CHECK(th_mode(t, "LAB") && th_has(t, "hw_inhibit_reasons", "LAB_KEY") && th_has(t, "hw_inhibit_reasons", "HEAD_UNDOCKED"));
        CHECK(!th_true(t, "chain.ARM_PERMIT") && th_is(t, "head_presence", "HEAD_VIA_LAB_EXTENSION"));
        th_env(t, "{\"chg_plug\":true}");
        th_run(t, 150);
        CHECK(th_mode(t, "SERVICE_CHARGE"));
        th_env(t, "{\"press\":\"REARM\"}");
        th_run(t, 400);
        CHECK(th_mode(t, "SERVICE_CHARGE") && !t->sim.latch);
    }

    SECTION("WATCHDOG: supervisor stops -> strobe stops -> chain opens, MCU reset, comes back inhibited");
    {
        th_t *t = armed(102);
        moving(t, 0.10, 0.0);
        char boot0[40], boot1[40];
        strcpy(boot0, t->sim.core.boot_id);
        uint32_t st0 = t->sim.n_strobes;
        th_env(t, "{\"freeze_supervisor\":true}");
        th_run_silent(t, 60);
        /* TPS3430 trips 23.4 ms after the last counted edge; WDO opens U23 and (JP1) holds NRST for 200 ms */
        CHECK(t->sim.n_strobes == st0 && !t->sim.wdg_ok && !t->sim.latch && t->sim.mcu_in_reset);
        CHECK(fabs(t->sim.v) < 0.10);
        th_env(t, "{\"freeze_supervisor\":false}");
        th_run_silent(t, 600);
        strcpy(boot1, t->sim.core.boot_id);
        CHECK(strcmp(boot0, boot1) != 0 && t->sim.n_resets == 1);
        CHECK(th_req(t, "HELLO", "{}") && th_is(t, "reset.cause", "WATCHDOG") && th_num(t, "reset.boot_count") == 2);
        CHECK(th_mode(t, "STANDBY") && !th_true(t, "hw_latch"));
        CHECK(th_req(t, "EVENTS", "{\"after_seq\":0}") && th_is(t, "events.0.kind", "BOOT") && th_is(t, "events.0.detail.prev_mode", "MOVING"));
    }
    SECTION("WATCHDOG: control loop stops / background stops -> no strobe");
    {
        th_t *t = armed(103);
        uint32_t st0 = t->sim.n_strobes;
        th_env(t, "{\"freeze_control\":true}");
        th_run_silent(t, 25);
        CHECK(t->sim.n_strobes <= st0 + 1u);
        th_run_silent(t, 40);
        CHECK(!t->sim.wdg_ok || t->sim.n_resets == 1);
        t = armed(104);
        th_env(t, "{\"freeze_background\":true}");
        th_run_silent(t, 480);
        CHECK(t->sim.wdg_ok && t->sim.n_resets == 0);
        th_run_silent(t, 300);
        CHECK(t->sim.n_resets == 1); /* stalled protocol/sensor loop is caught within ~0.6 s, reset after the 200 ms WDO pulse */
        /* the strobe is a 5 ms pulse every 10 ms: valid whether the device counts falling, rising or both edges */
        static const char *const edges[3] = {"{\"wdi_edge\":\"FALLING\"}", "{\"wdi_edge\":\"RISING\"}", "{\"wdi_edge\":\"BOTH\"}"};
        for (int k = 0; k < 3; k++) {
            t = th_new(110 + (uint64_t)k);
            th_env(t, edges[k]);
            th_run_silent(t, 3000);
            CHECK(t->sim.wdg_ok && t->sim.n_resets == 0);
            th_env(t, "{\"freeze_control\":true}"); /* WDI left high or low: no further counted edge */
            th_run_silent(t, 60);
            CHECK(!t->sim.wdg_ok);
        }
    }
    SECTION("MCU_NOT_READY: uncommanded motion while armed withdraws ARM_PERMIT; VMOT_FAULT: traction supply missing");
    {
        th_t *t = armed(105);
        for (int i = 0; i < 400 && t->sim.latch; i++) { /* something pushes/drives the wheels with no command */
            t->sim.w[0] = t->sim.w[1] = 2.0;
            th_run_silent(t, 1);
        }
        CHECK(!t->sim.latch);
        th_run(t, 200);
        CHECK(th_mode(t, "HW_INHIBIT") && th_has(t, "hw_inhibit_reasons", "MCU_NOT_READY") && th_has(t, "protective_stop_reasons", "ENCODER_FAULT"));
        th_run(t, 3500);
        CHECK(th_req(t, "STATE", "{}") && th_true(t, "chain.ARM_PERMIT")); /* permit returns once at rest */
        th_run(t, 6000);                                                     /* then C_SET recharges (round 4 N1) */
        CHECK(th_req(t, "STATE", "{}") && th_true(t, "rearm_ready"));
        th_env(t, "{\"press\":\"REARM\"}");
        th_run(t, 400);
        CHECK(th_mode(t, "ARMED_IDLE"));

        t = armed(106);
        for (int i = 0; i < 300; i++) { /* VMOT collapses although the latch is set (blown fuse) */
            t->sim.vmot = 0.5;
            th_run_silent(t, 1);
        }
        (void)th_req(t, "HELLO", "{}");
        CHECK(th_mode(t, "HW_INHIBIT") && th_has(t, "hw_inhibit_reasons", "VMOT_FAULT"));
    }
    SECTION("FAULT: E-stop pole discrepancy, welded latch; left only by reset");
    {
        th_t *t = armed(107);
        th_env(t, "{\"estop\":true,\"estop_a_stuck\":true}");
        th_run(t, 400);
        CHECK(th_mode(t, "FAULT") && th_has(t, "faults", "ESTOP_DISCREPANCY") && !th_true(t, "chain.ARM_PERMIT"));
        th_env(t, "{\"estop\":false,\"estop_a_stuck\":false,\"press\":\"REARM\"}");
        th_run(t, 500);
        CHECK(th_mode(t, "FAULT") && !t->sim.latch);
        CHECK(!th_rearm_sw(t) && th_status(t, "REJECTED"));
        CHECK(!th_drive(t, 0, 0, 200, OPM) && th_is(t, "reject_reason", "FAULT"));
        th_env(t, "{\"mcu_reset\":\"PIN\"}");
        th_run_silent(t, 400);
        CHECK(th_mode(t, "STANDBY"));
    }
}

/* ------------------------------------------------------------------------------------------ */
static void expect_pstop(th_t *t, const char *reason)
{
    CHECK(th_req(t, "STATE", "{}"));
    bool ok = th_is(t, "mode", "PROTECTIVE_STOP") && th_has(t, "protective_stop_reasons", reason);
    if (!ok) {
        printf("  (reason %s: not latched as documented)\n", reason);
    }
    CHECK(ok);
    CHECK(th_true(t, "hw_latch")); /* software stop leaves the hardware latch alone */
    CHECK(!th_drive(t, 0.05, 0, 200, OPM) && th_is(t, "reject_reason", "PROTECTIVE_STOP") && th_has(t, "stops.sw", reason));
    th_run(t, 1200);
    CHECK(fabs(t->sim.v) < 1e-3 && fabs(t->sim.wz) < 1e-3);
}

/* cause still present: REARM_SW refused; cause removed: still latched until REARM_SW; then ARMED_IDLE and no motion. */
static void clear_pstop(th_t *t, const char *reason, const char *clear_env, bool cause_was_present)
{
    if (cause_was_present) {
        CHECK(!th_rearm_sw(t) && th_status(t, "REJECTED") && th_is(t, "reason", "CAUSE_ACTIVE") && th_has(t, "active", reason));
        th_env(t, "{\"press\":\"REARM\"}"); /* the local button does not override a present cause either */
        th_run(t, 400);
        CHECK(th_mode(t, "PROTECTIVE_STOP"));
        th_env(t, clear_env);
        th_run(t, 2500);
    }
    CHECK(th_mode(t, "PROTECTIVE_STOP") && th_has(t, "protective_stop_reasons", reason)); /* did not auto-clear */
    CHECK(!diag_has(t, "sw_active", reason));
    double x = t->sim.x;
    CHECK(th_rearm_sw(t) && th_has(t, "cleared", reason) && th_is(t, "mode", "ARMED_IDLE"));
    th_run(t, 600);
    CHECK(th_mode(t, "ARMED_IDLE") && fabs(t->sim.x - x) < 1e-4);
}

static void test_protective_reasons(void)
{
    SECTION("host-labelled stops: FIELD_FRONT/LEFT/RIGHT/REAR, HEAD_LINK, LOCALIZATION, HOST_REQUEST");
    static const char *const host[] = {"FIELD_FRONT", "FIELD_LEFT", "FIELD_RIGHT", "FIELD_REAR", "HEAD_LINK", "LOCALIZATION", "HOST_REQUEST"};
    for (size_t i = 0; i < sizeof host / sizeof host[0]; i++) {
        th_t *t = armed(200 + i);
        moving(t, 0.10, 0.0);
        char a[80];
        snprintf(a, sizeof a, "{\"kind\":\"PROTECTIVE\",\"reason\":\"%s\"}", host[i]);
        CHECK(th_req(t, "STOP", a) && th_is(t, "mode", "PROTECTIVE_STOP"));
        expect_pstop(t, host[i]);
        clear_pstop(t, host[i], "{}", false);
    }
    CHECK(!th_req(th_new(1), "STOP", "{\"kind\":\"PROTECTIVE\",\"reason\":\"TILT\"}")); /* not host-assertable */

    SECTION("CLIFF_FL/FR/RL/RR: confirmed drop latches when armed, even at rest");
    static const char *const cliff[] = {"CLIFF_FL", "CLIFF_FR", "CLIFF_RL", "CLIFF_RR"};
    for (int i = 0; i < 4; i++) {
        th_t *t = armed(210 + i);
        char e1[64], e2[64];
        snprintf(e1, sizeof e1, "{\"tof\":{\"%s\":300}}", cliff[i]);
        snprintf(e2, sizeof e2, "{\"tof\":{\"%s\":30}}", cliff[i]);
        th_env(t, e1);
        th_run(t, 150);
        expect_pstop(t, cliff[i]);
        clear_pstop(t, cliff[i], e2, true);
    }
    SECTION("cliff while driving toward it stops inside the stop model; NO_TARGET counts as a drop");
    {
        th_t *t = armed(220);
        moving(t, 0.20, 0.0);
        double x0 = t->sim.x;
        th_env(t, "{\"tof\":{\"CLIFF_FR\":null}}");
        th_run(t, 1500);
        expect_pstop(t, "CLIFF_FR");
        printf("  SIMULATED: cliff at 0.20 m/s -> stopped %.1f mm after the first bad sample could exist\n", (t->sim.x - x0) * 1000.0);
        CHECK(t->sim.x - x0 < 0.100);
    }
    SECTION("unlatched direction inhibit: rear sensor trouble at rest refuses reverse and pivot but allows forward");
    {
        th_t *t = armed(221);
        th_env(t, "{\"tof_stale\":[\"CLIFF_RL\"]}");
        th_run(t, 300);
        CHECK(th_mode(t, "ARMED_IDLE")); /* nothing moved, nothing to latch */
        CHECK(!th_drive(t, -0.05, 0, 200, OPM) && th_is(t, "reject_reason", "DIR_INHIBITED") && !th_true(t, "allow.rev") && !th_true(t, "allow.pivot"));
        CHECK(!th_drive(t, 0, 0.2, 200, OPM) && th_is(t, "reject_reason", "DIR_INHIBITED"));
        CHECK(th_true(t, "allow.fwd") && th_drive(t, 0.1, 0, 200, OPM));
    }
    SECTION("LOOKAHEAD_L / LOOKAHEAD_R: speed is reduced, then the stop is latched before the edge");
    static const char *const look[2][2] = {{"LOOK_FL", "LOOKAHEAD_L"}, {"LOOK_FR", "LOOKAHEAD_R"}};
    for (int i = 0; i < 2; i++) {
        th_t *t = armed(230 + i);
        moving(t, 0.20, 0.0);
        char e1[64], e2[64];
        snprintf(e1, sizeof e1, "{\"tof\":{\"%s\":800}}", look[i][0]); /* floor beyond an edge: longer than 524 + 60 mm */
        snprintf(e2, sizeof e2, "{\"tof\":{\"%s\":524}}", look[i][0]);
        double x0 = t->sim.x, vmin_seen = 1.0;
        th_env(t, e1);
        bool reduced = false;
        for (int k = 0; k < 150 && !t->sim.core.sw_latched; k++) {
            (void)th_drive(t, 0.20, 0, 200, OPM);
            if (th_num(t, "v_cap_mps") < 0.19 && t->sim.core.mode == RRCH_MODE_MOVING) {
                reduced = true;
            }
            th_run_silent(t, 19);
            vmin_seen = t->sim.v < vmin_seen ? t->sim.v : vmin_seen;
        }
        CHECK(reduced);
        expect_pstop(t, look[i][1]);
        printf("  SIMULATED: floor lost on %s at 0.20 m/s -> stopped after %.1f mm (edge assumed %.0f mm ahead)\n", look[i][0], (t->sim.x - x0) * 1000.0, 285.0);
        CHECK(t->sim.x - x0 < 0.285); /* look.fwd_ahead_m: floor intersection beyond the leading rail */
        clear_pstop(t, look[i][1], e2, true);
    }
    SECTION("IB-34: the tail pair guards reverse (LOOKAHEAD_L/R = left/right sensor of the pair in the direction of travel)");
    static const char *const rlook[2][2] = {{"LOOK_RL", "LOOKAHEAD_L"}, {"LOOK_RR", "LOOKAHEAD_R"}};
    for (int i = 0; i < 2; i++) {
        th_t *t = armed(235 + i);
        moving(t, -0.05, 0.0);
        char e1[64], e2[64];
        snprintf(e1, sizeof e1, "{\"tof\":{\"%s\":null}}", rlook[i][0]); /* nothing behind the tail edge */
        snprintf(e2, sizeof e2, "{\"tof\":{\"%s\":267}}", rlook[i][0]);
        double x0 = t->sim.x;
        th_env(t, e1);
        for (int k = 0; k < 400 && !t->sim.core.sw_latched; k++) {
            (void)th_drive(t, -0.05, 0, 200, OPM);
            th_run_silent(t, 19);
        }
        expect_pstop(t, rlook[i][1]);
        printf("  SIMULATED: floor lost behind the tail on %s at -0.05 m/s -> stopped after %.1f mm (edge 201 mm behind the 0.290 m radius)\n", rlook[i][0], (x0 - t->sim.x) * 1000.0);
        CHECK(x0 - t->sim.x < 0.201);
        clear_pstop(t, rlook[i][1], e2, true);
    }
    SECTION("IB-34: a look pair not in the direction of travel does not stop the robot but is supervised and inhibits its own direction");
    {
        th_t *t = armed(237);
        moving(t, 0.10, 0.0);
        th_env(t, "{\"tof_stale\":[\"LOOK_RR\"],\"tof\":{\"LOOK_RL\":null}}");
        th_drive_for(t, 0.10, 0, 600, OPM);
        CHECK(th_mode(t, "MOVING") && !t->sim.core.sw_latched);
        CHECK(diag_has(t, "sw_active", "TOF_STALE") && diag_has(t, "sw_active", "LOOKAHEAD_L"));
        CHECK(th_req(t, "STATE", "{}") && th_is(t, "tof.7.id", "LOOK_FR") && th_is(t, "tof.6.id", "LOOK_RR") && th_is(t, "tof.6.status", "STALE"));
        CHECK(th_drive(t, 0.10, 0, 200, OPM) && !th_true(t, "allow.rev") && th_true(t, "allow.fwd"));
        th_drive_for(t, 0, 0, 1500, OPM);
        CHECK(th_mode(t, "ARMED_IDLE"));
        CHECK(!th_drive(t, -0.05, 0, 200, OPM) && th_is(t, "reject_reason", "DIR_INHIBITED"));
        th_env(t, "{\"tof_stale\":[],\"tof\":{\"LOOK_RL\":267}}");
        th_run(t, 300);
        CHECK(th_drive(t, -0.05, 0, 200, OPM));

        t = armed(238); /* and the other way round: reversing with the forward pair blind */
        moving(t, -0.05, 0.0);
        th_env(t, "{\"tof\":{\"LOOK_FL\":\"INVALID\",\"LOOK_FR\":900}}");
        th_drive_for(t, -0.05, 0, 600, OPM);
        CHECK(th_mode(t, "MOVING") && !t->sim.core.sw_latched);
        CHECK(diag_has(t, "sw_active", "LOOKAHEAD_L") && diag_has(t, "sw_active", "LOOKAHEAD_R")); /* supervised; caps forward when it is used */
    }
    SECTION("look-ahead: obstacle (short reading) reduces speed without a stop when it disappears");
    {
        th_t *t = armed(232);
        moving(t, 0.20, 0.0);
        th_env(t, "{\"tof\":{\"LOOK_FR\":290,\"LOOK_FL\":295}}"); /* something 64 mm beyond the rail */
        th_drive_for(t, 0.20, 0, 400, OPM);
        CHECK(th_drive(t, 0.20, 0, 200, OPM) && th_num(t, "v_cap_mps") < 0.19 && th_num(t, "v_cap_mps") > 0.0);
        CHECK(t->sim.v < 0.19);
        th_env(t, "{\"tof\":{\"LOOK_FR\":524,\"LOOK_FL\":524}}");
        th_drive_for(t, 0.20, 0, 1500, OPM);
        CHECK(th_mode(t, "MOVING") && fabs(t->sim.v - 0.20) < 0.01);
    }
    SECTION("FIELD_REAR while reversing; TOF_STALE and TOF_DISAGREE (blocked cliff window) while driving forward");
    {
        th_t *t = armed(240);
        moving(t, -0.05, 0.0);
        th_env(t, "{\"tof\":{\"REAR_C\":80}}");
        th_drive_for(t, -0.05, 0, 300, OPM);
        expect_pstop(t, "FIELD_REAR");
        clear_pstop(t, "FIELD_REAR", "{\"tof\":{\"REAR_C\":null}}", true);

        t = armed(241);
        moving(t, 0.10, 0.0);
        uint64_t t0 = t->sim.t_us;
        th_env(t, "{\"tof_stale\":[\"LOOK_FR\"]}");
        int ms = 0;
        for (; ms < 400 && !t->sim.core.sw_latched; ms += 20) {
            (void)th_drive(t, 0.10, 0, 200, OPM);
            th_run_silent(t, 19);
        }
        CHECK((t->sim.t_us - t0) <= 160000u); /* max_age 100 ms + one sensor period + poll granularity */
        expect_pstop(t, "TOF_STALE");
        clear_pstop(t, "TOF_STALE", "{\"tof_stale\":[]}", true);

        /* IB-34: the partners of a look pair watch floor spots that do not overlap (frames.yaml: 0.29 m apart
         * against ~0.17 m spots), so two different but individually nominal readings are not a disagreement */
        t = armed(242);
        moving(t, 0.10, 0.0);
        th_env(t, "{\"tof\":{\"LOOK_FL\":475,\"LOOK_FR\":575}}");
        th_drive_for(t, 0.10, 0, 600, OPM);
        CHECK(th_mode(t, "MOVING") && !t->sim.core.sw_latched && !diag_has(t, "sw_active", "TOF_DISAGREE"));

        t = armed(243); /* blocked cliff window (reads ~0 mm) */
        moving(t, 0.10, 0.0);
        th_env(t, "{\"tof\":{\"CLIFF_FL\":2}}");
        th_drive_for(t, 0.10, 0, 500, OPM);
        expect_pstop(t, "TOF_DISAGREE");
    }
    SECTION("CMD_TIMEOUT and HOST_LINK_LOST");
    {
        th_t *t = armed(250);
        moving(t, 0.20, 0.0);
        CHECK(th_drive(t, 0.20, 0, 200, OPM));
        uint64_t t_acc = t->sim.t_us;
        int ms = 0;
        for (; ms < 400 && !(t->sim.core.sw_latched & RRCH_SW(CMD_TIMEOUT)); ms++) {
            th_run_silent(t, 1);
        }
        double dt_ms = (double)(t->sim.t_us - t_acc) / 1000.0;
        printf("  SIMULATED: last DRIVE ttl 200 ms -> CMD_TIMEOUT latched %.0f ms after acceptance\n", dt_ms);
        CHECK(dt_ms >= 199.0 && dt_ms <= 202.0); /* stops within the TTL bound */
        CHECK(t->sim.core.drive.v_sp < 0.2001f);
        th_run_silent(t, 400);
        CHECK(fabs(t->sim.v) < 1e-3);
        expect_pstop(t, "CMD_TIMEOUT");
        clear_pstop(t, "CMD_TIMEOUT", "{}", false);

        t = armed(251); /* armed and idle: the host goes silent */
        th_run_silent(t, 950);
        CHECK(t->sim.core.mode == RRCH_MODE_ARMED_IDLE);
        th_run_silent(t, 100);
        CHECK(t->sim.core.mode == RRCH_MODE_PROTECTIVE_STOP && (t->sim.core.sw_latched & RRCH_SW(HOST_LINK_LOST)));
        th_env(t, "{\"press\":\"REARM\"}"); /* local button cannot clear it while the host is still absent */
        th_run_silent(t, 400);
        CHECK(t->sim.core.mode == RRCH_MODE_PROTECTIVE_STOP);
        expect_pstop(t, "HOST_LINK_LOST"); /* link back: still latched */
        clear_pstop(t, "HOST_LINK_LOST", "{}", false);

        t = armed(252); /* USB stall while moving: buffered commands arrive late and are not executed */
        moving(t, 0.20, 0.0);
        th_env(t, "{\"usb_stall\":true}");
        for (int k = 0; k < 10; k++) {
            char a[160];
            int n = snprintf(a, sizeof a, "{\"type\":\"REQ\",\"v\":\"1.0\",\"id\":%u,\"op\":\"DRIVE\",\"args\":{\"seq\":%u,\"v_mps\":0.2,\"w_radps\":0,\"ttl_ms\":200,\"op_mode\":\"" OPM "\"}}",
                             9000u + (unsigned)k, 9000u + (unsigned)k);
            size_t len = rrc_frame_finish((uint8_t *)a, (size_t)n, sizeof a, RRCH_RECORD_MAX);
            sim_host_write(&t->sim, (const uint8_t *)a, len);
            th_run_silent(t, 20);
        }
        th_run_silent(t, 600);
        CHECK(fabs(t->sim.v) < 1e-3 && (t->sim.core.sw_latched & RRCH_SW(CMD_TIMEOUT)));
        double x = t->sim.x;
        th_env(t, "{\"usb_stall\":false}");
        th_run_silent(t, 500); /* the 10 stale commands are now delivered in a burst */
        uint8_t sink[4096];
        while (sim_host_read(&t->sim, sink, sizeof sink) > 0) {
        }
        CHECK(fabs(t->sim.x - x) < 1e-4 && t->sim.core.mode == RRCH_MODE_PROTECTIVE_STOP);

        t = armed(253); /* a new HELLO while moving = change of controlling session */
        moving(t, 0.10, 0.0);
        CHECK(th_req(t, "HELLO", "{}") && th_num(t, "session") == 2);
        expect_pstop(t, "HOST_LINK_LOST");
    }
    SECTION("STALL, ENCODER_FAULT, IMU_FAULT, TILT, BATTERY_LOW, TEMP_RANGE");
    {
        th_t *t = armed(260);
        moving(t, 0.10, 0.0);
        th_env(t, "{\"block\":\"L\"}");
        th_drive_for(t, 0.10, 0, 900, OPM);
        expect_pstop(t, "STALL");
        clear_pstop(t, "STALL", "{\"block\":\"NONE\"}", false);

        t = armed(261);
        moving(t, 0.20, 0.0);
        double x0 = t->sim.x;
        th_env(t, "{\"enc_dropout\":\"R\"}");
        th_drive_for(t, 0.20, 0, 400, OPM);
        expect_pstop(t, "ENCODER_FAULT");
        printf("  SIMULATED: right encoder dropout at 0.20 m/s -> stopped after %.1f mm, peak speed excursion bounded by detection time\n", (t->sim.x - x0) * 1000.0);
        CHECK(t->sim.x - x0 < 0.10);

        t = armed(262);
        th_env(t, "{\"imu_off\":true}");
        th_run(t, 100);
        expect_pstop(t, "IMU_FAULT");
        clear_pstop(t, "IMU_FAULT", "{\"imu_off\":false}", true);

        t = armed(263);
        th_env(t, "{\"tilt_deg\":25,\"block\":\"BOTH\"}"); /* wheels chocked so only the tilt monitor acts */
        th_run(t, 2500);
        expect_pstop(t, "TILT");
        clear_pstop(t, "TILT", "{\"tilt_deg\":0}", true);

        t = armed(264);
        th_env(t, "{\"vbat\":10.9}");
        th_run(t, 4000);
        CHECK(th_mode(t, "ARMED_IDLE") && th_has(t, "faults", "BATTERY_WARN"));
        th_run(t, 1500);
        expect_pstop(t, "BATTERY_LOW");
        clear_pstop(t, "BATTERY_LOW", "{\"vbat\":12.8}", true);
        th_env(t, "{\"soc\":3}");
        th_run(t, 400);
        expect_pstop(t, "BATTERY_LOW");

        t = armed(265);
        th_env(t, "{\"temp_pack\":65}");
        th_run(t, 100);
        expect_pstop(t, "TEMP_RANGE");
        clear_pstop(t, "TEMP_RANGE", "{\"temp_pack\":20}", true);
        th_env(t, "{\"temp_bay\":-30}");
        th_run(t, 100);
        expect_pstop(t, "TEMP_RANGE");
    }
    SECTION("BRAKE_TEST: pass leaves STANDBY; welded latch fails, latches BRAKE_TEST_FAIL and enters FAULT");
    {
        th_t *t = armed(270);
        CHECK(th_req(t, "BRAKE_TEST", "{}") && th_true(t, "passed") && th_len(t, "fail") == 0 && th_is(t, "mode", "STANDBY"));
        printf("  SIMULATED: brake test latch_drop %.0f ms, relays %.0f ms, VMOT decay %.0f ms to %.2f V\n", th_num(t, "latch_drop_ms"), th_num(t, "relay_ms"),
               th_num(t, "vmot_decay_ms"), th_num(t, "vmot_end_v"));
        CHECK(th_num(t, "latch_drop_ms") <= 50 && th_num(t, "probe_i_a.0") < 0.1);
        CHECK(th_mode(t, "STANDBY") && th_len(t, "hw_inhibit_reasons") == 0);
        CHECK(th_req(t, "DIAG", "{}") && th_is(t, "brake_test.state", "PASSED") && th_true(t, "brake_test.passed_since_boot"));
        CHECK(!th_req(t, "BRAKE_TEST", "{}") && th_status(t, "REJECTED")); /* needs ARMED_IDLE */

        /* stage 3: K1 welded (both poles). U_HOLD keeps RUN_HD off, and the brake test now sees the weld directly:
         * K1 pole A does not read released (LATCH_NC_RB) and K1_RUN rises when ARM_PERMIT returns (LATCH_RUN_RB) */
        t = armed(271);
        th_env(t, "{\"latch_weld\":true}");
        CHECK(th_req(t, "BRAKE_TEST", "{}") && !th_true(t, "passed") && (th_has(t, "fail", "K1_WELDED") || th_has(t, "fail", "K1_NOT_RELEASED")));
        th_run(t, 300);
        CHECK(th_mode(t, "FAULT") && th_has(t, "faults", "K1_WELD"));
        CHECK(!t->sim.core.out.arm_permit && !t->sim.core.out.bridge_awake && !t->sim.run12);

        t = th_new(272); /* no motion before a passed test */
        th_run_silent(t, 300);
        CHECK(th_req(t, "HELLO", "{}") && th_req(t, "SET_OP_MODE", "{\"op_mode\":\"" OPM "\"}"));
        th_env(t, "{\"press\":\"REARM\"}");
        th_run(t, 300);
        CHECK(th_mode(t, "ARMED_IDLE"));
        CHECK(!th_drive(t, 0.1, 0, 200, OPM) && th_is(t, "reject_reason", "BRAKE_TEST_REQUIRED"));
        CHECK(th_drive(t, 0, 0, 200, OPM)); /* keep-alive is fine */
        /* while the test runs every other request is BUSY; a retry of the test request returns the result */
        const char *bt = "{\"type\":\"REQ\",\"v\":\"1.0\",\"id\":5000,\"op\":\"BRAKE_TEST\",\"args\":{}}";
        char fr[128];
        strcpy(fr, bt);
        size_t fl = rrc_frame_finish((uint8_t *)fr, strlen(bt), sizeof fr, RRCH_RECORD_MAX);
        sim_host_write(&t->sim, (const uint8_t *)fr, fl);
        th_run_silent(t, 30);
        CHECK(!th_req(t, "STATE", "{}") && th_status(t, "BUSY"));
        th_run_silent(t, 2600); /* VMOT bleed tau 0.8 s: the test needs about 2.1 s */
        uint8_t sink[4096];
        while (sim_host_read(&t->sim, sink, sizeof sink) > 0) {
        }
        memcpy(t->last_req, fr, fl);
        t->last_req_len = fl;
        CHECK(th_resend(t) && th_true(t, "passed")); /* cached result, test not run twice */
        CHECK(th_mode(t, "STANDBY"));
    }
}

/* ------------------------------------------------------------------------------------------ */
static void test_commands(void)
{
    SECTION("DRIVE acceptance: sequence, TTL, op_mode, limits, retry cache, no queueing");
    th_t *t = armed(300);
    CHECK(th_drive(t, 0, 0, 200, OPM));
    uint32_t seq = t->seq - 1u;
    char a[200];
    snprintf(a, sizeof a, "{\"seq\":%u,\"v_mps\":0,\"w_radps\":0,\"ttl_ms\":200,\"op_mode\":\"" OPM "\"}", seq);
    CHECK(th_req(t, "DRIVE", a) && !th_true(t, "accepted") && th_is(t, "reject_reason", "SEQ"));
    snprintf(a, sizeof a, "{\"seq\":%u,\"v_mps\":0,\"w_radps\":0,\"ttl_ms\":200,\"op_mode\":\"" OPM "\"}", seq - 1u);
    CHECK(th_req(t, "DRIVE", a) && th_is(t, "reject_reason", "SEQ"));
    /* retry with identical bytes: cached reply, the command is not executed a second time */
    CHECK(th_drive(t, 0, 0, 200, OPM));
    char first[RRCH_RECORD_MAX];
    size_t first_len = t->reply_len;
    memcpy(first, t->reply, first_len);
    th_run_silent(t, 30);
    CHECK(th_resend(t) && t->reply_len == first_len && memcmp(first, t->reply, first_len) == 0);
    /* issued_us: a command that is already older than its TTL is refused */
    snprintf(a, sizeof a, "{\"seq\":%u,\"v_mps\":0.05,\"w_radps\":0,\"ttl_ms\":100,\"op_mode\":\"" OPM "\",\"issued_us\":%llu}", t->seq++,
             (unsigned long long)(t->sim.t_us - 150000u));
    CHECK(th_req(t, "DRIVE", a) && th_is(t, "reject_reason", "TTL"));
    snprintf(a, sizeof a, "{\"seq\":%u,\"v_mps\":0.05,\"w_radps\":0,\"ttl_ms\":100,\"op_mode\":\"" OPM "\",\"issued_us\":%llu}", t->seq++,
             (unsigned long long)(t->sim.t_us + 500000u));
    CHECK(!th_req(t, "DRIVE", a) && th_status(t, "BAD_ARG"));
    CHECK(!th_drive(t, 0.05, 0, 200, "GUIDED") && th_is(t, "reject_reason", "OP_MODE"));
    CHECK(!th_drive(t, 0.21, 0, 200, OPM) && th_is(t, "reject_reason", "LIMIT"));
    CHECK(!th_drive(t, -0.06, 0, 200, OPM) && th_is(t, "reject_reason", "LIMIT"));
    CHECK(!th_drive(t, 0.0, 0.31, 200, OPM) && th_is(t, "reject_reason", "LIMIT"));
    th_run(t, 500);
    CHECK(fabs(t->sim.x) < 1e-4 && th_mode(t, "ARMED_IDLE"));

    SECTION("op_mode profiles: caps enforced locally, change only when stationary, LAB/SERVICE have no traction");
    CHECK(th_req(t, "SET_OP_MODE", "{\"op_mode\":\"SURVEY_SHARED\"}") && th_num(t, "caps.v_fwd_mps") == 0.1);
    CHECK(!th_drive(t, 0.15, 0, 200, "SURVEY_SHARED") && th_is(t, "reject_reason", "LIMIT"));
    CHECK(th_drive(t, 0.10, 0, 200, "SURVEY_SHARED"));
    CHECK(!th_req(t, "SET_OP_MODE", "{\"op_mode\":\"" OPM "\"}") && th_status(t, "REJECTED") && th_is(t, "reason", "NOT_STATIONARY"));
    CHECK(th_drive(t, 0, 0, 200, "SURVEY_SHARED"));
    th_run(t, 800);
    CHECK(th_req(t, "SET_OP_MODE", "{\"op_mode\":\"SERVICE\"}") && th_num(t, "caps.v_fwd_mps") == 0);
    CHECK(!th_drive(t, 0.01, 0, 200, "SERVICE") && th_is(t, "reject_reason", "LIMIT"));
    CHECK(th_req(t, "SET_OP_MODE", "{\"op_mode\":\"LAB\"}") && !th_drive(t, 0.0, 0.01, 200, "LAB"));
    CHECK(!th_req(t, "SET_OP_MODE", "{\"op_mode\":\"FAST\"}") && th_status(t, "BAD_ARG"));

    SECTION("pre-motion alert before any motion from rest; not repeated inside alert.rest_ms");
    t = armed(301);
    uint64_t t0 = t->sim.t_us;
    int buzz = 0, first_move_ms = -1;
    for (int ms = 0; ms < 2500; ms++) {
        if (ms % 20 == 0) {
            (void)th_drive(t, 0.10, 0, 200, OPM);
            if (ms == 100) {
                CHECK(th_is(t, "motion", "ALERT") && th_is(t, "mode", "MOVING") && th_num(t, "applied.v_mps") == 0);
            }
        } else {
            th_run_silent(t, 1);
        }
        if (t->sim.core.out.buzzer && first_move_ms < 0) {
            buzz++;
        }
        if (first_move_ms < 0 && fabs(t->sim.v) > 0.002) {
            first_move_ms = (int)((t->sim.t_us - t0) / 1000u);
        }
    }
    printf("  SIMULATED: first wheel motion %d ms after the first DRIVE (alert.premotion_ms = 1500), buzzer on for %d ms of it\n", first_move_ms, buzz);
    CHECK(first_move_ms >= 1500 && first_move_ms < 1600 && buzz > 600);
    th_drive_for(t, 0, 0, 800, OPM); /* short stop: below alert.rest_ms */
    CHECK(fabs(t->sim.v) < 1e-3);
    th_drive_for(t, 0.10, 0, 300, OPM);
    CHECK(t->sim.v > 0.02);
    th_drive_for(t, 0, 0, 5500, OPM); /* rest longer than alert.rest_ms (5 s): alert again */
    (void)th_drive(t, 0.10, 0, 200, OPM);
    th_run_silent(t, 19);
    CHECK(th_drive(t, 0.10, 0, 200, OPM) && th_is(t, "motion", "ALERT"));
    /* alert length is configurable but has a floor */
    CHECK(!th_req(t, "CONFIG_SET", "{\"key\":\"alert.premotion_ms\",\"value\":100}") && th_status(t, "BAD_ARG"));

    SECTION("HOLD: STOP CONTROLLED and local PAUSE latch a hold; DRIVE is refused until a deliberate resume");
    t = armed(302);
    moving(t, 0.10, 0.0);
    CHECK(th_req(t, "STOP", "{\"kind\":\"CONTROLLED\"}") && th_is(t, "mode", "HOLD") && th_has(t, "hold", "HOST_STOP"));
    CHECK(!th_drive(t, 0.10, 0, 200, OPM) && th_is(t, "reject_reason", "HOLD"));
    th_drive_for(t, 0.10, 0, 1500, OPM);
    if (!(fabs(t->sim.v) < 1e-3) || !th_mode(t, "HOLD")) {
        printf("  dbg: v=%f mode=%s sw=%x hold=%x hw=%x\n", t->sim.v, rrch_mode_names[t->sim.core.mode], t->sim.core.sw_latched, t->sim.core.hold, t->sim.core.chain.hw_latched);
    }
    CHECK(fabs(t->sim.v) < 1e-3 && th_mode(t, "HOLD"));
    CHECK(th_rearm_sw(t) && th_has(t, "hold_cleared", "HOST_STOP") && th_is(t, "mode", "ARMED_IDLE"));
    moving(t, 0.10, 0.0);
    th_env(t, "{\"press\":\"PAUSE\"}");
    th_drive_for(t, 0.10, 0, 1200, OPM);
    CHECK(th_mode(t, "HOLD") && th_has(t, "hold", "LOCAL_PAUSE") && fabs(t->sim.v) < 1e-3);
    th_env(t, "{\"press\":\"REARM\"}");
    th_run(t, 300);
    CHECK(th_mode(t, "ARMED_IDLE"));
    CHECK(!th_req(t, "STOP", "{\"kind\":\"SLOW\"}") && th_status(t, "BAD_ARG"));

    SECTION("REARM_SW: nonce must be the current one; a replayed re-arm does not clear a later stop");
    t = armed(303);
    CHECK(th_req(t, "STOP", "{\"kind\":\"PROTECTIVE\"}"));
    double nonce1 = th_num(t, "rearm_nonce");
    CHECK(nonce1 > 0);
    CHECK(!th_req(t, "REARM_SW", "{\"nonce\":12345,\"operator\":\"x\"}") && th_status(t, "REJECTED") && th_is(t, "reason", "NONCE"));
    CHECK(!th_req(t, "REARM_SW", "{\"nonce\":1}") && th_status(t, "BAD_ARG"));
    snprintf(a, sizeof a, "{\"nonce\":%.0f,\"operator\":\"a.tech\"}", nonce1);
    CHECK(th_req(t, "REARM_SW", a) && th_has(t, "cleared", "HOST_REQUEST"));
    CHECK(th_req(t, "STOP", "{\"kind\":\"PROTECTIVE\"}"));
    CHECK(!th_req(t, "REARM_SW", a) && th_is(t, "reason", "NONCE")); /* stale nonce */
    CHECK(th_mode(t, "PROTECTIVE_STOP"));
    CHECK(th_req(t, "EVENTS", "{\"after_seq\":0}"));

    SECTION("retreat is off by default; with safety.allow_retreat only motion away from the hazard is accepted, slowly");
    t = armed(304);
    th_env(t, "{\"tof\":{\"CLIFF_RL\":250}}");
    th_run(t, 200);
    CHECK(!th_rearm_sw(t) && th_is(t, "reason", "CAUSE_ACTIVE"));
    CHECK(th_req(t, "CONFIG_SET", "{\"key\":\"safety.allow_retreat\",\"value\":1}"));
    CHECK(th_rearm_sw(t) && th_has(t, "cleared", "CLIFF_RL"));
    th_run(t, 300);
    CHECK(th_mode(t, "ARMED_IDLE")); /* acknowledged cause does not re-latch */
    CHECK(!th_drive(t, -0.05, 0, 200, OPM) && th_is(t, "reject_reason", "DIR_INHIBITED"));
    CHECK(!th_drive(t, 0, 0.2, 200, OPM) && th_is(t, "reject_reason", "DIR_INHIBITED"));
    moving(t, 0.20, 0.0);
    CHECK(t->sim.v > 0.03 && t->sim.v < 0.055); /* forward retreat only, capped at safety.retreat_v_mps */
    th_env(t, "{\"tof\":{\"CLIFF_RL\":30}}");
    th_drive_for(t, 0.20, 0, 1500, OPM);
    CHECK(t->sim.v > 0.19);
}

/* ------------------------------------------------------------------------------------------ */
static void test_step_and_count(void)
{
    SECTION("step-and-count: stationary evidence, no long alert between short hops, stop/inhibit events inside a count");
    th_t *t = armed(350);
    CHECK(th_drive(t, 0, 0, 200, OPM) && th_true(t, "stationary.is_stationary") && th_num(t, "stationary.since_us") > 0);
    int alerts = 0;
    double prev_since = 0;
    for (int hop = 0; hop < 4; hop++) {
        double x0 = t->sim.x;
        bool saw_moving_flag = false;
        for (int k = 0; k < 400 && t->sim.x - x0 < 0.095; k++) { /* move ~100 mm */
            (void)th_drive(t, 0.10, 0, 200, OPM);
            alerts += th_is(t, "motion", "ALERT") && k == 2;
            if (t->sim.v > 0.02) {
                saw_moving_flag |= !th_true(t, "stationary.is_stationary") && rrc_json_is_null(&t->doc, th_get(t, "stationary.since_us"));
            }
            th_run_silent(t, 19);
        }
        CHECK(saw_moving_flag);
        th_drive_for(t, 0, 0, 600, OPM); /* stop and settle */
        CHECK(th_drive(t, 0, 0, 200, OPM) && th_true(t, "stationary.is_stationary") && th_is(t, "motion", "REST"));
        double since = th_num(t, "stationary.since_us");
        CHECK(since > prev_since && since <= (double)(t->sim.t_us - t->sim.boot_us));
        for (int k = 0; k < 100; k++) { /* a 2 s scaler count: the evidence must not move */
            th_run_silent(t, 19);
            CHECK(th_drive(t, 0, 0, 200, OPM) && th_true(t, "stationary.is_stationary") && th_num(t, "stationary.since_us") == since);
        }
        CHECK(th_req(t, "STATE", "{}") && th_true(t, "stationary.is_stationary") && th_num(t, "stationary.since_us") == since);
        prev_since = since;
        CHECK(fabs(t->sim.x - x0 - 0.10) < 0.012);
    }
    printf("  SIMULATED: 4 hops of ~100 mm with 2.6 s counts: %d pre-motion alert(s) (first start only; idle time alert.rest_ms = 5 s)\n", alerts);
    CHECK(alerts == 1);
    /* something disturbs the robot during a count: the evidence resets and the transition is in the event log */
    CHECK(th_drive(t, 0, 0, 200, OPM));
    double since = th_num(t, "stationary.since_us"), ev0 = th_num(t, "event_seq");
    uint64_t t_bump = t->sim.t_us - t->sim.boot_us;
    th_env(t, "{\"bumper_r\":true}");
    for (int i = 0; i < 30; i++) { /* the contact also shoves the robot a little */
        t->sim.w[0] = t->sim.w[1] = 0.3;
        th_run_silent(t, 1);
    }
    th_env(t, "{\"bumper_r\":false}");
    th_run(t, 600);
    CHECK(!th_drive(t, 0, 0, 200, OPM) && th_num(t, "stationary.since_us") > since && th_num(t, "event_seq") > ev0);
    char a[48];
    snprintf(a, sizeof a, "{\"after_seq\":%.0f}", ev0);
    CHECK(th_req(t, "EVENTS", a));
    bool chain_ev = false, latch_ev = false, mode_ev = false;
    for (int i = 0; i < th_len(t, "events"); i++) {
        char p[40];
        snprintf(p, sizeof p, "events.%d.t_us", i);
        bool in_window = th_num(t, p) >= (double)t_bump && th_num(t, p) <= (double)t_bump + 60000.0;
        snprintf(p, sizeof p, "events.%d.kind", i);
        chain_ev |= in_window && th_is(t, p, "CHAIN");
        latch_ev |= in_window && th_is(t, p, "HW_LATCH");
        mode_ev |= in_window && th_is(t, p, "MODE");
    }
    CHECK(chain_ev && latch_ev && mode_ev);
    /* gyro alone (no encoder ticks) also breaks stationarity: threshold is configurable */
    CHECK(th_req(t, "CONFIG_GET", "{\"key\":\"stationary.gyro_max_radps\"}") && th_num(t, "value") == 0.05);
    CHECK(th_req(t, "CONFIG_GET", "{\"key\":\"alert.rest_ms\"}") && th_num(t, "value") == 5000);
}

/* ------------------------------------------------------------------------------------------ */
static void test_reset_and_aux(void)
{
    SECTION("MCU reset mid-motion: stops, comes back inhibited with a new boot_id, old session is void");
    th_t *t = armed(400);
    moving(t, 0.20, 0.0);
    char boot0[40];
    strcpy(boot0, t->sim.core.boot_id);
    double x0 = t->sim.x;
    th_env(t, "{\"mcu_reset\":\"SOFTWARE\"}");
    CHECK(!t->sim.core.out.arm_permit);
    th_run_silent(t, 400);
    CHECK(!t->sim.latch && fabs(t->sim.v) < 1e-3);
    printf("  SIMULATED: MCU reset at 0.20 m/s -> stopped by the latch drop after %.1f mm\n", (t->sim.x - x0) * 1000.0);
    CHECK(t->sim.x - x0 < 0.05);
    CHECK(!th_drive(t, 0.2, 0, 200, OPM) && th_is(t, "reject_reason", "NO_SESSION"));
    CHECK(th_req(t, "HELLO", "{}") && !th_is(t, "boot_id", boot0) && th_is(t, "reset.cause", "SOFTWARE") && th_num(t, "session") == 1);
    CHECK(th_mode(t, "STANDBY") && !th_true(t, "hw_latch") && th_is(t, "op_mode", "SERVICE"));
    CHECK(th_req(t, "DIAG", "{}") && th_is(t, "brake_test.state", "NONE") && !th_true(t, "brake_test.passed_since_boot"));
    CHECK(th_req(t, "STATE", "{}"));
    CHECK(th_num(t, "uptime_us") < 2e6);
    CHECK(!th_drive(t, 0.2, 0, 200, OPM) && th_is(t, "reject_reason", "STANDBY"));
    th_run(t, 1000);
    CHECK(fabs(t->sim.v) < 1e-3);

    SECTION("HEAD_POWER: forced off in SERVICE_CHARGE, allowed in LAB, off on unplug, never restored automatically");
    t = armed(401);
    CHECK(th_req(t, "HEAD_POWER", "{\"electronics\":true,\"heater_enable\":true}") && th_true(t, "electronics") && th_true(t, "heater_enable"));
    th_run(t, 20);
    CHECK(t->sim.core.out.head_pwr_en && t->sim.core.out.head_htr_en);
    CHECK(!th_req(t, "HEAD_POWER", "{\"electronics\":false,\"heater_enable\":true}") && th_status(t, "BAD_ARG"));
    th_env(t, "{\"chg_plug\":true}");
    th_run(t, 100);
    CHECK(th_mode(t, "SERVICE_CHARGE") && !t->sim.core.out.head_pwr_en && !t->sim.core.out.head_htr_en);
    CHECK(!th_req(t, "HEAD_POWER", "{\"electronics\":true,\"heater_enable\":false}") && th_status(t, "REJECTED") && th_is(t, "reason", "SERVICE_CHARGE"));
    th_env(t, "{\"chg_plug\":false}");
    th_run(t, 300);
    CHECK(!t->sim.core.out.head_pwr_en); /* not restored by itself */
    th_env(t, "{\"pres_ohm\":1137,\"head_docked\":false}");
    th_run(t, 100);
    CHECK(th_mode(t, "LAB"));
    CHECK(th_req(t, "HEAD_POWER", "{\"electronics\":true,\"heater_enable\":false}") && th_true(t, "electronics"));
    th_run(t, 20);
    CHECK(t->sim.core.out.head_pwr_en && !t->sim.core.out.arm_permit && !t->sim.latch); /* power yes, traction hard-inhibited */
    th_env(t, "{\"pres_ohm\":1e9}");
    th_run_silent(t, 5);
    CHECK(!t->sim.core.out.head_pwr_en); /* J1 unplugged: off within 5 ms */
    th_env(t, "{\"pres_ohm\":1500}");
    th_run(t, 100);
    CHECK(!th_req(t, "HEAD_POWER", "{\"electronics\":true,\"heater_enable\":false}") && th_is(t, "reason", "HEAD_ABSENT"));
    th_env(t, "{\"pres_ohm\":4700,\"efuse_fault\":1}");
    th_run(t, 300);
    CHECK(th_req(t, "HEAD_POWER", "{\"electronics\":true,\"heater_enable\":false}"));
    th_run(t, 300);
    CHECK(!t->sim.core.out.head_pwr_en && th_req(t, "STATE", "{}") && th_has(t, "faults", "EFUSE_HEAD_PWR"));

    SECTION("HEATER: default off, proportional band, forced off on sensor fault / over-temperature / low battery");
    t = armed(402);
    th_env(t, "{\"temp_bay\":-5,\"temp_pack\":-4}");
    th_run(t, 2100);
    CHECK(!t->sim.core.out.chs_htr_on && th_req(t, "STATE", "{}") && th_num(t, "heater.chassis_duty_pct") == 0);
    CHECK(th_req(t, "HEATER", "{\"chassis_setpoint_c\":10}"));
    th_run(t, 100);
    CHECK(th_req(t, "STATE", "{}") && th_num(t, "heater.chassis_duty_pct") == 100 && t->sim.core.out.chs_htr_on);
    th_env(t, "{\"temp_bay\":9,\"temp_pack\":9}");
    th_run(t, 100);
    CHECK(th_req(t, "STATE", "{}") && th_num(t, "heater.chassis_duty_pct") == 50);
    t->sim.temp[0] = NAN; /* open NTC */
    th_run(t, 100);
    CHECK(!t->sim.core.out.chs_htr_on && th_req(t, "STATE", "{}") && th_has(t, "faults", "HEATER_SENSOR") && !th_true(t, "heater.sensor_ok"));
    t->sim.temp[0] = 9.0;
    th_env(t, "{\"vbat\":11.8}");
    th_run(t, 100);
    CHECK(th_req(t, "STATE", "{}") && th_num(t, "heater.chassis_duty_pct") == 0);
    th_env(t, "{\"vbat\":13,\"temp_bay\":36}");
    th_run(t, 100);
    CHECK(!t->sim.core.out.chs_htr_on);
    CHECK(!th_req(t, "HEATER", "{\"chassis_setpoint_c\":45}") && th_status(t, "BAD_ARG"));
    CHECK(th_req(t, "HEATER", "{\"chassis_setpoint_c\":null}"));
    th_env(t, "{\"mcu_reset\":\"PIN\"}");
    th_run_silent(t, 400);
    CHECK(!t->sim.core.htr_enabled && !t->sim.core.out.chs_htr_on); /* default off after every boot */

    SECTION("CONFIG: range check, persistence with CRC across resets, defaults on corruption, write failure");
    t = armed(403);
    CHECK(th_req(t, "CONFIG_GET", "{\"key\":\"cal.track_m\"}") && th_num(t, "value") == 0.27 && th_num(t, "min") == 0.2);
    CHECK(!th_req(t, "CONFIG_SET", "{\"key\":\"cal.track_m\",\"value\":0.5}") && th_status(t, "BAD_ARG"));
    CHECK(!th_req(t, "CONFIG_SET", "{\"key\":\"caps.commissioning.v_fwd_mps\",\"value\":0.25}") && th_status(t, "BAD_ARG")); /* contract ceiling */
    CHECK(!th_req(t, "CONFIG_GET", "{\"key\":\"nope\"}") && th_status(t, "BAD_ARG"));
    CHECK(th_req(t, "CONFIG_SET", "{\"key\":\"cal.track_m\",\"value\":0.2713}") && th_num(t, "gen") == 1 && th_num(t, "old") == 0.27);
    CHECK(th_req(t, "CONFIG_SET", "{\"key\":\"cal.wheel_radius_l_m\",\"value\":0.0518}") && th_num(t, "gen") == 2);
    CHECK(th_req(t, "CONFIG_GET", "{\"key\":\"_keys\",\"offset\":0}") && th_len(t, "keys") == 24 && th_num(t, "total") == RRCH_CFG_N);
    moving(t, 0.10, 0);
    CHECK(!th_req(t, "CONFIG_SET", "{\"key\":\"cal.track_m\",\"value\":0.26}") && th_status(t, "REJECTED") && th_is(t, "reason", "NOT_STATIONARY"));
    th_env(t, "{\"mcu_reset\":\"PIN\"}");
    th_run_silent(t, 400);
    CHECK(th_req(t, "HELLO", "{}") && th_is(t, "config.source", "FLASH") && th_num(t, "config.gen") == 2);
    CHECK(th_req(t, "CONFIG_GET", "{\"key\":\"cal.track_m\"}") && fabs(th_num(t, "value") - 0.2713) < 1e-6);
    CHECK(th_req(t, "CONFIG_GET", "{\"key\":\"cal.wheel_radius_l_m\"}") && fabs(th_num(t, "value") - 0.0518) < 1e-6);
    t->sim.nv[RRCH_NV_SLOT_CFG_B][30] ^= 0xFF; /* newest copy (gen 2) corrupted: the older valid copy is used */
    th_env(t, "{\"mcu_reset\":\"PIN\"}");
    th_run_silent(t, 400);
    CHECK(th_req(t, "HELLO", "{}") && th_is(t, "config.source", "FLASH") && th_num(t, "config.gen") == 1);
    CHECK(th_req(t, "CONFIG_GET", "{\"key\":\"cal.wheel_radius_l_m\"}") && fabs(th_num(t, "value") - 0.052) < 1e-6);
    t->sim.nv[RRCH_NV_SLOT_CFG_A][30] ^= 0xFF; /* both copies bad: defaults, flagged */
    th_env(t, "{\"mcu_reset\":\"PIN\"}");
    th_run_silent(t, 400);
    CHECK(th_req(t, "HELLO", "{}") && th_is(t, "config.source", "DEFAULTS"));
    CHECK(th_req(t, "STATE", "{}") && th_has(t, "faults", "CONFIG_DEFAULTED"));
    th_env(t, "{\"nv_fail\":true}");
    CHECK(!th_req(t, "CONFIG_SET", "{\"key\":\"cal.track_m\",\"value\":0.28}") && th_status(t, "FAULT") && th_is(t, "reason", "NV_WRITE"));
    CHECK(th_req(t, "CONFIG_GET", "{\"key\":\"cal.track_m\"}") && th_num(t, "value") == 0.27);

    SECTION("EVENTS: every transition logged in order, paging with after_seq, gap flag after overflow");
    t = armed(404);
    CHECK(th_req(t, "EVENTS", "{\"after_seq\":0}") && th_is(t, "events.0.kind", "BOOT") && th_num(t, "events.0.seq") == 1 && !th_true(t, "gap"));
    double newest = th_num(t, "newest_seq");
    int got = th_len(t, "events");
    bool more = th_true(t, "more");
    double last = 0;
    char p[40];
    snprintf(p, sizeof p, "events.%d.seq", got - 1);
    last = th_num(t, p);
    CHECK(got > 5 && (more || last == newest));
    while (more) {
        snprintf(p, sizeof p, "{\"after_seq\":%.0f}", last);
        CHECK(th_req(t, "EVENTS", p));
        got = th_len(t, "events");
        CHECK(got > 0 && th_num(t, "events.0.seq") == last + 1);
        snprintf(p, sizeof p, "events.%d.seq", got - 1);
        last = th_num(t, p);
        more = th_true(t, "more");
    }
    CHECK(last == th_num(t, "newest_seq"));
    for (int i = 0; i < 80; i++) { /* flood: 160 chain events */
        th_env(t, "{\"hands_on\":true}");
        th_run_silent(t, 3);
        th_env(t, "{\"hands_on\":false}");
        th_run_silent(t, 60);
    }
    CHECK(th_req(t, "EVENTS", "{\"after_seq\":3}") && th_true(t, "gap") && th_num(t, "oldest_seq") > 4 && th_true(t, "more"));
    CHECK(th_num(t, "events.0.seq") == th_num(t, "oldest_seq"));
    CHECK(!th_req(t, "EVENTS", "{}") && th_status(t, "BAD_ARG"));

    SECTION("STATE stays below the 2048-byte record limit in a worst case; panel indications per mode");
    t = armed(405);
    CHECK(th_req(t, "PANEL", "{\"pattern\":\"ARRIVED\"}") && th_is(t, "leds.ready", "BLINK_2"));
    CHECK(th_req(t, "STATE", "{}") && th_is(t, "panel.leds.ready", "BLINK_2") && th_len(t, "tof") == RRCH_TOF_N);
    th_env(t, "{\"tof_stale\":[\"ALL\"],\"imu_off\":true,\"temp_pack\":70,\"soc\":1,\"vbat\":10.5,\"efuse_fault\":31,\"tilt_deg\":30}");
    th_run(t, 1500);
    (void)th_req(t, "STOP", "{\"kind\":\"PROTECTIVE\",\"reason\":\"LOCALIZATION\"}");
    (void)th_req(t, "STOP", "{\"kind\":\"PROTECTIVE\",\"reason\":\"FIELD_FRONT\"}");
    (void)th_req(t, "STOP", "{\"kind\":\"PROTECTIVE\",\"reason\":\"FIELD_RIGHT\"}");
    (void)th_req(t, "STOP", "{\"kind\":\"CONTROLLED\"}");
    th_env(t, "{\"estop\":true,\"hands_on\":true,\"mode_run\":false,\"head_docked\":false,\"bumper_l\":true,\"bumper_r\":true,\"loop_ohm\":1e9,\"j2\":false,\"pres_ohm\":8000}");
    th_run(t, 400);
    t->max_reply_len = 0;
    CHECK(th_req(t, "STATE", "{}"));
    /* node semantics: everything behind the open selector is UNKNOWN, not a reason; MODE_NOT_RUN, ESTOP (pole B),
     * HEAD_LOOP_OPEN (comparator) and MCU_NOT_READY (presence FAULT) remain */
    CHECK(th_is(t, "mode", "HW_INHIBIT") && th_len(t, "hw_inhibit_reasons") >= 4);
    printf("  worst-case STATE record observed: %zu bytes (limit %u)\n", t->max_reply_len, RRCH_RECORD_MAX);
    CHECK(t->max_reply_len <= RRCH_RECORD_MAX);
    /* absolute worst case: every reason and flag set at once (forced directly; not reachable in practice) */
    t->sim.core.sw_latched = t->sim.core.sw_acked = (1u << RRCH_SW_N) - 1u;
    t->sim.core.chain.hw_latched = (1u << RRCH_HW_N) - 1u;
    t->sim.core.faults |= ((1ull << RRCH_FLT_N) - 1ull) & ~RRCH_FLT_FATAL_MASK;
    t->sim.core.hold = 3u;
    t->max_reply_len = 0;
    CHECK(th_req(t, "STATE", "{}") && th_true(t, "truncated") && th_len(t, "protective_stop_reasons") == 12 && th_len(t, "hw_inhibit_reasons") == RRCH_HW_N);
    CHECK(th_req(t, "DIAG", "{}") && th_len(t, "protective_stop_reasons") == RRCH_SW_N && th_len(t, "faults") >= 3 && th_len(t, "hw_inhibit_reasons") == RRCH_HW_N);
    CHECK(th_req(t, "STATE", "{}"));
    printf("  absolute worst-case STATE record: %zu bytes (additive lists dropped, \"truncated\":true)\n", t->max_reply_len);
    CHECK(t->max_reply_len <= RRCH_RECORD_MAX && th_len(t, "tof") == RRCH_TOF_N);
    CHECK(th_is(t, "head_presence", "FAULT") && !th_true(t, "chain.ARM_PERMIT") && th_has(t, "hw_inhibit_reasons", "MCU_NOT_READY"));
}

int main(void)
{
    test_boot_and_hello();
    test_chain_elements();
    test_protective_reasons();
    test_commands();
    test_step_and_count();
    test_reset_and_aux();
    return th_summary("test_state_machine");
}
