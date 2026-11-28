/* Head protocol 2.0 state machine (interface/head_icd.md sections 4-6).
 *
 * Binding rules in one place:
 *   UNBOUND    after rrh_core_init() (every MCU boot -> fresh boot_id) and after
 *              rrh_core_invalidate_binding() (setup change). Only HELLO is useful here:
 *              TIME/SYNC/ARM/READ/DISARM/DIAG answer UNBOUND and carry no counts.
 *   HANDSHAKE  entered by HELLO from ANY state. A fresh HELLO always aborts acquisition,
 *              switches the heater off and discards frames, sync records and the reply cache.
 *              GET_DESCRIPTOR and BIND are accepted only here and only with the current boot_id.
 *   BOUND      entered by BIND when boot_id, setup_id and descriptor_sha256 all equal the
 *              current values. Left only by HELLO, a setup change or a reset.
 * Sequence numbers start at 0 at HELLO and keep counting across DISARM/ARM.
 */
#include <string.h>

#include "rrh_internal.h"

static const rrc_json_limits_t k_limits = {RRH_JSON_DEPTH, RRH_JSON_STRING};

/* ---- small helpers ---------------------------------------------------------------------- */
void rrh_reply_status(rrc_jw_t *w, uint32_t id, const char *status, const char *reason)
{
    rrc_rsp_begin(w, RRH_PROTO_VERSION, id, status);
    rrc_jw_obj_begin(w);
    if (reason != NULL) {
        rrc_jw_kstr(w, "reason", reason);
    }
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
}

static void reply_begin_ok(rrc_jw_t *w, uint32_t id)
{
    rrc_rsp_begin(w, RRH_PROTO_VERSION, id, "OK");
}

static bool arg_i64(const rrc_json_t *d, int args, const char *key, int64_t lo, int64_t hi, int64_t *out)
{
    return rrc_json_to_i64(d, rrc_json_get(d, args, key), out) && (*out >= lo) && (*out <= hi);
}

static void stop_acquisition_now(rrh_core_t *c)
{
    rrh_hal_acq_abort();
    c->armed = false;
    c->draining = false;
    rrh_control_heater_off(c);
}

void rrh_core_invalidate_binding(rrh_core_t *c)
{
    stop_acquisition_now(c);
    rrh_acq_reset(c);
    c->link = RRH_LINK_UNBOUND;
}

/* ---- handshake ops -------------------------------------------------------------------------- */
static void op_hello(rrh_core_t *c, const rrc_req_t *req, rrc_jw_t *w)
{
    /* Fresh handshake: nothing of a previous attachment survives. */
    stop_acquisition_now(c);
    rrh_acq_reset(c);
    c->bumper_latched = 0u;
    /* A new attachment is a new acquisition epoch: faults of the discarded stream are history (counted in STATUS gates_lost / fault_events) */
    c->health = (uint16_t)(c->health & (uint16_t)~(RRH_H_RECORD_LOST | RRH_H_GATE_TIMING | RRH_H_GATE_TIMEOUT));
    c->acq_event_pending = false;
    c->link = RRH_LINK_HANDSHAKE;

    reply_begin_ok(w, req->id);
    rrc_jw_obj_begin(w);
    rrc_jw_kstr(w, "boot_id", c->boot_id);
    rrc_jw_kstr(w, "head_id", c->ident.serial);
    rrc_jw_kstr(w, "head_type", RRH_HEAD_TYPE);
    rrc_jw_kstr(w, "firmware", rrh_firmware_id(c));
    rrc_jw_key(w, "supported_discovery");
    rrc_jw_arr_begin(w);
    rrc_jw_str(w, RRH_PROTO_VERSION);
    rrc_jw_arr_end(w);
    rrc_jw_kstr(w, "acq_format", RRH_ACQ_FORMAT);
    rrc_jw_kstr(w, "descriptor_id", c->ident.descriptor_id);
    rrc_jw_kstr(w, "descriptor_sha256", c->descriptor_sha256);
    rrc_jw_ku64(w, "descriptor_bytes", c->descriptor_len);
    rrc_jw_kstr(w, "setup_id", c->setup_id);
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
}

/* Common gate of GET_DESCRIPTOR and BIND. Returns true if the op may proceed. */
static bool handshake_gate(rrh_core_t *c, const rrc_json_t *d, const rrc_req_t *req, rrc_jw_t *w, bool allow_bound)
{
    const int boot = rrc_json_get(d, req->args, "boot_id");
    if (rrc_json_type(d, boot) != RRC_JT_STRING) {
        rrh_reply_status(w, req->id, "BAD_ARG", "boot_id");
        return false;
    }
    if (!rrc_json_str_eq(d, boot, c->boot_id)) {
        rrh_reply_status(w, req->id, "WRONG_BOOT", NULL); /* stale handshake: other boot or other head */
        return false;
    }
    if (c->link == RRH_LINK_UNBOUND) {
        rrh_reply_status(w, req->id, "UNBOUND", "hello_required");
        return false;
    }
    if ((c->link == RRH_LINK_BOUND) && !allow_bound) {
        rrh_reply_status(w, req->id, "BUSY", "handshake_only");
        return false;
    }
    return true;
}

static void op_get_descriptor(rrh_core_t *c, const rrc_json_t *d, const rrc_req_t *req, rrc_jw_t *w)
{
    static char b64[RRC_BASE64_ENC_LEN(RRH_DESCRIPTOR_CHUNK_MAX)];
    if (!handshake_gate(c, d, req, w, false)) {
        return;
    }
    if (!rrc_json_str_eq(d, rrc_json_get(d, req->args, "descriptor_id"), c->ident.descriptor_id)) {
        rrh_reply_status(w, req->id, "BAD_ARG", "descriptor_id");
        return;
    }
    int64_t offset = 0;
    int64_t count = 0;
    if ((c->descriptor_len == 0u) || !arg_i64(d, req->args, "offset", 0, (int64_t)c->descriptor_len - 1, &offset)) {
        rrh_reply_status(w, req->id, "BAD_ARG", "offset");
        return;
    }
    if (!arg_i64(d, req->args, "count", 1, (int64_t)RRH_DESCRIPTOR_CHUNK_MAX, &count)) {
        rrh_reply_status(w, req->id, "BAD_ARG", "count");
        return;
    }
    size_t n = c->descriptor_len - (size_t)offset;
    if (n > (size_t)count) {
        n = (size_t)count;
    }
    const size_t bl = rrc_base64_encode(&c->descriptor[offset], n, b64, sizeof b64);
    reply_begin_ok(w, req->id);
    rrc_jw_obj_begin(w);
    rrc_jw_kstr(w, "boot_id", c->boot_id);
    rrc_jw_kstr(w, "descriptor_id", c->ident.descriptor_id);
    rrc_jw_ku64(w, "offset", (uint64_t)offset);
    rrc_jw_key(w, "bytes_b64");
    rrc_jw_strn(w, b64, bl);
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
}

static void op_bind(rrh_core_t *c, const rrc_json_t *d, const rrc_req_t *req, rrc_jw_t *w)
{
    if (!handshake_gate(c, d, req, w, true)) {
        return;
    }
    if (!rrc_json_str_eq(d, rrc_json_get(d, req->args, "setup_id"), c->setup_id)) {
        rrh_reply_status(w, req->id, "BAD_ARG", "setup_id");
        return;
    }
    if (!rrc_json_str_eq(d, rrc_json_get(d, req->args, "descriptor_sha256"), c->descriptor_sha256)) {
        rrh_reply_status(w, req->id, "BAD_ARG", "descriptor_sha256");
        return;
    }
    /* All three identifiers are current. A repeated BIND on a bound link changes nothing. */
    c->link = RRH_LINK_BOUND;
    reply_begin_ok(w, req->id);
    rrc_jw_obj_begin(w);
    rrc_jw_kbool(w, "bound", true);
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
}

/* ---- bound ops -------------------------------------------------------------------------------- */
static void op_time(const rrc_req_t *req, rrc_jw_t *w, uint64_t rx_us, uint64_t *tx_at_us)
{
    const uint64_t tx_us = rrh_hal_reply_tx_time_us(rx_us);
    *tx_at_us = tx_us;
    reply_begin_ok(w, req->id);
    rrc_jw_obj_begin(w);
    rrc_jw_ku64(w, "rx_us", rx_us);
    rrc_jw_ku64(w, "tx_us", tx_us);
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
}

static bool sync_id_ok(const char *s, size_t n)
{
    /* ACQ schema: ^[A-Za-z0-9][A-Za-z0-9_.:-]*$ , 1..96 characters */
    if ((n == 0u) || (n > RRH_SYNC_ID_MAX)) {
        return false;
    }
    for (size_t i = 0u; i < n; i++) {
        const char ch = s[i];
        const bool alnum = ((ch >= 'A') && (ch <= 'Z')) || ((ch >= 'a') && (ch <= 'z')) || ((ch >= '0') && (ch <= '9'));
        const bool punct = (ch == '_') || (ch == '.') || (ch == ':') || (ch == '-');
        if (!alnum && !((i > 0u) && punct)) {
            return false;
        }
    }
    return true;
}

static void op_sync(rrh_core_t *c, const rrc_json_t *d, const rrc_req_t *req, rrc_jw_t *w, uint64_t rx_us)
{
    char id[RRH_SYNC_ID_MAX + 2u];
    int64_t bound = 0;
    int64_t expiry = 0;
    const int n = rrc_json_str_copy(d, rrc_json_get(d, req->args, "sync_id"), id, sizeof id);
    if ((n < 0) || !sync_id_ok(id, (size_t)n)) {
        rrh_reply_status(w, req->id, "BAD_ARG", "sync_id");
        return;
    }
    if (!arg_i64(d, req->args, "bound_us", 0, (int64_t)RRH_BOUND_MAX_US, &bound)) {
        rrh_reply_status(w, req->id, "BAD_ARG", "bound_us");
        return;
    }
    if (!arg_i64(d, req->args, "expiry_us", 1, (int64_t)RRH_EXPIRY_MAX_US, &expiry)) {
        rrh_reply_status(w, req->id, "BAD_ARG", "expiry_us");
        return;
    }
    /* The record takes effect at the receipt time of this request and applies to every gate
     * that starts at or after it. */
    if (!rrh_sync_install(c, id, (uint32_t)bound, (uint64_t)expiry, rx_us)) {
        rrh_reply_status(w, req->id, "BUSY", "sync_table_full");
        return;
    }
    rrh_reply_status(w, req->id, "OK", NULL);
}

static void op_arm(rrh_core_t *c, const rrc_json_t *d, const rrc_req_t *req, rrc_jw_t *w)
{
    int64_t span = 0;
    if (!arg_i64(d, req->args, "span_us", (int64_t)c->ident.gate_min_us, (int64_t)c->ident.gate_max_us, &span)) {
        rrh_reply_status(w, req->id, "BAD_ARG", "span_us");
        return;
    }
    if (c->armed) {
        if ((uint32_t)span != c->span_us) {
            rrh_reply_status(w, req->id, "BUSY", "armed_with_other_span"); /* change settings only after DISARM */
            return;
        }
        /* matching repeat: acquisition is left untouched */
    } else if (c->draining) {
        rrh_reply_status(w, req->id, "BUSY", "final_gate_pending");
        return;
    } else {
        rrh_epoch_t epoch;
        /* Never count with a device type that is not set or thresholds that are only placeholders (review O6). */
        if (!c->ident.allow_placeholder_thresholds && ((c->setup.device == RRH_DEVICE_NONE) || !c->setup.thr_confirmed)) {
            rrh_reply_status(w, req->id, "FAULT", (c->setup.device == RRH_DEVICE_NONE) ? "device_type_unset" : "placeholder_thresholds");
            return;
        }
        if (!rrh_hal_acq_start((uint32_t)span, &epoch) || (epoch.tick_hz == 0u)) {
            c->health |= RRH_H_SOURCE;
            rrh_reply_status(w, req->id, "FAULT", "acquisition_source");
            return;
        }
        c->epoch = epoch;
        c->armed = true;
        c->span_us = (uint32_t)span;
        c->first_seq = c->next_seq;
        c->expect_src_seq = 0u;
        c->have_prev_tick = false;
        c->last_gate_us = rrh_hal_now_us();
        c->heater_dwell = RRH_HEATER_MIN_DWELL_GATES;
        c->heater_history = 0u;
        rrh_sync_pin_newest(c);
    }
    reply_begin_ok(w, req->id);
    rrc_jw_obj_begin(w);
    rrc_jw_ku64(w, "first_seq", c->first_seq);
    rrc_jw_ku64(w, "span_us", c->span_us);
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
}

static void put_range(rrh_core_t *c, rrc_jw_t *w)
{
    rrc_jw_ku64(w, "oldest_seq", rrh_acq_oldest(c)->sequence);
    rrc_jw_ku64(w, "newest_seq", rrh_acq_newest(c)->sequence);
}

static void op_read(rrh_core_t *c, const rrc_json_t *d, const rrc_req_t *req, rrc_jw_t *w)
{
    int64_t after = 0;
    if (!arg_i64(d, req->args, "after_seq", -1, 9007199254740991LL, &after)) {
        rrh_reply_status(w, req->id, "BAD_ARG", "after_seq");
        return;
    }
    const rrh_frame_t *oldest = rrh_acq_oldest(c);
    if (oldest == NULL) {
        rrh_reply_status(w, req->id, "EMPTY", NULL); /* nothing produced yet in this attachment */
        return;
    }
    if ((after + 1) < (int64_t)oldest->sequence) {
        /* Requested data have expired: report the exact retained range. */
        rrc_rsp_begin(w, RRH_PROTO_VERSION, req->id, "GAP");
        rrc_jw_obj_begin(w);
        put_range(c, w);
        rrc_jw_obj_end(w);
        rrc_rsp_end(w);
        return;
    }
    const rrh_frame_t *f = rrh_acq_first_after(c, after);
    if (f == NULL) {
        rrh_reply_status(w, req->id, "EMPTY", NULL); /* the requested sequence is still pending */
        return;
    }
    reply_begin_ok(w, req->id);
    rrh_acq_write_frame(c, f, w);
    rrc_rsp_end(w);
}

static void op_disarm(rrh_core_t *c, const rrc_req_t *req, rrc_jw_t *w)
{
    bool pending = c->draining;
    if (c->armed) {
        /* The gate in progress is completed and delivered; the heater goes off with it. */
        pending = rrh_hal_acq_stop();
        c->armed = false;
        c->draining = rrh_hal_acq_running();
        rrh_control_heater_off(c);
        rrh_acq_drain(c);
        pending = pending && c->draining;
    }
    reply_begin_ok(w, req->id);
    rrc_jw_obj_begin(w);
    if (pending) {
        rrc_jw_ku64(w, "last_seq", c->next_seq); /* number of the gate now being completed */
    } else if (c->next_seq > 0u) {
        rrc_jw_ku64(w, "last_seq", c->next_seq - 1u);
    } else {
        rrc_jw_knull(w, "last_seq");
    }
    rrc_jw_kbool(w, "complete", !pending);
    rrc_jw_obj_end(w);
    rrc_rsp_end(w);
}

/* ---- dispatch -------------------------------------------------------------------------------- */
static bool op_is(const rrc_json_t *d, const rrc_req_t *req, const char *name)
{
    return rrc_json_str_eq(d, req->op, name);
}

static void dispatch(rrh_core_t *c, const rrc_json_t *d, const rrc_req_t *req, rrc_jw_t *w, uint64_t rx_us,
                     uint64_t *tx_at_us)
{
    if (op_is(d, req, "HELLO")) {
        op_hello(c, req, w);
    } else if (op_is(d, req, "GET_DESCRIPTOR")) {
        op_get_descriptor(c, d, req, w);
    } else if (op_is(d, req, "BIND")) {
        op_bind(c, d, req, w);
    } else if (op_is(d, req, "TIME") || op_is(d, req, "SYNC") || op_is(d, req, "ARM") || op_is(d, req, "READ") ||
               op_is(d, req, "DISARM")) {
        if (c->link != RRH_LINK_BOUND) {
            rrh_reply_status(w, req->id, "UNBOUND", NULL); /* no counts, no state change */
        } else if (op_is(d, req, "TIME")) {
            op_time(req, w, rx_us, tx_at_us);
        } else if (op_is(d, req, "SYNC")) {
            op_sync(c, d, req, w, rx_us);
        } else if (op_is(d, req, "ARM")) {
            op_arm(c, d, req, w);
        } else if (op_is(d, req, "READ")) {
            op_read(c, d, req, w);
        } else {
            op_disarm(c, req, w);
        }
    } else if (!rrh_eng_dispatch(c, d, req, w)) {
        rrh_reply_status(w, req->id, "UNSUPPORTED", NULL);
    } else {
        /* handled by an additive op */
    }
}

static bool handle_record(rrh_core_t *c, size_t json_len, uint32_t crc, uint64_t rx_us, rrh_reply_t *reply)
{
    static rrc_jtok_t tok[RRH_JSON_TOKENS];
    rrc_json_t doc;
    rrc_req_t req;
    if (rrc_json_parse(&doc, (const char *)c->rx_buf, json_len, tok, RRH_JSON_TOKENS, &k_limits) != RRC_JSON_OK) {
        c->n_discarded++;
        return false; /* malformed / duplicate-key records are discarded without a reply */
    }
    const rrc_req_status_t st = rrc_req_parse(&doc, RRH_PROTO_VERSION, &req);
    if (st == RRC_REQ_INVALID) {
        c->n_discarded++;
        return false;
    }
    c->n_requests++;
    /* TIME is the one op that is never answered from the cache: its reply is a measurement of
     * THIS exchange, and it changes no state, so re-executing it is idempotent. */
    const bool is_time = (st == RRC_REQ_OK) && op_is(&doc, &req, "TIME");
    if (!is_time && rrc_cache_hit(&c->cache, req.id, crc, json_len)) {
        c->n_retries++;
        reply->data = c->tx_buf;
        reply->len = c->cache.reply_len;
        reply->tx_at_us = 0u;
        return true;
    }
    rrc_cache_clear(&c->cache); /* tx_buf is about to be overwritten */
    rrh_acq_drain(c);           /* act on the state as of now */

    rrc_jw_t w;
    uint64_t tx_at_us = 0u;
    rrc_jw_init(&w, (char *)c->tx_buf, RRH_TX_MAX - RRC_FRAME_TRAILER_LEN);
    if (st == RRC_REQ_BAD_VERSION) {
        rrh_reply_status(&w, req.id, "UNSUPPORTED", "version");
    } else if (st == RRC_REQ_BAD_SHAPE) {
        rrh_reply_status(&w, req.id, "BAD_ARG", "envelope");
    } else {
        dispatch(c, &doc, &req, &w, rx_us, &tx_at_us);
    }
    if (!rrc_jw_ok(&w)) {
        rrc_jw_init(&w, (char *)c->tx_buf, RRH_TX_MAX - RRC_FRAME_TRAILER_LEN);
        rrh_reply_status(&w, req.id, "FAULT", "reply_overflow");
        tx_at_us = 0u;
    }
    const size_t n = rrc_frame_finish(c->tx_buf, rrc_jw_len(&w), RRH_TX_MAX, RRH_RX_MAX);
    if (n == 0u) {
        return false;
    }
    if (!is_time) {
        rrc_cache_store(&c->cache, req.id, crc, json_len, n);
    }
    reply->data = c->tx_buf;
    reply->len = n;
    reply->tx_at_us = tx_at_us;
    return true;
}

/* ---- public API -------------------------------------------------------------------------------- */
void rrh_core_init(rrh_core_t *c, const rrh_identity_t *ident)
{
    uint8_t blob[128];
    size_t blob_len = 0u;
    uint8_t rnd[16];

    memset(c, 0, sizeof *c);
    c->ident = *ident;
    if ((c->ident.gate_min_us < RRH_SPAN_MIN_US) || (c->ident.gate_max_us > RRH_SPAN_MAX_US) ||
        (c->ident.gate_min_us > c->ident.gate_max_us)) {
        c->ident.gate_min_us = RRH_SPAN_DEFAULT_US;
        c->ident.gate_max_us = RRH_SPAN_DEFAULT_US;
    }
    c->reset_cause = rrh_hal_reset_cause();
    if (c->reset_cause == RRH_RESET_WATCHDOG) {
        c->health |= RRH_H_WATCHDOG_RESET;
    }

    /* Fresh boot id at EVERY boot; nothing of a previous boot's link state exists (memset). */
    if (!rrh_hal_entropy(rnd, sizeof rnd)) {
        c->health |= RRH_H_ENTROPY;
    }
    rrc_uuid4_format(rnd, c->boot_id);

    rrh_setup_defaults(&c->setup);
    if (rrh_hal_nv_load(RRH_NV_SLOT_SETUP, blob, sizeof blob, &blob_len)) {
        if (!rrh_setup_unpack(&c->setup, blob, blob_len)) {
            c->health |= RRH_H_STORAGE; /* stored setup damaged: defaults stay in use */
        }
    }
    if (!rrh_descriptor_rebuild(c)) {
        c->health |= RRH_H_STORAGE;
    }
    if (!rrh_hal_frontend_apply(&c->setup.fe)) {
        c->health |= RRH_H_SOURCE;
    }
    rrc_frame_rx_init(&c->rx, c->rx_buf, RRH_RX_MAX);
    c->rx_gap_timeout_us = RRH_RX_GAP_TIMEOUT_US;
    rrc_cache_clear(&c->cache);
    c->link = RRH_LINK_UNBOUND;
    rrh_acq_reset(c);
    rrh_control_init(c);
    rrh_cal_id_compute(c, c->cal_id);
    c->image_crc32 = rrh_hal_image_crc32();
}

void rrh_core_poll(rrh_core_t *c)
{
    const uint64_t now = rrh_hal_now_us();
    rrh_acq_drain(c);
    rrh_control_periodic(c, now);

    if (c->armed) {
        /* Stale-gate watchdog: an armed head that stops producing gates must say so. */
        const uint64_t limit = ((uint64_t)c->span_us * RRH_GATE_TIMEOUT_SPANS) + 50000u;
        if (rrc_time_since(now, c->last_gate_us) > limit) {
            c->health |= RRH_H_GATE_TIMEOUT;
            c->acq_event_pending = true;
            c->fault_events_total++;
            c->last_gate_us = now;
        }
    } else if (!c->draining && c->heater_on) {
        rrh_control_heater_off(c); /* the heater never runs outside an armed acquisition */
    } else {
        /* idle */
    }
    if (rrc_frame_rx_busy(&c->rx) && (rrc_time_since(now, c->rx_last_us) > c->rx_gap_timeout_us)) {
        rrc_frame_rx_reset(&c->rx);
    }
    rrh_hal_watchdog_kick();
}

bool rrh_core_rx_byte(rrh_core_t *c, uint8_t byte, uint64_t rx_us, rrh_reply_t *reply)
{
    size_t json_len = 0u;
    uint32_t crc = 0u;
    c->rx_last_us = rx_us;
    const rrc_rx_result_t r = rrc_frame_rx_push(&c->rx, byte, &json_len, &crc);
    if (r == RRC_RX_DISCARDED) {
        c->n_discarded++;
    }
    if (r != RRC_RX_RECORD) {
        return false;
    }
    return handle_record(c, json_len, crc, rx_us, reply);
}

void rrh_core_rx_timeout(rrh_core_t *c)
{
    rrc_frame_rx_reset(&c->rx);
}
