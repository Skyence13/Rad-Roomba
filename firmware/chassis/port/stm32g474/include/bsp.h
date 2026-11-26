/* Board support for RR-CHS-MAIN (STM32G474RET6). See pinmap.yaml; board_pins.h is generated. */
#ifndef RR_BSP_H
#define RR_BSP_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "stm32g4xx_hal.h"

#include "board_pins.h"
#include "rrch.h"

/* board constants that depend on the schematic (placeholders until the electronics lead freezes values) */
#define RR_VREF 3.3f
#define RR_DIV_VBAT ((47.0f + 10.0f) / 10.0f)   /* VMOT_SENSE and VBAT_SENSE dividers 47k/10k */
#define RR_DIV_V5 2.0f
#define RR_PRES_PULLUP_OHM 4700.0f              /* HEAD_PRES_ID pull-up to VREF+ */
#define RR_LOOP_PULLUP_OHM 1000.0f              /* PLACEHOLDER: depends on the loop source circuit */
#define RR_IPROPI_V_PER_A 0.45f                 /* UNVERIFIED: DRV8874 IPROPI gain x RIPROPI (1 kOhm) */
#define RR_NTC_R0 10000.0f
#define RR_NTC_BETA 3435.0f
#define RR_NTC_PULLUP 10000.0f
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
