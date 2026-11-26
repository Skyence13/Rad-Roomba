/* Compile-time configuration of the head firmware core. Sizes are RAM budget decisions;
 * the protocol limits come from interface/head_icd.md and interface/system/contract.yaml. */
#ifndef RRH_CONFIG_H
#define RRH_CONFIG_H

#define RRH_FW_VERSION "rr-head-0.4.0"
#define RRH_PROTO_VERSION "2.0"
#define RRH_ACQ_FORMAT "2.0"
#define RRH_HEAD_TYPE "FOUR_LANE_ZNS_PLASTIC_WITH_REFERENCE"

#define RRH_LANES 4u
#define RRH_WIDTH_BINS 4u /* coarse pulse-width (time over threshold) histogram bins per chain */

/* Link */
#define RRH_RX_MAX 8192u          /* ICD section 4: maximum record including trailer */
#define RRH_TX_MAX 4096u          /* largest reply this firmware produces is < 2 kB */
#define RRH_JSON_TOKENS 96u       /* largest legal request (ENG_SETUP_SET) needs ~70 */
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
#define RRH_BIAS_MIN_MV 20000u
#define RRH_BIAS_MAX_MV 60000u
#define RRH_BIAS_TOLERANCE_MV 500u
#define RRH_BIAS_CURRENT_MAX_UA 500u
#define RRH_BIAS_STEP_MV 20u             /* slew limit per control period */
#define RRH_BIAS_DEADBAND_MV 5u
#define RRH_BIAS_SETTLE_PERIODS 5u

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
