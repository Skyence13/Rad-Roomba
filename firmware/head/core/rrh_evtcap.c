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

void rrh_evtcap_set_alpha_hold(rrh_evtcap_t *e, uint32_t ticks)
{
    e->alpha_hold_ticks = ticks;
}

void rrh_evtcap_set_alpha_tot_min(rrh_evtcap_t *e, uint32_t ticks)
{
    e->alpha_tot_min_ticks = ticks;
}

static void clear_accumulators(rrh_evtcap_t *e)
{
    memset(e->count, 0, sizeof e->count);
    memset(e->busy, 0, sizeof e->busy);
    e->saturated = 0u;
    memset(e->width_hist, 0, sizeof e->width_hist);
    memset(e->next_count, 0, sizeof e->next_count);
    memset(e->next_busy, 0, sizeof e->next_busy);
    memset(e->next_width_hist, 0, sizeof e->next_width_hist);
    e->next_saturated = 0u;
    memset(e->short_alpha, 0, sizeof e->short_alpha);
    memset(e->next_short_alpha, 0, sizeof e->next_short_alpha);
    memset(e->idle_clears, 0, sizeof e->idle_clears);
    memset(e->next_idle_clears, 0, sizeof e->next_idle_clears);
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

/* Over-current / frame fault: the switch opens at once, not at the next boundary. The gate that contains the edge is marked
 * (heater_prev still holds the state at its start). */
void rrh_evtcap_heater_force_off(rrh_evtcap_t *e)
{
    e->heater_req = false;
    heater_apply(e, false);
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
        if ((((uint32_t)e->pending >> ch) & 1u) != 0u) {
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
            l->alpha_idle_clears = e->idle_clears[lane];
            l->alpha_short_counts = e->short_alpha[lane];
            if ((((uint32_t)e->saturated >> fc) & 1u) != 0u) {
                l->flags |= RRH_GF_FLOOR_SATURATED;
            }
            if ((((uint32_t)e->saturated >> rc) & 1u) != 0u) {
                l->flags |= RRH_GF_REF_SATURATED;
            }
            if ((((uint32_t)e->chain_enable >> fc) & 1u) == 0u) {
                l->flags |= RRH_GF_FLOOR_INVALID;
                l->floor_live_ticks = 0u; /* a disabled chain never reports a valid zero */
            }
            if ((((uint32_t)e->chain_enable >> rc) & 1u) == 0u) {
                l->flags |= RRH_GF_REF_INVALID;
                l->ref_live_ticks = 0u;
            }
        }
        r->width_mask = e->cfg.width_mask;
        if (r->width_mask != 0u) {
            memcpy(r->width_edges_ns, e->cfg.width_edges_ns, sizeof r->width_edges_ns);
            memcpy(r->width_hist, e->width_hist, sizeof r->width_hist);
        }
        e->fifo_head = next;
    }
    /* The next gate starts with whatever was already booked for it. */
    memcpy(e->width_hist, e->next_width_hist, sizeof e->width_hist);
    memset(e->next_width_hist, 0, sizeof e->next_width_hist);
    memcpy(e->count, e->next_count, sizeof e->count);
    memcpy(e->busy, e->next_busy, sizeof e->busy);
    memcpy(e->short_alpha, e->next_short_alpha, sizeof e->short_alpha);
    memset(e->next_short_alpha, 0, sizeof e->next_short_alpha);
    memcpy(e->idle_clears, e->next_idle_clears, sizeof e->idle_clears);
    memset(e->next_idle_clears, 0, sizeof e->next_idle_clears);
    e->saturated = e->next_saturated;
    memset(e->next_count, 0, sizeof e->next_count);
    memset(e->next_busy, 0, sizeof e->next_busy);
    e->next_saturated = 0u;
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

/* Book the busy interval [from, to) of a chain into the gate in progress and, beyond g1, into the
 * next gate. Both ends are timer readings; the split at g1 is arithmetic. */
static void book_busy(rrh_evtcap_t *e, uint32_t ch, uint64_t from, uint64_t to)
{
    if (from < e->g0) {
        from = e->g0;
    }
    if (to <= from) {
        return;
    }
    if (from < e->g1) {
        e->busy[ch] += ((to < e->g1) ? to : e->g1) - from;
    }
    if (to > e->g1) {
        e->next_busy[ch] += to - ((from > e->g1) ? from : e->g1);
    }
}

static uint32_t width_bin(const rrh_evtcap_t *e, const rrh_evt_in_t *in, uint32_t ch, bool counted)
{
    uint32_t wbin = RRH_WIDTH_BINS;
    if (counted && (((uint32_t)e->cfg.width_mask & (uint32_t)in->width_valid & (1u << ch)) != 0u)) {
        wbin = 0u;
        while ((wbin < (RRH_WIDTH_BINS - 1u)) && (in->width_ticks[ch] >= e->cfg.width_edges_ticks[wbin])) {
            wbin++;
        }
    }
    return wbin;
}

/* ALPHA latch set on an idle floor chain (slow light below BETA_LLD, budget 4 note 1): without
 * this it would be read with the next beta event. Cleared after RRH_IDLE_ALPHA_SERVICES services
 * in a row; one service is not enough because the capture flag of a real event can lag the latch
 * read-back by one service (the flags are sampled before the latch levels). */
static void idle_alpha_service(rrh_evtcap_t *e, uint64_t now, const rrh_evt_in_t *in, uint8_t busy_at_entry)
{
    for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
        const uint8_t bit = (uint8_t)(1u << lane);
        /* the latch levels in `in` predate this service's own clears: a chain that was BUSY when the
         * service began is not idle even if it has been cleared since */
        const bool idle_alpha = ((in->alpha & bit) != 0u) && ((busy_at_entry & bit) == 0u) && ((e->pending & bit) == 0u);
        if (!idle_alpha) {
            e->idle_alpha_seen[lane] = 0u;
            continue;
        }
        if (++e->idle_alpha_seen[lane] < RRH_IDLE_ALPHA_SERVICES) {
            continue;
        }
        e->idle_alpha_seen[lane] = 0u;
        uint64_t clear = e->cfg.clear(e->cfg.ctx, (uint8_t)lane);
        if (clear < now) {
            clear = now;
        }
        e->last_clear[lane] = clear;
        e->total_idle_alpha_clears++;
        if (e->running && (clear >= e->g0)) {
            const uint64_t blind = e->cfg.clear_blind_ticks;
            book_busy(e, lane, (clear > blind) ? (clear - blind) : 0u, clear);
            if (clear < e->g1) {
                e->idle_clears[lane]++;
            } else {
                e->next_idle_clears[lane]++;
            }
        }
    }
}

void rrh_evtcap_service(rrh_evtcap_t *e, uint64_t now, const rrh_evt_in_t *in)
{
    /* 1. Adopt events whose BUSY was captured since the last service. */
    const uint8_t fresh = (uint8_t)(in->busy & (uint8_t)~e->pending);
    for (uint32_t ch = 0u; (fresh != 0u) && (ch < RRH_EVT_CHAINS); ch++) {
        if ((((uint32_t)fresh >> ch) & 1u) != 0u) {
            uint64_t s = in->start_tick[ch];
            if (s < e->last_clear[ch]) {
                s = e->last_clear[ch]; /* a capture cannot precede the previous clear */
            }
            if (s > now) {
                s = now;
            }
            e->start[ch] = s;
            e->pending |= (uint8_t)(1u << ch);
            e->holding &= (uint8_t)~(1u << ch);
        }
    }
    /* 2. Gate boundaries that have passed. */
    while (e->running && (now >= e->g1)) {
        close_gate(e);
    }
    /* 3. Blind chains: comparator high with no BUSY means the latch cannot see an edge. */
    const uint8_t idle_high = (uint8_t)(~in->lld_low & ~e->pending & ~in->busy);
    for (uint32_t ch = 0u; ch < RRH_EVT_CHAINS; ch++) {
        if ((((uint32_t)idle_high >> ch) & 1u) != 0u) {
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
    const uint8_t busy_at_entry = e->pending;
    for (uint32_t ch = 0u; ch < RRH_EVT_CHAINS; ch++) {
        const uint8_t bit = (uint8_t)(1u << ch);
        if ((e->pending & bit) == 0u) {
            continue;
        }
        const uint64_t age = now - e->start[ch];
        const bool in_hold = (e->holding & bit) != 0u;
        bool ready;
        bool forced;
        uint32_t cls;
        uint32_t wbin;
        bool is_short = false;
        if (in_hold) {
            /* class and width were decided when the event first became ready */
            /* The hold itself is never "too long" (it is bounded by RRH_ALPHA_HOLD_MAX_US); the
             * over-long case is a comparator that is still high when the hold has run out. */
            ready = (now >= e->hold_until[ch]) && ((in->lld_low & bit) != 0u);
            forced = !ready && (now >= e->hold_until[ch]) && (age >= e->cfg.max_hold_ticks);
            cls = e->held_cls[ch];
            wbin = e->held_wbin[ch];
        } else {
            ready = (age >= e->cfg.window_ticks) && ((in->lld_low & bit) != 0u);
            forced = !ready && (age >= e->cfg.max_hold_ticks);
            if (!ready && !forced) {
                continue;
            }
            if (ch < 4u) {
                if ((in->alpha & bit) != 0u) {
                    /* The falling-edge flag is sampled before the comparator level: an event that ended in
                     * between has LLD low but no width yet. Wait (at most 2 services) rather than call it short. */
                    if ((e->alpha_tot_min_ticks != 0u) && ((in->width_valid & bit) == 0u) && ((e->cfg.width_mask & bit) != 0u) &&
                        (e->width_wait[ch] < 2u) && ready) {
                        e->width_wait[ch]++;
                        continue;
                    }
                    const bool width_ok = (e->alpha_tot_min_ticks == 0u) ||
                                          ((((uint32_t)e->cfg.width_mask & (uint32_t)in->width_valid & (uint32_t)bit) != 0u) &&
                                           (in->width_ticks[ch] >= e->alpha_tot_min_ticks));
                    is_short = !width_ok;
                    cls = width_ok ? 0u : 2u; /* short ALPHA: a bright beta (or unmeasurable): reject, never alpha */
                } else {
                    cls = ((in->uld & bit) != 0u) ? 2u : 1u;
                }
            } else {
                cls = ((in->uld & bit) != 0u) ? 1u : 0u;
            }
            /* Pulse width of the triggering pulse, if the port measured it: engineering histogram
             * only, the class decision above does not use it. */
            wbin = width_bin(e, in, ch, !forced && ((e->chain_enable & bit) != 0u));
            if (ready && (ch < 4u) && (cls == 0u) && (e->alpha_hold_ticks != 0u)) {
                /* afterglow hold: keep the chain BUSY, decide nothing more */
                e->holding |= bit;
                e->hold_until[ch] = now + e->alpha_hold_ticks;
                e->held_cls[ch] = (uint8_t)cls;
                e->held_wbin[ch] = (uint8_t)wbin;
                e->total_held++;
                continue;
            }
        }
        if (!ready && !forced) {
            continue;
        }
        uint64_t clear = e->cfg.clear(e->cfg.ctx, (uint8_t)ch);
        if (clear < now) {
            clear = now;
        }
        e->pending &= (uint8_t)~bit;
        e->holding &= (uint8_t)~bit;
        if (ch < RRH_LANES) {
            e->width_wait[ch] = 0u;
        }
        e->last_clear[ch] = clear;
        if (!e->running || (clear < e->g0)) {
            continue; /* not recording (yet): the chain is kept clear, nothing is counted */
        }
        const bool counted = !forced && ((e->chain_enable & bit) != 0u);
        book_busy(e, ch, e->start[ch], clear);
        /* An event belongs to the gate that contains its clear time. If the boundary g1 lies
         * between this service's `now` and the clear, the gate cannot be closed yet (other chains
         * may still start an event before g1): the busy time was split by book_busy, the count
         * goes to the next gate. */
        if (forced) {
            if (clear < e->g1) {
                e->saturated |= bit; /* over-long BUSY: not counted, the gate is flagged */
            } else {
                e->next_saturated |= bit;
            }
        } else if (counted) {
            if (is_short) {
                if (clear < e->g1) {
                    e->short_alpha[ch]++;
                } else {
                    e->next_short_alpha[ch]++;
                }
            }
            if (clear < e->g1) {
                e->count[ch][cls]++;
                if (wbin < RRH_WIDTH_BINS) {
                    e->width_hist[ch][wbin]++;
                }
            } else {
                e->next_count[ch][cls]++;
                if (wbin < RRH_WIDTH_BINS) {
                    e->next_width_hist[ch][wbin]++;
                }
            }
        } else {
            /* disabled chain: cleared, never counted */
        }
        if (forced) {
            e->total_forced++;
        } else if (counted) {
            e->total_events++;
        } else {
            /* nothing */
        }
    }
    /* 5. ALPHA latches on idle floor chains. */
    idle_alpha_service(e, now, in, busy_at_entry);
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
