#include "rrc_crc32.h"

/* Nibble table for polynomial 0xEDB88320 (16 words of flash instead of 256). */
static const uint32_t k_tab[16] = {
    0x00000000u, 0x1DB71064u, 0x3B6E20C8u, 0x26D930ACu, 0x76DC4190u, 0x6B6B51F4u, 0x4DB26158u, 0x5005713Cu,
    0xEDB88320u, 0xF00F9344u, 0xD6D6A3E8u, 0xCB61B38Cu, 0x9B64C2B0u, 0x86D3D2D4u, 0xA00AE278u, 0xBDBDF21Cu};

uint32_t rrc_crc32_update(uint32_t crc, const uint8_t *data, size_t len)
{
    uint32_t c = ~crc;
    for (size_t i = 0; i < len; i++) {
        c ^= data[i];
        c = (c >> 4) ^ k_tab[c & 0x0Fu];
        c = (c >> 4) ^ k_tab[c & 0x0Fu];
    }
    return ~c;
}

uint32_t rrc_crc32(const uint8_t *data, size_t len)
{
    return rrc_crc32_update(0u, data, len);
}
