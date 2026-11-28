/* Host unit tests for firmware/common. Build and run: see firmware/common/README.md. */
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "rr_common.h"
#include "rrc_test.h"

/* ------------------------------------------------------------------ CRC-32 */
static void test_crc32_check_value(void)
{
    CHECK(rrc_crc32((const uint8_t *)"123456789", 9u) == 0xCBF43926u);
    CHECK(rrc_crc32((const uint8_t *)"", 0u) == 0u);
    uint32_t c = rrc_crc32_update(0u, (const uint8_t *)"1234", 4u);
    c = rrc_crc32_update(c, (const uint8_t *)"56789", 5u);
    CHECK(c == 0xCBF43926u);
}

/* ------------------------------------------------------------------ framing */
static size_t make_line(uint8_t *buf, size_t cap, const char *json)
{
    const size_t n = strlen(json);
    memcpy(buf, json, n);
    return rrc_frame_finish(buf, n, cap, RRC_HEAD_MAX_RECORD);
}

static void test_frame_finish_and_check(void)
{
    uint8_t buf[64];
    const size_t n = make_line(buf, sizeof buf, "123456789");
    CHECK(n == 19u);
    CHECK(memcmp(buf, "123456789\tCBF43926\n", 19u) == 0);
    size_t jl = 0u;
    uint32_t crc = 0u;
    CHECK(rrc_frame_check(buf, n, RRC_HEAD_MAX_RECORD, &jl, &crc) == RRC_FRAME_OK);
    CHECK(jl == 9u);
    CHECK(crc == 0xCBF43926u);
    /* refuses TAB/CR/LF inside the JSON part, and too-small buffers */
    uint8_t bad[32] = "a\tb";
    CHECK(rrc_frame_finish(bad, 3u, sizeof bad, RRC_HEAD_MAX_RECORD) == 0u);
    bad[1] = (uint8_t)'\r';
    CHECK(rrc_frame_finish(bad, 3u, sizeof bad, RRC_HEAD_MAX_RECORD) == 0u);
    bad[1] = (uint8_t)'\n';
    CHECK(rrc_frame_finish(bad, 3u, sizeof bad, RRC_HEAD_MAX_RECORD) == 0u);
    bad[1] = (uint8_t)'x';
    CHECK(rrc_frame_finish(bad, 3u, 12u, RRC_HEAD_MAX_RECORD) == 0u);
    CHECK(rrc_frame_finish(bad, 3u, 13u, RRC_HEAD_MAX_RECORD) == 13u);
    CHECK(rrc_frame_finish(bad, 3u, sizeof bad, 12u) == 0u);
}

static void test_frame_check_rejects(void)
{
    uint8_t buf[64];
    size_t n = make_line(buf, sizeof buf, "{\"a\":1}");
    size_t jl;
    uint32_t crc;
    CHECK(rrc_frame_check(buf, n, 8192u, &jl, &crc) == RRC_FRAME_OK);
    CHECK(rrc_frame_check(buf, n - 1u, 8192u, &jl, &crc) != RRC_FRAME_OK); /* missing LF */
    buf[0] ^= 1u;
    CHECK(rrc_frame_check(buf, n, 8192u, &jl, &crc) == RRC_FRAME_ERR_CRC_MISMATCH);
    buf[0] ^= 1u;
    /* lowercase hex is not a valid CRC field */
    for (size_t i = 0; i < 8u; i++) {
        uint8_t *c = &buf[jl + 1u + i];
        if ((*c >= (uint8_t)'A') && (*c <= (uint8_t)'F')) {
            *c = (uint8_t)(*c + 32u);
            CHECK(rrc_frame_check(buf, n, 8192u, &jl, &crc) == RRC_FRAME_ERR_CRC_FORMAT);
            *c = (uint8_t)(*c - 32u);
        }
    }
    /* two TABs */
    uint8_t two[64];
    memcpy(two, buf, jl);
    two[jl] = (uint8_t)'\t';
    memcpy(&two[jl + 1u], &buf[jl], n - jl);
    CHECK(rrc_frame_check(two, n + 1u, 8192u, &jl, &crc) == RRC_FRAME_ERR_DELIMITER);
    /* CR inside the JSON part */
    n = make_line(buf, sizeof buf, "{\"a\":1}");
    buf[3] = (uint8_t)'\r';
    CHECK(rrc_frame_check(buf, n, 8192u, &jl, &crc) == RRC_FRAME_ERR_DELIMITER);
    /* shorter than a trailer */
    CHECK(rrc_frame_check((const uint8_t *)"\tAAAAAAA\n", 9u, 8192u, &jl, &crc) == RRC_FRAME_ERR_DELIMITER);
    /* empty JSON with a correct CRC passes framing (the JSON layer rejects it) */
    CHECK(rrc_frame_check((const uint8_t *)"\t00000000\n", 10u, 8192u, &jl, &crc) == RRC_FRAME_OK);
    CHECK(jl == 0u);
}

static void test_frame_rx_stream(void)
{
    static uint8_t rxbuf[64];
    rrc_frame_rx_t rx;
    rrc_frame_rx_init(&rx, rxbuf, sizeof rxbuf);
    uint8_t line[64];
    const size_t n = make_line(line, sizeof line, "{\"k\":true}");
    size_t jl = 0u;
    uint32_t crc = 0u;
    /* two records back to back, the first preceded by garbage that ends in LF */
    const char *garbage = "noise without trailer\n";
    for (size_t i = 0; i < strlen(garbage); i++) {
        const rrc_rx_result_t r = rrc_frame_rx_push(&rx, (uint8_t)garbage[i], &jl, &crc);
        CHECK((i + 1u < strlen(garbage)) ? (r == RRC_RX_NONE) : (r == RRC_RX_DISCARDED));
    }
    for (int rep = 0; rep < 2; rep++) {
        for (size_t i = 0; i < n; i++) {
            const rrc_rx_result_t r = rrc_frame_rx_push(&rx, line[i], &jl, &crc);
            if (i + 1u < n) {
                CHECK(r == RRC_RX_NONE);
                CHECK(rrc_frame_rx_busy(&rx));
            } else {
                CHECK(r == RRC_RX_RECORD);
                CHECK(jl == 10u);
                CHECK(memcmp(rxbuf, "{\"k\":true}", 10u) == 0);
                CHECK(!rrc_frame_rx_busy(&rx));
            }
        }
    }
    CHECK(rx.n_records == 2u);
    CHECK(rx.n_discarded == 1u);
    /* timeout in the middle of a record: reset, then a clean record is accepted */
    for (size_t i = 0; i < 5u; i++) {
        (void)rrc_frame_rx_push(&rx, line[i], &jl, &crc);
    }
    rrc_frame_rx_reset(&rx);
    CHECK(!rrc_frame_rx_busy(&rx));
    rrc_rx_result_t r = RRC_RX_NONE;
    for (size_t i = 0; i < n; i++) {
        r = rrc_frame_rx_push(&rx, line[i], &jl, &crc);
    }
    CHECK(r == RRC_RX_RECORD);
}

static void test_frame_rx_oversize(void)
{
    static uint8_t rxbuf[32];
    rrc_frame_rx_t rx;
    rrc_frame_rx_init(&rx, rxbuf, sizeof rxbuf); /* max record 32 bytes */
    size_t jl = 0u;
    uint32_t crc = 0u;
    /* exactly 32 bytes including the trailer is accepted */
    uint8_t line[64];
    size_t n = make_line(line, sizeof line, "{\"abcdefghijklmnop\":1}"); /* 22 + 10 = 32 */
    CHECK(n == 32u);
    rrc_rx_result_t r = RRC_RX_NONE;
    for (size_t i = 0; i < n; i++) {
        r = rrc_frame_rx_push(&rx, line[i], &jl, &crc);
    }
    CHECK(r == RRC_RX_RECORD);
    /* 33 bytes: discarded through the LF, and the next good record is still received */
    uint8_t big[64];
    memcpy(big, "{\"abcdefghijklmnopq\":1}", 23u);
    const uint32_t c = rrc_crc32(big, 23u);
    static const char hex[] = "0123456789ABCDEF";
    big[23] = (uint8_t)'\t';
    for (uint32_t i = 0; i < 8u; i++) {
        big[24u + i] = (uint8_t)hex[(c >> (28u - 4u * i)) & 0xFu];
    }
    big[32] = (uint8_t)'\n';
    for (size_t i = 0; i < 33u; i++) {
        r = rrc_frame_rx_push(&rx, big[i], &jl, &crc);
    }
    CHECK(r == RRC_RX_DISCARDED);
    CHECK(rx.last_error == RRC_FRAME_ERR_OVERSIZE);
    /* a very long line without LF, then LF, then a good record */
    for (int i = 0; i < 1000; i++) {
        r = rrc_frame_rx_push(&rx, (uint8_t)'x', &jl, &crc);
        CHECK(r == RRC_RX_NONE);
    }
    CHECK(rrc_frame_rx_busy(&rx));
    r = rrc_frame_rx_push(&rx, (uint8_t)'\n', &jl, &crc);
    CHECK(r == RRC_RX_DISCARDED);
    for (size_t i = 0; i < n; i++) {
        r = rrc_frame_rx_push(&rx, line[i], &jl, &crc);
    }
    CHECK(r == RRC_RX_RECORD);
}

/* ------------------------------------------------------------------ JSON writer */
static void test_writer_basic(void)
{
    char buf[256];
    rrc_jw_t w;
    rrc_jw_init(&w, buf, sizeof buf);
    rrc_jw_obj_begin(&w);
    rrc_jw_kstr(&w, "s", "a\"b\\c\n\t\x01");
    rrc_jw_ki64(&w, "n", -42);
    rrc_jw_ku64(&w, "u", 18446744073709551615uLL);
    rrc_jw_ki64(&w, "min", INT64_MIN);
    rrc_jw_kbool(&w, "t", true);
    rrc_jw_knull(&w, "z");
    rrc_jw_key(&w, "a");
    rrc_jw_arr_begin(&w);
    rrc_jw_i64(&w, 1);
    rrc_jw_arr_begin(&w);
    rrc_jw_arr_end(&w);
    rrc_jw_obj_begin(&w);
    rrc_jw_obj_end(&w);
    rrc_jw_arr_end(&w);
    rrc_jw_obj_end(&w);
    CHECK(rrc_jw_ok(&w));
    buf[rrc_jw_len(&w)] = '\0';
    CHECK_STR(buf, "{\"s\":\"a\\\"b\\\\c\\n\\t\\u0001\",\"n\":-42,\"u\":18446744073709551615,"
                   "\"min\":-9223372036854775808,\"t\":true,\"z\":null,\"a\":[1,[],{}]}");
}

static void fixed(char *out, size_t cap, int64_t v, uint8_t dec, bool trim)
{
    rrc_jw_t w;
    rrc_jw_init(&w, out, cap - 1u);
    rrc_jw_fixed(&w, v, dec, trim);
    out[rrc_jw_ok(&w) ? rrc_jw_len(&w) : 0u] = '\0';
}

static void test_writer_fixed(void)
{
    char b[40];
    fixed(b, sizeof b, 82, 1, false);       CHECK_STR(b, "8.2");
    fixed(b, sizeof b, -3, 1, false);       CHECK_STR(b, "-0.3");
    fixed(b, sizeof b, 0, 1, false);        CHECK_STR(b, "0.0");
    fixed(b, sizeof b, 200, 1, false);      CHECK_STR(b, "20.0");
    fixed(b, sizeof b, 131250, 6, true);    CHECK_STR(b, "0.13125");
    fixed(b, sizeof b, -175000, 6, true);   CHECK_STR(b, "-0.175");
    fixed(b, sizeof b, 300, 6, true);       CHECK_STR(b, "0.0003");
    fixed(b, sizeof b, -1000000, 6, true);  CHECK_STR(b, "-1");
    fixed(b, sizeof b, 0, 6, true);         CHECK_STR(b, "0");
    fixed(b, sizeof b, 10000, 6, true);     CHECK_STR(b, "0.01");
    fixed(b, sizeof b, 15, 0, false);       CHECK_STR(b, "15");
    fixed(b, sizeof b, 1, 10, false);       CHECK_STR(b, ""); /* decimals > 9 is an error */
}

static void test_writer_overflow_and_misuse(void)
{
    char buf[16];
    rrc_jw_t w;
    rrc_jw_init(&w, buf, sizeof buf);
    rrc_jw_obj_begin(&w);
    rrc_jw_kstr(&w, "key", "this string does not fit");
    rrc_jw_obj_end(&w);
    CHECK(!rrc_jw_ok(&w));
    CHECK(rrc_jw_len(&w) <= sizeof buf);
    /* value without key inside an object */
    rrc_jw_init(&w, buf, sizeof buf);
    rrc_jw_obj_begin(&w);
    rrc_jw_i64(&w, 1);
    CHECK(!rrc_jw_ok(&w));
    /* unbalanced */
    rrc_jw_init(&w, buf, sizeof buf);
    rrc_jw_arr_begin(&w);
    CHECK(!rrc_jw_ok(&w));
    rrc_jw_obj_end(&w);
    CHECK(!rrc_jw_ok(&w));
    /* two top-level values */
    rrc_jw_init(&w, buf, sizeof buf);
    rrc_jw_i64(&w, 1);
    rrc_jw_i64(&w, 2);
    CHECK(!rrc_jw_ok(&w));
    /* depth limit */
    char deep[64];
    rrc_jw_init(&w, deep, sizeof deep);
    for (unsigned i = 0; i < RRC_JW_MAX_DEPTH + 1u; i++) {
        rrc_jw_arr_begin(&w);
    }
    CHECK(!rrc_jw_ok(&w));
}

/* ------------------------------------------------------------------ JSON reader */
static const rrc_json_limits_t k_lim = {8u, 256u};

static rrc_json_err_t parse(rrc_json_t *doc, const char *s)
{
    static rrc_jtok_t tok[64];
    return rrc_json_parse(doc, s, strlen(s), tok, 64u, &k_lim);
}

static void test_reader_valid(void)
{
    rrc_json_t d;
    CHECK(parse(&d, "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":4294967295,\"op\":\"READ\",\"args\":{\"after_seq\":-1}}") ==
          RRC_JSON_OK);
    CHECK(rrc_json_type(&d, 0) == RRC_JT_OBJECT);
    CHECK(rrc_json_size(&d, 0) == 5u);
    uint64_t u = 0;
    CHECK(rrc_json_to_u64(&d, rrc_json_get(&d, 0, "id"), &u) && (u == 4294967295u));
    const int args = rrc_json_get(&d, 0, "args");
    int64_t i = 0;
    CHECK(rrc_json_to_i64(&d, rrc_json_get(&d, args, "after_seq"), &i) && (i == -1));
    CHECK(rrc_json_str_eq(&d, rrc_json_get(&d, 0, "op"), "READ"));
    CHECK(!rrc_json_str_eq(&d, rrc_json_get(&d, 0, "op"), "REA"));
    CHECK(rrc_json_get(&d, 0, "missing") == -1);
    CHECK(rrc_json_get(&d, args, "id") == -1); /* lookups do not leak across nesting levels */

    CHECK(parse(&d, " { \"a\" : [ 1 , 2.5 , -0 , 1e3 , true , false , null , \"x\" , { } , [ ] ] } ") == RRC_JSON_OK);
    const int a = rrc_json_get(&d, 0, "a");
    CHECK(rrc_json_size(&d, a) == 10u);
    CHECK(rrc_json_to_i64(&d, rrc_json_at(&d, a, 0), &i) && (i == 1));
    CHECK(!rrc_json_to_i64(&d, rrc_json_at(&d, a, 1), &i)); /* fraction is not an integer */
    CHECK(rrc_json_to_i64(&d, rrc_json_at(&d, a, 2), &i) && (i == 0));
    CHECK(!rrc_json_to_i64(&d, rrc_json_at(&d, a, 3), &i)); /* exponent is not an integer */
    bool b = false;
    CHECK(rrc_json_to_bool(&d, rrc_json_at(&d, a, 4), &b) && b);
    CHECK(rrc_json_to_bool(&d, rrc_json_at(&d, a, 5), &b) && !b);
    CHECK(rrc_json_is_null(&d, rrc_json_at(&d, a, 6)));
    CHECK(rrc_json_type(&d, rrc_json_at(&d, a, 8)) == RRC_JT_OBJECT);
    CHECK(rrc_json_type(&d, rrc_json_at(&d, a, 9)) == RRC_JT_ARRAY);
    CHECK(rrc_json_at(&d, a, 10) == -1);
    /* scalar roots are valid JSON */
    CHECK(parse(&d, "42") == RRC_JSON_OK);
    CHECK(parse(&d, "\"s\"") == RRC_JSON_OK);
    CHECK(parse(&d, "null") == RRC_JSON_OK);
}

static void test_reader_integer_limits(void)
{
    rrc_json_t d;
    int64_t i = 0;
    uint64_t u = 0;
    CHECK(parse(&d, "[9223372036854775807,-9223372036854775808,9223372036854775808,18446744073709551615,"
                    "18446744073709551616,-1]") == RRC_JSON_OK);
    CHECK(rrc_json_to_i64(&d, rrc_json_at(&d, 0, 0), &i) && (i == INT64_MAX));
    CHECK(rrc_json_to_i64(&d, rrc_json_at(&d, 0, 1), &i) && (i == INT64_MIN));
    CHECK(!rrc_json_to_i64(&d, rrc_json_at(&d, 0, 2), &i));
    CHECK(rrc_json_to_u64(&d, rrc_json_at(&d, 0, 3), &u) && (u == UINT64_MAX));
    CHECK(!rrc_json_to_u64(&d, rrc_json_at(&d, 0, 4), &u));
    CHECK(!rrc_json_to_u64(&d, rrc_json_at(&d, 0, 5), &u));
}

static void test_reader_strings(void)
{
    rrc_json_t d;
    char out[64];
    CHECK(parse(&d, "{\"k\":\"a\\n\\u00e9\\ud83d\\ude00\\/\\\"\"}") == RRC_JSON_OK);
    const int v = rrc_json_get(&d, 0, "k");
    CHECK(rrc_json_str_copy(&d, v, out, sizeof out) == 10);
    CHECK(memcmp(out, "a\n\xC3\xA9\xF0\x9F\x98\x80/\"", 10u) == 0);
    CHECK(rrc_json_str_eq(&d, v, "a\n\xC3\xA9\xF0\x9F\x98\x80/\""));
    CHECK(rrc_json_str_copy(&d, v, out, 10u) == -1); /* needs 11 bytes with the NUL */
    /* escaped key is found by its unescaped name */
    CHECK(parse(&d, "{\"\\u0061b\":7}") == RRC_JSON_OK);
    int64_t i = 0;
    CHECK(rrc_json_to_i64(&d, rrc_json_get(&d, 0, "ab"), &i) && (i == 7));
    /* raw UTF-8 passes */
    CHECK(parse(&d, "{\"k\":\"\xE2\x82\xAC\"}") == RRC_JSON_OK);
}

static void test_reader_rejects(void)
{
    rrc_json_t d;
    static const char *const bad[] = {
        "", " ", "{", "}", "[1,]", "{,}", "{\"a\":1,}", "{\"a\"}", "{\"a\":}", "{a:1}", "{'a':1}",
        "[1 2]", "01", "-", "+1", ".5", "1.", "1e", "1e+", "0x10", "NaN", "Infinity", "-Infinity",
        "nul", "tru", "True", "\"abc", "\"a\\x\"", "\"\\u12\"", "\"\\u12G4\"", "\"a\tb\"", "\"a\x01\"",
        "[1]]", "{}{}", "{} x", "[\"a\":1]", "{\"a\":1 \"b\":2}", "{1:2}", "[,1]", "\"\\ud800\"",
        "\"\\udc00\"", "\"\\ud800\\u0041\"", "\"\xC0\x80\"", "\"\xED\xA0\x80\"", "\"\xF4\x90\x80\x80\"",
        "\"\xE2\x82\"", "\"\x80\"", "\"\xFF\""};
    for (size_t i = 0; i < sizeof bad / sizeof bad[0]; i++) {
        const rrc_json_err_t e = parse(&d, bad[i]);
        if (e == RRC_JSON_OK) {
            printf("  accepted invalid JSON #%zu: %s\n", i, bad[i]);
        }
        CHECK(e != RRC_JSON_OK);
    }
    CHECK(parse(&d, "{} x") == RRC_JSON_ERR_TRAILING);
    CHECK(parse(&d, "\"\xC0\x80\"") == RRC_JSON_ERR_UTF8);
}

static void test_reader_duplicate_keys(void)
{
    rrc_json_t d;
    CHECK(parse(&d, "{\"a\":1,\"a\":2}") == RRC_JSON_ERR_DUPLICATE_KEY);
    CHECK(parse(&d, "{\"a\":1,\"b\":{\"x\":1,\"x\":2}}") == RRC_JSON_ERR_DUPLICATE_KEY);
    CHECK(parse(&d, "{\"a\":1,\"\\u0061\":2}") == RRC_JSON_ERR_DUPLICATE_KEY); /* same key after unescaping */
    CHECK(parse(&d, "[{\"a\":1},{\"a\":2}]") == RRC_JSON_OK);                   /* different objects */
    CHECK(parse(&d, "{\"a\":{\"a\":{\"a\":1}}}") == RRC_JSON_OK);               /* same name at different levels */
    CHECK(parse(&d, "{\"a\":1,\"A\":2,\"aa\":3}") == RRC_JSON_OK);
}

static void test_reader_limits(void)
{
    rrc_json_t d;
    CHECK(parse(&d, "[[[[[[[[1]]]]]]]]") == RRC_JSON_OK);          /* depth 8 */
    CHECK(parse(&d, "[[[[[[[[[1]]]]]]]]]") == RRC_JSON_ERR_DEPTH); /* depth 9 */
    char s[300];
    s[0] = '"';
    memset(&s[1], 'a', 256u);
    s[257] = '"';
    s[258] = '\0';
    CHECK(parse(&d, s) == RRC_JSON_OK);
    memset(&s[1], 'a', 257u);
    s[258] = '"';
    s[259] = '\0';
    CHECK(parse(&d, s) == RRC_JSON_ERR_STRING_LENGTH);
    /* token budget: 64 tokens available, array of 63 numbers fits, 64 does not */
    char big[400];
    size_t n = 0;
    big[n++] = '[';
    for (int i = 0; i < 63; i++) {
        if (i != 0) {
            big[n++] = ',';
        }
        big[n++] = '1';
    }
    big[n++] = ']';
    big[n] = '\0';
    CHECK(parse(&d, big) == RRC_JSON_OK);
    big[n - 1u] = ',';
    big[n++] = '1';
    big[n++] = ']';
    big[n] = '\0';
    CHECK(parse(&d, big) == RRC_JSON_ERR_TOKENS);
    rrc_jtok_t t[1];
    CHECK(rrc_json_parse(&d, "1", 1u, t, 0u, &k_lim) == RRC_JSON_ERR_ARG);
}

/* ------------------------------------------------------------------ envelope + cache */
static void test_envelope_request(void)
{
    rrc_json_t d;
    rrc_req_t r;
    CHECK(parse(&d, "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":7,\"op\":\"TIME\",\"args\":{}}") == RRC_JSON_OK);
    CHECK(rrc_req_parse(&d, "2.0", &r) == RRC_REQ_OK);
    CHECK(r.id == 7u);
    CHECK(rrc_json_str_eq(&d, r.op, "TIME"));
    CHECK(rrc_json_type(&d, r.args) == RRC_JT_OBJECT);
    CHECK(rrc_req_parse(&d, "1.0", &r) == RRC_REQ_BAD_VERSION);
    CHECK(r.id == 7u);
    static const char *const invalid[] = {
        "[1]", "{\"type\":\"RSP\",\"v\":\"2.0\",\"id\":1,\"op\":\"X\",\"args\":{}}",
        "{\"v\":\"2.0\",\"id\":1,\"op\":\"X\",\"args\":{}}",
        "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":-1,\"op\":\"X\",\"args\":{}}",
        "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":4294967296,\"op\":\"X\",\"args\":{}}",
        "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":1.0,\"op\":\"X\",\"args\":{}}",
        "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":\"1\",\"op\":\"X\",\"args\":{}}",
        "{\"type\":\"REQ\",\"v\":\"2.0\",\"op\":\"X\",\"args\":{}}"};
    for (size_t i = 0; i < sizeof invalid / sizeof invalid[0]; i++) {
        CHECK(parse(&d, invalid[i]) == RRC_JSON_OK);
        CHECK(rrc_req_parse(&d, "2.0", &r) == RRC_REQ_INVALID);
    }
    static const char *const shape[] = {
        "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":1,\"op\":5,\"args\":{}}",
        "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":1,\"op\":\"X\",\"args\":[]}",
        "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":1,\"op\":\"X\"}", "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":1,\"args\":{}}"};
    for (size_t i = 0; i < sizeof shape / sizeof shape[0]; i++) {
        CHECK(parse(&d, shape[i]) == RRC_JSON_OK);
        CHECK(rrc_req_parse(&d, "2.0", &r) == RRC_REQ_BAD_SHAPE);
    }
    /* missing or non-string version with a usable id is a version problem, not garbage */
    CHECK(parse(&d, "{\"type\":\"REQ\",\"id\":3,\"op\":\"X\",\"args\":{}}") == RRC_JSON_OK);
    CHECK(rrc_req_parse(&d, "2.0", &r) == RRC_REQ_BAD_VERSION);
}

static void test_envelope_response_and_cache(void)
{
    char buf[128];
    rrc_jw_t w;
    rrc_jw_init(&w, buf, sizeof buf);
    rrc_rsp_begin(&w, "2.0", 9u, "OK");
    rrc_jw_obj_begin(&w);
    rrc_jw_kbool(&w, "bound", true);
    rrc_jw_obj_end(&w);
    rrc_rsp_end(&w);
    CHECK(rrc_jw_ok(&w));
    buf[rrc_jw_len(&w)] = '\0';
    CHECK_STR(buf, "{\"type\":\"RSP\",\"v\":\"2.0\",\"id\":9,\"status\":\"OK\",\"body\":{\"bound\":true}}");
    rrc_jw_init(&w, buf, sizeof buf);
    rrc_rsp_empty(&w, "1.0", 0u, "UNBOUND");
    buf[rrc_jw_len(&w)] = '\0';
    CHECK_STR(buf, "{\"type\":\"RSP\",\"v\":\"1.0\",\"id\":0,\"status\":\"UNBOUND\",\"body\":{}}");
    rrc_jw_init(&w, buf, sizeof buf);
    rrc_req_begin(&w, "2.0", 1u, "HELLO");
    rrc_jw_obj_begin(&w);
    rrc_jw_obj_end(&w);
    rrc_req_end(&w);
    buf[rrc_jw_len(&w)] = '\0';
    CHECK_STR(buf, "{\"type\":\"REQ\",\"v\":\"2.0\",\"id\":1,\"op\":\"HELLO\",\"args\":{}}");

    rrc_reply_cache_t c;
    rrc_cache_clear(&c);
    CHECK(!rrc_cache_hit(&c, 0u, 0u, 0u));
    rrc_cache_store(&c, 5u, 0xDEADBEEFu, 60u, 99u);
    CHECK(rrc_cache_hit(&c, 5u, 0xDEADBEEFu, 60u));
    CHECK(c.reply_len == 99u);
    CHECK(!rrc_cache_hit(&c, 6u, 0xDEADBEEFu, 60u));
    CHECK(!rrc_cache_hit(&c, 5u, 0xDEADBEEEu, 60u)); /* same id, different request bytes */
    CHECK(!rrc_cache_hit(&c, 5u, 0xDEADBEEFu, 61u));
    rrc_cache_clear(&c);
    CHECK(!rrc_cache_hit(&c, 5u, 0xDEADBEEFu, 60u));
}

/* ------------------------------------------------------------------ clock, ring */
static void test_clock(void)
{
    rrc_wrap32_t w;
    rrc_wrap32_init(&w, 0xFFFFFFF0u);
    CHECK(rrc_wrap32_extend(&w, 0xFFFFFFF8u) == 0xFFFFFFF8uLL);
    CHECK(rrc_wrap32_extend(&w, 0x00000004u) == 0x100000004uLL);
    CHECK(rrc_wrap32_extend(&w, 0x00000004u) == 0x100000004uLL);
    CHECK(rrc_wrap32_extend(&w, 0x00000003u) == 0x200000003uLL); /* a smaller value is one more wrap */
    CHECK(rrc_ticks_to_us(2400000u, 24000000u) == 100000u);
    CHECK(rrc_ticks_to_us(2397840u, 24000000u) == 99910u);
    CHECK(rrc_ticks_to_us(23u, 24000000u) == 0u);
    CHECK(rrc_us_to_ticks(100000u, 24000000u) == 2400000u);
    CHECK(rrc_muldiv_u64(UINT64_MAX, 1u, 1u) == UINT64_MAX);
    CHECK(rrc_muldiv_u64(UINT64_MAX, 2u, 1u) == UINT64_MAX); /* saturates */
    CHECK(rrc_muldiv_u64(0xFFFFFFFFFFFFuLL, 1000000u, 24000000u) == 0xFFFFFFFFFFFFuLL / 24u);
    CHECK(rrc_muldiv_u64(7u, 3u, 2u) == 10u);
    CHECK(rrc_time_reached(10u, 10u) && !rrc_time_reached(9u, 10u));
    CHECK(rrc_time_since(10u, 4u) == 6u && rrc_time_since(4u, 10u) == 0u);
    CHECK(rrc_time_add(UINT64_MAX - 1u, 5u) == UINT64_MAX);
}

static void test_ring(void)
{
    uint8_t store[8];
    rrc_ring_t r;
    CHECK(!rrc_ring_init(&r, store, 6u));
    CHECK(rrc_ring_init(&r, store, 8u));
    uint8_t b = 0;
    CHECK(!rrc_ring_pop(&r, &b));
    for (uint8_t i = 0; i < 8u; i++) {
        CHECK(rrc_ring_push(&r, i));
    }
    CHECK(!rrc_ring_push(&r, 99u));
    CHECK(r.dropped == 1u);
    CHECK(rrc_ring_count(&r) == 8u && rrc_ring_free(&r) == 0u);
    for (uint8_t i = 0; i < 8u; i++) {
        CHECK(rrc_ring_pop(&r, &b) && (b == i));
    }
    /* wrap the free-running indices many times */
    for (uint32_t i = 0; i < 1000u; i++) {
        CHECK(rrc_ring_push(&r, (uint8_t)i));
        CHECK(rrc_ring_push(&r, (uint8_t)(i + 1u)));
        CHECK(rrc_ring_pop(&r, &b) && (b == (uint8_t)i));
        CHECK(rrc_ring_pop(&r, &b) && (b == (uint8_t)(i + 1u)));
    }
    (void)rrc_ring_push(&r, 1u);
    rrc_ring_clear(&r);
    CHECK(rrc_ring_count(&r) == 0u);
}

/* ------------------------------------------------------------------ UUID, SHA-256, base64 */
static bool counting_entropy(void *ctx, uint8_t *buf, size_t len)
{
    uint8_t *next = (uint8_t *)ctx;
    for (size_t i = 0; i < len; i++) {
        buf[i] = (*next)++;
    }
    return true;
}

static bool failing_entropy(void *ctx, uint8_t *buf, size_t len)
{
    (void)ctx; (void)buf; (void)len;
    return false;
}

static void test_uuid(void)
{
    char u[RRC_UUID_STR_LEN + 1u];
    uint8_t seed = 0u;
    CHECK(rrc_uuid4_generate(counting_entropy, &seed, u));
    CHECK_STR(u, "00010203-0405-4607-8809-0a0b0c0d0e0f");
    CHECK(rrc_uuid_is_canonical(u));
    const uint8_t ff[16] = {255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255};
    rrc_uuid4_format(ff, u);
    CHECK_STR(u, "ffffffff-ffff-4fff-bfff-ffffffffffff");
    strcpy(u, "unchanged");
    CHECK(!rrc_uuid4_generate(failing_entropy, NULL, u));
    CHECK_STR(u, "unchanged");
    CHECK(!rrc_uuid_is_canonical("8050A49F-b67f-4ce2-9b87-1502a340d1f4"));
    CHECK(!rrc_uuid_is_canonical("8050a49f-b67f-4ce2-9b87-1502a340d1f"));
    CHECK(!rrc_uuid_is_canonical("8050a49f-b67f-4ce2-9b87-1502a340d1f40"));
    CHECK(rrc_uuid_is_canonical("8050a49f-b67f-4ce2-9b87-1502a340d1f4"));
}

static void test_sha256(void)
{
    uint8_t dg[RRC_SHA256_LEN];
    char hex[RRC_SHA256_HEX_LEN + 1u];
    rrc_sha256("", 0u, dg);
    rrc_hex_lower(dg, sizeof dg, hex);
    CHECK_STR(hex, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    rrc_sha256("abc", 3u, dg);
    rrc_hex_lower(dg, sizeof dg, hex);
    CHECK_STR(hex, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    const char *m = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
    rrc_sha256(m, strlen(m), dg);
    rrc_hex_lower(dg, sizeof dg, hex);
    CHECK_STR(hex, "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1");
    /* one million 'a', fed in uneven chunks */
    rrc_sha256_t ctx;
    rrc_sha256_init(&ctx);
    char chunk[977];
    memset(chunk, 'a', sizeof chunk);
    size_t left = 1000000u;
    while (left > 0u) {
        const size_t n = (left < sizeof chunk) ? left : sizeof chunk;
        rrc_sha256_update(&ctx, chunk, n);
        left -= n;
    }
    rrc_sha256_final(&ctx, dg);
    rrc_hex_lower(dg, sizeof dg, hex);
    CHECK_STR(hex, "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
}

static void test_base64(void)
{
    static const struct { const char *raw; const char *b64; } v[] = {
        {"f", "Zg=="}, {"fo", "Zm8="}, {"foo", "Zm9v"}, {"foob", "Zm9vYg=="}, {"fooba", "Zm9vYmE="}, {"foobar", "Zm9vYmFy"}};
    char enc[16];
    uint8_t dec[16];
    for (size_t i = 0; i < sizeof v / sizeof v[0]; i++) {
        const size_t n = rrc_base64_encode((const uint8_t *)v[i].raw, strlen(v[i].raw), enc, sizeof enc);
        CHECK((n == strlen(v[i].b64)) && (memcmp(enc, v[i].b64, n) == 0));
        const long m = rrc_base64_decode(v[i].b64, strlen(v[i].b64), dec, sizeof dec);
        CHECK((m == (long)strlen(v[i].raw)) && (memcmp(dec, v[i].raw, (size_t)m) == 0));
    }
    CHECK(rrc_base64_encode((const uint8_t *)"foo", 3u, enc, 3u) == 0u);
    CHECK(RRC_BASE64_ENC_LEN(768u) == 1024u);
    CHECK(rrc_base64_decode("Zg=", 3u, dec, sizeof dec) == -1);   /* bad length */
    CHECK(rrc_base64_decode("Zh==", 4u, dec, sizeof dec) == -1);  /* non-zero pad bits */
    CHECK(rrc_base64_decode("Zm9=", 4u, dec, sizeof dec) == -1);  /* non-zero pad bits */
    CHECK(rrc_base64_decode("Z===", 4u, dec, sizeof dec) == -1);
    CHECK(rrc_base64_decode("Zg==Zg==", 8u, dec, sizeof dec) == -1); /* padding inside */
    CHECK(rrc_base64_decode("Zm9v\n", 5u, dec, sizeof dec) == -1);
    CHECK(rrc_base64_decode("Zm-v", 4u, dec, sizeof dec) == -1);
    CHECK(rrc_base64_decode("Zm9vYmFy", 8u, dec, 5u) == -1);       /* output too small */
    CHECK(rrc_base64_decode("", 0u, dec, sizeof dec) == 0);
}

int main(void)
{
    RUN(test_crc32_check_value);
    RUN(test_frame_finish_and_check);
    RUN(test_frame_check_rejects);
    RUN(test_frame_rx_stream);
    RUN(test_frame_rx_oversize);
    RUN(test_writer_basic);
    RUN(test_writer_fixed);
    RUN(test_writer_overflow_and_misuse);
    RUN(test_reader_valid);
    RUN(test_reader_integer_limits);
    RUN(test_reader_strings);
    RUN(test_reader_rejects);
    RUN(test_reader_duplicate_keys);
    RUN(test_reader_limits);
    RUN(test_envelope_request);
    RUN(test_envelope_response_and_cache);
    RUN(test_clock);
    RUN(test_ring);
    RUN(test_uuid);
    RUN(test_sha256);
    RUN(test_base64);
    return TEST_SUMMARY();
}
