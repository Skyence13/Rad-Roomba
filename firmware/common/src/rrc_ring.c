#include "rrc_ring.h"

bool rrc_ring_init(rrc_ring_t *r, uint8_t *buf, uint32_t capacity)
{
    if ((buf == NULL) || (capacity < 2u) || ((capacity & (capacity - 1u)) != 0u)) {
        return false;
    }
    r->buf = buf;
    r->mask = capacity - 1u;
    r->head = 0u;
    r->tail = 0u;
    r->dropped = 0u;
    return true;
}

uint32_t rrc_ring_count(const rrc_ring_t *r)
{
    const uint32_t h = r->head;
    const uint32_t t = r->tail;
    return h - t;
}

uint32_t rrc_ring_free(const rrc_ring_t *r)
{
    return (r->mask + 1u) - rrc_ring_count(r);
}

bool rrc_ring_push(rrc_ring_t *r, uint8_t byte)
{
    const uint32_t h = r->head;
    if ((h - r->tail) > r->mask) {
        r->dropped = r->dropped + 1u;
        return false;
    }
    r->buf[h & r->mask] = byte;
    r->head = h + 1u;
    return true;
}

bool rrc_ring_pop(rrc_ring_t *r, uint8_t *byte)
{
    const uint32_t t = r->tail;
    if (t == r->head) {
        return false;
    }
    *byte = r->buf[t & r->mask];
    r->tail = t + 1u;
    return true;
}

void rrc_ring_clear(rrc_ring_t *r)
{
    r->tail = r->head;
}
