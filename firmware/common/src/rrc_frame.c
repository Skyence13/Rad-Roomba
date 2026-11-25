#include "rrc_frame.h"

#include "rrc_crc32.h"

static const char k_hex[] = "0123456789ABCDEF";

void rrc_frame_rx_init(rrc_frame_rx_t *rx, uint8_t *buf, size_t max_record)
{
    rx->buf = buf;
    rx->max_record = max_record;
    rx->len = 0u;
    rx->discarding = false;
    rx->last_error = RRC_FRAME_OK;
    rx->n_records = 0u;
    rx->n_discarded = 0u;
}

void rrc_frame_rx_reset(rrc_frame_rx_t *rx)
{
    rx->len = 0u;
    rx->discarding = false;
}

bool rrc_frame_rx_busy(const rrc_frame_rx_t *rx)
{
    return rx->discarding || (rx->len != 0u);
}

static bool hex_value(uint8_t c, uint32_t *v)
{
    if ((c >= (uint8_t)'0') && (c <= (uint8_t)'9')) {
        *v = (uint32_t)c - (uint32_t)'0';
        return true;
    }
    if ((c >= (uint8_t)'A') && (c <= (uint8_t)'F')) {
        *v = (uint32_t)c - (uint32_t)'A' + 10u;
        return true;
    }
    return false; /* lowercase is not accepted */
}

rrc_frame_err_t rrc_frame_check(const uint8_t *line, size_t len, size_t max_record, size_t *json_len,
                                uint32_t *crc)
{
    if (len > max_record) {
        return RRC_FRAME_ERR_OVERSIZE;
    }
    if ((len < RRC_FRAME_TRAILER_LEN) || (line[len - 1u] != (uint8_t)'\n')) {
        return RRC_FRAME_ERR_DELIMITER;
    }
    const size_t n = len - RRC_FRAME_TRAILER_LEN;
    /* Exactly one TAB in the line, and it must be the one that starts the trailer. */
    size_t tabs = 0u;
    for (size_t i = 0u; i < (len - 1u); i++) {
        if (line[i] == (uint8_t)'\t') {
            tabs++;
        }
        if ((i < n) && ((line[i] == (uint8_t)'\r') || (line[i] == (uint8_t)'\n'))) {
            return RRC_FRAME_ERR_DELIMITER;
        }
    }
    if ((tabs != 1u) || (line[n] != (uint8_t)'\t')) {
        /* Distinguish "trailer present but CRC field malformed" from a delimiter error. */
        if ((tabs == 1u) && (line[n] != (uint8_t)'\t')) {
            return RRC_FRAME_ERR_CRC_FORMAT;
        }
        return RRC_FRAME_ERR_DELIMITER;
    }
    uint32_t want = 0u;
    for (size_t i = 0u; i < 8u; i++) {
        uint32_t v = 0u;
        if (!hex_value(line[n + 1u + i], &v)) {
            return RRC_FRAME_ERR_CRC_FORMAT;
        }
        want = (want << 4) | v;
    }
    const uint32_t got = rrc_crc32(line, n);
    if (got != want) {
        return RRC_FRAME_ERR_CRC_MISMATCH;
    }
    if (json_len != NULL) {
        *json_len = n;
    }
    if (crc != NULL) {
        *crc = got;
    }
    return RRC_FRAME_OK;
}

rrc_rx_result_t rrc_frame_rx_push(rrc_frame_rx_t *rx, uint8_t byte, size_t *json_len, uint32_t *crc)
{
    if (rx->discarding) {
        if (byte == (uint8_t)'\n') {
            rx->discarding = false;
            rx->len = 0u;
            rx->last_error = RRC_FRAME_ERR_OVERSIZE;
            rx->n_discarded++;
            return RRC_RX_DISCARDED;
        }
        return RRC_RX_NONE;
    }
    if (rx->len >= rx->max_record) {
        /* The line already has max_record bytes and this byte would make it longer. */
        rx->len = 0u;
        if (byte == (uint8_t)'\n') {
            rx->last_error = RRC_FRAME_ERR_OVERSIZE;
            rx->n_discarded++;
            return RRC_RX_DISCARDED;
        }
        rx->discarding = true;
        return RRC_RX_NONE;
    }
    rx->buf[rx->len] = byte;
    rx->len++;
    if (byte != (uint8_t)'\n') {
        return RRC_RX_NONE;
    }
    const size_t line_len = rx->len;
    rx->len = 0u;
    rx->last_error = rrc_frame_check(rx->buf, line_len, rx->max_record, json_len, crc);
    if (rx->last_error == RRC_FRAME_OK) {
        rx->n_records++;
        return RRC_RX_RECORD;
    }
    rx->n_discarded++;
    return RRC_RX_DISCARDED;
}

size_t rrc_frame_finish(uint8_t *buf, size_t json_len, size_t cap, size_t max_record)
{
    const size_t total = json_len + RRC_FRAME_TRAILER_LEN;
    if ((total > cap) || (total > max_record) || (total < json_len)) {
        return 0u;
    }
    for (size_t i = 0u; i < json_len; i++) {
        if ((buf[i] == (uint8_t)'\t') || (buf[i] == (uint8_t)'\r') || (buf[i] == (uint8_t)'\n')) {
            return 0u;
        }
    }
    const uint32_t crc = rrc_crc32(buf, json_len);
    buf[json_len] = (uint8_t)'\t';
    for (size_t i = 0u; i < 8u; i++) {
        const uint32_t nib = (crc >> (28u - (4u * (uint32_t)i))) & 0x0Fu;
        buf[json_len + 1u + i] = (uint8_t)k_hex[nib];
    }
    buf[json_len + 9u] = (uint8_t)'\n';
    return total;
}
