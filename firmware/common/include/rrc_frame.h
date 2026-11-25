/* Record framing of head ICD section 4 (also used by the chassis link):
 *
 *   <UTF-8 JSON object bytes> TAB <8 uppercase hex digits: CRC-32 of the JSON bytes> LF
 *
 * The JSON bytes contain no literal TAB, CR or LF. The maximum record length INCLUDING the
 * 10-byte trailer is a link parameter (head: 8192, chassis: 2048).
 *
 * Receiver discard rules implemented here (the JSON content itself is checked by rrc_json):
 *   - a record longer than max_record is discarded through the next LF;
 *   - a line without exactly one TAB, with a CR, with a CRC field that is not 8 characters
 *     of [0-9A-F], or with a CRC mismatch is discarded;
 *   - rrc_frame_rx_reset() drops an unfinished record (idle-line timeout, link reset).
 * No dynamic allocation; the caller supplies the buffer.
 */
#ifndef RRC_FRAME_H
#define RRC_FRAME_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define RRC_FRAME_TRAILER_LEN 10u /* TAB + 8 hex + LF */
#define RRC_HEAD_MAX_RECORD 8192u
#define RRC_CHASSIS_MAX_RECORD 2048u

typedef enum {
    RRC_RX_NONE = 0,     /* byte consumed, no complete record yet */
    RRC_RX_RECORD = 1,   /* a record with a valid trailer is in the buffer */
    RRC_RX_DISCARDED = 2 /* a line ended and was discarded (see last_error) */
} rrc_rx_result_t;

typedef enum {
    RRC_FRAME_OK = 0,
    RRC_FRAME_ERR_OVERSIZE,
    RRC_FRAME_ERR_DELIMITER, /* TAB count != 1, CR present, or line shorter than the trailer */
    RRC_FRAME_ERR_CRC_FORMAT,
    RRC_FRAME_ERR_CRC_MISMATCH
} rrc_frame_err_t;

typedef struct {
    uint8_t *buf;      /* caller storage, at least max_record bytes */
    size_t max_record; /* maximum line length including TAB, CRC and LF */
    size_t len;        /* bytes of the current line collected so far */
    bool discarding;   /* oversize line: swallow bytes through the next LF */
    rrc_frame_err_t last_error;
    uint32_t n_records;
    uint32_t n_discarded;
} rrc_frame_rx_t;

/* buf must hold max_record bytes. */
void rrc_frame_rx_init(rrc_frame_rx_t *rx, uint8_t *buf, size_t max_record);

/* Drop any partially received record (receive timeout releases the half-duplex receiver). */
void rrc_frame_rx_reset(rrc_frame_rx_t *rx);

/* True while a record is partially received (or an oversize line is being swallowed). */
bool rrc_frame_rx_busy(const rrc_frame_rx_t *rx);

/* Feed one received byte. On RRC_RX_RECORD, rx->buf[0 .. *json_len) holds the JSON bytes and
 * *crc holds their CRC-32; both stay valid until the next call that modifies rx. */
rrc_rx_result_t rrc_frame_rx_push(rrc_frame_rx_t *rx, uint8_t byte, size_t *json_len, uint32_t *crc);

/* Validate one complete line (ending in LF). Returns RRC_FRAME_OK and the JSON length. */
rrc_frame_err_t rrc_frame_check(const uint8_t *line, size_t len, size_t max_record, size_t *json_len,
                                uint32_t *crc);

/* Append TAB + CRC + LF to json_len bytes already in buf. Returns the total line length, or 0
 * if it would exceed cap or max_record, or if the JSON bytes contain TAB, CR or LF. */
size_t rrc_frame_finish(uint8_t *buf, size_t json_len, size_t cap, size_t max_record);

#ifdef __cplusplus
}
#endif
#endif
