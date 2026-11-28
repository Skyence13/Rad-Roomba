#include "rrc_sha256.h"

#include <string.h>

static const uint32_t k_k[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
    0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u, 0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
    0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
    0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
    0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u, 0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
    0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
    0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
    0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u, 0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u};

static uint32_t rotr(uint32_t x, uint32_t n)
{
    return (x >> n) | (x << (32u - n));
}

static void compress(uint32_t st[8], const uint8_t blk[64])
{
    uint32_t w[64];
    for (uint32_t i = 0u; i < 16u; i++) {
        w[i] = ((uint32_t)blk[4u * i] << 24) | ((uint32_t)blk[(4u * i) + 1u] << 16) |
               ((uint32_t)blk[(4u * i) + 2u] << 8) | (uint32_t)blk[(4u * i) + 3u];
    }
    for (uint32_t i = 16u; i < 64u; i++) {
        const uint32_t s0 = rotr(w[i - 15u], 7u) ^ rotr(w[i - 15u], 18u) ^ (w[i - 15u] >> 3);
        const uint32_t s1 = rotr(w[i - 2u], 17u) ^ rotr(w[i - 2u], 19u) ^ (w[i - 2u] >> 10);
        w[i] = w[i - 16u] + s0 + w[i - 7u] + s1;
    }
    uint32_t a = st[0], b = st[1], c = st[2], d = st[3], e = st[4], f = st[5], g = st[6], h = st[7];
    for (uint32_t i = 0u; i < 64u; i++) {
        const uint32_t s1 = rotr(e, 6u) ^ rotr(e, 11u) ^ rotr(e, 25u);
        const uint32_t ch = (e & f) ^ (~e & g);
        const uint32_t t1 = h + s1 + ch + k_k[i] + w[i];
        const uint32_t s0 = rotr(a, 2u) ^ rotr(a, 13u) ^ rotr(a, 22u);
        const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        const uint32_t t2 = s0 + maj;
        h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    st[0] += a; st[1] += b; st[2] += c; st[3] += d; st[4] += e; st[5] += f; st[6] += g; st[7] += h;
}

void rrc_sha256_init(rrc_sha256_t *ctx)
{
    static const uint32_t iv[8] = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
                                   0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
    memcpy(ctx->state, iv, sizeof iv);
    ctx->total = 0u;
    ctx->fill = 0u;
}

void rrc_sha256_update(rrc_sha256_t *ctx, const void *data, size_t len)
{
    const uint8_t *p = (const uint8_t *)data;
    ctx->total += (uint64_t)len;
    while (len > 0u) {
        size_t n = 64u - (size_t)ctx->fill;
        if (n > len) {
            n = len;
        }
        memcpy(&ctx->block[ctx->fill], p, n);
        ctx->fill += (uint32_t)n;
        p += n;
        len -= n;
        if (ctx->fill == 64u) {
            compress(ctx->state, ctx->block);
            ctx->fill = 0u;
        }
    }
}

void rrc_sha256_final(rrc_sha256_t *ctx, uint8_t digest[RRC_SHA256_LEN])
{
    const uint64_t bits = ctx->total * 8u;
    ctx->block[ctx->fill] = 0x80u;
    ctx->fill++;
    if (ctx->fill > 56u) {
        memset(&ctx->block[ctx->fill], 0, 64u - (size_t)ctx->fill);
        compress(ctx->state, ctx->block);
        ctx->fill = 0u;
    }
    memset(&ctx->block[ctx->fill], 0, 56u - (size_t)ctx->fill);
    for (uint32_t i = 0u; i < 8u; i++) {
        ctx->block[56u + i] = (uint8_t)(bits >> (56u - (8u * i)));
    }
    compress(ctx->state, ctx->block);
    for (uint32_t i = 0u; i < 8u; i++) {
        digest[4u * i] = (uint8_t)(ctx->state[i] >> 24);
        digest[(4u * i) + 1u] = (uint8_t)(ctx->state[i] >> 16);
        digest[(4u * i) + 2u] = (uint8_t)(ctx->state[i] >> 8);
        digest[(4u * i) + 3u] = (uint8_t)ctx->state[i];
    }
}

void rrc_sha256(const void *data, size_t len, uint8_t digest[RRC_SHA256_LEN])
{
    rrc_sha256_t ctx;
    rrc_sha256_init(&ctx);
    rrc_sha256_update(&ctx, data, len);
    rrc_sha256_final(&ctx, digest);
}

void rrc_hex_lower(const uint8_t *bytes, size_t n, char *out)
{
    static const char hex[] = "0123456789abcdef";
    for (size_t i = 0u; i < n; i++) {
        out[2u * i] = hex[(bytes[i] >> 4) & 0x0Fu];
        out[(2u * i) + 1u] = hex[bytes[i] & 0x0Fu];
    }
    out[2u * n] = '\0';
}
