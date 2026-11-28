#include "rrc_base64.h"

static const char k_alpha[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

size_t rrc_base64_encode(const uint8_t *in, size_t n, char *out, size_t cap)
{
    const size_t need = RRC_BASE64_ENC_LEN(n);
    if ((need > cap) || (need < n)) {
        return 0u;
    }
    size_t o = 0u;
    size_t i = 0u;
    while ((n - i) >= 3u) {
        const uint32_t v = ((uint32_t)in[i] << 16) | ((uint32_t)in[i + 1u] << 8) | (uint32_t)in[i + 2u];
        out[o] = k_alpha[(v >> 18) & 0x3Fu];
        out[o + 1u] = k_alpha[(v >> 12) & 0x3Fu];
        out[o + 2u] = k_alpha[(v >> 6) & 0x3Fu];
        out[o + 3u] = k_alpha[v & 0x3Fu];
        o += 4u;
        i += 3u;
    }
    if ((n - i) == 1u) {
        const uint32_t v = (uint32_t)in[i] << 16;
        out[o] = k_alpha[(v >> 18) & 0x3Fu];
        out[o + 1u] = k_alpha[(v >> 12) & 0x3Fu];
        out[o + 2u] = '=';
        out[o + 3u] = '=';
        o += 4u;
    } else if ((n - i) == 2u) {
        const uint32_t v = ((uint32_t)in[i] << 16) | ((uint32_t)in[i + 1u] << 8);
        out[o] = k_alpha[(v >> 18) & 0x3Fu];
        out[o + 1u] = k_alpha[(v >> 12) & 0x3Fu];
        out[o + 2u] = k_alpha[(v >> 6) & 0x3Fu];
        out[o + 3u] = '=';
        o += 4u;
    } else {
        /* nothing left */
    }
    return o;
}

static int sextet(char c)
{
    if ((c >= 'A') && (c <= 'Z')) {
        return c - 'A';
    }
    if ((c >= 'a') && (c <= 'z')) {
        return (c - 'a') + 26;
    }
    if ((c >= '0') && (c <= '9')) {
        return (c - '0') + 52;
    }
    if (c == '+') {
        return 62;
    }
    if (c == '/') {
        return 63;
    }
    return -1;
}

long rrc_base64_decode(const char *in, size_t n, uint8_t *out, size_t cap)
{
    if ((n % 4u) != 0u) {
        return -1;
    }
    size_t o = 0u;
    for (size_t i = 0u; i < n; i += 4u) {
        const int a = sextet(in[i]);
        const int b = sextet(in[i + 1u]);
        const int last = ((i + 4u) == n) ? 1 : 0;
        int c = sextet(in[i + 2u]);
        int d = sextet(in[i + 3u]);
        size_t bytes = 3u;
        if ((a < 0) || (b < 0)) {
            return -1;
        }
        if ((last != 0) && (in[i + 3u] == '=')) {
            d = 0;
            bytes = 2u;
            if (in[i + 2u] == '=') {
                c = 0;
                bytes = 1u;
                if ((b & 0x0F) != 0) {
                    return -1; /* non-zero pad bits */
                }
            } else if ((c < 0) || ((c & 0x03) != 0)) {
                return -1;
            } else {
                /* two data bytes, pad bits are zero */
            }
        } else if ((c < 0) || (d < 0)) {
            return -1;
        } else {
            /* full quantum */
        }
        if ((o + bytes) > cap) {
            return -1;
        }
        const uint32_t v = ((uint32_t)a << 18) | ((uint32_t)b << 12) | ((uint32_t)c << 6) | (uint32_t)d;
        out[o] = (uint8_t)(v >> 16);
        if (bytes > 1u) {
            out[o + 1u] = (uint8_t)(v >> 8);
        }
        if (bytes > 2u) {
            out[o + 2u] = (uint8_t)v;
        }
        o += bytes;
    }
    return (long)o;
}
