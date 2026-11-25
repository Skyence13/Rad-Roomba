/* Command-line bridge used by tests/test_interop.py to compare this library with the baseline
 * Python tools byte for byte.
 *
 *   rrc_codec_tool check     stdin: wire lines        stdout: "OK" or "ERR <reason>" per line
 *   rrc_codec_tool reencode  stdin: wire lines        stdout: the record parsed, re-serialised with
 *                                                     the writer and re-framed ("!" LF if rejected)
 *   rrc_codec_tool digest    stdin: hex per line      stdout: "<sha256 hex> <base64> <crc32 hex>"
 *   rrc_codec_tool b64dec    stdin: base64 per line   stdout: hex of the decoded bytes or "ERR"
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rr_common.h"

#define MAX_LINE 20000u
#define MAX_TOK 8192u

static uint8_t g_line[MAX_LINE];
static uint8_t g_out[MAX_LINE];
static rrc_jtok_t g_tok[MAX_TOK];
static const rrc_json_limits_t k_lim = {64u, 8192u};

static const char *frame_err(rrc_frame_err_t e)
{
    switch (e) {
    case RRC_FRAME_ERR_OVERSIZE: return "oversize";
    case RRC_FRAME_ERR_DELIMITER: return "delimiter";
    case RRC_FRAME_ERR_CRC_FORMAT: return "crc-format";
    case RRC_FRAME_ERR_CRC_MISMATCH: return "crc-mismatch";
    default: return "ok";
    }
}

static const char *json_err(rrc_json_err_t e)
{
    switch (e) {
    case RRC_JSON_ERR_SYNTAX: return "json-syntax";
    case RRC_JSON_ERR_UTF8: return "json-utf8";
    case RRC_JSON_ERR_DEPTH: return "json-depth";
    case RRC_JSON_ERR_TOKENS: return "json-tokens";
    case RRC_JSON_ERR_STRING_LENGTH: return "json-string-length";
    case RRC_JSON_ERR_DUPLICATE_KEY: return "json-duplicate-key";
    case RRC_JSON_ERR_TRAILING: return "json-trailing";
    default: return "json-arg";
    }
}

/* Re-emit token `t` and everything below it; returns the index after the subtree. */
static int emit(const rrc_json_t *d, rrc_jw_t *w, int t)
{
    static char str[8200];
    const rrc_jtype_t ty = rrc_json_type(d, t);
    size_t n = 0u;
    const char *raw = rrc_json_raw(d, t, &n);
    int next = t + 1;
    switch (ty) {
    case RRC_JT_OBJECT: {
        const uint16_t members = rrc_json_size(d, t);
        rrc_jw_obj_begin(w);
        for (uint16_t i = 0u; i < members; i++) {
            if (rrc_json_str_copy(d, next, str, sizeof str) < 0) {
                w->error = true;
                return next;
            }
            rrc_jw_key(w, str);
            next = emit(d, w, next + 1);
        }
        rrc_jw_obj_end(w);
        break;
    }
    case RRC_JT_ARRAY: {
        const uint16_t elems = rrc_json_size(d, t);
        rrc_jw_arr_begin(w);
        for (uint16_t i = 0u; i < elems; i++) {
            next = emit(d, w, next);
        }
        rrc_jw_arr_end(w);
        break;
    }
    case RRC_JT_STRING: {
        const int len = rrc_json_str_copy(d, t, str, sizeof str);
        if (len < 0) {
            w->error = true;
        } else {
            rrc_jw_strn(w, str, (size_t)len);
        }
        break;
    }
    default:
        rrc_jw_raw(w, raw, n);
        break;
    }
    return next;
}

static int read_line(size_t *len)
{
    size_t n = 0u;
    int c;
    while ((c = getchar()) != EOF) {
        if (n < MAX_LINE) {
            g_line[n] = (uint8_t)c;
        }
        n++;
        if (c == '\n') {
            break;
        }
    }
    *len = n;
    return (n == 0u) ? 0 : 1;
}

static int mode_wire(int reencode)
{
    size_t len;
    while (read_line(&len) != 0) {
        size_t jl = 0u;
        uint32_t crc = 0u;
        const rrc_frame_err_t fe =
            (len > MAX_LINE) ? RRC_FRAME_ERR_OVERSIZE : rrc_frame_check(g_line, len, RRC_HEAD_MAX_RECORD, &jl, &crc);
        rrc_json_t doc;
        rrc_json_err_t je = RRC_JSON_OK;
        if (fe == RRC_FRAME_OK) {
            je = rrc_json_parse(&doc, (const char *)g_line, jl, g_tok, MAX_TOK, &k_lim);
            if ((je == RRC_JSON_OK) && (rrc_json_type(&doc, 0) != RRC_JT_OBJECT)) {
                je = RRC_JSON_ERR_ARG; /* the wire carries exactly one JSON object */
            }
        }
        if (reencode == 0) {
            if (fe != RRC_FRAME_OK) {
                printf("ERR %s\n", frame_err(fe));
            } else if (je != RRC_JSON_OK) {
                printf("ERR %s\n", (je == RRC_JSON_ERR_ARG) ? "json-not-object" : json_err(je));
            } else {
                printf("OK\n");
            }
            continue;
        }
        size_t total = 0u;
        if ((fe == RRC_FRAME_OK) && (je == RRC_JSON_OK)) {
            rrc_jw_t w;
            rrc_jw_init(&w, (char *)g_out, sizeof g_out);
            (void)emit(&doc, &w, 0);
            if (rrc_jw_ok(&w)) {
                total = rrc_frame_finish(g_out, rrc_jw_len(&w), sizeof g_out, RRC_HEAD_MAX_RECORD);
            }
        }
        if (total == 0u) {
            fputs("!\n", stdout);
        } else {
            fwrite(g_out, 1u, total, stdout);
        }
    }
    return 0;
}

static int hexval(int c)
{
    if ((c >= '0') && (c <= '9')) { return c - '0'; }
    if ((c >= 'a') && (c <= 'f')) { return c - 'a' + 10; }
    return -1;
}

static int mode_digest(void)
{
    size_t len;
    while (read_line(&len) != 0) {
        size_t n = 0u;
        for (size_t i = 0u; (i + 1u) < len; i += 2u) {
            const int hi = hexval(g_line[i]);
            const int lo = hexval(g_line[i + 1u]);
            if ((hi < 0) || (lo < 0)) {
                break;
            }
            g_out[n++] = (uint8_t)((hi << 4) | lo);
        }
        uint8_t dg[RRC_SHA256_LEN];
        char hex[RRC_SHA256_HEX_LEN + 1u];
        static char b64[MAX_LINE];
        rrc_sha256(g_out, n, dg);
        rrc_hex_lower(dg, sizeof dg, hex);
        const size_t bl = rrc_base64_encode(g_out, n, b64, sizeof b64 - 1u);
        b64[bl] = '\0';
        printf("%s %s %08X\n", hex, b64, (unsigned)rrc_crc32(g_out, n));
    }
    return 0;
}

static int mode_b64dec(void)
{
    size_t len;
    while (read_line(&len) != 0) {
        const size_t n = ((len > 0u) && (g_line[len - 1u] == (uint8_t)'\n')) ? (len - 1u) : len;
        const long m = rrc_base64_decode((const char *)g_line, n, g_out, sizeof g_out);
        if (m < 0) {
            puts("ERR");
        } else {
            for (long i = 0; i < m; i++) {
                printf("%02x", g_out[i]);
            }
            putchar('\n');
        }
    }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "usage: %s check|reencode|digest|b64dec\n", argv[0]);
        return 2;
    }
    if (strcmp(argv[1], "check") == 0) { return mode_wire(0); }
    if (strcmp(argv[1], "reencode") == 0) { return mode_wire(1); }
    if (strcmp(argv[1], "digest") == 0) { return mode_digest(); }
    if (strcmp(argv[1], "b64dec") == 0) { return mode_b64dec(); }
    return 2;
}
