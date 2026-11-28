# RR-HEAD-ACQ - open connections after routing (state on disk)

Source: `reports/summary.json` of the build of 2026-11-27 01:43-01:55 (second routing build: lane-0 block routes
replicated to lanes 1-3 as fixed pre-routes, Freerouting 2.6.0, one 540 s run; the automatic continue run crashed in
the tool, see README). Not waived; the board is **FAIL** on unconnected items.

* KiCad connectivity after zone fill: **1090 connections open on 212 nets** (`unconnected_after_fill`).
* Freerouting: 1475 connections to route after plane fan-out (836 plane vias) and 1947 locked pre-route items; 1099 left after the 540 s pass.
* Routed copper: 3014 tracks, 1400 vias, 8427 mm of track.
* DRC: 0 errors (waivers as listed in summary.json), 0 schematic-parity items.

Nets with open connections (212):

+3V3, +3V3A, +3V3_EVT, +3V3_HV, +5V6_A, +5V6_E, +5V_A, ALPHA_F0, ALPHA_F1, ALPHA_F2, ALPHA_F3, BIAS_IMON, BIAS_IMON_R, BIAS_VMON, BIAS_VMON_B, BK_CB, BK_EN, BK_FB, BK_SW, BOOT0, BUMP_ZONE_F_N, BUMP_ZONE_L_N, BUMP_ZONE_R_N, BUSY_F0, BUSY_F1, BUSY_F2, BUSY_F3, BUSY_R0, BUSY_R1, BUSY_R2, BUSY_R3, BZ_F_IN, BZ_L_IN, BZ_R_IN, CLR_F0_N, CLR_F1_N, CLR_F2_N, CLR_F3_N, CLR_R0_N, CLR_R1_N, CLR_R2_N, CLR_R3_N, DAC0_REF, DAC0_SDO, DAC1_REF, DAC1_SDO, DAC1_SPARE, DAC2_REF, DAC2_SDO, DAC3_REF, DAC3_SDO, DAC_CS0_N, DAC_CS1_N, DAC_CS2_N, DAC_CS3_N, DAC_MISO, DAC_MOSI, DAC_SCK, EF_DVDT, EF_FLT_N, EF_ILIM, EF_IMON, EF_MODE, EF_OVP, EF_RTN, EF_SHDN, EF_UVLO, FRAME, GND, HEAD_HTR_N, HEAD_HTR_P, HEAD_LOOP_OUT, HEAD_LOOP_RET, HEAD_PRES_ID, HEAD_PWR_N, HEAD_PWR_P, HTR_CQB, HTR_CUT, HTR_CUTOUT_OK, HTR_CX, HTR_EN, HTR_ENG, HTR_GATE, HTR_GD, HTR_PS, HTR_SENSE, HTR_SW, HV_B, HV_BFB, HV_BFBM, HV_BLD, HV_BUS, HV_CAP, HV_DRV, HV_E, HV_EN, HV_FB, HV_FBM, HV_G, HV_INH_N, HV_ISHORT, HV_MDIV, HV_MDM, HV_MIR, HV_MON2, HV_OFF, HV_OFFR, HV_ON, HV_OVP_SET, HV_PERMIT, HV_PG_DIV, HV_RAW, HV_RAWF, HV_SET, HV_SUM, HV_SW, I2C_SCL, IMON_CH, IMON_F0, LATCH_TEST, LED_AMPL, LED_FB, LID_G, LID_IN, LLD_F0, LLD_F1, LLD_F2, LLD_F3, LLD_R0, LLD_R1, LLD_R2, LLD_R3, LOOP_A, LOOP_B, LOOP_C, MON_ADC, MON_BUS, MON_DRV, MON_EN_1, MON_MUX_A0, MON_MUX_A1, MON_MUX_A2, MON_MUX_A3, MON_OUT, NRST, NTC_BOARD, NTC_HTR, NTC_SIPM0, NTC_SIPM1, NTC_SIPM2, NTC_SIPM3, PULSER_A0, PULSER_A1, PULSER_AMPL, PULSER_STROBE, RS485_RX, RS485_TX, SHLD_J1, SWDIO, SYNC_IN, THR_ALPHA_F0, THR_ALPHA_F1, THR_ALPHA_F2, THR_ALPHA_F3, THR_LLD_F0, THR_LLD_F1, THR_LLD_F2, THR_LLD_F3, THR_LLD_R0, THR_LLD_R1, THR_LLD_R2, THR_LLD_R3, THR_ULD_F0, THR_ULD_F1, THR_ULD_F2, THR_ULD_F3, THR_ULD_R0, THR_ULD_R1, THR_ULD_R2, THR_ULD_R3, TP_INH_F0_N, TP_INH_F1_N, TP_INH_F2_N, TP_INH_F3_N, TP_INH_R0_N, TP_INH_R1_N, TP_INH_R2_N, TRIM_DAC_F0, TRIM_DAC_F1, TRIM_DAC_F2, TRIM_DAC_F3, TRIM_DAC_R0, TRIM_DAC_R1, TRIM_DAC_R2, TRIM_DAC_R3, ULD_F0, ULD_F1, ULD_F2, ULD_F3, ULD_R0, ULD_R1, ULD_R2, ULD_R3, VBL, VBL_DIV, VIN_CM, VIN_DMP, VIN_EF, VIN_F, VIN_MON, VREF_ADC, V_LED

First 200 open connections as reported by the tool (net, both ends, board frame mm):

| net | end 1 | at | end 2 | at |
|---|---|---|---|---|
| HEAD_PWR_P | Pad 1 [HEAD_PWR_P] of L2001 on F.Cu | [95.9, 21.4] | Pad 1 [HEAD_PWR_P] of D2001 on F.Cu | [96.0, 14.35] |
| HEAD_PWR_P | Pad 1 [HEAD_PWR_P] of D2001 on F.Cu | [96.0, 14.35] | PTH pad 1 [HEAD_PWR_P] of J2001 | [97.34, 10.57] |
| HEAD_PWR_N | PTH pad 2 [HEAD_PWR_N] of J2001 | [94.34, 10.57] | Pad 2 [HEAD_PWR_N] of R2001 on F.Cu | [99.25, 16.075] |
| HEAD_PWR_N | Pad 2 [HEAD_PWR_N] of D2001 on F.Cu | [96.0, 18.65] | Pad 2 [HEAD_PWR_N] of R2001 on F.Cu | [99.25, 16.075] |
| HEAD_PWR_N | Pad 4 [HEAD_PWR_N] of L2001 on F.Cu | [97.1, 21.4] | Pad 2 [HEAD_PWR_N] of D2001 on F.Cu | [96.0, 18.65] |
| HEAD_HTR_P | Pad 1 [HEAD_HTR_P] of C2601 on F.Cu | [74.5, 24.725] | Pad 1 [HEAD_HTR_P] of D2601 on F.Cu | [58.35, 16.2] |
| HEAD_HTR_P | Pad 1 [HEAD_HTR_P] of R2610 on F.Cu | [77.81, 22.6] | Pad 1 [HEAD_HTR_P] of R2607 on F.Cu | [79.5, 20.075] |
| HEAD_HTR_P | Pad 1 [HEAD_HTR_P] of R2610 on F.Cu | [77.81, 22.6] | Pad 1 [HEAD_HTR_P] of C2601 on F.Cu | [74.5, 24.725] |
| HEAD_HTR_P | Pad 1 [HEAD_HTR_P] of R2601 on F.Cu | [81.037, 15.2] | Pad 1 [HEAD_HTR_P] of R2607 on F.Cu | [79.5, 20.075] |
| HEAD_HTR_P | Pad 1 [HEAD_HTR_P] of R2601 on F.Cu | [81.037, 15.2] | PTH pad 3 [HEAD_HTR_P] of J2001 | [91.34, 10.57] |
| HEAD_HTR_P | Pad 3 [HEAD_HTR_P] of U2601 on F.Cu | [83.863, 19.55] | Pad 1 [HEAD_HTR_P] of R2607 on F.Cu | [79.5, 20.075] |
| HEAD_HTR_N | Pad 2 [HEAD_HTR_N] of D2601 on F.Cu | [62.65, 16.2] | PTH pad 2 [HEAD_HTR_N] of J2601 | [65.58, 10.57] |
| HEAD_HTR_N | Pad 2 [HEAD_HTR_N] of C2601 on F.Cu | [74.5, 21.775] | Pad 2 [HEAD_HTR_N] of D2601 on F.Cu | [62.65, 16.2] |
| HEAD_HTR_N | PTH pad 4 [HEAD_HTR_N] of J2001 | [88.34, 10.57] | Pad 2 [HEAD_HTR_N] of C2601 on F.Cu | [74.5, 21.775] |
| HEAD_LOOP_OUT | PTH pad 5 [HEAD_LOOP_OUT] of J2001 | [85.34, 10.57] | Pad 1 [HEAD_LOOP_OUT] of J2002 on F.Cu | [156.375, 90.15] |
| HEAD_LOOP_RET | PTH pad 6 [HEAD_LOOP_RET] of J2001 | [82.34, 10.57] | Pad 2 [HEAD_LOOP_RET] of R2019 on F.Cu | [136.7, 75.375] |
| HEAD_PRES_ID | PTH pad 7 [HEAD_PRES_ID] of J2001 | [79.34, 10.57] | Pad 1 [HEAD_PRES_ID] of R2001 on F.Cu | [99.25, 14.425] |
| VIN_CM | Pad 2 [VIN_CM] of L2001 on F.Cu | [95.9, 24.6] | Pad 1 [VIN_CM] of R2002 on F.Cu | [97.9, 30.325] |
| VIN_CM | Pad 1 [VIN_CM] of U2001 on F.Cu | [96.275, 32.775] | Pad 2 [VIN_CM] of U2001 on F.Cu | [95.625, 32.775] |
| VIN_CM | Pad 1 [VIN_CM] of C2001 on F.Cu | [97.9, 32.025] | Pad 1 [VIN_CM] of U2001 on F.Cu | [96.275, 32.775] |
| VIN_CM | Pad 1 [VIN_CM] of R2002 on F.Cu | [97.9, 30.325] | Pad 1 [VIN_CM] of C2001 on F.Cu | [97.9, 32.025] |
| GND | Zone 'GND_outer' [GND] on F.Cu and B.Cu, priority 0 | [0.0, 0.0] | Pad 2 [GND] of U2601 on F.Cu | [83.863, 20.5] |
| GND | Zone 'GND_outer' [GND] on F.Cu and B.Cu, priority 0 | [0.0, 0.0] | Zone 'GND_outer' [GND] on F.Cu and B.Cu, priority 0 | [0.0, 0.0] |
| GND | Zone 'GND_outer' [GND] on F.Cu and B.Cu, priority 0 | [0.0, 0.0] | Pad 7 [GND] of U2201 on F.Cu | [108.25, 77.562] |
| GND | Zone 'GND_outer' [GND] on F.Cu and B.Cu, priority 0 | [0.0, 0.0] | Pad 5 [GND] of U2503 on F.Cu | [234.095, 12.525] |
| EF_UVLO | Pad 3 [EF_UVLO] of U2001 on F.Cu | [94.975, 32.775] | Pad 1 [EF_UVLO] of R2003 on F.Cu | [92.41, 34.3] |
| EF_UVLO | Pad 2 [EF_UVLO] of R2002 on F.Cu | [97.9, 28.675] | Pad 3 [EF_UVLO] of U2001 on F.Cu | [94.975, 32.775] |
| EF_OVP | Pad 2 [EF_OVP] of R2003 on F.Cu | [91.39, 34.3] | Pad 1 [EF_OVP] of R2004 on F.Cu | [90.4, 33.01] |
| EF_OVP | Pad 5 [EF_OVP] of U2001 on F.Cu | [93.675, 32.775] | Pad 2 [EF_OVP] of R2003 on F.Cu | [91.39, 34.3] |
| EF_MODE | Pad 1 [EF_MODE] of R2007 on F.Cu | [90.51, 30.8] | Pad 6 [EF_MODE] of U2001 on F.Cu | [93.025, 32.775] |
| EF_MODE | Pad 6 [EF_MODE] of U2001 on F.Cu | [93.025, 32.775] | Pad 1 [EF_MODE] of TP2003 on F.Cu | [91.8, 37.0] |
| EF_SHDN | Pad 1 [EF_SHDN] of TP2002 on F.Cu | [89.7, 34.7] | Pad 7 [EF_SHDN] of U2001 on F.Cu | [92.375, 32.775] |
| EF_RTN | Pad 2 [EF_RTN] of R2007 on F.Cu | [89.49, 30.8] | Pad 2 [EF_RTN] of R2005 on F.Cu | [90.4, 28.91] |
| EF_RTN | Pad 2 [EF_RTN] of R2006 on F.Cu | [89.49, 26.7] | Pad 2 [EF_RTN] of C2002 on F.Cu | [92.22, 25.7] |
| EF_RTN | Pad 2 [EF_RTN] of R2004 on F.Cu | [90.4, 31.99] | Pad 2 [EF_RTN] of R2007 on F.Cu | [89.49, 30.8] |
| EF_RTN | Pad 2 [EF_RTN] of R2005 on F.Cu | [90.4, 28.91] | Pad 2 [EF_RTN] of R2006 on F.Cu | [89.49, 26.7] |
| EF_RTN | Pad 8 [EF_RTN] of U2001 on F.Cu | [91.725, 32.775] | Pad 2 [EF_RTN] of R2004 on F.Cu | [90.4, 31.99] |
| EF_RTN | Pad 17 [EF_RTN] of U2001 on F.Cu | [94.0, 30.0] | Pad 8 [EF_RTN] of U2001 on F.Cu | [91.725, 32.775] |
| VIN_EF | Pad 1 [VIN_EF] of L2002 on F.Cu | [94.315, 37.0] | Pad 15 [VIN_EF] of U2001 on F.Cu | [95.625, 27.225] |
| VIN_EF | Pad 15 [VIN_EF] of U2001 on F.Cu | [95.625, 27.225] | Pad 1 [VIN_EF] of C2003 on F.Cu | [94.075, 22.5] |
| VIN_EF | Pad 16 [VIN_EF] of U2001 on F.Cu | [96.275, 27.225] | Pad 15 [VIN_EF] of U2001 on F.Cu | [95.625, 27.225] |
| EF_FLT_N | Track [EF_FLT_N] on In3.Cu, length 2.8406 mm | [102.009, 32.219] | Pad 14 [EF_FLT_N] of U2001 on F.Cu | [94.975, 27.225] |
| EF_IMON | Pad 1 [EF_IMON] of R2006 on F.Cu | [90.51, 26.7] | Pad 1 [EF_IMON] of TP2001 on F.Cu | [90.5, 24.9] |
| EF_IMON | Pad 10 [EF_IMON] of U2001 on F.Cu | [92.375, 27.225] | Pad 1 [EF_IMON] of R2006 on F.Cu | [90.51, 26.7] |
| EF_ILIM | Pad 1 [EF_ILIM] of R2005 on F.Cu | [90.4, 27.89] | Pad 11 [EF_ILIM] of U2001 on F.Cu | [93.025, 27.225] |
| EF_DVDT | Pad 1 [EF_DVDT] of C2002 on F.Cu | [93.18, 25.7] | Pad 12 [EF_DVDT] of U2001 on F.Cu | [93.675, 27.225] |
| +3V3 | Track [+3V3] on In2.Cu, length 9.7349 mm | [58.287, 19.75] | Pad 1 [+3V3] of R1017 on F.Cu | [30.24, 9.25] |
| +3V3 | Track [+3V3] on F.Cu, length 0.6500 mm | [88.613, 51.65] | Track [+3V3] on In2.Cu, length 16.1182 mm | [76.694, 70.835] |
| +3V3 | Pad 1 [+3V3] of FB2101 on F.Cu | [92.213, 58.5] | Track [+3V3] on F.Cu, length 0.6500 mm | [88.613, 51.65] |
| +3V3 | Pad 1 [+3V3] of R2227 on F.Cu | [120.76, 88.0] | Via [+3V3] on F.Cu - B.Cu | [138.79, 84.27] |
| +3V3 | Track [+3V3] on F.Cu, length 1.1875 mm | [179.137, 52.625] | Pad 1 [+3V3] of R1217 on F.Cu | [205.24, 9.25] |
| +3V3 | Pad 1 [+3V3] of R1217 on F.Cu | [205.24, 9.25] | Pad 8 [+3V3] of U2503 on F.Cu | [237.905, 12.525] |
| +3V3 | Pad 8 [+3V3] of U2503 on F.Cu | [237.905, 12.525] | Track [+3V3] on In2.Cu, length 3.1258 mm | [240.99, 29.72] |
| +3V3 | Track [+3V3] on In2.Cu, length 3.1258 mm | [240.99, 29.72] | Track [+3V3] on F.Cu, length 0.0636 mm | [254.4, 21.62] |
| +3V3 | Pad 1 [+3V3] of R1317 on F.Cu | [292.74, 9.25] | Track [+3V3] on F.Cu, length 1.9250 mm | [254.445, 21.575] |
| VIN_F | Pad 1 [VIN_F] of R2101 on F.Cu | [61.2, 50.39] | Pad 5 [VIN_F] of U2101 on F.Cu | [59.138, 52.0] |
| VIN_F | Pad 1 [VIN_F] of TP2101 on F.Cu | [62.7, 46.8] | Pad 1 [VIN_F] of C2102 on F.Cu | [62.975, 48.8] |
| VIN_F | Pad 1 [VIN_F] of C2102 on F.Cu | [62.975, 48.8] | Pad 1 [VIN_F] of C2101 on F.Cu | [65.2, 48.675] |
| VIN_F | Pad 1 [VIN_F] of C2102 on F.Cu | [62.975, 48.8] | Pad 1 [VIN_F] of R2101 on F.Cu | [61.2, 50.39] |
| VIN_F | Pad 1 [VIN_F] of C2101 on F.Cu | [65.2, 48.675] | Pad 1 [VIN_F] of C2004 on F.Cu | [91.975, 39.4] |
| VIN_F | Pad 1 [VIN_F] of C2004 on F.Cu | [91.975, 39.4] | Pad 2 [VIN_F] of L2002 on F.Cu | [96.685, 37.0] |
| VIN_F | Pad 2 [VIN_F] of L2002 on F.Cu | [96.685, 37.0] | Pad 1 [VIN_F] of C2005 on F.Cu | [99.3, 37.525] |
| VIN_F | Pad 1 [VIN_F] of C2005 on F.Cu | [99.3, 37.525] | Pad 1 [VIN_F] of R2010 on F.Cu | [99.09, 45.2] |
| VIN_DMP | Pad 2 [VIN_DMP] of C2005 on F.Cu | [99.3, 40.475] | Pad 1 [VIN_DMP] of R2009 on F.Cu | [99.912, 47.0] |
| VIN_MON | Pad 2 [VIN_MON] of R2010 on F.Cu | [100.11, 45.2] | Pad 1 [VIN_MON] of R2011 on F.Cu | [167.3, 68.11] |
| VIN_MON | Pad 1 [VIN_MON] of R2011 on F.Cu | [167.3, 68.11] | Pad 1 [VIN_MON] of C2006 on F.Cu | [169.2, 68.08] |
| VIN_MON | Pad 1 [VIN_MON] of C2006 on F.Cu | [169.2, 68.08] | Pad 33 [VIN_MON] of U2401 on F.Cu | [175.675, 75.0] |
| SHLD_J1 | Pad 1 [SHLD_J1] of TP2004 on F.Cu | [23.5, 70.5] | Pad 1 [SHLD_J1] of R2012 on F.Cu | [20.425, 68.5] |
| SHLD_J1 | Pad 1 [SHLD_J1] of C2007 on F.Cu | [25.275, 68.5] | Pad 1 [SHLD_J1] of TP2004 on F.Cu | [23.5, 70.5] |
| FRAME | Pad 2 [FRAME] of R2012 on F.Cu | [22.075, 68.5] | PTH pad 1 [FRAME] of H2807 | [6.432, 49.432] |
| FRAME | Pad 2 [FRAME] of C2007 on F.Cu | [23.725, 68.5] | Pad 2 [FRAME] of R2012 on F.Cu | [22.075, 68.5] |
| FRAME | Pad 2 [FRAME] of C2007 on F.Cu | [23.725, 68.5] | PTH pad 1 [FRAME] of H2804 | [74.068, 90.068] |
| FRAME | PTH pad 1 [FRAME] of H2804 | [75.5, 89.475] | PTH pad 1 [FRAME] of H2801 | [75.5, 32.025] |
| FRAME | PTH pad 1 [FRAME] of H2804 | [77.525, 91.5] | PTH pad 1 [FRAME] of H2805 | [160.975, 91.5] |
| FRAME | PTH pad 1 [FRAME] of H2805 | [163.0, 89.475] | PTH pad 1 [FRAME] of H2802 | [163.0, 6.525] |
| FRAME | PTH pad 1 [FRAME] of H2805 | [165.025, 91.5] | PTH pad 1 [FRAME] of H2806 | [248.475, 91.5] |
| FRAME | PTH pad 1 [FRAME] of H2803 | [250.5, 6.525] | Pad 2 [FRAME] of R2505 on F.Cu | [252.7, 66.175] |
| FRAME | Pad 2 [FRAME] of C2504 on F.Cu | [250.7, 70.375] | Pad 2 [FRAME] of R2505 on F.Cu | [252.7, 66.175] |
| FRAME | Pad 2 [FRAME] of C2504 on F.Cu | [250.7, 70.375] | PTH pad 1 [FRAME] of H2806 | [250.5, 89.475] |
| FRAME | Pad 1 [FRAME] of C2803 on F.Cu | [316.4, 23.125] | PTH pad 1 [FRAME] of H2803 | [252.525, 4.5] |
| FRAME | Pad 1 [FRAME] of R2802 on F.Cu | [318.075, 25.6] | Pad 1 [FRAME] of C2804 on F.Cu | [318.125, 27.3] |
| FRAME | Pad 1 [FRAME] of R2801 on F.Cu | [318.075, 23.9] | Pad 1 [FRAME] of R2802 on F.Cu | [318.075, 25.6] |
| FRAME | Pad 1 [FRAME] of R2801 on F.Cu | [318.075, 23.9] | Pad 1 [FRAME] of C2803 on F.Cu | [316.4, 23.125] |
| FRAME | Pad 1 [FRAME] of C2801 on F.Cu | [318.125, 22.2] | Pad 1 [FRAME] of R2801 on F.Cu | [318.075, 23.9] |
| FRAME | Pad 1 [FRAME] of C2801 on F.Cu | [318.125, 22.2] | Pad 1 [FRAME] of C2802 on F.Cu | [321.4, 23.125] |
| FRAME | PTH pad 1 [FRAME] of H2808 | [321.0, 45.975] | Pad 1 [FRAME] of C2804 on F.Cu | [318.125, 27.3] |
| LOOP_A | Pad 2 [LOOP_A] of J2002 on F.Cu | [155.125, 90.15] | Pad 1 [LOOP_A] of J2003 on F.Cu | [173.375, 90.15] |
| BZ_F_IN | Pad 1 [BZ_F_IN] of D2002 on F.Cu | [153.2, 87.95] | Pad 1 [BZ_F_IN] of R2013 on F.Cu | [155.1, 86.81] |
| BZ_F_IN | Pad 3 [BZ_F_IN] of J2002 on F.Cu | [153.875, 90.15] | Pad 1 [BZ_F_IN] of D2002 on F.Cu | [153.2, 87.95] |
| BUMP_ZONE_F_N | Pad 2 [BUMP_ZONE_F_N] of R2014 on F.Cu | [163.21, 68.0] | Track [BUMP_ZONE_F_N] on F.Cu, length 0.9617 mm | [165.0, 68.68] |
| BUMP_ZONE_F_N | Track [BUMP_ZONE_F_N] on F.Cu, length 1.1450 mm | [165.0, 69.825] | Pad 2 [BUMP_ZONE_F_N] of R2013 on F.Cu | [155.1, 85.79] |
| LOOP_B | Pad 1 [LOOP_B] of J2004 on F.Cu | [146.475, 90.15] | Pad 2 [LOOP_B] of J2003 on F.Cu | [172.125, 90.15] |
| BZ_L_IN | Pad 1 [BZ_L_IN] of R2015 on F.Cu | [169.2, 87.91] | Pad 1 [BZ_L_IN] of D2003 on F.Cu | [170.55, 87.6] |
| BZ_L_IN | Pad 1 [BZ_L_IN] of D2003 on F.Cu | [170.55, 87.6] | Pad 3 [BZ_L_IN] of J2003 on F.Cu | [170.875, 90.15] |
| BUMP_ZONE_L_N | Pad 1 [BUMP_ZONE_L_N] of C2009 on F.Cu | [161.08, 68.0] | Pad 2 [BUMP_ZONE_L_N] of R2016 on F.Cu | [165.7, 66.81] |
| BUMP_ZONE_L_N | Pad 2 [BUMP_ZONE_L_N] of R2016 on F.Cu | [165.7, 66.81] | Pad 8 [BUMP_ZONE_L_N] of U2401 on F.Cu | [165.5, 69.825] |
| BUMP_ZONE_L_N | Pad 2 [BUMP_ZONE_L_N] of R2015 on F.Cu | [169.2, 86.89] | Pad 8 [BUMP_ZONE_L_N] of U2401 on F.Cu | [165.5, 69.825] |
| LOOP_C | Pad 1 [LOOP_C] of R2019 on F.Cu | [136.7, 77.025] | Pad 2 [LOOP_C] of J2004 on F.Cu | [145.225, 90.15] |
| BZ_R_IN | Pad 1 [BZ_R_IN] of D2004 on F.Cu | [143.6, 87.95] | Pad 1 [BZ_R_IN] of R2017 on F.Cu | [147.0, 86.81] |
| BZ_R_IN | Pad 3 [BZ_R_IN] of J2004 on F.Cu | [143.975, 90.15] | Pad 1 [BZ_R_IN] of D2004 on F.Cu | [143.6, 87.95] |
| BUMP_ZONE_R_N | Pad 2 [BUMP_ZONE_R_N] of R2017 on F.Cu | [147.0, 85.79] | Pad 2 [BUMP_ZONE_R_N] of R2018 on F.Cu | [158.61, 71.3] |
| BUMP_ZONE_R_N | Pad 2 [BUMP_ZONE_R_N] of R2018 on F.Cu | [158.61, 71.3] | Pad 1 [BUMP_ZONE_R_N] of C2010 on F.Cu | [161.3, 66.78] |
| BUMP_ZONE_R_N | Pad 1 [BUMP_ZONE_R_N] of C2010 on F.Cu | [161.3, 66.78] | Pad 9 [BUMP_ZONE_R_N] of U2401 on F.Cu | [166.0, 69.825] |
| BK_EN | Pad 4 [BK_EN] of U2101 on F.Cu | [59.138, 51.05] | Pad 2 [BK_EN] of R2101 on F.Cu | [61.2, 51.41] |
| BK_FB | Pad 1 [BK_FB] of R2103 on F.Cu | [55.21, 50.9] | Pad 2 [BK_FB] of C2106 on F.Cu | [55.6, 49.58] |
| BK_FB | Pad 2 [BK_FB] of C2106 on F.Cu | [55.6, 49.58] | Pad 2 [BK_FB] of R2102 on F.Cu | [56.9, 49.61] |
| BK_FB | Pad 2 [BK_FB] of R2102 on F.Cu | [56.9, 49.61] | Pad 3 [BK_FB] of U2101 on F.Cu | [56.862, 51.05] |
| BK_CB | Pad 1 [BK_CB] of U2101 on F.Cu | [56.862, 52.95] | Pad 1 [BK_CB] of C2103 on F.Cu | [57.325, 54.7] |
| BK_SW | Pad 2 [BK_SW] of C2103 on F.Cu | [58.875, 54.7] | Pad 6 [BK_SW] of U2101 on F.Cu | [59.138, 52.95] |
| BK_SW | Pad 6 [BK_SW] of U2101 on F.Cu | [59.138, 52.95] | Pad 1 [BK_SW] of L2101 on F.Cu | [62.735, 52.0] |
| +5V6_A | Pad 1 [+5V6_A] of C2107 on F.Cu | [76.0, 53.75] | Pad 2 [+5V6_A] of L2102 on F.Cu | [72.0, 52.4] |
| +5V6_A | Pad 1 [+5V6_A] of U2102 on F.Cu | [76.362, 51.95] | Pad 1 [+5V6_A] of C2107 on F.Cu | [76.0, 53.75] |
| +5V6_A | Pad 3 [+5V6_A] of U2102 on F.Cu | [76.362, 50.05] | Pad 1 [+5V6_A] of U2102 on F.Cu | [76.362, 51.95] |
| +5V_A | Pad 7 [+5V_A] of U2301 on F.Cu | [146.25, 48.562] | Track [+5V_A] on In2.Cu, length 0.7090 mm | [145.975, 45.291] |
| +5V_A | Track [+5V_A] on In2.Cu, length 15.1820 mm | [219.821, 59.659] | Track [+5V_A] on In3.Cu, length 0.1451 mm | [209.225, 50.76] |
| +5V6_E | Pad 2 [+5V6_E] of L2103 on F.Cu | [84.0, 52.4] | Pad 1 [+5V6_E] of C2111 on F.Cu | [95.4, 48.65] |
| +5V6_E | Pad 1 [+5V6_E] of C2111 on F.Cu | [95.4, 48.65] | Pad 4 [+5V6_E] of U2104 on F.Cu | [96.387, 50.35] |
| +5V6_E | Pad 4 [+5V6_E] of U2104 on F.Cu | [96.387, 50.35] | Pad 6 [+5V6_E] of U2104 on F.Cu | [96.387, 51.65] |
| +3V3_EVT | Track [+3V3_EVT] on F.Cu, length 0.0632 mm | [37.205, 38.565] | Track [+3V3_EVT] on In2.Cu, length 2.5225 mm | [47.426, 35.787] |
| +3V3_EVT | Via [+3V3_EVT] on F.Cu - B.Cu | [42.137, 53.8] | Track [+3V3_EVT] on F.Cu, length 2.0500 mm | [62.95, 59.8] |
| +3V3_EVT | Track [+3V3_EVT] on F.Cu, length 0.3536 mm | [63.2, 59.55] | Track [+3V3_EVT] on In2.Cu, length 7.4536 mm | [99.761, 57.48] |
| +3V3_EVT | Track [+3V3_EVT] on F.Cu, length 0.8258 mm | [112.167, 38.059] | Track [+3V3_EVT] on In2.Cu, length 0.6025 mm | [115.79, 30.252] |
| +3V3_EVT | Pad 2 [+3V3_EVT] of D302 on F.Cu | [191.213, 32.65] | Track [+3V3_EVT] on In2.Cu, length 6.4763 mm | [199.443, 37.965] |
| +3V3_EVT | Pad 2 [+3V3_EVT] of D302 on F.Cu | [191.213, 32.65] | Track [+3V3_EVT] on In2.Cu, length 1.4557 mm | [135.999, 26.898] |
| +3V3_EVT | Track [+3V3_EVT] on F.Cu, length 1.7925 mm | [208.3, 72.98] | Via [+3V3_EVT] on F.Cu - B.Cu | [206.113, 63.6] |
| +3V3_EVT | Track [+3V3_EVT] on In2.Cu, length 0.8327 mm | [212.839, 39.109] | Pad 4 [+3V3_EVT] of U306 on F.Cu | [207.887, 34.85] |
| +3V3_EVT | Track [+3V3_EVT] on In2.Cu, length 0.3428 mm | [214.432, 39.351] | Track [+3V3_EVT] on F.Cu, length 0.0701 mm | [220.738, 37.516] |
| +3V3_EVT | Pad 16 [+3V3_EVT] of U2702 on F.Cu | [215.863, 76.275] | Track [+3V3_EVT] on F.Cu, length 0.0636 mm | [210.092, 72.98] |
| +3V3_EVT | Track [+3V3_EVT] on In2.Cu, length 8.3449 mm | [307.974, 46.098] | Track [+3V3_EVT] on In2.Cu, length 3.1496 mm | [299.75, 38.52] |
| +3V3_EVT | Pad 8 [+3V3_EVT] of U801 on F.Cu | [310.2, 19.75] | Track [+3V3_EVT] on In2.Cu, length 0.9570 mm | [310.977, 23.397] |
| +3V3A | Pad 1 [+3V3A] of C2113 on F.Cu | [65.425, 61.3] | Pad 1 [+3V3A] of C2114 on F.Cu | [65.62, 55.2] |
| +3V3A | Pad 1 [+3V3A] of C2114 on F.Cu | [65.62, 55.2] | Pad 2 [+3V3A] of FB2101 on F.Cu | [93.787, 58.5] |
| +3V3A | Pad 1 [+3V3A] of U2105 on F.Cu | [95.062, 63.95] | Pad 2 [+3V3A] of FB2101 on F.Cu | [93.787, 58.5] |
| +3V3A | Pad 1 [+3V3A] of U2105 on F.Cu | [95.062, 63.95] | Pad 37 [+3V3A] of U2401 on F.Cu | [175.675, 77.0] |
| +3V3A | Pad 37 [+3V3A] of U2401 on F.Cu | [175.675, 77.0] | Pad 1 [+3V3A] of C2407 on F.Cu | [177.42, 76.9] |
| +3V3A | Pad 1 [+3V3A] of C2407 on F.Cu | [177.42, 76.9] | Pad 2 [+3V3A] of D2701 on F.Cu | [198.062, 85.05] |
| VREF_ADC | Pad 1 [VREF_ADC] of C2115 on F.Cu | [61.8, 56.225] | Pad 1 [VREF_ADC] of C2116 on F.Cu | [68.7, 59.42] |
| VREF_ADC | Pad 1 [VREF_ADC] of C2115 on F.Cu | [61.8, 56.225] | Pad 1 [VREF_ADC] of R1016 on F.Cu | [41.3, 14.11] |
| VREF_ADC | Pad 1 [VREF_ADC] of TP2106 on F.Cu | [69.0, 62.3] | Pad 1 [VREF_ADC] of C2116 on F.Cu | [68.7, 59.42] |
| VREF_ADC | Pad 2 [VREF_ADC] of U2105 on F.Cu | [95.062, 62.05] | Pad 1 [VREF_ADC] of TP2106 on F.Cu | [69.0, 62.3] |
| VREF_ADC | Pad 2 [VREF_ADC] of U2105 on F.Cu | [95.062, 62.05] | Pad 1 [VREF_ADC] of R2613 on F.Cu | [88.25, 30.74] |
| VREF_ADC | Pad 2 [VREF_ADC] of U2105 on F.Cu | [95.062, 62.05] | Pad 1 [VREF_ADC] of R2222 on F.Cu | [136.39, 78.5] |
| VREF_ADC | Pad 1 [VREF_ADC] of R1116 on F.Cu | [128.8, 14.11] | Pad 1 [VREF_ADC] of R2613 on F.Cu | [88.25, 30.74] |
| VREF_ADC | Pad 4 [VREF_ADC] of U2204 on F.Cu | [140.137, 85.05] | Pad 1 [VREF_ADC] of R2222 on F.Cu | [136.39, 78.5] |
| VREF_ADC | Pad 4 [VREF_ADC] of U2204 on F.Cu | [140.137, 85.05] | Track [VREF_ADC] on F.Cu, length 0.8584 mm | [176.817, 86.14] |
| VREF_ADC | Pad 1 [VREF_ADC] of R1216 on F.Cu | [216.3, 14.11] | Track [VREF_ADC] on B.Cu, length 8.9694 mm | [178.023, 75.965] |
| VREF_ADC | Pad 1 [VREF_ADC] of R1216 on F.Cu | [216.3, 14.11] | Pad 1 [VREF_ADC] of R1316 on F.Cu | [303.8, 14.11] |
| HTR_SW | Pad 2 [HTR_SW] of C2604 on F.Cu | [72.23, 23.75] | Pad 1 [HTR_SW] of TP2601 on F.Cu | [69.3, 21.8] |
| HTR_SW | Pad 2 [HTR_SW] of C2604 on F.Cu | [72.23, 23.75] | Pad 2 [HTR_SW] of Q2601 on F.Cu | [74.76, 17.0] |
| HTR_SW | Pad 2 [HTR_SW] of Q2601 on F.Cu | [74.76, 17.0] | Pad 2 [HTR_SW] of R2607 on F.Cu | [79.5, 18.425] |
| HTR_SW | Pad 2 [HTR_SW] of Q2601 on F.Cu | [74.76, 17.0] | PTH pad 1 [HTR_SW] of J2601 | [68.58, 10.57] |
| HTR_CUT | Pad 1 [HTR_CUT] of R2608 on F.Cu | [61.61, 13.1] | PTH pad 3 [HTR_CUT] of J2601 | [62.58, 10.57] |
| NTC_HTR | Pad 1 [NTC_HTR] of D2604 on F.Cu | [53.0, 20.95] | PTH pad 4 [NTC_HTR] of J2601 | [59.58, 10.57] |
| NTC_HTR | PTH pad 4 [NTC_HTR] of J2601 | [59.58, 10.57] | Pad 1 [NTC_HTR] of C2606 on F.Cu | [65.3, 14.28] |
| NTC_HTR | Track [NTC_HTR] on In3.Cu, length 1.3957 mm | [89.119, 32.673] | Pad 1 [NTC_HTR] of C2606 on F.Cu | [65.3, 14.28] |
| HTR_PS | Pad 3 [HTR_PS] of D2602 on F.Cu | [64.938, 22.5] | Pad 3 [HTR_PS] of Q2601 on F.Cu | [68.46, 14.72] |
| HTR_PS | Pad 1 [HTR_PS] of R2603 on F.Cu | [70.0, 25.26] | Pad 3 [HTR_PS] of D2602 on F.Cu | [64.938, 22.5] |
| HTR_PS | Track [HTR_PS] on F.Cu, length 1.1667 mm | [86.137, 19.55] | Pad 1 [HTR_PS] of R2603 on F.Cu | [70.0, 25.26] |
| HTR_SENSE | Track [HTR_SENSE] on In2.Cu, length 0.0743 mm | [155.963, 79.375] | Pad 2 [HTR_SENSE] of R2602 on F.Cu | [99.4, 32.81] |
| HTR_GATE | Pad 1 [HTR_GATE] of Q2601 on F.Cu | [68.46, 19.28] | Pad 1 [HTR_GATE] of TP2602 on F.Cu | [71.6, 21.8] |
| HTR_GATE | Pad 1 [HTR_GATE] of R2604 on F.Cu | [68.51, 23.75] | Pad 1 [HTR_GATE] of D2602 on F.Cu | [63.062, 23.45] |
| HTR_GATE | Pad 2 [HTR_GATE] of R2603 on F.Cu | [70.0, 24.24] | Pad 1 [HTR_GATE] of R2604 on F.Cu | [68.51, 23.75] |
| HTR_GATE | Pad 1 [HTR_GATE] of C2604 on F.Cu | [71.27, 23.75] | Pad 2 [HTR_GATE] of R2603 on F.Cu | [70.0, 24.24] |
| HTR_GATE | Pad 1 [HTR_GATE] of TP2602 on F.Cu | [71.6, 21.8] | Pad 1 [HTR_GATE] of C2604 on F.Cu | [71.27, 23.75] |
| HTR_GD | Pad 3 [HTR_GD] of Q2602 on F.Cu | [62.938, 27.0] | Pad 2 [HTR_GD] of R2604 on F.Cu | [67.49, 23.75] |
| HTR_ENG | Pad 1 [HTR_ENG] of Q2602 on F.Cu | [61.062, 27.95] | Pad 2 [HTR_ENG] of R2605 on F.Cu | [79.29, 37.3] |
| HTR_EN | Track [HTR_EN] on In2.Cu, length 2.5131 mm | [158.61, 80.8] | Pad 1 [HTR_EN] of R2605 on F.Cu | [80.31, 37.3] |
| HTR_CQB | Pad 1 [HTR_CQB] of R2609 on F.Cu | [57.6, 28.61] | Pad 1 [HTR_CQB] of Q2603 on F.Cu | [56.062, 31.95] |
| HTR_CQB | Pad 2 [HTR_CQB] of R2608 on F.Cu | [60.59, 13.1] | Pad 1 [HTR_CQB] of R2609 on F.Cu | [57.6, 28.61] |
| HTR_CX | Pad 1 [HTR_CX] of R2611 on F.Cu | [67.99, 35.1] | Pad 3 [HTR_CX] of Q2603 on F.Cu | [57.938, 31.0] |
| HTR_CX | Pad 2 [HTR_CX] of R2610 on F.Cu | [76.79, 22.6] | Pad 1 [HTR_CX] of R2611 on F.Cu | [67.99, 35.1] |
| HTR_CUTOUT_OK | Pad 1 [HTR_CUTOUT_OK] of C2605 on F.Cu | [64.0, 38.38] | Pad 3 [HTR_CUTOUT_OK] of D2603 on F.Cu | [57.938, 36.0] |
| HTR_CUTOUT_OK | Pad 1 [HTR_CUTOUT_OK] of R2612 on F.Cu | [65.6, 39.01] | Pad 1 [HTR_CUTOUT_OK] of C2605 on F.Cu | [64.0, 38.38] |
| HTR_CUTOUT_OK | Pad 2 [HTR_CUTOUT_OK] of R2611 on F.Cu | [69.01, 35.1] | Pad 1 [HTR_CUTOUT_OK] of R2612 on F.Cu | [65.6, 39.01] |
| HTR_CUTOUT_OK | Pad 2 [HTR_CUTOUT_OK] of R2611 on F.Cu | [69.01, 35.1] | Pad 72 [HTR_CUTOUT_OK] of U2401 on F.Cu | [163.5, 85.175] |
| +3V3_HV | Pad 2 [+3V3_HV] of FB2201 on F.Cu | [104.0, 74.787] | Pad 10 [+3V3_HV] of U2201 on F.Cu | [109.438, 78.75] |
| +3V3_HV | Track [+3V3_HV] on F.Cu, length 0.1495 mm | [105.77, 83.399] | Pad 1 [+3V3_HV] of C2201 on F.Cu | [104.0, 82.3] |
| +3V3_HV | Pad 1 [+3V3_HV] of L2201 on F.Cu | [106.235, 86.5] | Track [+3V3_HV] on F.Cu, length 0.8484 mm | [106.37, 83.999] |
| +3V3_HV | Pad 10 [+3V3_HV] of U2201 on F.Cu | [109.438, 78.75] | Track [+3V3_HV] on F.Cu, length 0.5000 mm | [107.75, 80.438] |
| HV_ON | Pad 1 [HV_ON] of R2230 on F.Cu | [123.25, 78.26] | Pad 13 [HV_ON] of U2201 on F.Cu | [108.75, 80.438] |
| HV_ON | Pad 6 [HV_ON] of U2206 on F.Cu | [139.137, 74.7] | Pad 1 [HV_ON] of R2230 on F.Cu | [123.25, 78.26] |
| HV_BFB | Pad 2 [HV_BFB] of R2202 on F.Cu | [111.088, 71.0] | Pad 1 [HV_BFB] of R2203 on F.Cu | [111.25, 76.76] |
| HV_BFB | Pad 1 [HV_BFB] of R2203 on F.Cu | [111.25, 76.76] | Pad 12 [HV_BFB] of U2201 on F.Cu | [109.438, 79.75] |
| HV_ISHORT | Pad 1 [HV_ISHORT] of R2205 on F.Cu | [106.71, 81.9] | Pad 11 [HV_ISHORT] of U2201 on F.Cu | [109.438, 79.25] |
| HV_CAP | Pad 9 [HV_CAP] of U2201 on F.Cu | [109.438, 78.25] | Pad 1 [HV_CAP] of C2205 on F.Cu | [111.5, 79.775] |
| HV_SW | Pad 8 [HV_SW] of U2201 on F.Cu | [108.75, 77.562] | Pad 2 [HV_SW] of D2201 on F.Cu | [114.5, 83.4] |
| HV_SW | Pad 2 [HV_SW] of D2201 on F.Cu | [114.5, 83.4] | Pad 2 [HV_SW] of L2201 on F.Cu | [109.765, 86.5] |
| HV_RAWF | Pad 6 [HV_RAWF] of U2201 on F.Cu | [107.75, 77.562] | Pad 1 [HV_RAWF] of R2209 on F.Cu | [108.787, 73.5] |
| HV_RAWF | Pad 1 [HV_RAWF] of C2204 on F.Cu | [108.725, 71.0] | Pad 1 [HV_RAWF] of R2209 on F.Cu | [108.787, 73.5] |
| HV_RAWF | Pad 2 [HV_RAWF] of R2204 on F.Cu | [110.338, 82.5] | Pad 6 [HV_RAWF] of U2201 on F.Cu | [107.75, 77.562] |
| HV_MIR | Pad 5 [HV_MIR] of U2201 on F.Cu | [107.25, 77.562] | Pad 3 [HV_MIR] of Q2201 on F.Cu | [124.938, 81.0] |
| BIAS_IMON_R | Pad 1 [BIAS_IMON_R] of C2206 on F.Cu | [105.18, 80.5] | Pad 1 [BIAS_IMON_R] of R2206 on F.Cu | [105.21, 79.2] |
| BIAS_IMON_R | Pad 1 [BIAS_IMON_R] of R2206 on F.Cu | [105.21, 79.2] | Pad 4 [BIAS_IMON_R] of U2201 on F.Cu | [106.562, 78.25] |
| BIAS_IMON_R | Pad 4 [BIAS_IMON_R] of U2201 on F.Cu | [106.562, 78.25] | Pad 1 [BIAS_IMON_R] of R2207 on F.Cu | [117.49, 77.5] |
| HV_MON2 | Pad 1 [HV_MON2] of R2208 on F.Cu | [105.9, 75.31] | Pad 3 [HV_MON2] of U2201 on F.Cu | [106.562, 78.75] |
| HV_MON2 | Pad 3 [HV_MON2] of U2201 on F.Cu | [106.562, 78.75] | Pad 1 [HV_MON2] of TP2201 on F.Cu | [102.5, 79.7] |
| HV_RAW | Pad 1 [HV_RAW] of R2204 on F.Cu | [112.162, 82.5] | Pad 1 [HV_RAW] of D2201 on F.Cu | [114.5, 80.6] |
| HV_RAW | Pad 1 [HV_RAW] of C2203 on F.Cu | [113.025, 86.75] | Pad 1 [HV_RAW] of R2204 on F.Cu | [112.162, 82.5] |
| HV_RAW | Pad 1 [HV_RAW] of TP2203 on F.Cu | [114.4, 76.2] | Pad 1 [HV_RAW] of R2201 on F.Cu | [114.662, 74.0] |
| HV_RAW | Pad 1 [HV_RAW] of D2201 on F.Cu | [114.5, 80.6] | Pad 1 [HV_RAW] of TP2203 on F.Cu | [114.4, 76.2] |
