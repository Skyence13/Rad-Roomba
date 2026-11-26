#include "rrh_evtcap.h"

#include <string.h>

void rrh_evtcap_init(rrh_evtcap_t *e, const rrh_evt_cfg_t *cfg)
{
    memset(e, 0, sizeof *e);
    e->cfg = *cfg;
    e->chain_enable = 0xFFu;
}

void rrh_evtcap_set_chain_enable(rrh_evtcap_t *e, uint8_t mask)
{
    e->chain_enable = mask;
}

static void clear_accumulators(rrh_evtcap_t *e)
{
    memset(e->count, 0, sizeof e->count);
    memset(e->busy, 0, sizeof e->busy);
    e->saturated = 0u;
}

bool rrh_evtcap_start(rrh_evtcap_t *e, uint64_t first_gate_tick, uint32_t gate_ticks)
{
    if ((gate_ticks == 0u) || (e->cfg.tick_hz == 0u)) {
        return false;
    }
    clear_accumulators(e);
    e->g0 = first_gate_tick;
    e->g1 = first_gate_tick + gate_ticks;
    e->gate_ticks = gate_ticks;
    e->seq = 0u;
    e->fifo_tail = e->fifo_head; /* drop anything left from an earlier run */
    e->heater_prev = e->heater_state;
    e->stopping = false;
    e->running = true;
    return true;
}

bool rrh_evtcap_stop(rrh_evtcap_t *e, uint64_t now_tick)
{
    if (!e->running) {
        return false;
    }
    if (now_tick < e->g0) {
        e->running = false; /* the first gate never started: nothing will be delivered */
        return false;
    }
    e->stopping = true;
    return true;
}

static void heater_apply(rrh_evtcap_t *e, bool on)
{
    if (on != e->heater_state) {
        e->heater_state = on;
        if (e->cfg.heater != NULL) {
            e->cfg.heater(e->cfg.ctx, on);
        }
    }
}

void rrh_evtcap_abort(rrh_evtcap_t *e)
{
    e->running = false;
    e->stopping = false;
    e->fifo_tail = e->fifo_head;
    heater_apply(e, e->heater_req);
}

bool rrh_evtcap_running(const rrh_evtcap_t *e)
{
    return e->running || (e->fifo_head != e->fifo_tail);
}

void rrh_evtcap_heater_request(rrh_evtcap_t *e, bool on)
{
    e->heater_req = on;
    if (!e->running) {
        heater_apply(e, on); /* no gate boundaries to wait for */
    }
}

static uint32_t live_of(const rrh_evtcap_t *e, uint32_t chain)
{
    return (e->busy[chain] >= e->gate_ticks) ? 0u : (e->gate_ticks - (uint32_t)e->busy[chain]);
}

/* Close the gate [g0, g1): give it the busy time of events still open at g1, snapshot it into
 * the FIFO, start the next gate at g1, apply a pending heater request on this boundary. */
static void close_gate(rrh_evtcap_t *e)
{
    for (uint32_t ch = 0u; ch < RRH_EVT_CHAINS; ch++) {
        if (((e->pending >> ch) & 1u) != 0u) {
            const uint64_t from = (e->start[ch] > e->g0) ? e->start[ch] : e->g0;
            if (from < e->g1) {
                e->busy[ch] += e->g1 - from;
            }
        }
    }
    const uint32_t next = (e->fifo_head + 1u) % RRH_EVT_FIFO;
    if (next == e->fifo_tail) {
        e->lost_gates++; /* main loop too slow: the gap shows up as a sequence skip */
    } else {
        rrh_gate_record_t *r = &e->fifo[e->fifo_head];
        memset(r, 0, sizeof *r);
        r->sequence = e->seq;
        r->gate_start_tick = e->g0;
        r->gate_ticks = e->gate_ticks;
        r->tick_hz = e->cfg.tick_hz;
        r->heater_on_ticks = e->heater_state ? e->gate_ticks : 0u;
        r->heater_transition_in_gate = e->heater_state != e->heater_prev;
        for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
            rrh_gate_lane_t *l = &r->lane[lane];
            const uint32_t fc = lane;
            const uint32_t rc = lane + 4u;
            l->alpha_counts = e->count[fc][0];
            l->beta_counts = e->count[fc][1];
            l->floor_reject_counts = e->count[fc][2];
            l->floor_live_ticks = live_of(e, fc);
            l->ref_counts = e->count[rc][0];
            l->ref_reject_counts = e->count[rc][1];
            l->ref_live_ticks = live_of(e, rc);
            if (((e->saturated >> fc) & 1u) != 0u) {
                l->flags |= RRH_GF_FLOOR_SATURATED;
            }
            if (((e->saturated >> rc) & 1u) != 0u) {
                l->flags |= RRH_GF_REF_SATURATED;
            }
            if (((e->chain_enable >> fc) & 1u) == 0u) {
                l->flags |= RRH_GF_FLOOR_INVALID;
                l->floor_live_ticks = 0u; /* a disabled chain never reports a valid zero */
            }
            if (((e->chain_enable >> rc) & 1u) == 0u) {
                l->flags |= RRH_GF_REF_INVALID;
                l->ref_live_ticks = 0u;
            }
        }
        e->fifo_head = next;
    }
    clear_accumulators(e);
    e->heater_prev = e->heater_state;
    e->g0 = e->g1;
    e->g1 += e->gate_ticks;
    e->seq++;
    if (e->stopping) {
        e->stopping = false;
        e->running = false;
        e->heater_req = false; /* the heater goes off with the final gate */
    }
    heater_apply(e, e->heater_req);
}

void rrh_evtcap_service(rrh_evtcap_t *e, uint64_t now, const rrh_evt_in_t *in)
{
    /* 1. Adopt events whose BUSY was captured since the last service. */
    const uint8_t fresh = (uint8_t)(in->busy & (uint8_t)~e->pending);
    for (uint32_t ch = 0u; (fresh != 0u) && (ch < RRH_EVT_CHAINS); ch++) {
        if (((fresh >> ch) & 1u) != 0u) {
            uint64_t s = in->start_tick[ch];
            if (s < e->last_clear[ch]) {
                s = e->last_clear[ch]; /* a capture cannot precede the previous clear */
            }
            if (s > now) {
                s = now;
            }
            e->start[ch] = s;
            e->pending |= (uint8_t)(1u << ch);
        }
    }
    /* 2. Gate boundaries that have passed. */
    while (e->running && (now >= e->g1)) {
        close_gate(e);
    }
    /* 3. Blind chains: comparator high with no BUSY means the latch cannot see an edge. */
    const uint8_t idle_high = (uint8_t)(~in->lld_low & ~e->pending & ~in->busy);
    for (uint32_t ch = 0u; ch < RRH_EVT_CHAINS; ch++) {
        if (((idle_high >> ch) & 1u) != 0u) {
            if (e->blind_count[ch] < RRH_EVT_BLIND_SERVICES) {
                e->blind_count[ch]++;
            } else {
                e->saturated |= (uint8_t)(1u << ch);
            }
        } else {
            e->blind_count[ch] = 0u;
        }
    }
    /* 4. Classify and clear. */
    if (e->pending == 0u) {
        return;
    }
    for (uint32_t ch = 0u; ch < RRH_EVT_CHAINS; ch++) {
        const uint8_t bit = (uint8_t)(1u << ch);
        if ((e->pending & bit) == 0u) {
            continue;
        }
        const uint64_t age = now - e->start[ch];
        const bool ready = (age >= e->cfg.window_ticks) && ((in->lld_low & bit) != 0u);
        const bool forced = !ready && (age >= e->cfg.max_hold_ticks);
        if (!ready && !forced) {
            continue;
        }
        uint32_t cls;
        if (ch < 4u) {
            cls = ((in->alpha & bit) != 0u) ? 0u : (((in->uld & bit) != 0u) ? 2u : 1u);
        } else {
            cls = ((in->uld & bit) != 0u) ? 1u : 0u;
        }
        uint64_t clear = e->cfg.clear(e->cfg.ctx, (uint8_t)ch);
        if (clear < now) {
            clear = now;
        }
        /* The boundary may fall between `now` and the clear: the event then belongs to the
         * next gate and its busy interval is split at the boundary. */
        while (e->running && (clear >= e->g1)) {
            close_gate(e);
        }
        e->pending &= (uint8_t)~bit;
        e->last_clear[ch] = clear;
        if (e->running && (clear >= e->g0)) {
            const uint64_t from = (e->start[ch] > e->g0) ? e->start[ch] : e->g0;
            e->busy[ch] += clear - from;
            if (forced) {
                e->saturated |= bit; /* over-long BUSY: not counted, the gate is flagged */
                e->total_forced++;
            } else if ((e->chain_enable & bit) != 0u) {
                e->count[ch][cls]++;
                e->total_events++;
            } else {
                /* disabled chain: cleared, never counted */
            }
        }
    }
}

bool rrh_evtcap_pop(rrh_evtcap_t *e, rrh_gate_record_t *rec)
{
    if (e->fifo_tail == e->fifo_head) {
        return false;
    }
    *rec = e->fifo[e->fifo_tail];
    e->fifo_tail = (e->fifo_tail + 1u) % RRH_EVT_FIFO;
    return true;
}
