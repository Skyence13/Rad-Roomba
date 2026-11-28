/* Chain supervision: 1 kHz debounce with immediate latching of the "unsafe" direction, J1
 * presence-code decode, interlock-loop decode, node decode of the series chain (element states
 * CLOSED / OPEN / UNKNOWN), readback plausibility, ARM_PERMIT readback through CHAIN_END_RB, live
 * hardware-cause decode, latched hardware reasons. Observes the hardwired chain; has no means of
 * closing it.
 *
 * Electrical semantics (IB-01, IB-02; electronics/chassis_main/design/CONTRACT_CHANGE_REQUESTS.md
 * CCR-E02/E03, electronics/analysis/chassis_safety_chain.md 2.1-2.4):
 *  - the readbacks MODE_RUN .. WDG_OK are taps on the chain NODES CH_N1 .. CH_N9 ("the chain is
 *    live up to and including this element"); an element downstream of a dead node is UNKNOWN;
 *  - HEAD_LOOP_OK / HEAD_LOOP_SHORT / LAB_KEY_N are comparator outputs (input condition of the
 *    photo-MOS U21/U22); the nodes CH_N6/CH_N7 have no readback, so BODY_BUMPER_L is known only
 *    while CH_N5 is live and both comparators say "closed";
 *  - ESTOP_B is the COIL_RTN detector (pole B), independent of the chain nodes;
 *  - CHAIN_END_RB (IOX_B P17, read over I2C at ~100 Hz) is the node after the ARM_PERMIT element;
 *  - BRAKE_x_RB is an OR over both relay poles and valid only while the bridges are asleep. */
#include <math.h>
#include <string.h>

#include "rrch.h"

/* Inputs whose logical 1 is the direction that must be taken immediately (pressed / fault). */
#define IMM_HIGH_MASK (RRCH_DI(BTN_REARM) | RRCH_DI(BTN_PAUSE) | RRCH_DI(HEAD_LOOP_SHORT) | RRCH_DI(DRV_FAULT_L) | RRCH_DI(DRV_FAULT_R) | RRCH_DI(REARM_SET))

rrch_pres_t rrch_pres_classify(uint32_t ohm)
{
    if (ohm > 20000u) {
        return RRCH_PRES_ABSENT;
    }
    if (ohm >= 3900u && ohm <= 5600u) {
        return RRCH_PRES_HEAD_DIRECT;
    }
    if (ohm >= 950u && ohm < 1330u) {
        return RRCH_PRES_HEAD_VIA_LAB_EXTENSION;
    }
    if (ohm >= 1330u && ohm <= 1800u) {
        return RRCH_PRES_LAB_EXTENSION_ONLY;
    }
    return RRCH_PRES_FAULT;
}

static bool timer_run(uint16_t *t, bool cond, uint16_t limit_ms)
{
    if (!cond) {
        *t = 0;
        return false;
    }
    if (*t < limit_ms) {
        (*t)++;
    }
    return *t >= limit_ms;
}

/* Chain events and button actions. Node readbacks raise CHAIN events from the element decode below
 * (an element that becomes UNKNOWN is not reported as opened). */
static void di_changed(rrch_t *c, int i, bool v)
{
    if (i == RRCH_DII_J2_PRES) {
        rrch_event(c, RRCH_EV_J2, v, 0, 0);
    } else if (i == RRCH_DII_BTN_REARM || i == RRCH_DII_BTN_PAUSE) {
        rrch_event(c, RRCH_EV_BUTTON, i == RRCH_DII_BTN_PAUSE, v, 0);
        if (v && c->boot_done) {
            if (i == RRCH_DII_BTN_PAUSE) {
                rrch_hold(c, RRCH_HOLD_LOCAL_PAUSE);
            } else {
                uint32_t blocked, hc;
                (void)rrch_rearm_sw(c, true, "LOCAL", &blocked, &hc);
            }
        }
    }
}

/* A failed read keeps the last good sample (review m7): one I2C glitch must not drop the latch while
 * driving. Freshness is judged in chain_end_step. */
void rrch_iox_b_update(rrch_t *c, bool ok, bool chain_end, uint64_t t_us)
{
    rrch_iox_b_t *b = &c->chain.iox_b;
    b->ok = ok;
    if (ok) {
        b->chain_end = chain_end;
        b->t_us = t_us;
        b->fail_n = 0;
    } else if (b->fail_n < 1000000u) {
        b->fail_n++;
    }
}

/* stage 4 G6: a read is good only when the input bits of the two test outputs (P4, P7) read what the port wrote
 * (replaces the stage-3 fixed pattern; the port also checks configuration 0x03 == 0x6F) */
void rrch_iox_d_update(rrch_t *c, bool ok, uint8_t in, uint8_t out, uint64_t t_us)
{
    rrch_iox_d_t *d = &c->chain.iox_d;
    if (ok && (in & 0x90u) == (out & 0x90u)) {
        d->ok = true;
        d->val = in;
        d->out = out;
        d->t_us = t_us;
        d->fail_n = 0;
    } else {
        d->ok = false;
        d->fail_n = d->fail_n < 1000000u ? d->fail_n + 1u : d->fail_n;
    }
}

uint8_t rrch_iox_d_out(const rrch_t *c)
{
    return c->chain.lt_out;
}

bool rrch_iox_d_fast(const rrch_t *c)
{
    return c->chain.lt_phase != 0u || c->chain.ld_phase == 2u;
}

/* S4: after "A open, analog open, B closed" (LOOP_FAIL, fail-safe already), one LOOP_TEST_B pulse of 30 ms with the
 * latch down tells the two causes apart: channel B goes open -> B is healthy, the fault is on the A side (Q_LTA stuck
 * on or LOOP_F grounded: "loop self-test path fault"); B stays closed -> B stuck healthy. The pulse can only open. */
static void loop_diag_step(rrch_t *c, bool latch)
{
    rrch_chain_t *ch = &c->chain;
    const rrch_iox_d_t *xd = &ch->iox_d;
    if (ch->ld_phase == 1u && !latch && ch->lt_phase == 0u && ch->iox_d_known) {
        ch->ld_phase = 2;
        ch->ld_ms = 0;
        ch->ld_b_low = false;
        ch->lt_out = 0x80u;
    } else if (ch->ld_phase == 2u) {
        if (latch) {
            ch->lt_out = 0;
            ch->ld_phase = 1;
            return;
        }
        uint64_t start = c->now_us - 1000u * (uint64_t)ch->ld_ms;
        if (ch->iox_d_known && (xd->out & 0x80u) && xd->t_us >= start + 10000u && !(xd->val & 0x04u)) {
            ch->ld_b_low = true;
        }
        if (++ch->ld_ms >= 30u) {
            ch->lt_out = 0;
            ch->ld_phase = 0;
            ch->loop_cause = ch->ld_b_low ? RRCH_LC_TEST_PATH_A : RRCH_LC_B_STUCK_HEALTHY;
        }
    }
}

/* stage 4 G1/G2: what a REARM press would meet now (latch down). SET_READY_RB is the set stage's own comparator
 * (C_SET >= 10.8 V; Q_SETC keeps the reservoir untouched while it is low); the set margin is guaranteed for a coil
 * <= +45 C, taken as the board NTC (unreadable counts as hot). */
#define REARM_COIL_MAX_C 45.0f
#define REARM_HELD_LATCHED_MS 5000u /* stage 5 H6 (was 2 s): a W-018 crush now arms for 5 s */
#define REARM_VBAT_MIN_V 11.7f /* G2: SET_READY never comes below this (worst case) */
static uint8_t rearm_why(const rrch_t *c, bool others_closed)
{
    const rrch_chain_t *ch = &c->chain;
    if (!c->boot_done || c->mode == RRCH_MODE_FAULT || c->mode == RRCH_MODE_BOOT || c->mode == RRCH_MODE_LAB || c->mode == RRCH_MODE_SERVICE_CHARGE ||
        (c->faults & (RRCH_FLT_FATAL_MASK | RRCH_FLT(SET_STAGE_FAULT) | RRCH_FLT(REARM_RB_FAULT)))) {
        return RRCH_RREF_FAULT_OR_MODE;
    }
    if (ch->rearm_held_ms > 2000u || ch->rearm_set_held_ms > 2000u) {
        return RRCH_RREF_REARM_HELD;
    }
    if (ch->lt_phase != 0u) {
        return RRCH_RREF_LOOP_TEST;
    }
    if (!others_closed || (ch->hw_live & ~RRCH_HW(MCU_NOT_READY)) != 0u) {
        return RRCH_RREF_CHAIN_OPEN;
    }
    if (!c->out.arm_permit || ch->el[RRCH_EL_ARM_PERMIT] != RRCH_ELS_CLOSED) {
        return RRCH_RREF_PERMIT_WITHHELD;
    }
    if (!ch->lt_passed) {
        return RRCH_RREF_LOOP_TEST;
    }
    /* Q_SETC conducts 13-28 ms after SET_READY rises (T13): offer the press only 30 ms after the first high sample */
    if (!(ch->iox_d_known && ch->set_ready && ch->set_ready_since_us != 0u && c->now_us - ch->set_ready_since_us >= 30000u)) {
        return (c->in.vbat_v < REARM_VBAT_MIN_V && !ch->set_ready) ? RRCH_RREF_SUPPLY_LOW : RRCH_RREF_NOT_READY;
    }
    return RRCH_RREF_NONE;
}

/* stage 4 G5: loop self-test before every arming (latch down, chain otherwise closed, ARM_PERMIT high). Each test
 * output can only force its channel open. TEST_A 30 ms: channel A (GPA5) and CHN6A_RB must read open/dead;
 * 20 ms gap; TEST_B 30 ms: channel B (HEAD_LOOP2_OK_RB) and BODY_BUMPER_L_RB (CH_N8A) must read open/dead. For
 * the ~90 ms of the test the chain decode uses the readbacks from before it (no events, no latched reasons, no
 * loop-disagreement rules; the latch is down and the test itself holds the chain open). Any failure: LOOP_FAIL. */
#define LT_MASK (RRCH_DI(HEAD_LOOP_OK) | RRCH_DI(HEAD_LOOP_SHORT) | RRCH_DI(LAB_KEY_N) | RRCH_DI(BODY_BUMPER_L) | RRCH_DI(BODY_BUMPER_R) | RRCH_DI(WDG_OK))
static void loop_test_step(rrch_t *c, bool start_ok)
{
    rrch_chain_t *ch = &c->chain;
    const rrch_iox_d_t *xd = &ch->iox_d;
    uint32_t raw = c->in.di;
    /* a sample taken with the test output applied (written by the port) at least 10 ms into the phase */
    uint64_t ph_start = c->now_us - 1000u * (uint64_t)ch->lt_ms;
    bool fresh = ch->iox_d_known && xd->t_us >= ph_start + 10000u;
    switch (ch->lt_phase) {
    case 0:
        if (start_ok) {
            ch->lt_snap_st = ch->state;
            ch->lt_snap_ohm = c->in.loop_ohm;
            ch->lt_snap_b = ch->loop_b;
            ch->lt_phase = 1;
            ch->lt_ms = 0;
            ch->lt_a_ok = ch->lt_b_ok = false;
            ch->lt_out = 0x10u;
        }
        return;
    case 1:
        if (fresh && (xd->out & 0x10u) && !(xd->val & 0x40u) && !(raw & RRCH_DI(HEAD_LOOP_OK))) {
            ch->lt_a_ok = true;
        }
        if (++ch->lt_ms >= 30u) {
            ch->lt_out = 0;
            ch->lt_phase = 2;
            ch->lt_ms = 0;
        }
        return;
    case 2:
        if (++ch->lt_ms >= 20u) {
            ch->lt_out = 0x80u;
            ch->lt_phase = 3;
            ch->lt_ms = 0;
        }
        return;
    case 3:
        if (fresh && (xd->out & 0x80u) && !(xd->val & 0x04u) && !(raw & RRCH_DI(BODY_BUMPER_L)) && (raw & RRCH_DI(HEAD_LOOP_OK))) {
            ch->lt_b_ok = true;
        }
        if (++ch->lt_ms >= 30u) {
            ch->lt_out = 0;
            ch->lt_phase = 4;
            ch->lt_ms = 0;
            if (!(ch->lt_a_ok && ch->lt_b_ok)) {
                if (!(c->faults & RRCH_FLT(LOOP_FAIL))) {
                    ch->loop_cause = !ch->lt_a_ok ? RRCH_LC_SELF_TEST_A : RRCH_LC_SELF_TEST_B;
                }
                rrch_fault_set(c, RRCH_FLT(LOOP_FAIL), true); /* a channel or its photo-MOS does not open */
            }
        }
        return;
    default: /* settle: test outputs off; end at the first fresh IOX_D sample (>= 10 ms) */
        ch->lt_ms++;
        if ((fresh && (xd->out & 0x90u) == 0u) || ch->lt_ms >= 100u) {
            /* readbacks back exactly as before the test: take them without the close debounce (the opening was the
             * test's own); anything else changed during the test is decoded normally from now on */
            if ((raw & LT_MASK) == (ch->lt_snap_st & LT_MASK) && ch->loop_b == ch->lt_snap_b) {
                ch->state = (ch->state & ~LT_MASK) | (raw & LT_MASK);
                for (int i = 0; i < RRCH_DI_N; i++) {
                    if (LT_MASK & (1u << i)) {
                        ch->cnt[i] = 0;
                    }
                }
            }
            ch->lt_phase = 0;
            ch->lt_passed = ch->lt_a_ok && ch->lt_b_ok;
            ch->lt_n += ch->lt_passed ? 1u : 0u;
        }
        return;
    }
}

static rrch_el_state_t node_el(uint32_t st, uint32_t known, uint32_t bit)
{
    if (!(known & bit)) {
        return RRCH_ELS_UNKNOWN;
    }
    return (st & bit) ? RRCH_ELS_CLOSED : RRCH_ELS_OPEN;
}

static rrch_el_state_t el_and(rrch_el_state_t a, rrch_el_state_t b)
{
    if (a == RRCH_ELS_OPEN || b == RRCH_ELS_OPEN) {
        return RRCH_ELS_OPEN;
    }
    return (a == RRCH_ELS_CLOSED && b == RRCH_ELS_CLOSED) ? RRCH_ELS_CLOSED : RRCH_ELS_UNKNOWN;
}

/* history bit k = value k ms before this tick; true if the bit was `v` for the whole window */
static bool hist_all(uint32_t h, uint32_t from_ms, uint32_t len_ms, bool v)
{
    if (from_ms + len_ms > 31u) {
        return false;
    }
    uint32_t m = ((1u << len_ms) - 1u) << from_ms;
    return v ? (h & m) == m : (h & m) == 0u;
}

/* IB-01: ARM_PERMIT readback. A sample of CHAIN_END_RB is judged against the ARM_PERMIT output and
 * the raw CH_N9 (WDG_OK) readback at the time it was taken, both stable for the 10 ms before it
 * (photo-MOS U24 1 ms [U], tap RC 0.8 ms). Three consecutive bad samples (>= 20 ms) are needed. */
#define CE_SETTLE_MS 10u
static void chain_end_step(rrch_t *c)
{
    rrch_chain_t *ch = &c->chain;
    ch->permit_hist = (ch->permit_hist << 1) | (c->out.arm_permit ? 1u : 0u);
    ch->n9_hist = (ch->n9_hist << 1) | ((c->in.di & RRCH_DI(WDG_OK)) ? 1u : 0u);
    const rrch_iox_b_t *b = &ch->iox_b;
    /* review m7: while latched a sample up to 50 ms old is accepted (several consecutive failed reads at
     * 100 Hz); arming (latch down) needs the last read to have succeeded */
    bool fresh = b->t_us != 0u && b->t_us <= c->now_us && c->now_us - b->t_us <= 50000u && (ch->latch || b->fail_n == 0u);
    ch->chain_end_known = fresh;
    ch->chain_end = fresh && b->chain_end;
    ch->ce_high_ms = ch->chain_end ? (uint16_t)(ch->ce_high_ms < 60000u ? ch->ce_high_ms + 1u : 60000u) : 0u;
    rrch_fault_set(c, RRCH_FLT(IOX_B), c->boot_done && !fresh);
    if (b->t_us == 0u || b->t_us == ch->iox_b_seen_us || b->t_us > c->now_us) {
        return;
    }
    ch->iox_b_seen_us = b->t_us;
    uint32_t age = (uint32_t)((c->now_us - b->t_us + 500u) / 1000u);
    if (age > 31u - CE_SETTLE_MS) {
        return; /* too old to be compared with the history */
    }
    bool p_low = hist_all(ch->permit_hist, age, CE_SETTLE_MS, false), p_high = hist_all(ch->permit_hist, age, CE_SETTLE_MS, true);
    bool n9_live = hist_all(ch->n9_hist, age, CE_SETTLE_MS, true), n9_dead = hist_all(ch->n9_hist, age, CE_SETTLE_MS, false);
    bool none_open = true; /* element states of the previous tick */
    for (int e = 0; e < RRCH_EL_N; e++) {
        none_open = none_open && ch->el[e] != RRCH_ELS_OPEN;
    }
    if (p_high && n9_live && b->chain_end && none_open && ch->t_implausible == 0u) {
        ch->ce_live_us = b->t_us; /* really live through closed elements: C_SET is (being) charged from CHAIN_END */
    }
    /* review M1: on rev A, C_SET holds CHAIN_END (and nodes behind an opened element) up through R_SET
     * for up to ~10 s after the chain was last live. "Live with ARM_PERMIT low" and "live behind a
     * dead CH_N9" are judged only outside that window; meanwhile a latch rise with ARM_PERMIT low is
     * fatal at once (LATCH_NO_REARM / LATCH_STUCK), which is what a stuck U24 would lead to. */
    if (ch->backfeed) {
        ch->n_stuck_on = ch->n_end_impl = 0;
    }
    if (ch->backfeed) {
        ch->n_stuck_off = (p_high && n9_live && !b->chain_end) ? (uint8_t)(ch->n_stuck_off < 250u ? ch->n_stuck_off + 1u : 250u) : 0u;
        goto judge;
    }
    ch->n_stuck_on = (p_low && b->chain_end) ? (uint8_t)(ch->n_stuck_on < 250u ? ch->n_stuck_on + 1u : 250u) : 0u;
    ch->n_stuck_off = (p_high && n9_live && !b->chain_end) ? (uint8_t)(ch->n_stuck_off < 250u ? ch->n_stuck_off + 1u : 250u) : 0u;
    ch->n_end_impl = (n9_dead && b->chain_end) ? (uint8_t)(ch->n_end_impl < 250u ? ch->n_end_impl + 1u : 250u) : 0u;
judge:
    if (ch->n_stuck_on >= 3u) {
        rrch_fault_set(c, RRCH_FLT(PERMIT_STUCK_ON), true); /* ARM_PERMIT element closed although commanded open */
    }
    if (ch->n_end_impl >= 3u) {
        rrch_fault_set(c, RRCH_FLT(CHAIN_IMPLAUSIBLE), true); /* CHAIN_END live behind a dead CH_N9 */
    }
    if (ch->n_stuck_off >= 3u) {
        rrch_fault_set(c, RRCH_FLT(PERMIT_STUCK_OFF), true); /* element open although commanded closed (fails safe) */
    } else if (ch->n_stuck_off == 0u && (p_low || !n9_live || b->chain_end)) {
        rrch_fault_set(c, RRCH_FLT(PERMIT_STUCK_OFF), false);
    }
}

#define RB_NODE_MASK (RRCH_DI(MODE_RUN) | RRCH_DI(ESTOP_A) | RRCH_DI(HANDS_ON) | RRCH_DI(CHG_COVER) | RRCH_DI(CHG_PLUG_LINK) | RRCH_DI(HEAD_DOCK) | \
                      RRCH_DI(BODY_BUMPER_L) | RRCH_DI(BODY_BUMPER_R) | RRCH_DI(WDG_OK))
#define BRAKE_MASK (RRCH_DI(BRAKE_L) | RRCH_DI(BRAKE_R))
#define RB_VALID_MS 3u /* DRV8874 tSLEEP 1 ms [D] + comparator and RC */

void rrch_chain_step(rrch_t *c)
{
    rrch_chain_t *ch = &c->chain;
    const rrch_in_t *in = &c->in;
    uint16_t close_n = (uint16_t)CFG(c, CHAIN_CLOSE_DEBOUNCE_MS);

    /* BRAKE_x_RB is valid only while the bridges sleep (CCR-E03 e): firmware commanded sleep in the
     * previous tick, or the latch readback (RUN_12V, which also forces nSLEEP low through U9) is low. */
    bool asleep = !c->out.bridge_awake || !(in->di & RRCH_DI(HW_LATCH));
    ch->asleep_ms = asleep ? (uint16_t)(ch->asleep_ms < 60000u ? ch->asleep_ms + 1u : 60000u) : 0u;
    bool rb_valid = ch->asleep_ms >= RB_VALID_MS;
    uint32_t raw = in->di;
    if (!rb_valid && ch->primed) {
        raw = (raw & ~BRAKE_MASK) | (ch->state & BRAKE_MASK); /* hold the last valid reading */
    }

    if (!ch->primed) {
        ch->state = raw;
        ch->pres = ch->pres_cand = rrch_pres_classify(in->pres_ohm);
        ch->latch = (in->di & RRCH_DI(HW_LATCH)) != 0;
        ch->rb_reported = raw;
        ch->primed = true;
        /* after any reset C_SET may still be charged from before (it holds CHAIN_END for up to ~10 s,
         * review M1): treat the boot like the end of a live period */
        ch->ce_live_us = c->now_us > 0u ? c->now_us : 1u;
    }

    /* --- digital debounce --- */
    for (int i = 0; i < RRCH_DI_N; i++) {
        uint32_t bit = 1u << i;
        bool r = (raw & bit) != 0, s = (ch->state & bit) != 0;
        if (r == s) {
            ch->cnt[i] = 0;
            continue;
        }
        bool imm = ((IMM_HIGH_MASK & bit) != 0) ? r : !r;
        if (imm || ++ch->cnt[i] >= close_n) {
            ch->state = (ch->state & ~bit) | (r ? bit : 0u);
            ch->cnt[i] = 0;
            di_changed(c, i, r);
        }
    }
    uint32_t st = ch->state;
    if (ch->lt_phase != 0u) {
        st = (st & ~LT_MASK) | (ch->lt_snap_st & LT_MASK); /* loop self-test: decode the readbacks from before it */
    }

    /* --- J1 presence code: ABSENT after 2 samples, any other change after the settle time --- */
    rrch_pres_t rawp = rrch_pres_classify(in->pres_ohm);
    ch->pres_ohm = in->pres_ohm;
    if (rawp == ch->pres) {
        ch->pres_cnt = 0;
        ch->pres_cand = rawp;
    } else {
        if (rawp != ch->pres_cand) {
            ch->pres_cand = rawp;
            ch->pres_cnt = 0;
        }
        ch->pres_cnt++;
        uint16_t need = (rawp == RRCH_PRES_ABSENT) ? 2u : (uint16_t)CFG(c, CHAIN_PRES_SETTLE_MS);
        if (ch->pres_cnt >= need) {
            rrch_event(c, RRCH_EV_J1, ch->pres, rawp, (int32_t)(in->pres_ohm > 999999u ? 999999u : in->pres_ohm));
            ch->pres = rawp;
            ch->pres_cnt = 0;
        }
    }
    rrch_fault_set(c, RRCH_FLT(J1_PRES_FAULT), ch->pres == RRCH_PRES_FAULT);

    /* --- interlock loop: hardware comparator and analog decode, report the worse --- */
    ch->loop_ohm = in->loop_ohm;
    /* --- stage 3 IOX_D readbacks (F1-F6). Known only with a fresh, pattern-checked sample: up to 50 ms old
     * while latched (m7), and the last read good before arming. --- */
    bool raw_latch = (in->di & RRCH_DI(HW_LATCH)) != 0;
    const rrch_iox_d_t *xd = &ch->iox_d;
    ch->iox_d_known = xd->t_us != 0u && xd->t_us <= c->now_us && c->now_us - xd->t_us <= 50000u && (raw_latch || xd->fail_n == 0u);
    rrch_fault_set(c, RRCH_FLT(IOX_D), c->boot_done && !ch->iox_d_known);
    bool d_new = ch->iox_d_known && xd->t_us != xd->seen_us;
    if (ch->iox_d_known) {
        ch->k1_nc = (xd->val & 0x01u) != 0;     /* P0 HIGH = K1 pole A released */
        ch->k1_run = (xd->val & 0x02u) != 0;    /* P1 HIGH = CHAIN_END live AND K1 pole B closed (before U_HOLD) */
        ch->loop_b = (xd->val & 0x04u) != 0;    /* P2 HIGH = loop channel B (U46) sees the loop closed */
        ch->bus_clamp = (xd->val & 0x08u) != 0; /* P3 BUS_CLAMP_ACTIVE (stage 4 G4) */
        ch->set_ready = (xd->val & 0x20u) != 0; /* P5 SET_READY_RB: C_SET >= 10.8 V (stage 4 G1) */
        ch->chn6a = (xd->val & 0x40u) != 0;     /* P6 CHN6A_RB: node between U21 and U21B (stage 4 G5) */
    } else {
        ch->k1_nc = ch->k1_run = ch->loop_b = ch->set_ready = ch->chn6a = false; /* unknown counts as "not healthy" */
    }
    if (!ch->set_ready) {
        ch->set_ready_since_us = 0u;
    } else if (ch->set_ready_since_us == 0u) {
        ch->set_ready_since_us = xd->t_us; /* first sample seen high (the rise was at most one read period earlier) */
    }
    /* stage 4 G4: the REARM set contact is on IOX_A GPB6, sampled at 1 kHz; edges from the undebounced line */
    ch->rearm_set = (in->di & RRCH_DI(REARM_SET)) != 0;
    if (ch->rearm_set && !ch->rearm_set_prev) {
        ch->rearm_set_edge_us = c->now_us;
        ch->set_close_us = c->now_us;
    } else if (!ch->rearm_set && ch->rearm_set_prev) {
        ch->set_open_us = c->now_us;
    }
    ch->rearm_set_prev = ch->rearm_set;
    rrch_fault_set(c, RRCH_FLT(BUS_CLAMP), ch->bus_clamp);
    /* stage 4 G5 (review N3): a loop photo-MOS that conducts while its channel says open. Channel A (GPA5, raw)
     * open for > 10 ms with CHN6A_RB high on two samples: U21/Q22 shorted. Channel B (IOX_D P2) low for > 10 ms with
     * BODY_BUMPER_L_RB (CH_N8A, raw) high on two samples: U21B/Q_LB shorted. Both fatal (LOOP_SW_SHORT). */
    bool a_raw_open = !(in->di & RRCH_DI(HEAD_LOOP_OK));
    ch->a_open_since_us = a_raw_open ? (ch->a_open_since_us ? ch->a_open_since_us : c->now_us) : 0u;
    if (d_new) {
        rrch_iox_d_t *xw = &ch->iox_d;
        xw->seen_us = xd->t_us;
        if (!ch->loop_b) {
            ch->b_low_since_us = ch->b_low_since_us ? ch->b_low_since_us : xd->t_us;
        } else {
            ch->b_low_since_us = 0u;
        }
        bool u21s = ch->chn6a && ch->a_open_since_us != 0u && xd->t_us >= ch->a_open_since_us + 10000u;
        bool u21bs = !ch->loop_b && (in->di & RRCH_DI(BODY_BUMPER_L)) && ch->b_low_since_us != 0u && xd->t_us >= ch->b_low_since_us + 10000u;
        ch->n_u21s = u21s ? (uint8_t)(ch->n_u21s + 1u) : 0u;
        ch->n_u21bs = u21bs ? (uint8_t)(ch->n_u21bs + 1u) : 0u;
        if ((ch->n_u21s >= 2u || ch->n_u21bs >= 2u) && c->boot_done) {
            rrch_fault_set(c, RRCH_FLT(LOOP_SW_SHORT), true);
        }
    }
    /* stage 4 G1: SET_READY high with CHAIN_END known dead for > 1 s (C_SET is discharged then): comparator stuck */
    ch->ce_dead_ms = (ch->chain_end_known && !ch->chain_end) ? (ch->ce_dead_ms < 600000u ? ch->ce_dead_ms + 1u : ch->ce_dead_ms) : 0u;
    if (ch->ce_dead_ms > 1000u && ch->iox_d_known && ch->set_ready && c->boot_done) {
        rrch_fault_set(c, RRCH_FLT(SET_STAGE_FAULT), true); /* non-fatal, sticky: arming withheld until a reset */
    }
    /* raw HW_LATCH_RB (RUN_12V tap) level history for the weld / short rules */
    static const uint64_t settle_us = 10000u;
    if (raw_latch != ch->raw_latch_prev) {
        ch->raw_latch_prev = raw_latch;
        ch->raw_latch_since_us = c->now_us;
    }
    bool sample_after = d_new && xd->t_us >= ch->raw_latch_since_us + settle_us && c->now_us - ch->raw_latch_since_us >= 20000u;
    if (sample_after) {
        /* F2/F3: latch down but K1 operated (pole A NC open) or K1 pole B passing CHAIN_END: K1 welded (U_HOLD
         * keeps RUN_HD off, so this is detection, not the barrier). F4: RUN_12V up without K1_RUN: RUN_SHORT. */
        /* the set pulse (110 ms) may hold K1 for a moment without the hold path: not judged within 300 ms of a REARM edge */
        uint64_t last_edge = ch->rearm_edge_us > ch->rearm_set_edge_us ? ch->rearm_edge_us : ch->rearm_set_edge_us;
        bool in_pulse = last_edge != 0u && c->now_us - last_edge < 300000u;
        /* round 4 N2: K1 closed with the latch down while CHAIN_END is (or may be) live is first a set that did not
         * complete (a REARM tap shorter than K1's operate time: K1 sealed in by its own contact, U_HOLD never set),
         * not proof of a weld: ARM_PERMIT is withdrawn for 200 ms (K1 releases in 4 ms) and the press is reported
         * PARTIAL. K1_WELD needs pole A still operated, or K1_RUN live, with CHAIN_END known dead (ARM_PERMIT low >= 30 ms). */
        bool ce_dead = !c->out.arm_permit && hist_all(ch->permit_hist, 0u, 30u, false);
        bool k1_closed = !ch->k1_nc || ch->k1_run;
        bool unheld = !raw_latch && k1_closed && !ce_dead && c->boot_done;
        bool weld = !raw_latch && k1_closed && ce_dead && !in_pulse; /* K1_RUN live without CHAIN_END: fed from elsewhere */
        bool run_short = raw_latch && !ch->k1_run;
        ch->n_unheld = unheld ? (uint8_t)(ch->n_unheld + 1u) : 0u;
        if (ch->n_unheld >= 2u) {
            ch->unheld_until_us = c->now_us + 30000u; /* stage 5 H4: 30 ms keeps C_SET (discharge starts >= 41 ms) */
            ch->short_dip = true;
            if (ch->press_pending || (ch->press_us != 0u && c->now_us - ch->press_us < 1000000u)) {
                ch->press_why = RRCH_RREF_PARTIAL;
                ch->press_pending = true;
            }
        }
        ch->n_weld = weld ? (uint8_t)(ch->n_weld + 1u) : 0u;
        ch->n_run_short = run_short ? (uint8_t)(ch->n_run_short + 1u) : 0u;
        if (ch->n_weld >= 2u && c->boot_done) {
            rrch_fault_set(c, RRCH_FLT(K1_WELD), true);
        }
        if (ch->n_run_short >= 1u) {
            rrch_fault_set(c, RRCH_FLT(RUN_SHORT), true);
        }
    }

    /* The hardware window (U30) passes 0.59-1.55 kOhm (safety_chain.md 2.2). The analog copy uses bands
     * around it so that tolerances do not read as disagreement: OK 620-1500, OPEN > 1650, SHORT < 560,
     * in between "marginal" (follows the comparator). */
    uint8_t cmp = (st & RRCH_DI(HEAD_LOOP_SHORT)) ? 2u : ((st & RRCH_DI(HEAD_LOOP_OK)) ? 0u : 1u);
    uint32_t lo = ch->lt_phase != 0u ? ch->lt_snap_ohm : in->loop_ohm; /* self-test: the analog copy reads open by design */
    uint8_t ana = lo < 560u ? 2u : (lo > 1650u ? 1u : ((lo >= 620u && lo <= 1500u) ? 0u : 3u));
    ch->ana3 = ana;
    uint8_t anaw = ana == 3u ? cmp : ana;
    ch->loop_state = (cmp == 2u || anaw == 2u) ? 2u : ((cmp == 1u || anaw == 1u || (ch->iox_d_known && !(ch->lt_phase != 0u ? ch->lt_snap_b : ch->loop_b))) ? 1u : 0u);
    bool disagree = ana != 3u && ((cmp == 0u) != (ana == 0u));
    bool latched_now = (st & RRCH_DI(HW_LATCH)) != 0;
    rrch_fault_set(c, RRCH_FLT(LOOP_DISCREPANCY), timer_run(&ch->t_loop_disc, disagree, 200));
    /* review C2: while latched, the loop is not only a warning. Any opening seen by either channel
     * (analog: 2 consecutive 1 kHz samples; comparator: immediate) withdraws ARM_PERMIT (U24 is upstream
     * of K1, so the latch drops even if U21 is held closed) and latches STOP_ESCALATED; a disagreement
     * lasting 5 ms while latched (the comparator lags the analog copy by about 1.5 ms) is LOOP_FAIL. */
    bool ana_bad = timer_run(&ch->t_loop_ana, ana == 1u || ana == 2u, 2);
    bool b_open = ch->iox_d_known && !(ch->lt_phase != 0u ? ch->lt_snap_b : ch->loop_b);
    if (latched_now && c->boot_done && (ana_bad || cmp != 0u || b_open)) {
        if (!c->permit_withdrawn) {
            c->permit_withdrawn = true;
            rrch_event(c, RRCH_EV_PERMIT, 0, 5, 0);
        }
        rrch_pstop(c, RRCH_SW(STOP_ESCALATED));
    }
    /* stage 3 F6: channel A (U30, open/short window) and channel B (U46, open only) in series. A/B
     * disagreement about "open" for 20 ms (A reporting a short is not a disagreement: B cannot see
     * shorts): the analog copy arbitrates. Analog says open -> the channel that says closed is stuck
     * healthy, a hardware barrier is lost: LOOP_FAIL (fatal). Analog says OK or marginal -> the channel
     * that says open is wrong in the safe direction: LOOP_DISCREPANCY (arming withheld, not fatal; that
     * channel holds the chain open anyway). Without IOX_D the stage-2 rule (A vs analog) stays. */
    bool ab = ch->iox_d_known && cmp != 2u && ((cmp == 1u) != b_open);
    bool ab_t = timer_run(&ch->t_loopab, ab, 20);
    /* round 4 N6 / stage 4 G7: the channels have different thresholds (A opens above 1.55 kOhm, B only above
     * 1.89 kOhm), so a loop between them (analog 1.65-2.05 kOhm, B's threshold plus tolerance) is "A open, B closed" by
     * design: HEAD_LOOP_OPEN (arming withheld, A holds U21 open) plus the warning LOOP_HIGH_R, not a fault.
     * LOOP_FAIL only when a channel is provably stuck healthy: A closed with the analog copy above 1.65 kOhm,
     * or B closed with the analog copy above loop.b_stuck_ohm (2.05 kOhm: B's 1.89 kOhm threshold plus tolerance, G7). */
    uint32_t b_lim = (uint32_t)CFG(c, LOOP_B_STUCK_OHM); /* 2050: stage 4 G7 (B 1.89 kOhm, current netlist); 2900: stage 3 (B 2.70 kOhm) */
    bool high_r = lo > 1650u && lo <= b_lim;
    bool a_stuck = cmp == 0u && ana == 1u;
    bool b_stuck = !b_open && lo > b_lim;
    if (ab_t && (a_stuck || b_stuck)) {
        /* S4: the analog copy is taken from LOOP_F, the node Q_LTA (LOOP_TEST_A) pulls to ground, so "A open, analog
         * open, B closed" is either B stuck healthy or the A path (Q_LTA stuck on, LOOP_F grounded). Fail safe at once;
         * the diagnosis is settled by one LOOP_TEST_B pulse once the latch is down (loop_diag_step). */
        if (!(c->faults & RRCH_FLT(LOOP_FAIL))) {
            ch->loop_cause = a_stuck ? RRCH_LC_A_STUCK_HEALTHY : RRCH_LC_CHECKING_B;
            ch->ld_phase = a_stuck ? 0u : 1u;
        }
        rrch_fault_set(c, RRCH_FLT(LOOP_FAIL), true);
    }
    bool ab_disc = ab_t && !(high_r && cmp == 1u && !b_open);
    rrch_fault_set(c, RRCH_FLT(LOOP_HIGH_R), timer_run(&ch->t_loop_high, high_r && cmp == 1u, 200));
    if (ch->iox_d_known) {
        /* analog alone disagreeing with two agreeing hardware channels is a diagnostic discrepancy only */
        disagree = false;
        rrch_fault_set(c, RRCH_FLT(LOOP_DISCREPANCY), ab_disc || timer_run(&ch->t_loop_disc, ana != 3u && ((cmp == 0u && !b_open) != (ana == 0u)), 200));
    }
    if (!disagree) {
        ch->loop_disc_latched = false;
    } else if (ch->t_loop_fail == 0u) {
        ch->loop_disc_latched = latched_now; /* latched when the disagreement began */
    }
    if (timer_run(&ch->t_loop_fail, ch->loop_disc_latched && disagree, 5)) {
        if (!(c->faults & RRCH_FLT(LOOP_FAIL))) {
            ch->loop_cause = RRCH_LC_A_ANALOG_DISAGREE;
        }
        rrch_fault_set(c, RRCH_FLT(LOOP_FAIL), true);
    }
    if (ab_disc && b_open && cmp == 0u && ch->loop_cause == RRCH_LC_NONE) {
        ch->loop_cause = RRCH_LC_B_OPEN_OR_TEST_PATH_B; /* B (or Q_LTB stuck on) says open, A and analog closed */
    } else if (ab_disc && !b_open && cmp == 1u && ana == 0u && ch->loop_cause == RRCH_LC_NONE) {
        ch->loop_cause = RRCH_LC_A_OPEN_OR_TEST_PATH_A; /* stage 5 H3 (analog from LOOP_SNS): A or Q_LTA stuck on */
    } else if (!(c->faults & (RRCH_FLT(LOOP_FAIL) | RRCH_FLT(LOOP_DISCREPANCY))) &&
               (ch->loop_cause == RRCH_LC_B_OPEN_OR_TEST_PATH_B || ch->loop_cause == RRCH_LC_A_OPEN_OR_TEST_PATH_A)) {
        ch->loop_cause = RRCH_LC_NONE;
    }
    bool lab_code = ch->pres == RRCH_PRES_HEAD_VIA_LAB_EXTENSION || ch->pres == RRCH_PRES_LAB_EXTENSION_ONLY;

    /* --- node decode: which readbacks show their own element (upstream node live) --- */
    bool n1 = st & RRCH_DI(MODE_RUN), n2 = st & RRCH_DI(ESTOP_A), n3 = st & RRCH_DI(HANDS_ON), n4a = st & RRCH_DI(CHG_COVER);
    bool n4 = st & RRCH_DI(CHG_PLUG_LINK), n5 = st & RRCH_DI(HEAD_DOCK), n8a = st & RRCH_DI(BODY_BUMPER_L), n8 = st & RRCH_DI(BODY_BUMPER_R);
    bool n9 = st & RRCH_DI(WDG_OK);
    bool u21 = (st & RRCH_DI(HEAD_LOOP_OK)) != 0, u22 = (st & RRCH_DI(LAB_KEY_N)) != 0;
    bool lb = ch->lt_phase != 0u ? ch->lt_snap_b : ch->loop_b; /* loop self-test: channel B from before it */
    bool u21b = ch->iox_d_known && lb; /* stage 3: U21B (channel B) between CH_N6A and CH_N6 */
    bool n7a = n5 && u21 && u22;
    bool n7 = n7a && u21b; /* CH_N7 inferred: no readback behind the photo-MOS U21/U21B/U22 */
    bool n7_dead = !n7a || (ch->iox_d_known && !lb); /* known dead (an unreadable IOX_D proves nothing) */
    uint32_t known = ~RB_NODE_MASK | RRCH_DI(MODE_RUN);
    known |= n1 ? RRCH_DI(ESTOP_A) : 0u;
    known |= n2 ? RRCH_DI(HANDS_ON) : 0u;
    known |= n3 ? RRCH_DI(CHG_COVER) : 0u;
    known |= n4a ? RRCH_DI(CHG_PLUG_LINK) : 0u;
    known |= n4 ? RRCH_DI(HEAD_DOCK) : 0u;
    known |= n7 ? RRCH_DI(BODY_BUMPER_L) : 0u;
    known |= n8a ? RRCH_DI(BODY_BUMPER_R) : 0u;
    known |= n8 ? RRCH_DI(WDG_OK) : 0u;
    ch->rb_known = known;
    /* a node that is live behind a dead upstream node: harness short to a live conductor, readback
     * fault, or a shorted photo-MOS U21/U22 (safety_chain.md section 6 rows 8, 16, 23, 31, 32) */
    bool impl = (n2 && !n1) || (n3 && !n2) || (n4a && !n3) || (n4 && !n4a) || (n5 && !n4) || (n8a && n7_dead) || (n8 && !n8a) || (n9 && !n8);
    float bf_ms = CFG(c, CHAIN_BACKFEED_MS);
    ch->backfeed = bf_ms > 0.0f && (float)(c->now_us - ch->ce_live_us) < bf_ms * 1000.0f;
    if (timer_run(&ch->t_implausible, impl && !ch->backfeed, 20)) { /* back-fed nodes are not a fault (review M1) */
        rrch_fault_set(c, RRCH_FLT(CHAIN_IMPLAUSIBLE), true);
    }
    chain_end_step(c);

    rrch_el_state_t eb = (st & RRCH_DI(ESTOP_B)) ? RRCH_ELS_CLOSED : RRCH_ELS_OPEN;
    ch->el[RRCH_EL_MODE_RUN] = n1 ? RRCH_ELS_CLOSED : RRCH_ELS_OPEN;
    ch->el[RRCH_EL_ESTOP] = el_and(node_el(st, known, RRCH_DI(ESTOP_A)), eb);
    ch->el[RRCH_EL_HANDS_ON] = node_el(st, known, RRCH_DI(HANDS_ON));
    ch->el[RRCH_EL_CHG_COVER] = el_and(node_el(st, known, RRCH_DI(CHG_COVER)), node_el(st, known, RRCH_DI(CHG_PLUG_LINK)));
    ch->el[RRCH_EL_HEAD_DOCK] = node_el(st, known, RRCH_DI(HEAD_DOCK));
    ch->el[RRCH_EL_HEAD_LOOP] = (ch->loop_state == 0u && u21b) ? RRCH_ELS_CLOSED : RRCH_ELS_OPEN;
    ch->el[RRCH_EL_LAB_KEY_N] = (u22 && !lab_code) ? RRCH_ELS_CLOSED : RRCH_ELS_OPEN;
    ch->el[RRCH_EL_BODY_BUMPER] = el_and(node_el(st, known, RRCH_DI(BODY_BUMPER_L)), node_el(st, known, RRCH_DI(BODY_BUMPER_R)));
    ch->el[RRCH_EL_WDG_OK] = node_el(st, known, RRCH_DI(WDG_OK));
    ch->el[RRCH_EL_ARM_PERMIT] = (n9 && ch->chain_end_known) ? (ch->chain_end ? RRCH_ELS_CLOSED : RRCH_ELS_OPEN) : RRCH_ELS_UNKNOWN;

    /* CHAIN events: a known readback whose state differs from the last reported one */
    for (int i = 0; i < RRCH_DI_CHAIN_EVENT_N; i++) {
        uint32_t bit = 1u << i;
        if ((known & bit) && ((st ^ ch->rb_reported) & bit)) {
            ch->rb_reported ^= bit;
            rrch_event(c, RRCH_EV_CHAIN, i, (st & bit) != 0, 0);
        }
    }

    /* --- plausibility faults --- */
    bool ea = (st & RRCH_DI(ESTOP_A)) != 0, ebc = eb == RRCH_ELS_CLOSED;
    if (timer_run(&ch->t_estop_disc, n1 && ea != ebc, 200)) { /* pole A is only visible while CH_N1 is live */
        rrch_fault_set(c, RRCH_FLT(ESTOP_DISCREPANCY), true);
    }
    bool latch = (st & RRCH_DI(HW_LATCH)) != 0;
    if (timer_run(&ch->t_latch_stuck, latch && !c->out.arm_permit && c->boot_done, 100)) {
        rrch_fault_set(c, RRCH_FLT(LATCH_STUCK), true);
    }
    if (timer_run(&ch->t_iox, !in->iox_ok, 5)) {
        rrch_fault_set(c, RRCH_FLT(IOX_A), true);
    }
    if (!in->io_cfg_ok) {
        rrch_fault_set(c, RRCH_FLT(PIN_CONFIG), true); /* review M2/M3: a tap pin or expander pin not an input */
    }
    if (timer_run(&ch->t_adc, !in->adc_ok, 5)) {
        rrch_fault_set(c, RRCH_FLT(ADC), true);
    }
    rrch_fault_set(c, RRCH_FLT(BRIDGE_L), (st & RRCH_DI(DRV_FAULT_L)) != 0);
    rrch_fault_set(c, RRCH_FLT(BRIDGE_R), (st & RRCH_DI(DRV_FAULT_R)) != 0);

    /* --- live hardware causes: only elements known to be open --- */
    uint32_t hw = 0;
    if (ch->el[RRCH_EL_MODE_RUN] == RRCH_ELS_OPEN) {
        hw |= RRCH_HW(MODE_NOT_RUN);
    }
    if (ch->el[RRCH_EL_ESTOP] == RRCH_ELS_OPEN) {
        hw |= RRCH_HW(ESTOP);
    }
    if (ch->el[RRCH_EL_HANDS_ON] == RRCH_ELS_OPEN) {
        hw |= RRCH_HW(HANDS_ON);
    }
    /* charger: cover/plug element open, or (with those nodes dead upstream, e.g. selector in SERVICE)
     * the charger itself reports input power */
    if (ch->el[RRCH_EL_CHG_COVER] == RRCH_ELS_OPEN || (c->pwr.charger_ok && c->pwr.chg_input)) {
        hw |= RRCH_HW(CHARGER);
    }
    if (ch->el[RRCH_EL_HEAD_DOCK] == RRCH_ELS_OPEN) {
        hw |= RRCH_HW(HEAD_UNDOCKED);
    }
    if (ch->pres == RRCH_PRES_ABSENT) {
        hw |= RRCH_HW(J1_ABSENT);
    } else if (ch->loop_state == 1u) {
        hw |= RRCH_HW(HEAD_LOOP_OPEN);
    }
    if (ch->loop_state == 2u) {
        hw |= RRCH_HW(HEAD_LOOP_SHORT);
    }
    /* U31 passes only a direct head (3.92-5.64 kOhm): with no head the comparator is open too, which is
     * J1_ABSENT / presence FAULT, not LAB. LAB = LAB code decoded, or the comparator open while the
     * decode says a direct head (disagreement, fail-safe). */
    if (lab_code || (!u22 && ch->pres == RRCH_PRES_HEAD_DIRECT)) {
        hw |= RRCH_HW(LAB_KEY);
    }
    if (ch->el[RRCH_EL_BODY_BUMPER] == RRCH_ELS_OPEN) {
        hw |= RRCH_HW(BODY_BUMPER);
    }
    if (ch->el[RRCH_EL_WDG_OK] == RRCH_ELS_OPEN) {
        hw |= RRCH_HW(WATCHDOG);
    }
    bool bt_running = c->bt.state == RRCH_BT_RUNNING;
    /* (the 50 ms permit hold after a latch fall is a consequence of the drop, not a cause) */
    if (!c->out.arm_permit && c->boot_done && !bt_running && c->mode != RRCH_MODE_SERVICE_CHARGE && c->mode != RRCH_MODE_LAB && ch->drop_ms >= 60u) {
        /* S5: withheld because a REARM contact is held: say so */
        hw |= (ch->rearm_held_ms > 2000u || ch->rearm_set_held_ms > 2000u) ? RRCH_HW(REARM_HELD) : RRCH_HW(MCU_NOT_READY);
    }
    if (c->faults & RRCH_FLT(PERMIT_STUCK_OFF)) {
        hw |= RRCH_HW(MCU_NOT_READY); /* the ARM_PERMIT element does not close (fails safe) */
    }
    bool vlow = timer_run(&ch->t_vmot_low, latch && in->vmot_v < CFG(c, BRK_VMOT_MIN_V), 100);
    bool vhigh = timer_run(&ch->t_vmot_high, !latch && in->vmot_v > CFG(c, BRK_VMOT_OFF_V), (uint16_t)CFG(c, BRK_VMOT_DECAY_MAX_MS));
    bool bl = (st & RRCH_DI(BRAKE_L)) != 0, br = (st & RRCH_DI(BRAKE_R)) != 0;
    /* relay readback against the latch, judged only while the readback is valid. After the latch is
     * set the bridges stay asleep until both relays read "connected" (relays_ok), so the pick-up of
     * both relays is proven on every arming before any PWM. */
    bool brb = timer_run(&ch->t_brake_rb, rb_valid && (bl != latch || br != latch) && !bt_running, 200);
    if (!latch) {
        ch->relays_ok = false;
    } else if (rb_valid && bl && br) {
        ch->relays_ok = true;
    }
    if (vlow || vhigh || brb) {
        hw |= RRCH_HW(VMOT_FAULT);
    }
    uint32_t prev_live = ch->hw_live;
    ch->hw_live = hw;

    /* --- REARM qualification (review C1, m3; safety_chain.md rows 39, 40, 42, 43) ---
     * HW_LATCH_RB is the tap on RUN_12V = CHAIN_END through K1 pole B: it reads high only while the chain
     * is live AND K1 is closed. A rise is legitimate only within 250 ms after a REARM_BTN edge that the
     * firmware saw while every element read closed, ARM_PERMIT was high and the latch was down. */
    bool rb_now = (st & RRCH_DI(BTN_REARM)) != 0;
    bool all_closed = true, others_closed = true;
    for (int e = 0; e < RRCH_EL_N; e++) {
        all_closed = all_closed && ch->el[e] == RRCH_ELS_CLOSED;
        others_closed = others_closed && (e == RRCH_EL_ARM_PERMIT || ch->el[e] == RRCH_ELS_CLOSED);
    }
    bool qual_now = all_closed && !latch && c->boot_done && c->out.arm_permit;
    if (ch->rearm_set_edge_us == c->now_us) {
        ch->set_edge_ok = qual_now; /* S3: the set line's edge is qualified like the aux edge */
    }
    if (rb_now && !ch->rearm_prev) {
        ch->rearm_edge_us = c->now_us;
        ch->rearm_edge_ok = qual_now;
        if (!ch->rearm_edge_ok && !latch) {
            /* pressed before the chain closed: refuse it by holding ARM_PERMIT low for longer than the
             * C_SET set pulse can hold K1 (245 ms above must-release, review m3) */
            ch->rearm_block_until_us = c->now_us + 300000u;
        }
        if (!latch) {
            /* N1: every press with the latch down gets an outcome: the latch rises, or REARM_REFUSED with a reason */
            ch->press_pending = true;
            ch->press_us = c->now_us;
            ch->press_why = ch->rearm_why;
        }
    }
    bool aux_raw = (in->di & RRCH_DI(BTN_REARM)) != 0u;
    if (!aux_raw && ch->aux_raw_prev) {
        ch->aux_open_us = c->now_us;
    }
    ch->aux_raw_prev = aux_raw;
    ch->rearm_prev = rb_now;
    ch->rearm_held_ms = rb_now ? (ch->rearm_held_ms < 0x7FFFFFFFu ? ch->rearm_held_ms + 1u : ch->rearm_held_ms) : 0u;
    rrch_fault_set(c, RRCH_FLT(REARM_HELD), (!latch && (ch->rearm_held_ms > 2000u || ch->rearm_set_held_ms > 2000u)) || ch->latched_held_ms > REARM_HELD_LATCHED_MS); /* held / welded REARM: permit withheld */
    /* F5: the two REARM contact lines must agree; F17: both closing edges within 100 ms (+ the 10 ms IOX_D
     * sampling) and the rise within the window after the later one */
    rrch_fault_set(c, RRCH_FLT(REARM_DISCREPANCY), timer_run(&ch->t_rearm_disc, ch->rearm_set != rb_now, 200));
    ch->rearm_set_held_ms = ch->rearm_set ? ch->rearm_set_held_ms + 1u : 0u;

    /* legitimacy of a latch rise (C1, F17, stage 4 G4): both contact lines are sampled at 1 kHz and the set stage needs
     * >= 3.2 ms of set-contact closure, so every press that can set shows both closing edges. Stage-4 review S3: the
     * set-contact readback (GPB6) has a thin high-level margin. A rise with ONE line showing a qualified press (edge
     * seen with every element closed, ARM_PERMIT high, latch down, within the window, and that contact still closed or
     * released < 20 ms before the rise) while the other line showed nothing is a readback fault, not an unexplained
     * latch: REARM_RB_FAULT (warning, sticky until reset, withholds every later arming). A rise with NEITHER line showing
     * a qualified press stays LATCH_NO_REARM (fatal). */
    uint64_t a_e = ch->rearm_edge_us, b_e = ch->rearm_set_edge_us;
    bool both = a_e != 0u && b_e != 0u && (a_e > b_e ? a_e - b_e : b_e - a_e) <= 110000u;
    if (latch && !ch->latch) {
        uint64_t win = 250000u + 1000u * (uint64_t)CFG(c, CHAIN_CLOSE_DEBOUNCE_MS);
        uint64_t later = b_e > a_e ? b_e : a_e;
        bool legit = ch->rearm_edge_ok && both && c->now_us - later <= win;
        bool aux_level = (in->di & RRCH_DI(BTN_REARM)) != 0u || (ch->aux_open_us >= a_e && c->now_us - ch->aux_open_us < 20000u);
        bool set_level = ch->rearm_set || (ch->set_open_us >= b_e && c->now_us - ch->set_open_us < 20000u);
        bool aux_press = ch->rearm_edge_ok && a_e != 0u && c->now_us - a_e <= win && aux_level;
        bool set_press = ch->set_edge_ok && b_e != 0u && c->now_us - b_e <= win && set_level;
        ch->rearm_edge_ok = false;
        ch->set_edge_ok = false;
        ch->held_drop = false;
        ch->lt_passed = false; /* G5: a fresh loop self-test before the next arming */
        if (!legit) {
            if (aux_press != set_press) {
                rrch_fault_set(c, RRCH_FLT(REARM_RB_FAULT), true); /* one contact line missed the press (S3) */
                ch->rb_fault_line = aux_press ? 1u : 2u;        /* 1: set line (GPB6) missed, 2: aux line missed */
            } else {
                rrch_fault_set(c, RRCH_FLT(LATCH_NO_REARM), true); /* welded K1, K1_SET short, RUN_12V short */
            }
        }
    }
    /* N1: outcome of a press made with the latch down */
    if (ch->press_pending) {
        if (latch) {
            ch->press_pending = false;
            ch->rearm_refusal = RRCH_RREF_NONE;
        } else if (c->now_us - ch->press_us >= 300000u) {
            ch->press_pending = false;
            /* offered (NONE) and not set: a set-contact closure shorter than the 11.2 ms maximum qualification time is
             * TOO_SHORT (nothing happened, G4); otherwise SET_FAILED */
            bool short_set = ch->set_close_us != 0u && ch->set_open_us > ch->set_close_us && ch->set_open_us - ch->set_close_us < 12000u &&
                             ch->set_close_us + 110000u >= ch->press_us;
            uint8_t why = ch->press_why;
            if (why == RRCH_RREF_NONE) {
                why = (short_set || ch->set_close_us + 110000u < ch->press_us) ? RRCH_RREF_TOO_SHORT
                      : (c->faults & RRCH_FLT(COIL_HOT))                    ? RRCH_RREF_COIL_HOT /* H2: margin not guaranteed */
                                                                            : RRCH_RREF_SET_FAILED;
            }
            ch->rearm_refusal = why;
            rrch_event(c, RRCH_EV_REARM_REFUSED, ch->rearm_refusal, 0, 0);
            ch->refused_us = c->now_us;
        }
    }
    /* W-018: a REARM contact still closed 2 s after the latch rose (held, welded, or a body against the button) */
    /* S5 / stage 5 H6: the hardware sets the latch 7-15 ms into a press, so the firmware cannot know the press length
     * before the rise and cannot defer the set (the set pulse ends at most 170 ms after closure; ARM_PERMIT low during
     * it only makes the press fail). So: the buzzer beeps fast from 1 s of holding after the rise ("release"), the drop
     * at 5 s carries the latched reason REARM_HELD and a REARM_REFUSED {why: REARM_HELD_AFTER_SET, latch_dropped}. */
    ch->latched_held_ms = (latch && (rb_now || ch->rearm_set)) ? (ch->latched_held_ms < 0x7FFFFFFFu ? ch->latched_held_ms + 1u : ch->latched_held_ms) : 0u;
    if (ch->latched_held_ms > REARM_HELD_LATCHED_MS) {
        rrch_fault_set(c, RRCH_FLT(REARM_HELD), true);
        if (!ch->held_drop) {
            ch->rearm_refusal = RRCH_RREF_REARM_HELD_AFTER_SET;
            rrch_event(c, RRCH_EV_REARM_REFUSED, RRCH_RREF_REARM_HELD_AFTER_SET, 1, 0);
            ch->refused_us = c->now_us;
        }
        ch->held_drop = true;
    }
    /* G5: loop self-test before every arming: latch down, every element (but ARM_PERMIT) closed for 100 ms, ARM_PERMIT
     * and CHAIN_END high, IOX_D known, no REARM contact closed, no brake test, no fatal fault */
    if (latch || !others_closed) {
        ch->lt_passed = ch->lt_passed && latch; /* an element opened: test again before the next arming */
    }
    ch->closed_ms = (!latch && others_closed && ch->hw_live == 0u) ? (ch->closed_ms < 60000u ? ch->closed_ms + 1u : ch->closed_ms) : 0u;
    bool lt_start = !latch && c->boot_done && !ch->lt_passed && ch->closed_ms >= 100u && c->out.arm_permit && ch->chain_end_known && ch->chain_end &&
                    ch->iox_d_known && !rb_now && !ch->rearm_set && c->bt.state != RRCH_BT_RUNNING && !(c->faults & RRCH_FLT_FATAL_MASK);
    if (latch && ch->lt_phase != 0u) {
        ch->lt_phase = 0; /* never while latched (each test opens the chain) */
        ch->lt_out = 0;
    }
    loop_test_step(c, lt_start);
    loop_diag_step(c, latch);
    /* low-battery re-arm warning (lead item 6): re-arming needs SET_READY (>= 11.7 V worst case) while the
     * battery-low stop is lower; warn (2 s filter, 0.2 V hysteresis) before re-arming becomes impossible */
    float vb = c->in.vbat_v, vw = CFG(c, REARM_VBAT_WARN_V);
    bool vlow_now = (c->faults & RRCH_FLT(BATTERY_REARM_LOW)) ? vb < vw + 0.2f : vb <= vw;
    rrch_fault_set(c, RRCH_FLT(BATTERY_REARM_LOW), c->boot_done && timer_run(&ch->t_vbat_warn, vlow_now, 10000)); /* stage 5 H5 */
    /* stage 5 H2: K1 coil estimate = RT1 (now beside K1) - configured offset + self-heating 10 K x f, f = latch-set
     * state filtered with tau 300 s. COIL_HOT above 45 C is a warning only: the press is still offered */
    ch->coil_f += ((latch ? 1.0f : 0.0f) - ch->coil_f) * 3.3333e-6f;
    float tcoil = c->in.ntc_c[2] - CFG(c, REARM_NTC_OFFSET_K) + CFG(c, REARM_COIL_SELFHEAT_K) * ch->coil_f;
    ch->coil_c = tcoil;
    rrch_fault_set(c, RRCH_FLT(COIL_HOT), c->boot_done && !(tcoil <= REARM_COIL_MAX_C));
    ch->rearm_why = latch ? RRCH_RREF_NONE : rearm_why(c, others_closed);
    if (timer_run(&ch->t_latch_boot, latch && !c->boot_done, 40)) {
        rrch_fault_set(c, RRCH_FLT(LATCH_NO_REARM), true); /* latch readback high at boot (ARM_PERMIT is low) */
    }
    /* an element known open while the latch still reads set: the hardware did not drop (K1 takes 4 ms,
     * contact-to-resistor 10.5 ms; the loop has its own faster rule above) */
    bool open_el = false;
    for (int e = 0; e < RRCH_EL_N; e++) {
        open_el = open_el || (e != RRCH_EL_HEAD_LOOP && ch->el[e] == RRCH_ELS_OPEN);
    }
    if (timer_run(&ch->t_no_drop, latch && open_el && c->boot_done, 30)) {
        rrch_fault_set(c, RRCH_FLT(LATCH_NO_DROP), true);
    }

    /* any fall of the latch readback is made a complete drop: an opening shorter than K1's release time
     * (4 ms) removes RUN_12V for a moment but would let K1 hold and RUN_12V return with no REARM (review m4) */
    if (!latch && ch->latch) {
        ch->drop_ms = 0;
    } else if (ch->drop_ms < 60000u) {
        ch->drop_ms++;
    }

    /* --- latched hardware reasons --- */
    if (latch != ch->latch) {
        ch->latch = latch;
        if (!latch) {
            ch->hw_latched = hw | prev_live; /* causes seen just before the drop count too */
            if (ch->held_drop) {
                ch->hw_latched = (ch->hw_latched & ~RRCH_HW(LATCH_UNEXPLAINED)) | RRCH_HW(REARM_HELD); /* W-018 / S5 */
            }
            ch->held_drop = false;
            if (ch->hw_latched == 0 && !bt_running) {
                ch->hw_latched = RRCH_HW(LATCH_UNEXPLAINED); /* drop that no readback explains (contract draft7) */
            }
        } else if (!(c->faults & (RRCH_FLT(LATCH_NO_REARM)))) {
            ch->hw_latched = 0;
        }
        rrch_event(c, RRCH_EV_HW_LATCH, latch, (int32_t)ch->hw_latched, 0);
    } else if (!latch && c->boot_done) {
        ch->hw_latched |= hw;
    }
}

bool rrch_rearm_blocked(const rrch_t *c)
{
    const rrch_chain_t *ch = &c->chain;
    /* latch down: no arming while a REARM contact is held or the two contacts disagree, while IOX_D cannot
     * be read, or while K1 pole A does not read released (F1, F2, F5) */
    bool raw_latch = (c->in.di & RRCH_DI(HW_LATCH)) != 0;
    if (ch->latch || raw_latch) {
        return ch->latched_held_ms > REARM_HELD_LATCHED_MS; /* W-018 / stage 5 H6 */
    }
    if (c->now_us < ch->unheld_until_us) {
        return true; /* N2: K1 sealed in without U_HOLD: release it */
    }
    /* K1 must read released before ARM_PERMIT is raised (F2): blocks raising only, never withdraws */
    bool k1_unproven = !c->out.arm_permit && !(ch->iox_d_known && ch->k1_nc);
    return c->now_us < ch->rearm_block_until_us || ch->rearm_held_ms > 2000u || ch->rearm_set_held_ms > 2000u ||
           (c->faults & (RRCH_FLT(REARM_DISCREPANCY) | RRCH_FLT(SET_STAGE_FAULT) | RRCH_FLT(REARM_RB_FAULT))) || !ch->iox_d_known || k1_unproven;
}
