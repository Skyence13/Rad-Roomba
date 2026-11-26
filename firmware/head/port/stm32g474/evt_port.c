/* Event capture port: TIM2/TIM5 input captures (BUSY start times), latch read-backs on GPIOD/GPIOE,
 * CLR pulses on GPIOE, fixed 100 kHz service interrupt on TIM6. All decisions are taken by the
 * hardware-independent core/rrh_evtcap.c; this file only moves bits. NOT TESTED ON HARDWARE.
 *
 * Chain index: 0..3 = floor lanes (TIM2 CH1..4, CLR on PE4..7), 4..7 = reference lanes
 * (TIM5 CH1..4, CLR on PE10..13). Read-backs: PD0-3 ULD_F, PD4-7 ALPHA_F, PD8-11 ULD_R,
 * PD12-15 LLD_F, PE0-3 LLD_R (pinmap.yaml).
 */
#include "bsp.h"

#include "rrh_evtcap.h"

#define EVT_SERVICE_HZ 100000u
#define EVT_WINDOW_US 4u        /* acceptance window W */
#define EVT_MAX_HOLD_US 1000u   /* BUSY longer than this: chain saturated */
#define EVT_CLR_TICKS 30u       /* CLR pulse width + latch recovery booked as dead time (~0.2 us) */
#define EVT_ARM_DELAY_US 1000u  /* first gate starts this long after ARM */

static rrh_evtcap_t g_evt;
static rrh_evt_in_t g_in;
static uint8_t g_busy;        /* chains whose BUSY capture has been taken and not yet cleared */
static uint32_t g_tim5_offset; /* TIM2 count minus TIM5 count */
static const uint8_t k_clr_pin[RRH_EVT_CHAINS] = {4u, 5u, 6u, 7u, 10u, 11u, 12u, 13u};

static uint64_t clear_cb(void *ctx, uint8_t chain)
{
    (void)ctx;
    const uint64_t t = bsp_now_ticks(); /* the clear time is a timer reading, not an assumption */
    GPIOE->BSRR = 1uL << (k_clr_pin[chain] + 16u); /* CLR low */
    __NOP();
    __NOP();
    __NOP();
    __NOP();
    GPIOE->BSRR = 1uL << k_clr_pin[chain]; /* CLR high: the chain can latch again */
    g_busy &= (uint8_t)~(1u << chain);
    return t + EVT_CLR_TICKS;
}

static void heater_cb(void *ctx, bool on)
{
    (void)ctx;
    bsp_gpio_write(PIN_HTR_EN_PORT, PIN_HTR_EN_PIN, on);
}

void TIM6_DAC_IRQHandler(void)
{
    TIM6->SR = 0u;
    bsp_tick_isr_update();
    const uint64_t now = bsp_now_ticks();
    const uint32_t now32 = (uint32_t)now;

    /* New events: a capture flag means the BUSY latch was set; the CCR holds its start time. */
    const uint32_t sr2 = TIM2->SR;
    const uint32_t sr5 = TIM5->SR;
    if (((sr2 | sr5) & (TIM_SR_CC1IF | TIM_SR_CC2IF | TIM_SR_CC3IF | TIM_SR_CC4IF)) != 0u) {
        for (uint32_t n = 0u; n < 4u; n++) {
            if ((sr2 & (TIM_SR_CC1IF << n)) != 0u) {
                const uint32_t cap = (&TIM2->CCR1)[n]; /* reading clears the flag */
                g_in.start_tick[n] = now - (uint32_t)(now32 - cap);
                g_busy |= (uint8_t)(1u << n);
            }
            if ((sr5 & (TIM_SR_CC1IF << n)) != 0u) {
                const uint32_t cap = (&TIM5->CCR1)[n] + g_tim5_offset;
                g_in.start_tick[4u + n] = now - (uint32_t)(now32 - cap);
                g_busy |= (uint8_t)(1u << (4u + n));
            }
        }
    }
    const uint32_t d = GPIOD->IDR;
    const uint32_t e = GPIOE->IDR;
    g_in.busy = g_busy;
    g_in.uld = (uint8_t)((d & 0x0Fu) | (((d >> 8) & 0x0Fu) << 4));
    g_in.alpha = (uint8_t)((d >> 4) & 0x0Fu);
    g_in.lld_low = (uint8_t)~(((d >> 12) & 0x0Fu) | ((e & 0x0Fu) << 4));
    rrh_evtcap_service(&g_evt, now, &g_in);

    bsp_rs485_tx_service(now);
}

static void service_irq(bool enable)
{
    if (enable) {
        NVIC_EnableIRQ(TIM6_DAC_IRQn);
    } else {
        NVIC_DisableIRQ(TIM6_DAC_IRQn);
        __DSB();
        __ISB();
    }
}

void evt_port_init(void)
{
    const rrh_evt_cfg_t cfg = {BSP_TICK_HZ, EVT_WINDOW_US * BSP_TICKS_PER_US, EVT_MAX_HOLD_US * BSP_TICKS_PER_US,
                               clear_cb, heater_cb, NULL};
    rrh_evtcap_init(&g_evt, &cfg);
    /* Both timers count the same clock; their constant offset is measured once. The two reads are
     * a few CPU cycles apart, which is a fixed error of a few ticks (tens of ns) on where a
     * reference-chain busy interval is split at a gate boundary; busy durations are unaffected. */
    const uint32_t primask = __get_PRIMASK();
    __disable_irq();
    const uint32_t c5 = TIM5->CNT;
    const uint32_t c2 = TIM2->CNT;
    __set_PRIMASK(primask);
    g_tim5_offset = c2 - c5;
    /* Release the latches (CLR high) and discard captures taken while they were held. */
    GPIOE->BSRR = 0x3CF0u;
    TIM2->SR = 0u;
    TIM5->SR = 0u;
    TIM6->PSC = 0u;
    TIM6->ARR = (BSP_SYSCLK_HZ / EVT_SERVICE_HZ) - 1u;
    TIM6->EGR = TIM_EGR_UG;
    TIM6->SR = 0u;
    TIM6->DIER = TIM_DIER_UIE;
    TIM6->CR1 = TIM_CR1_CEN;
    NVIC_SetPriority(TIM6_DAC_IRQn, 1);
    service_irq(true);
}

bool evt_port_start(uint32_t span_us, rrh_epoch_t *epoch)
{
    /* Head microseconds are ticks / 144 by definition, so tick 0 is head time 0. */
    epoch->tick = 0u;
    epoch->us = 0u;
    epoch->tick_hz = BSP_TICK_HZ;
    service_irq(false);
    const uint64_t first = ((bsp_now_us() + EVT_ARM_DELAY_US) * BSP_TICKS_PER_US);
    const bool ok = rrh_evtcap_start(&g_evt, first, span_us * BSP_TICKS_PER_US);
    service_irq(true);
    return ok;
}

bool evt_port_stop(void)
{
    service_irq(false);
    const bool in_progress = rrh_evtcap_stop(&g_evt, bsp_now_ticks());
    service_irq(true);
    return in_progress;
}

void evt_port_abort(void)
{
    service_irq(false);
    rrh_evtcap_abort(&g_evt);
    service_irq(true);
}

bool evt_port_running(void)
{
    service_irq(false);
    const bool r = rrh_evtcap_running(&g_evt);
    service_irq(true);
    return r;
}

bool evt_port_poll(rrh_gate_record_t *rec)
{
    service_irq(false); /* atomic copy of one completed gate */
    const bool got = rrh_evtcap_pop(&g_evt, rec);
    service_irq(true);
    return got;
}

void evt_port_chain_enable(uint8_t mask)
{
    service_irq(false);
    rrh_evtcap_set_chain_enable(&g_evt, mask);
    service_irq(true);
}

void evt_port_heater_request(bool on)
{
    service_irq(false);
    rrh_evtcap_heater_request(&g_evt, on);
    service_irq(true);
}

/* Latch self-test without any analog signal: one edge on LATCH_TEST must set every latch (all
 * BUSY captures, all ULD/ALPHA read-backs); the service interrupt then clears them again. Only
 * meaningful while disarmed. */
bool evt_port_selftest(void)
{
    service_irq(false);
    TIM2->SR = 0u;
    TIM5->SR = 0u;
    bsp_gpio_write(PIN_LATCH_TEST_PORT, PIN_LATCH_TEST_PIN, true);
    bsp_delay_us(2u);
    bsp_gpio_write(PIN_LATCH_TEST_PORT, PIN_LATCH_TEST_PIN, false);
    const uint32_t caps = TIM_SR_CC1IF | TIM_SR_CC2IF | TIM_SR_CC3IF | TIM_SR_CC4IF;
    const bool busy_ok = ((TIM2->SR & caps) == caps) && ((TIM5->SR & caps) == caps);
    const bool latch_ok = (GPIOD->IDR & 0x0FFFu) == 0x0FFFu;
    service_irq(true);
    bsp_delay_us(2000u); /* several service periods: every chain is classified and cleared */
    const bool cleared = ((GPIOD->IDR & 0x0FFFu) == 0u) && (g_busy == 0u);
    return busy_ok && latch_ok && cleared;
}
