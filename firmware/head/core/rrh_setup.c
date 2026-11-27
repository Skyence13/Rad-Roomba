/* Setup (thresholds, trims, bias, heater), setup_id derivation and the descriptor builder. */
#include <string.h>

#include "rrh_board.h"
#include "rrh_internal.h"

/* ---- Rev E concept geometry, micrometres in the head_mount frame ------------------------------
 * Source: interface/system/contract.yaml (frames.head_mount, head_envelope_rev_e_mm, optics).
 *   head_mount = (65.7, 0, 32) mm in base_link (option C, DEC-041); envelope x 66.0..212.5 (sprung
 *   leading rail front face at 212.2 unloaded), y +-175, z 5..50;
 *   optics row centre x = 131.2, entrance film z = 10, active 100 (x) by 80 (y),
 *   lane centres y = +131.25, +43.75, -43.75, -131.25.
 * firmware 0.4 carried the pre-IB-11 envelope x max 192.2 (126500 um); the contract has moved to
 * 212.5, which the baseline test test_descriptor_rev_e_concept reads from contract.yaml. */
#define GEO_ENV_MIN_X 300
#define GEO_ENV_MIN_Y (-175000)
#define GEO_ENV_MIN_Z (-27000)
#define GEO_ENV_MAX_X 146800
#define GEO_ENV_MAX_Y 175000
#define GEO_ENV_MAX_Z 18000
#define GEO_CENTER_X 65500
#define GEO_WINDOW_Z (-22000)
#define GEO_HALF_X 50000
#define GEO_HALF_Y 40000
#define GEO_STANDOFF 10000
static const int32_t k_lane_y[RRH_LANES] = {131250, 43750, -43750, -131250};

void rrh_setup_defaults(rrh_setup_t *s)
{
    memset(s, 0, sizeof *s);
    /* Thresholds are voltages ABOVE the 0.600 V baseline (R2310/R2311): a DAC code below the
     * baseline (firmware 0.4 used 200 = 0.12 V) leaves the comparator permanently high. Levels in
     * photo-electrons use the FAST path gain of a 6 mm onsemi J-series device at low overvoltage
     * (6.9 mV per p.e., budget 2.2, ASSUMED until the SiPM is chosen). */
    const uint16_t lld = rrh_board_threshold_code(RRH_DEFAULT_LLD_PE * RRH_FAST_UV_PER_PE);
    const uint16_t uld = rrh_board_threshold_code(RRH_DEFAULT_ULD_PE * RRH_FAST_UV_PER_PE);
    const uint16_t alpha = rrh_board_threshold_code(RRH_DEFAULT_ALPHA_UV);
    for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
        s->fe.threshold[(lane * 3u) + 0u] = lld;   /* BETA_LLD */
        s->fe.threshold[(lane * 3u) + 1u] = uld;   /* BETA_ULD */
        s->fe.threshold[(lane * 3u) + 2u] = alpha; /* ALPHA (slow path) */
        s->fe.threshold[12u + (lane * 2u) + 0u] = lld; /* REF_LLD */
        s->fe.threshold[12u + (lane * 2u) + 1u] = uld; /* REF_ULD */
    }
    for (uint32_t i = 0u; i < RRH_N_TRIMS; i++) {
        s->fe.trim[i] = 2048u; /* 1.25 V of the usable 0.10 ... 2.50 V */
    }
    s->fe.pulser_code = 0u;
    s->fe.pulser_enable = false;
    s->fe.pulser_channel = 0u;
    s->fe.pulser_width_us = 2u;
    s->fe.led_code = 0u;
    s->fe.led_enable = false;
    s->fe.alpha_hold_us = RRH_ALPHA_HOLD_DEFAULT_US;
    s->fe.chain_enable = 0xFFu;
    /* Placeholders until the SiPM type is known: 30.0 V at 25 degC is below the fitted 31.5 V
     * over-voltage trip (rev A, onsemi J/C strap); 21.5 mV/degC is the onsemi J-series value. */
    s->bias_ref_mv = 30000u;
    s->bias_tc_uv_per_c = 21500;
    s->t_ref_mc = 25000;
    s->heater_enable = false; /* heater defaults OFF */
    s->heater_setpoint_mc = 5000;
    s->heater_max_duty_pct = 80u;
}

bool rrh_setup_valid(const rrh_setup_t *s)
{
    for (uint32_t i = 0u; i < RRH_N_THRESHOLDS; i++) {
        if (s->fe.threshold[i] > 4095u) {
            return false;
        }
    }
    for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
        if (s->fe.threshold[lane * 3u] >= s->fe.threshold[(lane * 3u) + 1u]) {
            return false; /* BETA_LLD must be below BETA_ULD */
        }
        if (s->fe.threshold[12u + (lane * 2u)] >= s->fe.threshold[12u + (lane * 2u) + 1u]) {
            return false; /* REF_LLD must be below REF_ULD */
        }
    }
    for (uint32_t i = 0u; i < RRH_N_TRIMS; i++) {
        if (s->fe.trim[i] > 4095u) {
            return false;
        }
    }
    if ((s->fe.pulser_channel > 7u) || (s->fe.pulser_width_us < 1u) || (s->fe.pulser_width_us > 100u) ||
        (s->fe.led_code > 4095u) || (s->fe.alpha_hold_us > RRH_ALPHA_HOLD_MAX_US)) {
        return false;
    }
    return (s->fe.pulser_code <= 4095u) && (s->bias_ref_mv >= RRH_BIAS_MIN_MV) &&
           (s->bias_ref_mv <= rrh_board_bias_limit_mv()) &&
           (s->bias_tc_uv_per_c >= -200000) && (s->bias_tc_uv_per_c <= 200000) && (s->t_ref_mc >= -40000) &&
           (s->t_ref_mc <= 85000) && (s->heater_setpoint_mc >= -20000) && (s->heater_setpoint_mc <= 40000) &&
           (s->heater_max_duty_pct <= 100u);
}

/* ---- canonical byte image (non-volatile storage and setup hash) ------------------------------ */
#define SETUP_IMAGE_VERSION 2u
#define SETUP_IMAGE_LEN (1u + (2u * RRH_N_THRESHOLDS) + (2u * RRH_N_TRIMS) + 2u + 1u + 1u + 4u + 4u + 4u + 1u + 4u + 1u + 1u + 1u + 1u + 2u + 2u)

static size_t put_be(uint8_t *buf, size_t pos, uint32_t v, size_t bytes)
{
    for (size_t i = 0u; i < bytes; i++) {
        buf[pos + i] = (uint8_t)(v >> (8u * (bytes - 1u - i)));
    }
    return pos + bytes;
}

static uint32_t get_be(const uint8_t *buf, size_t *pos, size_t bytes)
{
    uint32_t v = 0u;
    for (size_t i = 0u; i < bytes; i++) {
        v = (v << 8) | buf[*pos + i];
    }
    *pos += bytes;
    return v;
}

static size_t pack_image(const rrh_setup_t *s, uint8_t *buf)
{
    size_t n = 0u;
    n = put_be(buf, n, SETUP_IMAGE_VERSION, 1u);
    for (uint32_t i = 0u; i < RRH_N_THRESHOLDS; i++) {
        n = put_be(buf, n, s->fe.threshold[i], 2u);
    }
    for (uint32_t i = 0u; i < RRH_N_TRIMS; i++) {
        n = put_be(buf, n, s->fe.trim[i], 2u);
    }
    n = put_be(buf, n, s->fe.pulser_code, 2u);
    n = put_be(buf, n, s->fe.pulser_enable ? 1u : 0u, 1u);
    n = put_be(buf, n, s->fe.chain_enable, 1u);
    n = put_be(buf, n, s->bias_ref_mv, 4u);
    n = put_be(buf, n, (uint32_t)s->bias_tc_uv_per_c, 4u);
    n = put_be(buf, n, (uint32_t)s->t_ref_mc, 4u);
    n = put_be(buf, n, s->heater_enable ? 1u : 0u, 1u);
    n = put_be(buf, n, (uint32_t)s->heater_setpoint_mc, 4u);
    n = put_be(buf, n, s->heater_max_duty_pct, 1u);
    n = put_be(buf, n, s->fe.pulser_channel, 1u);
    n = put_be(buf, n, s->fe.pulser_width_us, 1u);
    n = put_be(buf, n, s->fe.led_enable ? 1u : 0u, 1u);
    n = put_be(buf, n, s->fe.led_code, 2u);
    n = put_be(buf, n, s->fe.alpha_hold_us, 2u);
    return n;
}

/* Stored form: image followed by its CRC-32 (big endian). */
size_t rrh_setup_pack(const rrh_setup_t *s, uint8_t *buf, size_t cap)
{
    if (cap < (SETUP_IMAGE_LEN + 4u)) {
        return 0u;
    }
    const size_t n = pack_image(s, buf);
    return put_be(buf, n, rrc_crc32(buf, n), 4u);
}

bool rrh_setup_unpack(rrh_setup_t *s, const uint8_t *buf, size_t len)
{
    if ((len != (SETUP_IMAGE_LEN + 4u)) || (buf[0] != SETUP_IMAGE_VERSION)) {
        return false;
    }
    size_t pos = SETUP_IMAGE_LEN;
    if (get_be(buf, &pos, 4u) != rrc_crc32(buf, SETUP_IMAGE_LEN)) {
        return false;
    }
    rrh_setup_t t;
    memset(&t, 0, sizeof t);
    pos = 1u;
    for (uint32_t i = 0u; i < RRH_N_THRESHOLDS; i++) {
        t.fe.threshold[i] = (uint16_t)get_be(buf, &pos, 2u);
    }
    for (uint32_t i = 0u; i < RRH_N_TRIMS; i++) {
        t.fe.trim[i] = (uint16_t)get_be(buf, &pos, 2u);
    }
    t.fe.pulser_code = (uint16_t)get_be(buf, &pos, 2u);
    t.fe.pulser_enable = get_be(buf, &pos, 1u) != 0u;
    t.fe.chain_enable = (uint8_t)get_be(buf, &pos, 1u);
    t.bias_ref_mv = get_be(buf, &pos, 4u);
    t.bias_tc_uv_per_c = (int32_t)get_be(buf, &pos, 4u);
    t.t_ref_mc = (int32_t)get_be(buf, &pos, 4u);
    t.heater_enable = get_be(buf, &pos, 1u) != 0u;
    t.heater_setpoint_mc = (int32_t)get_be(buf, &pos, 4u);
    t.heater_max_duty_pct = (uint8_t)get_be(buf, &pos, 1u);
    t.fe.pulser_channel = (uint8_t)get_be(buf, &pos, 1u);
    t.fe.pulser_width_us = (uint8_t)get_be(buf, &pos, 1u);
    t.fe.led_enable = get_be(buf, &pos, 1u) != 0u;
    t.fe.led_code = (uint16_t)get_be(buf, &pos, 2u);
    t.fe.alpha_hold_us = (uint16_t)get_be(buf, &pos, 2u);
    if (!rrh_setup_valid(&t)) {
        return false;
    }
    *s = t;
    return true;
}

/* setup_id = "S1-" + first 16 hex digits of SHA-256(domain | setup image | firmware id).
 * Any change of a threshold, trim, bias law, pulser, heater law, chain enable or firmware
 * version therefore changes the id the host bound to. (DEC-037: there is no bitstream.) */
void rrh_setup_compute_id(const rrh_setup_t *s, const char *firmware, char out[24])
{
    static const char domain[] = "RRH-SETUP-1";
    uint8_t image[SETUP_IMAGE_LEN];
    uint8_t dg[RRC_SHA256_LEN];
    char hex[RRC_SHA256_HEX_LEN + 1u];
    rrc_sha256_t ctx;
    const size_t n = pack_image(s, image);
    rrc_sha256_init(&ctx);
    rrc_sha256_update(&ctx, domain, sizeof domain); /* includes the NUL as a separator */
    rrc_sha256_update(&ctx, image, n);
    rrc_sha256_update(&ctx, firmware, strlen(firmware) + 1u);
    rrc_sha256_final(&ctx, dg);
    rrc_hex_lower(dg, sizeof dg, hex);
    out[0] = 'S';
    out[1] = '1';
    out[2] = '-';
    memcpy(&out[3], hex, 16u);
    out[19] = '\0';
}

/* ---- JSON form (ENG_SETUP_GET / ENG_SETUP_SET) ------------------------------------------------ */
static const char *const k_thr_names[5] = {"beta_lld", "beta_uld", "alpha", "ref_lld", "ref_uld"};

static uint32_t thr_index(uint32_t kind, uint32_t lane)
{
    return (kind < 3u) ? ((lane * 3u) + kind) : (12u + (lane * 2u) + (kind - 3u));
}

void rrh_setup_to_json(const rrh_setup_t *s, rrc_jw_t *w)
{
    rrc_jw_obj_begin(w);
    rrc_jw_key(w, "thresholds");
    rrc_jw_obj_begin(w);
    for (uint32_t kind = 0u; kind < 5u; kind++) {
        rrc_jw_key(w, k_thr_names[kind]);
        rrc_jw_arr_begin(w);
        for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
            rrc_jw_u64(w, s->fe.threshold[thr_index(kind, lane)]);
        }
        rrc_jw_arr_end(w);
    }
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "trim");
    rrc_jw_obj_begin(w);
    for (uint32_t g = 0u; g < 2u; g++) {
        rrc_jw_key(w, (g == 0u) ? "floor" : "ref");
        rrc_jw_arr_begin(w);
        for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
            rrc_jw_u64(w, s->fe.trim[(g * 4u) + lane]);
        }
        rrc_jw_arr_end(w);
    }
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "bias");
    rrc_jw_obj_begin(w);
    rrc_jw_ku64(w, "ref_mv", s->bias_ref_mv);
    rrc_jw_ki64(w, "tc_uv_per_c", s->bias_tc_uv_per_c);
    rrc_jw_ki64(w, "t_ref_mc", s->t_ref_mc);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "pulser");
    rrc_jw_obj_begin(w);
    rrc_jw_kbool(w, "enable", s->fe.pulser_enable);
    rrc_jw_ku64(w, "code", s->fe.pulser_code);
    rrc_jw_ku64(w, "channel", s->fe.pulser_channel);
    rrc_jw_ku64(w, "width_us", s->fe.pulser_width_us);
    rrc_jw_kbool(w, "led_enable", s->fe.led_enable);
    rrc_jw_ku64(w, "led_code", s->fe.led_code);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "afterglow");
    rrc_jw_obj_begin(w);
    rrc_jw_ku64(w, "alpha_hold_us", s->fe.alpha_hold_us);
    rrc_jw_obj_end(w);
    rrc_jw_key(w, "heater");
    rrc_jw_obj_begin(w);
    rrc_jw_kbool(w, "enable", s->heater_enable);
    rrc_jw_ki64(w, "setpoint_mc", s->heater_setpoint_mc);
    rrc_jw_ku64(w, "max_duty_pct", s->heater_max_duty_pct);
    rrc_jw_obj_end(w);
    rrc_jw_ku64(w, "chain_enable", s->fe.chain_enable);
    rrc_jw_obj_end(w);
}

static bool get_int(const rrc_json_t *d, int obj, const char *key, int64_t lo, int64_t hi, int64_t *out, uint16_t *seen)
{
    const int t = rrc_json_get(d, obj, key);
    if (t < 0) {
        return true; /* absent: keep the current value */
    }
    int64_t v = 0;
    if (!rrc_json_to_i64(d, t, &v) || (v < lo) || (v > hi)) {
        return false;
    }
    *out = v;
    (*seen)++;
    return true;
}

static bool get_flag(const rrc_json_t *d, int obj, const char *key, bool *out, uint16_t *seen)
{
    const int t = rrc_json_get(d, obj, key);
    if (t < 0) {
        return true;
    }
    (*seen)++;
    return rrc_json_to_bool(d, t, out);
}

static bool get_codes4(const rrc_json_t *d, int obj, const char *key, uint16_t out[4], uint16_t *seen)
{
    const int a = rrc_json_get(d, obj, key);
    if (a < 0) {
        return true;
    }
    if ((rrc_json_type(d, a) != RRC_JT_ARRAY) || (rrc_json_size(d, a) != RRH_LANES)) {
        return false;
    }
    for (uint16_t i = 0u; i < RRH_LANES; i++) {
        int64_t v = 0;
        if (!rrc_json_to_i64(d, rrc_json_at(d, a, i), &v) || (v < 0) || (v > 4095)) {
            return false;
        }
        out[i] = (uint16_t)v;
    }
    (*seen)++;
    return true;
}

/* A sub-object may be absent; if present it must be an object with only known members. */
static bool sub_object(const rrc_json_t *d, int obj, const char *key, int *sub, uint16_t *seen)
{
    *sub = rrc_json_get(d, obj, key);
    if (*sub < 0) {
        return true;
    }
    (*seen)++;
    return rrc_json_type(d, *sub) == RRC_JT_OBJECT;
}

bool rrh_setup_from_json(rrh_setup_t *s, const rrc_json_t *d, int obj)
{
    rrh_setup_t t = *s;
    uint16_t top = 0u;
    int sub = -1;
    uint16_t n = 0u;
    int64_t v = 0;

    if (!sub_object(d, obj, "thresholds", &sub, &top)) {
        return false;
    }
    if (sub >= 0) {
        n = 0u;
        for (uint32_t kind = 0u; kind < 5u; kind++) {
            uint16_t codes[4];
            for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
                codes[lane] = t.fe.threshold[thr_index(kind, lane)];
            }
            if (!get_codes4(d, sub, k_thr_names[kind], codes, &n)) {
                return false;
            }
            for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
                t.fe.threshold[thr_index(kind, lane)] = codes[lane];
            }
        }
        if (n != rrc_json_size(d, sub)) {
            return false; /* unknown member */
        }
    }
    if (!sub_object(d, obj, "trim", &sub, &top)) {
        return false;
    }
    if (sub >= 0) {
        n = 0u;
        if (!get_codes4(d, sub, "floor", &t.fe.trim[0], &n) || !get_codes4(d, sub, "ref", &t.fe.trim[4], &n) ||
            (n != rrc_json_size(d, sub))) {
            return false;
        }
    }
    if (!sub_object(d, obj, "bias", &sub, &top)) {
        return false;
    }
    if (sub >= 0) {
        n = 0u;
        v = (int64_t)t.bias_ref_mv;
        if (!get_int(d, sub, "ref_mv", RRH_BIAS_MIN_MV, rrh_board_bias_limit_mv(), &v, &n)) {
            return false;
        }
        t.bias_ref_mv = (uint32_t)v;
        v = t.bias_tc_uv_per_c;
        if (!get_int(d, sub, "tc_uv_per_c", -200000, 200000, &v, &n)) {
            return false;
        }
        t.bias_tc_uv_per_c = (int32_t)v;
        v = t.t_ref_mc;
        if (!get_int(d, sub, "t_ref_mc", -40000, 85000, &v, &n) || (n != rrc_json_size(d, sub))) {
            return false;
        }
        t.t_ref_mc = (int32_t)v;
    }
    if (!sub_object(d, obj, "pulser", &sub, &top)) {
        return false;
    }
    if (sub >= 0) {
        n = 0u;
        v = t.fe.pulser_code;
        if (!get_flag(d, sub, "enable", &t.fe.pulser_enable, &n) || !get_int(d, sub, "code", 0, 4095, &v, &n)) {
            return false;
        }
        t.fe.pulser_code = (uint16_t)v;
        v = t.fe.pulser_channel;
        if (!get_int(d, sub, "channel", 0, 7, &v, &n)) {
            return false;
        }
        t.fe.pulser_channel = (uint8_t)v;
        v = t.fe.pulser_width_us;
        if (!get_int(d, sub, "width_us", 1, 100, &v, &n) || !get_flag(d, sub, "led_enable", &t.fe.led_enable, &n)) {
            return false;
        }
        t.fe.pulser_width_us = (uint8_t)v;
        v = t.fe.led_code;
        if (!get_int(d, sub, "led_code", 0, 4095, &v, &n) || (n != rrc_json_size(d, sub))) {
            return false;
        }
        t.fe.led_code = (uint16_t)v;
    }
    if (!sub_object(d, obj, "afterglow", &sub, &top)) {
        return false;
    }
    if (sub >= 0) {
        n = 0u;
        v = t.fe.alpha_hold_us;
        if (!get_int(d, sub, "alpha_hold_us", 0, RRH_ALPHA_HOLD_MAX_US, &v, &n) || (n != rrc_json_size(d, sub))) {
            return false;
        }
        t.fe.alpha_hold_us = (uint16_t)v;
    }
    if (!sub_object(d, obj, "heater", &sub, &top)) {
        return false;
    }
    if (sub >= 0) {
        n = 0u;
        v = t.heater_setpoint_mc;
        if (!get_flag(d, sub, "enable", &t.heater_enable, &n) || !get_int(d, sub, "setpoint_mc", -20000, 40000, &v, &n)) {
            return false;
        }
        t.heater_setpoint_mc = (int32_t)v;
        v = t.heater_max_duty_pct;
        if (!get_int(d, sub, "max_duty_pct", 0, 100, &v, &n) || (n != rrc_json_size(d, sub))) {
            return false;
        }
        t.heater_max_duty_pct = (uint8_t)v;
    }
    v = t.fe.chain_enable;
    if (!get_int(d, obj, "chain_enable", 0, 255, &v, &top)) {
        return false;
    }
    t.fe.chain_enable = (uint8_t)v;
    bool persist = false;
    if (!get_flag(d, obj, "persist", &persist, &top)) {
        return false;
    }
    if ((top != rrc_json_size(d, obj)) || !rrh_setup_valid(&t)) {
        return false; /* unknown top-level member or inconsistent values */
    }
    *s = t;
    return true;
}

/* ---- identity defaults and descriptor --------------------------------------------------------- */
static void copy_str(char *dst, size_t cap, const char *src)
{
    size_t n = strlen(src);
    if (n >= cap) {
        n = cap - 1u;
    }
    memcpy(dst, src, n);
    dst[n] = '\0';
}

void rrh_identity_defaults(rrh_identity_t *id, const char *serial)
{
    memset(id, 0, sizeof *id);
    copy_str(id->serial, sizeof id->serial, serial);
    copy_str(id->descriptor_id, sizeof id->descriptor_id, "D-RRHEAD-E-P01");
    copy_str(id->mechanical_revision, sizeof id->mechanical_revision, "E");
    copy_str(id->electronics_revision, sizeof id->electronics_revision, "RR-HEAD-ACQ-A");
    copy_str(id->geometry_id, sizeof id->geometry_id, "revE-nominal-geometry-concept");
    id->gate_min_us = RRH_SPAN_DEFAULT_US;
    id->gate_max_us = RRH_SPAN_DEFAULT_US;
    id->rail_5mm = false;
}

const char *rrh_firmware_id(const rrh_core_t *c)
{
    return (c->ident.firmware_override != NULL) ? c->ident.firmware_override : RRH_FW_VERSION;
}

static void put_xyz(rrc_jw_t *w, int32_t x, int32_t y, int32_t z)
{
    rrc_jw_arr_begin(w);
    rrc_jw_fixed(w, x, 6u, true);
    rrc_jw_fixed(w, y, 6u, true);
    rrc_jw_fixed(w, z, 6u, true);
    rrc_jw_arr_end(w);
}

/* Descriptor format 1.0 (interface/head_descriptor.schema.json), compact JSON plus one LF.
 * geometry_basis is always CONCEPT here: an as-built descriptor needs measured values this
 * firmware does not hold yet (see README, known gaps). */
static size_t build_descriptor(const rrh_core_t *c, uint8_t *buf, size_t cap)
{
    static const char *const caps[] = {"raw_counts", "per_channel_live_time", "head_temperature", "heater_status",
                                       "diag", "status", "fault_clear", "eng_setup", "eng_wave"};
    rrc_jw_t w;
    rrc_jw_init(&w, (char *)buf, cap - 1u);
    rrc_jw_obj_begin(&w);
    rrc_jw_kstr(&w, "version", "1.0");
    rrc_jw_kstr(&w, "descriptor_id", c->ident.descriptor_id);
    rrc_jw_kstr(&w, "serial", c->ident.serial);
    rrc_jw_kstr(&w, "head_type", RRH_HEAD_TYPE);
    rrc_jw_kstr(&w, "mechanical_revision", c->ident.mechanical_revision);
    rrc_jw_kstr(&w, "electronics_revision", c->ident.electronics_revision);
    rrc_jw_kstr(&w, "geometry_id", c->ident.geometry_id);
    rrc_jw_kstr(&w, "setup_id", c->setup_id);
    rrc_jw_kstr(&w, "geometry_basis", "CONCEPT");
    rrc_jw_kstr(&w, "frame", "head_mount");
    rrc_jw_kstr(&w, "coordinate_units", "m");
    rrc_jw_key(&w, "axes");
    rrc_jw_arr_begin(&w);
    rrc_jw_str(&w, "forward");
    rrc_jw_str(&w, "left");
    rrc_jw_str(&w, "up");
    rrc_jw_arr_end(&w);
    rrc_jw_key(&w, "envelope_m");
    rrc_jw_obj_begin(&w);
    rrc_jw_key(&w, "min");
    put_xyz(&w, GEO_ENV_MIN_X, GEO_ENV_MIN_Y, GEO_ENV_MIN_Z);
    rrc_jw_key(&w, "max");
    put_xyz(&w, GEO_ENV_MAX_X, GEO_ENV_MAX_Y, GEO_ENV_MAX_Z);
    rrc_jw_obj_end(&w);
    rrc_jw_key(&w, "mount_to_window_normal");
    put_xyz(&w, 0, 0, -1000000);
    rrc_jw_kfixed(&w, "nominal_window_standoff_m", GEO_STANDOFF, 6u, true);
    rrc_jw_kfixed(&w, "bumper_projection_below_window_m", c->ident.rail_5mm ? 5000 : 3000, 6u, true);
    rrc_jw_knull(&w, "measured_registration_uncertainty_m");
    rrc_jw_key(&w, "electrical");
    rrc_jw_obj_begin(&w);
    rrc_jw_key(&w, "supply_range_V");
    rrc_jw_arr_begin(&w);
    rrc_jw_i64(&w, 10);
    rrc_jw_i64(&w, 15);
    rrc_jw_arr_end(&w);
    rrc_jw_ki64(&w, "electronics_power_allocation_W", 10);
    rrc_jw_ki64(&w, "heater_power_allocation_W", 30);
    rrc_jw_obj_end(&w);
    rrc_jw_key(&w, "channel_order");
    rrc_jw_arr_begin(&w);
    rrc_jw_str(&w, "alpha");
    rrc_jw_str(&w, "beta_window");
    rrc_jw_str(&w, "photon_ref");
    rrc_jw_arr_end(&w);
    rrc_jw_kstr(&w, "acq_format", RRH_ACQ_FORMAT);
    rrc_jw_key(&w, "capabilities");
    rrc_jw_arr_begin(&w);
    for (size_t i = 0u; i < (sizeof caps / sizeof caps[0]); i++) {
        rrc_jw_str(&w, caps[i]);
    }
    rrc_jw_arr_end(&w);
    rrc_jw_key(&w, "gate_range_us");
    rrc_jw_arr_begin(&w);
    rrc_jw_u64(&w, c->ident.gate_min_us);
    rrc_jw_u64(&w, c->ident.gate_max_us);
    rrc_jw_arr_end(&w);
    rrc_jw_knull(&w, "qualified_standoff_m");
    rrc_jw_knull(&w, "qualified_detector_temperature_C");
    rrc_jw_key(&w, "segments");
    rrc_jw_arr_begin(&w);
    for (uint32_t lane = 0u; lane < RRH_LANES; lane++) {
        const int32_t y = k_lane_y[lane];
        rrc_jw_obj_begin(&w);
        rrc_jw_ku64(&w, "id", lane);
        rrc_jw_key(&w, "center_m");
        put_xyz(&w, GEO_CENTER_X, y, GEO_WINDOW_Z);
        rrc_jw_key(&w, "sensitive_polygon_m");
        rrc_jw_arr_begin(&w);
        put_xyz(&w, GEO_CENTER_X - GEO_HALF_X, y - GEO_HALF_Y, GEO_WINDOW_Z);
        put_xyz(&w, GEO_CENTER_X + GEO_HALF_X, y - GEO_HALF_Y, GEO_WINDOW_Z);
        put_xyz(&w, GEO_CENTER_X + GEO_HALF_X, y + GEO_HALF_Y, GEO_WINDOW_Z);
        put_xyz(&w, GEO_CENTER_X - GEO_HALF_X, y + GEO_HALF_Y, GEO_WINDOW_Z);
        rrc_jw_arr_end(&w);
        rrc_jw_knull(&w, "window_to_effective_plane_m");
        rrc_jw_knull(&w, "reference_center_m");
        rrc_jw_obj_end(&w);
    }
    rrc_jw_arr_end(&w);
    rrc_jw_knull(&w, "spatial_response_record_id");
    rrc_jw_obj_end(&w);
    if (!rrc_jw_ok(&w)) {
        return 0u;
    }
    size_t n = rrc_jw_len(&w);
    buf[n] = (uint8_t)'\n';
    n++;
    return n;
}

bool rrh_descriptor_rebuild(rrh_core_t *c)
{
    uint8_t dg[RRC_SHA256_LEN];
    if (c->ident.setup_id_override != NULL) {
        copy_str(c->setup_id, sizeof c->setup_id, c->ident.setup_id_override);
    } else {
        rrh_setup_compute_id(&c->setup, rrh_firmware_id(c), c->setup_id);
    }
    if ((c->ident.descriptor_override != NULL) && (c->ident.descriptor_override_len > 0u)) {
        c->descriptor = c->ident.descriptor_override;
        c->descriptor_len = c->ident.descriptor_override_len;
    } else {
        c->descriptor = c->descriptor_buf;
        c->descriptor_len = build_descriptor(c, c->descriptor_buf, sizeof c->descriptor_buf);
    }
    rrc_sha256(c->descriptor, c->descriptor_len, dg);
    rrc_hex_lower(dg, sizeof dg, c->descriptor_sha256);
    return c->descriptor_len > 0u;
}
