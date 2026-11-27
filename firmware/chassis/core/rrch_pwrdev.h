/* Power telemetry devices on I2C_SYS: register maps, configuration words and decode, hardware
 * independent so that the STM32 port (I2C transfers) and the emulator (register images from the
 * plant) run the same code, and the unit tests can check it against datasheet examples.
 *
 * Evidence:
 *   INA228  (U2, 0x40)  register map, LSBs and SHUNT_CAL equation read from TI SLYS021A (2022), tables
 *                       7-2/7-3/7-5..7-15 and section 8.1.2, on 2026-11-27: VERIFIED against the datasheet,
 *                       not on hardware.
 *   INA3221 (U15, 0x41) register map and LSBs read from TI SBOS576C, tables 7-1, 8-1, 8-2, 8-5, 8-7:
 *                       VERIFIED against the datasheet, not on hardware.
 *   LTC4162-FAD (U3, 0x68) UNVERIFIED: the datasheet could not be fetched (analog.com, IB-06; one attempt
 *                       on 2026-11-27 failed). The register table below is a recollection of the Linux
 *                       driver for the LTC4162-L (drivers/power/supply/ltc4162-l-charger.c), NOT checked
 *                       for the -F variant and NOT checked against any datasheet. It is compiled but not
 *                       used: RR_LTC4162_REGMAP_VERIFIED is 0, the driver reports "not ok" and the core
 *                       raises CHARGER_COMM. Charging safety does not depend on it: the +5 C charge
 *                       inhibit (U32B/Q6 on the NTC line) and the charger's own limits are hardware.
 */
#ifndef RRCH_PWRDEV_H
#define RRCH_PWRDEV_H
#include <stdbool.h>
#include <stdint.h>

/* ---- INA228 (SLYS021A) ---- */
#define RR_INA228_REG_CONFIG 0x00u
#define RR_INA228_REG_ADC_CONFIG 0x01u
#define RR_INA228_REG_SHUNT_CAL 0x02u
#define RR_INA228_REG_VSHUNT 0x04u      /* 24 bit, bits 23-4 */
#define RR_INA228_REG_VBUS 0x05u        /* 24 bit, bits 23-4, 195.3125 uV/LSB */
#define RR_INA228_REG_DIETEMP 0x06u     /* 16 bit, 7.8125 m degC/LSB */
#define RR_INA228_REG_CURRENT 0x07u     /* 24 bit, bits 23-4, x CURRENT_LSB */
#define RR_INA228_REG_CHARGE 0x0Au      /* 40 bit two's complement, x CURRENT_LSB = coulomb */
#define RR_INA228_REG_DIAG_ALRT 0x0Bu
#define RR_INA228_REG_MANUFACTURER_ID 0x3Eu /* 0x5449 "TI" */
#define RR_INA228_REG_DEVICE_ID 0x3Fu       /* DIEID (bits 15-4) = 0x228 */
#define RR_INA228_CONFIG_ADCRANGE 0x0010u   /* bit 4: +-40.96 mV */
#define RR_INA228_CONFIG_RSTACC 0x4000u     /* bit 14: clear ENERGY / CHARGE */
#define RR_PMON_SHUNT_OHM 0.001             /* R_SH1, WSL25121L000FEA (netlist export) */
#define RR_PMON_CURRENT_LSB 1.0e-4          /* A: 2^19 x 1e-4 = 52 A > 41 A full scale at ADCRANGE 1 */
uint16_t rr_ina228_shunt_cal(double current_lsb, double r_shunt, bool adcrange_1); /* equation (2), x4 for ADCRANGE 1 */
int32_t rr_ina228_s20(const uint8_t b[3]);   /* bits 23-4 of a big-endian 24-bit register, sign extended */
float rr_ina228_vbus_v(const uint8_t b[3]);
float rr_ina228_current_a(const uint8_t b[3], double current_lsb);
float rr_ina228_dietemp_c(const uint8_t b[2]);
double rr_ina228_charge_c(const uint8_t b[5], double current_lsb);
bool rr_ina228_id_ok(const uint8_t mfr[2], const uint8_t dev[2]);

/* ---- INA3221 (SBOS576C) ---- */
#define RR_INA3221_REG_CONFIG 0x00u     /* reset 0x7127: all channels, continuous shunt + bus */
#define RR_INA3221_REG_SHUNT(ch) (uint8_t)(0x01u + 2u * (ch)) /* ch 0..2; bits 15-3, 40 uV/LSB */
#define RR_INA3221_REG_BUS(ch) (uint8_t)(0x02u + 2u * (ch))   /* bits 15-3, 8 mV/LSB */
#define RR_INA3221_REG_MANUFACTURER_ID 0xFEu /* 0x5449 */
#define RR_INA3221_REG_DIE_ID 0xFFu          /* 0x3220 */
/* channel shunts from the netlist export: ch1 HEAD_PWR R_SH2 20 mOhm, ch2 HEAD_HTR R_SH3 5 mOhm, ch3 CHS_HTR R_SH4 5 mOhm */
extern const double rr_branch_shunt_ohm[3];
float rr_ina3221_shunt_v(const uint8_t b[2]);
float rr_ina3221_bus_v(const uint8_t b[2]);
bool rr_ina3221_id_ok(const uint8_t mfr[2], const uint8_t die[2]);
/* inverse functions for the emulator's register model and the unit tests */
void rr_ina3221_encode_shunt(double v, uint8_t b[2]);
void rr_ina228_encode_s20(int32_t v, uint8_t b[3]);

/* ---- LTC4162-FAD: UNVERIFIED, NOT USED (see the header comment) ---- */
#define RR_LTC4162_REGMAP_VERIFIED 0
typedef struct {
    const char *name;
    uint8_t addr;       /* recalled, UNVERIFIED */
} rr_ltc4162_reg_t;
extern const rr_ltc4162_reg_t rr_ltc4162_regs_unverified[];
extern const unsigned rr_ltc4162_regs_unverified_n;

#endif
