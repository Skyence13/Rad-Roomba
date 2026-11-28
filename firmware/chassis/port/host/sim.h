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
enum { SIM_N1 = 1, SIM_N2, SIM_N3, SIM_N4A, SIM_N4, SIM_N5, SIM_N6A, SIM_N6, SIM_N7, SIM_N8A, SIM_N8, SIM_N9, SIM_NEND, SIM_NODES };

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
    bool node[SIM_NODES];           /* chain node really live (index SIM_N1..SIM_NEND) */
    bool held[SIM_NODES];           /* node held up only by C_SET back-feed through R_SET (review M1) */
    double v_held;                  /* voltage of the held nodes */
    bool pole_b;
    bool run12;                     /* RUN_12V (HW_LATCH_RB taps it) = RUN_HD through D_RUN, or a short */
    /* stage 3 (electronics/analysis/chassis_safety_chain.md 2.1): K1 armature, K1_RUN = CHAIN_END through K1 pole B,
     * U_HOLD (self-holding photo-MOS, set only by the set pulse), RUN_HD = K1_RUN through U_HOLD; s->latch = RUN_HD */
    bool k1, k1_run, u_hold, run_hd, set_prev, u_set;
    double set_pulse_s;             /* edge-triggered gate pulse of the set stage (110 ms) */
    bool rearm_aux_short, rearm_set_short; /* REARM contact lines held closed (welded contact / W-018 short) */
    bool rail_weld, loop_sns_leak, bumper_l_weld, run_hd_short, k1_run_short, chain_end_short, uhold_short, loop_b_stuck_ok, loop_b_stuck_open, iox_d_fail, iox_d_bad_pattern;
    double vc;                      /* C_SET voltage */
    double k1_on_s, k1_pulse_s;     /* K1 coil energised time (pick-up), time since the REARM press (set pulse) */
    /* review fault models (selectable) */
    int k1_fault;                   /* 1 seal-in contact welded: coil follows CHAIN_END; 2 K1_SET shorted to V12_AUX in W-018 */
    bool run12_short;               /* RUN_12V shorted to a supply on the board (M6) */
    bool loop_cmp_stuck;            /* U30A cannot pull HEAD_LOOP_OK_RB low (pin 1 open, R74 short, pin 7-8 bridge) (C2) */
    bool iox_drive_loop;            /* IOX_A GPA5 configured as an output driving HEAD_LOOP_OK_RB high (M2) */
    bool io_cfg_fault;              /* a tap pin / expander direction reads back wrong (M2/M3) */
    bool cset_diode;                /* stage-3 option: diode in series with R_SET, no back-feed */
    double vmot_tau_s;              /* VMOT bleed time constant (1 kOhm x bulk capacitance), default 0.81 s */
    bool cset_energy;               /* REARM sets K1 only from a charged C_SET (T11 coil-current model); false = any press sets */
    /* round 4 (N1/N2, T11): set stage parameters and fault models */
    double cset_uf;                 /* C_SET capacitance, default 100 uF (T11: -20 % tolerance) */
    double k1_coil_c;               /* K1 coil temperature; NAN = board temperature (temp_board) */
    double k1_pickup_ms;            /* K1 operate time, default 3 ms (T11: 4 ms max) */
    bool uhold_open;                /* U_HOLD LED open: K1 can close on a set pulse but RUN_HD never comes */
    int iox_d_period_ms;            /* 0: IOX_D read every 1 ms when rrch_iox_d_fast() asks, else 10 ms; >0 forced period */
    /* stage 4 (G1, G2, G4, G5, G8, G12) */
    double rset_ohm;                /* R_SET, default 15 k (G2) */
    double set_ready_v;             /* SET_READY rising threshold, default 10.8 V (falls at 9.3 V) */
    double set_qual_ms;             /* set-contact closure before a set pulse can start, default 6 ms (3.2-11.2 ms, T13) */
    bool set_ready, q_setc, set_ready_stuck; /* comparator output, third stack FET, comparator stuck high (fault) */
    int qsetc_on_ms, qsetc_off_ms, ce_dead_ms, set_closed_ms;
    bool u21_short, u21b_short;     /* loop photo-MOS U21 (channel A) / U21B (channel B) conducting whatever the channel says */
    double loop_b_ohm;              /* channel B threshold, default 1890 ohm (G7) */
    uint8_t iox_d_out;              /* IOX_D output register as written by the port (P4 LOOP_TEST_A, P7 LOOP_TEST_B) */
    /* stage-4 review: analog levels the emulator used to treat as logic, and stuck test FETs */
    bool lta_stuck, ltb_stuck;      /* Q_LTA / Q_LTB D-S short (S4) */
    double set_rb_v, v3v3;          /* GPB6 high level with the set contact closed (2.80 V nominal, 2.76-2.83 V) and the 3V3
                                     * rail: reads high only above VIH(max) = 0.8 x 3V3 (S3) */
    double board_ntc_rise_k;        /* RT1 reading above temp_board (0: stage 5 H2, RT1 beside K1; >0 models the stage-4 position) */
    bool analog_from_loop_f;        /* stage-4 option: analog loop copy from LOOP_F (follows Q_LTA); default false = LOOP_SNS (H3) */
    double coil_heat_k;             /* K1 coil self-heating: 10 K x latch-set state, first order, tau 300 s (stage 5 H2) */
    /* TPS3430 window watchdog: WDI edges counted per wdi_mode (0 falling, 1 rising, 2 both); a counted edge
     * closer than 2.2 ms to the previous one or none for 23.4 ms (tWDU min) asserts WDO for 200 ms; with
     * JP1 closed WDO also holds NRST, so the MCU sits in reset for those 200 ms */
    bool wdi;
    uint8_t wdi_mode;
    uint64_t wdi_last_us;
    int wdo_low_ms;
    bool jp1_open, mcu_in_reset;
    /* environment */
    bool mode_run, estop, hands_on, chg_cover_open, chg_plug, head_docked, bumper_l, bumper_r, j2;
    double pres_ohm, loop_ohm, vbat, soc, temp[3], tilt_deg;
    int32_t tof_mm[RRCH_TOF_N];
    rrch_tof_status_t tof_st[RRCH_TOF_N];
    bool tof_stale[RRCH_TOF_N];
    int rearm_ms, pause_ms;
    int usb_down_ms;                /* timed link outage (host scenario s15): usb_down for this long, then restored */
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
    bool wdg_ok;
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
