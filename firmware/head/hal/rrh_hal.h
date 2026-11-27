/* Hardware abstraction layer of the head firmware: the ONLY boundary between the
 * hardware-independent core (firmware/head/core) and a port (port/host = emulator,
 * port/stm32g474 = RR-HEAD-ACQ, tests = mock). Every function is called from the core's single
 * execution context (main loop); none may block for longer than about one millisecond.
 *
 * The acquisition part mirrors `head_gate_record` in interface/system/contract.yaml.
 */
#ifndef RRH_HAL_H
#define RRH_HAL_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "rrh_config.h"
#ifdef __cplusplus
extern "C" {
#endif

/* ---- time, entropy, system ------------------------------------------------------------- */
/* 64-bit microseconds, monotonic since MCU boot, derived from the 24 MHz TCXO. */
uint64_t rrh_hal_now_us(void);
/* Head-clock time at which the port will put the first bit of the reply to the request that
 * finished arriving at rx_us on the wire (TIME.tx_us). The port must then honour it. */
uint64_t rrh_hal_reply_tx_time_us(uint64_t rx_us);
/* len bytes of entropy for the boot UUID. false = the source failed (bytes still filled with
 * the best available device-unique, boot-unique material). */
bool rrh_hal_entropy(uint8_t *buf, size_t len);

typedef enum {
    RRH_RESET_POWER_ON = 0,
    RRH_RESET_PIN,
    RRH_RESET_WATCHDOG,
    RRH_RESET_SOFTWARE,
    RRH_RESET_BROWNOUT,
    RRH_RESET_OTHER
} rrh_reset_cause_t;
rrh_reset_cause_t rrh_hal_reset_cause(void);
void rrh_hal_watchdog_kick(void);

/* ---- acquisition source (event capture: MCU timers + latches, or the emulator) ----------------- */
#define RRH_GF_FLOOR_SATURATED 0x01u   /* contract flag */
#define RRH_GF_REF_SATURATED 0x02u     /* contract flag */
#define RRH_GF_BIAS_OUT_OF_RANGE 0x04u /* contract flag */
#define RRH_GF_BASELINE_SHIFT 0x08u    /* contract flag */
#define RRH_GF_FLOOR_INVALID 0x10u     /* extension: floor chain disabled / front end not usable */
#define RRH_GF_REF_INVALID 0x20u       /* extension: reference chain disabled / not usable */

typedef struct {
    uint32_t alpha_counts;
    uint32_t beta_counts;
    uint32_t floor_reject_counts;
    uint32_t floor_live_ticks;
    uint32_t ref_counts;
    uint32_t ref_reject_counts;
    uint32_t ref_live_ticks;
    uint32_t alpha_short_counts; /* ALPHA latch set but time over threshold below the limit (or unmeasured): counted as floor reject, not alpha (DIAG only) */
    uint32_t alpha_idle_clears; /* ALPHA latch found set on the idle floor chain and cleared (engineering, DIAG only) */
    uint8_t flags; /* RRH_GF_* */
} rrh_gate_lane_t;

typedef struct {
    uint32_t sequence;        /* gate index since rrh_hal_acq_start(), starts at 0 */
    uint64_t gate_start_tick; /* capture-timer tick at the first tick of the gate */
    uint32_t gate_ticks;
    uint32_t tick_hz;
    uint32_t heater_on_ticks;
    bool heater_transition_in_gate;
    bool source_fault; /* port-detected fault of the capture hardware for this gate */
    rrh_gate_lane_t lane[RRH_LANES];
    /* Optional engineering extension (not in the contract record): time over threshold of the
     * triggering LLD pulse, histogrammed per chain (0..3 floor lanes, 4..7 reference lanes).
     * width_mask bit n set = the port measures widths on chain n; 0 = feature absent. Bin b
     * counts classified events with width in [edge[b-1], edge[b]) ns, the last bin is open. */
    uint8_t width_mask;
    uint32_t width_edges_ns[RRH_WIDTH_BINS - 1u];
    uint32_t width_hist[2u * RRH_LANES][RRH_WIDTH_BINS];
} rrh_gate_record_t;

/* Relation between the capture-timer tick counter and the head clock: tick `tick` happened at
 * head-clock time `us`. Both run from the same TCXO, so one pair per ARM is exact. */
typedef struct {
    uint64_t tick;
    uint64_t us;
    uint32_t tick_hz;
} rrh_epoch_t;

/* Start recording equal gates of span_us from the next gate boundary; sequence restarts at 0.
 * false = the source cannot start (not configured, bad span, link fault). */
bool rrh_hal_acq_start(uint32_t span_us, rrh_epoch_t *epoch);
/* Stop after the gate in progress (which is still delivered). Returns true if a gate was in
 * progress and will be delivered, false if recording had not started a gate yet. */
bool rrh_hal_acq_stop(void);
/* Stop immediately and drop everything not yet delivered (fresh HELLO, binding invalidated). */
void rrh_hal_acq_abort(void);
/* True from rrh_hal_acq_start() until the last record after a stop has been delivered. */
bool rrh_hal_acq_running(void);
/* Next completed gate, oldest first. false = none available now. */
bool rrh_hal_acq_poll(rrh_gate_record_t *rec);

/* ---- configuration of the analog front end ------------------------------------------------ */
#define RRH_N_THRESHOLDS 20u /* lane*3 + {BETA_LLD, BETA_ULD, ALPHA}, then 12 + lane*2 + {REF_LLD, REF_ULD} */
#define RRH_N_TRIMS 8u       /* floor 0..3, reference 0..3 */

typedef struct {
    uint16_t threshold[RRH_N_THRESHOLDS]; /* 12-bit DAC codes */
    uint16_t trim[RRH_N_TRIMS];           /* 12-bit DAC codes, SiPM anode trim */
    uint16_t pulser_code;                 /* 12-bit test-pulser amplitude (U_DAC1 output 6 = PULSER_AMPL) */
    bool pulser_enable;                   /* periodic strobe on PC6 (TIM8_CH1), 1 kHz */
    uint8_t pulser_channel;               /* 0..7 = F0..F3, R0..R3: chain that receives the test pulse (PULSER_A[2:0] on PF2/PF9/PF10) */
    uint8_t pulser_width_us;              /* strobe width, 1..100 us (alpha-scale tests need >= 20 us, budget 7) */
    uint16_t led_code;                    /* 12-bit LED pulser amplitude (U_DAC0 output 7 = LED_AMPL, V_LED = 2 x) */
    bool led_enable;                      /* strobe LED_STROBE (PC12) with the pulser period */
    uint16_t alpha_hold_us;               /* afterglow hold after an alpha event, 0 = off (IB-18) */
    uint16_t alpha_min_tot_ns;            /* alpha = ALPHA latch AND raw-LLD time over threshold >= this (C1); 0 = no width condition */
    uint8_t chain_enable; /* bit n: floor lane n; bit 4+n: reference lane n */
} rrh_frontend_cfg_t;

/* Write thresholds, trims, pulser, LED, hold and chain enables. Only called while not recording. */
bool rrh_hal_frontend_apply(const rrh_frontend_cfg_t *cfg);
/* Bias converter: set-point in millivolts and enable. */
void rrh_hal_bias_set(uint32_t millivolts, bool enable);

/* ---- housekeeping inputs ------------------------------------------------------------------ */
#define RRH_TEMP_INVALID INT32_MIN

typedef struct {
    int32_t sipm_mc[RRH_LANES]; /* milli-degC near each lane's SiPMs, RRH_TEMP_INVALID if unusable */
    int32_t heater_plate_mc;
    int32_t board_mc;
    uint32_t bias_mv;
    uint32_t bias_ua;
    bool bias_valid;
    uint32_t supply_mv;
    bool supply_valid;
    bool heater_cutout_ok;  /* independent hardware thermal cut-out closed / heater feed present */
    /* Rail-zone identification. Rev A has NO zone identification (IB-21 closed: single-pole rail
     * switches, the inputs are idle): the port sets zones_available = false and bumper_zones then
     * means nothing ("not available", not "not actuated"). */
    bool zones_available;
    uint8_t bumper_zones;   /* bit0 front, bit1 left, bit2 right: auxiliary contact closed (only if zones_available) */
    uint8_t frontend_fault; /* bit n: floor chain n; bit 4+n: reference chain n not usable */
} rrh_analog_t;

void rrh_hal_analog_read(rrh_analog_t *out);

/* ---- per-chain anode current monitor (IMON_CH on PE15 = ADC4_IN2, mux MON_MUX_A[2:0]) ---------- */
/* The port scans the eight chains in the background (select, wait RRH_IMON_SETTLE_US, convert).
 * uv[n] is the voltage seen at the ADC pin for chain n, i.e. V(TRIMDRV) of that chain in
 * microvolts; the core turns it into a current with the trim code (I = (V_trim - V)/4.99 k).
 * valid bit n = chain n has a conversion not older than RRH_IMON_MAX_AGE_US. */
typedef struct {
    uint8_t valid;
    uint32_t uv[8];
} rrh_imon_t;
void rrh_hal_imon_read(rrh_imon_t *out);

/* ---- optional I2C expander TCA9534 at 0x20 (bias permit / inhibit / lid / eFuse fault) -------- */
typedef struct {
    bool present;    /* the device answered on the last read */
    uint8_t inputs;  /* raw input port, bit assignment RRH_EXP_* in rrh_board.h */
} rrh_expander_t;
void rrh_hal_expander_read(rrh_expander_t *out);

/* ---- heater ------------------------------------------------------------------------------- */
/* Requested state; the port applies it on the next gate boundary while gates run,
 * immediately otherwise. */
void rrh_hal_heater_request(bool on);

/* ---- non-volatile storage ----------------------------------------------------------------- */
#define RRH_NV_SLOT_SETUP 0u
/* Load at most cap bytes of a slot; false if empty / unreadable. Integrity is the core's job. */
bool rrh_hal_nv_load(uint8_t slot, uint8_t *buf, size_t cap, size_t *len);
bool rrh_hal_nv_save(uint8_t slot, const uint8_t *buf, size_t len);

/* ---- monitor waveform capture (engineering) ------------------------------------------------ */
typedef struct {
    uint8_t channel;      /* 0..3 floor, 4..7 reference */
    bool slow_path;       /* false = fast path, true = slow (alpha) path */
    uint16_t samples;     /* total samples, <= RRH_WAVE_MAX_SAMPLES */
    uint16_t pretrigger;  /* samples kept before the trigger */
    uint8_t trigger;      /* 0 = immediate, 1 = event on the selected chain */
} rrh_wave_cfg_t;

typedef enum { RRH_WAVE_IDLE = 0, RRH_WAVE_ARMED, RRH_WAVE_DONE, RRH_WAVE_FAILED } rrh_wave_state_t;

bool rrh_hal_wave_arm(const rrh_wave_cfg_t *cfg);
/* State, and when DONE: sample count, sample period in nanoseconds, index of the trigger sample. */
rrh_wave_state_t rrh_hal_wave_status(uint16_t *samples, uint32_t *period_ns, uint16_t *trigger_index);
/* Copy `count` 16-bit little-endian samples starting at sample `offset` into buf (2*count bytes). */
bool rrh_hal_wave_read(uint16_t offset, uint16_t count, uint8_t *buf);

#ifdef __cplusplus
}
#endif
#endif
