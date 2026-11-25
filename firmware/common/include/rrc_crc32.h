/* CRC-32 (IEEE 802.3, reflected, as Python zlib.crc32). Check value of "123456789" is 0xCBF43926. */
#ifndef RRC_CRC32_H
#define RRC_CRC32_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Incremental form: start with crc = 0, feed chunks, the return value is the running CRC. */
uint32_t rrc_crc32_update(uint32_t crc, const uint8_t *data, size_t len);
uint32_t rrc_crc32(const uint8_t *data, size_t len);

#ifdef __cplusplus
}
#endif
#endif
