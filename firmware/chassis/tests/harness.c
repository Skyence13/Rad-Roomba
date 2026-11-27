#include "harness.h"

#include <stdlib.h>
#include <string.h>

int th_failures, th_checks;
static th_t g_th;

th_t *th_new(uint64_t seed)
{
    memset(&g_th, 0, sizeof g_th);
    sim_init(&g_th.sim, seed);
    g_th.next_id = 1;
    g_th.seq = 1;
    g_th.keepalive = true;
    g_th.body = -1;
    return &g_th;
}

void th_run_silent(th_t *t, int ms)
{
    for (int i = 0; i < ms; i++) {
        sim_step_ms(&t->sim);
    }
}

static bool exchange(th_t *t)
{
    sim_host_write(&t->sim, (const uint8_t *)t->last_req, t->last_req_len);
    t->reply_len = 0;
    t->body = -1;
    for (int ms = 0; ms < 4000; ms++) {
        sim_step_ms(&t->sim);
        uint8_t b;
        while (sim_host_read(&t->sim, &b, 1) == 1) {
            if (t->reply_len < RRCH_RECORD_MAX) {
                t->reply[t->reply_len++] = (char)b;
            }
            if (b == '\n') {
                size_t jl = 0;
                uint32_t crc;
                if (rrc_frame_check((const uint8_t *)t->reply, t->reply_len, RRCH_RECORD_MAX, &jl, &crc) != RRC_FRAME_OK) {
                    printf("  harness: bad frame in reply\n");
                    return false;
                }
                if (t->reply_len > t->max_reply_len) {
                    t->max_reply_len = t->reply_len;
                }
                static const rrc_json_limits_t lim = {8, 256};
                if (rrc_json_parse(&t->doc, t->reply, jl, t->tok, 512, &lim) != RRC_JSON_OK) {
                    printf("  harness: reply is not valid JSON\n");
                    return false;
                }
                t->body = rrc_json_get(&t->doc, 0, "body");
                return th_status(t, "OK");
            }
        }
    }
    printf("  harness: no reply\n");
    return false;
}

bool th_req(th_t *t, const char *op, const char *args_json)
{
    int n = snprintf(t->last_req, sizeof t->last_req - 12, "{\"type\":\"REQ\",\"v\":\"1.0\",\"id\":%u,\"op\":\"%s\",\"args\":%s}", t->next_id++, op, args_json);
    t->last_req_len = rrc_frame_finish((uint8_t *)t->last_req, (size_t)n, sizeof t->last_req, RRCH_RECORD_MAX);
    return exchange(t);
}

bool th_resend(th_t *t)
{
    return exchange(t);
}

void th_run(th_t *t, int ms)
{
    while (ms > 0) {
        int step = ms > 200 ? 200 : ms;
        th_run_silent(t, step);
        ms -= step;
        if (t->keepalive && ms > 0) {
            (void)th_req(t, "TIME", "{}");
            ms--;
        }
    }
}

bool th_status(th_t *t, const char *status)
{
    return rrc_json_str_eq(&t->doc, rrc_json_get(&t->doc, 0, "status"), status);
}

int th_get(th_t *t, const char *path)
{
    int tok = t->body;
    char key[48];
    while (tok >= 0 && *path) {
        size_t n = strcspn(path, ".");
        if (n >= sizeof key) {
            return -1;
        }
        memcpy(key, path, n);
        key[n] = 0;
        path += n + (path[n] == '.' ? 1 : 0);
        if (key[0] >= '0' && key[0] <= '9' && rrc_json_type(&t->doc, tok) == RRC_JT_ARRAY) {
            tok = rrc_json_at(&t->doc, tok, (uint16_t)atoi(key));
        } else {
            tok = rrc_json_get(&t->doc, tok, key);
        }
    }
    return tok;
}

double th_num(th_t *t, const char *path)
{
    size_t n;
    int tok = th_get(t, path);
    if (rrc_json_type(&t->doc, tok) != RRC_JT_NUMBER) {
        return -1e30;
    }
    const char *s = rrc_json_raw(&t->doc, tok, &n);
    char tmp[40];
    if (n >= sizeof tmp) {
        return -1e30;
    }
    memcpy(tmp, s, n);
    tmp[n] = 0;
    return strtod(tmp, NULL);
}

bool th_true(th_t *t, const char *path)
{
    bool b = false;
    return rrc_json_to_bool(&t->doc, th_get(t, path), &b) && b;
}

bool th_is(th_t *t, const char *path, const char *str)
{
    return rrc_json_str_eq(&t->doc, th_get(t, path), str);
}

int th_len(th_t *t, const char *path)
{
    int tok = th_get(t, path);
    return rrc_json_type(&t->doc, tok) == RRC_JT_ARRAY ? (int)rrc_json_size(&t->doc, tok) : -1;
}

bool th_has(th_t *t, const char *path, const char *str)
{
    int tok = th_get(t, path), n = th_len(t, path);
    for (int i = 0; i < n; i++) {
        if (rrc_json_str_eq(&t->doc, rrc_json_at(&t->doc, tok, (uint16_t)i), str)) {
            return true;
        }
    }
    return false;
}

void th_env(th_t *t, const char *json)
{
    /* stage 3 / round 4 N1: REARM sets K1 only from a charged C_SET. An operator waits for the REARM lamp
     * (rearm_ready); the harness does the same while the only thing missing is the C_SET charge
     * (RESERVOIR_LOW). Any other refusal reason is pressed into at once, so refusal tests stay meaningful. */
    if (strstr(json, "\"press\":\"REARM\"") && t->sim.cset_energy && !t->sim.latch && !strstr(json, "\"no_wait\"")) {
        for (int ms = 0; ms < 10000 && t->sim.core.chain.rearm_why == RRCH_RREF_RESERVOIR_LOW; ms += 50) {
            th_run_silent(t, 49);
            if (t->keepalive) {
                (void)th_req(t, "TIME", "{}");
            }
        }
    }
    if (!sim_env_apply(&t->sim, json, strlen(json))) {
        printf("  harness: bad env json: %s\n", json);
        th_failures++;
    }
}

bool th_mode(th_t *t, const char *mode)
{
    return th_req(t, "STATE", "{}") && th_is(t, "mode", mode);
}

bool th_drive(th_t *t, double v, double w, int ttl_ms, const char *op_mode)
{
    char a[160];
    snprintf(a, sizeof a, "{\"seq\":%u,\"v_mps\":%.4f,\"w_radps\":%.4f,\"ttl_ms\":%d,\"op_mode\":\"%s\"}", t->seq++, v, w, ttl_ms, op_mode);
    return th_req(t, "DRIVE", a) && th_true(t, "accepted");
}

void th_drive_for(th_t *t, double v, double w, int ms, const char *op_mode)
{
    for (int k = 0; k < ms; k += 20) {
        (void)th_drive(t, v, w, 200, op_mode);
        th_run_silent(t, 19);
    }
}

bool th_rearm_sw(th_t *t)
{
    char a[96];
    (void)th_req(t, "STATE", "{}");
    snprintf(a, sizeof a, "{\"nonce\":%.0f,\"operator\":\"unit.test\"}", th_num(t, "rearm_nonce"));
    return th_req(t, "REARM_SW", a);
}

bool th_arm(th_t *t, const char *op_mode)
{
    char a[64];
    th_run_silent(t, 300);
    if (!th_req(t, "HELLO", "{}")) {
        return false;
    }
    snprintf(a, sizeof a, "{\"op_mode\":\"%s\"}", op_mode);
    if (!th_req(t, "SET_OP_MODE", a)) {
        return false;
    }
    th_env(t, "{\"press\":\"REARM\"}");
    th_run(t, 300);
    if (!th_req(t, "BRAKE_TEST", "{}") || !th_true(t, "passed")) {
        printf("  harness: brake test did not pass\n");
        return false;
    }
    /* the test runs about 2.1 s (VMOT bleed tau 0.8 s, safety_chain.md 7.4): a host keeps polling
     * meanwhile; one TIME keeps the link supervision alive here */
    (void)th_req(t, "TIME", "{}");
    th_run(t, 100);
    th_env(t, "{\"press\":\"REARM\"}");
    th_run(t, 300);
    return th_mode(t, "ARMED_IDLE");
}

int th_summary(const char *name)
{
    printf("%s: %d checks, %d failures -> %s\n", name, th_checks, th_failures, th_failures ? "FAIL" : "PASS");
    return th_failures ? 1 : 0;
}
