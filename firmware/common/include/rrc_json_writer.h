/* Bounded, allocation-free JSON writer producing compact output (no whitespace), byte-compatible
 * with Python json.dumps(obj, separators=(",", ":"), ensure_ascii=False) for the value kinds it
 * supports. On overflow nothing is written past the buffer, the writer latches an error and
 * every later call is a no-op: check rrc_jw_ok() once at the end. */
#ifndef RRC_JSON_WRITER_H
#define RRC_JSON_WRITER_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define RRC_JW_MAX_DEPTH 16u

typedef struct {
    char *buf;
    size_t cap;
    size_t len;
    bool error;      /* overflow or misuse (depth, value without key, ...) */
    bool after_key;  /* a key was just written; the next value needs no comma */
    uint8_t depth;
    uint32_t has_item; /* bit d set: container at depth d already holds an item */
    uint32_t is_obj;   /* bit d set: container at depth d is an object */
} rrc_jw_t;

void rrc_jw_init(rrc_jw_t *w, char *buf, size_t cap);
bool rrc_jw_ok(const rrc_jw_t *w);
size_t rrc_jw_len(const rrc_jw_t *w);

void rrc_jw_obj_begin(rrc_jw_t *w);
void rrc_jw_obj_end(rrc_jw_t *w);
void rrc_jw_arr_begin(rrc_jw_t *w);
void rrc_jw_arr_end(rrc_jw_t *w);
void rrc_jw_key(rrc_jw_t *w, const char *key); /* key must be plain ASCII without escapes */

void rrc_jw_str(rrc_jw_t *w, const char *s);            /* NUL-terminated UTF-8, escaped as needed */
void rrc_jw_strn(rrc_jw_t *w, const char *s, size_t n); /* n bytes of UTF-8 */
void rrc_jw_i64(rrc_jw_t *w, int64_t v);
void rrc_jw_u64(rrc_jw_t *w, uint64_t v);
void rrc_jw_bool(rrc_jw_t *w, bool v);
void rrc_jw_null(rrc_jw_t *w);
/* Decimal fixed point: value / 10^decimals. trim removes trailing zeros (and the point if no
 * fraction remains), otherwise exactly `decimals` digits follow the point. decimals <= 9. */
void rrc_jw_fixed(rrc_jw_t *w, int64_t value, uint8_t decimals, bool trim);
/* Insert pre-formed JSON text as one value (caller guarantees validity). */
void rrc_jw_raw(rrc_jw_t *w, const char *json, size_t n);

/* key + value shorthands */
void rrc_jw_kstr(rrc_jw_t *w, const char *key, const char *s);
void rrc_jw_ki64(rrc_jw_t *w, const char *key, int64_t v);
void rrc_jw_ku64(rrc_jw_t *w, const char *key, uint64_t v);
void rrc_jw_kbool(rrc_jw_t *w, const char *key, bool v);
void rrc_jw_knull(rrc_jw_t *w, const char *key);
void rrc_jw_kfixed(rrc_jw_t *w, const char *key, int64_t value, uint8_t decimals, bool trim);

#ifdef __cplusplus
}
#endif
#endif
