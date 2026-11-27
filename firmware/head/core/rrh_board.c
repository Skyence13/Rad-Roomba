/* Pure conversions derived from the RR-HEAD-ACQ circuit (see rrh_board.h). No hardware access. */
#include "rrh_board.h"

#define NTC_N 34u
#define NTC_T0_MC (-40000)
#define NTC_STEP_MC 5000
/* ADC code of a 10.0 k pull-up to VREF with the NTC to ground, -40 ... +125 degC in 5 degC steps:
 * code = 4095 x R/(10 k + R), R = 10 k x exp(B x (1/T - 1/298.15 K)) (beta model, calculated). */
static const uint16_t k_ntc_tab[2][NTC_N] = {
    {3936u, 3882u, 3813u, 3729u, 3627u, 3507u, 3368u, 3210u, 3037u, 2850u, 2654u, 2451u, 2248u, 2048u, 1854u, 1669u, 1496u,
     1337u, 1191u, 1059u, 940u, 834u, 740u, 657u, 584u, 519u, 462u, 412u, 368u, 329u, 295u, 265u, 238u, 215u},
    {3928u, 3872u, 3802u, 3716u, 3613u, 3492u, 3353u, 3196u, 3024u, 2839u, 2644u, 2445u, 2245u, 2048u, 1857u, 1675u, 1505u,
     1347u, 1203u, 1072u, 954u, 849u, 755u, 672u, 598u, 533u, 476u, 425u, 380u, 341u, 306u, 276u, 249u, 224u}};

const rrh_device_t rrh_devices[RRH_DEVICE_COUNT] = {
    {"J60035", 290u, 10u, 6930u, 30000u},  {"J30035", 180u, 9u, 12200u, 41500u}, {"S14160", 215u, 10u, 8200u, 31200u},
    {"S13360", 190u, 7u, 6300u, 23000u},   {"NUVMT", 200u, 23u, 24000u, 95000u}, {"4xJ60035", 655u, 12u, 2800u, 17800u}};

const rrh_strap_t rrh_straps[RRH_STRAP_COUNT] = {
    {"onsemi J/C", 71500u, 7150u}, {"Hamamatsu S14160", 53600u, 13000u}, {"Broadcom NUV-MT", 49900u, 16900u},
    {"Hamamatsu S13360", 40200u, 40200u}};

static uint32_t div_round(uint64_t num, uint64_t den)
{
    return (uint32_t)((num + (den / 2u)) / den);
}

uint16_t rrh_board_hv_code(uint32_t bias_mv)
{
    const uint32_t code = div_round((uint64_t)bias_mv * RRH_DAC_CODES, RRH_HV_FS_MV);
    return (uint16_t)((code > (RRH_DAC_CODES - 1u)) ? (RRH_DAC_CODES - 1u) : code);
}

uint32_t rrh_board_hv_mv(uint16_t code)
{
    return div_round((uint64_t)code * RRH_HV_FS_MV, RRH_DAC_CODES);
}

uint32_t rrh_board_bias_mv(uint32_t adc_mv)
{
    return div_round((uint64_t)adc_mv * (RRH_R2217_OHM + RRH_R2218_OHM + RRH_R2219_OHM), RRH_R2219_OHM);
}

/* I = V / (0.8 x R2206): mV / (8 mV per uA) with R2206 = 10 k (mirror gain 0.8 is a datasheet figure). */
uint32_t rrh_board_bias_mv_cal(uint32_t adc_uv, uint32_t ratio_e4)
{
    return div_round((uint64_t)adc_uv * ratio_e4, 10000000u);
}

uint32_t rrh_board_bias_adc_uv(uint32_t bias_mv, uint32_t ratio_e4)
{
    return div_round((uint64_t)bias_mv * 10000000u, ratio_e4);
}

/* V(sense) = I x 10 mohm x 50 = 0.5 V/A: mA = uV / 500 */
uint32_t rrh_board_heater_ma(uint32_t adc_uv)
{
    return div_round((uint64_t)adc_uv * 1000u, (uint64_t)RRH_R2601_MOHM * RRH_INA180_GAIN * 1000u);
}

uint32_t rrh_board_frame_nominal_uv(void)
{
    return rrh_board_baseline_uv() / 2u;
}

int32_t rrh_board_frame_mv(uint32_t mon_adc_uv)
{
    return (int32_t)(((int64_t)mon_adc_uv - (int64_t)rrh_board_frame_nominal_uv()) * 2 / 1000);
}

uint32_t rrh_board_bias_total_ua(uint32_t adc_mv)
{
    return div_round((uint64_t)adc_mv * 1000u * 10u, (uint64_t)8u * RRH_R2206_OHM);
}

uint32_t rrh_board_supply_mv(uint32_t adc_mv)
{
    return div_round((uint64_t)adc_mv * (RRH_R2010_OHM + RRH_R2011_OHM), RRH_R2011_OHM);
}

uint32_t rrh_board_bias_divider_na(uint32_t bias_mv)
{
    /* mV / ohm = mA; x 1e6 = nA */
    return div_round((uint64_t)bias_mv * 1000000u, RRH_HV_GAIN_NUM) +
           div_round((uint64_t)bias_mv * 1000000u, RRH_R2217_OHM + RRH_R2218_OHM + RRH_R2219_OHM);
}

uint32_t rrh_board_trim_uv(uint16_t trim_code)
{
    return div_round((uint64_t)trim_code * RRH_DAC_VREF_MV * 1000u, RRH_DAC_CODES);
}

uint32_t rrh_board_adc_uv(uint16_t code)
{
    return div_round((uint64_t)code * RRH_VREF_MV * 1000u, RRH_ADC_FS);
}

uint32_t rrh_board_imon_na(uint16_t trim_code, uint32_t imon_uv)
{
    const uint32_t vt = rrh_board_trim_uv(trim_code);
    if (imon_uv >= vt) {
        return 0u;
    }
    /* uV / ohm = uA; x 1000 = nA */
    return div_round((uint64_t)(vt - imon_uv) * 1000u, RRH_R105_OHM);
}

uint32_t rrh_board_led_mv(uint16_t code)
{
    return div_round((uint64_t)code * RRH_DAC_VREF_MV * (RRH_R2313_OHM + RRH_R2314_OHM), (uint64_t)RRH_DAC_CODES * RRH_R2314_OHM);
}

uint32_t rrh_board_pulser_fc(uint16_t code)
{
    /* Q = C x V: pF x mV = fC */
    return div_round((uint64_t)code * RRH_DAC_VREF_MV * RRH_CINJ_PF, RRH_DAC_CODES);
}

uint32_t rrh_board_baseline_uv(void)
{
    return div_round((uint64_t)RRH_DAC_VREF_MV * 1000u * RRH_R2311_OHM, RRH_R2310_OHM + RRH_R2311_OHM);
}

uint16_t rrh_board_threshold_code(uint32_t above_baseline_uv)
{
    const uint64_t uv = (uint64_t)rrh_board_baseline_uv() + above_baseline_uv;
    const uint32_t code = div_round(uv * RRH_DAC_CODES, (uint64_t)RRH_DAC_VREF_MV * 1000u);
    return (uint16_t)((code > (RRH_DAC_CODES - 1u)) ? (RRH_DAC_CODES - 1u) : code);
}

int32_t rrh_board_ntc_mc(uint16_t adc_code, rrh_ntc_t kind)
{
    const uint16_t *tab = k_ntc_tab[(kind == RRH_NTC_B3380) ? 1 : 0];
    if ((adc_code > 4000u) || (adc_code < 150u)) {
        return RRH_TEMP_NTC_INVALID; /* open or shorted sensor */
    }
    if ((adc_code > tab[0]) || (adc_code < tab[NTC_N - 1u])) {
        return RRH_TEMP_NTC_INVALID; /* outside -40 ... +125 degC */
    }
    for (uint32_t i = 0u; i < (NTC_N - 1u); i++) {
        if (adc_code >= tab[i + 1u]) {
            const int32_t span = (int32_t)tab[i] - (int32_t)tab[i + 1u];
            const int32_t into = (int32_t)tab[i] - (int32_t)adc_code;
            return NTC_T0_MC + ((int32_t)i * NTC_STEP_MC) + ((into * NTC_STEP_MC) / span);
        }
    }
    return RRH_TEMP_NTC_INVALID;
}

uint32_t rrh_board_hv_raw_mv(uint32_t r_raw_ohm)
{
    /* 1.2 V x (1 + (R2201 + R2202) / R) */
    return div_round((uint64_t)1200u * (r_raw_ohm + RRH_R2201_OHM + RRH_R2202_OHM), r_raw_ohm);
}

uint32_t rrh_board_ovp_trip_mv(uint32_t r_ovp_ohm)
{
    /* V(set) = VREF x R / (R2222 + R); bias = V(set) x (R2217 + R2218 + R2219) / R2219 */
    const uint64_t num = (uint64_t)RRH_VREF_MV * r_ovp_ohm * (RRH_R2217_OHM + RRH_R2218_OHM + RRH_R2219_OHM);
    return div_round(num, (uint64_t)(RRH_R2222_OHM + r_ovp_ohm) * RRH_R2219_OHM);
}

uint32_t rrh_board_fitted_ovp_trip_mv(void)
{
    return rrh_board_ovp_trip_mv(rrh_straps[RRH_SIPM_FAMILY].r_ovp_ohm);
}

uint32_t rrh_board_bias_limit_mv(void)
{
    return rrh_board_fitted_ovp_trip_mv() - RRH_BIAS_OVP_MARGIN_MV;
}

/* Compile-time consistency of the derived constants. */
_Static_assert(RRH_HV_FS_MV == 62500u, "bias full scale is 25 x 2.5 V");
_Static_assert(RRH_BIAS_RAMP_STEP_MV == (5000uLL * RRH_CONTROL_PERIOD_US / 1000000u), "bias ramp step = 5 V/s at HV_BUS per control period");
_Static_assert(RRH_IMON_SETTLE_US == (10u * RRH_R108_OHM * RRH_C2704_NF / 1000u), "10 time constants of R108 x C2704");
