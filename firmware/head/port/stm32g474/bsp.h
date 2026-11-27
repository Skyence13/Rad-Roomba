/* Board support for RR-HEAD-ACQ (STM32G474VET6, LQFP100; DEC-037: no FPGA). Thin register-level drivers; no logic that
 * belongs in the core. NOT TESTED ON HARDWARE: compiled and linked only. */
#ifndef RRH_BSP_H
#define RRH_BSP_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "stm32g4xx.h"

#include "rrh_board.h"
#include "rrh_hal.h"
#include "rrh_pins.h"

#define BSP_SYSCLK_HZ 144000000u
#define BSP_TICK_HZ BSP_SYSCLK_HZ    /* TIM2 / TIM5 capture timers run at the system clock */
#define BSP_TICKS_PER_US (BSP_TICK_HZ / 1000000u)
#define BSP_VREF_MV 3000u           /* external ADC reference (pinmap.yaml VREF+) */
#define BSP_RS485_TURNAROUND_US 200u /* minimum silence between the request's LF and our first bit */
#define BSP_TIME_REPLY_DELAY_US 1000u /* TIME: reply starts exactly this long after the request ended */

/* ---- bsp.c ---- */
void bsp_init(void);
bool bsp_clock_from_tcxo(void); /* false: running on the HSI16 fallback */
uint64_t bsp_now_ticks(void); /* 64-bit extension of TIM2, 144 ticks per microsecond */
uint64_t bsp_now_us(void);
void bsp_tick_isr_update(void); /* called by the 100 kHz service interrupt */
void bsp_delay_us(uint32_t us);
rrh_reset_cause_t bsp_reset_cause(void);
void bsp_watchdog_kick(void);
bool bsp_rng_words(uint32_t *out, size_t n);
void bsp_uid(uint8_t out[12]);
void bsp_led(bool status_on, bool fault_on);
void bsp_dbg_puts(const char *s);

/* GPIO helpers (port, pin from rrh_pins.h) */
static inline void bsp_gpio_write(GPIO_TypeDef *port, uint32_t pin, bool level)
{
    port->BSRR = level ? (1uL << pin) : (1uL << (pin + 16u));
}
static inline bool bsp_gpio_read(const GPIO_TypeDef *port, uint32_t pin)
{
    return ((port->IDR >> pin) & 1u) != 0u;
}

/* RS-485 link */
bool bsp_rs485_pop(uint8_t *byte, uint64_t *rx_us);
void bsp_rs485_send(const uint8_t *data, size_t len, uint64_t at_us);
void bsp_rs485_tx_service(uint64_t now_ticks); /* from the service interrupt: start a scheduled reply */

/* SPI1: DACs (mode 1) */
uint8_t bsp_spi_dac_xfer(uint8_t b);
/* Test pulser (PC6 = TIM8_CH1, charge injection) and LED pulser (PC12 = TIM8_CH3N), both 1 kHz from TIM8 (48 MHz).
 * Which chain is pulsed is selected with PULSER_A[2:0] (PF2, PF9, PF10, GPIO). */
void bsp_pulser_config(bool pulser_enable, uint8_t width_us, bool led_enable);
void bsp_pulser_select(uint8_t chain); /* 0..7 = F0..F3, R0..R3 */

/* DAC60508 x4 */
bool bsp_dac_init(void);
void bsp_dac_write(uint8_t device, uint8_t channel, uint16_t code12);

/* I2C3: TMP117 x2, EUI EEPROM, optional TCA9534 expander */
bool bsp_i2c_xfer(uint8_t addr, const uint8_t *w, size_t wn, uint8_t *r, size_t rn);
bool bsp_expander_read(uint8_t *inputs); /* false = no answer; configures the device on first contact */
bool bsp_eui64(uint8_t out[8]);
int32_t bsp_tmp117_mc(uint8_t index); /* RRH_TEMP_INVALID if absent */

/* ADC1 housekeeping scan (non-blocking, one conversion per call) */
typedef enum {
    BSP_ADC_BIAS_V = 0, BSP_ADC_BIAS_I, BSP_ADC_NTC0, BSP_ADC_NTC1, BSP_ADC_NTC2, BSP_ADC_NTC3,
    BSP_ADC_NTC_HTR, BSP_ADC_NTC_BOARD, BSP_ADC_VIN, BSP_ADC_HTR_SENSE, BSP_ADC_COUNT
} bsp_adc_ch_t;
void bsp_adc_step(void);
uint32_t bsp_adc_mv(bsp_adc_ch_t ch);
uint16_t bsp_adc_code(bsp_adc_ch_t ch);
bool bsp_adc_valid(void); /* every channel converted at least once */
/* Per-chain anode current monitor IMON_CH (PE15 = ADC4_IN2) behind the TMUX1108 addressed by MON_MUX_A[2:0].
 * bsp_imon_step() is a non-blocking background scan (select, settle, convert), called from the main loop. */
void bsp_imon_step(void);
void bsp_imon_get(rrh_imon_t *out);

/* Flash-backed non-volatile slot */
bool bsp_nv_load(uint8_t *buf, size_t cap, size_t *len);
bool bsp_nv_save(const uint8_t *buf, size_t len);

/* ---- evt_port.c: event capture on TIM2/TIM5 + 100 kHz service interrupt (TIM6) ---- */
void evt_port_init(void);
bool evt_port_start(uint32_t span_us, rrh_epoch_t *epoch);
bool evt_port_stop(void);
void evt_port_abort(void);
bool evt_port_running(void);
bool evt_port_poll(rrh_gate_record_t *rec);
void evt_port_chain_enable(uint8_t mask);
void evt_port_heater_request(bool on);
void evt_port_set_alpha_hold_us(uint16_t us);
bool evt_port_selftest(void); /* LATCH_TEST line: every latch sets and clears */

#endif
