/* Compile-time configuration of the head firmware core. Sizes are RAM budget decisions;
 * the protocol limits come from interface/head_icd.md and interface/system/contract.yaml. */
#ifndef RRH_CONFIG_H
#define RRH_CONFIG_H

#define RRH_FW_VERSION "rr-head-0.5.2"
#define RRH_PROTO_VERSION "2.0"
#define RRH_ACQ_FORMAT "2.0"
#define RRH_HEAD_TYPE "FOUR_LANE_ZNS_PLASTIC_WITH_REFERENCE"

#define RRH_LANES 4u
#define RRH_WIDTH_BINS 4u /* coarse pulse-width (time over threshold) histogram bins per chain */

/* Link */
#define RRH_RX_MAX 8192u          /* ICD section 4: maximum record including trailer */
#define RRH_TX_MAX 4096u          /* largest reply this firmware produces is < 2 kB */
#define RRH_JSON_TOKENS 128u      /* largest legal request (a full ENG_SETUP_SET) needs ~110 */
#define RRH_JSON_DEPTH 6u
#define RRH_JSON_STRING 256u
#define RRH_RX_GAP_TIMEOUT_US 5000u /* default idle gap that releases a partial record */

/* Acquisition buffer: contract timing.head_buffer_frames_min = 128 */
#define RRH_FRAME_BUFFER 160u
#define RRH_SYNC_SLOTS 32u
#define RRH_SYNC_ID_MAX 96u

/* Descriptor */
#define RRH_DESCRIPTOR_MAX 4096u  /* built descriptor (host accepts up to 16384) */
#define RRH_DESCRIPTOR_CHUNK_MAX 768u

/* Gate span accepted by ARM unless the identity narrows it (ACQ schema: 1000..1000000) */
#define RRH_SPAN_MIN_US 1000u
#define RRH_SPAN_MAX_US 1000000u
#define RRH_SPAN_DEFAULT_US 100000u

/* Clock quality (head ICD section 6; addendum 0.4 section 5) */
#define RRH_BOUND_MAX_US 10000000u       /* ACQ schema maximum of sync.bound_us */
#define RRH_HOLDOVER_DRIFT_PPM 200u      /* growth of the reported bound after expiry */
#define RRH_HOLDOVER_MAX_US 60000000u    /* HOLDOVER lasts this long after expiry, then UNSYNCED */
#define RRH_EXPIRY_MAX_US 3600000000uLL  /* SYNC.expiry_us upper limit: one hour */

/* Channel validity */
#define RRH_MIN_LIVE_PERCENT 50u         /* below this live fraction a chain is SATURATED */

/* Health windows (defaults; not part of the setup hash because they do not change a sample) */
#define RRH_SUPPLY_MIN_MV 9500u
#define RRH_HEAD_TEMP_MIN_MC (-30000)
#define RRH_HEAD_TEMP_MAX_MC 50000
#define RRH_HEATER_PLATE_MAX_MC 70000    /* software over-temperature limit of the heater plate */
#define RRH_BIAS_MIN_MV 20000u           /* qualified range 20 ... 60 V (budget 5); lower bound of a set-point */
/* The upper bound is the fitted over-voltage trip less a margin (rrh_board_bias_limit_mv()):
 * 31.5 V trip on rev A (R2222/R2223 strap for onsemi J/C) -> 30.5 V. A set-point above the trip
 * would be cut off by the hardware permit latch, so the firmware refuses it instead. */
#define RRH_BIAS_OVP_MARGIN_MV 1000u     /* margin below the nominal trip: R2217/R2218 are 1 % parts (+-0.3 V at 31 V),
                                          * comparator offset and VREF accuracy are datasheet figures (UNVERIFIED) */
#define RRH_BIAS_TOLERANCE_MV 500u       /* tracking window of BIAS_VMON against the set-point; the divider alone is +-1 % */
/* Total bias current limit: the TPS61391 mirror monitor (BIAS_IMON, 8.0 mV/uA) is specified to 250 uA
 * (2.0 V, budget 5.1; MON1 compliance is an open datasheet item B2), so a limit of 500 uA as in
 * firmware 0.3 could never be reached. 200 uA = 80 % of the monitor range, 2x the budget's worst
 * case (SiPM dark 70 uA + dividers 15 uA). */
#define RRH_BIAS_CURRENT_MAX_UA 200u
#define RRH_BIAS_STEP_MV 20u             /* slew limit per control period while tracking temperature */
#define RRH_BIAS_DEADBAND_MV 5u
#define RRH_BIAS_SETTLE_PERIODS 5u
/* Bias-on sequence (CCR-HE-09, S3-07): HV_SET starts at 0; the ramp is 5 V/s AT HV_BUS (0.2 V/s at the DAC output): 500 mV per
 * 100 ms control period, 0 -> 31.5 V in 6.3 s. (~9.8 uF on the bias bus: 49 uA at 5 V/s, 1.2 mA at 125 V/s.) */
#define RRH_BIAS_RAMP_STEP_MV 500u
/* HV_EN high and BIAS_VMON below this once the ramp has finished: the permit latch is tripped
 * (CCR-HE-09); the commanded set-point is at least RRH_BIAS_MIN_MV. */
#define RRH_BIAS_PERMIT_TRIP_MV 1000u

/* Per-chain anode current monitor IMON_CH (PE15 = ADC4_IN2, mux TMUX1108 U2703, MON_MUX_A[2:0]).
 * Window thresholds ("configuration"): numbers from electronics/analysis/head_afe_budget.md 5.1 and 6. */
#define RRH_IMON_SETTLE_US 10000u  /* 10 x (R108 10 k x C2704 100 nF = 1 ms): settle after a mux step to < 0.1 LSB of a 3 V step */
#define RRH_IMON_MAX_NA 200000u    /* per-channel soft limit 0.2 - 0.5 mA (budget 5.1: trim buffer runs out of range); low end */
#define RRH_IMON_SAT_UV 50000u     /* V(TRIMDRV) below this with a trim of >= 2 x this: buffer at its rail, overvoltage collapses; UNVERIFIED (TLV9062 output swing) */
#define RRH_IMON_MIN_NA 0u         /* low-side window DISABLED: dark current of a healthy SiPM at -25 C (~10 nA, calculated) is below the 147 nA
                                    * monitor resolution and the +-0.3 uA op-amp offset; a disconnected channel is not detectable. UNVERIFIED placeholder */
#define RRH_IMON_HOLD_US 200000u   /* out-of-window condition must persist this long (two control periods) before a chain is flagged */
#define RRH_IMON_MAX_AGE_US 1000000u /* a chain not converted within this long is reported as not measured */
#ifndef RRH_IMON_SCAN_WHILE_ARMED
#define RRH_IMON_SCAN_WHILE_ARMED 0 /* review M2: MON_MUX_A[2:0] also address the lane monitor decoder (U2701), which connects a FAST tap to FCMP through 1 k;
                                     * scanning while counting is off until the circuit change (tap moved to the op-amp output / decoder disable) is verified */
#endif
#define RRH_IMON_PARK_CHAIN 7u      /* address left on the lines while armed: R3 (a reference tap loads one reference channel, not an alpha/beta chain) */

/* Default thresholds above the 0.600 V baseline (rrh_setup_defaults): levels in p.e. of the FAST path
 * of a 6 mm onsemi J-series device (6.9 mV per p.e., budget 2.2) - ASSUMED, replace when the SiPM is chosen. */
#define RRH_FAST_UV_PER_PE 6900u
/* LLD per device type is in rrh_devices[] (T6, +10 degC, dark triggers < 0.05 /s per chain; J60035: 10 p.e., 11 at maximum DCR). */
#define RRH_DEFAULT_ULD_PE 250u      /* above the brightest assumed beta (240 p.e., T13), limited to 1.8 V above baseline */
#define RRH_DEFAULT_ULD_MAX_UV 1800000u
#define RRH_DEFAULT_ALPHA_UV 30000u  /* ALPHA (slow path): just below the assumed alpha minimum of 33 mV; a beta above ~80 p.e. (0.37 mV/p.e.)
                                      * also crosses it - the budget 2.3 ranges overlap (beta maximum 44 mV). ASSUMED */

/* Afterglow hold after an alpha event (IB-18, budget 4): ZnS(Ag) afterglow / slow-baseline undershoot. */
#define RRH_ALPHA_HOLD_DEFAULT_US 300u /* review m2: FAST is still ~3 p.e. low 150 us after a large alpha (PZ network passes DC), zero crossing ~314 us */
#define RRH_ALPHA_HOLD_MAX_US 500u
/* Hold 300 us kept (S3-04): with the 47 nF C150..C850 in the PZ branch the electronics' T14 gives -0.49 p.e. at 150 us and +0.06 p.e. at
 * 300 us after a 15 000 p.e. alpha (-3.3 p.e. at 300 us with the stage-1 network). 150 us would now do for the baseline; the afterglow of
 * ZnS (budget 4: 100 - 200 us) is the other reason and is not removed by the capacitor, so 300 us stays (set 150 on the bench if live time matters). */

/* Heater over-current cut-off on the head's own sense (S3 heater-contact decision): Micro-Fit contact 3.13 A continuous
 * (UNVERIFIED), normal draw up to 3.04 A at 14.6 V, chassis eFuse trips anywhere from 3.56 to 4.35 A. */
#define RRH_HEATER_OC_MA_DEFAULT 3200u
#define RRH_HEATER_OC_MS_DEFAULT 300u   /* sustained: three control periods; the heater switch is opened at once when it expires */
#define RRH_HEATER_OC_MA_MAX 4500u
#define RRH_HEATER_OC_MS_MAX 5000u

/* Frame potential check (S3-03): MON_ADC = 0.300 V + V_FRAME/2 with the lane muxes off. */
#define RRH_FRAME_RISE_MV 30         /* > 15 mV at MON_ADC = 30 mV of frame potential above the stored reference: heater off, FRAME_FAULT */
#define RRH_FRAME_ABS_MIN_MV (-60)   /* nominal window of the frame potential at boot (VBL +-20 mV -> +-20 mV at the frame term, plus offsets) */
#define RRH_FRAME_ABS_MAX_MV 60
#define RRH_MON_GAIN_PCT 98          /* lane monitor tap gain, 10 k into 1 M // 1 M (S3-01); monitor capture is not implemented in the port */
#define RRH_MON_SETTLE_US 2000u      /* settle after a lane mux change (10 k x 50 - 150 pF bus), S3-01 */

/* Alpha classification (review C1): the ALPHA latch alone is not enough, a bright beta (>= ~81 p.e.) crosses the slow
 * threshold too (SLOW 0.369 mV/p.e. for plastic light against 0.218 for ZnS, head_afe_calc_out.md T2). Alpha needs
 * a raw-LLD time over threshold >= this: bright beta 120 p.e. ~ 160 ns, ZnS alpha 150 p.e. >= 280 ns (calculated). */
#define RRH_ALPHA_MIN_TOT_DEFAULT_NS 290u /* only when no device type is set; the cut follows the device (rrh_devices[]) unless overridden */
#define RRH_ALPHA_MIN_TOT_MAX_NS 5000u

/* ALPHA latch set on a chain whose BUSY latch is not (slow light below BETA_LLD): cleared after
 * it has been seen on this many consecutive services (one service is not enough: the capture
 * flag of a real event can lag the latch read-back by one service). */
#define RRH_IDLE_ALPHA_SERVICES 2u

/* Control loop period when no gates are running, and stale-gate watchdog */
#define RRH_CONTROL_PERIOD_US 100000u
#define RRH_GATE_TIMEOUT_SPANS 3u

/* Heater: gate-aligned bang-bang with dwell and duty limit */
#define RRH_HEATER_HYST_MC 500
#define RRH_HEATER_MIN_DWELL_GATES 5u
#define RRH_HEATER_WINDOW_GATES 20u

/* Waveform capture (engineering) */
#define RRH_WAVE_MAX_SAMPLES 4096u
#define RRH_WAVE_CHUNK_MAX 768u

#endif
