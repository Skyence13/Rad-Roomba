/* Rad Roomba chassis firmware core (RR-CHS 1.0) - hardware independent C11.
 *
 * NOT a certified safety controller. The hardwired traction chain works without this code;
 * this code never opposes it, supervises it and adds the software protective-stop layer.
 * Interface document: interface/chassis_icd.md. Ports: port/host (emulator), port/stm32g474.
 */
#ifndef RRCH_H
#define RRCH_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "rr_common.h"

#define RRCH_FW_VERSION "rr-chassis 0.4.0"
#ifndef RRCH_FW_SUFFIX
#define RRCH_FW_SUFFIX ""
#endif
#define RRCH_PROTO "RR-CHS 1.0"
#define RRCH_PROTO_V "1.0"
#define RRCH_TOF_N 11
#define RRCH_EVENTS_N 128u
#define RRCH_RECORD_MAX RRC_CHASSIS_MAX_RECORD
#define RRCH_ENCODER_CPR 9600
#define RRCH_TTL_MAX_MS 250u
/* contract.yaml motion: hard ceilings */
#define RRCH_MAX_V_FWD 0.20f
#define RRCH_MAX_V_REV 0.05f
#define RRCH_MAX_W 0.30f
#define RRCH_MAX_ACCEL 0.30f

/* ---- enumerations (names spelled as in contract.yaml enums) ---- */
#define RRCH_MODE_LIST(X) X(BOOT) X(SERVICE_CHARGE) X(LAB) X(STANDBY) X(ARMED_IDLE) X(MOVING) X(HOLD) X(PROTECTIVE_STOP) X(HW_INHIBIT) X(FAULT)
#define RRCH_HW_LIST(X) X(MODE_NOT_RUN) X(ESTOP) X(HANDS_ON) X(CHARGER) X(HEAD_UNDOCKED) X(HEAD_LOOP_OPEN) X(HEAD_LOOP_SHORT) X(J1_ABSENT) X(LAB_KEY) X(BODY_BUMPER) X(WATCHDOG) X(MCU_NOT_READY) X(VMOT_FAULT) X(LATCH_UNEXPLAINED) X(REARM_HELD)
#define RRCH_SW_LIST(X) X(FIELD_FRONT) X(FIELD_REAR) X(FIELD_LEFT) X(FIELD_RIGHT) X(CLIFF_FL) X(CLIFF_FR) X(CLIFF_RL) X(CLIFF_RR) X(LOOKAHEAD_L) X(LOOKAHEAD_R) X(TOF_STALE) X(TOF_DISAGREE) X(CMD_TIMEOUT) X(HOST_LINK_LOST) X(STALL) X(ENCODER_FAULT) X(IMU_FAULT) X(TILT) X(BATTERY_LOW) X(TEMP_RANGE) X(HOST_REQUEST) X(HEAD_LINK) X(LOCALIZATION) X(BRAKE_TEST_FAIL) X(STOP_ESCALATED)
#define RRCH_OPMODE_LIST(X) X(COMMISSIONING) X(SURVEY_SHARED) X(SURVEY_UNATTENDED) X(GUIDED) X(LAB) X(SERVICE)
#define RRCH_PRES_LIST(X) X(ABSENT) X(HEAD_DIRECT) X(HEAD_VIA_LAB_EXTENSION) X(LAB_EXTENSION_ONLY) X(FAULT)
#define RRCH_FLT_LIST(X) /* first group enters FAULT mode */ \
    X(ESTOP_DISCREPANCY) X(LATCH_STUCK) X(IOX_A) X(ADC) X(TIMING) X(PERMIT_STUCK_ON) X(CHAIN_IMPLAUSIBLE) \
    X(LATCH_NO_REARM) X(LATCH_NO_DROP) X(LOOP_FAIL) X(PIN_CONFIG) X(K1_WELD) X(RUN_SHORT) X(LOOP_SW_SHORT) \
    X(PERMIT_STUCK_OFF) X(IOX_B) X(IOX_D) X(REARM_HELD) X(REARM_DISCREPANCY) X(CONFIG_DEFAULTED) X(LOOP_DISCREPANCY) X(J1_PRES_FAULT) X(CHARGER_COMM) X(PMON_COMM) X(TOF_BUS) X(HEATER_SENSOR) \
    X(EFUSE_HEAD_PWR) X(EFUSE_HEAD_HTR) X(EFUSE_CHS_HTR) X(EFUSE_LIDAR) X(EFUSE_V5) X(BRIDGE_L) X(BRIDGE_R) X(BUS_CLAMP) \
    X(EVENT_OVERFLOW) X(BATTERY_WARN) X(LOOP_HIGH_R) X(SET_STAGE_FAULT) X(REARM_RB_FAULT) X(BATTERY_REARM_LOW) X(COIL_HOT)
/* IB-34 (lead decision, corrected mapping): two forward-looking (grip cheeks, over the head) and two rearward-looking
 * (tail) oblique sensors. Index 4 LOOK_FL (J_TOF4, mux 0 ch 2), 5 LOOK_RL (J_TOF5, mux 1 ch 2), 6 LOOK_RR (J_TOF6,
 * mux 0 ch 3), 7 LOOK_FR (J_TOF7, mux 1 ch 3): each pair is split across the two muxes. */
#define RRCH_TOF_LIST(X) X(CLIFF_FL) X(CLIFF_FR) X(CLIFF_RL) X(CLIFF_RR) X(LOOK_FL) X(LOOK_RL) X(LOOK_RR) X(LOOK_FR) X(REAR_L) X(REAR_C) X(REAR_R)

#define X(n) RRCH_MODE_##n,
typedef enum { RRCH_MODE_LIST(X) RRCH_MODE_N } rrch_mode_t;
#undef X
#define X(n) RRCH_HWI_##n,
typedef enum { RRCH_HW_LIST(X) RRCH_HW_N } rrch_hw_idx_t;
#undef X
#define X(n) RRCH_SWI_##n,
typedef enum { RRCH_SW_LIST(X) RRCH_SW_N } rrch_sw_idx_t;
#undef X
#define X(n) RRCH_OP_##n,
typedef enum { RRCH_OPMODE_LIST(X) RRCH_OP_N } rrch_opmode_t;
#undef X
#define X(n) RRCH_PRES_##n,
typedef enum { RRCH_PRES_LIST(X) RRCH_PRES_N } rrch_pres_t;
#undef X
#define X(n) RRCH_FLTI_##n,
typedef enum { RRCH_FLT_LIST(X) RRCH_FLT_N } rrch_flt_idx_t;
#undef X
#define X(n) RRCH_TOF_##n,
typedef enum { RRCH_TOF_LIST(X) RRCH_TOF_COUNT } rrch_tof_id_t;
#undef X
#define RRCH_HW(n) (1u << RRCH_HWI_##n)
#define RRCH_SW(n) (1u << RRCH_SWI_##n)
#define RRCH_FLT(n) (1ull << RRCH_FLTI_##n) /* 64-bit flag word (stage 3 filled the 32-bit one) */
#define RRCH_FLT_FATAL_MASK (RRCH_FLT(ESTOP_DISCREPANCY) | RRCH_FLT(LATCH_STUCK) | RRCH_FLT(IOX_A) | RRCH_FLT(ADC) | RRCH_FLT(TIMING) | RRCH_FLT(PERMIT_STUCK_ON) | \
                             RRCH_FLT(CHAIN_IMPLAUSIBLE) | RRCH_FLT(LATCH_NO_REARM) | RRCH_FLT(LATCH_NO_DROP) | RRCH_FLT(LOOP_FAIL) | RRCH_FLT(PIN_CONFIG) | \
                             RRCH_FLT(K1_WELD) | RRCH_FLT(RUN_SHORT) | RRCH_FLT(LOOP_SW_SHORT))
/* fatal flags after which the supervisor stops the watchdog strobe (the chain is then opened at WDG_OK, upstream of a
 * suspect ARM_PERMIT element): electronics/analysis/chassis_safety_chain.md section 6, row 38 */
#define RRCH_FLT_NO_STROBE_MASK (RRCH_FLT(TIMING) | RRCH_FLT(PERMIT_STUCK_ON) | RRCH_FLT(LATCH_STUCK) | RRCH_FLT(LATCH_NO_REARM) | RRCH_FLT(LATCH_NO_DROP))
/* (review C1: a latch that rose without an observed REARM or did not drop is treated like PERMIT_STUCK_ON) */

extern const char *const rrch_mode_names[RRCH_MODE_N];
extern const char *const rrch_hw_names[RRCH_HW_N];
extern const char *const rrch_sw_names[RRCH_SW_N];
extern const char *const rrch_opmode_names[RRCH_OP_N];
extern const char *const rrch_pres_names[RRCH_PRES_N];
extern const char *const rrch_flt_names[RRCH_FLT_N];
/* round 4 (N1): why a REARM press would not, or did not, set the hardware latch. NONE = a press will set it. */
#define RRCH_RREF_LIST(X) X(NONE) X(FAULT_OR_MODE) X(CHAIN_OPEN) X(REARM_HELD) X(PERMIT_WITHHELD) X(LOOP_TEST) X(SUPPLY_LOW) X(COIL_HOT) \
    X(NOT_READY) X(TOO_SHORT) X(PARTIAL) X(SET_FAILED) X(REARM_HELD_AFTER_SET)
#define X(n) RRCH_RREF_##n,
typedef enum { RRCH_RREF_LIST(X) RRCH_RREF_N } rrch_rref_t;
#undef X
extern const char *const rrch_rref_names[RRCH_RREF_N];
/* stage-4 review S4: diagnosis of a head-loop LOOP_FAIL (or of a B-only opening) */
#define RRCH_LCAUSE_LIST(X) X(NONE) X(A_STUCK_HEALTHY) X(CHECKING_B) X(B_STUCK_HEALTHY) X(TEST_PATH_A) X(SELF_TEST_A) X(SELF_TEST_B) \
    X(A_ANALOG_DISAGREE) X(B_OPEN_OR_TEST_PATH_B) X(A_OPEN_OR_TEST_PATH_A)
#define X(n) RRCH_LC_##n,
typedef enum { RRCH_LCAUSE_LIST(X) RRCH_LC_N } rrch_lcause_t;
#undef X
extern const char *const rrch_lcause_names[RRCH_LC_N];
extern const char *const rrch_tof_names[RRCH_TOF_COUNT];

/* ---- digital inputs: one bit each, logical level 1 = closed / healthy / present / pressed ---- */
#define RRCH_DI_LIST(X) \
    X(MODE_RUN) X(ESTOP_A) X(ESTOP_B) X(HANDS_ON) X(CHG_COVER) X(CHG_PLUG_LINK) X(HEAD_DOCK) X(HEAD_LOOP_OK) \
    X(HEAD_LOOP_SHORT) X(LAB_KEY_N) X(BODY_BUMPER_L) X(BODY_BUMPER_R) X(WDG_OK) X(BRAKE_L) X(BRAKE_R) /* chain events up to here */ \
    X(HW_LATCH) X(J2_PRES) X(BTN_REARM) X(BTN_PAUSE) X(DRV_FAULT_L) X(DRV_FAULT_R) X(REARM_SET) /* stage 4 G4: IOX_A GPB6 */
#define X(n) RRCH_DII_##n,
typedef enum { RRCH_DI_LIST(X) RRCH_DI_N } rrch_di_idx_t;
#undef X
#define RRCH_DI(n) (1u << RRCH_DII_##n)
#define RRCH_DI_CHAIN_EVENT_N (RRCH_DII_BRAKE_R + 1)
extern const char *const rrch_di_names[RRCH_DI_N];
/* CHG_PLUG_LINK = 1 means the chain contact is closed, i.e. the charge plug link is ABSENT.
 * HEAD_LOOP_SHORT = 1 means the comparator reports a short. BRAKE_x = 1: motor connected to bridge.
 * IB-02 / CCR-E03 (d): MODE_RUN, ESTOP_A, HANDS_ON, CHG_COVER, CHG_PLUG_LINK, HEAD_DOCK, BODY_BUMPER_L, BODY_BUMPER_R and
 * WDG_OK are NODE voltages of the series chain (electronics/analysis/chassis_safety_chain.md 2.3: "the chain is live up to
 * and including this element"); an element behind an open one is UNKNOWN, not closed. HEAD_LOOP_OK/SHORT and LAB_KEY_N are
 * comparator outputs (the input condition of U21/U22), ESTOP_B is the separate COIL_RTN detector. CCR-E03 (e): BRAKE_x is an
 * OR over both relay poles and valid only while the bridges are asleep. */

/* chain elements in contract order (safety_chain.series_elements) and their decoded state */
#define RRCH_EL_LIST(X) X(MODE_RUN) X(ESTOP) X(HANDS_ON) X(CHG_COVER) X(HEAD_DOCK) X(HEAD_LOOP) X(LAB_KEY_N) X(BODY_BUMPER) X(WDG_OK) X(ARM_PERMIT)
#define X(n) RRCH_EL_##n,
typedef enum { RRCH_EL_LIST(X) RRCH_EL_N } rrch_el_t;
#undef X
extern const char *const rrch_el_names[RRCH_EL_N];
typedef enum { RRCH_ELS_UNKNOWN = 0, RRCH_ELS_CLOSED, RRCH_ELS_OPEN } rrch_el_state_t;

typedef enum { RRCH_TOF_ST_OK = 0, RRCH_TOF_ST_NO_TARGET, RRCH_TOF_ST_INVALID, RRCH_TOF_ST_STALE, RRCH_TOF_ST_OFFLINE } rrch_tof_status_t;
typedef enum { RRCH_CHG_NONE = 0, RRCH_CHG_PRECHARGE, RRCH_CHG_CC, RRCH_CHG_CV, RRCH_CHG_DONE, RRCH_CHG_TEMP_INHIBIT, RRCH_CHG_FAULT, RRCH_CHG_UNKNOWN } rrch_chg_state_t;
typedef enum { RRCH_RST_POWER_ON = 0, RRCH_RST_BROWNOUT, RRCH_RST_PIN, RRCH_RST_WATCHDOG, RRCH_RST_SOFTWARE, RRCH_RST_UNKNOWN } rrch_reset_cause_t;
typedef enum { RRCH_LED_OFF = 0, RRCH_LED_ON, RRCH_LED_BLINK_SLOW, RRCH_LED_BLINK_FAST, RRCH_LED_BLINK_2 } rrch_led_pat_t;
enum { RRCH_LED_READY = 0, RRCH_LED_MOVING, RRCH_LED_HOLD, RRCH_LED_FAULT, RRCH_LED_CHARGE, RRCH_LED_N };
typedef enum { RRCH_MOTION_REST = 0, RRCH_MOTION_ALERT, RRCH_MOTION_RUN, RRCH_MOTION_DECEL } rrch_motion_t;
typedef enum { RRCH_PANEL_AUTO = 0, RRCH_PANEL_ARRIVED, RRCH_PANEL_ATTENTION, RRCH_PANEL_LOCATE, RRCH_PANEL_QUIET, RRCH_PANEL_N } rrch_panel_pat_t;
#define RRCH_HOLD_LOCAL_PAUSE 1u
#define RRCH_HOLD_HOST_STOP 2u
#define RRCH_DIR_FWD 1u
#define RRCH_DIR_REV 2u
#define RRCH_DIR_PIVOT 4u

/* ---- HAL data ---- */
typedef struct {            /* sampled by the port every 1 ms (control tick) */
    uint32_t di;            /* RRCH_DI() bits */
    bool iox_ok;            /* expander read path verified this tick */
    bool io_cfg_ok;         /* review M2/M3: tap pins and expander directions read back as inputs without pulls */
    bool adc_ok;
    uint32_t pres_ohm;      /* J1 pin 7 to pin 2, saturate at 1 000 000 for open */
    uint32_t loop_ohm;      /* J1 5/6 loop, saturate at 1 000 000 */
    float vmot_v, vbat_v, v5_v;
    float i_mot_a[2];       /* magnitude, left/right */
    float ntc_c[3];         /* bay, pack, board; NAN when the sensor is open/short */
    uint16_t enc[2];        /* free-running 16-bit quadrature counters, + = forward, left/right */
    bool imu_ok;
    float gyro[3], accel[3]; /* body axes x fwd, y left, z up; rad/s, m/s^2 */
} rrch_in_t;

typedef struct {            /* written by the core every 1 ms; the port applies changes */
    float duty[2];          /* -1..+1, + = forward, left/right. 0 with bridge awake = brake (slow decay) */
    bool bridge_awake;
    bool arm_permit;
    bool head_pwr_en, head_htr_en;
    bool chs_htr_on;
    bool buzzer;
    uint8_t leds;           /* bit per RRCH_LED_x, instantaneous on/off */
    bool lamp_rearm, lamp_pause;
} rrch_out_t;

typedef struct {            /* slow telemetry pushed by the port's background drivers */
    bool pmon_ok, charger_ok;
    float ibat_a;           /* + = discharge */
    float soc_pct;          /* <0 = unknown */
    float chg_temp_c;       /* charger thermistor, NAN if unknown */
    rrch_chg_state_t charge_state;
    float i_head_a, i_head_htr_a, i_chs_htr_a; /* NAN if unknown */
    uint8_t efuse_fault;    /* bit0 HEAD_PWR, 1 HEAD_HTR, 2 CHS_HTR, 3 LIDAR, 4 V5 */
    bool tof_bus_ok;
    bool chg_input;         /* charger reports input power (needs charger_ok); used when the chain nodes of the
                             * cover/plug elements are dead upstream (selector in SERVICE) */
    float vbat_pmon_v;      /* INA228 bus voltage, NAN if unknown */
} rrch_power_t;

typedef struct {            /* IOX_B input P17 = CHAIN_END_RB (CCR-E02), pushed by the port's background I2C driver */
    bool ok;                /* last read succeeded */
    bool chain_end;         /* last good sample: node after the ARM_PERMIT element is live */
    uint64_t t_us;          /* chassis time of the last good read */
    uint32_t fail_n;        /* consecutive failed reads */
} rrch_iox_b_t;

typedef struct { bool ok; uint8_t val, out; uint64_t t_us, seen_us; uint32_t fail_n; } rrch_iox_d_t; /* IOX_D: input, output register written */

typedef struct {
    void *ctx;
    uint64_t (*now_us)(void *ctx);
    void (*read_inputs)(void *ctx, rrch_in_t *in);
    void (*write_outputs)(void *ctx, const rrch_out_t *out);
    void (*wdg_strobe)(void *ctx);                           /* one edge on WDI */
    size_t (*link_read)(void *ctx, uint8_t *buf, size_t cap); /* non-blocking */
    bool (*link_write)(void *ctx, const uint8_t *buf, size_t len);
    bool (*link_up)(void *ctx);                              /* USB configured and not suspended */
    bool (*nv_read)(void *ctx, int slot, uint8_t *buf, size_t cap, size_t *len);
    bool (*nv_write)(void *ctx, int slot, const uint8_t *buf, size_t len);
    void *(*retained)(void *ctx, size_t size);               /* reset-surviving RAM or NULL */
    bool (*entropy)(void *ctx, uint8_t *buf, size_t len);
    rrch_reset_cause_t (*reset_cause)(void *ctx);
    void (*irq_lock)(void *ctx);                             /* mask the control + supervisor ticks (may be NULL) */
    void (*irq_unlock)(void *ctx);
    void (*wdg_low)(void *ctx);                              /* WDI back low (strobe = 5 ms high pulse every 10 ms); may be NULL */
} rrch_hal_t;

/* ---- configuration ---- */
#define RRCH_CFG_LIST(X) \
    X(ID_SERIAL_NO, "id.serial_no", 1, 0, 999999, "") \
    X(ID_HW_REV, "id.hw_rev", 1, 1, 26, "") \
    X(CAL_RADIUS_L, "cal.wheel_radius_l_m", 0.052, 0.045, 0.060, "m") \
    X(CAL_RADIUS_R, "cal.wheel_radius_r_m", 0.052, 0.045, 0.060, "m") \
    X(CAL_TRACK, "cal.track_m", 0.270, 0.20, 0.34, "m") \
    X(CAP_COM_VF, "caps.commissioning.v_fwd_mps", 0.20, 0, 0.20, "m/s") \
    X(CAP_COM_VR, "caps.commissioning.v_rev_mps", 0.05, 0, 0.05, "m/s") \
    X(CAP_COM_W, "caps.commissioning.w_radps", 0.30, 0, 0.30, "rad/s") \
    X(CAP_SSH_VF, "caps.survey_shared.v_fwd_mps", 0.10, 0, 0.20, "m/s") \
    X(CAP_SSH_VR, "caps.survey_shared.v_rev_mps", 0.05, 0, 0.05, "m/s") \
    X(CAP_SSH_W, "caps.survey_shared.w_radps", 0.30, 0, 0.30, "rad/s") \
    X(CAP_SUN_VF, "caps.survey_unattended.v_fwd_mps", 0.20, 0, 0.20, "m/s") \
    X(CAP_SUN_VR, "caps.survey_unattended.v_rev_mps", 0.05, 0, 0.05, "m/s") \
    X(CAP_SUN_W, "caps.survey_unattended.w_radps", 0.30, 0, 0.30, "rad/s") \
    X(CAP_GUI_VF, "caps.guided.v_fwd_mps", 0.10, 0, 0.20, "m/s") \
    X(CAP_GUI_VR, "caps.guided.v_rev_mps", 0.05, 0, 0.05, "m/s") \
    X(CAP_GUI_W, "caps.guided.w_radps", 0.30, 0, 0.30, "rad/s") \
    X(DRV_ACCEL, "drive.accel_mps2", 0.30, 0.05, 0.30, "m/s2") \
    X(DRV_DECEL, "drive.decel_mps2", 0.40, 0.20, 1.0, "m/s2") \
    X(DRV_PSTOP_DECEL, "drive.pstop_decel_mps2", 1.0, 0.40, 2.0, "m/s2") \
    X(DRV_YAW_ACCEL, "drive.yaw_accel_radps2", 1.5, 0.2, 3.0, "rad/s2") \
    X(DRV_KP, "drive.kp", 0.12, 0, 2.0, "duty.s/rad") \
    X(DRV_KI, "drive.ki", 2.5, 0, 50, "duty/rad") \
    X(DRV_I_LIMIT, "drive.i_limit_a", 2.5, 0.5, 2.6, "A") /* bridges chop in hardware at 2.68 A (CCR-E03 b) */ \
    X(DRV_STALL_MS, "drive.stall_ms", 500, 100, 2000, "ms") \
    X(DRV_ENC_FAULT_MS, "drive.enc_fault_ms", 100, 20, 500, "ms") \
    X(DRV_UNCMD_TICKS, "drive.uncmd_ticks", 600, 50, 5000, "ticks") \
    X(DRV_MOTOR_R, "drive.motor_r_ohm", 2.18, 0.5, 10, "ohm") /* 12 V / 5.5 A, chassis_braking_tables.md T1 */ \
    X(DRV_MOTOR_KE, "drive.motor_ke", 1.65, 0.5, 5, "V.s/rad") \
    X(LINK_TIMEOUT_MS, "link.timeout_ms", 1000, 300, 5000, "ms") \
    X(ALERT_PREMOTION_MS, "alert.premotion_ms", 1500, 500, 5000, "ms") \
    X(ALERT_REST_MS, "alert.rest_ms", 5000, 0, 600000, "ms") \
    X(STAT_GYRO_MAX, "stationary.gyro_max_radps", 0.05, 0.005, 0.5, "rad/s") \
    X(STAT_MIN_MS, "stationary.min_ms", 100, 0, 2000, "ms") \
    X(TOF_MAX_AGE_MS, "tof.max_age_ms", 100, 40, 250, "ms") \
    X(TOF_DISAGREE_MS, "tof.disagree_ms", 200, 50, 1000, "ms") \
    X(CLIFF_DROP_MM, "cliff.drop_mm", 60, 20, 200, "mm") \
    X(CLIFF_FLOOR_MIN_MM, "cliff.floor_min_mm", 8, 0, 50, "mm") \
    X(CLIFF_CONFIRM_N, "cliff.confirm_n", 3, 1, 10, "samples") \
    /* look-ahead geometry (IB-34): defaults computed from mechanical/common/frames.yaml by tools/look_geometry.py, which \
     * check.sh runs to catch drift. fwd = grip-cheek pair LOOK_FL/FR, rev = tail pair LOOK_RL/RR. ahead = horizontal \
     * distance of the nominal floor intersection beyond the leading rail (fwd) / the 0.290 m tail swept radius (rev). */ \
    X(LOOK_FWD_NOMINAL_MM, "look.fwd_nominal_mm", 524, 50, 1000, "mm") \
    X(LOOK_FWD_TOL_MM, "look.fwd_tol_mm", 60, 10, 200, "mm") \
    X(LOOK_FWD_AHEAD_M, "look.fwd_ahead_m", 0.285, 0.03, 0.60, "m") \
    X(LOOK_FWD_COS, "look.fwd_cos", 0.946, 0.3, 1.0, "") \
    X(LOOK_REV_NOMINAL_MM, "look.rev_nominal_mm", 267, 50, 1000, "mm") \
    X(LOOK_REV_TOL_MM, "look.rev_tol_mm", 40, 10, 200, "mm") \
    X(LOOK_REV_AHEAD_M, "look.rev_ahead_m", 0.201, 0.03, 0.60, "m") \
    X(LOOK_REV_COS, "look.rev_cos", 0.913, 0.3, 1.0, "") \
    X(REAR_STOP_MM, "rear.stop_mm", 120, 40, 500, "mm") \
    X(REAR_SLOW_MM, "rear.slow_mm", 300, 60, 1000, "mm") \
    X(STOP_T_DELAY_MS, "stop.t_delay_ms", 150, 20, 500, "ms") \
    X(STOP_A_MIN, "stop.a_min_mps2", 0.40, 0.1, 2.0, "m/s2") \
    X(STOP_MARGIN_M, "stop.margin_m", 0.020, 0, 0.2, "m") \
    X(STOP_ESCALATE_MS, "stop.escalate_ms", 300, 100, 2000, "ms") \
    X(SAFE_ALLOW_RETREAT, "safety.allow_retreat", 0, 0, 1, "bool") \
    X(SAFE_RETREAT_V, "safety.retreat_v_mps", 0.05, 0.01, 0.05, "m/s") \
    X(SAFE_REQUIRE_BRAKE_TEST, "safety.require_brake_test", 1, 0, 1, "bool") \
    X(IMU_TILT_MAX_DEG, "imu.tilt_max_deg", 15, 3, 45, "deg") \
    X(IMU_TILT_MS, "imu.tilt_ms", 200, 20, 2000, "ms") \
    X(BATT_STOP_V, "batt.stop_v", 11.2, 10.0, 13.0, "V") \
    X(BATT_WARN_V, "batt.warn_v", 12.0, 10.0, 13.5, "V") \
    X(BATT_STOP_SOC, "batt.stop_soc_pct", 5, 0, 50, "%") \
    X(BATT_BROWNOUT_V, "batt.brownout_v", 9.5, 8.0, 11.0, "V") \
    X(TEMP_MIN_C, "temp.min_c", -25, -40, 10, "C") \
    X(TEMP_MAX_C, "temp.max_c", 60, 30, 80, "C") \
    X(HTR_BAND_C, "heater.band_c", 2.0, 0.5, 10, "C") \
    X(HTR_MAX_DUTY, "heater.max_duty_pct", 100, 0, 100, "%") \
    X(HTR_MAX_C, "heater.max_c", 35, 10, 50, "C") \
    X(HTR_DISAGREE_C, "heater.disagree_c", 15, 2, 40, "C") \
    X(HTR_MIN_DISCHARGE_C, "heater.min_discharge_c", -10, -20, 10, "C") /* contract thermal_policy.bay_min_discharge_c */ \
    X(HTR_PRECHARGE_C, "heater.precharge_c", 5, 0, 15, "C")             /* contract thermal_policy.bay_precharge_c */ \
    X(CHAIN_CLOSE_DEBOUNCE_MS, "chain.close_debounce_ms", 50, 5, 500, "ms") \
    X(CHAIN_PRES_SETTLE_MS, "chain.pres_settle_ms", 20, 5, 500, "ms") \
    /* review M1: without the stage-3 diode D_RSET, C_SET back-feeds CHAIN_END through R_SET and readbacks behind an \
     * open element can read live for ~10 s. The current netlist (S3, F12) has D_RSET: 0. 12000 for a stage-2 board. */ \
    X(CHAIN_BACKFEED_MS, "chain.backfeed_ms", 0, 0, 20000, "ms") \
    X(LOOP_B_STUCK_OHM, "loop.b_stuck_ohm", 2050, 1900, 3500, "ohm") \
    X(REARM_VBAT_WARN_V, "rearm.vbat_warn_v", 12.0, 11.5, 13.0, "V") \
    X(REARM_NTC_OFFSET_K, "rearm.ntc_coil_offset_k", 0, 0, 30, "K") \
    X(REARM_COIL_SELFHEAT_K, "rearm.coil_selfheat_k", 10, 0, 30, "K") \
    X(BRK_LATCH_DROP_MAX_MS, "brake.latch_drop_max_ms", 50, 5, 500, "ms") \
    X(BRK_VMOT_MIN_V, "brake.vmot_min_v", 9.0, 5, 12, "V") \
    X(BRK_VMOT_OFF_V, "brake.vmot_off_v", 1.0, 0.2, 5, "V") \
    X(BRK_VMOT_DECAY_MAX_MS, "brake.vmot_decay_max_ms", 3500, 50, 6000, "ms") /* 1 kOhm bleed on 3 x 270 uF +20 % + 20 uF: 2.66 s from 14.6 V (review m1) */ \
    X(BRK_PROBE_DUTY, "brake.probe_duty_pct", 10, 2, 30, "%") \
    X(BRK_PROBE_I_MAX, "brake.probe_i_max_a", 0.1, 0.02, 1.0, "A")

#define X(id, name, def, mn, mx, unit) RRCH_CFG_##id,
typedef enum { RRCH_CFG_LIST(X) RRCH_CFG_N } rrch_cfg_id_t;
#undef X
typedef struct { const char *name; float def, min, max; const char *unit; } rrch_cfg_desc_t;
extern const rrch_cfg_desc_t rrch_cfg_desc[RRCH_CFG_N];
typedef struct {
    float v[RRCH_CFG_N];
    uint32_t gen;
    uint32_t crc;
    bool from_flash;
} rrch_cfg_t;
#define RRCH_NV_SLOT_CFG_A 0
#define RRCH_NV_SLOT_CFG_B 1
#define RRCH_NV_SLOT_BOOTLOG 2
#define RRCH_NV_MAX 1024u
#define RRCH_CFG_LAYOUT_VERSION 1u

void rrch_cfg_defaults(rrch_cfg_t *c);
/* Serialise / parse the persistent image (magic, layout version, generation, key hashes, CRC-32). */
size_t rrch_cfg_pack(const rrch_cfg_t *c, uint8_t *buf, size_t cap);
bool rrch_cfg_unpack(rrch_cfg_t *c, const uint8_t *buf, size_t len);
int rrch_cfg_find(const char *name);
bool rrch_cfg_load(rrch_cfg_t *c, const rrch_hal_t *hal);   /* false = defaults in use */
bool rrch_cfg_save(rrch_cfg_t *c, const rrch_hal_t *hal);   /* bumps gen, alternates slots */

/* ---- events ---- */
typedef enum {
    RRCH_EV_BOOT = 0, RRCH_EV_BROWNOUT, RRCH_EV_CHAIN, RRCH_EV_HW_LATCH, RRCH_EV_PERMIT, RRCH_EV_J1, RRCH_EV_J2, RRCH_EV_BUTTON,
    RRCH_EV_MODE, RRCH_EV_PSTOP, RRCH_EV_PSTOP_CLEAR, RRCH_EV_HOLD, RRCH_EV_REARM_REJECT, RRCH_EV_OP_MODE, RRCH_EV_CONFIG,
    RRCH_EV_HEAD_POWER, RRCH_EV_FAULT, RRCH_EV_BRAKE_TEST, RRCH_EV_LINK, RRCH_EV_TOF, RRCH_EV_REARM_REFUSED, RRCH_EV_KIND_N
} rrch_ev_kind_t;
typedef struct {
    uint32_t seq;
    uint64_t t_us;
    uint8_t kind;
    int32_t a, b, c;
    float f, g;
    char s[16];
} rrch_event_t;

/* ---- sub-states ---- */
typedef struct {
    uint32_t state;             /* debounced DI bits */
    uint16_t cnt[RRCH_DI_N];
    rrch_pres_t pres;           /* debounced J1 class */
    rrch_pres_t pres_cand;
    uint16_t pres_cnt;
    uint32_t pres_ohm;
    uint32_t loop_ohm;
    uint8_t loop_state;         /* 0 OK, 1 OPEN, 2 SHORT */
    uint32_t hw_live;           /* live hardware causes */
    uint32_t hw_latched;
    bool latch;                 /* debounced HW latch readback */
    uint16_t t_estop_disc, t_loop_disc, t_vmot_low, t_vmot_high, t_latch_stuck, t_brake_rb, t_iox, t_adc;
    bool primed;
    /* IB-02: node decode */
    uint8_t el[RRCH_EL_N];      /* rrch_el_state_t per chain element */
    uint32_t rb_known;          /* DI bits whose element state is known (upstream node live) */
    uint32_t rb_reported;       /* last reported (CHAIN event) known state per DI bit */
    uint16_t t_implausible;
    uint16_t asleep_ms;         /* bridges commanded asleep (or latch readback low) for this long: BRAKE_x valid */
    bool relays_ok;             /* both brake relays read "connected" since the latch was set (bridges may wake) */
    /* IB-01: ARM_PERMIT readback through CHAIN_END_RB (IOX_B P17) */
    rrch_iox_b_t iox_b;
    uint64_t iox_b_seen_us;
    /* review C1 / m3: REARM qualification, latch rise / drop supervision */
    bool rearm_prev, rearm_edge_ok;
    uint64_t rearm_edge_us, rearm_block_until_us;
    uint32_t rearm_held_ms;
    uint16_t t_no_drop, t_latch_boot, t_loop_ana, t_loop_fail;
    bool loop_disc_latched;
    uint16_t ce_high_ms;        /* CHAIN_END_RB continuously high (stage 3 F12: REARM sets only after ~1-2 s) */
    uint16_t drop_ms;           /* since the latch readback last fell (ARM_PERMIT held low for 50 ms after it) */
    uint8_t ana3;               /* analog loop: 0 OK, 1 OPEN, 2 SHORT, 3 marginal (between the bands) */
    uint64_t ce_live_us;        /* last time CHAIN_END was really live (permit high, CH_N9 live): C_SET charged */
    bool backfeed;              /* readbacks behind an open element may be held up by C_SET */
    /* stage 3: IOX_D readbacks */
    rrch_iox_d_t iox_d;
    bool iox_d_known, k1_nc, k1_run, loop_b, rearm_set, rearm_set_prev;
    uint64_t rearm_set_edge_us;
    uint16_t t_k1_weld_nc, t_k1_weld_run, t_run_short, t_rearm_disc, t_loopab, hw_latch_raw_low_ms;
    uint32_t rearm_set_held_ms;
    bool raw_latch_prev;
    uint64_t raw_latch_since_us;
    uint8_t n_weld, n_run_short;
    uint32_t permit_hist, n9_hist; /* bit k: ARM_PERMIT output / raw CH_N9 readback k ms ago */
    uint8_t n_stuck_on, n_stuck_off, n_end_impl;
    bool chain_end_known, chain_end;
    /* round 4 / stage 4: SET_READY (G1), CH_N6A tap and loop self-test (G5), refusal reporting (G3) */
    bool set_ready, chn6a, bus_clamp, rearm_set_raw_prev;
    uint32_t ce_dead_ms;        /* CHAIN_END_RB known dead for this long (SET_STAGE_FAULT) */
    uint64_t set_ready_since_us; /* SET_READY_RB first seen high */
    uint64_t set_close_us, set_open_us; /* REARM set contact (IOX_A GPB6, raw 1 kHz) closing / opening */
    uint64_t a_open_since_us, b_low_since_us; /* channel A (GPA5 raw) open / channel B (IOX_D) low since */
    uint8_t n_u21s, n_u21bs;
    uint8_t lt_phase;           /* 0 idle, 1 TEST_A, 2 gap, 3 TEST_B, 4 settle */
    uint16_t lt_ms, closed_ms;
    bool lt_passed, lt_a_ok, lt_b_ok;
    uint8_t lt_out;             /* requested IOX_D output register (P4 LOOP_TEST_A, P7 LOOP_TEST_B) */
    uint32_t lt_snap_st, lt_snap_ohm;
    bool lt_snap_b;
    uint32_t lt_n;              /* self-tests passed since boot */
    uint8_t rearm_why;          /* rrch_rref_t: what a press would meet now (NONE = it will set the latch) */
    uint8_t rearm_refusal;      /* rrch_rref_t: last press that did not set (cleared when the latch is set) */
    uint8_t press_why;          /* rearm_why at the moment of the pending press */
    bool press_pending;         /* REARM aux edge with the latch down, outcome not yet reported */
    uint64_t press_us, press_end_us; /* aux edge and release of the latest press */
    uint64_t refused_us;        /* last REARM_REFUSED (lamp: fast blink for 2 s, stage 4 G3) */
    /* N2: K1 sealed in without U_HOLD (set pulse shorter than the operate time): released, not a weld */
    uint8_t n_unheld;
    uint64_t unheld_until_us;
    uint32_t latched_held_ms;   /* W-018: a REARM contact closed while latched */
    bool held_drop, set_edge_ok, aux_raw_prev;
    uint64_t aux_open_us;
    uint8_t rb_fault_line;      /* REARM_RB_FAULT: 1 set line missed the press, 2 aux line missed it */
    uint8_t loop_cause;         /* rrch_lcause_t: diagnosis of the last LOOP_FAIL / loop discrepancy (S4) */
    uint8_t ld_phase;           /* S4 diagnostic TEST_B after a 'B stuck' verdict: 0 idle, 1 pending, 2 running */
    uint16_t ld_ms;
    bool ld_b_low;
    uint16_t t_vbat_warn;
    float coil_f, coil_c;       /* stage 5 H2: latch-set self-heating filter, K1 coil estimate */
    bool short_dip;             /* stage 5 H4: the current permit withdrawal is the 30 ms PARTIAL-set dip */
    uint16_t t_loop_high;
} rrch_chain_t;

typedef struct {
    int32_t range_mm;
    rrch_tof_status_t status;   /* as delivered */
    uint64_t t_us;
    bool seen;
    /* derived each tick */
    bool valid;
    rrch_tof_status_t eff;      /* effective status incl. STALE/OFFLINE */
    uint8_t drop_n;
    uint64_t last_count_t;
    bool ev_valid;
    uint32_t ev_ms;
} rrch_tof_t;

typedef struct {
    uint8_t inhibit;            /* RRCH_DIR_x currently inhibited */
    uint32_t cause_now;         /* sw reason bits whose condition is present */
    uint32_t dir_cause[3];      /* per direction (fwd, rev, pivot): reasons to latch if moving that way */
    uint32_t confirmed;         /* confirmed cliffs: latch whenever armed */
    float v_cap_fwd, v_cap_rev;
    bool look_active[4];
    float look_dist0[4];        /* distance available at detection */
    double look_s0[4];          /* odometer at detection */
    uint16_t t_blocked[4];
} rrch_fields_t;

typedef struct {
    /* command */
    bool cmd_valid;
    float cmd_v, cmd_w;
    uint64_t cmd_expiry_us;
    uint32_t last_seq;
    bool seq_valid;
    /* ramped set-point */
    float v_sp, w_sp;
    rrch_motion_t motion;
    uint32_t alert_ms, rest_ms;
    bool alert_force;           /* next start from rest needs the pre-motion alert whatever the rest time */
    bool stop_req;              /* a stop is being enforced (pstop / hold / inhibit) */
    float stop_decel;
    bool brake_now;             /* zero duty immediately (encoder fault / hw inhibit) */
    uint32_t stop_ms, stop_deadline_ms;
    /* wheels */
    uint16_t enc_prev[2];
    int64_t ticks[2];
    int32_t win[2][10];
    uint8_t win_i;
    float w_meas[2];            /* rad/s filtered */
    float tps[2];
    float th_err[2];
    float duty[2];
    float lim[2];
    float i_f[2];
    uint16_t t_stall[2], t_enc[2], t_over[2];
    bool at_rest;
    uint16_t t_rest;
    int64_t rest_ticks[2];
    bool stat_run;              /* both encoders zero ticks and |gyro| under the threshold, this tick and since stat_since_us */
    bool is_stationary;         /* ... for at least stationary.min_ms */
    uint64_t stat_since_us;
    double odometer_m;          /* signed path length of the body centre */
    float v_meas, w_meas_body;
} rrch_drive_t;

typedef struct { uint64_t t_us; int64_t l, r; float l_tps, r_tps; uint32_t seq; } rrch_odom_t;
typedef struct { uint64_t t_us; float gyro[3], accel[3]; bool ok; } rrch_imu_t;

typedef enum { RRCH_BT_NONE = 0, RRCH_BT_RUNNING, RRCH_BT_PASSED, RRCH_BT_FAILED } rrch_bt_state_t;
#define RRCH_BTF_PRECOND_VMOT 0x001u
#define RRCH_BTF_PRECOND_RELAY 0x002u
#define RRCH_BTF_LATCH_NOT_DROPPED 0x004u
#define RRCH_BTF_RELAY_L 0x008u
#define RRCH_BTF_RELAY_R 0x010u
#define RRCH_BTF_VMOT_NOT_REMOVED 0x020u
#define RRCH_BTF_BRIDGE_CURRENT_L 0x040u
#define RRCH_BTF_BRIDGE_CURRENT_R 0x080u
#define RRCH_BTF_WHEEL_MOVED 0x100u
#define RRCH_BTF_K1_NOT_RELEASED 0x200u /* stage 3: LATCH_NC_RB low with the latch down */
#define RRCH_BTF_K1_WELDED 0x400u       /* stage 3: ARM_PERMIT raised without REARM: LATCH_RUN_RB or HW_LATCH_RB rose */
typedef struct {
    rrch_bt_state_t state;
    uint8_t step;
    uint32_t ms;
    uint32_t fail;
    int32_t latch_drop_ms, relay_ms, vmot_decay_ms;
    float vmot_end_v, probe_i[2];
    int64_t t0_ticks[2];
    int32_t moved[2];
    uint64_t done_us;
    bool passed_since_boot;
    bool result_ready;          /* for the protocol server: deferred reply */
} rrch_brake_test_t;

typedef struct {
    rrc_frame_rx_t rx;
    uint8_t rx_buf[RRCH_RECORD_MAX];
    uint8_t tx_buf[RRCH_RECORD_MAX];
    rrc_reply_cache_t cache;
    bool session_open;
    uint32_t session;
    uint64_t last_rx_us;
    bool any_rx;
    bool bt_pending;
    uint32_t bt_id, bt_crc;
    size_t bt_len;
    uint32_t n_req, n_bad;
} rrch_proto_t;

typedef struct { uint32_t magic; uint32_t mode; uint32_t uptime_s; uint32_t brownout; uint32_t crc; } rrch_retained_t;

typedef struct rrch {
    rrch_hal_t hal;
    rrch_cfg_t cfg;
    rrch_in_t in;
    rrch_out_t out;
    rrch_power_t pwr;
    uint32_t ms;                 /* control ticks since boot */
    uint64_t now_us;             /* time of the current control tick */
    char boot_id[RRC_UUID_STR_LEN + 1u];
    uint32_t boot_count;
    rrch_reset_cause_t reset_cause;
    uint32_t rng;
    /* mode */
    rrch_mode_t mode;
    rrch_opmode_t op_mode;
    bool boot_done;
    uint64_t faults;             /* RRCH_FLT bits */
    uint32_t sw_latched, sw_active, sw_acked;
    uint32_t hold;
    uint32_t rearm_nonce;
    bool permit_withdrawn;
    uint32_t permit_rest_ms;
    uint32_t permit_low_ms;
    bool arm_permit;
    rrch_chain_t chain;
    rrch_tof_t tof[RRCH_TOF_N];
    rrch_fields_t fields;
    rrch_drive_t drive;
    rrch_odom_t odom;
    rrch_imu_t imu;
    float imu_acc[6];
    uint8_t imu_n;
    uint64_t imu_t0;
    float grav[3];
    uint16_t t_imu_missing, t_imu_norm, t_tilt, t_batt_low;
    float tilt_deg;
    rrch_brake_test_t bt;
    /* head power / heater / panel */
    bool head_pwr, head_htr;
    bool htr_enabled;
    float htr_setpoint_c;
    float htr_active_sp;        /* effective set-point (thermal policy floor or host) */
    float htr_duty;
    bool htr_sensor_ok;
    uint32_t t_htr_disagree_s;
    rrch_panel_pat_t panel_pat;
    uint8_t led_pat[RRCH_LED_N];
    uint32_t beep_ms_left, beep_gap, beep_count, beep_on_ms;
    uint32_t link_lost_latched_rx;
    bool brownout_seen;
    /* events */
    rrch_event_t ev[RRCH_EVENTS_N];
    uint32_t ev_newest;          /* seq of newest event, 0 = none */
    /* watchdog cross-checks */
    volatile uint32_t wd_ctl_count, wd_flow, wd_sup_count, wd_bg_count;
    uint32_t wd_ctl_seen, wd_bg_seen, wd_bg_age, wd_sup_seen_by_ctl, wd_sup_age;
    bool wd_inhibit_strobe;      /* test hook */
    bool wd_high;                /* WDI high since the last strobe */
    uint32_t wd_strobe_ms;
    rrch_proto_t proto;
} rrch_t;

/* ---- core API ---- */
void rrch_init(rrch_t *c, const rrch_hal_t *hal);
void rrch_tick_1khz(rrch_t *c);        /* control context */
void rrch_supervise_100hz(rrch_t *c);  /* supervision context: the only caller of hal.wdg_strobe */
void rrch_background(rrch_t *c);       /* main loop: protocol server */
void rrch_tof_update(rrch_t *c, int idx, int32_t range_mm, rrch_tof_status_t st, uint64_t t_us);
void rrch_power_update(rrch_t *c, const rrch_power_t *p);
void rrch_iox_b_update(rrch_t *c, bool ok, bool chain_end, uint64_t t_us); /* background context, ~100 Hz */
/* IOX_D (U47, TCA9534 0x22), stage 4 G6 map: P0 LATCH_NC_RB, P1 LATCH_RUN_RB, P2 HEAD_LOOP2_OK_RB, P3 BUS_CLAMP_ACTIVE,
 * P4 LOOP_TEST_A (out), P5 SET_READY_RB, P6 CHN6A_RB, P7 LOOP_TEST_B (out). `in` = input register, `out` = the output
 * register value the port has written (and read back); read >= 100 Hz */
void rrch_iox_d_update(rrch_t *c, bool ok, uint8_t in, uint8_t out, uint64_t t_us);
uint8_t rrch_iox_d_out(const rrch_t *c);  /* output register the port must write (0 except during the loop self-test) */
bool rrch_iox_d_fast(const rrch_t *c);    /* read IOX_D every 1 ms (loop self-test in progress), else every 10 ms */

/* ---- internal, shared between core files (also used by unit tests) ---- */
rrch_pres_t rrch_pres_classify(uint32_t ohm);
void rrch_chain_step(rrch_t *c);
bool rrch_rearm_blocked(const rrch_t *c); /* REARM pressed early or held: ARM_PERMIT withheld */
void rrch_fields_step(rrch_t *c);
float rrch_stop_vcap(const rrch_cfg_t *cfg, float dist_m);
float rrch_stop_distance(const rrch_cfg_t *cfg, float v);
void rrch_drive_step(rrch_t *c);
void rrch_drive_stop(rrch_t *c, float decel, bool brake_now);
uint8_t rrch_drive_dir(float v, float w);
void rrch_caps(const rrch_t *c, float *vf, float *vr, float *w);
rrch_event_t *rrch_event(rrch_t *c, rrch_ev_kind_t kind, int32_t a, int32_t b, int32_t d);
void rrch_fault_set(rrch_t *c, uint64_t flt_bit, bool on);
void rrch_pstop(rrch_t *c, uint32_t sw_bits);
void rrch_hold(rrch_t *c, uint32_t why);
/* by_local: REARM button. Returns the reasons cleared; *blocked = causes still present (nothing cleared then). */
uint32_t rrch_rearm_sw(rrch_t *c, bool by_local, const char *operator_name, uint32_t *blocked, uint32_t *hold_cleared);
void rrch_set_head_power(rrch_t *c, bool el, bool htr, int why);
bool rrch_brake_test_start(rrch_t *c);
void rrch_brake_test_step(rrch_t *c);
void rrch_proto_init(rrch_t *c);
void rrch_proto_poll(rrch_t *c);
uint32_t rrch_rand(rrch_t *c);
static inline void rrch_str16(char *dst, const char *src)
{
    size_t n = 0;
    while (n < 15u && src[n]) {
        dst[n] = src[n];
        n++;
    }
    dst[n] = 0;
}
#define CFG(c, id) ((c)->cfg.v[RRCH_CFG_##id])

#endif
