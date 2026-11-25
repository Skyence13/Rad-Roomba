/* Chain supervision: presence-code decode incl. boundaries, debounce, event latching of short
 * pulses, stop model, configuration image. SIMULATED inputs on the host port. */
#include <math.h>
#include <string.h>

#include "harness.h"

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
        a.v[RRCH_CFG_CAL_TRACK] = 0.2213f;
        a.gen = 41;
        size_t n = rrch_cfg_pack(&a, img, sizeof img);
        CHECK(n > 0 && n <= RRCH_NV_MAX);
        CHECK(rrch_cfg_unpack(&b, img, n) && b.gen == 41 && b.v[RRCH_CFG_CAL_TRACK] == 0.2213f && b.from_flash);
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
