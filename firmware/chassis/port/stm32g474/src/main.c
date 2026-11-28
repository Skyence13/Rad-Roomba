/* RR-CHS-MAIN motion MCU firmware entry point. NOT a certified safety controller.
 * Contexts: TIM6 interrupt = 1 kHz control tick; TIM7 interrupt = 100 Hz supervision (the only
 * caller of the watchdog strobe); main loop = protocol server and slow buses. */
#include <string.h>

#include "bsp.h"

rrch_t g_core;

static void put_u(char **p, uint32_t v)
{
    char tmp[11];
    int n = 0;
    do {
        tmp[n++] = (char)('0' + v % 10u);
        v /= 10u;
    } while (v);
    while (n) {
        *(*p)++ = tmp[--n];
    }
}
static void put_s(char **p, const char *s)
{
    while (*s) {
        *(*p)++ = *s++;
    }
}
static void put_x(char **p, uint32_t v)
{
    static const char H[] = "0123456789ABCDEF";
    for (int i = 7; i >= 0; i--) {
        *(*p)++ = H[(v >> (4 * i)) & 15u];
    }
}

/* One line per second and one per mode change on the debug UART (see README "First power-up"). */
static void debug_report(void)
{
    static uint32_t last_s = 0xFFFFFFFFu;
    static rrch_mode_t last_mode = RRCH_MODE_N;
    uint32_t s = g_core.ms / 1000u;
    if (s == last_s && g_core.mode == last_mode) {
        return;
    }
    last_s = s;
    last_mode = g_core.mode;
    char line[160], *p = line;
    put_s(&p, "t=");
    put_u(&p, s);
    put_s(&p, " mode=");
    put_s(&p, rrch_mode_names[g_core.mode]);
    put_s(&p, " latch=");
    put_u(&p, g_core.chain.latch);
    put_s(&p, " permit=");
    put_u(&p, g_core.out.arm_permit);
    put_s(&p, " hw=");
    put_x(&p, g_core.chain.hw_latched);
    put_s(&p, " live=");
    put_x(&p, g_core.chain.hw_live);
    put_s(&p, " sw=");
    put_x(&p, g_core.sw_latched);
    put_s(&p, " flt=");
    put_x(&p, (uint32_t)(g_core.faults >> 32));
    put_x(&p, (uint32_t)g_core.faults);
    put_s(&p, " di=");
    put_x(&p, g_core.chain.state);
    put_s(&p, " vbat_mV=");
    put_u(&p, (uint32_t)(g_core.in.vbat_v * 1000.0f));
    put_s(&p, " vmot_mV=");
    put_u(&p, (uint32_t)(g_core.in.vmot_v * 1000.0f));
    put_s(&p, " pres_ohm=");
    put_u(&p, g_core.chain.pres_ohm);
    put_s(&p, " usb=");
    put_u(&p, usb_cdc_up());
    put_s(&p, "\r\n");
    *p = 0;
    bsp_dbg_puts(line);
}

int main(void)
{
    static const char *const rst[6] = {"POWER_ON", "BROWNOUT", "PIN", "WATCHDOG", "SOFTWARE", "UNKNOWN"};
    rrch_hal_t hal;
    HAL_Init();
    bsp_init();
    bsp_fill_hal(&hal);
    rrch_init(&g_core, &hal);
    bsp_dbg_puts("\r\n" RRCH_FW_VERSION RRCH_FW_SUFFIX " " RRCH_PROTO " - not a certified safety controller\r\nreset=");
    bsp_dbg_puts(rst[g_core.reset_cause]);
    bsp_dbg_puts(bsp_clock_fallback ? " clock=HSI-FALLBACK(no crystal)" : " clock=HSE");
    bsp_dbg_puts(g_core.cfg.from_flash ? " config=FLASH boot_id=" : " config=DEFAULTS boot_id=");
    bsp_dbg_puts(g_core.boot_id);
    bsp_dbg_puts("\r\n");
    usb_cdc_init();
    bsp_start_ticks();
    for (;;) {
        rrch_background(&g_core);
        bsp_background(&g_core);
        debug_report();
    }
}

/* Any CPU fault: stop here with interrupts off. The supervision tick no longer runs, the external
 * watchdog opens the chain and resets the MCU. */
void HardFault_Handler(void)
{
    __disable_irq();
    for (;;) {
    }
}
