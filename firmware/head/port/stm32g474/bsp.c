/* RR-HEAD-ACQ board support: clocks, timebase, RS-485 USART, SPI, I2C, ADC, flash, watchdog.
 *
 * NOT TESTED ON HARDWARE. Register and bit names are compile-checked against ST's CMSIS device
 * header; behaviour that is recalled from reference manual RM0440 and device datasheets and
 * could not be checked here is marked UNVERIFIED.
 */
#include "bsp.h"

#include <string.h>

#include "rr_common.h"

/* ---- GPIO ----------------------------------------------------------------------------------- */
enum { MODE_IN = 0, MODE_OUT = 1, MODE_AF = 2, MODE_ANALOG = 3 };
enum { PULL_NONE = 0, PULL_UP = 1, PULL_DOWN = 2 };

static void gpio_cfg(GPIO_TypeDef *port, uint32_t pin, uint32_t mode, uint32_t af, uint32_t pull)
{
    port->MODER = (port->MODER & ~(3uL << (pin * 2u))) | (mode << (pin * 2u));
    port->PUPDR = (port->PUPDR & ~(3uL << (pin * 2u))) | (pull << (pin * 2u));
    port->OSPEEDR = (port->OSPEEDR & ~(3uL << (pin * 2u))) | (1uL << (pin * 2u)); /* medium speed */
    if (mode == MODE_AF) {
        const uint32_t idx = pin >> 3;
        const uint32_t sh = (pin & 7u) * 4u;
        port->AFR[idx] = (port->AFR[idx] & ~(0xFuL << sh)) | (af << sh);
    }
}

#define CFG_OUT(sig, level)                              \
    do {                                                 \
        bsp_gpio_write(PIN_##sig##_PORT, PIN_##sig##_PIN, (level)); \
        gpio_cfg(PIN_##sig##_PORT, PIN_##sig##_PIN, MODE_OUT, 0u, PULL_NONE); \
    } while (0)
#define CFG_IN(sig, pull) gpio_cfg(PIN_##sig##_PORT, PIN_##sig##_PIN, MODE_IN, 0u, (pull))
#define CFG_AF(sig, pull) gpio_cfg(PIN_##sig##_PORT, PIN_##sig##_PIN, MODE_AF, PIN_##sig##_AF, (pull))
#define CFG_ANALOG(sig) gpio_cfg(PIN_##sig##_PORT, PIN_##sig##_PIN, MODE_ANALOG, 0u, PULL_NONE)

/* ---- clock ------------------------------------------------------------------------------------ */
static bool g_tcxo_ok;

static bool wait_set(const volatile uint32_t *reg, uint32_t mask, uint32_t loops)
{
    while (loops-- > 0u) {
        if ((*reg & mask) == mask) {
            return true;
        }
    }
    return false;
}

static void clock_init(void)
{
    /* 24 MHz TCXO on OSC_IN, HSE bypass (NUCLEO-G474RE: 24 MHz crystal, oscillator mode). */
#ifndef RRH_BOARD_NUCLEO
    RCC->CR |= RCC_CR_HSEBYP;
#endif
    RCC->CR |= RCC_CR_HSEON;
    g_tcxo_ok = wait_set(&RCC->CR, RCC_CR_HSERDY, 400000u);

    /* Four wait states for 144 MHz in range 1 normal mode (RM0440 table, UNVERIFIED). */
    FLASH->ACR = (FLASH->ACR & ~FLASH_ACR_LATENCY) | FLASH_ACR_LATENCY_4WS;

    /* VCO 288 MHz, R = /2 -> 144 MHz SYSCLK, Q = /6 -> 48 MHz for the RNG. */
    uint32_t cfg = RCC_PLLCFGR_PLLREN | RCC_PLLCFGR_PLLQEN | (2uL << RCC_PLLCFGR_PLLQ_Pos);
    if (g_tcxo_ok) {
        cfg |= RCC_PLLCFGR_PLLSRC_HSE | (1uL << RCC_PLLCFGR_PLLM_Pos) | (24uL << RCC_PLLCFGR_PLLN_Pos); /* 24 / 2 x 24 */
    } else {
        cfg |= RCC_PLLCFGR_PLLSRC_HSI | (3uL << RCC_PLLCFGR_PLLM_Pos) | (72uL << RCC_PLLCFGR_PLLN_Pos); /* 16 / 4 x 72: degraded, flagged */
    }
    RCC->PLLCFGR = cfg;
    RCC->CR |= RCC_CR_PLLON;
    (void)wait_set(&RCC->CR, RCC_CR_PLLRDY, 400000u);
    /* Switching to more than 80 MHz: run the AHB at half speed across the switch (RM0440
     * recommendation, UNVERIFIED), then return to /1. */
    RCC->CFGR = (RCC->CFGR & ~RCC_CFGR_HPRE) | RCC_CFGR_HPRE_DIV2;
    RCC->CFGR = (RCC->CFGR & ~RCC_CFGR_SW) | RCC_CFGR_SW_PLL;
    (void)wait_set(&RCC->CFGR, RCC_CFGR_SWS_PLL, 400000u);
    for (volatile uint32_t i = 0u; i < 200u; i++) {
    }
    RCC->CFGR &= ~RCC_CFGR_HPRE;
    SystemCoreClock = BSP_SYSCLK_HZ;

    RCC->CCIPR = (RCC->CCIPR & ~(RCC_CCIPR_CLK48SEL | RCC_CCIPR_ADC12SEL | RCC_CCIPR_ADC345SEL)) | RCC_CCIPR_CLK48SEL_1 |
                 RCC_CCIPR_ADC12SEL_1 | RCC_CCIPR_ADC345SEL_1; /* ADC kernel clocks = SYSCLK */
    RCC->CSR |= RCC_CSR_LSION; /* IWDG clock */

    RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN | RCC_AHB2ENR_GPIOBEN | RCC_AHB2ENR_GPIOCEN | RCC_AHB2ENR_GPIODEN |
                    RCC_AHB2ENR_GPIOEEN | RCC_AHB2ENR_GPIOFEN | RCC_AHB2ENR_ADC12EN | RCC_AHB2ENR_ADC345EN | RCC_AHB2ENR_RNGEN;
    RCC->APB1ENR1 |= RCC_APB1ENR1_TIM2EN | RCC_APB1ENR1_TIM3EN | RCC_APB1ENR1_TIM4EN | RCC_APB1ENR1_TIM5EN | RCC_APB1ENR1_TIM6EN |
                     RCC_APB1ENR1_UART4EN | RCC_APB1ENR1_I2C3EN | RCC_APB1ENR1_PWREN;
    RCC->APB2ENR |= RCC_APB2ENR_USART1EN | RCC_APB2ENR_SPI1EN | RCC_APB2ENR_SYSCFGEN | RCC_APB2ENR_TIM8EN;
    (void)RCC->APB2ENR;
    /* PB4 / PB6 are UCPD CC pins: switch their dead-battery pull-downs off (UNVERIFIED need). */
    PWR->CR3 |= PWR_CR3_UCPD_DBDIS;
}

bool bsp_clock_from_tcxo(void)
{
    return g_tcxo_ok;
}

/* ---- head clock: TIM2 free running at 144 MHz, extended to 64 bit ----------------------------------
 * The 100 kHz service interrupt calls bsp_tick_isr_update() far more often than the 29.8 s wrap
 * period, so no overflow interrupt is needed. Head microseconds = ticks / 144. */
static volatile uint32_t g_tick_high;
static volatile uint32_t g_tick_last;

void bsp_tick_isr_update(void)
{
    const uint32_t primask = __get_PRIMASK();
    __disable_irq(); /* the USART interrupt (higher priority) reads the pair */
    const uint32_t cnt = TIM2->CNT;
    if (cnt < g_tick_last) {
        g_tick_high++;
    }
    g_tick_last = cnt;
    __set_PRIMASK(primask);
}

uint64_t bsp_now_ticks(void)
{
    const uint32_t primask = __get_PRIMASK();
    __disable_irq();
    const uint32_t cnt = TIM2->CNT;
    uint32_t high = g_tick_high;
    if (cnt < g_tick_last) {
        high++; /* wrapped since the last service interrupt */
    }
    __set_PRIMASK(primask);
    return ((uint64_t)high << 32) | cnt;
}

uint64_t bsp_now_us(void)
{
    return bsp_now_ticks() / BSP_TICKS_PER_US;
}

void bsp_delay_us(uint32_t us)
{
    const uint32_t start = TIM2->CNT;
    while ((TIM2->CNT - start) < (us * BSP_TICKS_PER_US)) {
    }
}

static void timebase_init(void)
{
    /* TIM2 and TIM5: 32-bit, no prescaler, free running; all four channels capture rising edges
     * of the BUSY latches (configured here, used by evt_port.c). */
    TIM_TypeDef *const timers[2] = {TIM2, TIM5};
    for (uint32_t i = 0u; i < 2u; i++) {
        TIM_TypeDef *t = timers[i];
        t->PSC = 0u;
        t->ARR = 0xFFFFFFFFu;
        t->CCMR1 = TIM_CCMR1_CC1S_0 | TIM_CCMR1_CC2S_0;
        t->CCMR2 = TIM_CCMR2_CC3S_0 | TIM_CCMR2_CC4S_0;
        t->CCER = TIM_CCER_CC1E | TIM_CCER_CC2E | TIM_CCER_CC3E | TIM_CCER_CC4E;
        t->EGR = TIM_EGR_UG;
        t->SR = 0u;
    }
    /* TIM4 and TIM3: 16-bit, same clock, free running; all four channels capture the FALLING
     * edge of the raw LLD comparator outputs (floor on TIM4, reference on TIM3). Together with
     * the BUSY capture this gives the time over threshold of the triggering pulse. */
    TIM_TypeDef *const width_timers[2] = {TIM4, TIM3};
    for (uint32_t i = 0u; i < 2u; i++) {
        TIM_TypeDef *t = width_timers[i];
        t->PSC = 0u;
        t->ARR = 0xFFFFu;
        t->CCMR1 = TIM_CCMR1_CC1S_0 | TIM_CCMR1_CC2S_0;
        t->CCMR2 = TIM_CCMR2_CC3S_0 | TIM_CCMR2_CC4S_0;
        t->CCER = TIM_CCER_CC1E | TIM_CCER_CC1P | TIM_CCER_CC2E | TIM_CCER_CC2P | TIM_CCER_CC3E | TIM_CCER_CC3P |
                  TIM_CCER_CC4E | TIM_CCER_CC4P;
        t->EGR = TIM_EGR_UG;
        t->SR = 0u;
    }
    TIM2->CR1 = TIM_CR1_CEN;
    TIM5->CR1 = TIM_CR1_CEN;
    TIM4->CR1 = TIM_CR1_CEN;
    TIM3->CR1 = TIM_CR1_CEN;
}

/* ---- RS-485 on USART1 with hardware driver enable ---------------------------------------------- */
static uint8_t g_rx_store[1024];
static rrc_ring_t g_rx_ring;
static volatile uint64_t g_lf_ticks;
static volatile uint64_t g_tx_at_ticks;
static volatile bool g_tx_armed;
static const uint8_t *volatile g_tx_data;
static volatile size_t g_tx_len, g_tx_pos;

static void rs485_init(void)
{
    (void)rrc_ring_init(&g_rx_ring, g_rx_store, sizeof g_rx_store);
    USART1->BRR = BSP_SYSCLK_HZ / 1000000u; /* 144: 1 Mbaud, oversampling 16, exact */
    USART1->CR3 = USART_CR3_DEM;            /* DE active high, driven by the USART */
    /* DE asserted 8/16 bit before the start bit and held 8/16 bit after the stop bit (5 us). */
    USART1->CR1 = (8uL << USART_CR1_DEAT_Pos) | (8uL << USART_CR1_DEDT_Pos) | USART_CR1_RE | USART_CR1_TE |
                  USART_CR1_RXNEIE;
    USART1->CR1 |= USART_CR1_UE;
    NVIC_SetPriority(USART1_IRQn, 0); /* highest: receive timestamps (short handler) */
    NVIC_EnableIRQ(USART1_IRQn);
}

void USART1_IRQHandler(void)
{
    const uint32_t isr = USART1->ISR;
    if ((isr & (USART_ISR_ORE | USART_ISR_FE | USART_ISR_NE)) != 0u) {
        USART1->ICR = USART_ICR_ORECF | USART_ICR_FECF | USART_ICR_NECF;
    }
    if ((isr & USART_ISR_RXNE) != 0u) {
        const uint8_t b = (uint8_t)USART1->RDR;
        if (b == (uint8_t)'\n') {
            /* Receipt time of a request = time its LF was received (ISR entry, about half a
             * bit after the middle of the stop bit plus interrupt latency; UNVERIFIED offset). */
            g_lf_ticks = bsp_now_ticks();
        }
        (void)rrc_ring_push(&g_rx_ring, b);
    }
    if (((USART1->CR1 & USART_CR1_TXEIE) != 0u) && ((isr & USART_ISR_TXE) != 0u)) {
        if (g_tx_pos < g_tx_len) {
            USART1->TDR = g_tx_data[g_tx_pos];
            g_tx_pos++;
        } else {
            USART1->CR1 &= ~USART_CR1_TXEIE; /* DE drops after the last stop bit (hardware) */
        }
    }
}

/* Called from the 100 kHz service interrupt: releases a reply whose start time has come.
 * The start is therefore at most one service period (10 us) after the requested time. */
void bsp_rs485_tx_service(uint64_t now_ticks)
{
    if (g_tx_armed && (now_ticks >= g_tx_at_ticks)) {
        g_tx_armed = false;
        USART1->CR1 |= USART_CR1_TXEIE;
    }
}

bool bsp_rs485_pop(uint8_t *byte, uint64_t *rx_us)
{
    if (!rrc_ring_pop(&g_rx_ring, byte)) {
        return false;
    }
    *rx_us = ((*byte == (uint8_t)'\n') ? g_lf_ticks : bsp_now_ticks()) / BSP_TICKS_PER_US;
    return true;
}

void bsp_rs485_send(const uint8_t *data, size_t len, uint64_t at_us)
{
    USART1->CR1 &= ~USART_CR1_TXEIE;
    g_tx_armed = false;
    g_tx_data = data;
    g_tx_len = len;
    g_tx_pos = 0u;
    /* at_us == 0: as soon as the bus turnaround allows. Either way the service interrupt starts
     * the transmission, so the driver is never enabled inside the turnaround time. */
    g_tx_at_ticks = (at_us != 0u) ? (at_us * BSP_TICKS_PER_US)
                                  : (g_lf_ticks + ((uint64_t)BSP_RS485_TURNAROUND_US * BSP_TICKS_PER_US));
    g_tx_armed = true;
}

/* ---- SPI ------------------------------------------------------------------------------------------ */
static void spi_setup(SPI_TypeDef *spi, uint32_t br, bool cpol, bool cpha)
{
    spi->CR1 = 0u;
    spi->CR2 = (7uL << SPI_CR2_DS_Pos) | SPI_CR2_FRXTH; /* 8-bit frames */
    spi->CR1 = SPI_CR1_MSTR | SPI_CR1_SSM | SPI_CR1_SSI | (br << SPI_CR1_BR_Pos) | (cpol ? SPI_CR1_CPOL : 0u) |
               (cpha ? SPI_CR1_CPHA : 0u);
    spi->CR1 |= SPI_CR1_SPE;
}

static uint8_t spi_xfer(SPI_TypeDef *spi, uint8_t b)
{
    (void)wait_set(&spi->SR, SPI_SR_TXE, 100000u);
    *(volatile uint8_t *)&spi->DR = b;
    (void)wait_set(&spi->SR, SPI_SR_RXNE, 100000u);
    return *(volatile uint8_t *)&spi->DR;
}

uint8_t bsp_spi_dac_xfer(uint8_t b) { return spi_xfer(SPI1, b); }

/* Test pulser strobe (TIM8_CH1 = PC6) and LED pulser strobe (TIM8_CH3N = PC12): both at 1 kHz from
 * TIM8 running at 48 MHz (PSC 2, 20.8 ns resolution), PWM mode 1. The charge pulser stays high for
 * width_us (1 ... 100 us; alpha-scale tests need >= 20 us, budget 7). The LED strobe is a fixed
 * ~208 ns pulse: with the FET on, R1018 (10 k) keeps feeding the LED, so the pulse must be short
 * (UNVERIFIED: LED and optical coupling are not chosen). OC3N follows OC3REF because CC3E = 0 and
 * CC3NE = 1 (RM0440 complementary output rule, UNVERIFIED on hardware). Amplitudes come from DAC outputs. */
void bsp_pulser_config(bool pulser_enable, uint8_t width_us, bool led_enable)
{
    TIM8->CR1 = 0u;
    TIM8->CCER = 0u;
    TIM8->BDTR = 0u;
    if (!pulser_enable && !led_enable) {
        return;
    }
    TIM8->PSC = 2u; /* 144 MHz / 3 = 48 MHz */
    TIM8->ARR = 47999u; /* 1 kHz */
    TIM8->CCR1 = (uint32_t)width_us * 48u;
    TIM8->CCR3 = 10u;
    TIM8->CCMR1 = (6uL << TIM_CCMR1_OC1M_Pos) | TIM_CCMR1_OC1PE;
    TIM8->CCMR2 = (6uL << TIM_CCMR2_OC3M_Pos) | TIM_CCMR2_OC3PE;
    TIM8->CCER = (pulser_enable ? TIM_CCER_CC1E : 0u) | (led_enable ? TIM_CCER_CC3NE : 0u);
    TIM8->BDTR = TIM_BDTR_MOE; /* advanced timer: main output enable */
    TIM8->EGR = TIM_EGR_UG;
    TIM8->CR1 = TIM_CR1_CEN;
}

void bsp_pulser_select(uint8_t chain)
{
    bsp_gpio_write(PIN_PULSER_A0_PORT, PIN_PULSER_A0_PIN, (chain & 1u) != 0u);
    bsp_gpio_write(PIN_PULSER_A1_PORT, PIN_PULSER_A1_PIN, (chain & 2u) != 0u);
    bsp_gpio_write(PIN_PULSER_A2_PORT, PIN_PULSER_A2_PIN, (chain & 4u) != 0u);
}

/* ---- DAC60508 (register map recalled from the TI datasheet: UNVERIFIED) ----------------------------- */
#define DAC_REG_DEVICE_ID 0x01u
#define DAC_REG_GAIN 0x04u
#define DAC_REG_DAC0 0x08u

static void dac_cs(uint8_t device, bool level)
{
    switch (device) {
    case 0u: bsp_gpio_write(PIN_DAC_CS0_N_PORT, PIN_DAC_CS0_N_PIN, level); break;
    case 1u: bsp_gpio_write(PIN_DAC_CS1_N_PORT, PIN_DAC_CS1_N_PIN, level); break;
    case 2u: bsp_gpio_write(PIN_DAC_CS2_N_PORT, PIN_DAC_CS2_N_PIN, level); break;
    default: bsp_gpio_write(PIN_DAC_CS3_N_PORT, PIN_DAC_CS3_N_PIN, level); break;
    }
}

static uint16_t dac_frame(uint8_t device, uint8_t cmd, uint16_t data)
{
    dac_cs(device, false);
    (void)bsp_spi_dac_xfer(cmd);
    const uint8_t hi = bsp_spi_dac_xfer((uint8_t)(data >> 8));
    const uint8_t lo = bsp_spi_dac_xfer((uint8_t)data);
    dac_cs(device, true);
    return (uint16_t)(((uint16_t)hi << 8) | lo);
}

void bsp_dac_write(uint8_t device, uint8_t channel, uint16_t code12)
{
    /* 12-bit data is left-justified in the 16-bit field. */
    (void)dac_frame(device, (uint8_t)(DAC_REG_DAC0 + (channel & 7u)), (uint16_t)((code12 & 0x0FFFu) << 4));
}

bool bsp_dac_init(void)
{
    bool ok = true;
    for (uint8_t dev = 0u; dev < 4u; dev++) {
        (void)dac_frame(dev, DAC_REG_GAIN, 0x0000u); /* reference not divided, all buffer gains 1 */
        (void)dac_frame(dev, (uint8_t)(0x80u | DAC_REG_DEVICE_ID), 0u);
        const uint16_t id = dac_frame(dev, 0x00u, 0u); /* read back with a NOP frame */
        if ((id == 0x0000u) || (id == 0xFFFFu)) {
            ok = false; /* no device answered on this chip select */
        }
    }
    return ok;
}

/* ---- I2C3 (100 kHz; TIMINGR calculated for a 144 MHz kernel clock, UNVERIFIED on hardware) ----------- */
static bool i2c_wait(uint32_t flag)
{
    for (uint32_t i = 0u; i < 200000u; i++) {
        const uint32_t isr = I2C3->ISR;
        if ((isr & flag) != 0u) {
            return true;
        }
        if ((isr & (I2C_ISR_NACKF | I2C_ISR_BERR | I2C_ISR_ARLO)) != 0u) {
            break;
        }
    }
    I2C3->ICR = I2C_ICR_NACKCF | I2C_ICR_BERRCF | I2C_ICR_ARLOCF | I2C_ICR_STOPCF;
    return false;
}

bool bsp_i2c_xfer(uint8_t addr, const uint8_t *w, size_t wn, uint8_t *r, size_t rn)
{
    if (wn > 0u) {
        I2C3->CR2 = ((uint32_t)addr << 1) | ((uint32_t)wn << I2C_CR2_NBYTES_Pos) | I2C_CR2_START |
                    ((rn == 0u) ? I2C_CR2_AUTOEND : 0u);
        for (size_t i = 0u; i < wn; i++) {
            if (!i2c_wait(I2C_ISR_TXIS)) {
                return false;
            }
            I2C3->TXDR = w[i];
        }
        if ((rn > 0u) && !i2c_wait(I2C_ISR_TC)) {
            return false;
        }
    }
    if (rn > 0u) {
        I2C3->CR2 = ((uint32_t)addr << 1) | I2C_CR2_RD_WRN | ((uint32_t)rn << I2C_CR2_NBYTES_Pos) | I2C_CR2_START |
                    I2C_CR2_AUTOEND;
        for (size_t i = 0u; i < rn; i++) {
            if (!i2c_wait(I2C_ISR_RXNE)) {
                return false;
            }
            r[i] = (uint8_t)I2C3->RXDR;
        }
    }
    const bool ok = i2c_wait(I2C_ISR_STOPF);
    I2C3->ICR = I2C_ICR_STOPCF;
    return ok;
}

bool bsp_eui64(uint8_t out[8])
{
    const uint8_t reg = 0xF8u; /* 24AA025E64: EUI-64 at 0xF8..0xFF (UNVERIFIED) */
    return bsp_i2c_xfer(0x50u, &reg, 1u, out, 8u);
}

int32_t bsp_tmp117_mc(uint8_t index)
{
    const uint8_t reg = 0x00u; /* temperature result, 7.8125 mdegC per LSB (UNVERIFIED) */
    uint8_t raw[2];
    if (!bsp_i2c_xfer((uint8_t)(0x48u + index), &reg, 1u, raw, 2u)) {
        return RRH_TEMP_INVALID;
    }
    const int16_t code = (int16_t)(((uint16_t)raw[0] << 8) | raw[1]);
    return ((int32_t)code * 125) / 16;
}

/* ---- TCA9534 at 0x20 (optional; register map recalled from the data sheet: UNVERIFIED) ------------
 * 0x00 input port, 0x01 output port, 0x02 polarity inversion, 0x03 configuration (1 = input).
 * P0 = MON_EXT is an output held low (lane monitor page 0); everything else is read. */
static bool g_exp_configured;

bool bsp_expander_read(uint8_t *inputs)
{
    const uint8_t reg_in = 0x00u;
    if (!g_exp_configured) {
        /* P7 = MON_LANE_EN (all lane monitor muxes off) and P0 = MON_EXT must be written 0 BEFORE they become outputs: the
         * output register powers up 0xFF (recalled, UNVERIFIED), which would switch the lane muxes on for an instant. */
        const uint8_t out[2] = {0x01u, 0x00u};
        const uint8_t cfg[2] = {0x03u, RRH_EXP_DIR_MASK};
        if (!bsp_i2c_xfer(0x20u, out, 2u, NULL, 0u) || !bsp_i2c_xfer(0x20u, cfg, 2u, NULL, 0u)) {
            return false;
        }
        g_exp_configured = true;
    }
    if (!bsp_i2c_xfer(0x20u, &reg_in, 1u, inputs, 1u)) {
        g_exp_configured = false; /* re-configure when it answers again */
        return false;
    }
    return true;
}

/* ---- ADC1 housekeeping ------------------------------------------------------------------------------- */
static const uint8_t k_adc_channel[BSP_ADC_COUNT] = {
    PIN_BIAS_VMON_ADC_CH, PIN_BIAS_IMON_ADC_CH, PIN_NTC_SIPM0_ADC_CH, PIN_NTC_SIPM1_ADC_CH, PIN_NTC_SIPM2_ADC_CH,
    PIN_NTC_SIPM3_ADC_CH, PIN_NTC_HTR_ADC_CH,   PIN_NTC_BOARD_ADC_CH, PIN_VIN_MON_ADC_CH,   PIN_HTR_SENSE_ADC_CH};
static uint16_t g_adc_code[BSP_ADC_COUNT];
static uint32_t g_adc_index;
static uint32_t g_adc_rounds;
static bool g_adc_busy;

static void adc_init(void)
{
    ADC1->CR &= ~ADC_CR_DEEPPWD;
    ADC1->CR |= ADC_CR_ADVREGEN;
    bsp_delay_us(50u);
    ADC12_COMMON->CCR = (6uL << ADC_CCR_PRESC_Pos); /* kernel clock 144 MHz / 12 = 12 MHz (code 6, UNVERIFIED) */
    ADC1->CR |= ADC_CR_ADCAL;
    for (uint32_t i = 0u; (i < 400000u) && ((ADC1->CR & ADC_CR_ADCAL) != 0u); i++) {
    }
    ADC1->ISR = ADC_ISR_ADRDY;
    ADC1->CR |= ADC_CR_ADEN;
    (void)wait_set(&ADC1->ISR, ADC_ISR_ADRDY, 400000u);
    ADC1->SMPR1 = 0x36DB6DB6u & 0x3FFFFFFFu; /* 247.5 cycles (code 6) on channels 0..9 */
    ADC1->SMPR2 = 0x06DB6DB6u;               /* and on channels 10..18 */
}

void bsp_adc_step(void)
{
    bsp_imon_step();
    if (g_adc_busy) {
        if ((ADC1->ISR & ADC_ISR_EOC) == 0u) {
            return;
        }
        g_adc_code[g_adc_index] = (uint16_t)ADC1->DR;
        g_adc_busy = false;
        g_adc_index++;
        if (g_adc_index >= BSP_ADC_COUNT) {
            g_adc_index = 0u;
            if (g_adc_rounds < 0xFFFFFFFFu) {
                g_adc_rounds++;
            }
        }
    }
    ADC1->SQR1 = (uint32_t)k_adc_channel[g_adc_index] << ADC_SQR1_SQ1_Pos; /* one conversion */
    ADC1->CR |= ADC_CR_ADSTART;
    g_adc_busy = true;
}

uint16_t bsp_adc_code(bsp_adc_ch_t ch) { return g_adc_code[ch]; }
uint32_t bsp_adc_mv(bsp_adc_ch_t ch) { return ((uint32_t)g_adc_code[ch] * BSP_VREF_MV) / 4095u; }
bool bsp_adc_valid(void) { return g_adc_rounds > 0u; }

/* ---- IMON_CH: per-chain anode current monitor on ADC4 -------------------------------------------------
 * PE15 = ADC4_IN2 reads V(TRIMDRV) of the chain addressed by MON_MUX_A[2:0] (TMUX1108 U2703). The
 * mux output filter is R108 x C2704 = 1 ms, so each step waits RRH_IMON_SETTLE_US (10 time
 * constants) before the conversion: a full scan of eight chains takes 80 ms plus conversions. The
 * same address lines select the lane monitor decoder; see README (open electronics questions). */
static uint32_t g_imon_steps;
static uint32_t g_imon_uv[RRH_CHAINS];
static uint64_t g_imon_at_us[RRH_CHAINS];
static uint8_t g_imon_chain;
static uint8_t g_imon_state; /* 0: select, 1: settling, 2: converting */
static uint64_t g_imon_t0_us;
static bool g_adc4_ready;

static void adc4_init(void)
{
    ADC345_COMMON->CCR = (6uL << ADC_CCR_PRESC_Pos); /* 144 MHz / 12 = 12 MHz (as ADC1, UNVERIFIED) */
    ADC4->CR &= ~ADC_CR_DEEPPWD;
    ADC4->CR |= ADC_CR_ADVREGEN;
    bsp_delay_us(50u);
    ADC4->CR |= ADC_CR_ADCAL;
    for (uint32_t i = 0u; (i < 400000u) && ((ADC4->CR & ADC_CR_ADCAL) != 0u); i++) {
    }
    ADC4->ISR = ADC_ISR_ADRDY;
    ADC4->CR |= ADC_CR_ADEN;
    g_adc4_ready = wait_set(&ADC4->ISR, ADC_ISR_ADRDY, 400000u);
    ADC4->SMPR1 = (6uL << ADC_SMPR1_SMP2_Pos); /* 247.5 cycles on channel 2 (20 us at 12 MHz, source 1 k) */
}

/* MON_ADC (PC4 = ADC2_IN5) behind the monitor buffer: with MON_LANE_EN = 0 (always) it reads 0.300 V + V(FRAME)/2 (S3-03). */
static bool g_adc2_ready;

static void adc2_init(void)
{
    ADC2->CR &= ~ADC_CR_DEEPPWD;
    ADC2->CR |= ADC_CR_ADVREGEN;
    bsp_delay_us(50u);
    ADC2->CR |= ADC_CR_ADCAL;
    for (uint32_t i = 0u; (i < 400000u) && ((ADC2->CR & ADC_CR_ADCAL) != 0u); i++) {
    }
    ADC2->ISR = ADC_ISR_ADRDY;
    ADC2->CR |= ADC_CR_ADEN;
    g_adc2_ready = wait_set(&ADC2->ISR, ADC_ISR_ADRDY, 400000u);
    ADC2->SMPR1 = (6uL << ADC_SMPR1_SMP5_Pos);
}

bool bsp_mon_adc_uv(uint32_t *uv)
{
    if (!g_adc2_ready) {
        return false;
    }
    ADC2->SQR1 = (uint32_t)PIN_MON_ADC_ADC_CH << ADC_SQR1_SQ1_Pos;
    ADC2->CR |= ADC_CR_ADSTART;
    if (!wait_set(&ADC2->ISR, ADC_ISR_EOC, 20000u)) {
        return false;
    }
    *uv = rrh_board_adc_uv((uint16_t)ADC2->DR);
    return true;
}

static void imon_select(uint8_t chain)
{
    g_imon_steps++;
    bsp_gpio_write(PIN_MON_MUX_A0_PORT, PIN_MON_MUX_A0_PIN, (chain & 1u) != 0u);
    bsp_gpio_write(PIN_MON_MUX_A1_PORT, PIN_MON_MUX_A1_PIN, (chain & 2u) != 0u);
    bsp_gpio_write(PIN_MON_MUX_A2_PORT, PIN_MON_MUX_A2_PIN, (chain & 4u) != 0u);
}

void bsp_imon_step(void)
{
    if (!g_adc4_ready) {
        return;
    }
#if !RRH_IMON_SCAN_WHILE_ARMED
    static bool parked;
    if (evt_port_running()) {
        if (!parked) { /* park the address on a reference tap once (review M2); readings age out */
            imon_select(RRH_IMON_PARK_CHAIN);
            g_imon_state = 0u;
            parked = true;
        }
        return;
    }
    parked = false;
#endif
    const uint64_t now = bsp_now_us();
    switch (g_imon_state) {
    case 0u:
        imon_select(g_imon_chain);
        g_imon_t0_us = now;
        g_imon_state = 1u;
        break;
    case 1u:
        if ((now - g_imon_t0_us) >= RRH_IMON_SETTLE_US) {
            ADC4->SQR1 = (uint32_t)PIN_IMON_CH_ADC_CH << ADC_SQR1_SQ1_Pos; /* one conversion */
            ADC4->CR |= ADC_CR_ADSTART;
            g_imon_state = 2u;
        }
        break;
    default:
        if ((ADC4->ISR & ADC_ISR_EOC) != 0u) {
            const uint16_t code = (uint16_t)ADC4->DR;
            g_imon_uv[g_imon_chain] = rrh_board_adc_uv(code);
            g_imon_at_us[g_imon_chain] = now;
            g_imon_chain = (uint8_t)((g_imon_chain + 1u) & 7u);
            g_imon_state = 0u;
        }
        break;
    }
}

void bsp_imon_get(rrh_imon_t *out)
{
    const uint64_t now = bsp_now_us();
    memset(out, 0, sizeof *out);
    out->steps = g_imon_steps;
    for (uint32_t ch = 0u; ch < RRH_CHAINS; ch++) {
        out->uv[ch] = g_imon_uv[ch];
        if ((g_imon_at_us[ch] != 0u) && ((now - g_imon_at_us[ch]) < RRH_IMON_MAX_AGE_US)) {
            out->valid |= (uint8_t)(1u << ch);
        }
    }
}

/* ---- flash: one page for the setup image ------------------------------------------------------------- */
#define NV_ADDR 0x0807F800u /* last 2 kB of the 512 kB flash; the image must end below (checked) */
#define NV_MAGIC 0x31485252u /* "RRH1" */
extern uint32_t _sidata, _sdata, _edata;

static bool flash_wait(void)
{
    for (uint32_t i = 0u; i < 4000000u; i++) {
        if ((FLASH->SR & FLASH_SR_BSY) == 0u) {
            return (FLASH->SR & (FLASH_SR_PROGERR | FLASH_SR_WRPERR | FLASH_SR_PGAERR | FLASH_SR_SIZERR | FLASH_SR_PGSERR)) == 0u;
        }
    }
    return false;
}

bool bsp_nv_load(uint8_t *buf, size_t cap, size_t *len)
{
    const uint32_t *p = (const uint32_t *)NV_ADDR;
    if ((p[0] != NV_MAGIC) || (p[1] == 0u) || (p[1] > cap) || (p[1] > 1024u)) {
        return false;
    }
    memcpy(buf, &p[2], p[1]);
    *len = p[1];
    return true;
}

bool bsp_nv_save(const uint8_t *buf, size_t len)
{
    uint32_t words[64];
    const uintptr_t image_end = (uintptr_t)&_sidata + ((uintptr_t)&_edata - (uintptr_t)&_sdata);
    if ((len > (sizeof words - 8u)) || (image_end > NV_ADDR)) {
        return false;
    }
    memset(words, 0xFF, sizeof words);
    words[0] = NV_MAGIC;
    words[1] = (uint32_t)len;
    memcpy(&words[2], buf, len);
    const uint32_t primask = __get_PRIMASK();
    __disable_irq(); /* a few tens of ms without the link; only ever done while disarmed */
    FLASH->KEYR = 0x45670123u;
    FLASH->KEYR = 0xCDEF89ABu;
    bool ok = flash_wait();
    FLASH->SR = FLASH_SR_PROGERR | FLASH_SR_WRPERR | FLASH_SR_PGAERR | FLASH_SR_SIZERR | FLASH_SR_PGSERR | FLASH_SR_EOP;
    /* Page number: dual-bank (2 kB pages, bank 2 page 127) or single-bank (4 kB pages, page 127).
     * Layout recalled from RM0440: UNVERIFIED. */
    uint32_t cr = FLASH_CR_PER | (127uL << FLASH_CR_PNB_Pos);
    if ((FLASH->OPTR & FLASH_OPTR_DBANK) != 0u) {
        cr |= FLASH_CR_BKER;
    }
    FLASH->CR = cr;
    FLASH->CR |= FLASH_CR_STRT;
    ok = flash_wait() && ok;
    FLASH->CR = FLASH_CR_PG;
    for (uint32_t i = 0u; ok && (i < 64u); i += 2u) {
        volatile uint32_t *dst = (volatile uint32_t *)(NV_ADDR + (i * 4u));
        dst[0] = words[i];
        dst[1] = words[i + 1u];
        ok = flash_wait();
    }
    FLASH->CR = FLASH_CR_LOCK;
    __set_PRIMASK(primask);
    return ok && (memcmp((const void *)NV_ADDR, words, sizeof words) == 0);
}

/* ---- watchdog, reset cause, entropy, misc --------------------------------------------------------------- */
static rrh_reset_cause_t g_reset_cause;

static void reset_cause_capture(void)
{
    const uint32_t csr = RCC->CSR;
    if ((csr & (RCC_CSR_IWDGRSTF | RCC_CSR_WWDGRSTF)) != 0u) {
        g_reset_cause = RRH_RESET_WATCHDOG;
    } else if ((csr & RCC_CSR_SFTRSTF) != 0u) {
        g_reset_cause = RRH_RESET_SOFTWARE;
    } else if ((csr & RCC_CSR_BORRSTF) != 0u) {
        g_reset_cause = RRH_RESET_POWER_ON; /* power-on and brown-out share this flag */
    } else if ((csr & RCC_CSR_PINRSTF) != 0u) {
        g_reset_cause = RRH_RESET_PIN;
    } else {
        g_reset_cause = RRH_RESET_OTHER;
    }
    RCC->CSR |= RCC_CSR_RMVF;
}

rrh_reset_cause_t bsp_reset_cause(void) { return g_reset_cause; }

static void watchdog_init(void)
{
    IWDG->KR = 0xCCCCu; /* start (cannot be stopped again) */
    IWDG->KR = 0x5555u;
    IWDG->PR = 4u;      /* LSI 32 kHz / 64 = 500 Hz */
    IWDG->RLR = 500u;   /* about 1 s */
    for (uint32_t i = 0u; (i < 400000u) && (IWDG->SR != 0u); i++) {
    }
    IWDG->KR = 0xAAAAu;
}

void bsp_watchdog_kick(void) { IWDG->KR = 0xAAAAu; }

bool bsp_rng_words(uint32_t *out, size_t n)
{
    bool ok = true;
    RNG->CR |= RNG_CR_RNGEN;
    for (size_t i = 0u; i < n; i++) {
        if (!wait_set(&RNG->SR, RNG_SR_DRDY, 400000u) || ((RNG->SR & (RNG_SR_SEIS | RNG_SR_CEIS)) != 0u)) {
            ok = false;
            RNG->SR = 0u;
        }
        out[i] = RNG->DR;
    }
    return ok;
}

void bsp_uid(uint8_t out[12])
{
    memcpy(out, (const void *)UID_BASE, 12u);
}

void bsp_led(bool status_on, bool fault_on)
{
    bsp_gpio_write(PIN_LED_STATUS_N_PORT, PIN_LED_STATUS_N_PIN, !status_on); /* active low */
    bsp_gpio_write(PIN_LED_FAULT_N_PORT, PIN_LED_FAULT_N_PIN, !fault_on);
}

void bsp_dbg_puts(const char *s)
{
    while (*s != '\0') {
        (void)wait_set(&UART4->ISR, USART_ISR_TXE, 100000u);
        UART4->TDR = (uint8_t)*s;
        s++;
    }
}

void bsp_init(void)
{
    reset_cause_capture();
    clock_init();

    /* Safe levels first: heater and bias off, latches held cleared, chip selects idle. */
    CFG_OUT(HTR_EN, false);
    CFG_OUT(HV_EN, false);
    CFG_OUT(CLR_F0_N, false);
    CFG_OUT(CLR_F1_N, false);
    CFG_OUT(CLR_F2_N, false);
    CFG_OUT(CLR_F3_N, false);
    CFG_OUT(CLR_R0_N, false);
    CFG_OUT(CLR_R1_N, false);
    CFG_OUT(CLR_R2_N, false);
    CFG_OUT(CLR_R3_N, false);
    CFG_OUT(LATCH_TEST, false);
    CFG_OUT(DAC_CS0_N, true);
    CFG_OUT(DAC_CS1_N, true);
    CFG_OUT(DAC_CS2_N, true);
    CFG_OUT(DAC_CS3_N, true);
    CFG_OUT(LED_STATUS_N, true);
    CFG_OUT(LED_FAULT_N, true);
    CFG_OUT(MON_MUX_A0, false);
    CFG_OUT(MON_MUX_A1, false);
    CFG_OUT(MON_MUX_A2, false);
    CFG_OUT(MON_MUX_A3, false);
    /* Latch read-backs: PD0..PD11 plain inputs. Raw LLD comparator outputs: PD12..15 (TIM4) and
     * PE2..5 (TIM3) as timer inputs; their level is still visible in the port's IDR. */
    for (uint32_t pin = 0u; pin < 12u; pin++) {
        gpio_cfg(GPIOD, pin, MODE_IN, 0u, PULL_DOWN);
    }
    CFG_AF(LLD_F0, PULL_DOWN);
    CFG_AF(LLD_F1, PULL_DOWN);
    CFG_AF(LLD_F2, PULL_DOWN);
    CFG_AF(LLD_F3, PULL_DOWN);
    CFG_AF(LLD_R0, PULL_DOWN);
    CFG_AF(LLD_R1, PULL_DOWN);
    CFG_AF(LLD_R2, PULL_DOWN);
    CFG_AF(LLD_R3, PULL_DOWN);
    /* the six former spare pins (IB-17): anode current monitor, LED strobe, pulse channel select, reserved sync input */
    CFG_ANALOG(IMON_CH);
    CFG_AF(LED_STROBE, PULL_DOWN);
    CFG_OUT(PULSER_A0, false); /* default channel F0 */
    CFG_OUT(PULSER_A1, false);
    CFG_OUT(PULSER_A2, false);
#ifndef RRH_BOARD_NUCLEO
    CFG_IN(SYNC_IN, PULL_DOWN); /* reserved: hardware time pulse, not used by this firmware */
#endif
    CFG_IN(HTR_CUTOUT_OK, PULL_DOWN);
    CFG_IN(BUMP_ZONE_F_N, PULL_UP);
    CFG_IN(BUMP_ZONE_L_N, PULL_UP);
    CFG_IN(BUMP_ZONE_R_N, PULL_UP);
    CFG_AF(BUSY_F0, PULL_DOWN);
    CFG_AF(BUSY_F1, PULL_DOWN);
    CFG_AF(BUSY_F2, PULL_DOWN);
    CFG_AF(BUSY_F3, PULL_DOWN);
    CFG_AF(BUSY_R0, PULL_DOWN);
    CFG_AF(BUSY_R1, PULL_DOWN);
    CFG_AF(BUSY_R2, PULL_DOWN);
    CFG_AF(BUSY_R3, PULL_DOWN);
    CFG_AF(PULSER_STROBE, PULL_DOWN);
    CFG_AF(RS485_TX, PULL_NONE);
    CFG_AF(RS485_RX, PULL_UP);
    CFG_AF(RS485_DE, PULL_DOWN);
    CFG_AF(DBG_TX, PULL_NONE);
    CFG_AF(DBG_RX, PULL_UP);
    CFG_AF(DAC_SCK, PULL_NONE);
    CFG_AF(DAC_MISO, PULL_UP);
    CFG_AF(DAC_MOSI, PULL_NONE);
    CFG_AF(I2C_SCL, PULL_NONE);
    CFG_AF(I2C_SDA, PULL_NONE);
    PIN_I2C_SCL_PORT->OTYPER |= 1uL << PIN_I2C_SCL_PIN; /* open drain */
    PIN_I2C_SDA_PORT->OTYPER |= 1uL << PIN_I2C_SDA_PIN;
    CFG_ANALOG(BIAS_VMON);
    CFG_ANALOG(BIAS_IMON);
    CFG_ANALOG(NTC_SIPM0);
    CFG_ANALOG(NTC_SIPM1);
    CFG_ANALOG(NTC_SIPM2);
    CFG_ANALOG(NTC_SIPM3);
    CFG_ANALOG(NTC_HTR);
    CFG_ANALOG(NTC_BOARD);
    CFG_ANALOG(VIN_MON);
    CFG_ANALOG(HTR_SENSE);
    CFG_ANALOG(MON_ADC);

    timebase_init();
    watchdog_init();
    UART4->BRR = BSP_SYSCLK_HZ / 115200u;
    UART4->CR1 = USART_CR1_TE | USART_CR1_UE;
    spi_setup(SPI1, 4u, false, true); /* DACs: mode 1, 144/32 = 4.5 MHz */
    /* 100 kHz: PRESC 8 (62.5 ns), SCLL 80, SCLH 64, SDADEL 2, SCLDEL 4 (calculated). */
    I2C3->TIMINGR = 0x80423F4Fu;
    I2C3->CR1 = I2C_CR1_PE;
    adc_init();
    adc4_init();
    adc2_init();
    rs485_init();
}
