/* Host port: plant model + HAL for the real chassis core. Used by rr_chassis_sim (TCP/UDP
 * front end in sim_main.c) and linked directly into the unit tests. All results obtained with
 * it are SIMULATED; the plant parameters are datasheet-level estimates, not measurements. */
#ifndef RR_CHASSIS_SIM_H
#define RR_CHASSIS_SIM_H
#include "rrch.h"

typedef struct {
    /* motor + vehicle parameters */
    double R, L, Ke, Kt, J, mass, Iz, r, track, tau_c, b_visc, R_brake;
} sim_params_t;

typedef struct {
    sim_params_t p;
    uint64_t t_us;
    uint64_t rng;
    /* plant state */
    double w[2], th[2], i[2];       /* wheel speed rad/s, wheel angle rad, motor current A (left, right) */
    double x, y, yaw, v, wz, acc;   /* ground truth */
    double vmot;
    bool latch, relay[2];
    int latch_drop_ms, latch_set_ms, relay_ms[2];
    /* environment */
    bool mode_run, estop, hands_on, chg_cover_open, chg_plug, head_docked, bumper_l, bumper_r, j2;
    double pres_ohm, loop_ohm, vbat, soc, temp[3], tilt_deg;
    int32_t tof_mm[RRCH_TOF_N];
    rrch_tof_status_t tof_st[RRCH_TOF_N];
    bool tof_stale[RRCH_TOF_N];
    int rearm_ms, pause_ms;
    /* fault injection */
    bool enc_dropout[2], block[2], usb_stall, usb_down, imu_off, iox_fail, latch_weld, estop_a_stuck;
    bool freeze_control, freeze_supervisor, freeze_background;
    double slip[2];
    uint8_t efuse_fault;
    /* watchdog model */
    uint64_t last_strobe_us, wdg_arm_us;
    bool wdg_ok;
    int wdg_reset_ms;
    uint32_t n_strobes, n_resets;
    /* link byte queues (CDC stream) */
    uint8_t rx[16384];
    size_t rx_len;
    uint8_t tx[32768];
    size_t tx_len;
    /* non-volatile + retained RAM */
    uint8_t nv[3][RRCH_NV_MAX];
    size_t nv_len[3];
    bool nv_fail;
    rrch_retained_t retained;
    rrch_reset_cause_t reset_cause;
    uint16_t enc_raw[2];
    double enc_frozen[2];
    rrch_t core;
} sim_t;

void sim_init(sim_t *s, uint64_t seed);
void sim_step_ms(sim_t *s);                                /* advance 1 ms of simulated time */
void sim_mcu_reset(sim_t *s, rrch_reset_cause_t cause);
void sim_host_write(sim_t *s, const uint8_t *buf, size_t len); /* bytes from the host */
size_t sim_host_read(sim_t *s, uint8_t *buf, size_t cap);      /* bytes to the host */
/* Apply one environment JSON object (see README "Emulator"). Returns false on a parse error. */
bool sim_env_apply(sim_t *s, const char *json, size_t len);
/* Ground-truth JSON line for the environment socket. Returns the length. */
size_t sim_truth_json(const sim_t *s, char *buf, size_t cap);

#endif
