#include "rrc_json_reader.h"

#include <string.h>

typedef struct {
    const char *js;
    size_t len;
    size_t pos;
    rrc_jtok_t *tok;
    uint16_t cap;
    uint16_t ntok;
    const rrc_json_limits_t *lim;
    rrc_json_err_t err;
} parser_t;

static bool fail(parser_t *p, rrc_json_err_t e)
{
    if (p->err == RRC_JSON_OK) {
        p->err = e;
    }
    return false;
}

static void skip_ws(parser_t *p)
{
    while (p->pos < p->len) {
        const char c = p->js[p->pos];
        if ((c != ' ') && (c != '\t') && (c != '\n') && (c != '\r')) {
            break;
        }
        p->pos++;
    }
}

static int new_tok(parser_t *p, rrc_jtype_t type, int parent, size_t start)
{
    if (p->ntok >= p->cap) {
        (void)fail(p, RRC_JSON_ERR_TOKENS);
        return -1;
    }
    rrc_jtok_t *t = &p->tok[p->ntok];
    t->type = (uint8_t)type;
    t->flags = 0u;
    t->parent = (int16_t)parent;
    t->size = 0u;
    t->start = (uint32_t)start;
    t->end = (uint32_t)start;
    const int idx = (int)p->ntok;
    p->ntok++;
    return idx;
}

static bool hex4(const char *s, uint32_t *out)
{
    uint32_t v = 0u;
    for (int i = 0; i < 4; i++) {
        const char c = s[i];
        uint32_t d;
        if ((c >= '0') && (c <= '9')) {
            d = (uint32_t)(c - '0');
        } else if ((c >= 'a') && (c <= 'f')) {
            d = (uint32_t)(c - 'a') + 10u;
        } else if ((c >= 'A') && (c <= 'F')) {
            d = (uint32_t)(c - 'A') + 10u;
        } else {
            return false;
        }
        v = (v << 4) | d;
    }
    *out = v;
    return true;
}

/* Decode one code point of string content starting at s[*i] (i < end). Handles raw UTF-8 and
 * backslash escapes including surrogate pairs. Returns false on any malformation. */
static bool next_cp(const char *s, size_t end, size_t *i, uint32_t *cp, rrc_json_err_t *err, bool escapes)
{
    const unsigned char c = (unsigned char)s[*i];
    if (escapes && (c == (unsigned char)'\\')) {
        if ((*i + 1u) >= end) {
            *err = RRC_JSON_ERR_SYNTAX;
            return false;
        }
        const char e = s[*i + 1u];
        *i += 2u;
        switch (e) {
        case '"': *cp = (uint32_t)'"'; return true;
        case '\\': *cp = (uint32_t)'\\'; return true;
        case '/': *cp = (uint32_t)'/'; return true;
        case 'b': *cp = 0x08u; return true;
        case 'f': *cp = 0x0Cu; return true;
        case 'n': *cp = 0x0Au; return true;
        case 'r': *cp = 0x0Du; return true;
        case 't': *cp = 0x09u; return true;
        case 'u': {
            uint32_t hi = 0u;
            if (((*i + 4u) > end) || !hex4(&s[*i], &hi)) {
                *err = RRC_JSON_ERR_SYNTAX;
                return false;
            }
            *i += 4u;
            if ((hi >= 0xDC00u) && (hi <= 0xDFFFu)) {
                *err = RRC_JSON_ERR_UTF8; /* lone low surrogate */
                return false;
            }
            if ((hi >= 0xD800u) && (hi <= 0xDBFFu)) {
                uint32_t lo = 0u;
                if (((*i + 6u) > end) || (s[*i] != '\\') || (s[*i + 1u] != 'u') || !hex4(&s[*i + 2u], &lo) ||
                    (lo < 0xDC00u) || (lo > 0xDFFFu)) {
                    *err = RRC_JSON_ERR_UTF8; /* unpaired high surrogate */
                    return false;
                }
                *i += 6u;
                *cp = 0x10000u + ((hi - 0xD800u) << 10) + (lo - 0xDC00u);
                return true;
            }
            *cp = hi;
            return true;
        }
        default:
            *err = RRC_JSON_ERR_SYNTAX;
            return false;
        }
    }
    if (escapes && (c < 0x20u)) {
        *err = RRC_JSON_ERR_SYNTAX; /* unescaped control character */
        return false;
    }
    if (c < 0x80u) {
        *cp = c;
        *i += 1u;
        return true;
    }
    /* Strict UTF-8: shortest form only, no surrogates, at most U+10FFFF. */
    uint32_t v;
    size_t n;
    uint32_t min;
    if ((c & 0xE0u) == 0xC0u) {
        v = c & 0x1Fu; n = 1u; min = 0x80u;
    } else if ((c & 0xF0u) == 0xE0u) {
        v = c & 0x0Fu; n = 2u; min = 0x800u;
    } else if ((c & 0xF8u) == 0xF0u) {
        v = c & 0x07u; n = 3u; min = 0x10000u;
    } else {
        *err = RRC_JSON_ERR_UTF8;
        return false;
    }
    if ((*i + n) >= end) { /* sequence would run past the end */
        *err = RRC_JSON_ERR_UTF8;
        return false;
    }
    for (size_t k = 1u; k <= n; k++) {
        const unsigned char cc = (unsigned char)s[*i + k];
        if ((cc & 0xC0u) != 0x80u) {
            *err = RRC_JSON_ERR_UTF8;
            return false;
        }
        v = (v << 6) | (cc & 0x3Fu);
    }
    if ((v < min) || (v > 0x10FFFFu) || ((v >= 0xD800u) && (v <= 0xDFFFu))) {
        *err = RRC_JSON_ERR_UTF8;
        return false;
    }
    *cp = v;
    *i += n + 1u;
    return true;
}

/* p->pos is at the opening quote. Validates the string and creates its token. */
static int parse_string(parser_t *p, int parent)
{
    const size_t start = p->pos + 1u;
    size_t i = start;
    bool escaped = false;
    for (;;) {
        if (i >= p->len) {
            p->pos = i;
            (void)fail(p, RRC_JSON_ERR_SYNTAX);
            return -1;
        }
        if (p->js[i] == '"') {
            break;
        }
        if (p->js[i] == '\\') {
            escaped = true;
        }
        uint32_t cp = 0u;
        rrc_json_err_t e = RRC_JSON_OK;
        /* The closing quote bounds the content; an escape can never run past p->len because
         * next_cp checks against the limit it is given. */
        if (!next_cp(p->js, p->len, &i, &cp, &e, true)) {
            p->pos = i;
            (void)fail(p, e);
            return -1;
        }
        if ((i - start) > (size_t)p->lim->max_string) {
            p->pos = i;
            (void)fail(p, RRC_JSON_ERR_STRING_LENGTH);
            return -1;
        }
    }
    const int t = new_tok(p, RRC_JT_STRING, parent, start);
    if (t < 0) {
        return -1;
    }
    p->tok[t].end = (uint32_t)i;
    if (escaped) {
        p->tok[t].flags |= RRC_JF_ESCAPED;
    }
    p->pos = i + 1u;
    return t;
}

static bool is_digit(char c)
{
    return (c >= '0') && (c <= '9');
}

static int parse_number(parser_t *p, int parent)
{
    const size_t start = p->pos;
    size_t i = start;
    bool integer = true;
    if ((i < p->len) && (p->js[i] == '-')) {
        i++;
    }
    if ((i >= p->len) || !is_digit(p->js[i])) {
        p->pos = i;
        (void)fail(p, RRC_JSON_ERR_SYNTAX);
        return -1;
    }
    if (p->js[i] == '0') {
        i++;
    } else {
        while ((i < p->len) && is_digit(p->js[i])) {
            i++;
        }
    }
    if ((i < p->len) && (p->js[i] == '.')) {
        integer = false;
        i++;
        if ((i >= p->len) || !is_digit(p->js[i])) {
            p->pos = i;
            (void)fail(p, RRC_JSON_ERR_SYNTAX);
            return -1;
        }
        while ((i < p->len) && is_digit(p->js[i])) {
            i++;
        }
    }
    if ((i < p->len) && ((p->js[i] == 'e') || (p->js[i] == 'E'))) {
        integer = false;
        i++;
        if ((i < p->len) && ((p->js[i] == '+') || (p->js[i] == '-'))) {
            i++;
        }
        if ((i >= p->len) || !is_digit(p->js[i])) {
            p->pos = i;
            (void)fail(p, RRC_JSON_ERR_SYNTAX);
            return -1;
        }
        while ((i < p->len) && is_digit(p->js[i])) {
            i++;
        }
    }
    const int t = new_tok(p, RRC_JT_NUMBER, parent, start);
    if (t < 0) {
        return -1;
    }
    p->tok[t].end = (uint32_t)i;
    if (integer) {
        p->tok[t].flags |= RRC_JF_INTEGER;
    }
    p->pos = i;
    return t;
}

static int parse_literal(parser_t *p, int parent, const char *word, rrc_jtype_t type)
{
    const size_t n = strlen(word);
    if (((p->len - p->pos) < n) || (memcmp(&p->js[p->pos], word, n) != 0)) {
        (void)fail(p, RRC_JSON_ERR_SYNTAX);
        return -1;
    }
    const int t = new_tok(p, type, parent, p->pos);
    if (t < 0) {
        return -1;
    }
    p->pos += n;
    p->tok[t].end = (uint32_t)p->pos;
    return t;
}

/* Compare the unescaped content of two string tokens. Both are already validated. */
static bool tok_str_equal(const parser_t *p, const rrc_jtok_t *a, const rrc_jtok_t *b)
{
    if (((a->flags | b->flags) & RRC_JF_ESCAPED) == 0u) {
        const size_t la = (size_t)a->end - (size_t)a->start;
        const size_t lb = (size_t)b->end - (size_t)b->start;
        return (la == lb) && (memcmp(&p->js[a->start], &p->js[b->start], la) == 0);
    }
    size_t ia = a->start;
    size_t ib = b->start;
    while ((ia < a->end) && (ib < b->end)) {
        uint32_t ca = 0u;
        uint32_t cb = 0u;
        rrc_json_err_t e = RRC_JSON_OK;
        if (!next_cp(p->js, a->end, &ia, &ca, &e, true) || !next_cp(p->js, b->end, &ib, &cb, &e, true)) {
            return false;
        }
        if (ca != cb) {
            return false;
        }
    }
    return (ia == a->end) && (ib == b->end);
}

static bool key_is_duplicate(const parser_t *p, int obj, int key)
{
    for (int i = obj + 1; i < key; i++) {
        const rrc_jtok_t *t = &p->tok[i];
        if (((int)t->parent == obj) && ((t->flags & RRC_JF_KEY) != 0u) && tok_str_equal(p, t, &p->tok[key])) {
            return true;
        }
    }
    return false;
}

/* Iterative parser: `cur` is the innermost open container (-1 at the root). */
static bool parse_document(parser_t *p)
{
    int cur = -1;
    uint16_t depth = 0u;
    bool want_value = true; /* a value (or, in an object, a key) is expected next */
    bool after_comma = false;

    for (;;) {
        skip_ws(p);
        if (p->pos >= p->len) {
            return fail(p, RRC_JSON_ERR_SYNTAX); /* document ended inside a value or container */
        }
        const char c = p->js[p->pos];

        if (!want_value) {
            /* After a value inside a container: ',' or the matching close. */
            rrc_jtok_t *ct = &p->tok[cur];
            if (c == ',') {
                p->pos++;
                want_value = true;
                after_comma = true;
                continue;
            }
            if (((c == '}') && (ct->type == (uint8_t)RRC_JT_OBJECT)) ||
                ((c == ']') && (ct->type == (uint8_t)RRC_JT_ARRAY))) {
                p->pos++;
                ct->end = (uint32_t)p->pos;
                cur = (int)ct->parent;
                depth--;
                if (cur < 0) {
                    return true;
                }
                continue;
            }
            return fail(p, RRC_JSON_ERR_SYNTAX);
        }

        /* Empty container closes immediately (not allowed after a comma). */
        if ((cur >= 0) && !after_comma && (p->tok[cur].size == 0u)) {
            rrc_jtok_t *ct = &p->tok[cur];
            if (((c == '}') && (ct->type == (uint8_t)RRC_JT_OBJECT)) ||
                ((c == ']') && (ct->type == (uint8_t)RRC_JT_ARRAY))) {
                p->pos++;
                ct->end = (uint32_t)p->pos;
                cur = (int)ct->parent;
                depth--;
                if (cur < 0) {
                    return true;
                }
                want_value = false;
                continue;
            }
        }
        after_comma = false;

        if ((cur >= 0) && (p->tok[cur].type == (uint8_t)RRC_JT_OBJECT)) {
            if (c != '"') {
                return fail(p, RRC_JSON_ERR_SYNTAX);
            }
            const int k = parse_string(p, cur);
            if (k < 0) {
                return false;
            }
            p->tok[k].flags |= RRC_JF_KEY;
            if (key_is_duplicate(p, cur, k)) {
                p->pos = p->tok[k].start;
                return fail(p, RRC_JSON_ERR_DUPLICATE_KEY);
            }
            skip_ws(p);
            if ((p->pos >= p->len) || (p->js[p->pos] != ':')) {
                return fail(p, RRC_JSON_ERR_SYNTAX);
            }
            p->pos++;
            skip_ws(p);
            if (p->pos >= p->len) {
                return fail(p, RRC_JSON_ERR_SYNTAX);
            }
        }
        if (cur >= 0) {
            if (p->tok[cur].size == UINT16_MAX) {
                return fail(p, RRC_JSON_ERR_TOKENS);
            }
            p->tok[cur].size++;
        }

        const char v = p->js[p->pos];
        int t;
        if ((v == '{') || (v == '[')) {
            if (depth >= p->lim->max_depth) {
                return fail(p, RRC_JSON_ERR_DEPTH);
            }
            t = new_tok(p, (v == '{') ? RRC_JT_OBJECT : RRC_JT_ARRAY, cur, p->pos);
            if (t < 0) {
                return false;
            }
            p->pos++;
            cur = t;
            depth++;
            want_value = true;
            continue;
        }
        if (v == '"') {
            t = parse_string(p, cur);
        } else if ((v == '-') || is_digit(v)) {
            t = parse_number(p, cur);
        } else if (v == 't') {
            t = parse_literal(p, cur, "true", RRC_JT_TRUE);
        } else if (v == 'f') {
            t = parse_literal(p, cur, "false", RRC_JT_FALSE);
        } else if (v == 'n') {
            t = parse_literal(p, cur, "null", RRC_JT_NULL);
        } else {
            return fail(p, RRC_JSON_ERR_SYNTAX);
        }
        if (t < 0) {
            return false;
        }
        if (cur < 0) {
            return true; /* scalar root */
        }
        want_value = false;
    }
}

rrc_json_err_t rrc_json_parse(rrc_json_t *doc, const char *js, size_t len, rrc_jtok_t *tok, uint16_t cap,
                              const rrc_json_limits_t *limits)
{
    if ((doc == NULL) || (js == NULL) || (tok == NULL) || (limits == NULL) || (cap == 0u) || (cap > (uint16_t)INT16_MAX) ||
        (len > (size_t)UINT32_MAX)) {
        return RRC_JSON_ERR_ARG;
    }
    parser_t p = {js, len, 0u, tok, cap, 0u, limits, RRC_JSON_OK};
    doc->js = js;
    doc->len = len;
    doc->tok = tok;
    doc->ntok = 0u;
    doc->error_offset = 0u;
    if (parse_document(&p)) {
        skip_ws(&p);
        if (p.pos != p.len) {
            p.err = RRC_JSON_ERR_TRAILING;
        }
    }
    if (p.err != RRC_JSON_OK) {
        doc->error_offset = p.pos;
        return p.err;
    }
    doc->ntok = p.ntok;
    return RRC_JSON_OK;
}

static const rrc_jtok_t *tok_at(const rrc_json_t *doc, int tok)
{
    if ((doc == NULL) || (tok < 0) || (tok >= (int)doc->ntok)) {
        return NULL;
    }
    return &doc->tok[tok];
}

rrc_jtype_t rrc_json_type(const rrc_json_t *doc, int tok)
{
    const rrc_jtok_t *t = tok_at(doc, tok);
    return (t == NULL) ? (rrc_jtype_t)0 : (rrc_jtype_t)t->type;
}

uint16_t rrc_json_size(const rrc_json_t *doc, int container)
{
    const rrc_jtok_t *t = tok_at(doc, container);
    if ((t == NULL) || ((t->type != (uint8_t)RRC_JT_OBJECT) && (t->type != (uint8_t)RRC_JT_ARRAY))) {
        return 0u;
    }
    return t->size;
}

bool rrc_json_str_eq(const rrc_json_t *doc, int tok, const char *s)
{
    const rrc_jtok_t *t = tok_at(doc, tok);
    if ((t == NULL) || (t->type != (uint8_t)RRC_JT_STRING)) {
        return false;
    }
    const size_t n = strlen(s);
    if ((t->flags & RRC_JF_ESCAPED) == 0u) {
        return (((size_t)t->end - (size_t)t->start) == n) && (memcmp(&doc->js[t->start], s, n) == 0);
    }
    /* Escaped token: compare code point by code point against the UTF-8 in s. */
    size_t i = t->start;
    size_t j = 0u;
    while ((i < t->end) && (j < n)) {
        uint32_t a = 0u;
        uint32_t b = 0u;
        rrc_json_err_t e = RRC_JSON_OK;
        if (!next_cp(doc->js, t->end, &i, &a, &e, true) || !next_cp(s, n, &j, &b, &e, false)) {
            return false;
        }
        if (a != b) {
            return false;
        }
    }
    return (i == t->end) && (j == n);
}

int rrc_json_get(const rrc_json_t *doc, int obj, const char *key)
{
    const rrc_jtok_t *o = tok_at(doc, obj);
    if ((o == NULL) || (o->type != (uint8_t)RRC_JT_OBJECT)) {
        return -1;
    }
    for (int i = obj + 1; (i + 1) < (int)doc->ntok; i++) {
        const rrc_jtok_t *t = &doc->tok[i];
        if (t->start >= o->end) {
            break;
        }
        if (((int)t->parent == obj) && ((t->flags & RRC_JF_KEY) != 0u) && rrc_json_str_eq(doc, i, key)) {
            return i + 1; /* the value always directly follows its key */
        }
    }
    return -1;
}

int rrc_json_at(const rrc_json_t *doc, int arr, uint16_t index)
{
    const rrc_jtok_t *a = tok_at(doc, arr);
    if ((a == NULL) || (a->type != (uint8_t)RRC_JT_ARRAY) || (index >= a->size)) {
        return -1;
    }
    uint16_t n = 0u;
    for (int i = arr + 1; (i < (int)doc->ntok) && (doc->tok[i].start < a->end); i++) {
        if ((int)doc->tok[i].parent == arr) {
            if (n == index) {
                return i;
            }
            n++;
        }
    }
    return -1;
}

bool rrc_json_to_u64(const rrc_json_t *doc, int tok, uint64_t *out)
{
    const rrc_jtok_t *t = tok_at(doc, tok);
    if ((t == NULL) || (t->type != (uint8_t)RRC_JT_NUMBER) || ((t->flags & RRC_JF_INTEGER) == 0u)) {
        return false;
    }
    size_t i = t->start;
    bool neg = false;
    if (doc->js[i] == '-') {
        neg = true;
        i++;
    }
    uint64_t v = 0u;
    for (; i < t->end; i++) {
        const uint64_t d = (uint64_t)(doc->js[i] - '0');
        if (v > ((UINT64_MAX - d) / 10u)) {
            return false;
        }
        v = (v * 10u) + d;
    }
    if (neg && (v != 0u)) {
        return false;
    }
    *out = v;
    return true;
}

bool rrc_json_to_i64(const rrc_json_t *doc, int tok, int64_t *out)
{
    const rrc_jtok_t *t = tok_at(doc, tok);
    if ((t == NULL) || (t->type != (uint8_t)RRC_JT_NUMBER) || ((t->flags & RRC_JF_INTEGER) == 0u)) {
        return false;
    }
    size_t i = t->start;
    bool neg = false;
    if (doc->js[i] == '-') {
        neg = true;
        i++;
    }
    uint64_t v = 0u;
    const uint64_t limit = neg ? ((uint64_t)INT64_MAX + 1u) : (uint64_t)INT64_MAX;
    for (; i < t->end; i++) {
        const uint64_t d = (uint64_t)(doc->js[i] - '0');
        if (v > ((limit - d) / 10u)) {
            return false;
        }
        v = (v * 10u) + d;
    }
    if (neg) {
        *out = (v == ((uint64_t)INT64_MAX + 1u)) ? INT64_MIN : -(int64_t)v;
    } else {
        *out = (int64_t)v;
    }
    return true;
}

bool rrc_json_to_bool(const rrc_json_t *doc, int tok, bool *out)
{
    const rrc_jtype_t ty = rrc_json_type(doc, tok);
    if (ty == RRC_JT_TRUE) {
        *out = true;
        return true;
    }
    if (ty == RRC_JT_FALSE) {
        *out = false;
        return true;
    }
    return false;
}

bool rrc_json_is_null(const rrc_json_t *doc, int tok)
{
    return rrc_json_type(doc, tok) == RRC_JT_NULL;
}

static size_t utf8_put(uint32_t cp, char out[4])
{
    if (cp < 0x80u) {
        out[0] = (char)cp;
        return 1u;
    }
    if (cp < 0x800u) {
        out[0] = (char)(0xC0u | (cp >> 6));
        out[1] = (char)(0x80u | (cp & 0x3Fu));
        return 2u;
    }
    if (cp < 0x10000u) {
        out[0] = (char)(0xE0u | (cp >> 12));
        out[1] = (char)(0x80u | ((cp >> 6) & 0x3Fu));
        out[2] = (char)(0x80u | (cp & 0x3Fu));
        return 3u;
    }
    out[0] = (char)(0xF0u | (cp >> 18));
    out[1] = (char)(0x80u | ((cp >> 12) & 0x3Fu));
    out[2] = (char)(0x80u | ((cp >> 6) & 0x3Fu));
    out[3] = (char)(0x80u | (cp & 0x3Fu));
    return 4u;
}

int rrc_json_str_copy(const rrc_json_t *doc, int tok, char *out, size_t cap)
{
    const rrc_jtok_t *t = tok_at(doc, tok);
    if ((t == NULL) || (t->type != (uint8_t)RRC_JT_STRING) || (out == NULL) || (cap == 0u)) {
        return -1;
    }
    size_t n = 0u;
    size_t i = t->start;
    while (i < t->end) {
        uint32_t cp = 0u;
        rrc_json_err_t e = RRC_JSON_OK;
        char u[4];
        if (!next_cp(doc->js, t->end, &i, &cp, &e, true)) {
            return -1;
        }
        const size_t k = utf8_put(cp, u);
        if ((n + k) >= cap) {
            return -1;
        }
        memcpy(&out[n], u, k);
        n += k;
    }
    out[n] = '\0';
    return (int)n;
}

const char *rrc_json_raw(const rrc_json_t *doc, int tok, size_t *len)
{
    const rrc_jtok_t *t = tok_at(doc, tok);
    if (t == NULL) {
        return NULL;
    }
    if (len != NULL) {
        *len = (size_t)t->end - (size_t)t->start;
    }
    return &doc->js[t->start];
}
