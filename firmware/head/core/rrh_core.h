/* Rad Roomba detector-head firmware core: hardware-independent implementation of head
 * protocol 2.0 (interface/head_icd.md) plus the additive 0.4 ops
 * (interface/head_icd_addendum_0.4.md). No dynamic allocation; all state is in rrh_core_t.
 *
 * Usage by a port:
 *     static rrh_core_t core;
 *     rrh_core_init(&core, &identity);
 *     for (;;) {
 *         rrh_core_poll(&core);                              // gates, control loops, watchdog
 *         for each received byte b (rx_us = head clock at the end of that byte):
 *             if (rrh_core_rx_byte(&core, b, rx_us, &reply)) transmit(reply);
 *         on receive idle timeout: rrh_core_rx_timeout(&core);
 *     }
 */
#ifndef RRH_CORE_H
#define RRH_CORE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "rr_common.h"
#include "rrh_config.h"
#include "rrh_hal.h"
#ifdef __cplusplus
extern "C" {
#endif

/* ---- identity (factory data supplied by the port) --------------------------------------- */
typedef struct {
    char serial[49];
    char descriptor_id[49];
    char mechanical_revision[17];
    char electronics_revision[33];
    char geometry_id[49];
    uint32_t gate_min_us; /* descriptor gate_range_us and ARM limits */
    uint32_t gate_max_us;
    bool rail_5mm; /* 5 mm bumper-rail projection trial instead of the 3 mm baseline */
    /* Bench/emulator only: serve these exact descriptor bytes and identifiers instead of the
     * built descriptor (used to reproduce the 0.3 baseline examples byte for byte). All NULL on
     * the target. With an override, ENG_SETUP_SET is UNSUPPORTED. */
    const uint8_t *descriptor_override;
    size_t descriptor_override_len;
    const char *setup_id_override;
    const char *firmware_override;
} rrh_identity_t;

/* ---- setup: everything that can change a sample; hashed into setup_id -------------------- */
typedef struct {
    rrh_frontend_cfg_t fe;
    uint32_t bias_ref_mv;       /* bias set-point at t_ref_mc */
    int32_t bias_tc_uv_per_c;   /* temperature coefficient, microvolt per degC */
    int32_t t_ref_mc;
    bool heater_enable;
    int32_t heater_setpoint_mc;
    uint8_t heater_max_duty_pct;
} rrh_setup_t;

/* ---- link state --------------------------------------------------------------------------- */
typedef enum {
    RRH_LINK_UNBOUND = 0, /* boot, or binding invalidated: only HELLO opens a handshake */
    RRH_LINK_HANDSHAKE,   /* HELLO answered: GET_DESCRIPTOR and BIND are accepted */
    RRH_LINK_BOUND        /* BIND accepted: TIME, SYNC, ARM, READ, DISARM, DIAG are served */
} rrh_link_state_t;

/* ---- latched health bits (cleared only by FAULT_CLEAR with the cause gone, or by a reset) --- */
#define RRH_H_SOURCE 0x0001u          /* event capture or front-end configuration fault */
#define RRH_H_GATE_TIMING 0x0002u     /* gate length or contiguity violated */
#define RRH_H_RECORD_LOST 0x0004u     /* one or more gate records were lost */
#define RRH_H_GATE_TIMEOUT 0x0008u    /* armed but no gate arrived in time */
#define RRH_H_INJECTED 0x0010u        /* deliberate fault (ENG_FAULT) */
#define RRH_H_HEATER_SENSOR 0x0020u   /* heater-plate sensor open/short while heating enabled */
#define RRH_H_HEATER_CUTOUT 0x0040u   /* hardware thermal cut-out open while heating enabled */
#define RRH_H_HEATER_OVERTEMP 0x0080u /* heater plate above the software limit */
#define RRH_H_HEATER_STUCK 0x0100u    /* heater reported on while commanded off */
#define RRH_H_BIAS_TRIP 0x0200u       /* bias over-current: converter disabled */
#define RRH_H_ENTROPY 0x0400u         /* entropy source failed at boot (boot id still unique) */
#define RRH_H_STORAGE 0x0800u         /* stored setup unreadable: defaults in use */
#define RRH_H_WATCHDOG_RESET 0x1000u  /* this boot followed a watchdog reset */
#define RRH_H_ALL 0x1FFFu

/* ---- retained frame (ACQ + DIAG source data for one gate) --------------------------------- */
#define RRH_SYNC_UNSYNCED 0u
#define RRH_SYNC_LOCKED 1u
#define RRH_SYNC_HOLDOVER 2u

#define RRH_CH_ALPHA 0x01u
#define RRH_CH_BETA 0x02u
#define RRH_CH_REF 0x04u

/* ACQ 2.0 segment flag bits (order = schema enum order) */
#define RRH_SF_FLOOR_FAULT 0x01u
#define RRH_SF_REFERENCE_FAULT 0x02u
#define RRH_SF_SATURATED 0x04u
#define RRH_SF_DEAD_TIME_UNKNOWN 0x08u
#define RRH_SF_DISCRIMINATOR_FAULT 0x10u

/* ACQ 2.0 global flag bits (order = schema enum order) */
#define RRH_AF_ACQ_FAULT 0x01u
#define RRH_AF_HEAD_TEMP_OUT_OF_RANGE 0x02u
#define RRH_AF_UNDERVOLTAGE 0x04u
#define RRH_AF_BIAS_OUT_OF_RANGE 0x08u
#define RRH_AF_HEATER_FAULT 0x10u
#define RRH_AF_OVERTEMP 0x20u

typedef struct {
    uint32_t alpha, beta, ref;          /* gross counts (valid where the null bit is clear) */
    uint32_t floor_live_us, ref_live_us;
    uint32_t floor_reject, ref_reject;  /* DIAG */
    uint32_t floor_live_ticks, ref_live_ticks;
    uint8_t null_mask;                  /* RRH_CH_*: channel reported as null */
    uint8_t seg_flags;                  /* RRH_SF_* */
    uint8_t gate_flags;                 /* RRH_GF_* as delivered (DIAG) */
} rrh_frame_lane_t;

typedef struct {
    uint64_t sequence;
    uint64_t start_us;
    uint32_t span_us;
    uint8_t sync_state;
    int8_t sync_slot; /* index into the sync table, -1 if UNSYNCED */
    uint32_t sync_bound_us;
    uint64_t sync_age_us;
    int32_t head_mc; /* RRH_TEMP_INVALID -> null */
    uint8_t heater;  /* 0 OFF, 1 ON, 2 FAULT */
    uint8_t duty_pct;
    uint8_t acq_flags; /* RRH_AF_* */
    rrh_frame_lane_t lane[RRH_LANES];
    /* DIAG-only data */
    uint64_t gate_start_tick;
    uint32_t gate_ticks;
    uint32_t tick_hz;
    uint32_t heater_on_us;
    bool heater_transition;
    uint16_t health; /* RRH_H_* latched when the gate completed */
    uint32_t bias_mv, bias_ua, bias_set_mv;
    int32_t sipm_mc[RRH_LANES];
    int32_t heater_plate_mc, board_mc;
    uint32_t supply_mv;
    uint8_t bumper_zones; /* zones seen closed at any poll during the gate */
} rrh_frame_t;

typedef struct {
    bool used;
    uint32_t gen;        /* installation order */
    uint32_t refs;       /* retained frames referencing this record */
    uint64_t installed_us;
    uint64_t expiry_us;
    uint32_t bound_us;
    char id[RRH_SYNC_ID_MAX + 1u];
} rrh_sync_slot_t;

typedef struct {
    const uint8_t *data;
    size_t len;
    uint64_t tx_at_us; /* 0 = as soon as the bus turnaround allows; else start exactly then */
} rrh_reply_t;

typedef struct {
    /* identity and derived handshake values */
    rrh_identity_t ident;
    rrh_setup_t setup;
    char boot_id[RRC_UUID_STR_LEN + 1u];
    char setup_id[97];
    char descriptor_sha256[RRC_SHA256_HEX_LEN + 1u];
    const uint8_t *descriptor;
    size_t descriptor_len;
    uint8_t descriptor_buf[RRH_DESCRIPTOR_MAX];
    rrh_reset_cause_t reset_cause;

    /* link */
    rrh_link_state_t link;
    rrc_frame_rx_t rx;
    uint64_t rx_last_us;
    rrc_reply_cache_t cache;
    uint8_t rx_buf[RRH_RX_MAX];
    uint8_t tx_buf[RRH_TX_MAX];
    uint32_t n_requests, n_retries, n_discarded;
    uint32_t rx_gap_timeout_us; /* a partial record is dropped after this much line idle time */

    /* acquisition */
    bool armed;       /* ARM accepted and no DISARM since */
    bool draining;    /* DISARM accepted, final gate not yet delivered */
    uint32_t span_us;
    uint64_t first_seq;       /* first sequence of the current / last run */
    uint64_t next_seq;        /* sequence the next completed gate will get */
    uint32_t expect_src_seq;  /* next sequence expected from the source */
    bool have_prev_tick;
    uint64_t prev_end_tick;
    rrh_epoch_t epoch;
    uint64_t last_gate_us;    /* head clock when the last gate completed (or ARM time) */
    rrh_frame_t frames[RRH_FRAME_BUFFER];
    uint32_t frame_head;      /* index of the oldest frame */
    uint32_t frame_count;
    rrh_sync_slot_t sync[RRH_SYNC_SLOTS];
    uint32_t sync_gen;
    int8_t sync_pinned;       /* slot that applies to the gate in progress, -1 if none */

    /* housekeeping and control */
    rrh_analog_t analog;
    uint64_t control_due_us;
    uint16_t health;          /* RRH_H_* latched */
    uint8_t live_flags;       /* RRH_AF_* conditions true at the last evaluation */
    uint8_t bumper_latched;   /* zones seen since the last HELLO / STATUS clear */
    uint8_t bumper_gate;      /* zones seen during the gate in progress */
    uint32_t bias_cmd_mv;     /* commanded bias set-point */
    bool bias_on;
    uint32_t bias_settle;     /* control periods since the last set-point change */
    bool heater_on;           /* state requested from the port */
    uint32_t heater_dwell;    /* gates spent in the current state */
    uint32_t heater_history;  /* bit n: heater requested on n gates ago */
} rrh_core_t;

/* Initialise after reset. Generates the boot id, loads (or defaults) the setup, builds the
 * descriptor, applies the setup to the hardware. The link starts UNBOUND. */
void rrh_core_init(rrh_core_t *c, const rrh_identity_t *ident);

/* Periodic work: drain completed gates, control loops, health, watchdog. Call at >= 100 Hz. */
void rrh_core_poll(rrh_core_t *c);

/* Feed one received byte with the head-clock time of its end. Returns true when a reply must
 * be transmitted (reply->data stays valid until the next call into the core). */
bool rrh_core_rx_byte(rrh_core_t *c, uint8_t byte, uint64_t rx_us, rrh_reply_t *reply);
/* Receive idle timeout: drop a partial record. */
void rrh_core_rx_timeout(rrh_core_t *c);

/* Default setup and identity helpers for ports. */
void rrh_setup_defaults(rrh_setup_t *s);
void rrh_identity_defaults(rrh_identity_t *id, const char *serial);

#ifdef __cplusplus
}
#endif
#endif
