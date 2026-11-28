/* Unit-test harness: drives the real core through its real protocol server on the plant model. */
#ifndef RR_CHASSIS_HARNESS_H
#define RR_CHASSIS_HARNESS_H
#include <stdio.h>

#include "sim.h"

typedef struct {
    sim_t sim;
    uint32_t next_id, seq;
    bool keepalive;          /* th_run sends TIME every 200 ms so the host link stays supervised-alive */
    char reply[RRCH_RECORD_MAX + 1];
    size_t reply_len, max_reply_len;
    rrc_jtok_t tok[512];
    rrc_json_t doc;
    int body;
    char last_req[RRCH_RECORD_MAX];
    size_t last_req_len;
} th_t;

extern int th_failures, th_checks;
#define CHECK(cond) do { th_checks++; if (!(cond)) { th_failures++; printf("  FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); } } while (0)
#define SECTION(name) printf("- %s\n", name)

th_t *th_new(uint64_t seed);                 /* fresh simulator (static storage, one at a time) */
void th_run_silent(th_t *t, int ms);
void th_run(th_t *t, int ms);
/* Sends one REQ and steps until its reply (max 4 s simulated). Returns true if status == "OK". */
bool th_req(th_t *t, const char *op, const char *args_json);
bool th_resend(th_t *t);                     /* identical bytes again (retry) */
bool th_status(th_t *t, const char *status);
int th_get(th_t *t, const char *path);       /* "a.b.c" below body; -1 if absent */
double th_num(th_t *t, const char *path);
bool th_true(th_t *t, const char *path);
bool th_is(th_t *t, const char *path, const char *str);
bool th_has(th_t *t, const char *array_path, const char *str);
int th_len(th_t *t, const char *array_path);
void th_env(th_t *t, const char *json);
bool th_mode(th_t *t, const char *mode);     /* STATE.mode == mode */
bool th_drive(th_t *t, double v, double w, int ttl_ms, const char *op_mode); /* returns accepted */
void th_drive_for(th_t *t, double v, double w, int ms, const char *op_mode);
/* HELLO, op_mode, local REARM, BRAKE_TEST, local REARM -> ARMED_IDLE. */
bool th_arm(th_t *t, const char *op_mode);
bool th_rearm_sw(th_t *t);                   /* REARM_SW with the current nonce; true if status OK */
int th_summary(const char *name);

#endif
