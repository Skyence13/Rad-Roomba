/* Power telemetry device decode (INA228, INA3221) and the UNVERIFIED LTC4162 table. See rrch_pwrdev.h. */
#include "rrch_pwrdev.h"

#include <math.h>

const double rr_branch_shunt_ohm[3] = {0.020, 0.005, 0.005};

uint16_t rr_ina228_shunt_cal(double current_lsb, double r_shunt, bool adcrange_1)
{
    /* SLYS021A equation (2): SHUNT_CAL = 13107.2e6 x CURRENT_LSB x RSHUNT, multiplied by 4 for ADCRANGE = 1 */
    double v = 13107.2e6 * current_lsb * r_shunt * (adcrange_1 ? 4.0 : 1.0);
    long n = lround(v);
    return (uint16_t)(n < 0 ? 0 : (n > 0x7FFF ? 0x7FFF : n)); /* bits 14-0 */
}

int32_t rr_ina228_s20(const uint8_t b[3])
{
    uint32_t u = ((uint32_t)b[0] << 16) | ((uint32_t)b[1] << 8) | b[2];
    u >>= 4;
    if (u & 0x80000u) {
        return (int32_t)u - (int32_t)0x100000;
    }
    return (int32_t)u;
}

void rr_ina228_encode_s20(int32_t v, uint8_t b[3])
{
    uint32_t u = ((uint32_t)v & 0xFFFFFu) << 4;
    b[0] = (uint8_t)(u >> 16);
    b[1] = (uint8_t)(u >> 8);
    b[2] = (uint8_t)u;
}

float rr_ina228_vbus_v(const uint8_t b[3])
{
    return (float)((double)rr_ina228_s20(b) * 195.3125e-6);
}

float rr_ina228_current_a(const uint8_t b[3], double current_lsb)
{
    return (float)((double)rr_ina228_s20(b) * current_lsb);
}

float rr_ina228_dietemp_c(const uint8_t b[2])
{
    return (float)((double)(int16_t)(((uint16_t)b[0] << 8) | b[1]) * 7.8125e-3);
}

double rr_ina228_charge_c(const uint8_t b[5], double current_lsb)
{
    uint64_t u = 0;
    for (int i = 0; i < 5; i++) {
        u = (u << 8) | b[i];
    }
    int64_t s = (u & (1ull << 39)) ? (int64_t)u - (int64_t)(1ull << 40) : (int64_t)u;
    return (double)s * current_lsb;
}

bool rr_ina228_id_ok(const uint8_t mfr[2], const uint8_t dev[2])
{
    uint16_t m = (uint16_t)((mfr[0] << 8) | mfr[1]), d = (uint16_t)((dev[0] << 8) | dev[1]);
    return m == 0x5449u && (d >> 4) == 0x228u;
}

float rr_ina3221_shunt_v(const uint8_t b[2])
{
    int16_t r = (int16_t)(((uint16_t)b[0] << 8) | b[1]);
    return (float)((double)(r >> 3) * 40e-6);
}

void rr_ina3221_encode_shunt(double v, uint8_t b[2])
{
    long n = lround(v / 40e-6);
    n = n > 4095 ? 4095 : (n < -4096 ? -4096 : n);
    uint16_t u = (uint16_t)((uint16_t)(int16_t)n << 3);
    b[0] = (uint8_t)(u >> 8);
    b[1] = (uint8_t)u;
}

float rr_ina3221_bus_v(const uint8_t b[2])
{
    int16_t r = (int16_t)(((uint16_t)b[0] << 8) | b[1]);
    return (float)((double)(r >> 3) * 8e-3);
}

bool rr_ina3221_id_ok(const uint8_t mfr[2], const uint8_t die[2])
{
    return ((mfr[0] << 8) | mfr[1]) == 0x5449 && ((die[0] << 8) | die[1]) == 0x3220;
}

/* UNVERIFIED (recollection of the Linux LTC4162-L driver; -F variant and datasheet not checked). Not used. */
const rr_ltc4162_reg_t rr_ltc4162_regs_unverified[] = {
    {"CHARGER_STATE", 0x34}, {"CHARGE_STATUS", 0x35}, {"SYSTEM_STATUS", 0x39}, {"VBAT", 0x3A}, {"VIN", 0x3B},
    {"IBAT", 0x3D}, {"IIN", 0x3E}, {"DIE_TEMPERATURE", 0x3F}, {"THERMISTOR_VOLTAGE", 0x40}, {"JEITA_REGION", 0x42},
    {"CHEM_CELLS", 0x43},
};
const unsigned rr_ltc4162_regs_unverified_n = sizeof rr_ltc4162_regs_unverified / sizeof rr_ltc4162_regs_unverified[0];
