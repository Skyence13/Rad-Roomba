/* Drive loop on the plant model: step response, stop distances, odometry consistency.
 * Every number printed here is SIMULATED on port/host/sim.c (datasheet-level motor model). */
#include <math.h>
#include <string.h>

#include "harness.h"

#define TICKS_PER_M (RRCH_ENCODER_CPR / (2.0 * 3.14159265358979 * (double)rrch_cfg_desc[RRCH_CFG_CAL_RADIUS_L].def))
#define TRACK_M ((double)rrch_cfg_desc[RRCH_CFG_CAL_TRACK].def)

static FILE *g_report;
static void rep(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
#include <stdarg.h>
static void rep(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
    if (g_report) {
        va_start(ap, fmt);
        vfprintf(g_report, fmt, ap);
        va_end(ap);
    }
}

/* Starts the motion (through the pre-motion alert) and returns once the wheels begin to move. */
static void start_motion(th_t *t, double v, double w)
{
    for (int k = 0; k < 200 && t->sim.core.drive.motion != RRCH_MOTION_RUN; k++) {
        (void)th_drive(t, v, w, 200, "COMMISSIONING");
        th_run_silent(t, 19);
    }
}

static void step_response(double v_cmd)
{
    th_t *t = th_new(11);
    CHECK(th_arm(t, "COMMISSIONING"));
    start_motion(t, v_cmd, 0.0);
    double t10 = -1, t90 = -1, peak = 0, sum = 0;
    int n = 0;
    /* the set-point itself ramps at 0.30 m/s^2, so rise time is dominated by the ramp */
    for (int ms = 0; ms < 3000; ms++) {
        if (ms % 20 == 0) {
            (void)th_drive(t, v_cmd, 0.0, 200, "COMMISSIONING");
        } else {
            th_run_silent(t, 1);
        }
        double v = t->sim.v;
        if (t10 < 0 && v >= 0.1 * v_cmd) {
            t10 = ms;
        }
        if (t90 < 0 && v >= 0.9 * v_cmd) {
            t90 = ms;
        }
        if (v > peak) {
            peak = v;
        }
        if (ms >= 2000) {
            sum += v;
            n++;
        }
    }
    double ss = sum / n, ramp_ms = v_cmd / 0.30 * 1000.0;
    rep("step to %.2f m/s: rise 10-90%% %.0f ms (set-point ramp alone: %.0f ms), overshoot %.1f %%, steady-state %.4f m/s (error %.2f %%)\n", v_cmd, t90 - t10,
        0.8 * ramp_ms, (peak - v_cmd) / v_cmd * 100.0, ss, (ss - v_cmd) / v_cmd * 100.0);
    CHECK(t90 > 0 && (t90 - t10) < 0.8 * ramp_ms + 150.0);
    CHECK((peak - v_cmd) / v_cmd < 0.08);
    CHECK(fabs(ss - v_cmd) / v_cmd < 0.02);
    CHECK(fabs(t->sim.i[0]) < 2.6 && fabs(t->sim.i[1]) < 2.6);
}

typedef enum { STOP_ZERO_CMD, STOP_CONTROLLED, STOP_PROTECTIVE, STOP_CMD_TIMEOUT, STOP_ESTOP, STOP_BUMPER } stop_kind_t;

static double stop_distance(stop_kind_t kind, const char *label, double limit_m)
{
    th_t *t = th_new(21);
    CHECK(th_arm(t, "COMMISSIONING"));
    start_motion(t, 0.20, 0.0);
    th_drive_for(t, 0.20, 0.0, 2000, "COMMISSIONING");
    CHECK(fabs(t->sim.v - 0.20) < 0.01);
    double x0 = t->sim.x, v0 = t->sim.v;
    uint64_t t0 = t->sim.t_us;
    switch (kind) {
    case STOP_ZERO_CMD: (void)th_drive(t, 0.0, 0.0, 200, "COMMISSIONING"); break;
    case STOP_CONTROLLED: (void)th_req(t, "STOP", "{\"kind\":\"CONTROLLED\"}"); break;
    case STOP_PROTECTIVE: (void)th_req(t, "STOP", "{\"kind\":\"PROTECTIVE\"}"); break;
    case STOP_CMD_TIMEOUT: break; /* simply stop sending: the last command had ttl 200 ms */
    case STOP_ESTOP: th_env(t, "{\"estop\":true}"); break;
    case STOP_BUMPER: th_env(t, "{\"bumper_l\":true}"); break;
    }
    int ms = 0;
    for (; ms < 3000; ms++) {
        if (kind == STOP_ZERO_CMD && ms % 20 == 19) {
            (void)th_drive(t, 0.0, 0.0, 200, "COMMISSIONING");
        } else if (kind != STOP_CMD_TIMEOUT && ms % 200 == 199) {
            (void)th_req(t, "TIME", "{}");
        } else {
            th_run_silent(t, 1);
        }
        if (fabs(t->sim.v) < 0.001 && ms > 20) {
            break;
        }
    }
    double d = t->sim.x - x0, ts = (double)(t->sim.t_us - t0) * 1e-6;
    rep("stop from %.3f m/s, %-34s: distance %6.1f mm, time %4.0f ms\n", v0, label, d * 1000.0, ts * 1000.0);
    CHECK(d < limit_m);
    CHECK(ms < 3000);
    th_run(t, 500);
    CHECK(fabs(t->sim.v) < 0.001); /* stays at rest */
    return d;
}

static void odometry(double v, double w, int ms, double slip_l, const char *label)
{
    th_t *t = th_new(31);
    CHECK(th_arm(t, "COMMISSIONING"));
    t->sim.slip[0] = slip_l;
    double x = t->sim.x, y = t->sim.y, yaw = t->sim.yaw, x0 = x, y0 = y;
    int64_t pl = 0, pr = 0;
    bool first = true;
    uint64_t last_t = 0;
    for (int k = 0; k < ms + 4000; k += 20) { /* 50 Hz host: integrate tick differences from the DRIVE replies */
        bool run = k < ms + 1600;
        (void)th_drive(t, run ? v : 0.0, run ? w : 0.0, 200, "COMMISSIONING");
        int64_t l = (int64_t)th_num(t, "odom.left_ticks"), r = (int64_t)th_num(t, "odom.right_ticks");
        uint64_t tu = (uint64_t)th_num(t, "odom.t_us");
        CHECK(tu >= last_t && tu <= t->sim.t_us && t->sim.t_us - tu <= 11000u); /* stamped at the sample, at most one period old */
        last_t = tu;
        if (!first) {
            double dl = (double)(l - pl) / TICKS_PER_M, dr = (double)(r - pr) / TICKS_PER_M;
            double ds = 0.5 * (dl + dr), dy = (dr - dl) / TRACK_M;
            x += ds * cos(yaw + 0.5 * dy);
            y += ds * sin(yaw + 0.5 * dy);
            yaw += dy;
        }
        first = false;
        pl = l;
        pr = r;
        th_run_silent(t, 19);
    }
    double path = hypot(t->sim.x - x0, t->sim.y - y0);
    double err = hypot(x - t->sim.x, y - t->sim.y), yerr = fabs(yaw - t->sim.yaw);
    rep("odometry %-28s: travelled %.3f m (chord), turned %.3f rad; integrated-ticks vs ground truth: position %.2f mm, yaw %.4f rad\n", label, path,
        t->sim.yaw, err * 1000.0, yerr);
    if (slip_l == 0.0) {
        CHECK(err < 0.002);
        CHECK(yerr < 0.002);
        /* cumulative ticks equal the true wheel angle within one count */
        CHECK(fabs((double)pl - floor(t->sim.th[0] * RRCH_ENCODER_CPR / (2.0 * 3.14159265358979))) <= 1.0);
    } else {
        CHECK(err > 0.005); /* slip is not observable by encoders: the error must show up, not be hidden */
    }
}

/* IB-03: latch drop (E-stop) on the plant alone, firmware not stepped, bridges driving the steady-state duty
 * until K1 releases. Two parameter sets from electronics/analysis/chassis_braking.py. Distance from the moment
 * the chain opens to rest. Reference: the same script's brake() + 10.5 ms dead time (chassis_braking_tables.md T3;
 * the 0.30 m/s value is computed with brake() because T3 stops at 0.20 m/s). */
static void latch_drop_study(void)
{
    static const double v0s[3] = {0.10, 0.20, 0.30};
    static const double ref[2][3] = {{3.76, 8.71, 13.91}, {14.25, 28.50, 42.75}};
    static const char *const nm[2] = {"nominal", "conservative"};
    rep("latch drop (E-stop) on the plant, distance from chain opening to rest [SIMULATED] vs electronics chassis_braking.py [calculated]:\n");
    for (int c = 0; c < 2; c++) {
        for (int k = 0; k < 3; k++) {
            th_t *t = th_new(51);
            sim_t *s = &t->sim;
            th_run_silent(t, 50);
            s->plant_only = true;
            if (c == 0) {
                sim_params_nominal(&s->p);
            } else {
                sim_params_conservative(&s->p);
            }
            const sim_params_t *p = &s->p;
            double w = v0s[k] / p->r, i_ss = p->tau_c / p->Kt;
            s->latch = true;
            s->vmot = s->vbat;
            for (int j = 0; j < 2; j++) {
                s->rstate[j] = 1;
                s->relay[j] = true;
                s->w[j] = w;
                s->i[j] = i_ss;
                s->core.out.duty[j] = (float)((p->Ke * w + p->R * i_ss) / s->vmot);
            }
            s->core.out.arm_permit = true;
            s->core.out.bridge_awake = true;
            th_run_silent(t, 30);
            double v_start = s->v, x0 = s->x;
            uint64_t t0 = s->t_us;
            s->estop = true;
            int ms = 0;
            for (; ms < 4000 && s->v > 1e-5; ms++) {
                th_run_silent(t, 1);
            }
            double d = (s->x - x0) * 1000.0, dev = (d - ref[c][k]) / ref[c][k] * 100.0;
            rep("  %-12s v0 %.2f m/s (plant %.3f): %5.1f mm in %4.0f ms; electronics %5.1f mm; difference %+5.1f %%\n", nm[c], v0s[k], v_start, d,
                (double)(s->t_us - t0) * 1e-3, ref[c][k], dev);
            CHECK(fabs(v_start - v0s[k]) < 0.003);
            CHECK(fabs(dev) < 10.0);
        }
    }
}

int main(int argc, char **argv)
{
    if (argc > 1) {
        g_report = fopen(argv[1], "w");
    }
    rep("# rr_chassis drive-loop report - SIMULATED on the host plant model (no hardware)\n");
    SECTION("step response");
    step_response(0.10);
    step_response(0.20);

    SECTION("stop distance from 0.20 m/s");
    rrch_cfg_t cfg;
    rrch_cfg_defaults(&cfg);
    double model = rrch_stop_distance(&cfg, 0.20f);
    rep("contract stop model d = v*t_delay + v^2/(2*a_min) + m at 0.20 m/s: %.1f mm (t_delay 0.15 s, a_min 0.40 m/s^2, m 20 mm)\n", model * 1000.0);
    CHECK(fabs(model - 0.100) < 1e-4);
    double d_zero = stop_distance(STOP_ZERO_CMD, "DRIVE v=0 (ramp 0.40 m/s^2)", model);
    double d_ctl = stop_distance(STOP_CONTROLLED, "STOP CONTROLLED (ramp 0.40 m/s^2)", model);
    double d_ps = stop_distance(STOP_PROTECTIVE, "STOP PROTECTIVE (ramp 1.0 m/s^2)", model);
    double d_to = stop_distance(STOP_CMD_TIMEOUT, "command TTL 200 ms expiry", 0.20 * 0.2 + model);
    double d_es = stop_distance(STOP_ESTOP, "E-stop: latch drop, brake resistor", model);
    double d_bu = stop_distance(STOP_BUMPER, "body bumper: latch drop", model);
    CHECK(d_ps < d_ctl && d_es < d_ctl);
    rep("margin to the contract model: controlled %.1f mm, protective %.1f mm, latch drop %.1f mm (TTL case adds up to v*ttl = 40 mm before the ramp)\n",
        (model - d_ctl) * 1000.0, (model - d_ps) * 1000.0, (model - d_es) * 1000.0);
    (void)d_zero;
    (void)d_to;
    (void)d_bu;

    SECTION("latch-drop stop distances, nominal and conservative electronics brake model (IB-03)");
    latch_drop_study();

    SECTION("odometry consistency");
    odometry(0.20, 0.0, 5000, 0.0, "straight 0.20 m/s");
    odometry(0.10, 0.25, 8000, 0.0, "arc 0.10 m/s, 0.25 rad/s");
    odometry(0.0, 0.30, 6000, 0.0, "pivot 0.30 rad/s");
    odometry(-0.05, 0.0, 4000, 0.0, "reverse 0.05 m/s");
    odometry(0.10, 0.0, 5000, 0.05, "straight, 5 % left wheel slip");

    SECTION("current limit and stall");
    {
        th_t *t = th_new(41);
        CHECK(th_arm(t, "COMMISSIONING"));
        start_motion(t, 0.20, 0.0);
        th_drive_for(t, 0.20, 0.0, 600, "COMMISSIONING");
        th_env(t, "{\"block\":\"BOTH\"}");
        double imax = 0;
        int ms = 0;
        for (; ms < 1500 && !(t->sim.core.sw_latched & RRCH_SW(STALL)); ms++) {
            if (ms % 20 == 0) {
                (void)th_drive(t, 0.20, 0.0, 200, "COMMISSIONING");
            } else {
                th_run_silent(t, 1);
            }
            if (ms > 100 && fabs(t->sim.i[0]) > imax) {
                imax = fabs(t->sim.i[0]);
            }
        }
        rep("blocked wheels at 0.20 m/s: STALL latched after %d ms, peak motor current after fold-back %.2f A (limit 2.5 A, stall current 5.5 A)\n", ms, imax);
        CHECK(t->sim.core.sw_latched & RRCH_SW(STALL));
        CHECK(ms < 900);
        CHECK(imax < 3.2);
    }
    if (g_report) {
        fclose(g_report);
    }
    return th_summary("test_drive");
}
