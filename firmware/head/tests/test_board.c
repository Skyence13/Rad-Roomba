/* Host tests of the board conversions (core/rrh_board.c): every transfer function is compared with
 * an independent floating-point evaluation of the circuit equation, and the numbers the electronics
 * budget quotes (head_afe_budget.md 5.1 / 5.2) are reproduced from the resistor values. The values
 * of the resistors themselves are checked against circuit.py by tools/check_circuit.py. */
#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "rrc_test.h"
#include "rrh_board.h"

static int near_u(uint32_t got, double want, double tol)
{
    return fabs((double)got - want) <= tol;
}

static void test_bias_set_point_law(void)
{
    /* HV_BUS = 25.0 x V(HV_SET), V(HV_SET) = code x 2.5 V / 4096: 15.26 mV per step, 62.5 V full scale */
    CHECK(RRH_HV_FS_MV == 62500u);
    CHECK(rrh_board_hv_code(0u) == 0u);
    CHECK(rrh_board_hv_code(62500u) == 4095u); /* clamped */
    CHECK(rrh_board_hv_code(100000u) == 4095u);
    for (uint32_t mv = 0u; mv <= 62400u; mv += 977u) {
        const uint16_t code = rrh_board_hv_code(mv);
        const double exact = (double)mv * 4096.0 / 62500.0;
        CHECK(fabs((double)code - exact) <= 0.5001);
        CHECK(near_u(rrh_board_hv_mv(code), (double)code * 62500.0 / 4096.0, 0.5001));
        CHECK(labs((long)rrh_board_hv_mv(code) - (long)mv) <= 8L); /* half a step (7.63 mV) + rounding */
    }
    /* the 0.4 firmware used 0 ... 60 V over 4095 codes: the same code now commands 62.5/60 x higher */
    CHECK(near_u(rrh_board_hv_mv(2048u), 31250.0, 0.6));
}

static void test_monitor_scales(void)
{
    /* BIAS_VMON = HV x 412 k / (4.99 M + 4.99 M + 412 k) -> 1:25.2233 */
    CHECK(near_u(rrh_board_bias_mv(1000u), 25223.3, 0.51));
    CHECK(near_u(rrh_board_bias_mv(2478u), 2478.0 * 25.2233009708738, 0.6));
    CHECK(near_u(rrh_board_bias_mv(1248u), 31478.0, 1.0)); /* about the 31.5 V trip */
    /* BIAS_IMON = 0.8 x I x 10 k = 8.0 mV per uA: 2.0 V = 250 uA */
    CHECK(rrh_board_bias_total_ua(2000u) == 250u);
    CHECK(rrh_board_bias_total_ua(8u) == 1u);
    CHECK(rrh_board_bias_total_ua(3000u) == 375u); /* ADC full scale */
    /* VIN_MON divider 1:6.6 -> 19.8 V at 3.0 V */
    CHECK(rrh_board_supply_mv(3000u) == 19800u);
    CHECK(rrh_board_supply_mv(1818u) == 11999u || rrh_board_supply_mv(1818u) == 12000u);
    /* the two bias dividers draw 24 + 6 uA at 60 V (budget 5.1) */
    CHECK(near_u(rrh_board_bias_divider_na(60000u), 24000.0 + 5773.0, 5.0));
    CHECK(near_u(rrh_board_adc_uv(4095u), 3000000.0, 1.0));
    CHECK(near_u(rrh_board_adc_uv(1u), 732.600732, 0.6)); /* 0.73 mV per LSB */
}

static void test_anode_current_monitor(void)
{
    /* I = (V_trim - V_TRIMDRV) / 4.99 k. 1 uA at trim code 2048 (1.25 V) is 4.99 mV below the trim. */
    CHECK(rrh_board_trim_uv(2048u) == 1250000u);
    CHECK(near_u(rrh_board_imon_na(2048u, 1250000u - 4990u), 1000.0, 1.0));
    CHECK(rrh_board_imon_na(2048u, 1250000u) == 0u);
    CHECK(rrh_board_imon_na(2048u, 1260000u) == 0u); /* negative (offset): 0, never wraps */
    CHECK(near_u(rrh_board_imon_na(4095u, 0u), 2499389.0 / 4.99, 2.0)); /* trim at 2.5 V, buffer at the rail: 0.5 mA */
    /* one ADC LSB is 0.7326 mV = 146.8 nA at the pin (budget: 0.15 uA per LSB) */
    CHECK(near_u(rrh_board_imon_na(2048u, 1250000u - 733u), 146.9, 0.5));
    /* soft limit of a channel is V_trim / 4.99 k: 0.2 mA at 1.0 V (the low end of the budget's 0.2 - 0.5 mA) */
    CHECK(near_u(rrh_board_imon_na(1638u, 0u), (1638.0 * 2500000.0 / 4096.0) / 4.99, 2.0));
}

static void test_dac_stage_scales(void)
{
    /* LED amplitude: V_LED = 2 x V(LED_AMPL): 0 ... 5.0 V */
    CHECK(rrh_board_led_mv(0u) == 0u);
    CHECK(near_u(rrh_board_led_mv(4095u), 4998.8, 0.6));
    CHECK(near_u(rrh_board_led_mv(2048u), 2500.0, 0.6));
    /* test pulser: Q = 100 pF x V: 250 pC full scale (budget 7), 0.61 fC x 100 per step */
    CHECK(near_u(rrh_board_pulser_fc(4095u), 249939.0, 1.0));
    CHECK(near_u(rrh_board_pulser_fc(1u), 61.0, 1.0));
    /* baseline 0.600 V and threshold codes above it */
    CHECK(near_u(rrh_board_baseline_uv(), 600304.0, 1.0));
    CHECK(rrh_board_threshold_code(0u) == 983u || rrh_board_threshold_code(0u) == 984u);
    CHECK(rrh_board_threshold_code(1900000u) >= 4094u); /* 1.90 V above baseline = DAC full scale */
    CHECK(rrh_board_threshold_code(8u * RRH_FAST_UV_PER_PE) == 1074u);
    CHECK(rrh_board_threshold_code(RRH_DEFAULT_ULD_PE * RRH_FAST_UV_PER_PE) == 2679u);
    CHECK(rrh_board_threshold_code(RRH_DEFAULT_ALPHA_UV) == 1033u);
}

static double ntc_code_exact(double temp_c, double beta)
{
    const double t = temp_c + 273.15;
    const double r = exp(beta * ((1.0 / t) - (1.0 / 298.15))); /* R / R25 */
    return 4095.0 * r / (1.0 + r);
}

static void test_ntc_tables(void)
{
    static const double beta[2] = {3435.0, 3380.0};
    for (int kind = 0; kind < 2; kind++) {
        double worst = 0.0;
        for (double tc = -39.0; tc <= 124.0; tc += 0.5) {
            const uint16_t code = (uint16_t)lround(ntc_code_exact(tc, beta[kind]));
            const int32_t mc = rrh_board_ntc_mc(code, (rrh_ntc_t)kind);
            CHECK(mc != RRH_TEMP_NTC_INVALID);
            if (mc != RRH_TEMP_NTC_INVALID) {
                /* a code step of 1 is 1/slope degrees; allow that plus the table's interpolation error */
                const double err = fabs((double)mc / 1000.0 - tc);
                if (err > worst) {
                    worst = err;
                }
            }
        }
        printf("    B%.0f: worst error over -39 ... +124 degC: %.3f degC\n", beta[kind], worst);
        CHECK(worst < 0.5); /* at -39 degC one ADC code is 0.4 degC wide; interpolation itself is < 0.05 degC */
    }
    CHECK(rrh_board_ntc_mc(2048u, RRH_NTC_B3435) == 25000);
    CHECK(rrh_board_ntc_mc(2048u, RRH_NTC_B3380) == 25000);
    CHECK(rrh_board_ntc_mc(10u, RRH_NTC_B3435) == RRH_TEMP_NTC_INVALID);   /* shorted */
    CHECK(rrh_board_ntc_mc(4095u, RRH_NTC_B3380) == RRH_TEMP_NTC_INVALID); /* open */
    /* the two betas differ by 0.2 degC at 0 degC and by more at the ends: the board NTC (RT2201) has its own table */
    CHECK(rrh_board_ntc_mc(2850u, RRH_NTC_B3435) != rrh_board_ntc_mc(2850u, RRH_NTC_B3380));
}

static void test_straps_reproduce_the_budget(void)
{
    /* budget 5.2: HV_RAW 37.1 / 49.1 / 52.7 / 65.1 V and OVP 31.5 / 42.8 / 47.5 / 60.6 V, computed here from the resistors */
    static const double raw[RRH_STRAP_COUNT] = {37116.0, 49110.0, 52663.0, 65081.0};
    static const double ovp[RRH_STRAP_COUNT] = {31548.0, 42770.0, 47540.0, 60596.0};
    for (uint32_t i = 0u; i < RRH_STRAP_COUNT; i++) {
        CHECK(near_u(rrh_board_hv_raw_mv(rrh_straps[i].r_raw_ohm), raw[i], 2.0));
        CHECK(near_u(rrh_board_ovp_trip_mv(rrh_straps[i].r_ovp_ohm), ovp[i], 2.0));
    }
    /* rev A is fitted for onsemi J/C: R2203 71.5 k and R2223 7.15 k, trip 31.5 V */
    CHECK((RRH_R2203_OHM == rrh_straps[0].r_raw_ohm) && (RRH_R2223_OHM == rrh_straps[0].r_ovp_ohm));
    CHECK(near_u(rrh_board_fitted_ovp_trip_mv(), 31548.0, 2.0));
    CHECK(near_u(rrh_board_bias_limit_mv(), 30548.0, 2.0));
    /* the 62.5 V DAC full scale is above every family's trip: the straps, not the DAC, protect the SiPM */
    for (uint32_t i = 0u; i < RRH_STRAP_COUNT; i++) {
        CHECK(rrh_board_ovp_trip_mv(rrh_straps[i].r_ovp_ohm) < RRH_HV_FS_MV);
    }
    /* the default set-point (30.0 V) and its code stay below the limit */
    CHECK(30000u < rrh_board_bias_limit_mv());
}

int main(void)
{
    RUN(test_bias_set_point_law);
    RUN(test_monitor_scales);
    RUN(test_anode_current_monitor);
    RUN(test_dac_stage_scales);
    RUN(test_ntc_tables);
    RUN(test_straps_reproduce_the_budget);
    return TEST_SUMMARY();
}
