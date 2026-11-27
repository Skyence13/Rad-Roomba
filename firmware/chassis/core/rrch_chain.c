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

void rrch_iox_b_update(rrch_t *c, bool ok, bool chain_end, uint64_t t_us)
{
    c->chain.iox_b.ok = ok;
    c->chain.iox_b.chain_end = chain_end;
    c->chain.iox_b.t_us = t_us;
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
    bool fresh = b->ok && b->t_us != 0u && b->t_us <= c->now_us && c->now_us - b->t_us <= 100000u;
    ch->chain_end_known = fresh;
    ch->chain_end = fresh && b->chain_end;
    rrch_fault_set(c, RRCH_FLT(IOX_B), c->boot_done && !fresh);
    if (!b->ok || b->t_us == ch->iox_b_seen_us || b->t_us > c->now_us) {
        return;
    }
    ch->iox_b_seen_us = b->t_us;
    uint32_t age = (uint32_t)((c->now_us - b->t_us + 500u) / 1000u);
    if (age > 31u - CE_SETTLE_MS) {
        return; /* too old to be compared with the history */
    }
    bool p_low = hist_all(ch->permit_hist, age, CE_SETTLE_MS, false), p_high = hist_all(ch->permit_hist, age, CE_SETTLE_MS, true);
    bool n9_live = hist_all(ch->n9_hist, age, CE_SETTLE_MS, true), n9_dead = hist_all(ch->n9_hist, age, CE_SETTLE_MS, false);
    ch->n_stuck_on = (p_low && b->chain_end) ? (uint8_t)(ch->n_stuck_on < 250u ? ch->n_stuck_on + 1u : 250u) : 0u;
    ch->n_stuck_off = (p_high && n9_live && !b->chain_end) ? (uint8_t)(ch->n_stuck_off < 250u ? ch->n_stuck_off + 1u : 250u) : 0u;
    ch->n_end_impl = (n9_dead && b->chain_end) ? (uint8_t)(ch->n_end_impl < 250u ? ch->n_end_impl + 1u : 250u) : 0u;
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
    uint8_t cmp = (st & RRCH_DI(HEAD_LOOP_SHORT)) ? 2u : ((st & RRCH_DI(HEAD_LOOP_OK)) ? 0u : 1u);
    uint8_t ana = (in->loop_ohm < 600u) ? 2u : ((in->loop_ohm > 1600u) ? 1u : 0u);
    ch->loop_state = (cmp == 2u || ana == 2u) ? 2u : ((cmp == 1u || ana == 1u) ? 1u : 0u);
    rrch_fault_set(c, RRCH_FLT(LOOP_DISCREPANCY), timer_run(&ch->t_loop_disc, cmp != ana, 200));
    bool lab_code = ch->pres == RRCH_PRES_HEAD_VIA_LAB_EXTENSION || ch->pres == RRCH_PRES_LAB_EXTENSION_ONLY;

    /* --- node decode: which readbacks show their own element (upstream node live) --- */
    bool n1 = st & RRCH_DI(MODE_RUN), n2 = st & RRCH_DI(ESTOP_A), n3 = st & RRCH_DI(HANDS_ON), n4a = st & RRCH_DI(CHG_COVER);
    bool n4 = st & RRCH_DI(CHG_PLUG_LINK), n5 = st & RRCH_DI(HEAD_DOCK), n8a = st & RRCH_DI(BODY_BUMPER_L), n8 = st & RRCH_DI(BODY_BUMPER_R);
    bool n9 = st & RRCH_DI(WDG_OK);
    bool u21 = (st & RRCH_DI(HEAD_LOOP_OK)) != 0, u22 = (st & RRCH_DI(LAB_KEY_N)) != 0;
    bool n7 = n5 && u21 && u22; /* CH_N7 inferred: no readback behind the photo-MOS U21/U22 */
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
    bool impl = (n2 && !n1) || (n3 && !n2) || (n4a && !n3) || (n4 && !n4a) || (n5 && !n4) || (n8a && !n7) || (n8 && !n8a) || (n9 && !n8);
    if (timer_run(&ch->t_implausible, impl, 20)) {
        rrch_fault_set(c, RRCH_FLT(CHAIN_IMPLAUSIBLE), true);
    }
    chain_end_step(c);

    rrch_el_state_t eb = (st & RRCH_DI(ESTOP_B)) ? RRCH_ELS_CLOSED : RRCH_ELS_OPEN;
    ch->el[RRCH_EL_MODE_RUN] = n1 ? RRCH_ELS_CLOSED : RRCH_ELS_OPEN;
    ch->el[RRCH_EL_ESTOP] = el_and(node_el(st, known, RRCH_DI(ESTOP_A)), eb);
    ch->el[RRCH_EL_HANDS_ON] = node_el(st, known, RRCH_DI(HANDS_ON));
    ch->el[RRCH_EL_CHG_COVER] = el_and(node_el(st, known, RRCH_DI(CHG_COVER)), node_el(st, known, RRCH_DI(CHG_PLUG_LINK)));
    ch->el[RRCH_EL_HEAD_DOCK] = node_el(st, known, RRCH_DI(HEAD_DOCK));
    ch->el[RRCH_EL_HEAD_LOOP] = ch->loop_state == 0u ? RRCH_ELS_CLOSED : RRCH_ELS_OPEN;
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
    if (timer_run(&ch->t_latch_stuck, latch && !c->out.arm_permit, 100)) {
        rrch_fault_set(c, RRCH_FLT(LATCH_STUCK), true);
    }
    if (timer_run(&ch->t_iox, !in->iox_ok, 5)) {
        rrch_fault_set(c, RRCH_FLT(IOX_A), true);
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
    if (!u22 || lab_code) {
        hw |= RRCH_HW(LAB_KEY);
    }
    if (ch->el[RRCH_EL_BODY_BUMPER] == RRCH_ELS_OPEN) {
        hw |= RRCH_HW(BODY_BUMPER);
    }
    if (ch->el[RRCH_EL_WDG_OK] == RRCH_ELS_OPEN) {
        hw |= RRCH_HW(WATCHDOG);
    }
    bool bt_running = c->bt.state == RRCH_BT_RUNNING;
    if (!c->out.arm_permit && c->boot_done && !bt_running && c->mode != RRCH_MODE_SERVICE_CHARGE && c->mode != RRCH_MODE_LAB) {
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

    /* --- latched hardware reasons --- */
    if (latch != ch->latch) {
        ch->latch = latch;
        if (!latch) {
            ch->hw_latched = hw | prev_live; /* causes seen just before the drop count too */
            if (ch->hw_latched == 0 && !bt_running) {
                ch->hw_latched = RRCH_HW(VMOT_FAULT); /* drop that no readback explains */
            }
        } else {
            ch->hw_latched = 0;
        }
        rrch_event(c, RRCH_EV_HW_LATCH, latch, (int32_t)ch->hw_latched, 0);
    } else if (!latch && c->boot_done) {
        ch->hw_latched |= hw;
    }
}
