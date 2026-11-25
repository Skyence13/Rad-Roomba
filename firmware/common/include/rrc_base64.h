/* Base64 (RFC 4648 standard alphabet, '=' padding). */
#ifndef RRC_BASE64_H
#define RRC_BASE64_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Encoded length for n input bytes, excluding any terminator. */
#define RRC_BASE64_ENC_LEN(n) ((((n) + 2u) / 3u) * 4u)

/* Encodes n bytes into out (not NUL-terminated). Returns the number of characters written,
 * or 0 if cap is too small (n == 0 also returns 0). */
size_t rrc_base64_encode(const uint8_t *in, size_t n, char *out, size_t cap);

/* Strict decode (as Python base64.b64decode(validate=True)): length must be a multiple of 4,
 * only alphabet characters, padding only at the end, zero pad bits. Returns the decoded
 * length, or -1 on any violation or if cap is too small. */
long rrc_base64_decode(const char *in, size_t n, uint8_t *out, size_t cap);

#ifdef __cplusplus
}
#endif
#endif
