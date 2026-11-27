/* Event capture (contract.yaml head_event_capture, DEC-037): the pure logic that turns
 * hardware-captured BUSY start times, latch read-backs and measured clear times into
 * `head_gate_record`s. No hardware access: the port samples the inputs and supplies two
 * callbacks, so the module runs unchanged under host tests with synthetic event streams.
 *
 * Per chain (0..3 = floor lanes, 4..7 = reference lanes) the hardware is a non-retriggerable
 * BUSY latch on the low threshold plus class latches (floor: ULD, ALPHA; reference: ULD).
 *
 * rrh_evtcap_service() is called at a fixed rate (default 100 kHz). For every chain whose BUSY
 * has been set for at least the acceptance window and whose LLD comparator is low again it
 *   classifies   floor: ALPHA -> alpha, else ULD -> reject, else beta
 *                ref:   ULD -> reject, else count
 *   clears       through the clear callback, which returns the timer reading of the clear
 *   accounts     busy = clear - captured start, split exactly at gate boundaries
 * An event belongs to the gate that contains its clear time. Live time of a gate is
 * gate_ticks - busy; nothing is inferred from a nominal dead time or from the service rate.
 *
 * Afterglow hold (IB-18b): an event classified alpha is not cleared at once; the chain stays BUSY
 * for alpha_hold ticks counted from the service that found it ready (window elapsed, comparator
 * low), and is cleared by the first service after that at which the comparator is low again. The
 * class (and pulse width) are decided when the event first becomes ready, so light that arrives
 * during the hold cannot reclassify it. The hold is inside [captured start, clear), hence inside
 * the measured busy time: live time stays exact.
 * Idle ALPHA latch (IB-18a): an ALPHA latch set on a floor chain that has no BUSY is cleared
 * after RRH_IDLE_ALPHA_SERVICES consecutive services (counted per gate for DIAG).
 *
 * Concurrency: service() runs in the service interrupt; every other function is called from the
 * main loop with that interrupt masked (the port's job).
 */
#ifndef RRH_EVTCAP_H
#define RRH_EVTCAP_H
#include <stdbool.h>
#include <stdint.h>

#include "rrh_hal.h"
#ifdef __cplusplus
extern "C" {
#endif

#define RRH_EVT_CHAINS 8u
#define RRH_EVT_FIFO 4u       /* completed gates waiting for the main loop */
#define RRH_EVT_BLIND_SERVICES 3u /* LLD high without BUSY for this many services = blind chain */

/* Inputs sampled by the port at one service call. Bit n = chain n. */
typedef struct {
    uint8_t busy;    /* BUSY latch set; start_tick[n] holds the hardware-captured rising edge */
    uint8_t lld_low; /* LLD comparator is low now (the pulse is over) */
    uint8_t uld;     /* ULD latch set */
    uint8_t alpha;   /* ALPHA latch set (floor chains, bits 0..3) */
    uint64_t start_tick[RRH_EVT_CHAINS];
    /* Optional: time over threshold of the pulse that set BUSY (raw LLD falling edge minus the
     * captured start). width_valid bit n set = width_ticks[n] is valid for the pending event. */
    uint8_t width_valid;
    uint32_t width_ticks[RRH_EVT_CHAINS];
} rrh_evt_in_t;

/* Pulse CLR of one chain and return the tick at which the chain can accept the next event. */
typedef uint64_t (*rrh_evt_clear_fn)(void *ctx, uint8_t chain);
/* Switch the heater output (called on gate boundaries, or at once when no gates run). */
typedef void (*rrh_evt_heater_fn)(void *ctx, bool on);

typedef struct {
    uint32_t tick_hz;
    uint32_t window_ticks;   /* acceptance window W: class latches are valid after it */
    uint32_t max_hold_ticks; /* BUSY longer than this without LLD low: chain saturated, forced clear */
    rrh_evt_clear_fn clear;
    rrh_evt_heater_fn heater;
    void *ctx;
    /* Pulse-width histogram (optional): chains on which the port measures widths (0 = none) and
     * the upper edges of bins 0 .. RRH_WIDTH_BINS-2 in ticks and, for the record, in ns. */
    uint8_t width_mask;
    uint32_t width_edges_ticks[RRH_WIDTH_BINS - 1u];
    uint32_t width_edges_ns[RRH_WIDTH_BINS - 1u];
    /* Length of the interval that ends at the tick returned by clear() during which the chain is
     * blind (CLR low plus latch recovery). Booked as dead time for a clear that ends no event
     * (an ALPHA latch cleared on an idle chain); an event's own clear is inside its busy interval. */
    uint32_t clear_blind_ticks;
} rrh_evt_cfg_t;

typedef struct {
    rrh_evt_cfg_t cfg;
    uint8_t chain_enable;
    bool running;
    bool stopping;
    uint64_t g0, g1; /* current gate [g0, g1) */
    uint32_t gate_ticks;
    uint32_t seq;
    uint8_t pending; /* chains with an event waiting for classification */
    uint64_t start[RRH_EVT_CHAINS];
    uint64_t last_clear[RRH_EVT_CHAINS];
    uint8_t blind_count[RRH_EVT_CHAINS];
    /* afterglow hold (IB-18): after an alpha event has been classified the chain is kept BUSY
     * (not cleared) until hold_until, so the hold is part of the measured busy interval */
    uint32_t alpha_hold_ticks;
    uint8_t holding;                       /* chains in the hold state */
    uint64_t hold_until[RRH_EVT_CHAINS];
    uint8_t held_cls[RRH_EVT_CHAINS];
    uint8_t held_wbin[RRH_EVT_CHAINS];
    uint8_t idle_alpha_seen[RRH_LANES];    /* consecutive services with ALPHA set on an idle floor chain */
    uint32_t idle_clears[RRH_LANES];       /* accumulators of the gate in progress */
    uint32_t next_idle_clears[RRH_LANES];
    /* accumulators of the gate in progress */
    uint32_t count[RRH_EVT_CHAINS][3]; /* floor: alpha, beta, reject; reference: count, reject, - */
    uint64_t busy[RRH_EVT_CHAINS];
    uint8_t saturated;
    /* events cleared a few ticks AFTER the boundary by a service that began before it: they
     * belong to the next gate and wait here until the current one has been closed */
    uint32_t width_hist[RRH_EVT_CHAINS][RRH_WIDTH_BINS];
    uint32_t next_width_hist[RRH_EVT_CHAINS][RRH_WIDTH_BINS];
    uint32_t next_count[RRH_EVT_CHAINS][3];
    uint64_t next_busy[RRH_EVT_CHAINS];
    uint8_t next_saturated;
    bool heater_state, heater_prev, heater_req;
    /* completed gates */
    rrh_gate_record_t fifo[RRH_EVT_FIFO];
    volatile uint32_t fifo_head, fifo_tail;
    uint32_t lost_gates;
    /* lifetime totals (diagnostics and tests) */
    uint64_t total_events, total_forced, total_held, total_idle_alpha_clears;
} rrh_evtcap_t;

void rrh_evtcap_init(rrh_evtcap_t *e, const rrh_evt_cfg_t *cfg);
void rrh_evtcap_set_chain_enable(rrh_evtcap_t *e, uint8_t mask);
/* Afterglow hold after an alpha event in ticks (0 = off). Not while recording. */
void rrh_evtcap_set_alpha_hold(rrh_evtcap_t *e, uint32_t ticks);
/* Start equal gates of gate_ticks; the first gate begins at first_gate_tick (>= now). */
bool rrh_evtcap_start(rrh_evtcap_t *e, uint64_t first_gate_tick, uint32_t gate_ticks);
/* Finish the gate in progress, then stop. Returns true if a gate is in progress at now_tick. */
bool rrh_evtcap_stop(rrh_evtcap_t *e, uint64_t now_tick);
void rrh_evtcap_abort(rrh_evtcap_t *e);
bool rrh_evtcap_running(const rrh_evtcap_t *e);
void rrh_evtcap_heater_request(rrh_evtcap_t *e, bool on);
/* Fixed-rate service. now_tick must not decrease between calls. */
void rrh_evtcap_service(rrh_evtcap_t *e, uint64_t now_tick, const rrh_evt_in_t *in);
/* Oldest completed gate; false if none. */
bool rrh_evtcap_pop(rrh_evtcap_t *e, rrh_gate_record_t *rec);

#ifdef __cplusplus
}
#endif
#endif
