/* RR-HEAD-ACQ head firmware entry point. Everything protocol-related is in ../../core. */
#include <string.h>

#include "bsp.h"
#include "rrh_core.h"

static rrh_core_t g_core;
static rrh_identity_t g_ident;

static void serial_from_bytes(char *out, const char *prefix, const uint8_t *bytes, size_t n)
{
    static const char hex[] = "0123456789ABCDEF";
    size_t o = strlen(prefix);
    memcpy(out, prefix, o);
    for (size_t i = 0u; i < n; i++) {
        out[o] = hex[bytes[i] >> 4];
        out[o + 1u] = hex[bytes[i] & 0x0Fu];
        o += 2u;
    }
    out[o] = '\0';
}

int main(void)
{
    char serial[49];
    uint8_t id[12];

    bsp_init();
    evt_port_init();
    bsp_dbg_puts("\r\n" RRH_FW_VERSION " boot\r\n");

    /* Serial number: factory EUI-64 of the identity EEPROM, else the MCU unique id. */
    if (bsp_eui64(id)) {
        serial_from_bytes(serial, "RRH-", id, 8u);
    } else {
        bsp_uid(id);
        serial_from_bytes(serial, "RRH-UID-", id, 12u);
    }
    rrh_identity_defaults(&g_ident, serial);

    /* One full housekeeping scan before the core takes its first snapshot. */
    while (!bsp_adc_valid()) {
        bsp_adc_step();
    }
    rrh_core_init(&g_core, &g_ident);
    if (!bsp_clock_from_tcxo()) {
        g_core.health |= RRH_H_SOURCE; /* running from the internal oscillator: timing not trustworthy */
    }
    if (!evt_port_selftest()) {
        g_core.health |= RRH_H_SOURCE; /* a latch did not set or did not clear */
    }
    bsp_dbg_puts(g_core.boot_id);
    bsp_dbg_puts("\r\n");

    for (;;) {
        uint8_t byte;
        uint64_t rx_us;
        rrh_reply_t reply;
        bsp_adc_step();
        rrh_core_poll(&g_core); /* also services the watchdog */
        while (bsp_rs485_pop(&byte, &rx_us)) {
            if (rrh_core_rx_byte(&g_core, byte, rx_us, &reply)) {
                bsp_rs485_send(reply.data, reply.len, reply.tx_at_us);
            }
        }
        bsp_led(((bsp_now_us() >> 19) & 1u) != 0u, g_core.health != 0u);
    }
}
