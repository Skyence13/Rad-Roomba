/* Monotonic clock helpers: 32->64 bit counter extension, overflow-safe tick scaling,
 * deadlines. All times are unsigned and monotonic; nothing here reads a clock itself. */
#ifndef RRC_CLOCK_H
#define RRC_CLOCK_H
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Extends a free-running 32-bit counter to 64 bits. rrc_wrap32_extend() must be called at
 * least once per counter period (2^32 ticks) and never concurrently with itself. */
typedef struct {
    uint32_t last;
    uint64_t high; /* multiple of 2^32 */
} rrc_wrap32_t;

void rrc_wrap32_init(rrc_wrap32_t *w, uint32_t now);
uint64_t rrc_wrap32_extend(rrc_wrap32_t *w, uint32_t now);

/* floor(a * mul / div) without intermediate overflow; div must be non-zero. Saturates to
 * UINT64_MAX if the result does not fit. */
uint64_t rrc_muldiv_u64(uint64_t a, uint32_t mul, uint32_t div);

/* Converts a tick count at tick_hz to whole microseconds (floor). tick_hz must be non-zero. */
uint64_t rrc_ticks_to_us(uint64_t ticks, uint32_t tick_hz);
/* Converts microseconds to ticks at tick_hz (floor). */
uint64_t rrc_us_to_ticks(uint64_t us, uint32_t tick_hz);

/* Deadline helpers on a 64-bit microsecond clock. */
static inline bool rrc_time_reached(uint64_t now_us, uint64_t deadline_us)
{
    return now_us >= deadline_us;
}
static inline uint64_t rrc_time_since(uint64_t now_us, uint64_t then_us)
{
    return (now_us >= then_us) ? (now_us - then_us) : 0u;
}
/* a + b saturating at UINT64_MAX */
static inline uint64_t rrc_time_add(uint64_t a, uint64_t b)
{
    return ((UINT64_MAX - a) < b) ? UINT64_MAX : (a + b);
}

#ifdef __cplusplus
}
#endif
#endif
