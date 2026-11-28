/* VL53L4ED ranging sensor driver - STUB.
 *
 * The init/ranging register sequence of the VL53L4ED is only published as part of ST's
 * "Ultra Lite Driver" (STSW-IMG034 / VL53L4ED ULD), which could not be downloaded in the build
 * environment of this revision. No register values are invented here. To complete the port:
 *   1. add the ULD sources (VL53L4ED_api.c, platform.c) to this directory;
 *   2. implement the ULD platform I2C functions with HAL_I2C_Mem_Read/Write on `bus`
 *      (7-bit address I2C_ADDR_TOF_X11, 16-bit register index);
 *   3. in tof_init(): for each of the 11 mux channels call the ULD sensor-init, set the timing
 *      budget (<= 20 ms) and start continuous ranging;
 *   4. in tof_read(): check data-ready, read the result, map the ULD range status to
 *      rrch_tof_status_t (0 -> OK, "no target"/signal fail -> NO_TARGET, others -> INVALID),
 *      clear the interrupt.
 * Until then every sensor stays OFFLINE: the core inhibits all motion directions and latches
 * TOF_STALE if motion is attempted, which is the intended fail-safe behaviour.
 */
#include "bsp.h"

bool tof_init(I2C_HandleTypeDef *bus)
{
    (void)bus;
    return false;
}

bool tof_read(I2C_HandleTypeDef *bus, int idx, int32_t *range_mm, rrch_tof_status_t *st)
{
    (void)bus; (void)idx; (void)range_mm; (void)st;
    return false;
}
