/* RR-HEAD-ACQ rev A board constants and the pure conversions derived from them.
 *
 * Every resistor below carries the reference designator of electronics/head_acq/design/circuit.py
 * (channel designators are for channel 0 = F0; channel c uses 100*(c+1)+k, the generator is the
 * same for all eight, the circuit self-check proves it). tools/check_circuit.py recomputes the
 * values from circuit.py on every `check.sh` run and fails if a #define here disagrees with the
 * circuit, so a change of the board cannot silently leave the firmware behind.
 *
 * Evidence classes: "circuit" = value read from circuit.py and checked by tool; "derived" =
 * calculated here from circuit values; "datasheet" = a device figure recalled from a data sheet
 * that could not be opened from the build host (UNVERIFIED unless stated); "assumed" = not
 * derivable (named placeholder, listed in README "Placeholders and unverified constants").
 * All conversions use integer arithmetic only.
 */
#ifndef RRH_BOARD_H
#define RRH_BOARD_H
#include <stdbool.h>
#include <stdint.h>

#include "rrh_config.h"

#ifdef __cplusplus
extern "C" {
#endif

#define RRH_CHAINS 8u /* chain index 0..3 = floor lanes F0..F3, 4..7 = reference lanes R0..R3 */

/* ---- resistors read from circuit.py (ohm) ---------------------------------------------------- */
/* Bias set-point law: HV_BUS = (R2213 + R2214 + R2215) / R2215 x V(HV_SET) = 25.0 x V(HV_SET). */
#define RRH_R2213_OHM 1200000u /* 0.1 %  feedback divider top */
#define RRH_R2214_OHM 1200000u /* 0.1 %  feedback divider top */
#define RRH_R2215_OHM 100000u  /* 0.1 %  feedback divider bottom */
/* Independent bias read-back BIAS_VMON = HV_BUS x R2219 / (R2217 + R2218 + R2219) (1:25.22). */
#define RRH_R2217_OHM 4990000u /* 1 %    monitor divider top */
#define RRH_R2218_OHM 4990000u /* 1 %    monitor divider top */
#define RRH_R2219_OHM 412000u  /* 0.1 %  monitor divider bottom */
/* Over-voltage comparator U2203 trips when V(BIAS_VMON_B) > VREF x R2223 / (R2222 + R2223). */
#define RRH_R2222_OHM 10000u /* 0.1 %  OVP strap divider top */
#define RRH_R2223_OHM 7150u  /* 0.1 %  OVP STRAP, fitted for onsemi J/C (31.5 V) */
/* Boost output HV_RAW = 1.2 V x (1 + (R2201 + R2202) / R2203) (strap = R2203). */
#define RRH_R2201_OHM 1070000u /* 1 % */
#define RRH_R2202_OHM 1070000u /* 1 % */
#define RRH_R2203_OHM 71500u   /* 1 %    HV_RAW STRAP, fitted for onsemi J/C (37.1 V) */
/* Total bias current monitor: BIAS_IMON = 0.8 x I x R2206 (TPS61391 mirror gain 0.8, datasheet). */
#define RRH_R2206_OHM 10000u /* 0.1 % */
/* Supply monitor: VIN_MON = HEAD_PWR x R2011 / (R2010 + R2011). */
#define RRH_R2010_OHM 56000u
#define RRH_R2011_OHM 10000u
/* Per-chain anode current sense: I = (V_TRIM - V_TRIMDRV) / R105 (R205 ... R805 identical). */
#define RRH_R105_OHM 4990u /* 0.1 % */
/* Per-chain IMON path to the ADC: R108 (10 k) from V_TRIMDRV to the IMON mux, C2704 (100 nF) on
 * the mux output, buffer U2306B, R2701 (1 k) + C2705 (10 nF) to PE15. */
#define RRH_R108_OHM 10000u
#define RRH_C2704_NF 100u
/* LED pulser amplitude stage U2306A: V_LED = (1 + R2313 / R2314) x V(LED_AMPL) = 2 x. */
#define RRH_R2313_OHM 10000u
#define RRH_R2314_OHM 10000u
/* Test pulser: charge = C_INJ x V(PULSER_AMPL); C_INJ = C109 (C209 ... C809) 100 pF 1 % C0G. */
#define RRH_CINJ_PF 100u
/* Baseline 0.600 V = 2.5 V x R2311 / (R2310 + R2311). */
#define RRH_R2310_OHM 10000u
#define RRH_R2311_OHM 3160u

/* ---- converters and references ------------------------------------------------------------------ */
#define RRH_ADC_BITS 12u
#define RRH_ADC_FS 4095u
#define RRH_VREF_MV 3000u      /* U2105 REF3030 (circuit); initial accuracy is a datasheet figure, UNVERIFIED */
#define RRH_DAC_VREF_MV 2500u  /* DAC60508Z internal reference (datasheet); output gain 1 after bsp_dac_init (UNVERIFIED) */
#define RRH_DAC_CODES 4096u

/* ---- derived transfer functions (integer, rounded to nearest) --------------------------------- */
/* HV_SET DAC code <-> bias voltage at HV_BUS. 25 x 2.5 V = 62.5 V full scale (code 4096). */
#define RRH_HV_GAIN_NUM (RRH_R2213_OHM + RRH_R2214_OHM + RRH_R2215_OHM)
#define RRH_HV_GAIN_DEN RRH_R2215_OHM
#define RRH_HV_FS_MV ((uint32_t)(((uint64_t)RRH_DAC_VREF_MV * RRH_HV_GAIN_NUM) / RRH_HV_GAIN_DEN)) /* 62500 */
uint16_t rrh_board_hv_code(uint32_t bias_mv);      /* clamps to 0..4095 */
uint32_t rrh_board_hv_mv(uint16_t code);           /* what the code commands (nominal) */
/* ADC pin voltage (mV) -> quantity at the source. */
uint32_t rrh_board_bias_mv(uint32_t adc_mv);       /* BIAS_VMON x (R2217 + R2218 + R2219) / R2219 */
uint32_t rrh_board_bias_total_ua(uint32_t adc_mv); /* BIAS_IMON / (0.8 x R2206) (includes both dividers) */
uint32_t rrh_board_supply_mv(uint32_t adc_mv);     /* VIN_MON x (R2010 + R2011) / R2011 */
/* Current that the two bias dividers draw at a bias voltage (nA): V / (R2213 + R2214 + R2215) +
 * V / (R2217 + R2218 + R2219). The total-current monitor includes them (budget 5.1). */
uint32_t rrh_board_bias_divider_na(uint32_t bias_mv);
/* Per-chain anode current in nA from the trim DAC code and the voltage seen on IMON_CH in uV:
 * I = (V_trim - V_imon) / R105. Result clamps at 0 (an offset-induced negative reading is 0). */
uint32_t rrh_board_trim_uv(uint16_t trim_code);
uint32_t rrh_board_imon_na(uint16_t trim_code, uint32_t imon_uv);
uint32_t rrh_board_adc_uv(uint16_t code);          /* ADC code -> uV at VREF 3.0 V */
/* LED amplitude: V_LED in mV for a DAC code (2 x gain stage). */
uint32_t rrh_board_led_mv(uint16_t code);
/* Test pulser: injected charge in fC for a DAC code (C_INJ x V). */
uint32_t rrh_board_pulser_fc(uint16_t code);
/* Baseline voltage in mV (0.600 V), and the threshold DAC code for a level `above_baseline_mv`
 * above it. Used for the default thresholds. */
uint32_t rrh_board_baseline_uv(void);
uint16_t rrh_board_threshold_code(uint32_t above_baseline_uv);

/* NTC conversion: 10.0 k (0.1 %) from VREF to the node, NTC to ground (circuit: R1016 ... R1316,
 * R2231, R2613). Beta-model tables at 5 degC steps from -40 to +125 degC with linear
 * interpolation; the device constant is a property of the part, not of the board. */
typedef enum {
    RRH_NTC_B3435 = 0, /* "10 k B3435-class" SiPM carrier and heater-plate NTCs: supplier part not chosen, ASSUMED */
    RRH_NTC_B3380 = 1  /* RT2201 NCP15XH103F03RC (circuit), board NTC */
} rrh_ntc_t;
#define RRH_TEMP_NTC_INVALID INT32_MIN
int32_t rrh_board_ntc_mc(uint16_t adc_code, rrh_ntc_t kind); /* RRH_TEMP_NTC_INVALID if open/short/out of range */

/* ---- bias protection straps per SiPM family (budget 5.2) ------------------------------------------ */
typedef struct {
    const char *family;
    uint32_t r_raw_ohm; /* R2203: boost feedback bottom */
    uint32_t r_ovp_ohm; /* R2223: OVP strap */
} rrh_strap_t;
#define RRH_STRAP_COUNT 4u
extern const rrh_strap_t rrh_straps[RRH_STRAP_COUNT];
uint32_t rrh_board_hv_raw_mv(uint32_t r_raw_ohm);  /* boost output for a strap */
uint32_t rrh_board_ovp_trip_mv(uint32_t r_ovp_ohm); /* over-voltage trip (nominal) for a strap */
/* The strap actually fitted: rev A = onsemi J/C (R2203 71.5 k, R2223 7.15 k). A build for another
 * family sets -DRRH_SIPM_FAMILY=n (index into rrh_straps) AFTER the straps on the board were changed;
 * tools/check_circuit.py compares the #defines above (the rev A circuit) with circuit.py. */
#ifndef RRH_SIPM_FAMILY
#define RRH_SIPM_FAMILY 0u
#endif
/* Nominal over-voltage trip of the fitted strap and the highest set-point the firmware accepts. */
uint32_t rrh_board_fitted_ovp_trip_mv(void);
uint32_t rrh_board_bias_limit_mv(void);

/* ---- I2C expander TCA9534 at 0x20 (U2405): bit assignment of the input port (circuit) ---------------- */
#define RRH_EXP_ADDR 0x20u
#define RRH_EXP_MON_EXT 0x01u    /* P0 output: lane monitor page select (not used by this firmware, left 0) */
#define RRH_EXP_HV_PERMIT 0x02u  /* P1 in: bias permit latch Q, high = permitted */
#define RRH_EXP_HV_INH_N 0x04u   /* P2 in: inhibit bus, LOW = inhibit active (OVP, +5V_A low or lid open) */
#define RRH_EXP_LID_G 0x08u      /* P3 in: lid input after filter, HIGH = lid open / unplugged (J2201) */
#define RRH_EXP_EF_FLT_N 0x10u   /* P4 in: TPS26600 eFuse fault, LOW = fault */
#define RRH_EXP_HWREV0 0x20u     /* P5: board revision strap bit 0 (rev A = 0) */
#define RRH_EXP_HWREV1 0x40u     /* P6: board revision strap bit 1 (rev A = 0) */
#define RRH_EXP_DIR_MASK 0xFEu   /* configuration register: P0 output, all others inputs */

#ifdef __cplusplus
}
#endif
#endif
