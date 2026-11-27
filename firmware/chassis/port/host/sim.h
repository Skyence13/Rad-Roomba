/* Host port: plant model + HAL for the real chassis core. Used by rr_chassis_sim (TCP/UDP
 * front end in sim_main.c) and linked directly into the unit tests. All results obtained with
 * it are SIMULATED; the plant parameters are datasheet-level estimates, not measurements. */
#ifndef RR_CHASSIS_SIM_H
#define RR_CHASSIS_SIM_H
#include "rrch.h"

typedef struct {
    /* motor + vehicle parameters, per wheel and referred to the wheel shaft (IB-03: source
     * electronics/analysis/chassis_braking.py, see sim_params_nominal / sim_params_conservative) */
    double R, L, Ke, Kt, J, mass, Iz, r, track, tau_c, b_visc, R_brake, R_path;
    double i_trip;                  /* bridge hardware current chop, A (CCR-E03 b: 2.68 A) */
    double ipropi_fs_a;             /* IPROPI ADC full scale, A (3.000 V / 1.1205 V/A) */
} sim_params_t;

/* chain nodes of the emulator (electronics/analysis/chassis_safety_chain.md 2.1) */
enum { SIM_N1 = 1, SIM_N2, SIM_N3, SIM_N4A, SIM_N4, SIM_N5, SIM_N6, SIM_N7, SIM_N8A, SIM_N8, SIM_N9, SIM_NEND, SIM_NODES };

typedef struct {
    sim_params_t p;
    uint64_t t_us;                  /* simulated (plant) time */
    uint64_t boot_us;               /* plant time of the last MCU boot: chassis clock = t_us - boot_us */
    uint64_t rng;
    /* plant state */
    double w[2], th[2], i[2];       /* wheel speed rad/s, wheel angle rad, motor current A (left, right) */
    double x, y, yaw, v, wz, acc;   /* ground truth */
    double vmot;
    bool latch, relay[2];           /* K1 contact (RUN_12V) / brake relay NO contacts closed (motor on the bridge) */
    uint8_t rstate[2];              /* 0 braked (NC closed), 1 connected (NO closed), 2 in transfer (both open) */
    int latch_set_ms;
    double k1_off_s, relay_t_s[2];  /* time since the coil supply went away / came back */
    bool node[SIM_NODES];           /* chain node live (index SIM_N1..SIM_NEND) */
    bool pole_b;
    /* environment */
    bool mode_run, estop, hands_on, chg_cover_open, chg_plug, head_docked, bumper_l, bumper_r, j2;
    double pres_ohm, loop_ohm, vbat, soc, temp[3], tilt_deg;
    int32_t tof_mm[RRCH_TOF_N];
    rrch_tof_status_t tof_st[RRCH_TOF_N];
    bool tof_stale[RRCH_TOF_N];
    int rearm_ms, pause_ms;
    /* fault injection */
    bool enc_dropout[2], block[2], usb_stall, usb_down, imu_off, iox_fail, latch_weld, estop_a_stuck;
    bool iox_b_fail, permit_short, permit_open; /* IOX_B not answering; ARM_PERMIT photo-MOS U24 shorted / open */
    bool pmon_fail, branch_fail, charger_fail; /* INA228 / INA3221 / charger not answering */
    int chain_short;                /* node shorted to a live conductor (SIM_N1..SIM_NEND), 0 = none */
    bool plant_only;                /* firmware not stepped, watchdog model off (stop-distance studies) */
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
    /* real-time pacing diagnostics of rr_chassis_sim (IB-47): lag of simulated behind scaled wall time when the
     * last batch of steps started, and the number of times the pacing gave up catching up (time base reset) */
    uint64_t emu_lag_us;
    uint32_t emu_rebases;
    rrch_t core;
} sim_t;

void sim_init(sim_t *s, uint64_t seed);
void sim_params_nominal(sim_params_t *p);       /* chassis_braking.py "nominal" case (default plant) */
void sim_params_conservative(sim_params_t *p);  /* chassis_braking.py "conservative" case */
void sim_step_ms(sim_t *s);                                /* advance 1 ms of simulated time */
void sim_mcu_reset(sim_t *s, rrch_reset_cause_t cause);
void sim_host_write(sim_t *s, const uint8_t *buf, size_t len); /* bytes from the host */
size_t sim_host_read(sim_t *s, uint8_t *buf, size_t cap);      /* bytes to the host */
/* Apply one environment JSON object (see README "Emulator"). Returns false on a parse error. */
bool sim_env_apply(sim_t *s, const char *json, size_t len);
/* Ground-truth JSON line for the environment socket. Returns the length. */
size_t sim_truth_json(const sim_t *s, char *buf, size_t cap);

#endif
