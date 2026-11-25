#include "rrc_clock.h"

void rrc_wrap32_init(rrc_wrap32_t *w, uint32_t now)
{
    w->last = now;
    w->high = 0u;
}

uint64_t rrc_wrap32_extend(rrc_wrap32_t *w, uint32_t now)
{
    if (now < w->last) {
        w->high += (uint64_t)1 << 32;
    }
    w->last = now;
    return w->high | (uint64_t)now;
}

uint64_t rrc_muldiv_u64(uint64_t a, uint32_t mul, uint32_t div)
{
    const uint64_t q = a / div;
    const uint64_t r = a % div;
    /* r < div <= 2^32-1 and mul <= 2^32-1, so r * mul cannot overflow 64 bits. */
    const uint64_t low = (r * (uint64_t)mul) / div;
    if ((mul != 0u) && (q > (UINT64_MAX / (uint64_t)mul))) {
        return UINT64_MAX;
    }
    const uint64_t high = q * (uint64_t)mul;
    return ((UINT64_MAX - high) < low) ? UINT64_MAX : (high + low);
}

uint64_t rrc_ticks_to_us(uint64_t ticks, uint32_t tick_hz)
{
    return rrc_muldiv_u64(ticks, 1000000u, tick_hz);
}

uint64_t rrc_us_to_ticks(uint64_t us, uint32_t tick_hz)
{
    return rrc_muldiv_u64(us, tick_hz, 1000000u);
}
