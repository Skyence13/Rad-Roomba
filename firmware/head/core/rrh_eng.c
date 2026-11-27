/* Additive ops of interface/head_icd_addendum_0.4.md. A 2.0 host that never sends them is not
 * affected; a head without them answers UNSUPPORTED. None of their replies carries identity
 * fields or counts outside the retained frames.
 *
 *   DIAG {seq}            bound only   engineering record of retained sequence seq
 *   STATUS {clear_bumper} any state    operating state, health, housekeeping, bumper zones
 *   FAULT_CLEAR {codes}   any state    clear latched health bits whose cause is gone
 *   ENG_FAULT {}          any state    latch a deliberate fault (test of the fault path)
 *   ENG_SETUP_GET {}      any state    current setup values
 *   ENG_SETUP_SET {...}   not armed    change the setup; INVALIDATES THE BINDING first
 *   ENG_WAVE_ARM {...}    not armed    arm a monitor waveform capture
 *   ENG_WAVE_READ {...}   any state    fetch captured samples in base64 chunks
 */
#include <string.h>

#include "rrh_internal.h"

static bool op_is(const rrc_json_t *d, const rrc_req_t *req, const char *name)
{
    return rrc_json_str_eq(d, req->op, name);
}

static void put_temp_key(rrc_jw_t *w, const char *key, int32_t mc)
{
    rrc_jw_key(w, key);
    if (mc == RRH_TEMP_INVALID) {
        rrc_jw_null(w);
    } else {
        rrc_jw_fixed(w, mc, 3u, true);
    }
}

static void put_range_status(rrh_core_t *c, rrc_jw_t *w, uint32_t id, const char *status)
{
    rrc_rsp_begin(w, RRH_PROTO_VERSION, id, status);
    rrc_jw_obj_begin(w);
    rrc_jw_ku64(w, "oldest_seq", rrh_acq_oldest(c)->sequence);
    rrc_jw_ku64(w, "newest_seq", rrh_acq_newest(c)->sequence);
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
}

static void op_diag(rrh_core_t *c, const rrc_json_t *d, const rrc_req_t *req, rrc_jw_t *w)
{
    int64_t seq = 0;
    if (c->link != RRH_LINK_BOUND) {
        rrh_reply_status(w, req->id, "UNBOUND", NULL);
        return;
    }
    if (!rrc_json_to_i64(d, rrc_json_get(d, req->args, "seq"), &seq) || (seq < 0) || (seq > 9007199254740991LL)) {
        rrh_reply_status(w, req->id, "BAD_ARG", "seq");
        return;
    }
    const rrh_frame_t *newest = rrh_acq_newest(c);
    if ((newest == NULL) || ((uint64_t)seq > newest->sequence)) {
        rrh_reply_status(w, req->id, "EMPTY", NULL);
        return;
    }
    const rrh_frame_t *f = rrh_acq_find(c, (uint64_t)seq);
    if (f == NULL) {
        put_range_status(c, w, req->id, "GAP"); /* expired, or the gate itself was lost */
        return;
    }
    rrc_rsp_begin(w, RRH_PROTO_VERSION, req->id, "OK");
    rrh_acq_write_diag(c, f, w);
    rrc_rsp_end(w);
}

static void op_status(rrh_core_t *c, const rrc_json_t *d, const rrc_req_t *req, rrc_jw_t *w)
{
    static const char *const link_names[3] = {"UNBOUND", "HANDSHAKE", "BOUND"};
    static const char *const reset_names[6] = {"POWER_ON", "PIN", "WATCHDOG", "SOFTWARE", "BROWNOUT", "OTHER"};
    static const char *const acq_names[6] = {"ACQ_FAULT", "HEAD_TEMP_OUT_OF_RANGE", "UNDERVOLTAGE", "BIAS_OUT_OF_RANGE",
                                             "HEATER_FAULT", "OVERTEMP"};
    bool clear_bumper = false;
    const int cb = rrc_json_get(d, req->args, "clear_bumper");
    if ((cb >= 0) && !rrc_json_to_bool(d, cb, &clear_bumper)) {
        rrh_reply_status(w, req->id, "BAD_ARG", "clear_bumper");
        return;
    }
    const rrh_analog_t *a = &c->analog;
    const rrh_frame_t *oldest = rrh_acq_oldest(c);
    const uint8_t flags = rrh_control_acq_flags(c);
    rrc_rsp_begin(w, RRH_PROTO_VERSION, req->id, "OK");
    rrc_jw_obj_begin(w);
    rrc_jw_kstr(w, "link", link_names[c->link]);
    rrc_jw_kbool(w, "armed", c->armed);
    rrc_jw_kbool(w, "draining", c->draining);
    rrc_jw_ku64(w, "uptime_us", rrh_hal_now_us());
    rrc_jw_kstr(w, "reset_cause", reset_names[c->reset_cause]);
    rrc_jw_ku64(w, "span_us", c->span_us);
    rrc_jw_ku64(w, "next_seq", c->next_seq);
    if (oldest != NULL) {
        rrc_jw_ku64(w, "oldest_seq", oldest->sequence);
        rrc_jw_ku64(w, "newest_seq", rrh_acq_newest(c)->sequence);
    } else {
        rrc_jw_knull(w, "oldest_seq");
        rrc_jw_knull(w, "newest_seq");
    }
    rrc_jw_ku64(w, "buffer_frames", RRH_FRAME_BUFFER);
    rrc_jw_key(w, "health");
    rrh_write_health_names(c->health, w);
    rrc_jw_key(w, "flags");
    rrc_jw_arr_begin(w);
    for (uint32_t i = 0u; i < 6u; i++) {
        if (((flags >> i) & 1u) != 0u) {
            rrc_jw_str(w, acq_names[i]);
        }
    }
    rrc_jw_arr_end(w);
    rrc_jw_key(w, "heater");
    rrc_jw_obj_begin(w);
    rrc_jw_kbool(w, "enabled", c->setup.heater_enable);
    rrc_jw_kbool(w, "on", c->heater_on);
    put_temp_key(w, "plate_c", a->heater_plate_mc);
    rrc_jw_kbool(w, "cutout_ok", a->heater_cutout_ok);
    if (a->heater_ma_valid) {
        rrc_jw_ku64(w, "ma", a->heater_ma);
    } else {
        rrc_jw_knull(w, "ma");
    }
    rrc_jw_ku64(w, "oc_ma", c->setup.heater_oc_ma);
    rrc_jw_obj_end(w);
    /* Frame potential (stage 3): V(FRAME) in mV from MON_ADC with the lane muxes off; null = not measured */
    rrc_jw_key(w, "frame");
    rrc_jw_obj_begin(w);
    if (c->frame_mv == INT32_MIN) {
        rrc_jw_knull(w, "mv");
    } else {
        rrc_jw_ki64(w, "mv", c->frame_mv);
    }
    rrc_jw_kbool(w, "fault", (c->health & RRH_H_FRAME_FAULT) != 0u);
    rrc_jw_obj_end(w);
    rrc_jw_kstr(w, "device", (c->setup.device == 0u) ? "NONE" : rrh_devices[c->setup.device - 1u].name);
    rrc_jw_kbool(w, "thresholds_confirmed", c->setup.thr_confirmed);
    rrc_jw_ku64(w, "alpha_tot_ns", c->setup.fe.alpha_min_tot_ns);
    rrc_jw_key(w, "bias");
    rrc_jw_obj_begin(w);
    rrc_jw_kbool(w, "on", c->bias_on);
    rrc_jw_kfixed(w, "set_v", c->bias_cmd_mv, 3u, true);
    rrc_jw_kfixed(w, "out_v", c->bias_out_mv, 3u, true);
    rrc_jw_ku64(w, "vmon_ratio_e4", c->setup.vmon_ratio_e4);
    rrc_jw_kstr(w, "vmon", c->setup.vmon_calibrated ? "CALIBRATED" : "UNCALIBRATED");
    if (a->bias_valid) {
        rrc_jw_kfixed(w, "v", a->bias_mv, 3u, true);
        rrc_jw_ku64(w, "ua", a->bias_ua);
    } else {
        rrc_jw_knull(w, "v");
        rrc_jw_knull(w, "ua");
    }
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "temps");
    rrc_jw_obj_begin(w);
    put_temp_key(w, "head_c", rrh_control_head_mc(c));
    rrc_jw_key(w, "sipm_c");
    rrc_jw_arr_begin(w);
    for (uint32_t i = 0u; i < RRH_LANES; i++) {
        if (a->sipm_mc[i] == RRH_TEMP_INVALID) {
            rrc_jw_null(w);
        } else {
            rrc_jw_fixed(w, a->sipm_mc[i], 3u, true);
        }
    }
    rrc_jw_arr_end(w);
    put_temp_key(w, "board_c", a->board_mc);
    rrc_jw_obj_end(w);
    if (a->supply_valid) {
        rrc_jw_kfixed(w, "supply_v", a->supply_mv, 3u, true);
    } else {
        rrc_jw_knull(w, "supply_v");
    }
    /* Rail zones: rev A has no zone identification (IB-21 closed for rev A). "available": false
     * means NOT AVAILABLE, which is different from "no zone actuated" (empty arrays). */
    rrc_jw_key(w, "bumper");
    rrc_jw_obj_begin(w);
    rrc_jw_kbool(w, "available", a->zones_available);
    if (a->zones_available) {
        rrc_jw_key(w, "now");
        rrh_write_zone_names(a->bumper_zones, w);
        rrc_jw_key(w, "latched");
        rrh_write_zone_names(c->bumper_latched, w);
    } else {
        rrc_jw_knull(w, "now");
        rrc_jw_knull(w, "latched");
    }
    rrc_jw_obj_end(w);
    /* Optional I2C expander (TCA9534 at 0x20): hardware permit, inhibit, lid and eFuse read-back.
     * Without it every field but "present" is null ("unknown"). */
    rrc_jw_key(w, "expander");
    rrc_jw_obj_begin(w);
    rrc_jw_kbool(w, "present", c->exp.present);
    if (c->exp.present) {
        rrc_jw_kbool(w, "hv_permit", (c->exp.inputs & RRH_EXP_HV_PERMIT) != 0u);
        rrc_jw_kbool(w, "hv_inhibit", (c->exp.inputs & RRH_EXP_HV_INH_N) == 0u);
        rrc_jw_kbool(w, "lid_open", (c->exp.inputs & RRH_EXP_LID_G) != 0u);
        rrc_jw_kbool(w, "efuse_fault", (c->exp.inputs & RRH_EXP_EF_FLT_N) == 0u);
        rrc_jw_ku64(w, "hw_rev", (uint64_t)(((c->exp.inputs & RRH_EXP_HWREV0) != 0u) ? 1u : 0u) |
                                      (uint64_t)(((c->exp.inputs & RRH_EXP_HWREV1) != 0u) ? 2u : 0u));
    } else {
        rrc_jw_knull(w, "hv_permit");
        rrc_jw_knull(w, "hv_inhibit");
        rrc_jw_knull(w, "lid_open");
        rrc_jw_knull(w, "efuse_fault");
        rrc_jw_knull(w, "hw_rev");
    }
    rrc_jw_obj_end(w);
    /* Per-chain anode current (nA; null = not measured) and the chains out of window. */
    rrc_jw_key(w, "imon");
    rrc_jw_obj_begin(w);
    rrc_jw_kstr(w, "scan", c->imon_paused ? "PAUSED_ARMED" : "RUNNING");
    rrc_jw_key(w, "na");
    rrc_jw_arr_begin(w);
    for (uint32_t ch = 0u; ch < RRH_CHAINS; ch++) {
        if (c->imon_na[ch] == RRH_IMON_NA_INVALID) {
            rrc_jw_null(w);
        } else {
            rrc_jw_u64(w, c->imon_na[ch]);
        }
    }
    rrc_jw_arr_end(w);
    rrc_jw_key(w, "fault");
    rrc_jw_arr_begin(w);
    static const char *const chain_names[RRH_CHAINS] = {"F0", "F1", "F2", "F3", "R0", "R1", "R2", "R3"};
    for (uint32_t ch = 0u; ch < RRH_CHAINS; ch++) {
        if ((((uint32_t)c->imon_fault >> ch) & 1u) != 0u) {
            rrc_jw_str(w, chain_names[ch]);
        }
    }
    rrc_jw_arr_end(w);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "link_stats");
    rrc_jw_obj_begin(w);
    rrc_jw_ku64(w, "requests", c->n_requests);
    rrc_jw_ku64(w, "retries", c->n_retries);
    rrc_jw_ku64(w, "discarded", c->n_discarded);
    rrc_jw_obj_end(w);
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
    if (clear_bumper) {
        c->bumper_latched = a->zones_available ? a->bumper_zones : 0u;
    }
}

static uint16_t health_bit_by_name(const rrc_json_t *d, int tok)
{
    static const char *const names[RRH_H_COUNT] = {"SOURCE", "GATE_TIMING", "RECORD_LOST", "GATE_TIMEOUT", "INJECTED",
                                                   "HEATER_SENSOR", "HEATER_CUTOUT", "HEATER_OVERTEMP", "HEATER_STUCK",
                                                   "BIAS_TRIP", "ENTROPY", "STORAGE", "WATCHDOG_RESET", "BIAS_PERMIT", "FRAME_FAULT",
                                                   "HEATER_OVERCURRENT"};
    for (uint32_t i = 0u; i < RRH_H_COUNT; i++) {
        if (rrc_json_str_eq(d, tok, names[i])) {
            return (uint16_t)(1u << i);
        }
    }
    return 0u;
}

static void op_fault_clear(rrh_core_t *c, const rrc_json_t *d, const rrc_req_t *req, rrc_jw_t *w)
{
    uint16_t want = RRH_H_ALL;
    const int codes = rrc_json_get(d, req->args, "codes");
    if (codes >= 0) {
        if (rrc_json_type(d, codes) != RRC_JT_ARRAY) {
            rrh_reply_status(w, req->id, "BAD_ARG", "codes");
            return;
        }
        want = 0u;
        for (uint16_t i = 0u; i < rrc_json_size(d, codes); i++) {
            const uint16_t bit = health_bit_by_name(d, rrc_json_at(d, codes, i));
            if (bit == 0u) {
                rrh_reply_status(w, req->id, "BAD_ARG", "codes");
                return;
            }
            want |= bit;
        }
    }
    /* Refresh the inputs so "cause gone" is judged on current data, then clear only those. */
    rrh_control_refresh_inputs(c);
    const uint16_t cleared = (uint16_t)(c->health & want & rrh_control_clearable(c));
    c->health = (uint16_t)(c->health & (uint16_t)~cleared);
    rrc_rsp_begin(w, RRH_PROTO_VERSION, req->id, "OK");
    rrc_jw_obj_begin(w);
    rrc_jw_key(w, "cleared");
    rrh_write_health_names(cleared, w);
    rrc_jw_key(w, "health");
    rrh_write_health_names(c->health, w);
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
}

static void op_eng_fault(rrh_core_t *c, const rrc_req_t *req, rrc_jw_t *w)
{
    c->health |= RRH_H_INJECTED;
    rrc_rsp_begin(w, RRH_PROTO_VERSION, req->id, "OK");
    rrc_jw_obj_begin(w);
    rrc_jw_key(w, "health");
    rrh_write_health_names(c->health, w);
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
}

static void op_setup_get(rrh_core_t *c, const rrc_req_t *req, rrc_jw_t *w)
{
    rrc_rsp_begin(w, RRH_PROTO_VERSION, req->id, "OK");
    rrc_jw_obj_begin(w);
    rrc_jw_key(w, "setup");
    rrh_setup_to_json(&c->setup, w);
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
}

static void op_setup_set(rrh_core_t *c, const rrc_json_t *d, const rrc_req_t *req, rrc_jw_t *w)
{
    uint8_t blob[128];
    uint8_t before[128];
    rrh_setup_t next = c->setup;
    bool persist = false;
    if ((c->ident.setup_id_override != NULL) || (c->ident.descriptor_override != NULL)) {
        rrh_reply_status(w, req->id, "UNSUPPORTED", "fixed_descriptor");
        return;
    }
    if (c->armed || c->draining) {
        rrh_reply_status(w, req->id, "BUSY", "armed"); /* change settings only after disarming */
        return;
    }
    if (!rrh_setup_from_json(&next, d, req->args)) {
        rrh_reply_status(w, req->id, "BAD_ARG", "setup");
        return;
    }
    (void)rrc_json_to_bool(d, rrc_json_get(d, req->args, "persist"), &persist);
    /* Compare the canonical images (the same bytes the setup hash covers), not the structs. */
    const size_t n_before = rrh_setup_pack_image(&c->setup, before, sizeof before);
    const size_t n_after = rrh_setup_pack_image(&next, blob, sizeof blob);
    const bool changed = (n_before != n_after) || (memcmp(before, blob, n_after) != 0);
    if (changed) {
        /* ORDER MATTERS: the binding is invalidated BEFORE the new settings reach the hardware,
         * so no sample taken with them can ever be attributed to the old setup_id. */
        rrh_core_invalidate_binding(c);
        c->setup = next;
        (void)rrh_descriptor_rebuild(c);
        if (!rrh_hal_frontend_apply(&c->setup.fe)) {
            c->health |= RRH_H_SOURCE;
        }
        c->bias_settle = 0u;
    } else {
        c->setup = next; /* the BIAS_VMON calibration is not part of setup_id: no new binding needed */
    }
    if (persist) {
        const size_t n = rrh_setup_pack(&c->setup, blob, sizeof blob);
        if ((n == 0u) || !rrh_hal_nv_save(RRH_NV_SLOT_SETUP, blob, n)) {
            c->health |= RRH_H_STORAGE;
            rrh_reply_status(w, req->id, "FAULT", "storage");
            return;
        }
    }
    rrc_rsp_begin(w, RRH_PROTO_VERSION, req->id, "OK");
    rrc_jw_obj_begin(w);
    rrc_jw_kbool(w, "changed", changed);
    rrc_jw_kbool(w, "bound", c->link == RRH_LINK_BOUND);
    rrc_jw_kbool(w, "persisted", persist);
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
}

static void op_wave_arm(rrh_core_t *c, const rrc_json_t *d, const rrc_req_t *req, rrc_jw_t *w)
{
    rrh_wave_cfg_t cfg;
    int64_t ch = 0;
    int64_t samples = 0;
    int64_t pre = 0;
    int64_t trig = 1;
    bool slow = false;
    if (c->armed || c->draining) {
        rrh_reply_status(w, req->id, "BUSY", "armed"); /* the monitor mux is not switched during counting */
        return;
    }
    const int ts = rrc_json_get(d, req->args, "slow_path");
    const int tt = rrc_json_get(d, req->args, "trigger");
    if (!rrc_json_to_i64(d, rrc_json_get(d, req->args, "channel"), &ch) || (ch < 0) || (ch > 7) ||
        !rrc_json_to_i64(d, rrc_json_get(d, req->args, "samples"), &samples) || (samples < 16) ||
        (samples > (int64_t)RRH_WAVE_MAX_SAMPLES) ||
        !rrc_json_to_i64(d, rrc_json_get(d, req->args, "pretrigger"), &pre) || (pre < 0) || (pre >= samples) ||
        ((ts >= 0) && !rrc_json_to_bool(d, ts, &slow)) ||
        ((tt >= 0) && (!rrc_json_to_i64(d, tt, &trig) || (trig < 0) || (trig > 1)))) {
        rrh_reply_status(w, req->id, "BAD_ARG", "wave");
        return;
    }
    cfg.channel = (uint8_t)ch;
    cfg.slow_path = slow;
    cfg.samples = (uint16_t)samples;
    cfg.pretrigger = (uint16_t)pre;
    cfg.trigger = (uint8_t)trig;
    if (!rrh_hal_wave_arm(&cfg)) {
        rrh_reply_status(w, req->id, "FAULT", "capture");
        return;
    }
    rrh_reply_status(w, req->id, "OK", NULL);
}

static void op_wave_read(const rrc_json_t *d, const rrc_req_t *req, rrc_jw_t *w)
{
    static uint8_t raw[RRH_WAVE_CHUNK_MAX];
    static char b64[RRC_BASE64_ENC_LEN(RRH_WAVE_CHUNK_MAX)];
    uint16_t total = 0u;
    uint32_t period_ns = 0u;
    uint16_t trig_index = 0u;
    int64_t offset = 0;
    int64_t count = 0;
    const rrh_wave_state_t st = rrh_hal_wave_status(&total, &period_ns, &trig_index);
    if (st == RRH_WAVE_ARMED) {
        rrh_reply_status(w, req->id, "EMPTY", NULL); /* waiting for the trigger */
        return;
    }
    if (st == RRH_WAVE_FAILED) {
        rrh_reply_status(w, req->id, "FAULT", "capture");
        return;
    }
    if ((st != RRH_WAVE_DONE) || (total == 0u) ||
        !rrc_json_to_i64(d, rrc_json_get(d, req->args, "offset"), &offset) || (offset < 0) || (offset >= (int64_t)total) ||
        !rrc_json_to_i64(d, rrc_json_get(d, req->args, "count"), &count) || (count < 1) ||
        (count > (int64_t)(RRH_WAVE_CHUNK_MAX / 2u))) {
        rrh_reply_status(w, req->id, "BAD_ARG", "wave");
        return;
    }
    if (count > ((int64_t)total - offset)) {
        count = (int64_t)total - offset;
    }
    if (!rrh_hal_wave_read((uint16_t)offset, (uint16_t)count, raw)) {
        rrh_reply_status(w, req->id, "FAULT", "capture");
        return;
    }
    const size_t bl = rrc_base64_encode(raw, (size_t)count * 2u, b64, sizeof b64);
    rrc_rsp_begin(w, RRH_PROTO_VERSION, req->id, "OK");
    rrc_jw_obj_begin(w);
    rrc_jw_ku64(w, "samples", total);
    rrc_jw_ku64(w, "period_ns", period_ns);
    rrc_jw_ku64(w, "trigger_index", trig_index);
    rrc_jw_ku64(w, "offset", (uint64_t)offset);
    rrc_jw_ku64(w, "count", (uint64_t)count);
    rrc_jw_kstr(w, "format", "u16le");
    rrc_jw_key(w, "bytes_b64");
    rrc_jw_strn(w, b64, bl);
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
}

bool rrh_eng_dispatch(rrh_core_t *c, const rrc_json_t *d, const rrc_req_t *req, rrc_jw_t *w)
{
    if (op_is(d, req, "DIAG")) {
        op_diag(c, d, req, w);
    } else if (op_is(d, req, "STATUS")) {
        op_status(c, d, req, w);
    } else if (op_is(d, req, "FAULT_CLEAR")) {
        op_fault_clear(c, d, req, w);
    } else if (op_is(d, req, "ENG_FAULT")) {
        op_eng_fault(c, req, w);
    } else if (op_is(d, req, "ENG_SETUP_GET")) {
        op_setup_get(c, req, w);
    } else if (op_is(d, req, "ENG_SETUP_SET")) {
        op_setup_set(c, d, req, w);
    } else if (op_is(d, req, "ENG_WAVE_ARM")) {
        op_wave_arm(c, d, req, w);
    } else if (op_is(d, req, "ENG_WAVE_READ")) {
        op_wave_read(d, req, w);
    } else {
        return false;
    }
    return true;
}
