/* Single-producer / single-consumer byte ring buffer (ISR -> main loop). The capacity must be
 * a power of two; one producer context calls push, one consumer context calls pop. Indices are
 * free-running 32-bit counters, so no "one slot empty" rule is needed. */
#ifndef RRC_RING_H
#define RRC_RING_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint8_t *buf;
    uint32_t mask;          /* capacity - 1 */
    volatile uint32_t head; /* written by the producer */
    volatile uint32_t tail; /* written by the consumer */
    volatile uint32_t dropped; /* bytes rejected because the ring was full */
} rrc_ring_t;

/* Returns false if capacity is not a power of two (>= 2). */
bool rrc_ring_init(rrc_ring_t *r, uint8_t *buf, uint32_t capacity);
bool rrc_ring_push(rrc_ring_t *r, uint8_t byte); /* false (and counted in dropped) when full */
bool rrc_ring_pop(rrc_ring_t *r, uint8_t *byte); /* false when empty */
uint32_t rrc_ring_count(const rrc_ring_t *r);
uint32_t rrc_ring_free(const rrc_ring_t *r);
void rrc_ring_clear(rrc_ring_t *r); /* consumer side only */

#ifdef __cplusplus
}
#endif
#endif
