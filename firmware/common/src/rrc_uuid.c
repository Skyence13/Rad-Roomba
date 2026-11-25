#include "rrc_uuid.h"

#include <string.h>

void rrc_uuid4_format(const uint8_t random16[16], char out[RRC_UUID_STR_LEN + 1u])
{
    static const char hex[] = "0123456789abcdef";
    uint8_t b[16];
    memcpy(b, random16, sizeof b);
    b[6] = (uint8_t)((b[6] & 0x0Fu) | 0x40u); /* version 4 */
    b[8] = (uint8_t)((b[8] & 0x3Fu) | 0x80u); /* RFC 4122 variant */
    size_t o = 0u;
    for (size_t i = 0u; i < 16u; i++) {
        if ((i == 4u) || (i == 6u) || (i == 8u) || (i == 10u)) {
            out[o] = '-';
            o++;
        }
        out[o] = hex[(b[i] >> 4) & 0x0Fu];
        out[o + 1u] = hex[b[i] & 0x0Fu];
        o += 2u;
    }
    out[o] = '\0';
}

bool rrc_uuid4_generate(rrc_entropy_fn fn, void *ctx, char out[RRC_UUID_STR_LEN + 1u])
{
    uint8_t r[16];
    if ((fn == NULL) || !fn(ctx, r, sizeof r)) {
        return false;
    }
    rrc_uuid4_format(r, out);
    return true;
}

bool rrc_uuid_is_canonical(const char *s)
{
    if (s == NULL) {
        return false;
    }
    for (size_t i = 0u; i < RRC_UUID_STR_LEN; i++) {
        const char c = s[i];
        if ((i == 8u) || (i == 13u) || (i == 18u) || (i == 23u)) {
            if (c != '-') {
                return false;
            }
        } else if (!(((c >= '0') && (c <= '9')) || ((c >= 'a') && (c <= 'f')))) {
            return false;
        } else {
            /* hex digit */
        }
    }
    return s[RRC_UUID_STR_LEN] == '\0';
}
