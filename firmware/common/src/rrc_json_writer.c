#include "rrc_json_writer.h"

#include <string.h>

void rrc_jw_init(rrc_jw_t *w, char *buf, size_t cap)
{
    w->buf = buf;
    w->cap = cap;
    w->len = 0u;
    w->error = (buf == NULL) || (cap == 0u);
    w->after_key = false;
    w->depth = 0u;
    w->has_item = 0u;
    w->is_obj = 0u;
}

bool rrc_jw_ok(const rrc_jw_t *w)
{
    return (!w->error) && (w->depth == 0u) && (!w->after_key);
}

size_t rrc_jw_len(const rrc_jw_t *w)
{
    return w->len;
}

static void put(rrc_jw_t *w, const char *s, size_t n)
{
    if (w->error) {
        return;
    }
    if ((w->cap - w->len) < n) {
        w->error = true;
        return;
    }
    memcpy(&w->buf[w->len], s, n);
    w->len += n;
}

static void putc_(rrc_jw_t *w, char c)
{
    put(w, &c, 1u);
}

/* Emit the separator a new value needs and mark the container as non-empty. */
static void before_value(rrc_jw_t *w)
{
    if (w->error) {
        return;
    }
    if (w->after_key) {
        w->after_key = false;
        return;
    }
    if (w->depth == 0u) {
        if (w->len != 0u) {
            w->error = true; /* second top-level value */
        }
        return;
    }
    const uint32_t bit = 1uL << (w->depth - 1u);
    if ((w->is_obj & bit) != 0u) {
        w->error = true; /* value inside an object without a key */
        return;
    }
    if ((w->has_item & bit) != 0u) {
        putc_(w, ',');
    }
    w->has_item |= bit;
}

static void jw_open(rrc_jw_t *w, char c, bool is_obj)
{
    before_value(w);
    if (w->depth >= RRC_JW_MAX_DEPTH) {
        w->error = true;
        return;
    }
    putc_(w, c);
    const uint32_t bit = 1uL << w->depth;
    w->has_item &= ~bit;
    if (is_obj) {
        w->is_obj |= bit;
    } else {
        w->is_obj &= ~bit;
    }
    w->depth++;
}

static void jw_close(rrc_jw_t *w, char c, bool is_obj)
{
    if ((w->depth == 0u) || w->after_key) {
        w->error = true;
        return;
    }
    const uint32_t bit = 1uL << (w->depth - 1u);
    if (((w->is_obj & bit) != 0u) != is_obj) {
        w->error = true;
        return;
    }
    w->depth--;
    putc_(w, c);
}

void rrc_jw_obj_begin(rrc_jw_t *w) { jw_open(w, '{', true); }
void rrc_jw_obj_end(rrc_jw_t *w) { jw_close(w, '}', true); }
void rrc_jw_arr_begin(rrc_jw_t *w) { jw_open(w, '[', false); }
void rrc_jw_arr_end(rrc_jw_t *w) { jw_close(w, ']', false); }

static void put_escaped(rrc_jw_t *w, const char *s, size_t n)
{
    static const char hex[] = "0123456789abcdef";
    putc_(w, '"');
    for (size_t i = 0u; i < n; i++) {
        const unsigned char c = (unsigned char)s[i];
        switch (c) {
        case '"': put(w, "\\\"", 2u); break;
        case '\\': put(w, "\\\\", 2u); break;
        case '\n': put(w, "\\n", 2u); break;
        case '\r': put(w, "\\r", 2u); break;
        case '\t': put(w, "\\t", 2u); break;
        case '\b': put(w, "\\b", 2u); break;
        case '\f': put(w, "\\f", 2u); break;
        default:
            if (c < 0x20u) {
                char e[6] = {'\\', 'u', '0', '0', hex[(c >> 4) & 0x0Fu], hex[c & 0x0Fu]};
                put(w, e, sizeof e);
            } else {
                putc_(w, (char)c);
            }
            break;
        }
    }
    putc_(w, '"');
}

void rrc_jw_key(rrc_jw_t *w, const char *key)
{
    if (w->error) {
        return;
    }
    if ((w->depth == 0u) || w->after_key) {
        w->error = true;
        return;
    }
    const uint32_t bit = 1uL << (w->depth - 1u);
    if ((w->is_obj & bit) == 0u) {
        w->error = true;
        return;
    }
    if ((w->has_item & bit) != 0u) {
        putc_(w, ',');
    }
    w->has_item |= bit;
    put_escaped(w, key, strlen(key));
    putc_(w, ':');
    w->after_key = true;
}

void rrc_jw_strn(rrc_jw_t *w, const char *s, size_t n)
{
    before_value(w);
    put_escaped(w, s, n);
}

void rrc_jw_str(rrc_jw_t *w, const char *s)
{
    rrc_jw_strn(w, s, strlen(s));
}

static size_t fmt_u64(uint64_t v, char out[20])
{
    char tmp[20];
    size_t n = 0u;
    do {
        tmp[n] = (char)('0' + (char)(v % 10u));
        n++;
        v /= 10u;
    } while (v != 0u);
    for (size_t i = 0u; i < n; i++) {
        out[i] = tmp[n - 1u - i];
    }
    return n;
}

void rrc_jw_u64(rrc_jw_t *w, uint64_t v)
{
    char d[20];
    before_value(w);
    put(w, d, fmt_u64(v, d));
}

void rrc_jw_i64(rrc_jw_t *w, int64_t v)
{
    char d[20];
    before_value(w);
    uint64_t mag = (uint64_t)v;
    if (v < 0) {
        putc_(w, '-');
        mag = (uint64_t)0 - mag; /* two's complement magnitude, defined for INT64_MIN */
    }
    put(w, d, fmt_u64(mag, d));
}

void rrc_jw_bool(rrc_jw_t *w, bool v)
{
    before_value(w);
    if (v) {
        put(w, "true", 4u);
    } else {
        put(w, "false", 5u);
    }
}

void rrc_jw_null(rrc_jw_t *w)
{
    before_value(w);
    put(w, "null", 4u);
}

void rrc_jw_fixed(rrc_jw_t *w, int64_t value, uint8_t decimals, bool trim)
{
    char d[20];
    char frac[9];
    before_value(w);
    if (decimals > 9u) {
        w->error = true;
        return;
    }
    uint64_t scale = 1u;
    for (uint8_t i = 0u; i < decimals; i++) {
        scale *= 10u;
    }
    uint64_t mag = (uint64_t)value;
    const bool neg = value < 0;
    if (neg) {
        mag = (uint64_t)0 - mag;
    }
    const uint64_t ip = mag / scale;
    uint64_t fp = mag % scale;
    size_t nfrac = decimals;
    for (size_t i = 0u; i < (size_t)decimals; i++) {
        frac[(size_t)decimals - 1u - i] = (char)('0' + (char)(fp % 10u));
        fp /= 10u;
    }
    if (trim) {
        while ((nfrac > 0u) && (frac[nfrac - 1u] == '0')) {
            nfrac--;
        }
    }
    if (neg) {
        putc_(w, '-'); /* value < 0 implies a non-zero magnitude, so "-0" cannot appear */
    }
    put(w, d, fmt_u64(ip, d));
    if (nfrac > 0u) {
        putc_(w, '.');
        put(w, frac, nfrac);
    }
}

void rrc_jw_raw(rrc_jw_t *w, const char *json, size_t n)
{
    before_value(w);
    put(w, json, n);
}

void rrc_jw_kstr(rrc_jw_t *w, const char *key, const char *s) { rrc_jw_key(w, key); rrc_jw_str(w, s); }
void rrc_jw_ki64(rrc_jw_t *w, const char *key, int64_t v) { rrc_jw_key(w, key); rrc_jw_i64(w, v); }
void rrc_jw_ku64(rrc_jw_t *w, const char *key, uint64_t v) { rrc_jw_key(w, key); rrc_jw_u64(w, v); }
void rrc_jw_kbool(rrc_jw_t *w, const char *key, bool v) { rrc_jw_key(w, key); rrc_jw_bool(w, v); }
void rrc_jw_knull(rrc_jw_t *w, const char *key) { rrc_jw_key(w, key); rrc_jw_null(w); }
void rrc_jw_kfixed(rrc_jw_t *w, const char *key, int64_t value, uint8_t decimals, bool trim)
{
    rrc_jw_key(w, key);
    rrc_jw_fixed(w, value, decimals, trim);
}
