/* Gate records -> retained ACQ frames; sync-quality records; ACQ and DIAG serialisation.
 *
 * Mapping rules (contract.yaml head_gate_record.acq_mapping, head ICD section 5):
 *   alpha       = {alpha_counts, floor_live_us}
 *   beta_window = {beta_counts,  floor_live_us}      (floor chain: one shared acceptance gate)
 *   photon_ref  = {ref_counts,   ref_live_us}
 *   live_us     = floor(live_ticks * 1e6 / tick_hz)  (never derived from wall time)
 * A channel is null, with a segment flag, when any of these holds:
 *   FLOOR_SATURATED / REF_SATURATED            -> SATURATED
 *   live fraction < RRH_MIN_LIVE_PERCENT       -> SATURATED
 *   live_ticks == 0 or > gate_ticks            -> DEAD_TIME_UNKNOWN
 *   BASELINE_SHIFT (lane)                      -> DISCRIMINATOR_FAULT, all three channels
 *   BIAS_OUT_OF_RANGE (lane)                   -> FLOOR_FAULT + REFERENCE_FAULT, all three
 *   chain invalid/disabled, front-end fault    -> FLOOR_FAULT or REFERENCE_FAULT for that chain
 * A measured zero stays {"counts":0,"live_us":n}.
 */
#include <string.h>

#include "rrh_internal.h"

/* ---- frame ring -------------------------------------------------------------------------- */
static rrh_frame_t *frame_at(rrh_core_t *c, uint32_t i)
{
    return &c->frames[(c->frame_head + i) % RRH_FRAME_BUFFER];
}

static const rrh_frame_t *cframe_at(const rrh_core_t *c, uint32_t i)
{
    return &c->frames[(c->frame_head + i) % RRH_FRAME_BUFFER];
}

const rrh_frame_t *rrh_acq_oldest(const rrh_core_t *c)
{
    return (c->frame_count == 0u) ? NULL : cframe_at(c, 0u);
}

const rrh_frame_t *rrh_acq_newest(const rrh_core_t *c)
{
    return (c->frame_count == 0u) ? NULL : cframe_at(c, c->frame_count - 1u);
}

/* First retained frame with sequence > after_seq (frames are stored in ascending order). */
const rrh_frame_t *rrh_acq_first_after(const rrh_core_t *c, int64_t after_seq)
{
    uint32_t lo = 0u;
    uint32_t hi = c->frame_count;
    while (lo < hi) {
        const uint32_t mid = lo + ((hi - lo) / 2u);
        if ((after_seq >= 0) && (cframe_at(c, mid)->sequence <= (uint64_t)after_seq)) {
            lo = mid + 1u;
        } else {
            hi = mid;
        }
    }
    return (lo < c->frame_count) ? cframe_at(c, lo) : NULL;
}

const rrh_frame_t *rrh_acq_find(const rrh_core_t *c, uint64_t seq)
{
    const rrh_frame_t *f = (seq == 0u) ? rrh_acq_oldest(c) : rrh_acq_first_after(c, (int64_t)(seq - 1u));
    return ((f != NULL) && (f->sequence == seq)) ? f : NULL;
}

void rrh_acq_reset(rrh_core_t *c)
{
    c->frame_head = 0u;
    c->frame_count = 0u;
    c->next_seq = 0u;
    c->first_seq = 0u;
    c->have_prev_tick = false;
    memset(c->sync, 0, sizeof c->sync);
    c->sync_gen = 0u;
    c->sync_pinned = -1;
}

static rrh_frame_t *frame_alloc(rrh_core_t *c)
{
    if (c->frame_count == RRH_FRAME_BUFFER) {
        /* Overwrite the oldest frame: the host sees GAP if it had not read it. */
        const rrh_frame_t *old = frame_at(c, 0u);
        if ((old->sync_slot >= 0) && (c->sync[old->sync_slot].refs > 0u)) {
            c->sync[old->sync_slot].refs--;
        }
        c->frame_head = (c->frame_head + 1u) % RRH_FRAME_BUFFER;
        c->frame_count--;
    }
    rrh_frame_t *f = frame_at(c, c->frame_count);
    c->frame_count++;
    return f;
}

/* ---- sync-quality records ------------------------------------------------------------------- */
static int sync_newest(const rrh_core_t *c, uint64_t not_after_us)
{
    int best = -1;
    for (uint32_t i = 0u; i < RRH_SYNC_SLOTS; i++) {
        const rrh_sync_slot_t *s = &c->sync[i];
        if (s->used && (s->installed_us <= not_after_us) && ((best < 0) || (s->gen > c->sync[best].gen))) {
            best = (int)i;
        }
    }
    return best;
}

void rrh_sync_pin_newest(rrh_core_t *c)
{
    c->sync_pinned = (int8_t)sync_newest(c, UINT64_MAX);
}

bool rrh_sync_install(rrh_core_t *c, const char *id, uint32_t bound_us, uint64_t expiry_us, uint64_t now_us)
{
    /* A slot may be reused when no retained frame references it and no gate can still need it:
     * it must be older than the record that applies to the gate in progress (armed) or older
     * than the newest record (not armed). */
    const int newest = sync_newest(c, UINT64_MAX);
    const bool gate_open = c->armed || c->draining;
    const int keep = gate_open ? (int)c->sync_pinned : newest;
    int slot = -1;
    for (uint32_t i = 0u; (i < RRH_SYNC_SLOTS) && (slot < 0); i++) {
        const rrh_sync_slot_t *s = &c->sync[i];
        if (!s->used) {
            slot = (int)i;
        } else if ((s->refs == 0u) && (keep >= 0) && (s->gen < c->sync[keep].gen)) {
            slot = (int)i;
        } else if ((s->refs == 0u) && !gate_open) {
            slot = (int)i; /* nothing retained and no gate open: any unreferenced record may go */
        } else {
            /* still needed */
        }
    }
    if (slot < 0) {
        return false;
    }
    rrh_sync_slot_t *s = &c->sync[slot];
    memset(s, 0, sizeof *s);
    s->used = true;
    c->sync_gen++;
    s->gen = c->sync_gen;
    s->installed_us = now_us;
    s->expiry_us = expiry_us;
    s->bound_us = bound_us;
    strncpy(s->id, id, RRH_SYNC_ID_MAX);
    return true;
}

/* Time quality of a gate that starts at start_us. */
static void sync_evaluate(rrh_core_t *c, rrh_frame_t *f, uint64_t start_us)
{
    const int slot = sync_newest(c, start_us);
    f->sync_state = RRH_SYNC_UNSYNCED;
    f->sync_slot = -1;
    f->sync_bound_us = 0u;
    f->sync_age_us = 0u;
    if (slot < 0) {
        return;
    }
    const rrh_sync_slot_t *s = &c->sync[slot];
    const uint64_t age = start_us - s->installed_us;
    uint64_t bound = s->bound_us;
    uint8_t state = RRH_SYNC_LOCKED;
    if (age > s->expiry_us) {
        const uint64_t over = age - s->expiry_us;
        if (over > RRH_HOLDOVER_MAX_US) {
            return; /* too old to say anything: UNSYNCED with null fields */
        }
        state = RRH_SYNC_HOLDOVER;
        bound += ((over * RRH_HOLDOVER_DRIFT_PPM) + 999999u) / 1000000u;
    }
    if (bound > RRH_BOUND_MAX_US) {
        return; /* the bound no longer fits the ACQ field: report UNSYNCED */
    }
    f->sync_state = state;
    f->sync_slot = (int8_t)slot;
    f->sync_bound_us = (uint32_t)bound;
    f->sync_age_us = age;
    c->sync[slot].refs++;
}

/* ---- one gate record -> one frame ----------------------------------------------------------- */
static void map_lane(rrh_frame_lane_t *o, const rrh_gate_lane_t *in, const rrh_gate_record_t *rec, uint8_t fe_fault,
                     uint32_t lane, uint8_t chain_enable)
{
    memset(o, 0, sizeof *o);
    o->alpha = in->alpha_counts;
    o->beta = in->beta_counts;
    o->ref = in->ref_counts;
    o->floor_reject = in->floor_reject_counts;
    o->ref_reject = in->ref_reject_counts;
    o->floor_live_ticks = in->floor_live_ticks;
    o->ref_live_ticks = in->ref_live_ticks;
    o->gate_flags = in->flags;

    const uint8_t floor = (uint8_t)(RRH_CH_ALPHA | RRH_CH_BETA);
    const bool floor_off = (((uint32_t)chain_enable >> lane) & 1u) == 0u;
    const bool ref_off = (((uint32_t)chain_enable >> (4u + lane)) & 1u) == 0u;

    /* live time: integer conversion of the hardware counters, nothing else */
    if ((in->floor_live_ticks == 0u) || (in->floor_live_ticks > rec->gate_ticks)) {
        o->null_mask |= floor;
        o->seg_flags |= RRH_SF_DEAD_TIME_UNKNOWN;
    } else {
        o->floor_live_us = (uint32_t)rrc_ticks_to_us(in->floor_live_ticks, rec->tick_hz);
        if ((o->floor_live_us == 0u) ||
            (((uint64_t)in->floor_live_ticks * 100u) < ((uint64_t)rec->gate_ticks * RRH_MIN_LIVE_PERCENT))) {
            o->null_mask |= floor;
            o->seg_flags |= RRH_SF_SATURATED;
        }
    }
    if ((in->ref_live_ticks == 0u) || (in->ref_live_ticks > rec->gate_ticks)) {
        o->null_mask |= RRH_CH_REF;
        o->seg_flags |= RRH_SF_DEAD_TIME_UNKNOWN;
    } else {
        o->ref_live_us = (uint32_t)rrc_ticks_to_us(in->ref_live_ticks, rec->tick_hz);
        if ((o->ref_live_us == 0u) ||
            (((uint64_t)in->ref_live_ticks * 100u) < ((uint64_t)rec->gate_ticks * RRH_MIN_LIVE_PERCENT))) {
            o->null_mask |= RRH_CH_REF;
            o->seg_flags |= RRH_SF_SATURATED;
        }
    }
    if ((in->flags & RRH_GF_FLOOR_SATURATED) != 0u) {
        o->null_mask |= floor;
        o->seg_flags |= RRH_SF_SATURATED;
    }
    if ((in->flags & RRH_GF_REF_SATURATED) != 0u) {
        o->null_mask |= RRH_CH_REF;
        o->seg_flags |= RRH_SF_SATURATED;
    }
    if ((in->flags & RRH_GF_BASELINE_SHIFT) != 0u) {
        o->null_mask |= (uint8_t)(floor | RRH_CH_REF);
        o->seg_flags |= RRH_SF_DISCRIMINATOR_FAULT;
    }
    if ((in->flags & RRH_GF_BIAS_OUT_OF_RANGE) != 0u) {
        o->null_mask |= (uint8_t)(floor | RRH_CH_REF);
        o->seg_flags |= (uint8_t)(RRH_SF_FLOOR_FAULT | RRH_SF_REFERENCE_FAULT);
    }
    if (((in->flags & RRH_GF_FLOOR_INVALID) != 0u) || floor_off || ((((uint32_t)fe_fault >> lane) & 1u) != 0u)) {
        o->null_mask |= floor;
        o->seg_flags |= RRH_SF_FLOOR_FAULT;
    }
    if (((in->flags & RRH_GF_REF_INVALID) != 0u) || ref_off || ((((uint32_t)fe_fault >> (4u + lane)) & 1u) != 0u)) {
        o->null_mask |= RRH_CH_REF;
        o->seg_flags |= RRH_SF_REFERENCE_FAULT;
    }
}

static void on_gate(rrh_core_t *c, const rrh_gate_record_t *rec)
{
    /* Sequence continuity of the source: a skipped record skips the same number of ACQ
     * sequence numbers, so the loss is visible to the host as a sequence gap. */
    if (rec->sequence != c->expect_src_seq) {
        c->health |= RRH_H_RECORD_LOST;
        if (rec->sequence > c->expect_src_seq) {
            c->next_seq += (uint64_t)(rec->sequence - c->expect_src_seq);
        }
        c->have_prev_tick = false;
    }
    c->expect_src_seq = rec->sequence + 1u;
    if (rec->source_fault) {
        c->health |= RRH_H_SOURCE;
    }

    /* Equal, contiguous gates: the length must be exactly the armed span and each gate must
     * start on the tick the previous one ended. */
    bool timing_ok = (rec->tick_hz != 0u) && (rec->tick_hz == c->epoch.tick_hz) && (rec->gate_ticks != 0u) &&
                     (rec->gate_start_tick >= c->epoch.tick);
    uint64_t span = 0u;
    if (timing_ok) {
        span = rrc_ticks_to_us(rec->gate_ticks, rec->tick_hz);
        timing_ok = (rrc_us_to_ticks(span, rec->tick_hz) == rec->gate_ticks) && (span == c->span_us) &&
                    (rec->heater_on_ticks <= rec->gate_ticks);
        if (c->have_prev_tick && (rec->gate_start_tick != c->prev_end_tick)) {
            timing_ok = false;
        }
    }
    if (!timing_ok) {
        c->health |= RRH_H_GATE_TIMING;
    }
    if ((rec->tick_hz == 0u) || (rec->tick_hz != c->epoch.tick_hz) || (rec->gate_start_tick < c->epoch.tick) ||
        (span < RRH_SPAN_MIN_US) || (span > RRH_SPAN_MAX_US)) {
        /* No defensible interval: no frame. The sequence number is consumed (gap). */
        c->next_seq++;
        c->have_prev_tick = false;
        return;
    }
    c->prev_end_tick = rec->gate_start_tick + rec->gate_ticks;
    c->have_prev_tick = true;

    rrh_frame_t *f = frame_alloc(c);
    memset(f, 0, sizeof *f);
    f->sequence = c->next_seq;
    c->next_seq++;
    f->start_us = c->epoch.us + rrc_ticks_to_us(rec->gate_start_tick - c->epoch.tick, rec->tick_hz);
    f->span_us = (uint32_t)span;
    sync_evaluate(c, f, f->start_us);

    /* Housekeeping as of this gate, then the heater decision for the following gates. */
    rrh_control_sample(c);
    rrh_control_on_gate(c, rec);
    for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
        map_lane(&f->lane[lane], &rec->lane[lane], rec, c->analog.frontend_fault, lane, c->setup.fe.chain_enable);
    }
    f->health = c->health;
    f->acq_flags = rrh_control_acq_flags(c);
    f->head_mc = rrh_control_head_mc(c);
    f->heater_on_us = (uint32_t)rrc_ticks_to_us(rec->heater_on_ticks, rec->tick_hz);
    f->heater_transition = rec->heater_transition_in_gate;
    if ((f->acq_flags & RRH_AF_HEATER_FAULT) != 0u) {
        f->heater = 2u;
        f->duty_pct = 0u; /* a faulted heater reports no applied duty (true on-time is in DIAG) */
    } else if (rec->heater_on_ticks > 0u) {
        const uint64_t pct = (((uint64_t)rec->heater_on_ticks * 100u) + (rec->gate_ticks / 2u)) / rec->gate_ticks;
        f->heater = 1u;
        f->duty_pct = (uint8_t)((pct == 0u) ? 1u : pct);
    } else {
        f->heater = 0u;
        f->duty_pct = 0u;
    }
    f->gate_start_tick = rec->gate_start_tick;
    f->gate_ticks = rec->gate_ticks;
    f->tick_hz = rec->tick_hz;
    f->bias_mv = c->analog.bias_mv;
    f->bias_ua = c->analog.bias_ua;
    f->bias_set_mv = c->bias_on ? c->bias_cmd_mv : 0u;
    for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
        f->sipm_mc[lane] = c->analog.sipm_mc[lane];
    }
    f->heater_plate_mc = c->analog.heater_plate_mc;
    f->board_mc = c->analog.board_mc;
    f->supply_mv = c->analog.supply_valid ? c->analog.supply_mv : 0u;
    f->bumper_zones = (uint8_t)(c->bumper_gate | c->analog.bumper_zones);
    c->bumper_gate = 0u;

    /* The next gate starts where this one ended: remember which sync record applies to it. */
    c->sync_pinned = (int8_t)sync_newest(c, f->start_us + f->span_us);
    c->last_gate_us = rrh_hal_now_us();
}

void rrh_acq_drain(rrh_core_t *c)
{
    rrh_gate_record_t rec;
    while ((c->armed || c->draining) && rrh_hal_acq_poll(&rec)) {
        on_gate(c, &rec);
    }
    if (c->draining && !rrh_hal_acq_running()) {
        c->draining = false;
        c->sync_pinned = -1;
    }
}

/* ---- serialisation -------------------------------------------------------------------------- */
static void put_reading(rrc_jw_t *w, const char *key, bool is_null, uint32_t counts, uint32_t live_us)
{
    rrc_jw_key(w, key);
    if (is_null) {
        rrc_jw_null(w);
        return;
    }
    rrc_jw_obj_begin(w);
    rrc_jw_ku64(w, "counts", counts);
    rrc_jw_ku64(w, "live_us", live_us);
    rrc_jw_obj_end(w);
}

static void put_flag_names(rrc_jw_t *w, uint32_t bits, const char *const *names, uint32_t n)
{
    rrc_jw_arr_begin(w);
    for (uint32_t i = 0u; i < n; i++) {
        if (((bits >> i) & 1u) != 0u) {
            rrc_jw_str(w, names[i]);
        }
    }
    rrc_jw_arr_end(w);
}

static const char *const k_seg_flags[5] = {"FLOOR_FAULT", "REFERENCE_FAULT", "SATURATED", "DEAD_TIME_UNKNOWN",
                                           "DISCRIMINATOR_FAULT"};
static const char *const k_acq_flags[6] = {"ACQ_FAULT", "HEAD_TEMP_OUT_OF_RANGE", "UNDERVOLTAGE", "BIAS_OUT_OF_RANGE",
                                           "HEATER_FAULT", "OVERTEMP"};
static const char *const k_gate_flags[6] = {"FLOOR_SATURATED", "REF_SATURATED", "BIAS_OUT_OF_RANGE", "BASELINE_SHIFT",
                                            "FLOOR_INVALID", "REF_INVALID"};
static const char *const k_health[13] = {"SOURCE", "GATE_TIMING", "RECORD_LOST", "GATE_TIMEOUT", "INJECTED",
                                         "HEATER_SENSOR", "HEATER_CUTOUT", "HEATER_OVERTEMP", "HEATER_STUCK",
                                         "BIAS_TRIP", "ENTROPY", "STORAGE", "WATCHDOG_RESET"};
static const char *const k_zones[3] = {"FRONT", "LEFT", "RIGHT"};

void rrh_write_health_names(uint16_t health, rrc_jw_t *w)
{
    put_flag_names(w, health, k_health, 13u);
}

void rrh_write_zone_names(uint8_t zones, rrc_jw_t *w)
{
    put_flag_names(w, zones, k_zones, 3u);
}

/* ACQ 2.0 body, member order as in examples/head_normal.json. */
void rrh_acq_write_frame(const rrh_core_t *c, const rrh_frame_t *f, rrc_jw_t *w)
{
    static const char *const sync_names[3] = {"UNSYNCED", "LOCKED", "HOLDOVER"};
    static const char *const heater_names[3] = {"OFF", "ON", "FAULT"};
    rrc_jw_obj_begin(w);
    rrc_jw_kstr(w, "type", "ACQ");
    rrc_jw_kstr(w, "icd", RRH_ACQ_FORMAT);
    rrc_jw_ku64(w, "sequence", f->sequence);
    rrc_jw_ku64(w, "start_us", f->start_us);
    rrc_jw_ku64(w, "span_us", f->span_us);
    rrc_jw_key(w, "sync");
    rrc_jw_obj_begin(w);
    rrc_jw_kstr(w, "state", sync_names[f->sync_state]);
    if ((f->sync_state == RRH_SYNC_UNSYNCED) || (f->sync_slot < 0)) {
        rrc_jw_knull(w, "sync_id");
        rrc_jw_knull(w, "bound_us");
        rrc_jw_knull(w, "age_us");
    } else {
        rrc_jw_kstr(w, "sync_id", c->sync[f->sync_slot].id);
        rrc_jw_ku64(w, "bound_us", f->sync_bound_us);
        rrc_jw_ku64(w, "age_us", f->sync_age_us);
    }
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "thermal");
    rrc_jw_obj_begin(w);
    if (f->head_mc == RRH_TEMP_INVALID) {
        rrc_jw_knull(w, "head_c");
    } else {
        /* one decimal, rounded half away from zero */
        const int32_t tenth = (f->head_mc >= 0) ? ((f->head_mc + 50) / 100) : -((-f->head_mc + 50) / 100);
        rrc_jw_kfixed(w, "head_c", tenth, 1u, false);
    }
    rrc_jw_kstr(w, "heater", heater_names[f->heater]);
    rrc_jw_ku64(w, "duty_pct", f->duty_pct);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "flags");
    put_flag_names(w, f->acq_flags, k_acq_flags, 6u);
    rrc_jw_key(w, "segments");
    rrc_jw_arr_begin(w);
    for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
        const rrh_frame_lane_t *l = &f->lane[lane];
        rrc_jw_obj_begin(w);
        rrc_jw_ku64(w, "id", lane);
        put_reading(w, "alpha", (l->null_mask & RRH_CH_ALPHA) != 0u, l->alpha, l->floor_live_us);
        put_reading(w, "beta_window", (l->null_mask & RRH_CH_BETA) != 0u, l->beta, l->floor_live_us);
        put_reading(w, "photon_ref", (l->null_mask & RRH_CH_REF) != 0u, l->ref, l->ref_live_us);
        rrc_jw_key(w, "flags");
        put_flag_names(w, l->seg_flags, k_seg_flags, 5u);
        rrc_jw_obj_end(w);
    }
    rrc_jw_arr_end(w);
    rrc_jw_obj_end(w);
}

static void put_temp(rrc_jw_t *w, int32_t mc)
{
    if (mc == RRH_TEMP_INVALID) {
        rrc_jw_null(w);
    } else {
        rrc_jw_fixed(w, mc, 3u, true);
    }
}

/* DIAG 1.0 body: the engineering data of the same gate (addendum 0.4 section 3). Raw counters
 * are reported even for channels that the ACQ frame nulled. */
void rrh_acq_write_diag(const rrh_core_t *c, const rrh_frame_t *f, rrc_jw_t *w)
{
    (void)c;
    rrc_jw_obj_begin(w);
    rrc_jw_kstr(w, "type", "DIAG");
    rrc_jw_kstr(w, "diag", "1.0");
    rrc_jw_ku64(w, "sequence", f->sequence);
    rrc_jw_ku64(w, "tick_hz", f->tick_hz);
    rrc_jw_ku64(w, "gate_start_tick", f->gate_start_tick);
    rrc_jw_ku64(w, "gate_ticks", f->gate_ticks);
    rrc_jw_key(w, "heater");
    rrc_jw_obj_begin(w);
    rrc_jw_ku64(w, "on_us", f->heater_on_us);
    rrc_jw_kbool(w, "transition", f->heater_transition);
    rrc_jw_key(w, "plate_c");
    put_temp(w, f->heater_plate_mc);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "bias");
    rrc_jw_obj_begin(w);
    rrc_jw_kfixed(w, "set_v", f->bias_set_mv, 3u, true);
    rrc_jw_kfixed(w, "v", f->bias_mv, 3u, true);
    rrc_jw_ku64(w, "ua", f->bias_ua);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "temps");
    rrc_jw_obj_begin(w);
    rrc_jw_key(w, "sipm_c");
    rrc_jw_arr_begin(w);
    for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
        put_temp(w, f->sipm_mc[lane]);
    }
    rrc_jw_arr_end(w);
    rrc_jw_key(w, "board_c");
    put_temp(w, f->board_mc);
    rrc_jw_obj_end(w);
    rrc_jw_kfixed(w, "supply_v", f->supply_mv, 3u, true);
    rrc_jw_key(w, "bumper_zones");
    rrh_write_zone_names(f->bumper_zones, w);
    rrc_jw_key(w, "health");
    rrh_write_health_names(f->health, w);
    rrc_jw_key(w, "lanes");
    rrc_jw_arr_begin(w);
    for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
        const rrh_frame_lane_t *l = &f->lane[lane];
        rrc_jw_obj_begin(w);
        rrc_jw_ku64(w, "id", lane);
        rrc_jw_ku64(w, "alpha_raw", l->alpha);
        rrc_jw_ku64(w, "beta_raw", l->beta);
        rrc_jw_ku64(w, "floor_reject", l->floor_reject);
        rrc_jw_ku64(w, "floor_live_ticks", l->floor_live_ticks);
        rrc_jw_ku64(w, "ref_raw", l->ref);
        rrc_jw_ku64(w, "ref_reject", l->ref_reject);
        rrc_jw_ku64(w, "ref_live_ticks", l->ref_live_ticks);
        rrc_jw_key(w, "flags");
        put_flag_names(w, l->gate_flags, k_gate_flags, 6u);
        rrc_jw_obj_end(w);
    }
    rrc_jw_arr_end(w);
    rrc_jw_obj_end(w);
}
