/* Chain supervision: 1 kHz debounce with immediate latching of the "unsafe" direction, J1
 * presence-code decode, interlock-loop decode, live hardware-cause decode, latched hardware
 * reasons. Observes the hardwired chain; has no means of closing it. */
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

static void di_changed(rrch_t *c, int i, bool v)
{
    if (i < RRCH_DI_CHAIN_EVENT_N) {
        rrch_event(c, RRCH_EV_CHAIN, i, v, 0);
    } else if (i == RRCH_DII_J2_PRES) {
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

void rrch_chain_step(rrch_t *c)
{
    rrch_chain_t *ch = &c->chain;
    const rrch_in_t *in = &c->in;
    uint16_t close_n = (uint16_t)CFG(c, CHAIN_CLOSE_DEBOUNCE_MS);

    if (!ch->primed) {
        ch->state = in->di;
        ch->pres = ch->pres_cand = rrch_pres_classify(in->pres_ohm);
        ch->latch = (in->di & RRCH_DI(HW_LATCH)) != 0;
        ch->primed = true;
    }

    /* --- digital debounce --- */
    for (int i = 0; i < RRCH_DI_N; i++) {
        uint32_t bit = 1u << i;
        bool r = (in->di & bit) != 0, s = (ch->state & bit) != 0;
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
    rrch_pres_t raw = rrch_pres_classify(in->pres_ohm);
    ch->pres_ohm = in->pres_ohm;
    if (raw == ch->pres) {
        ch->pres_cnt = 0;
        ch->pres_cand = raw;
    } else {
        if (raw != ch->pres_cand) {
            ch->pres_cand = raw;
            ch->pres_cnt = 0;
        }
        ch->pres_cnt++;
        uint16_t need = (raw == RRCH_PRES_ABSENT) ? 2u : (uint16_t)CFG(c, CHAIN_PRES_SETTLE_MS);
        if (ch->pres_cnt >= need) {
            rrch_event(c, RRCH_EV_J1, ch->pres, raw, (int32_t)(in->pres_ohm > 999999u ? 999999u : in->pres_ohm));
            ch->pres = raw;
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

    /* --- plausibility faults --- */
    bool ea = (st & RRCH_DI(ESTOP_A)) != 0, eb = (st & RRCH_DI(ESTOP_B)) != 0;
    if (timer_run(&ch->t_estop_disc, ea != eb, 200)) {
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

    /* --- live hardware causes --- */
    uint32_t hw = 0;
    if (!(st & RRCH_DI(MODE_RUN))) {
        hw |= RRCH_HW(MODE_NOT_RUN);
    }
    if (!ea || !eb) {
        hw |= RRCH_HW(ESTOP);
    }
    if (!(st & RRCH_DI(HANDS_ON))) {
        hw |= RRCH_HW(HANDS_ON);
    }
    if (!(st & RRCH_DI(CHG_COVER)) || !(st & RRCH_DI(CHG_PLUG_LINK))) {
        hw |= RRCH_HW(CHARGER);
    }
    if (!(st & RRCH_DI(HEAD_DOCK))) {
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
    if (!(st & RRCH_DI(LAB_KEY_N)) || ch->pres == RRCH_PRES_HEAD_VIA_LAB_EXTENSION || ch->pres == RRCH_PRES_LAB_EXTENSION_ONLY) {
        hw |= RRCH_HW(LAB_KEY);
    }
    if (!(st & RRCH_DI(BODY_BUMPER_L)) || !(st & RRCH_DI(BODY_BUMPER_R))) {
        hw |= RRCH_HW(BODY_BUMPER);
    }
    if (!(st & RRCH_DI(WDG_OK))) {
        hw |= RRCH_HW(WATCHDOG);
    }
    bool bt_running = c->bt.state == RRCH_BT_RUNNING;
    if (!c->out.arm_permit && c->boot_done && !bt_running && c->mode != RRCH_MODE_SERVICE_CHARGE && c->mode != RRCH_MODE_LAB) {
        hw |= RRCH_HW(MCU_NOT_READY);
    }
    bool vlow = timer_run(&ch->t_vmot_low, latch && in->vmot_v < CFG(c, BRK_VMOT_MIN_V), 100);
    bool vhigh = timer_run(&ch->t_vmot_high, !latch && in->vmot_v > CFG(c, BRK_VMOT_OFF_V), (uint16_t)CFG(c, BRK_VMOT_DECAY_MAX_MS));
    bool bl = (st & RRCH_DI(BRAKE_L)) != 0, br = (st & RRCH_DI(BRAKE_R)) != 0;
    bool brb = timer_run(&ch->t_brake_rb, (bl != latch || br != latch) && !bt_running, 200);
    if (vlow || vhigh || brb) {
        hw |= RRCH_HW(VMOT_FAULT);
    }
    ch->hw_live = hw;

    /* --- latched hardware reasons --- */
    if (latch != ch->latch) {
        ch->latch = latch;
        if (!latch) {
            ch->hw_latched = hw;
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
