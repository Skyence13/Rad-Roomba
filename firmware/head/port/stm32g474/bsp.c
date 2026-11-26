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

    /* One wait state for 48 MHz in range 1 normal mode (RM0440 table, UNVERIFIED). */
    FLASH->ACR = (FLASH->ACR & ~FLASH_ACR_LATENCY) | FLASH_ACR_LATENCY_1WS;

    /* PLL input 8 MHz, VCO 96 MHz, R = /2 -> 48 MHz SYSCLK, Q = /2 -> 48 MHz for the RNG. */
    uint32_t cfg = (12uL << RCC_PLLCFGR_PLLN_Pos) | RCC_PLLCFGR_PLLREN | RCC_PLLCFGR_PLLQEN;
    if (g_tcxo_ok) {
        cfg |= RCC_PLLCFGR_PLLSRC_HSE | (2uL << RCC_PLLCFGR_PLLM_Pos); /* 24 MHz / 3 */
    } else {
        cfg |= RCC_PLLCFGR_PLLSRC_HSI | (1uL << RCC_PLLCFGR_PLLM_Pos); /* HSI16 / 2: degraded, flagged */
    }
    RCC->PLLCFGR = cfg;
    RCC->CR |= RCC_CR_PLLON;
    (void)wait_set(&RCC->CR, RCC_CR_PLLRDY, 400000u);
    RCC->CFGR = (RCC->CFGR & ~RCC_CFGR_SW) | RCC_CFGR_SW_PLL;
    (void)wait_set(&RCC->CFGR, RCC_CFGR_SWS_PLL, 400000u);
    SystemCoreClock = BSP_SYSCLK_HZ;

    RCC->CCIPR = (RCC->CCIPR & ~(RCC_CCIPR_CLK48SEL | RCC_CCIPR_ADC12SEL)) | RCC_CCIPR_CLK48SEL_1 | RCC_CCIPR_ADC12SEL_1;
    RCC->CSR |= RCC_CSR_LSION; /* IWDG clock */

    RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN | RCC_AHB2ENR_GPIOBEN | RCC_AHB2ENR_GPIOCEN | RCC_AHB2ENR_GPIODEN |
                    RCC_AHB2ENR_GPIOFEN | RCC_AHB2ENR_ADC12EN | RCC_AHB2ENR_RNGEN;
    RCC->APB1ENR1 |= RCC_APB1ENR1_TIM2EN | RCC_APB1ENR1_SPI3EN | RCC_APB1ENR1_I2C3EN | RCC_APB1ENR1_PWREN;
    RCC->APB1ENR2 |= RCC_APB1ENR2_LPUART1EN;
    RCC->APB2ENR |= RCC_APB2ENR_USART1EN | RCC_APB2ENR_SPI1EN | RCC_APB2ENR_SYSCFGEN;
    (void)RCC->APB2ENR;
    /* PB4 / PB6 are UCPD CC pins: switch their dead-battery pull-downs off (UNVERIFIED need). */
    PWR->CR3 |= PWR_CR3_UCPD_DBDIS;
}

bool bsp_clock_from_tcxo(void)
{
    return g_tcxo_ok;
}

/* ---- head clock: TIM2, 1 MHz, 32 bit, extended to 64 bit ------------------------------------------ */
static volatile uint32_t g_tim_high;
static volatile uint32_t g_gate_edges;
static volatile uint32_t g_gate_last_capture;

uint64_t bsp_now_us(void)
{
    const uint32_t primask = __get_PRIMASK();
    __disable_irq();
    uint32_t high = g_tim_high;
    uint32_t cnt = TIM2->CNT;
    if (((TIM2->SR & TIM_SR_UIF) != 0u)) {
        cnt = TIM2->CNT; /* the counter wrapped and the interrupt has not run yet */
        high++;
    }
    __set_PRIMASK(primask);
    return ((uint64_t)high << 32) | cnt;
}

void bsp_delay_us(uint32_t us)
{
    const uint32_t start = TIM2->CNT;
    while ((TIM2->CNT - start) < us) {
    }
}

static void timebase_init(void)
{
    TIM2->PSC = (BSP_SYSCLK_HZ / 1000000u) - 1u;
    TIM2->ARR = 0xFFFFFFFFu;
    TIM2->EGR = TIM_EGR_UG;
    TIM2->SR = 0u;
    /* CH3: input capture of the FPGA GATE_SYNC toggle (both edges). */
    TIM2->CCMR2 = TIM_CCMR2_CC3S_0;
    TIM2->CCER = TIM_CCER_CC3E | TIM_CCER_CC3P | TIM_CCER_CC3NP;
    TIM2->DIER = TIM_DIER_UIE | TIM_DIER_CC3IE;
    TIM2->CR1 = TIM_CR1_CEN;
    NVIC_SetPriority(TIM2_IRQn, 1);
    NVIC_EnableIRQ(TIM2_IRQn);
}

/* ---- RS-485 on USART1 with hardware driver enable ---------------------------------------------- */
static uint8_t g_rx_store[1024];
static rrc_ring_t g_rx_ring;
static volatile uint64_t g_lf_us;
static const uint8_t *volatile g_tx_data;
static volatile size_t g_tx_len, g_tx_pos;

static void rs485_init(void)
{
    (void)rrc_ring_init(&g_rx_ring, g_rx_store, sizeof g_rx_store);
    USART1->BRR = BSP_SYSCLK_HZ / 1000000u; /* 1 Mbaud, oversampling 16, exact */
    USART1->CR3 = USART_CR3_DEM;            /* DE active high, driven by the USART */
    /* DE asserted 8/16 bit before the start bit and held 8/16 bit after the stop bit (5 us). */
    USART1->CR1 = (8uL << USART_CR1_DEAT_Pos) | (8uL << USART_CR1_DEDT_Pos) | USART_CR1_RE | USART_CR1_TE |
                  USART_CR1_RXNEIE;
    USART1->CR1 |= USART_CR1_UE;
    NVIC_SetPriority(USART1_IRQn, 0); /* highest: receive timestamps */
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
            g_lf_us = bsp_now_us();
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

void TIM2_IRQHandler(void)
{
    const uint32_t sr = TIM2->SR;
    if ((sr & TIM_SR_UIF) != 0u) {
        TIM2->SR = ~TIM_SR_UIF;
        g_tim_high++;
    }
    if (((sr & TIM_SR_CC1IF) != 0u) && ((TIM2->DIER & TIM_DIER_CC1IE) != 0u)) {
        TIM2->DIER &= ~TIM_DIER_CC1IE;
        TIM2->SR = ~TIM_SR_CC1IF;
        USART1->CR1 |= USART_CR1_TXEIE; /* scheduled start of a reply */
    }
    if ((sr & TIM_SR_CC3IF) != 0u) {
        g_gate_last_capture = TIM2->CCR3; /* reading CCR3 clears the flag */
        g_gate_edges++;
    }
}

bool bsp_rs485_pop(uint8_t *byte, uint64_t *rx_us)
{
    if (!rrc_ring_pop(&g_rx_ring, byte)) {
        return false;
    }
    *rx_us = (*byte == (uint8_t)'\n') ? g_lf_us : bsp_now_us();
    return true;
}

uint64_t bsp_rs485_last_lf_us(void)
{
    return g_lf_us;
}

void bsp_rs485_send(const uint8_t *data, size_t len, uint64_t at_us)
{
    USART1->CR1 &= ~USART_CR1_TXEIE;
    g_tx_data = data;
    g_tx_len = len;
    g_tx_pos = 0u;
    if (at_us == 0u) {
        at_us = g_lf_us + BSP_RS485_TURNAROUND_US;
    }
    const uint64_t now = bsp_now_us();
    if (at_us <= (now + 20u)) {
        USART1->CR1 |= USART_CR1_TXEIE;
    } else {
        TIM2->CCR1 = (uint32_t)at_us;
        TIM2->SR = ~TIM_SR_CC1IF;
        TIM2->DIER |= TIM_DIER_CC1IE;
    }
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

void bsp_spi_fpga_mode(bool config_phase)
{
    /* Configuration: mode 3, 48/4 = 12 MHz. Register interface: mode 0, 48/16 = 3 MHz (<= 4 MHz). */
    spi_setup(SPI3, config_phase ? 1u : 3u, config_phase, config_phase);
}

uint8_t bsp_spi_dac_xfer(uint8_t b) { return spi_xfer(SPI1, b); }
uint8_t bsp_spi_fpga_xfer(uint8_t b) { return spi_xfer(SPI3, b); }

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

/* ---- I2C3 (100 kHz; TIMINGR for 48 MHz from the RM0440 example table, UNVERIFIED) ------------------- */
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
    ADC12_COMMON->CCR = (2uL << ADC_CCR_PRESC_Pos); /* kernel clock 48 MHz / 4 = 12 MHz */
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

/* 10 k B3435 NTC to ground with 10.0 k to VREF: ADC code at -40, -30, ... +120 degC (calculated). */
int32_t bsp_ntc_mc(uint16_t code)
{
    static const uint16_t tab[17] = {3936u, 3813u, 3627u, 3368u, 3037u, 2654u, 2248u, 1854u, 1496u,
                                     1191u, 940u,  740u,  584u,  462u,  368u,  295u,  238u};
    if ((code > 4000u) || (code < 150u)) {
        return RRH_TEMP_INVALID; /* open or shorted sensor, or outside -40..+120 degC */
    }
    for (uint32_t i = 0u; i < 16u; i++) {
        if (code >= tab[i + 1u]) {
            const int32_t span = (int32_t)tab[i] - (int32_t)tab[i + 1u];
            const int32_t into = (int32_t)tab[i] - (int32_t)code;
            return (-40000 + ((int32_t)i * 10000)) + ((into * 10000) / span);
        }
    }
    return RRH_TEMP_INVALID;
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
        (void)wait_set(&LPUART1->ISR, USART_ISR_TXE, 100000u);
        LPUART1->TDR = (uint8_t)*s;
        s++;
    }
}

void bsp_init(void)
{
    reset_cause_capture();
    clock_init();

    /* Safe levels first: heater and bias off, FPGA held in reset, chip selects idle. */
    CFG_OUT(HTR_EN, false);
    CFG_OUT(HV_EN, false);
    CFG_OUT(FPGA_CRESET_N, false);
    CFG_OUT(FPGA_SS_N, false);
    CFG_OUT(DAC_CS0_N, true);
    CFG_OUT(DAC_CS1_N, true);
    CFG_OUT(DAC_CS2_N, true);
    CFG_OUT(DAC_CS3_N, true);
    CFG_OUT(LED_STATUS_N, true);
    CFG_OUT(LED_FAULT_N, true);
    CFG_OUT(MON_MUX_A0, false);
    CFG_OUT(MON_MUX_A1, false);
    CFG_OUT(MON_MUX_A2, false);
#ifndef RRH_BOARD_NUCLEO
    CFG_OUT(MON_MUX_A3, false);
#endif
    CFG_IN(FPGA_CDONE, PULL_UP);
    CFG_IN(FPGA_MON_TRIG, PULL_DOWN);
    CFG_IN(FPGA_IRQ, PULL_DOWN);
    CFG_IN(HTR_CUTOUT_OK, PULL_DOWN);
    CFG_IN(BUMP_ZONE_F_N, PULL_UP);
    CFG_IN(BUMP_ZONE_L_N, PULL_UP);
    CFG_IN(BUMP_ZONE_R_N, PULL_UP);
    CFG_AF(RS485_TX, PULL_NONE);
    CFG_AF(RS485_RX, PULL_UP);
    CFG_AF(RS485_DE, PULL_DOWN);
    CFG_AF(DBG_TX, PULL_NONE);
    CFG_AF(DBG_RX, PULL_UP);
    CFG_AF(DAC_SCK, PULL_NONE);
    CFG_AF(DAC_MISO, PULL_UP);
    CFG_AF(DAC_MOSI, PULL_NONE);
    CFG_AF(FPGA_SCK, PULL_NONE);
    CFG_AF(FPGA_MISO, PULL_DOWN);
    CFG_AF(FPGA_MOSI, PULL_NONE);
    CFG_AF(FPGA_GATE, PULL_DOWN);
    CFG_AF(FPGA_SYNC, PULL_NONE);
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
    LPUART1->BRR = (uint32_t)((256uLL * BSP_SYSCLK_HZ) / 115200u);
    LPUART1->CR1 = USART_CR1_TE | USART_CR1_UE;
    spi_setup(SPI1, 2u, false, true); /* DACs: mode 1, 48/8 = 6 MHz */
    bsp_spi_fpga_mode(true);
    I2C3->TIMINGR = 0xB0420F13u;
    I2C3->CR1 = I2C_CR1_PE;
    adc_init();
    rs485_init();
}
