/* Chain supervision: presence-code decode incl. boundaries, debounce, event latching of short
 * pulses, stop model, configuration image. SIMULATED inputs on the host port. */
#include <math.h>
#include <string.h>

#include "harness.h"
#include "rrch_pwrdev.h"

/* Counts events of a kind in the core ring after seq `after`; optionally matching a and b. */
static int count_ev(th_t *t, uint32_t after, rrch_ev_kind_t kind, int a, int b)
{
    int n = 0;
    const rrch_t *c = &t->sim.core;
    for (uint32_t s = after + 1u; s <= c->ev_newest; s++) {
        const rrch_event_t *e = &c->ev[(s - 1u) % RRCH_EVENTS_N];
        if (e->kind == kind && (a < 0 || e->a == a) && (b < 0 || e->b == b)) {
            n++;
        }
    }
    return n;
}

int main(void)
{
    SECTION("presence resistor decode, nominal values and window boundaries");
    static const struct { uint32_t ohm; rrch_pres_t want; } tab[] = {
        {0, RRCH_PRES_FAULT}, {799, RRCH_PRES_FAULT}, {800, RRCH_PRES_FAULT}, {949, RRCH_PRES_FAULT},
        {950, RRCH_PRES_HEAD_VIA_LAB_EXTENSION}, {1137, RRCH_PRES_HEAD_VIA_LAB_EXTENSION}, {1329, RRCH_PRES_HEAD_VIA_LAB_EXTENSION},
        {1330, RRCH_PRES_LAB_EXTENSION_ONLY}, {1500, RRCH_PRES_LAB_EXTENSION_ONLY}, {1800, RRCH_PRES_LAB_EXTENSION_ONLY},
        {1801, RRCH_PRES_FAULT}, {3899, RRCH_PRES_FAULT}, {3900, RRCH_PRES_HEAD_DIRECT}, {4700, RRCH_PRES_HEAD_DIRECT},
        {5600, RRCH_PRES_HEAD_DIRECT}, {5601, RRCH_PRES_FAULT}, {20000, RRCH_PRES_FAULT}, {20001, RRCH_PRES_ABSENT}, {1000000, RRCH_PRES_ABSENT}};
    for (size_t i = 0; i < sizeof tab / sizeof tab[0]; i++) {
        CHECK(rrch_pres_classify(tab[i].ohm) == tab[i].want);
    }
    /* 1 % resistors: 4.70k || 1.50k = 1137 ohm; all tolerance corners stay inside their windows */
    for (int a = -1; a <= 1; a += 2) {
        for (int b = -1; b <= 1; b += 2) {
            double r1 = 4700.0 * (1 + 0.01 * a), r2 = 1500.0 * (1 + 0.01 * b);
            CHECK(rrch_pres_classify((uint32_t)(r1 * r2 / (r1 + r2))) == RRCH_PRES_HEAD_VIA_LAB_EXTENSION);
            CHECK(rrch_pres_classify((uint32_t)r1) == RRCH_PRES_HEAD_DIRECT);
            CHECK(rrch_pres_classify((uint32_t)r2) == RRCH_PRES_LAB_EXTENSION_ONLY);
        }
    }

    SECTION("5 ms J1 unplug pulse leaves an event pair without any polling");
    {
        th_t *t = th_new(3);
        th_run_silent(t, 400);
        uint32_t s0 = t->sim.core.ev_newest;
        t->sim.pres_ohm = 1e9;
        th_run_silent(t, 5);
        t->sim.pres_ohm = 4700.0;
        th_run_silent(t, 100);
        CHECK(count_ev(t, s0, RRCH_EV_J1, RRCH_PRES_HEAD_DIRECT, RRCH_PRES_ABSENT) == 1);
        CHECK(count_ev(t, s0, RRCH_EV_J1, RRCH_PRES_ABSENT, RRCH_PRES_HEAD_DIRECT) == 1);
        CHECK(t->sim.core.chain.pres == RRCH_PRES_HEAD_DIRECT);
        CHECK(t->sim.core.chain.hw_latched & RRCH_HW(J1_ABSENT)); /* and the reason stays latched */
        /* visible through the protocol, with timestamps 5 ms +- debounce apart */
        CHECK(th_req(t, "EVENTS", "{\"after_seq\":0}"));
        int n = th_len(t, "events"), seen = 0;
        double t_open = 0, t_close = 0;
        for (int i = 0; i < n; i++) {
            char p[40];
            snprintf(p, sizeof p, "events.%d.kind", i);
            if (th_is(t, p, "J1")) {
                snprintf(p, sizeof p, "events.%d.t_us", i);
                double tu = th_num(t, p);
                snprintf(p, sizeof p, "events.%d.detail.to", i);
                if (th_is(t, p, "ABSENT")) {
                    t_open = tu;
                } else {
                    t_close = tu;
                }
                seen++;
            }
        }
        CHECK(seen == 2);
        CHECK(t_close - t_open >= 5000.0 && t_close - t_open <= 5000.0 + 22000.0);
    }

    SECTION("5 ms J2 unplug pulse, 1 ms bumper pulse, 2 ms E-stop pulse");
    {
        th_t *t = th_new(4);
        th_run_silent(t, 400);
        uint32_t s0 = t->sim.core.ev_newest;
        t->sim.j2 = false;
        th_run_silent(t, 5);
        t->sim.j2 = true;
        th_run_silent(t, 100);
        CHECK(count_ev(t, s0, RRCH_EV_J2, 0, -1) == 1);
        CHECK(count_ev(t, s0, RRCH_EV_J2, 1, -1) == 1);

        s0 = t->sim.core.ev_newest;
        t->sim.bumper_l = true;
        th_run_silent(t, 1);
        t->sim.bumper_l = false;
        th_run_silent(t, 100);
        CHECK(count_ev(t, s0, RRCH_EV_CHAIN, RRCH_DII_BODY_BUMPER_L, 0) == 1);
        CHECK(count_ev(t, s0, RRCH_EV_CHAIN, RRCH_DII_BODY_BUMPER_L, 1) == 1);
        CHECK(t->sim.core.chain.hw_latched & RRCH_HW(BODY_BUMPER));

        s0 = t->sim.core.ev_newest;
        t->sim.estop = true;
        th_run_silent(t, 2);
        t->sim.estop = false;
        th_run_silent(t, 100);
        CHECK(count_ev(t, s0, RRCH_EV_CHAIN, RRCH_DII_ESTOP_A, 0) == 1 && count_ev(t, s0, RRCH_EV_CHAIN, RRCH_DII_ESTOP_B, 0) == 1);
        CHECK(t->sim.core.chain.hw_latched & RRCH_HW(ESTOP));
    }

    SECTION("debounce: open is immediate, close needs chain.close_debounce_ms");
    {
        th_t *t = th_new(5);
        th_run_silent(t, 400);
        t->sim.hands_on = true;
        th_run_silent(t, 1);
        CHECK(!(t->sim.core.chain.state & RRCH_DI(HANDS_ON)));
        t->sim.hands_on = false;
        th_run_silent(t, 40);
        CHECK(!(t->sim.core.chain.state & RRCH_DI(HANDS_ON))); /* still open at 40 ms */
        th_run_silent(t, 15);
        CHECK(t->sim.core.chain.state & RRCH_DI(HANDS_ON));
        /* contact bounce while closing restarts the timer */
        t->sim.hands_on = true;
        th_run_silent(t, 5);
        for (int i = 0; i < 6; i++) {
            t->sim.hands_on = false;
            th_run_silent(t, 30);
            t->sim.hands_on = true;
            th_run_silent(t, 1);
            CHECK(!(t->sim.core.chain.state & RRCH_DI(HANDS_ON)));
        }
    }

    SECTION("J1 class changes need the settle time; transient FAULT readings while mating do not flip the class");
    {
        th_t *t = th_new(6);
        th_run_silent(t, 400);
        uint32_t s0 = t->sim.core.ev_newest;
        t->sim.pres_ohm = 2500.0; /* between windows for 10 ms */
        th_run_silent(t, 10);
        t->sim.pres_ohm = 4700.0;
        th_run_silent(t, 50);
        CHECK(count_ev(t, s0, RRCH_EV_J1, -1, -1) == 0);
        t->sim.pres_ohm = 1137.0;
        th_run_silent(t, 30);
        CHECK(t->sim.core.chain.pres == RRCH_PRES_HEAD_VIA_LAB_EXTENSION);
        t->sim.pres_ohm = 1500.0;
        th_run_silent(t, 30);
        CHECK(t->sim.core.chain.pres == RRCH_PRES_LAB_EXTENSION_ONLY);
        t->sim.pres_ohm = 300.0;
        th_run_silent(t, 30);
        CHECK(t->sim.core.chain.pres == RRCH_PRES_FAULT);
        CHECK(t->sim.core.faults & RRCH_FLT(J1_PRES_FAULT));
        CHECK(!t->sim.core.out.arm_permit);
    }

    SECTION("interlock loop window and comparator/analog discrepancy");
    {
        th_t *t = th_new(7);
        th_run_silent(t, 400);
        static const struct { double ohm; uint8_t want; } lt[] = {{599, 2}, {600, 0}, {1000, 0}, {1600, 0}, {1700, 1}, {1e9, 1}, {0, 2}};
        for (size_t i = 0; i < sizeof lt / sizeof lt[0]; i++) {
            t->sim.loop_ohm = lt[i].ohm;
            th_run_silent(t, 80);
            CHECK(t->sim.core.chain.loop_state == lt[i].want);
        }
    }

    SECTION("IB-02 node semantics: elements behind an open one are UNKNOWN, not open; no false discrepancy");
    {
        th_t *t = th_new(20);
        th_run_silent(t, 400);
        uint32_t s0 = t->sim.core.ev_newest;
        t->sim.mode_run = false; /* selector in SERVICE: CH_N1..CHAIN_END all dead */
        th_run_silent(t, 400);
        const rrch_chain_t *ch = &t->sim.core.chain;
        CHECK(ch->hw_live == RRCH_HW(MODE_NOT_RUN) || ch->hw_live == (RRCH_HW(MODE_NOT_RUN) | RRCH_HW(MCU_NOT_READY)));
        CHECK(ch->el[RRCH_EL_MODE_RUN] == RRCH_ELS_OPEN && ch->el[RRCH_EL_ESTOP] == RRCH_ELS_UNKNOWN && ch->el[RRCH_EL_HANDS_ON] == RRCH_ELS_UNKNOWN);
        CHECK(ch->el[RRCH_EL_CHG_COVER] == RRCH_ELS_UNKNOWN && ch->el[RRCH_EL_BODY_BUMPER] == RRCH_ELS_UNKNOWN && ch->el[RRCH_EL_WDG_OK] == RRCH_ELS_UNKNOWN);
        CHECK(ch->el[RRCH_EL_ARM_PERMIT] == RRCH_ELS_UNKNOWN && ch->el[RRCH_EL_HEAD_LOOP] == RRCH_ELS_CLOSED);
        CHECK(!(t->sim.core.faults & RRCH_FLT(ESTOP_DISCREPANCY)) && t->sim.core.mode == RRCH_MODE_HW_INHIBIT);
        CHECK(count_ev(t, s0, RRCH_EV_CHAIN, RRCH_DII_MODE_RUN, 0) == 1 && count_ev(t, s0, RRCH_EV_CHAIN, -1, -1) == 1); /* only the selector */
        CHECK(th_req(t, "DIAG", "{}") && th_is(t, "chain_state.MODE_RUN", "OPEN") && th_is(t, "chain_state.HANDS_ON", "UNKNOWN") && th_is(t, "chain_state.HEAD_LOOP", "CLOSED"));
        CHECK(th_req(t, "STATE", "{}") && !th_true(t, "chain.HANDS_ON") && th_true(t, "chain.HEAD_LOOP") && !th_true(t, "rearm_ready"));
        /* E-stop pressed while in SERVICE: pole B is read independently, so ESTOP is known open */
        t->sim.estop = true;
        th_run_silent(t, 300);
        CHECK(ch->el[RRCH_EL_ESTOP] == RRCH_ELS_OPEN && (ch->hw_live & RRCH_HW(ESTOP)) && !(t->sim.core.faults & RRCH_FLT(ESTOP_DISCREPANCY)));
        /* hands-on pressed behind the E-stop: unknown, and becomes a known cause (with its event) once the E-stop is released */
        t->sim.mode_run = true;
        t->sim.hands_on = true;
        th_run_silent(t, 300);
        CHECK(ch->el[RRCH_EL_HANDS_ON] == RRCH_ELS_UNKNOWN && !(ch->hw_live & RRCH_HW(HANDS_ON)));
        s0 = t->sim.core.ev_newest;
        t->sim.estop = false;
        th_run_silent(t, 300);
        CHECK(ch->el[RRCH_EL_HANDS_ON] == RRCH_ELS_OPEN && (ch->hw_live & RRCH_HW(HANDS_ON)) && count_ev(t, s0, RRCH_EV_CHAIN, RRCH_DII_HANDS_ON, 0) == 1);
        CHECK(count_ev(t, s0, RRCH_EV_CHAIN, RRCH_DII_CHG_COVER, -1) == 0 && count_ev(t, s0, RRCH_EV_CHAIN, RRCH_DII_WDG_OK, -1) == 0);
        /* body bumper behind an open head loop: unknown (CH_N6/N7 have no readback, inferred from the comparators) */
        t->sim.hands_on = false;
        t->sim.loop_ohm = 1e9;
        t->sim.bumper_r = true;
        th_run_silent(t, 300);
        CHECK(ch->el[RRCH_EL_BODY_BUMPER] == RRCH_ELS_UNKNOWN && !(ch->hw_live & RRCH_HW(BODY_BUMPER)) && (ch->hw_live & RRCH_HW(HEAD_LOOP_OPEN)));
        t->sim.loop_ohm = 1000.0;
        th_run_silent(t, 300);
        CHECK(ch->el[RRCH_EL_BODY_BUMPER] == RRCH_ELS_OPEN && (ch->hw_live & RRCH_HW(BODY_BUMPER)));
        CHECK(!(t->sim.core.faults & RRCH_FLT_FATAL_MASK));
    }

    SECTION("IB-02: charger seen through its own telemetry while the cover/plug nodes are dead (selector in SERVICE)");
    {
        th_t *t = th_new(21);
        th_run_silent(t, 400);
        th_env(t, "{\"mode_run\":false,\"chg_plug\":true}");
        th_run_silent(t, 400);
        CHECK(t->sim.core.chain.el[RRCH_EL_CHG_COVER] == RRCH_ELS_UNKNOWN && t->sim.core.mode == RRCH_MODE_SERVICE_CHARGE);
    }

    SECTION("IB-02: a node live behind a dead node (harness short, shorted photo-MOS) is a FAULT");
    {
        static const char *const env[3] = {"{\"hands_on\":true,\"chain_short\":\"CH_N4A\"}", "{\"loop_ohm\":1e9,\"chain_short\":\"CH_N6\"}", "{\"bumper_l\":true,\"chain_short\":\"CH_N8\"}"};
        for (int k = 0; k < 3; k++) {
            th_t *t = th_new(22 + (uint64_t)k);
            th_run_silent(t, 400);
            th_env(t, env[k]);
            th_run_silent(t, 15);
            CHECK(!(t->sim.core.faults & RRCH_FLT(CHAIN_IMPLAUSIBLE))); /* 20 ms filter for the tap RC and photo-MOS delays */
            th_run_silent(t, 30);
            CHECK((t->sim.core.faults & RRCH_FLT(CHAIN_IMPLAUSIBLE)) && t->sim.core.mode == RRCH_MODE_FAULT && !t->sim.core.out.arm_permit);
        }
        /* opening and closing elements in normal use never trips it */
        th_t *t = th_new(25);
        th_run_silent(t, 400);
        const char *seq[6] = {"{\"estop\":true}", "{\"estop\":false}", "{\"bumper_l\":true}", "{\"bumper_l\":false}", "{\"mode_run\":false}", "{\"mode_run\":true}"};
        for (int k = 0; k < 6; k++) {
            th_env(t, seq[k]);
            th_run_silent(t, k % 2 ? 7 : 120);
        }
        th_run_silent(t, 300);
        CHECK(!(t->sim.core.faults & RRCH_FLT_FATAL_MASK) && t->sim.core.mode == RRCH_MODE_HW_INHIBIT);
    }

    SECTION("IB-01: CHAIN_END_RB (IOX_B P17) is the readback of ARM_PERMIT");
    {
        th_t *t = th_new(30);
        th_run_silent(t, 400);
        CHECK(t->sim.core.out.arm_permit && t->sim.core.chain.chain_end && t->sim.core.chain.el[RRCH_EL_ARM_PERMIT] == RRCH_ELS_CLOSED);
        CHECK(th_req(t, "DIAG", "{}") && th_true(t, "chain_end") && th_is(t, "chain_state.ARM_PERMIT", "CLOSED"));
        /* stuck high (U24 shorted / PB10 stuck): seen at boot while ARM_PERMIT is low -> FAULT, strobe withheld,
         * the watchdog opens the chain at WDG_OK and resets the MCU (JP1) */
        t = th_new(31);
        t->sim.permit_short = true;
        th_run_silent(t, 150);
        CHECK((t->sim.core.faults & RRCH_FLT(PERMIT_STUCK_ON)) && t->sim.core.mode == RRCH_MODE_FAULT);
        uint32_t n0 = t->sim.n_strobes;
        th_run_silent(t, 20);
        CHECK(t->sim.n_strobes == n0);
        th_run_silent(t, 500);
        CHECK(t->sim.n_resets >= 1u);
        t->sim.rearm_ms = 200; /* the latch cannot be set */
        th_run_silent(t, 30);
        CHECK(!t->sim.latch);
        /* the same fault appearing later is caught at the next ARM_PERMIT low (here a brake test) */
        t = th_new(32);
        CHECK(th_arm(t, "COMMISSIONING"));
        t->sim.permit_short = true;
        th_run(t, 200);
        CHECK(!(t->sim.core.faults & RRCH_FLT(PERMIT_STUCK_ON)));
        (void)th_req(t, "BRAKE_TEST", "{}"); /* the latch cannot drop through ARM_PERMIT: the watchdog drops it */
        CHECK(!t->sim.latch && (t->sim.n_resets >= 1u || (t->sim.core.faults & RRCH_FLT(PERMIT_STUCK_ON))));
        th_run_silent(t, 100);
        CHECK(t->sim.core.faults & RRCH_FLT(PERMIT_STUCK_ON)); /* again at the next boot */
        /* stuck open (fails safe): permit commanded, CH_N9 live, CHAIN_END dead -> warning, MCU_NOT_READY, no re-arm */
        t = th_new(33);
        th_run_silent(t, 400);
        t->sim.permit_open = true;
        th_run_silent(t, 100);
        CHECK((t->sim.core.faults & RRCH_FLT(PERMIT_STUCK_OFF)) && (t->sim.core.chain.hw_live & RRCH_HW(MCU_NOT_READY)));
        CHECK(t->sim.core.chain.el[RRCH_EL_ARM_PERMIT] == RRCH_ELS_OPEN && !(t->sim.core.faults & RRCH_FLT_FATAL_MASK));
        CHECK(th_req(t, "STATE", "{}") && !th_true(t, "rearm_ready") && !th_true(t, "chain.ARM_PERMIT"));
        t->sim.permit_open = false;
        th_run_silent(t, 100);
        CHECK(!(t->sim.core.faults & RRCH_FLT(PERMIT_STUCK_OFF)));
        /* a dead CH_N9 (watchdog) explains a dead CHAIN_END: no warning */
        th_run_silent(t, 100);
        /* IOX_B not readable: the permit is withheld (never closed unsupervised) */
        t = th_new(34);
        th_run_silent(t, 400);
        t->sim.iox_b_fail = true;
        th_run_silent(t, 150);
        CHECK((t->sim.core.faults & RRCH_FLT(IOX_B)) && !t->sim.core.out.arm_permit && (t->sim.core.chain.hw_live & RRCH_HW(MCU_NOT_READY)));
        t->sim.iox_b_fail = false;
        th_run_silent(t, 50);
        CHECK(!(t->sim.core.faults & RRCH_FLT(IOX_B)) && t->sim.core.out.arm_permit);
    }

    SECTION("IB-02: BRAKE_x_RB judged only with the bridges asleep; bridges wake only after both relays read back");
    {
        th_t *t = th_new(40);
        th_run_silent(t, 300);
        CHECK(th_req(t, "HELLO", "{}"));
        t->sim.rearm_ms = 200;
        bool woke_early = false;
        for (int ms = 0; ms < 80; ms++) {
            th_run_silent(t, 1);
            if (t->sim.core.out.bridge_awake && !(t->sim.core.chain.state & RRCH_DI(BRAKE_L))) {
                woke_early = true;
            }
        }
        CHECK(t->sim.latch && !woke_early && t->sim.core.chain.relays_ok);
        uint32_t s0 = t->sim.core.ev_newest;
        th_run(t, 1000); /* armed, bridges awake (braking): the comparators read garbage */
        CHECK(t->sim.core.out.bridge_awake && count_ev(t, s0, RRCH_EV_CHAIN, RRCH_DII_BRAKE_L, -1) == 0 && count_ev(t, s0, RRCH_EV_CHAIN, RRCH_DII_BRAKE_R, -1) == 0);
        CHECK(!(t->sim.core.chain.hw_live & RRCH_HW(VMOT_FAULT)));
        /* the latch drops: hardware sleeps the bridges, the readback becomes valid and must show "braked" */
        t->sim.bumper_r = true;
        th_run_silent(t, 30);
        CHECK(!(t->sim.core.chain.state & (RRCH_DI(BRAKE_L) | RRCH_DI(BRAKE_R))) && count_ev(t, s0, RRCH_EV_CHAIN, RRCH_DII_BRAKE_L, 0) == 1);
    }

    SECTION("IB-05: INA228 / INA3221 decode against datasheet values; LTC4162 stays disabled (UNVERIFIED)");
    {
        /* INA3221 SBOS576C 8.2.2 worked example: VSHUNT = -80 mV -> C180h */
        uint8_t b2[2] = {0xC1, 0x80};
        CHECK(fabsf(rr_ina3221_shunt_v(b2) + 0.080f) < 1e-6f);
        rr_ina3221_encode_shunt(-0.080, b2);
        CHECK(b2[0] == 0xC1 && b2[1] == 0x80);
        uint8_t fs[2] = {0x7F, 0xF8}; /* full scale 163.8 mV / 32.76 V (decimal 7FF8) */
        CHECK(fabsf(rr_ina3221_shunt_v(fs) - 0.1638f) < 1e-5f && fabsf(rr_ina3221_bus_v(fs) - 32.76f) < 1e-3f);
        uint8_t mfr[2] = {0x54, 0x49}, die[2] = {0x32, 0x20}, bad[2] = {0x22, 0x81};
        CHECK(rr_ina3221_id_ok(mfr, die) && !rr_ina3221_id_ok(mfr, bad));
        /* INA228 SLYS021A: equation (2) x4 at ADCRANGE 1; DEVICE_ID reset 2281h */
        CHECK(rr_ina228_shunt_cal(RR_PMON_CURRENT_LSB, RR_PMON_SHUNT_OHM, true) == 5243u);
        CHECK(rr_ina228_shunt_cal(RR_PMON_CURRENT_LSB, RR_PMON_SHUNT_OHM, false) == 1311u);
        CHECK(rr_ina228_id_ok(mfr, bad) && !rr_ina228_id_ok(mfr, die));
        uint8_t b3[3];
        rr_ina228_encode_s20(66560, b3); /* 13.0 V / 195.3125 uV */
        CHECK(fabsf(rr_ina228_vbus_v(b3) - 13.0f) < 1e-4f);
        rr_ina228_encode_s20(-12345, b3);
        CHECK(rr_ina228_s20(b3) == -12345 && fabsf(rr_ina228_current_a(b3, 1e-4) + 1.2345f) < 1e-5f);
        uint8_t t2[2] = {0x0C, 0x80}; /* 3200 x 7.8125 m degC = 25 C */
        CHECK(fabsf(rr_ina228_dietemp_c(t2) - 25.0f) < 1e-4f);
        uint8_t q5[5] = {0xFF, 0xFF, 0xFF, 0xFF, 0xF6}; /* -10 LSB */
        CHECK(fabs(rr_ina228_charge_c(q5, 1e-4) + 1e-3) < 1e-12);
        CHECK(RR_LTC4162_REGMAP_VERIFIED == 0 && rr_ltc4162_regs_unverified_n > 0u);
        /* in the emulator the telemetry runs through the same decode; loss raises the warnings, nothing unsafe */
        th_t *t = th_new(50);
        th_run_silent(t, 2600);
        CHECK(!(t->sim.core.faults & (RRCH_FLT(PMON_COMM) | RRCH_FLT(CHARGER_COMM))) && fabsf(t->sim.core.pwr.vbat_pmon_v - 13.0f) < 0.01f);
        CHECK(th_req(t, "STATE", "{}") && fabs(th_num(t, "rails.ibat_a") - 0.9) < 0.02 && th_num(t, "rails.i_head_a") == 0.0);
        th_env(t, "{\"pmon_fail\":true,\"branch_fail\":true,\"charger_fail\":true}");
        th_run_silent(t, 300);
        CHECK((t->sim.core.faults & RRCH_FLT(PMON_COMM)) && (t->sim.core.faults & RRCH_FLT(CHARGER_COMM)) && !(t->sim.core.faults & RRCH_FLT_FATAL_MASK));
        CHECK(th_req(t, "STATE", "{}") && rrc_json_is_null(&t->doc, th_get(t, "rails.ibat_a")) && rrc_json_is_null(&t->doc, th_get(t, "rails.i_head_htr_a")));
    }

    SECTION("stop model: v_cap is the inverse of the stopping distance");
    {
        rrch_cfg_t cfg;
        rrch_cfg_defaults(&cfg);
        for (float v = 0.01f; v <= 0.2001f; v += 0.01f) {
            float d = rrch_stop_distance(&cfg, v);
            CHECK(fabsf(rrch_stop_vcap(&cfg, d) - v) < 1e-4f);
        }
        CHECK(rrch_stop_vcap(&cfg, 0.020f) == 0.0f);
        CHECK(rrch_stop_vcap(&cfg, 0.0f) == 0.0f);
        CHECK(fabsf(rrch_stop_distance(&cfg, 0.20f) - 0.100f) < 1e-5f);
        CHECK(fabsf(rrch_stop_distance(&cfg, 0.05f) - 0.030625f) < 1e-5f);
    }

    SECTION("configuration image: round trip, CRC, version, unknown and out-of-range entries");
    {
        rrch_cfg_t a, b;
        uint8_t img[RRCH_NV_MAX];
        rrch_cfg_defaults(&a);
        a.v[RRCH_CFG_CAL_TRACK] = 0.2713f;
        a.gen = 41;
        size_t n = rrch_cfg_pack(&a, img, sizeof img);
        CHECK(n > 0 && n <= RRCH_NV_MAX);
        CHECK(rrch_cfg_unpack(&b, img, n) && b.gen == 41 && b.v[RRCH_CFG_CAL_TRACK] == 0.2713f && b.from_flash);
        img[40] ^= 0x01;
        CHECK(!rrch_cfg_unpack(&b, img, n)); /* CRC */
        img[40] ^= 0x01;
        CHECK(!rrch_cfg_unpack(&b, img, n - 1));
        img[4] = 99; /* layout version */
        CHECK(!rrch_cfg_unpack(&b, img, n));
        for (int i = 0; i < RRCH_CFG_N; i++) { /* every default is inside its own limits and every name is unique */
            CHECK(rrch_cfg_desc[i].def >= rrch_cfg_desc[i].min && rrch_cfg_desc[i].def <= rrch_cfg_desc[i].max);
            CHECK(rrch_cfg_find(rrch_cfg_desc[i].name) == i);
        }
        /* hard ceilings of the contract cannot be exceeded through configuration */
        CHECK(rrch_cfg_desc[RRCH_CFG_CAP_COM_VF].max <= RRCH_MAX_V_FWD && rrch_cfg_desc[RRCH_CFG_CAP_SUN_VF].max <= RRCH_MAX_V_FWD);
        CHECK(rrch_cfg_desc[RRCH_CFG_CAP_COM_VR].max <= RRCH_MAX_V_REV && rrch_cfg_desc[RRCH_CFG_CAP_COM_W].max <= RRCH_MAX_W);
        CHECK(rrch_cfg_desc[RRCH_CFG_DRV_ACCEL].max <= RRCH_MAX_ACCEL);
    }
    return th_summary("test_chain");
}
