/* Strict, minimal, allocation-free JSON reader (RFC 8259 grammar).
 *
 * rrc_json_parse() validates the WHOLE document before anything can be read from it and
 * fills a caller-supplied token array. It rejects:
 *   - anything that is not exactly one JSON value (trailing bytes other than whitespace);
 *   - duplicate keys in any object (compared after unescaping, so "a" == "a");
 *   - invalid UTF-8, unescaped control characters, bad escapes, unpaired surrogate escapes;
 *   - NaN / Infinity / leading zeros / leading '+' and every other non-RFC number form;
 *   - nesting deeper than limits.max_depth, strings longer than limits.max_string bytes
 *     (raw, between the quotes), and documents needing more than `cap` tokens.
 * Numbers are kept as text; integer accessors fail (return false) on fractions, exponents
 * and out-of-range values instead of rounding.
 */
#ifndef RRC_JSON_READER_H
#define RRC_JSON_READER_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    RRC_JT_OBJECT = 1,
    RRC_JT_ARRAY,
    RRC_JT_STRING,
    RRC_JT_NUMBER,
    RRC_JT_TRUE,
    RRC_JT_FALSE,
    RRC_JT_NULL
} rrc_jtype_t;

#define RRC_JF_KEY 0x01u     /* string token is an object member name */
#define RRC_JF_INTEGER 0x02u /* number token has no fraction and no exponent */
#define RRC_JF_ESCAPED 0x04u /* string token contains at least one backslash escape */

typedef struct {
    uint8_t type;   /* rrc_jtype_t */
    uint8_t flags;  /* RRC_JF_* */
    int16_t parent; /* token index of the enclosing container, -1 for the root */
    uint16_t size;  /* object: number of members; array: number of elements */
    uint32_t start; /* first byte of the token text (strings: after the opening quote) */
    uint32_t end;   /* one past the last byte (strings: the closing quote) */
} rrc_jtok_t;

typedef enum {
    RRC_JSON_OK = 0,
    RRC_JSON_ERR_SYNTAX,
    RRC_JSON_ERR_UTF8,
    RRC_JSON_ERR_DEPTH,
    RRC_JSON_ERR_TOKENS,
    RRC_JSON_ERR_STRING_LENGTH,
    RRC_JSON_ERR_DUPLICATE_KEY,
    RRC_JSON_ERR_TRAILING,
    RRC_JSON_ERR_ARG
} rrc_json_err_t;

typedef struct {
    uint16_t max_depth;  /* containers nested at most this deep (root container = depth 1) */
    uint32_t max_string; /* maximum raw string length in bytes */
} rrc_json_limits_t;

typedef struct {
    const char *js;
    size_t len;
    const rrc_jtok_t *tok;
    uint16_t ntok;
    size_t error_offset; /* byte offset of the first error, for diagnostics */
} rrc_json_t;

/* Token 0 is the root value on success. js need not be NUL-terminated. */
rrc_json_err_t rrc_json_parse(rrc_json_t *doc, const char *js, size_t len, rrc_jtok_t *tok, uint16_t cap,
                              const rrc_json_limits_t *limits);

/* All accessors take token indices; a negative or out-of-range index is "not found"/false. */
rrc_jtype_t rrc_json_type(const rrc_json_t *doc, int tok); /* 0 if tok is invalid */
int rrc_json_get(const rrc_json_t *doc, int obj, const char *key);     /* value token or -1 */
int rrc_json_at(const rrc_json_t *doc, int arr, uint16_t index);       /* element token or -1 */
uint16_t rrc_json_size(const rrc_json_t *doc, int container);          /* members / elements */
bool rrc_json_to_i64(const rrc_json_t *doc, int tok, int64_t *out);
bool rrc_json_to_u64(const rrc_json_t *doc, int tok, uint64_t *out);
bool rrc_json_to_bool(const rrc_json_t *doc, int tok, bool *out);
bool rrc_json_is_null(const rrc_json_t *doc, int tok);
/* String compare against a plain C string (the token is unescaped on the fly). */
bool rrc_json_str_eq(const rrc_json_t *doc, int tok, const char *s);
/* Copy the unescaped string as UTF-8 with a terminating NUL. Returns the length, or -1 if the
 * token is not a string or does not fit in cap bytes including the NUL. */
int rrc_json_str_copy(const rrc_json_t *doc, int tok, char *out, size_t cap);
/* Raw text of a token (numbers: the literal; strings: still escaped). */
const char *rrc_json_raw(const rrc_json_t *doc, int tok, size_t *len);

#ifdef __cplusplus
}
#endif
#endif
