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
#define IMM_HIGH_MASK (RRCH_DI(BTN_REARM) | RRCH_DI(BTN_PAUSE) | RRCH_DI(HEAD_LOOP_SHORT) | RRCH_DI(DRV_FAULT_L) | RRCH_DI(DRV_FAULT_R) | RRCH_DI(BUS_CLAMP))

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

/* stage 3 F1: a read is good only with the fixed pattern P4 = 1, P5..P7 = 0 */
void rrch_iox_d_update(rrch_t *c, bool ok, uint8_t in, uint64_t t_us)
{
    rrch_iox_d_t *d = &c->chain.iox_d;
    if (ok && (in & 0xF0u) == 0x10u) {
        d->ok = true;
        d->val = in;
        d->t_us = t_us;
        d->fail_n = 0;
    } else {
        d->ok = false;
        d->fail_n = d->fail_n < 1000000u ? d->fail_n + 1u : d->fail_n;
    }
}

bool rrch_iox_d_fast(const rrch_t *c)
{
    const rrch_chain_t *ch = &c->chain;
    if (ch->latch) {
        return ch->judge_pending || c->now_us - ch->raw_latch_since_us < 300000u;
    }
    return ch->chain_end || ch->press_pending || ch->judge_pending || (c->in.di & RRCH_DI(BTN_REARM)) != 0u;
}

/* --- round 4 N1: conservative timed model of the C_SET charge (the board has no C_SET readback) ---
 * electronics/analysis/chassis_braking_tables.md T11: C_SET 100 uF charged from CHAIN_END through D_RSET (0.4 V) and
 * R_SET 22 k, dumped into the K1 coil (1028 ohm at 23 C, +0.393 %/K) while U_SET conducts (set gate ~110 ms, cut short
 * when the set contact opens), emptied by Q_SDIS within ~0.3 s whenever CHAIN_END is dead. K1 operates when the coil
 * current exceeds 8.75 mA (9 V at 23 C) for the 4 ms operate time. Every constant below errs towards a LOWER modelled
 * voltage / HIGHER needed voltage, so rearm_ready can be late but not early. */
#define CSET_KC 3.7446e-4f      /* 1 - exp(-1 ms / 2.67 s): 22 k (1 %) x 120 uF (C_SET +20 % [A]; T11 states -20 %) */
#define CSET_KD 0.98582f        /* exp(-1 ms / 70 ms): dump through the coil, 1028 ohm -15 % x 80 uF (fastest) [A] */
#define CSET_DIODE_V 0.5f       /* D_RSET at the end of charge 0.4 V [A] + 0.1 V */
#define CSET_SUPPLY_LOSS_V 0.3f /* VBAT reading to CHAIN_END: chain photo-MOS, fuses, ADC error [A] */
#define K1_OPERATE_A 8.75e-3f   /* T11 must-operate current (ampere-turns: the same at any temperature) */
#define K1_COIL_OHM_23 1028.0f
#define K1_COIL_TC 0.00393f
#define K1_COIL_RISE_K 10.0f    /* coil above the board NTC (warm from an earlier seal-in) [A] */
#define K1_COIL_UNKNOWN_C 60.0f /* board NTC unreadable [A] */
#define K1_OPERATE_MARGIN 1.07f /* current above must-operate for the whole 4 ms operate time: exp(4/70) + 1 % */
#define SET_GATE_US 115000u     /* set gate 110 ms + 5 ms */
static void cset_model_step(rrch_t *c, bool aux, bool set)
{
    rrch_chain_t *ch = &c->chain;
    float tb = c->in.ntc_c[2];
    float tcoil = isfinite(tb) ? tb + K1_COIL_RISE_K : K1_COIL_UNKNOWN_C;
    float rc = K1_COIL_OHM_23 * (1.0f + K1_COIL_TC * (tcoil - 23.0f));
    rc = rc < 700.0f ? 700.0f : rc;
    ch->cset_need_v = K1_OPERATE_A * rc * K1_OPERATE_MARGIN;
    float vb = c->in.vbat_v;
    ch->cset_target_v = isfinite(vb) ? vb - CSET_SUPPLY_LOSS_V - CSET_DIODE_V : 0.0f;
    uint64_t last = ch->rearm_edge_us > ch->rearm_set_edge_us ? ch->rearm_edge_us : ch->rearm_set_edge_us;
    bool dumping = (aux || set) && last != 0u && c->now_us - last <= SET_GATE_US;
    if (!(ch->chain_end_known && ch->chain_end)) {
        ch->cset_model_v = 0.0f; /* Q_SDIS: assumed empty at once */
    } else if (dumping) {
        ch->cset_model_v *= CSET_KD;
    } else if (ch->cset_target_v > ch->cset_model_v) {
        ch->cset_model_v += (ch->cset_target_v - ch->cset_model_v) * CSET_KC;
    }
}

/* what a REARM press would meet now (latch down) */
static uint8_t rearm_why(const rrch_t *c, bool others_closed)
{
    const rrch_chain_t *ch = &c->chain;
    if (!c->boot_done || c->mode == RRCH_MODE_FAULT || c->mode == RRCH_MODE_BOOT || c->mode == RRCH_MODE_LAB || c->mode == RRCH_MODE_SERVICE_CHARGE ||
        (c->faults & RRCH_FLT_FATAL_MASK)) {
        return RRCH_RREF_FAULT_OR_MODE;
    }
    if (ch->rearm_held_ms > 2000u || ch->rearm_set_held_ms > 2000u) {
        return RRCH_RREF_REARM_HELD;
    }
    if (!others_closed || (ch->hw_live & ~RRCH_HW(MCU_NOT_READY)) != 0u) {
        return RRCH_RREF_CHAIN_OPEN;
    }
    if (!c->out.arm_permit || ch->el[RRCH_EL_ARM_PERMIT] != RRCH_ELS_CLOSED) {
        return RRCH_RREF_PERMIT_WITHHELD;
    }
    if (ch->cset_target_v < ch->cset_need_v + 0.1f) {
        return RRCH_RREF_SUPPLY_LOW;
    }
    if (ch->cset_model_v < ch->cset_need_v) {
        return RRCH_RREF_RESERVOIR_LOW;
    }
    return RRCH_RREF_NONE;
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
        ch->k1_nc = (xd->val & 1u) != 0;     /* HIGH = K1 pole A released */
        ch->k1_run = (xd->val & 2u) != 0;    /* HIGH = CHAIN_END live AND K1 pole B closed (before U_HOLD) */
        ch->loop_b = (xd->val & 4u) != 0;    /* HIGH = loop channel B (U46) sees the loop closed */
        ch->rearm_set = (xd->val & 8u) != 0; /* HIGH = REARM set contact closed */
    } else {
        ch->k1_nc = ch->k1_run = ch->loop_b = ch->rearm_set = false; /* unknown counts as "not healthy" */
    }
    if (d_new) {
        rrch_iox_d_t *xw = &ch->iox_d;
        xw->seen_us = xd->t_us;
        if (ch->rearm_set && !ch->rearm_set_prev) {
            ch->rearm_set_edge_us = xd->t_us;
        }
        ch->rearm_set_prev = ch->rearm_set;
        if ((in->di & RRCH_DI(BTN_REARM)) && ch->n_xd_in_press < 255u) {
            ch->n_xd_in_press++; /* N2: IOX_D samples taken while the aux contact was closed (raw line) */
        }
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
         * SET_INCOMPLETE. K1_WELD needs pole A still operated, or K1_RUN live, with CHAIN_END known dead (ARM_PERMIT low >= 30 ms). */
        bool ce_dead = !c->out.arm_permit && hist_all(ch->permit_hist, 0u, 30u, false);
        bool k1_closed = !ch->k1_nc || ch->k1_run;
        bool unheld = !raw_latch && k1_closed && !ce_dead && c->boot_done;
        bool weld = !raw_latch && k1_closed && ce_dead && !in_pulse; /* K1_RUN live without CHAIN_END: fed from elsewhere */
        bool run_short = raw_latch && !ch->k1_run;
        ch->n_unheld = unheld ? (uint8_t)(ch->n_unheld + 1u) : 0u;
        if (ch->n_unheld >= 2u) {
            ch->unheld_until_us = c->now_us + 200000u;
            if (ch->press_pending || (ch->press_us != 0u && c->now_us - ch->press_us < 1000000u)) {
                ch->press_why = RRCH_RREF_SET_INCOMPLETE;
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
    uint32_t lo = in->loop_ohm;
    uint8_t ana = lo < 560u ? 2u : (lo > 1650u ? 1u : ((lo >= 620u && lo <= 1500u) ? 0u : 3u));
    ch->ana3 = ana;
    uint8_t anaw = ana == 3u ? cmp : ana;
    ch->loop_state = (cmp == 2u || anaw == 2u) ? 2u : ((cmp == 1u || anaw == 1u || (ch->iox_d_known && !ch->loop_b)) ? 1u : 0u);
    bool disagree = ana != 3u && ((cmp == 0u) != (ana == 0u));
    bool latched_now = (st & RRCH_DI(HW_LATCH)) != 0;
    rrch_fault_set(c, RRCH_FLT(LOOP_DISCREPANCY), timer_run(&ch->t_loop_disc, disagree, 200));
    /* review C2: while latched, the loop is not only a warning. Any opening seen by either channel
     * (analog: 2 consecutive 1 kHz samples; comparator: immediate) withdraws ARM_PERMIT (U24 is upstream
     * of K1, so the latch drops even if U21 is held closed) and latches STOP_ESCALATED; a disagreement
     * lasting 5 ms while latched (the comparator lags the analog copy by about 1.5 ms) is LOOP_FAIL. */
    bool ana_bad = timer_run(&ch->t_loop_ana, ana == 1u || ana == 2u, 2);
    bool b_open = ch->iox_d_known && !ch->loop_b;
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
    /* round 4 N6: the channels have different thresholds (A opens above 1.55 kOhm, B only above 2.70 kOhm), so
     * a loop between them (analog 1.65-2.9 kOhm, i.e. B's threshold plus tolerance) is "A open, B closed" by
     * design: HEAD_LOOP_OPEN (arming withheld, A holds U21 open) plus the warning LOOP_HIGH_R, not a fault.
     * LOOP_FAIL only when a channel is provably stuck healthy: A closed with the analog copy above 1.65 kOhm,
     * or B closed with the analog copy above 2.9 kOhm. */
    bool high_r = lo > 1650u && lo <= 2900u;
    bool a_stuck = cmp == 0u && ana == 1u;
    bool b_stuck = !b_open && lo > 2900u;
    if (ab_t && (a_stuck || b_stuck)) {
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
        rrch_fault_set(c, RRCH_FLT(LOOP_FAIL), true);
    }
    bool lab_code = ch->pres == RRCH_PRES_HEAD_VIA_LAB_EXTENSION || ch->pres == RRCH_PRES_LAB_EXTENSION_ONLY;

    /* --- node decode: which readbacks show their own element (upstream node live) --- */
    bool n1 = st & RRCH_DI(MODE_RUN), n2 = st & RRCH_DI(ESTOP_A), n3 = st & RRCH_DI(HANDS_ON), n4a = st & RRCH_DI(CHG_COVER);
    bool n4 = st & RRCH_DI(CHG_PLUG_LINK), n5 = st & RRCH_DI(HEAD_DOCK), n8a = st & RRCH_DI(BODY_BUMPER_L), n8 = st & RRCH_DI(BODY_BUMPER_R);
    bool n9 = st & RRCH_DI(WDG_OK);
    bool u21 = (st & RRCH_DI(HEAD_LOOP_OK)) != 0, u22 = (st & RRCH_DI(LAB_KEY_N)) != 0;
    bool u21b = ch->iox_d_known && ch->loop_b; /* stage 3: U21B (channel B) between CH_N6A and CH_N6 */
    bool n7a = n5 && u21 && u22;
    bool n7 = n7a && u21b; /* CH_N7 inferred: no readback behind the photo-MOS U21/U21B/U22 */
    bool n7_dead = !n7a || (ch->iox_d_known && !ch->loop_b); /* known dead (an unreadable IOX_D proves nothing) */
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
    rrch_fault_set(c, RRCH_FLT(BUS_CLAMP), (st & RRCH_DI(BUS_CLAMP)) != 0);

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
        hw |= RRCH_HW(MCU_NOT_READY);
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
    if (rb_now && !ch->rearm_prev) {
        ch->rearm_edge_us = c->now_us;
        ch->rearm_edge_ok = all_closed && !latch && c->boot_done && c->out.arm_permit;
        ch->n_xd_in_press = 0;
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
    bool aux_raw = (in->di & RRCH_DI(BTN_REARM)) != 0u; /* undebounced: the release is debounced, the tap length is not */
    if (!aux_raw && ch->aux_raw_prev) {
        ch->press_end_us = c->now_us;
    }
    ch->aux_raw_prev = aux_raw;
    ch->rearm_prev = rb_now;
    cset_model_step(c, rb_now, ch->rearm_set); /* after the edge bookkeeping: a press dumps C_SET from its first ms */
    ch->rearm_held_ms = rb_now ? (ch->rearm_held_ms < 0x7FFFFFFFu ? ch->rearm_held_ms + 1u : ch->rearm_held_ms) : 0u;
    rrch_fault_set(c, RRCH_FLT(REARM_HELD), ch->rearm_held_ms > 2000u || ch->rearm_set_held_ms > 2000u); /* held / welded REARM: permit withheld */
    /* F5: the two REARM contact lines must agree; F17: both closing edges within 100 ms (+ the 10 ms IOX_D
     * sampling) and the rise within the window after the later one */
    rrch_fault_set(c, RRCH_FLT(REARM_DISCREPANCY), timer_run(&ch->t_rearm_disc, ch->iox_d_known && ch->rearm_set != rb_now, 200));
    ch->rearm_set_held_ms = ch->rearm_set ? ch->rearm_set_held_ms + 1u : 0u;
    if (ch->rearm_set_held_ms > 2000u) {
        rrch_fault_set(c, RRCH_FLT(REARM_HELD), true);
    }
    /* N2: legitimacy of a latch rise. The aux line (GPIO, 1 kHz) gives the timing; the set line is on IOX_D (1 kHz
     * while a press is possible, rrch_iox_d_fast, else 100 Hz). If the set edge has not been seen yet the judgement
     * waits for the first IOX_D sample taken after the rise (<= 50 ms). A tap so short that at most one IOX_D
     * sample fell inside it (<= 20 ms) cannot be confirmed on the set line and is accepted on the aux timing alone
     * (a set needs both contacts; neither line can be faked by a single stuck contact: a stuck set contact is
     * REARM_HELD and gives no edge). Anything else is LATCH_NO_REARM (welded K1, K1_SET short, RUN_12V short). */
    uint64_t a_e = ch->rearm_edge_us, b_e = ch->rearm_set_edge_us;
    bool both = a_e != 0u && b_e != 0u && (a_e > b_e ? a_e - b_e : b_e - a_e) <= 110000u;
    if (latch && !ch->latch) {
        uint64_t later = both && b_e > a_e ? b_e : a_e;
        bool timing = ch->rearm_edge_ok && a_e != 0u && c->now_us - later <= 250000u + 1000u * (uint64_t)CFG(c, CHAIN_CLOSE_DEBOUNCE_MS);
        ch->rearm_edge_ok = false;
        ch->judge_pending = timing && !both;
        ch->judge_rise_us = c->now_us;
        ch->held_drop = false;
        if (!timing) {
            rrch_fault_set(c, RRCH_FLT(LATCH_NO_REARM), true);
        }
    }
    if (ch->judge_pending) {
        bool sampled = ch->iox_d_known && ch->iox_d.t_us >= ch->judge_rise_us;
        bool short_tap = !aux_raw && ch->press_end_us >= a_e && ch->press_end_us - a_e <= 20000u && ch->n_xd_in_press <= 1u;
        if (both) {
            ch->judge_pending = false;
        } else if (sampled || c->now_us - ch->judge_rise_us > 50000u) {
            ch->judge_pending = false;
            if (!(sampled && short_tap)) {
                rrch_fault_set(c, RRCH_FLT(LATCH_NO_REARM), true);
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
            ch->rearm_refusal = ch->press_why != RRCH_RREF_NONE ? ch->press_why : RRCH_RREF_SET_FAILED;
            rrch_event(c, RRCH_EV_REARM_REFUSED, ch->rearm_refusal, 0, 0);
        }
    }
    /* W-018: a REARM contact still closed 2 s after the latch rose (held, welded, or a body against the button) */
    ch->latched_held_ms = (latch && (rb_now || ch->rearm_set)) ? (ch->latched_held_ms < 0x7FFFFFFFu ? ch->latched_held_ms + 1u : ch->latched_held_ms) : 0u;
    if (ch->latched_held_ms > 2000u) {
        rrch_fault_set(c, RRCH_FLT(REARM_HELD), true);
        ch->held_drop = true;
    }
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
                ch->hw_latched |= RRCH_HW(MCU_NOT_READY); /* W-018: ARM_PERMIT withdrawn, REARM held */
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
        return ch->latched_held_ms > 2000u; /* W-018 */
    }
    if (c->now_us < ch->unheld_until_us) {
        return true; /* N2: K1 sealed in without U_HOLD: release it */
    }
    /* K1 must read released before ARM_PERMIT is raised (F2): blocks raising only, never withdraws */
    bool k1_unproven = !c->out.arm_permit && !(ch->iox_d_known && ch->k1_nc);
    return c->now_us < ch->rearm_block_until_us || ch->rearm_held_ms > 2000u || ch->rearm_set_held_ms > 2000u ||
           (c->faults & RRCH_FLT(REARM_DISCREPANCY)) || !ch->iox_d_known || k1_unproven;
}
