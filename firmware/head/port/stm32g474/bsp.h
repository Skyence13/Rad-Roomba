/* Board support for RR-HEAD-ACQ (STM32G474RET6). Thin register-level drivers; no logic that
 * belongs in the core. NOT TESTED ON HARDWARE: compiled and linked only. */
#ifndef RRH_BSP_H
#define RRH_BSP_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "stm32g4xx.h"

#include "rrh_hal.h"
#include "rrh_pins.h"

#define BSP_SYSCLK_HZ 48000000u
#define BSP_VREF_MV 3000u           /* external ADC reference (pinmap.yaml VREF+) */
#define BSP_RS485_TURNAROUND_US 200u /* minimum silence between the request's LF and our first bit */
#define BSP_TIME_REPLY_DELAY_US 1000u /* TIME: reply starts exactly this long after the request ended */

/* ---- bsp.c ---- */
void bsp_init(void);
bool bsp_clock_from_tcxo(void); /* false: running on the HSI16 fallback */
uint64_t bsp_now_us(void);
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
uint64_t bsp_rs485_last_lf_us(void);

/* SPI: bus 0 = DACs (SPI1, mode 1), bus 1 = FPGA (SPI3) */
void bsp_spi_fpga_mode(bool config_phase);
uint8_t bsp_spi_dac_xfer(uint8_t b);
uint8_t bsp_spi_fpga_xfer(uint8_t b);

/* DAC60508 x4 */
bool bsp_dac_init(void);
void bsp_dac_write(uint8_t device, uint8_t channel, uint16_t code12);

/* I2C3: TMP117 x2, EUI EEPROM */
bool bsp_i2c_xfer(uint8_t addr, const uint8_t *w, size_t wn, uint8_t *r, size_t rn);
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
int32_t bsp_ntc_mc(uint16_t code);

/* Flash-backed non-volatile slot */
bool bsp_nv_load(uint8_t *buf, size_t cap, size_t *len);
bool bsp_nv_save(const uint8_t *buf, size_t len);

/* ---- fpga.c ---- */
bool fpga_configure(void);            /* load the embedded bitstream, check ID/version */
bool fpga_ready(void);
const char *fpga_bitstream_id(void);
bool fpga_acq_start(uint32_t span_us, rrh_epoch_t *epoch);
bool fpga_acq_stop(void);
void fpga_acq_abort(void);
bool fpga_acq_running(void);
bool fpga_acq_poll(rrh_gate_record_t *rec);
bool fpga_frontend(uint8_t chain_enable, bool pulser_enable);
void fpga_heater_request(bool on);

#endif
