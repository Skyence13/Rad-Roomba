/* RFC 4122 version-4 (random) UUID from an entropy callback. */
#ifndef RRC_UUID_H
#define RRC_UUID_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define RRC_UUID_STR_LEN 36u /* without the terminating NUL */

/* Fills buf with len bytes of entropy; returns false if the source failed. */
typedef bool (*rrc_entropy_fn)(void *ctx, uint8_t *buf, size_t len);

/* Formats 16 random bytes as a v4 UUID string (lowercase, NUL-terminated, 37 bytes). The
 * version and variant bits are forced. */
void rrc_uuid4_format(const uint8_t random16[16], char out[RRC_UUID_STR_LEN + 1u]);
/* Draws 16 bytes from the callback and formats them. Returns false (out untouched) if the
 * entropy source failed. */
bool rrc_uuid4_generate(rrc_entropy_fn fn, void *ctx, char out[RRC_UUID_STR_LEN + 1u]);
/* True if s (NUL-terminated) is a canonical lowercase 8-4-4-4-12 UUID string. */
bool rrc_uuid_is_canonical(const char *s);

#ifdef __cplusplus
}
#endif
#endif
