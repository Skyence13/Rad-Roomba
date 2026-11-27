/* RR-CHS-MAIN board support: STM32G474RET6 peripherals behind the chassis core HAL.
 *
 * STATUS: compiles and links; NEVER RUN ON HARDWARE. Items marked UNVERIFIED are recalled from
 * datasheets/reference manuals and must be checked on the bench (see README "First power-up").
 * Not implemented in this revision (the core reports them as warnings and stays safe):
 *   - VL53L4ED ranging (stub, see tof_vl53l4ed.c)      -> all ToF OFFLINE, motion inhibited
 *   - charger (LTC4162-FAD): register map UNVERIFIED (IB-06), driver disabled -> CHARGER_COMM
 * Implemented, never run: INA228 pack monitor, INA3221 branch monitor (TI register maps checked against
 * the datasheets, core/rrch_pwrdev.c), IOX_B P17 = CHAIN_END_RB input (IB-01).
 *   - PWM-synchronous current sampling (currents are sampled free-running and low-passed)
 */
#include <math.h>
#include <string.h>

#include "bsp.h"
#include "rrch_pwrdev.h"

#define P(sig) PIN_##sig##_PORT, PIN_##sig##_PIN
#define RD(sig) ((PIN_##sig##_PORT->IDR & PIN_##sig##_PIN) != 0u)

static TIM_HandleTypeDef htim_us, htim_enc_r, htim_enc_l, htim_ctl, htim_sup, htim_pwm;
static ADC_HandleTypeDef hadc1, hadc2;
static DMA_HandleTypeDef hdma1, hdma2;
static SPI_HandleTypeDef hspi1;
static I2C_HandleTypeDef hi2c_tof, hi2c_sys;
static UART_HandleTypeDef huart_dbg;
static RNG_HandleTypeDef hrng;
static volatile uint16_t adc1_buf[8], adc2_buf[2];
static rrc_wrap32_t us_wrap;
static bool iox_a_ok, imu_ok, iox_b_ok, tof_ok;
static volatile uint16_t iox_b_want;
static uint16_t iox_b_cur = 0xFFFFu;
static int lock_depth;
static rrch_reset_cause_t reset_cause = RRCH_RST_UNKNOWN;
static rrch_retained_t retained __attribute__((section(".noinit"))); /* UNVERIFIED: must not be zeroed by the startup code */
volatile uint32_t bsp_clock_fallback;
extern rrch_t g_core;
static bool io_cfg_check(void);

/* Boot-time WDI toggling (CCR-E11: with JP1 closed the first counted WDI edge is due within 23 ms of
 * reset release). Each call toggles the pin; calls are >= 2.5 ms apart where it matters. Not all of
 * the boot path is covered (HSE start-up timeout, I2C probes): see README "Known gaps". */
static void wdg_boot_toggle(void)
{
    HAL_GPIO_TogglePin(P(WDG_STROBE));
}

static void delay_kicking(uint32_t ms)
{
    for (uint32_t t = 0; t < ms; t += 5u) {
        HAL_Delay(5);
        wdg_boot_toggle();
    }
}

/* ------------------------------------------------------------------ clock */
static void clock_init(void)
{
    RCC_OscInitTypeDef osc = {0};
    RCC_ClkInitTypeDef clk = {0};
    RCC_PeriphCLKInitTypeDef per = {0};
    HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1);
    /* HSE -> 4 MHz PLL input -> VCO 288 MHz -> SYSCLK 144 MHz (R=2), USB/RNG 48 MHz (Q=6) */
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSE | RCC_OSCILLATORTYPE_HSI;
    osc.HSEState = RCC_HSE_ON;
    osc.HSIState = RCC_HSI_ON;
    osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    osc.PLL.PLLM = (RR_HSE_HZ == 24000000) ? RCC_PLLM_DIV6 : RCC_PLLM_DIV2;
    osc.PLL.PLLN = 72;
    osc.PLL.PLLP = RCC_PLLP_DIV2;
    osc.PLL.PLLQ = RCC_PLLQ_DIV6;
    osc.PLL.PLLR = RCC_PLLR_DIV2;
    per.UsbClockSelection = RCC_USBCLKSOURCE_PLL;
    per.RngClockSelection = RCC_RNGCLKSOURCE_PLL;
    if (HAL_RCC_OscConfig(&osc) != HAL_OK) { /* no crystal: HSI16 PLL, USB from HSI48 (bench fallback) */
        bsp_clock_fallback = 1;
        osc.OscillatorType = RCC_OSCILLATORTYPE_HSI | RCC_OSCILLATORTYPE_HSI48;
        osc.HSEState = RCC_HSE_OFF;
        osc.HSI48State = RCC_HSI48_ON;
        osc.PLL.PLLSource = RCC_PLLSOURCE_HSI;
        osc.PLL.PLLM = RCC_PLLM_DIV4;
        (void)HAL_RCC_OscConfig(&osc);
        per.UsbClockSelection = RCC_USBCLKSOURCE_HSI48;
        per.RngClockSelection = RCC_RNGCLKSOURCE_HSI48;
    }
    clk.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clk.APB1CLKDivider = RCC_HCLK_DIV1;
    clk.APB2CLKDivider = RCC_HCLK_DIV1;
    (void)HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_4); /* UNVERIFIED: 4 wait states for 144 MHz in range 1 */
    per.PeriphClockSelection = RCC_PERIPHCLK_USB | RCC_PERIPHCLK_RNG | RCC_PERIPHCLK_ADC12 | RCC_PERIPHCLK_I2C1 | RCC_PERIPHCLK_I2C2;
    per.Adc12ClockSelection = RCC_ADC12CLKSOURCE_SYSCLK;
    per.I2c1ClockSelection = RCC_I2C1CLKSOURCE_HSI; /* 16 MHz kernel clock: timing value below */
    per.I2c2ClockSelection = RCC_I2C2CLKSOURCE_HSI;
    (void)HAL_RCCEx_PeriphCLKConfig(&per);
}

/* ------------------------------------------------------------------ GPIO */
static void gpio(GPIO_TypeDef *port, uint16_t pin, uint32_t mode, uint32_t pull, uint32_t af)
{
    GPIO_InitTypeDef g = {0};
    g.Pin = pin;
    g.Mode = mode;
    g.Pull = pull;
    g.Speed = GPIO_SPEED_FREQ_MEDIUM;
    g.Alternate = af;
    HAL_GPIO_Init(port, &g);
}

static void gpio_init(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_GPIOF_CLK_ENABLE();
    __HAL_RCC_PWR_CLK_ENABLE();
    HAL_PWREx_DisableUCPDDeadBattery(); /* releases the pull-downs on PB4/PB6 (encoder inputs) */

    /* outputs: write the safe level BEFORE switching the pin to output */
    HAL_GPIO_WritePin(P(ARM_PERMIT), GPIO_PIN_RESET);
    HAL_GPIO_WritePin(P(DRV_NSLEEP), GPIO_PIN_RESET);
    HAL_GPIO_WritePin(P(HEAD_HTR_EN), GPIO_PIN_RESET);
    HAL_GPIO_WritePin(P(CHS_HTR_EN), GPIO_PIN_RESET);
    HAL_GPIO_WritePin(P(BUZZER), GPIO_PIN_RESET);
    HAL_GPIO_WritePin(P(WDG_STROBE), GPIO_PIN_RESET);
    HAL_GPIO_WritePin(P(IMU_CS_ACC_N), GPIO_PIN_SET);
    HAL_GPIO_WritePin(P(IMU_CS_GYR_N), GPIO_PIN_SET);
    HAL_GPIO_WritePin(P(IOX_A_CS_N), GPIO_PIN_SET);
    gpio(P(ARM_PERMIT), GPIO_MODE_OUTPUT_PP, GPIO_NOPULL, 0);
    gpio(P(DRV_NSLEEP), GPIO_MODE_OUTPUT_PP, GPIO_NOPULL, 0);
    gpio(P(HEAD_HTR_EN), GPIO_MODE_OUTPUT_PP, GPIO_NOPULL, 0);
    gpio(P(CHS_HTR_EN), GPIO_MODE_OUTPUT_PP, GPIO_NOPULL, 0);
    gpio(P(BUZZER), GPIO_MODE_OUTPUT_PP, GPIO_NOPULL, 0); /* level drive (self-oscillating buzzer); TIM5_CH1 tone not used */
    gpio(P(WDG_STROBE), GPIO_MODE_OUTPUT_PP, GPIO_NOPULL, 0);
    gpio(P(IMU_CS_ACC_N), GPIO_MODE_OUTPUT_PP, GPIO_NOPULL, 0);
    gpio(P(IMU_CS_GYR_N), GPIO_MODE_OUTPUT_PP, GPIO_NOPULL, 0);
    gpio(P(IOX_A_CS_N), GPIO_MODE_OUTPUT_PP, GPIO_NOPULL, 0);
    gpio(P(BOOT0_LED_STAT), GPIO_MODE_OUTPUT_PP, GPIO_NOPULL, 0);

    /* readbacks: NO internal pulls (review M3). The chain taps are 100k/56k dividers whose 56 k already
     * defines the open-wire level; an internal pull-down (25-55 k) loads them below VIH at normal pack
     * voltage. ESTOP_B/J2 have 10 k pull-downs (R121/R124), PC14/PC15 10 k pull-ups + Q41/Q42 inverters.
     * PD2 (HW_LATCH_RB) is also U9.B: it is TIM8_BKIN (AF, input-only function) and never an output. */
    gpio(P(ESTOP_A_RB), GPIO_MODE_INPUT, GPIO_NOPULL, 0);
    gpio(P(ESTOP_B_RB), GPIO_MODE_INPUT, GPIO_NOPULL, 0);
    gpio(P(HW_LATCH_RB), GPIO_MODE_AF_PP, GPIO_NOPULL, PIN_HW_LATCH_RB_ALT_AF);
    gpio(P(BRAKE_L_RB), GPIO_MODE_INPUT, GPIO_NOPULL, 0);
    gpio(P(BRAKE_R_RB), GPIO_MODE_INPUT, GPIO_NOPULL, 0);
    gpio(P(WDG_OK_RB), GPIO_MODE_INPUT, GPIO_NOPULL, 0);
    gpio(P(J2_PRES_RB), GPIO_MODE_INPUT, GPIO_NOPULL, 0);

    /* analog */
    gpio(P(IPROPI_L), GPIO_MODE_ANALOG, GPIO_NOPULL, 0);
    gpio(P(IPROPI_R), GPIO_MODE_ANALOG, GPIO_NOPULL, 0);
    gpio(P(VMOT_SENSE), GPIO_MODE_ANALOG, GPIO_NOPULL, 0);
    gpio(P(VBAT_SENSE), GPIO_MODE_ANALOG, GPIO_NOPULL, 0);
    gpio(P(HEAD_PRES_ID), GPIO_MODE_ANALOG, GPIO_NOPULL, 0);
    gpio(P(HEAD_LOOP_SENSE), GPIO_MODE_ANALOG, GPIO_NOPULL, 0);
    gpio(P(NTC_BAY), GPIO_MODE_ANALOG, GPIO_NOPULL, 0);
    gpio(P(NTC_PACK), GPIO_MODE_ANALOG, GPIO_NOPULL, 0);
    gpio(P(NTC_BOARD), GPIO_MODE_ANALOG, GPIO_NOPULL, 0);
    gpio(P(V5_SENSE), GPIO_MODE_ANALOG, GPIO_NOPULL, 0);

    /* alternate functions */
    gpio(P(SPI1_SCK), GPIO_MODE_AF_PP, GPIO_NOPULL, PIN_SPI1_SCK_AF);
    gpio(P(SPI1_MISO), GPIO_MODE_AF_PP, GPIO_PULLDOWN, PIN_SPI1_MISO_AF);
    gpio(P(SPI1_MOSI), GPIO_MODE_AF_PP, GPIO_NOPULL, PIN_SPI1_MOSI_AF);
    gpio(P(I2C_SYS_SDA), GPIO_MODE_AF_OD, GPIO_NOPULL, PIN_I2C_SYS_SDA_AF);
    gpio(P(I2C_SYS_SCL), GPIO_MODE_AF_OD, GPIO_NOPULL, PIN_I2C_SYS_SCL_AF);
    gpio(P(I2C_TOF_SCL), GPIO_MODE_AF_OD, GPIO_NOPULL, PIN_I2C_TOF_SCL_AF);
    gpio(P(I2C_TOF_SDA), GPIO_MODE_AF_OD, GPIO_NOPULL, PIN_I2C_TOF_SDA_AF);
    gpio(P(MOT_L_IN1), GPIO_MODE_AF_PP, GPIO_PULLDOWN, PIN_MOT_L_IN1_AF);
    gpio(P(MOT_L_IN2), GPIO_MODE_AF_PP, GPIO_PULLDOWN, PIN_MOT_L_IN2_AF);
    gpio(P(MOT_R_IN1), GPIO_MODE_AF_PP, GPIO_PULLDOWN, PIN_MOT_R_IN1_AF);
    gpio(P(MOT_R_IN2), GPIO_MODE_AF_PP, GPIO_PULLDOWN, PIN_MOT_R_IN2_AF);
    gpio(P(ENC_R_A), GPIO_MODE_AF_PP, GPIO_NOPULL, PIN_ENC_R_A_AF);
    gpio(P(ENC_R_B), GPIO_MODE_AF_PP, GPIO_NOPULL, PIN_ENC_R_B_AF);
    gpio(P(ENC_L_A), GPIO_MODE_AF_PP, GPIO_NOPULL, PIN_ENC_L_A_AF);
    gpio(P(ENC_L_B), GPIO_MODE_AF_PP, GPIO_NOPULL, PIN_ENC_L_B_AF);
    gpio(P(DBG_TX), GPIO_MODE_AF_PP, GPIO_NOPULL, PIN_DBG_TX_AF);
    gpio(P(DBG_RX), GPIO_MODE_AF_PP, GPIO_PULLUP, PIN_DBG_RX_AF);
    /* USB DM/DP, SWD and the oscillator pins keep their reset function */
}

/* ------------------------------------------------------------------ timers */
static void timers_init(void)
{
    uint32_t tclk = HAL_RCC_GetPCLK1Freq(); /* APB prescalers are 1: timer clock = PCLK = 144 MHz */
    __HAL_RCC_TIM2_CLK_ENABLE();
    __HAL_RCC_TIM3_CLK_ENABLE();
    __HAL_RCC_TIM4_CLK_ENABLE();
    __HAL_RCC_TIM6_CLK_ENABLE();
    __HAL_RCC_TIM7_CLK_ENABLE();
    __HAL_RCC_TIM8_CLK_ENABLE();

    /* chassis clock: 32-bit counter at 1 MHz, extended to 64 bits in software */
    htim_us.Instance = TIM2;
    htim_us.Init.Prescaler = tclk / 1000000u - 1u;
    htim_us.Init.Period = 0xFFFFFFFFu;
    htim_us.Init.CounterMode = TIM_COUNTERMODE_UP;
    (void)HAL_TIM_Base_Init(&htim_us);
    (void)HAL_TIM_Base_Start(&htim_us);
    rrc_wrap32_init(&us_wrap, 0);

    /* quadrature decoders, 4 edges per cycle, 16-bit free running */
    TIM_Encoder_InitTypeDef enc = {0};
    enc.EncoderMode = TIM_ENCODERMODE_TI12;
    enc.IC1Polarity = enc.IC2Polarity = TIM_ICPOLARITY_RISING;
    enc.IC1Selection = enc.IC2Selection = TIM_ICSELECTION_DIRECTTI;
    enc.IC1Filter = enc.IC2Filter = 6;
    htim_enc_r.Instance = TIM3;
    htim_enc_l.Instance = TIM4;
    htim_enc_r.Init.Period = htim_enc_l.Init.Period = 0xFFFFu;
    (void)HAL_TIM_Encoder_Init(&htim_enc_r, &enc);
    (void)HAL_TIM_Encoder_Init(&htim_enc_l, &enc);
    (void)HAL_TIM_Encoder_Start(&htim_enc_r, TIM_CHANNEL_ALL);
    (void)HAL_TIM_Encoder_Start(&htim_enc_l, TIM_CHANNEL_ALL);

    /* bridge PWM: centre aligned 20 kHz, four channels. TIM8 break on PD2 = HW_LATCH_RB (RUN_12V tap),
     * active low, automatic output re-enable: PWM is forced to its idle (low) state in hardware whenever
     * the latch readback is low - the fourth path of safety_chain.md 2.1 (review M4). UNVERIFIED on a board.
     * The brake-test probe then applies nothing, which is consistent: U9 holds the bridges asleep anyway. */
    TIM_OC_InitTypeDef oc = {0};
    htim_pwm.Instance = TIM8;
    htim_pwm.Init.CounterMode = TIM_COUNTERMODE_CENTERALIGNED1;
    htim_pwm.Init.Period = tclk / (2u * RR_PWM_HZ);
    (void)HAL_TIM_PWM_Init(&htim_pwm);
    oc.OCMode = TIM_OCMODE_PWM1;
    oc.OCPolarity = TIM_OCPOLARITY_HIGH;
    oc.Pulse = 0;
    static const uint32_t chs[4] = {TIM_CHANNEL_1, TIM_CHANNEL_2, TIM_CHANNEL_3, TIM_CHANNEL_4};
    for (int i = 0; i < 4; i++) {
        (void)HAL_TIM_PWM_ConfigChannel(&htim_pwm, &oc, chs[i]);
        (void)HAL_TIM_PWM_Start(&htim_pwm, chs[i]);
    }
    TIM_BreakDeadTimeConfigTypeDef bk = {0};
    bk.OffStateRunMode = TIM_OSSR_DISABLE;
    bk.OffStateIDLEMode = TIM_OSSI_DISABLE;
    bk.LockLevel = TIM_LOCKLEVEL_OFF;
    bk.DeadTime = 0;
    bk.BreakState = TIM_BREAK_ENABLE;
    bk.BreakPolarity = TIM_BREAKPOLARITY_LOW;
    bk.BreakFilter = 2;
    bk.Break2State = TIM_BREAK2_DISABLE;
    bk.AutomaticOutput = TIM_AUTOMATICOUTPUT_ENABLE;
    (void)HAL_TIMEx_ConfigBreakDeadTime(&htim_pwm, &bk);

    /* control tick 1 kHz and supervision tick 100 Hz from two separate timers */
    htim_ctl.Instance = TIM6;
    htim_ctl.Init.Prescaler = tclk / 1000000u - 1u;
    htim_ctl.Init.Period = 1000u - 1u;
    (void)HAL_TIM_Base_Init(&htim_ctl);
    htim_sup.Instance = TIM7;
    htim_sup.Init.Prescaler = tclk / 1000000u - 1u;
    htim_sup.Init.Period = RR_WDG_STROBE_PERIOD_MS * 1000u - 1u;
    (void)HAL_TIM_Base_Init(&htim_sup);
}

void bsp_start_ticks(void)
{
    HAL_NVIC_SetPriority(TIM6_DAC_IRQn, 1, 0);
    HAL_NVIC_SetPriority(TIM7_DAC_IRQn, 2, 0);
    HAL_NVIC_EnableIRQ(TIM6_DAC_IRQn);
    HAL_NVIC_EnableIRQ(TIM7_DAC_IRQn);
    (void)HAL_TIM_Base_Start_IT(&htim_ctl);
    (void)HAL_TIM_Base_Start_IT(&htim_sup);
}

void TIM6_DAC_IRQHandler(void)
{
    __HAL_TIM_CLEAR_IT(&htim_ctl, TIM_IT_UPDATE);
    rrch_tick_1khz(&g_core);
}

void TIM7_DAC_IRQHandler(void)
{
    __HAL_TIM_CLEAR_IT(&htim_sup, TIM_IT_UPDATE);
    rrch_supervise_100hz(&g_core);
}

void SysTick_Handler(void)
{
    HAL_IncTick();
}

uint64_t bsp_now_us(void)
{
    uint32_t pm = __get_PRIMASK();
    __disable_irq();
    uint64_t t = rrc_wrap32_extend(&us_wrap, TIM2->CNT);
    __set_PRIMASK(pm);
    return t;
}

/* ------------------------------------------------------------------ ADC */
static void adc_one(ADC_HandleTypeDef *h, ADC_TypeDef *inst, DMA_HandleTypeDef *d, DMA_Channel_TypeDef *dch, uint32_t req, const uint32_t *chan, uint32_t n,
                    volatile uint16_t *buf)
{
    static const uint32_t rank[8] = {ADC_REGULAR_RANK_1, ADC_REGULAR_RANK_2, ADC_REGULAR_RANK_3, ADC_REGULAR_RANK_4,
                                     ADC_REGULAR_RANK_5, ADC_REGULAR_RANK_6, ADC_REGULAR_RANK_7, ADC_REGULAR_RANK_8};
    d->Instance = dch;
    d->Init.Request = req;
    d->Init.Direction = DMA_PERIPH_TO_MEMORY;
    d->Init.PeriphInc = DMA_PINC_DISABLE;
    d->Init.MemInc = DMA_MINC_ENABLE;
    d->Init.PeriphDataAlignment = DMA_PDATAALIGN_HALFWORD;
    d->Init.MemDataAlignment = DMA_MDATAALIGN_HALFWORD;
    d->Init.Mode = DMA_CIRCULAR;
    d->Init.Priority = DMA_PRIORITY_LOW;
    (void)HAL_DMA_Init(d);
    __HAL_LINKDMA(h, DMA_Handle, *d);
    h->Instance = inst;
    h->Init.ClockPrescaler = ADC_CLOCK_SYNC_PCLK_DIV4;
    h->Init.Resolution = ADC_RESOLUTION_12B;
    h->Init.DataAlign = ADC_DATAALIGN_RIGHT;
    h->Init.ScanConvMode = ADC_SCAN_ENABLE;
    h->Init.EOCSelection = ADC_EOC_SEQ_CONV;
    h->Init.ContinuousConvMode = ENABLE;
    h->Init.NbrOfConversion = n;
    h->Init.ExternalTrigConv = ADC_SOFTWARE_START;
    h->Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_NONE;
    h->Init.DMAContinuousRequests = ENABLE;
    h->Init.Overrun = ADC_OVR_DATA_OVERWRITTEN;
    (void)HAL_ADC_Init(h);
    for (uint32_t i = 0; i < n; i++) {
        ADC_ChannelConfTypeDef c = {0};
        c.Channel = chan[i];
        c.Rank = rank[i];
        c.SamplingTime = ADC_SAMPLETIME_47CYCLES_5;
        c.SingleDiff = ADC_SINGLE_ENDED;
        c.OffsetNumber = ADC_OFFSET_NONE;
        (void)HAL_ADC_ConfigChannel(h, &c);
    }
    (void)HAL_ADCEx_Calibration_Start(h, ADC_SINGLE_ENDED);
    (void)HAL_ADC_Start_DMA(h, (uint32_t *)(uintptr_t)buf, n);
}

enum { A1_IPROPI_L, A1_VMOT, A1_VBAT, A1_PRES, A1_LOOP, A1_NTC_BAY, A1_NTC_PACK, A1_V5 };

static void adc_init(void)
{
    /* order = enum above; channel numbers from pinmap.yaml (ADC1_IN1,3,4,6,7,8,9,12 and ADC2_IN2,5) */
    static const uint32_t c1[8] = {ADC_CHANNEL_1, ADC_CHANNEL_3, ADC_CHANNEL_4, ADC_CHANNEL_6, ADC_CHANNEL_7, ADC_CHANNEL_8, ADC_CHANNEL_9, ADC_CHANNEL_12};
    static const uint32_t c2[2] = {ADC_CHANNEL_2, ADC_CHANNEL_5};
    __HAL_RCC_ADC12_CLK_ENABLE();
    __HAL_RCC_DMAMUX1_CLK_ENABLE();
    __HAL_RCC_DMA1_CLK_ENABLE();
    adc_one(&hadc1, ADC1, &hdma1, DMA1_Channel1, DMA_REQUEST_ADC1, c1, 8, adc1_buf);
    adc_one(&hadc2, ADC2, &hdma2, DMA1_Channel2, DMA_REQUEST_ADC2, c2, 2, adc2_buf);
}

static float adc_v(uint16_t raw)
{
    return (float)raw * (RR_VREF / 4095.0f);
}

static uint32_t ratio_ohm(uint16_t raw, float pullup)
{
    float x = (float)raw / 4095.0f;
    if (x > 0.985f) {
        return 1000000u; /* open */
    }
    return (uint32_t)(pullup * x / (1.0f - x));
}

static uint32_t loop_ohm(uint16_t raw)
{
    float v = adc_v(raw);
    if (v < 0.05f) {
        return 1000000u; /* open loop or unplugged */
    }
    float r = RR_LOOP_V5AUX * RR_LOOP_RSENSE / v - RR_LOOP_RSERIES - RR_LOOP_RSENSE;
    return r < 0.0f ? 0u : (r > 1.0e6f ? 1000000u : (uint32_t)r);
}

static float ntc_c(uint16_t raw)
{
    float x = (float)raw / 4095.0f;
    if (x < 0.01f || x > 0.99f) {
        return NAN; /* short or open */
    }
    float r = RR_NTC_PULLUP * x / (1.0f - x);
    return 1.0f / (1.0f / 298.15f + logf(r / RR_NTC_R0) / RR_NTC_BETA) - 273.15f;
}

/* ------------------------------------------------------------------ SPI devices (control tick context) */
static bool spi_xfer(GPIO_TypeDef *cs_port, uint16_t cs_pin, const uint8_t *tx, uint8_t *rx, uint16_t n)
{
    HAL_GPIO_WritePin(cs_port, cs_pin, GPIO_PIN_RESET);
    bool ok = HAL_SPI_TransmitReceive(&hspi1, (uint8_t *)(uintptr_t)tx, rx, n, 2) == HAL_OK;
    HAL_GPIO_WritePin(cs_port, cs_pin, GPIO_PIN_SET);
    return ok;
}

/* UNVERIFIED register numbers (BMI088 data sheet, recalled): accel CHIP_ID 0x00 = 0x1E, data from
 * 0x12, ACC_CONF 0x40, ACC_RANGE 0x41, ACC_PWR_CONF 0x7C, ACC_PWR_CTRL 0x7D; gyro CHIP_ID 0x00 =
 * 0x0F, rate data from 0x02, RANGE 0x0F, BANDWIDTH 0x10. Accelerometer reads return one dummy
 * byte first. If either chip id does not match, imu_ok stays false and the core reports
 * IMU_FAULT instead of using wrong data. */
static void bmi088_wr(GPIO_TypeDef *port, uint16_t pin, uint8_t reg, uint8_t val)
{
    uint8_t tx[2] = {reg & 0x7Fu, val}, rx[2];
    (void)spi_xfer(port, pin, tx, rx, 2);
}

static void spi_dev_init(void)
{
    __HAL_RCC_SPI1_CLK_ENABLE();
    hspi1.Instance = SPI1;
    hspi1.Init.Mode = SPI_MODE_MASTER;
    hspi1.Init.Direction = SPI_DIRECTION_2LINES;
    hspi1.Init.DataSize = SPI_DATASIZE_8BIT;
    hspi1.Init.CLKPolarity = SPI_POLARITY_HIGH;
    hspi1.Init.CLKPhase = SPI_PHASE_2EDGE;
    hspi1.Init.NSS = SPI_NSS_SOFT;
    hspi1.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_32; /* 4.5 MHz */
    hspi1.Init.FirstBit = SPI_FIRSTBIT_MSB;
    (void)HAL_SPI_Init(&hspi1);

    uint8_t tx[4] = {0}, rx[4] = {0};
    /* IOX_A (MCP23S17 class, UNVERIFIED opcodes): read IODIRA (0x00); power-on value is 0xFF = all inputs */
    tx[0] = 0x41;
    tx[1] = 0x00;
    iox_a_ok = spi_xfer(P(IOX_A_CS_N), tx, rx, 3) && rx[2] == 0xFFu;

    /* BMI088 */
    tx[0] = 0x80;
    (void)spi_xfer(P(IMU_CS_ACC_N), tx, rx, 3); /* first access switches the accelerometer to SPI */
    delay_kicking(5);
    bool acc = spi_xfer(P(IMU_CS_ACC_N), tx, rx, 3) && rx[2] == 0x1Eu;
    bool gyr = spi_xfer(P(IMU_CS_GYR_N), tx, rx, 2) && rx[1] == 0x0Fu;
    if (acc && gyr) {
        bmi088_wr(P(IMU_CS_ACC_N), 0x7C, 0x00); /* active mode */
        bmi088_wr(P(IMU_CS_ACC_N), 0x7D, 0x04); /* accelerometer on */
        delay_kicking(50);
        bmi088_wr(P(IMU_CS_ACC_N), 0x41, 0x00); /* +-3 g */
        bmi088_wr(P(IMU_CS_ACC_N), 0x40, 0xAB); /* 800 Hz, normal filter */
        bmi088_wr(P(IMU_CS_GYR_N), 0x0F, 0x02); /* +-500 deg/s */
        bmi088_wr(P(IMU_CS_GYR_N), 0x10, 0x02); /* 1 kHz ODR, 116 Hz filter */
    }
    imu_ok = acc && gyr;
}

/* ------------------------------------------------------------------ I2C devices (background context) */
static bool i2c_wr(I2C_HandleTypeDef *bus, uint8_t addr7, const uint8_t *data, uint16_t n)
{
    return HAL_I2C_Master_Transmit(bus, (uint16_t)(addr7 << 1), (uint8_t *)(uintptr_t)data, n, 5) == HAL_OK;
}

static bool i2c_rd_reg(I2C_HandleTypeDef *bus, uint8_t addr7, uint8_t reg, uint8_t *data, uint16_t n)
{
    return HAL_I2C_Mem_Read(bus, (uint16_t)(addr7 << 1), reg, I2C_MEMADD_SIZE_8BIT, data, n, 5) == HAL_OK;
}

/* INA228 pack monitor (SLYS021A): ADCRANGE 1, SHUNT_CAL for 1 mOhm / 100 uA LSB; ADC_CONFIG left at its
 * reset value FB68h (continuous bus, shunt and temperature). Identity checked before use. */
static bool pmon_ok, branch_ok;
static bool i2c_rd16(uint8_t addr, uint8_t reg, uint8_t b[2]);
static void pmon_init(void)
{
    uint8_t mfr[2], dev[2];
    pmon_ok = i2c_rd16(I2C_ADDR_PMON, RR_INA228_REG_MANUFACTURER_ID, mfr) && i2c_rd16(I2C_ADDR_PMON, RR_INA228_REG_DEVICE_ID, dev) &&
              rr_ina228_id_ok(mfr, dev);
    if (pmon_ok) {
        uint16_t cal = rr_ina228_shunt_cal(RR_PMON_CURRENT_LSB, RR_PMON_SHUNT_OHM, true);
        uint8_t c1[3] = {RR_INA228_REG_CONFIG, (uint8_t)(RR_INA228_CONFIG_ADCRANGE >> 8), (uint8_t)RR_INA228_CONFIG_ADCRANGE};
        uint8_t c2[3] = {RR_INA228_REG_SHUNT_CAL, (uint8_t)(cal >> 8), (uint8_t)cal};
        pmon_ok = i2c_wr(&hi2c_sys, I2C_ADDR_PMON, c1, 3) && i2c_wr(&hi2c_sys, I2C_ADDR_PMON, c2, 3);
    }
}

/* INA3221 branch monitor (SBOS576C): reset configuration 7127h is used as is (all channels, continuous). */
static void branch_init(void)
{
    uint8_t mfr[2], die[2];
    branch_ok = i2c_rd16(I2C_ADDR_BRANCH, RR_INA3221_REG_MANUFACTURER_ID, mfr) && i2c_rd16(I2C_ADDR_BRANCH, RR_INA3221_REG_DIE_ID, die) &&
                rr_ina3221_id_ok(mfr, die);
}

static bool i2c_rd16(uint8_t addr, uint8_t reg, uint8_t b[2])
{
    return i2c_rd_reg(&hi2c_sys, addr, reg, b, 2);
}

static void i2c_init(void)
{
    __HAL_RCC_I2C1_CLK_ENABLE();
    __HAL_RCC_I2C2_CLK_ENABLE();
    hi2c_tof.Instance = I2C1;
    hi2c_sys.Instance = I2C2;
    /* 400 kHz from the 16 MHz HSI kernel clock: PRESC 1, SCLDEL 3, SDADEL 2, SCLH 3, SCLL 9
     * (reference-manual example values; UNVERIFIED on this board, check with a scope). */
    hi2c_tof.Init.Timing = hi2c_sys.Init.Timing = 0x10320309u;
    hi2c_tof.Init.AddressingMode = hi2c_sys.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
    (void)HAL_I2C_Init(&hi2c_tof);
    (void)HAL_I2C_Init(&hi2c_sys);
    /* IOX_B (TCA9535 class, UNVERIFIED registers: output 0x02/0x03, configuration 0x06/0x07):
     * load the output latch first, then make every pin an output. Defaults: LiDAR on, 5 V rail
     * request not asserted, ToF held in reset until the driver starts them, head power off. */
    iox_b_want = (uint16_t)(1u << IOX_B_BIT_V12_LIDAR_EN);
    uint8_t out[3] = {0x02, (uint8_t)iox_b_want, (uint8_t)(iox_b_want >> 8)};
    /* every pin an output except IOX_B_INPUT_MASK (P17 = CHAIN_END_RB, CCR-E02: never driven) */
    uint8_t cfg[3] = {0x06, (uint8_t)IOX_B_INPUT_MASK, (uint8_t)(IOX_B_INPUT_MASK >> 8)};
    iox_b_ok = i2c_wr(&hi2c_sys, IOX_B_I2C_ADDR, out, 3) && i2c_wr(&hi2c_sys, IOX_B_I2C_ADDR, cfg, 3);
    iox_b_cur = iox_b_ok ? iox_b_want : 0xFFFFu;
    tof_ok = tof_init(&hi2c_tof);
    pmon_init();
    branch_init();
}

/* ------------------------------------------------------------------ non-volatile storage
 * Three slots, one 2 KB flash page each, at the end of bank 2 (0x0807E800...). Layout per page:
 * length (u32), ~length (u32), data. UNVERIFIED: assumes the factory dual-bank configuration
 * (DBANK = 1, 2 KB pages) so that erasing bank 2 does not stall code running from bank 1; the
 * image must stay below 256 KB (checked by check.sh). The boot counter page is erased once per
 * boot: 10 k boots endurance, to be replaced by an append log before series use. */
#define NV_PAGE0 125u
#define NV_ADDR(slot) (0x08040000u + (NV_PAGE0 + (uint32_t)(slot)) * 0x800u)

static bool nv_read(void *ctx, int slot, uint8_t *buf, size_t cap, size_t *len)
{
    (void)ctx;
    if (slot < 0 || slot > 2) {
        return false;
    }
    const uint32_t *p = (const uint32_t *)NV_ADDR(slot);
    if (p[0] != ~p[1] || p[0] == 0u || p[0] > cap || p[0] > 0x800u - 8u) {
        return false;
    }
    memcpy(buf, &p[2], p[0]);
    *len = p[0];
    return true;
}

static bool nv_write(void *ctx, int slot, const uint8_t *buf, size_t len)
{
    (void)ctx;
    if (slot < 0 || slot > 2 || len > 0x800u - 8u) {
        return false;
    }
    FLASH_EraseInitTypeDef er = {0};
    uint32_t err = 0, addr = NV_ADDR(slot);
    bool ok = HAL_FLASH_Unlock() == HAL_OK;
    er.TypeErase = FLASH_TYPEERASE_PAGES;
    er.Banks = FLASH_BANK_2;
    er.Page = NV_PAGE0 + (uint32_t)slot;
    er.NbPages = 1;
    ok = ok && HAL_FLASHEx_Erase(&er, &err) == HAL_OK;
    uint64_t w = (uint64_t)(uint32_t)len | ((uint64_t)(~(uint32_t)len) << 32);
    ok = ok && HAL_FLASH_Program(FLASH_TYPEPROGRAM_DOUBLEWORD, addr, w) == HAL_OK;
    for (size_t i = 0; ok && i < len; i += 8u) {
        uint8_t chunk[8] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
        memcpy(chunk, buf + i, (len - i) < 8u ? (len - i) : 8u);
        memcpy(&w, chunk, 8);
        ok = HAL_FLASH_Program(FLASH_TYPEPROGRAM_DOUBLEWORD, addr + 8u + (uint32_t)i, w) == HAL_OK;
    }
    (void)HAL_FLASH_Lock();
    return ok;
}

/* ------------------------------------------------------------------ core HAL */
static uint64_t h_now(void *ctx)
{
    (void)ctx;
    return bsp_now_us();
}

static void h_read(void *ctx, rrch_in_t *in)
{
    (void)ctx;
    uint32_t di = 0;
    uint8_t tx[8] = {0x41, 0x12, 0, 0}, rx[8] = {0};
    /* fast expander: GPIOA + GPIOB in one transfer; GPB7 must follow the watchdog strobe net */
    bool xok = iox_a_ok && spi_xfer(P(IOX_A_CS_N), tx, rx, 4);
    uint16_t x = (uint16_t)(rx[2] | ((uint16_t)rx[3] << 8));
    bool strobe = (PIN_WDG_STROBE_PORT->ODR & PIN_WDG_STROBE_PIN) != 0u;
    xok = xok && (((x >> IOX_A_BIT_SENTINEL) & 1u) == (strobe ? 1u : 0u));
#define XB(bit) (((x >> (bit)) & 1u) != 0u)
#define SET(name, v) if (v) { di |= RRCH_DI(name); }
    if (xok) {
        SET(MODE_RUN, XB(IOX_A_BIT_MODE_RUN_RB))
        SET(HANDS_ON, XB(IOX_A_BIT_HANDS_ON_RB))
        SET(CHG_COVER, XB(IOX_A_BIT_CHG_COVER_RB))
        SET(CHG_PLUG_LINK, XB(IOX_A_BIT_CHG_PLUG_LINK_RB))
        SET(HEAD_DOCK, XB(IOX_A_BIT_HEAD_DOCK_RB))
        SET(HEAD_LOOP_OK, XB(IOX_A_BIT_HEAD_LOOP_OK_RB))
        SET(HEAD_LOOP_SHORT, XB(IOX_A_BIT_HEAD_LOOP_SHORT_RB))
        SET(LAB_KEY_N, XB(IOX_A_BIT_LAB_KEY_N_RB))
        SET(BODY_BUMPER_L, XB(IOX_A_BIT_BODY_BUMPER_L_RB))
        SET(BODY_BUMPER_R, XB(IOX_A_BIT_BODY_BUMPER_R_RB))
        SET(BTN_REARM, XB(IOX_A_BIT_REARM_BTN))
        SET(BTN_PAUSE, XB(IOX_A_BIT_PAUSE_BTN))
        SET(DRV_FAULT_L, !XB(IOX_A_BIT_DRV_L_NFAULT))
        SET(DRV_FAULT_R, !XB(IOX_A_BIT_DRV_R_NFAULT))
        SET(BUS_CLAMP, XB(IOX_A_BIT_BUS_CLAMP_ACTIVE))
    } /* else: every expander readback reads "open / unhealthy" and iox_ok is false */
    SET(ESTOP_A, RD(ESTOP_A_RB))
    SET(ESTOP_B, RD(ESTOP_B_RB))
    SET(HW_LATCH, RD(HW_LATCH_RB))
    SET(BRAKE_L, RD(BRAKE_L_RB))
    SET(BRAKE_R, RD(BRAKE_R_RB))
    SET(WDG_OK, RD(WDG_OK_RB))
    SET(J2_PRES, RD(J2_PRES_RB))
#undef SET
#undef XB
    static uint32_t n_cfg;
    static bool cfg_ok = true;
    if (n_cfg++ % 100u == 0u) {
        cfg_ok = io_cfg_check();
    }
    memset(in, 0, sizeof *in);
    in->di = di;
    in->iox_ok = xok;
    in->io_cfg_ok = cfg_ok;
    /* ADC liveness: each ADC must have finished at least one sequence since the previous tick */
    in->adc_ok = __HAL_ADC_GET_FLAG(&hadc1, ADC_FLAG_EOS) && __HAL_ADC_GET_FLAG(&hadc2, ADC_FLAG_EOS);
    __HAL_ADC_CLEAR_FLAG(&hadc1, ADC_FLAG_EOS);
    __HAL_ADC_CLEAR_FLAG(&hadc2, ADC_FLAG_EOS);
    in->pres_ohm = ratio_ohm(adc1_buf[A1_PRES], RR_PRES_PULLUP_OHM);
    in->loop_ohm = loop_ohm(adc1_buf[A1_LOOP]);
    in->vmot_v = adc_v(adc1_buf[A1_VMOT]) * RR_DIV_VBAT;
    in->vbat_v = adc_v(adc1_buf[A1_VBAT]) * RR_DIV_VBAT;
    in->v5_v = adc_v(adc1_buf[A1_V5]) * RR_DIV_V5;
    in->i_mot_a[0] = adc_v(adc1_buf[A1_IPROPI_L]) / RR_IPROPI_V_PER_A;
    in->i_mot_a[1] = adc_v(adc2_buf[0]) / RR_IPROPI_V_PER_A;
    in->ntc_c[0] = ntc_c(adc1_buf[A1_NTC_BAY]);
    in->ntc_c[1] = ntc_c(adc1_buf[A1_NTC_PACK]);
    in->ntc_c[2] = ntc_c(adc2_buf[1]);
    /* encoders: forward rolling counts up on both sides (the left motor is mounted mirrored) */
    in->enc[0] = (uint16_t)(0u - (uint16_t)TIM4->CNT);
    in->enc[1] = (uint16_t)TIM3->CNT;
    /* IMU: gyro +-500 deg/s (65.536 LSB per deg/s), accel +-3 g (10920 LSB per g). Sensor axes are
     * assumed aligned with the body frame; the mounting rotation is a board constant to confirm. */
    in->imu_ok = false;
    if (imu_ok) {
        memset(tx, 0, sizeof tx);
        tx[0] = 0x80u | 0x02u;
        bool g = spi_xfer(P(IMU_CS_GYR_N), tx, rx, 7);
        int16_t gr[3] = {(int16_t)(rx[1] | (rx[2] << 8)), (int16_t)(rx[3] | (rx[4] << 8)), (int16_t)(rx[5] | (rx[6] << 8))};
        tx[0] = 0x80u | 0x12u;
        bool a = spi_xfer(P(IMU_CS_ACC_N), tx, rx, 8);
        int16_t ar[3] = {(int16_t)(rx[2] | (rx[3] << 8)), (int16_t)(rx[4] | (rx[5] << 8)), (int16_t)(rx[6] | (rx[7] << 8))};
        for (int i = 0; i < 3; i++) {
            in->gyro[i] = (float)gr[i] * (0.0174532925f / 65.536f);
            in->accel[i] = (float)ar[i] * (9.80665f / 10920.0f);
        }
        in->imu_ok = g && a;
    }
}

static void pwm_set(uint32_t ch1, uint32_t ch2, float duty, bool awake)
{
    uint32_t arr = __HAL_TIM_GET_AUTORELOAD(&htim_pwm);
    uint32_t a = 0, b = 0;
    if (awake) { /* slow decay (UNVERIFIED DRV8874 IN/IN truth table): the passive phase is "both inputs high" = brake */
        float m = fabsf(duty) > 1.0f ? 1.0f : fabsf(duty);
        uint32_t low = (uint32_t)((float)arr * (1.0f - m));
        a = duty >= 0.0f ? arr : low;
        b = duty >= 0.0f ? low : arr;
    }
    __HAL_TIM_SET_COMPARE(&htim_pwm, ch1, a);
    __HAL_TIM_SET_COMPARE(&htim_pwm, ch2, b);
}

static void h_write(void *ctx, const rrch_out_t *o)
{
    (void)ctx;
    pwm_set(TIM_CHANNEL_1, TIM_CHANNEL_2, o->duty[0], o->bridge_awake);
    pwm_set(TIM_CHANNEL_3, TIM_CHANNEL_4, o->duty[1], o->bridge_awake);
    HAL_GPIO_WritePin(P(DRV_NSLEEP), o->bridge_awake ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(P(ARM_PERMIT), o->arm_permit ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(P(HEAD_HTR_EN), o->head_htr_en ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(P(CHS_HTR_EN), o->chs_htr_on ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(P(BUZZER), o->buzzer ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(P(BOOT0_LED_STAT), (g_core.ms % 1000u) < (g_core.mode == RRCH_MODE_FAULT ? 900u : 100u) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    /* slow outputs: the background loop writes the expander when this word changes */
    uint16_t w = (uint16_t)(iox_b_want & ((1u << IOX_B_BIT_V12_LIDAR_EN) | (1u << IOX_B_BIT_V5_CM5_OFF_REQ) | (1u << IOX_B_BIT_TOF_XSHUT_CLIFF) |
                                         (1u << IOX_B_BIT_TOF_XSHUT_LOOK) | (1u << IOX_B_BIT_TOF_XSHUT_REAR) | (1u << IOX_B_BIT_TOF_MUX_NRST)));
    static const uint8_t led_bit[RRCH_LED_N] = {IOX_B_BIT_LED_READY, IOX_B_BIT_LED_MOVING, IOX_B_BIT_LED_HOLD, IOX_B_BIT_LED_FAULT, IOX_B_BIT_LED_CHARGE};
    for (int i = 0; i < RRCH_LED_N; i++) {
        if (o->leds & (1u << i)) {
            w |= (uint16_t)(1u << led_bit[i]);
        }
    }
    w |= o->lamp_rearm ? (uint16_t)(1u << IOX_B_BIT_LAMP_REARM) : 0u;
    w |= o->lamp_pause ? (uint16_t)(1u << IOX_B_BIT_LAMP_PAUSE) : 0u;
    w |= o->head_pwr_en ? (uint16_t)(1u << IOX_B_BIT_HEAD_PWR_EN) : 0u;
    iox_b_want = w;
}

/* WDI: 5 ms high pulse every 10 ms (core: supervisor raises, control tick lowers): one counted edge per
 * 10 ms whichever edge the TPS3430 counts (review m2). The MCU's own IWDG is refreshed with it (M4). */
static void h_strobe(void *ctx)
{
    (void)ctx;
    HAL_GPIO_WritePin(P(WDG_STROBE), GPIO_PIN_SET);
    IWDG->KR = 0xAAAAu;
}

static void h_wdg_low(void *ctx)
{
    (void)ctx;
    HAL_GPIO_WritePin(P(WDG_STROBE), GPIO_PIN_RESET);
}

/* Independent watchdog (review M4, safety_chain.md row 37): LSI ~32 kHz / 64 / 125 -> about 250 ms, longer
 * than the external window (23.4-31.6 ms) so the TPS3430 normally acts first; it is the reset path when
 * JP1 is open (CCR-E11). Frozen while a debugger halts the core. Register values UNVERIFIED on a board. */
static void iwdg_start(void)
{
    DBGMCU->APB1FZR1 |= DBGMCU_APB1FZR1_DBG_IWDG_STOP;
    IWDG->KR = 0xCCCCu;
    IWDG->KR = 0x5555u;
    IWDG->PR = 4u;      /* /64 */
    IWDG->RLR = 125u;
    while (IWDG->SR != 0u) {
    }
    IWDG->KR = 0xAAAAu;
}

/* review M2/M3: every chain-tap pin must be an input without pull (PD2: TIM8_BKIN AF), and both IOX_A
 * ports must be inputs (IODIR = 0xFF: GPA5/GPA7 sit on the U21/U22 gate nodes). Read back periodically. */
static bool pin_is(GPIO_TypeDef *port, uint16_t pin, uint32_t mode)
{
    uint32_t n = 0;
    while (((uint32_t)pin >> n) > 1u) {
        n++;
    }
    return ((port->MODER >> (2u * n)) & 3u) == mode && ((port->PUPDR >> (2u * n)) & 3u) == 0u;
}

static bool io_cfg_check(void)
{
    bool ok = pin_is(P(ESTOP_A_RB), 0u) && pin_is(P(ESTOP_B_RB), 0u) && pin_is(P(WDG_OK_RB), 0u) && pin_is(P(BRAKE_L_RB), 0u) &&
              pin_is(P(BRAKE_R_RB), 0u) && pin_is(P(J2_PRES_RB), 0u) && pin_is(P(HW_LATCH_RB), 2u);
    uint8_t tx[4] = {0x41, 0x00, 0, 0}, rx[4] = {0}; /* UNVERIFIED MCP23S17: read IODIRA, IODIRB (sequential) */
    ok = ok && spi_xfer(P(IOX_A_CS_N), tx, rx, 4) && rx[2] == 0xFFu && rx[3] == 0xFFu;
    return ok;
}

static size_t h_link_read(void *ctx, uint8_t *buf, size_t cap)
{
    (void)ctx;
    return usb_cdc_read(buf, cap);
}
static bool h_link_write(void *ctx, const uint8_t *buf, size_t len)
{
    (void)ctx;
    return usb_cdc_write(buf, len);
}
static bool h_link_up(void *ctx)
{
    (void)ctx;
    return usb_cdc_up();
}
static void *h_retained(void *ctx, size_t size)
{
    (void)ctx;
    return size <= sizeof retained ? &retained : NULL;
}
static bool h_entropy(void *ctx, uint8_t *buf, size_t len)
{
    (void)ctx;
    for (size_t i = 0; i < len; i += 4u) {
        uint32_t r;
        if (HAL_RNG_GenerateRandomNumber(&hrng, &r) != HAL_OK) {
            return false;
        }
        memcpy(buf + i, &r, (len - i) < 4u ? (len - i) : 4u);
    }
    return true;
}
static rrch_reset_cause_t h_reset_cause(void *ctx)
{
    (void)ctx;
    return reset_cause;
}
static void h_lock(void *ctx)
{
    (void)ctx;
    if (lock_depth++ == 0) {
        HAL_NVIC_DisableIRQ(TIM6_DAC_IRQn);
        HAL_NVIC_DisableIRQ(TIM7_DAC_IRQn);
    }
}
static void h_unlock(void *ctx)
{
    (void)ctx;
    if (--lock_depth == 0) {
        HAL_NVIC_EnableIRQ(TIM6_DAC_IRQn);
        HAL_NVIC_EnableIRQ(TIM7_DAC_IRQn);
    }
}

void bsp_fill_hal(rrch_hal_t *hal)
{
    rrch_hal_t h = {NULL, h_now, h_read, h_write, h_strobe, h_link_read, h_link_write, h_link_up, nv_read, nv_write, h_retained, h_entropy, h_reset_cause, h_lock, h_unlock, h_wdg_low};
    *hal = h;
}

/* ------------------------------------------------------------------ debug UART */
void bsp_dbg_puts(const char *s)
{
    (void)HAL_UART_Transmit(&huart_dbg, (uint8_t *)(uintptr_t)s, (uint16_t)strlen(s), 20);
}

/* ------------------------------------------------------------------ init + background */
void bsp_init(void)
{
    /* reset cause before anything clears the flags. G4 reports POR and BOR with the same flag. */
    uint32_t csr = RCC->CSR;
    if (csr & (RCC_CSR_IWDGRSTF | RCC_CSR_WWDGRSTF)) {
        reset_cause = RRCH_RST_WATCHDOG;
    } else if (csr & RCC_CSR_SFTRSTF) {
        reset_cause = RRCH_RST_SOFTWARE;
    } else if (csr & RCC_CSR_BORRSTF) {
        reset_cause = RRCH_RST_POWER_ON;
    } else if (csr & RCC_CSR_PINRSTF) {
        reset_cause = RRCH_RST_PIN; /* also what the external watchdog produces through NRST */
    }
    __HAL_RCC_CLEAR_RESET_FLAGS();
    clock_init();
    gpio_init();
    __HAL_RCC_USART3_CLK_ENABLE();
    huart_dbg.Instance = USART3;
    huart_dbg.Init.BaudRate = 115200;
    huart_dbg.Init.WordLength = UART_WORDLENGTH_8B;
    huart_dbg.Init.StopBits = UART_STOPBITS_1;
    huart_dbg.Init.Parity = UART_PARITY_NONE;
    huart_dbg.Init.Mode = UART_MODE_TX_RX;
    (void)HAL_UART_Init(&huart_dbg);
    __HAL_RCC_RNG_CLK_ENABLE();
    hrng.Instance = RNG;
    (void)HAL_RNG_Init(&hrng);
    wdg_boot_toggle();
    timers_init();
    adc_init();
    delay_kicking(5);
    spi_dev_init();
    delay_kicking(5);
    i2c_init();
    delay_kicking(5);
    iwdg_start();
}

void bsp_background(rrch_t *core)
{
    static uint32_t t_slow, t_tof;
    static int tof_idx;
    static const uint8_t mux_map[RRCH_TOF_N][2] = TOF_MUX_MAP;
    uint32_t now = HAL_GetTick();

    /* annunciators and sticky enables */
    uint16_t want = iox_b_want;
    if (want != iox_b_cur) {
        uint8_t out[3] = {0x02, (uint8_t)want, (uint8_t)(want >> 8)};
        if (i2c_wr(&hi2c_sys, IOX_B_I2C_ADDR, out, 3)) {
            iox_b_cur = want;
        }
    }
    /* ranging sensors, one per pass, 2 ms apart (11 sensors -> 22 ms round) */
    if (tof_ok && now - t_tof >= 2u) {
        t_tof = now;
        uint8_t sel = (uint8_t)(1u << mux_map[tof_idx][1]), off = 0;
        uint8_t this_mux = mux_map[tof_idx][0] ? I2C_ADDR_TOF_MUX1 : I2C_ADDR_TOF_MUX0;
        uint8_t other_mux = mux_map[tof_idx][0] ? I2C_ADDR_TOF_MUX0 : I2C_ADDR_TOF_MUX1;
        int32_t mm;
        rrch_tof_status_t st;
        if (i2c_wr(&hi2c_tof, other_mux, &off, 1) && i2c_wr(&hi2c_tof, this_mux, &sel, 1) && tof_read(&hi2c_tof, tof_idx, &mm, &st)) {
            uint64_t t = bsp_now_us();
            core->hal.irq_lock(NULL);
            rrch_tof_update(core, tof_idx, mm, st, t);
            core->hal.irq_unlock(NULL);
        }
        tof_idx = (tof_idx + 1) % RRCH_TOF_N;
    }
    /* 100 Hz: IOX_B input port 1 for P17 = CHAIN_END_RB (UNVERIFIED register 0x01, TCA9535 class) */
    static uint32_t t_iox_b;
    if (now - t_iox_b >= 10u) {
        t_iox_b = now;
        uint8_t hi = 0;
        static uint32_t n_fail;
        bool ok = i2c_rd_reg(&hi2c_sys, IOX_B_I2C_ADDR, 0x01, &hi, 1);
        n_fail = ok ? 0u : n_fail + 1u;
        if (n_fail == 3u) { /* review m7: re-initialise the bus after three failed reads (no SCL toggling, UNVERIFIED) */
            (void)HAL_I2C_DeInit(&hi2c_sys);
            (void)HAL_I2C_Init(&hi2c_sys);
        }
        uint64_t t = bsp_now_us();
        core->hal.irq_lock(NULL);
        rrch_iox_b_update(core, ok, ok && ((hi >> (IOX_B_BIT_CHAIN_END_RB - 8u)) & 1u) != 0u, t);
        core->hal.irq_unlock(NULL);
    }
    /* 10 Hz: eFuse faults, bus health, INA228 pack and INA3221 branch telemetry. The charger driver is
     * disabled (LTC4162 register map UNVERIFIED, IB-06): charger_ok false -> CHARGER_COMM. */
    if (now - t_slow >= 100u) {
        t_slow = now;
        rrch_power_t p;
        uint8_t in = 0xFF;
        memset(&p, 0, sizeof p);
        p.soc_pct = -1.0f;
        p.chg_temp_c = p.i_head_a = p.i_head_htr_a = p.i_chs_htr_a = p.vbat_pmon_v = p.ibat_a = NAN;
        p.charge_state = RRCH_CHG_UNKNOWN;
        p.charger_ok = false;
        if (!pmon_ok) {
            pmon_init();
        }
        uint8_t b3[3];
        if (pmon_ok && i2c_rd_reg(&hi2c_sys, I2C_ADDR_PMON, RR_INA228_REG_VBUS, b3, 3)) {
            p.vbat_pmon_v = rr_ina228_vbus_v(b3);
            if (i2c_rd_reg(&hi2c_sys, I2C_ADDR_PMON, RR_INA228_REG_CURRENT, b3, 3)) {
                p.ibat_a = rr_ina228_current_a(b3, RR_PMON_CURRENT_LSB);
                p.pmon_ok = true;
            }
        }
        if (!branch_ok) {
            branch_init();
        }
        float *dst[3] = {&p.i_head_a, &p.i_head_htr_a, &p.i_chs_htr_a};
        for (unsigned ch = 0; branch_ok && ch < 3u; ch++) {
            uint8_t b2[2];
            if (i2c_rd16(I2C_ADDR_BRANCH, RR_INA3221_REG_SHUNT(ch), b2)) {
                *dst[ch] = (float)(rr_ina3221_shunt_v(b2) / rr_branch_shunt_ohm[ch]);
            }
        }
        if (i2c_rd_reg(&hi2c_sys, IOX_C_I2C_ADDR, 0x00, &in, 1)) { /* UNVERIFIED: TCA9534 input register 0 */
            p.efuse_fault = (uint8_t)(~in & 0x1Fu);
        }
        p.tof_bus_ok = tof_ok && HAL_I2C_IsDeviceReady(&hi2c_tof, (uint16_t)(I2C_ADDR_TOF_MUX0 << 1), 1, 2) == HAL_OK;
        core->hal.irq_lock(NULL);
        rrch_power_update(core, &p);
        core->hal.irq_unlock(NULL);
    }
}
