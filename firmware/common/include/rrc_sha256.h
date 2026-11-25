/* SHA-256 (FIPS 180-4), streaming, no allocation. */
#ifndef RRC_SHA256_H
#define RRC_SHA256_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define RRC_SHA256_LEN 32u
#define RRC_SHA256_HEX_LEN 64u

typedef struct {
    uint32_t state[8];
    uint64_t total; /* bytes hashed so far */
    uint8_t block[64];
    uint32_t fill;
} rrc_sha256_t;

void rrc_sha256_init(rrc_sha256_t *ctx);
void rrc_sha256_update(rrc_sha256_t *ctx, const void *data, size_t len);
void rrc_sha256_final(rrc_sha256_t *ctx, uint8_t digest[RRC_SHA256_LEN]);
void rrc_sha256(const void *data, size_t len, uint8_t digest[RRC_SHA256_LEN]);
/* Lowercase hex with terminating NUL: out must hold 2 * n + 1 bytes. */
void rrc_hex_lower(const uint8_t *bytes, size_t n, char *out);

#ifdef __cplusplus
}
#endif
#endif
