/* Board support for RR-CHS-MAIN (STM32G474RET6). See pinmap.yaml; board_pins.h is generated. */
#ifndef RR_BSP_H
#define RR_BSP_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "stm32g4xx_hal.h"

#include "board_pins.h"
#include "rrch.h"

/* board constants of RR-CHS-MAIN rev A (IB-02; electronics/chassis_main/design/CONTRACT_CHANGE_REQUESTS.md CCR-E03 and
 * the netlist export electronics/chassis_main/out/pinmap.json). Not measured on a board. */
#define RR_VREF 3.000f                          /* VREF+ = REF3030 (U14), +-0.2 % (CCR-E03 a) */
#define RR_DIV_VBAT ((47.0f + 10.0f) / 10.0f)   /* VMOT_SENSE and VBAT_SENSE dividers 47k/10k (R139/R140, R11/R12) */
#define RR_DIV_V5 2.0f                          /* V5_SENSE 10k/10k (R33/R34) */
#define RR_PRES_PULLUP_OHM 4700.0f              /* HEAD_PRES_ID pull-up R77 to VREF+, no series R in the measured path (CCR-E03 c) */
/* J1 loop sense (safety_chain.md 2.2): V = V5_AUX x R71 / (R70 + 2 x 100 + R_loop + R71), R70 = R71 = 1.00 kOhm.
 * V5_AUX is not measured: nominal 5.0 V (UNVERIFIED tolerance; only this analog copy depends on it) */
#define RR_LOOP_V5AUX 5.0f
#define RR_LOOP_RSENSE 1000.0f
#define RR_LOOP_RSERIES 1200.0f                 /* R70 + 2 x 100 Ohm */
#define RR_IPROPI_V_PER_A 1.1205f               /* RIPROPI 2.49 kOhm (R153/R155) x 450 uA/A (CCR-E03 b); 0.8925 A/V */
#define RR_IPROPI_TRIP_A (RR_VREF / RR_IPROPI_V_PER_A) /* 2.68 A: hardware chop = ADC full scale */
#define RR_NTC_R0 10000.0f
#define RR_NTC_BETA 3435.0f
#define RR_NTC_PULLUP 10000.0f                  /* R215 / R217 / NTC_BOARD pull-up to VREF+ */
#define RR_PWM_HZ 20000u
#define RR_WDG_STROBE_PERIOD_MS 10u

extern volatile uint32_t bsp_clock_fallback;    /* 1 = HSE did not start, running from HSI */

void bsp_init(void);                            /* clocks, GPIO, timers, ADC, SPI, I2C, UART */
void bsp_start_ticks(void);                     /* 1 kHz control and 100 Hz supervision interrupts */
void bsp_fill_hal(rrch_hal_t *hal);
void bsp_background(rrch_t *core);              /* slow buses: ToF, expanders, power telemetry */
void bsp_dbg_puts(const char *s);
uint64_t bsp_now_us(void);

/* usb_cdc.c */
void usb_cdc_init(void);
bool usb_cdc_up(void);
size_t usb_cdc_read(uint8_t *buf, size_t cap);
bool usb_cdc_write(const uint8_t *buf, size_t len);

/* tof_vl53l4ed.c - HAL interface of the ranging sensors */
bool tof_init(I2C_HandleTypeDef *bus);          /* false = driver not installed / sensors not found */
/* Reads sensor idx (mux already selected). Returns false if no new sample is available. */
bool tof_read(I2C_HandleTypeDef *bus, int idx, int32_t *range_mm, rrch_tof_status_t *st);

#endif
