# head_afe_calc.py output (regenerate: python3 electronics/analysis/head_afe_calc.py)

### T1 SiPM candidates (datasheet unless noted)

| device | Vbr V | dVbr/dT mV/C | Vov V | gain | PDE % | DCR typ MHz @25C | DCR max MHz | crosstalk % | Ct pF | recharge ns | Top C | source / note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| J60035@2.5V | 24.4 | 21.5 | 2.5 | 2.9e+06 | 38 | 1.84 | 5.52 | 8 | 4140 | 50 | -40..85 | onsemi MICROJ-SERIES/D Rev. 9 (Oct 2026), Tables 1-4 |
| J60035@6V | 24.4 | 21.5 | 6.0 | 6.3e+06 | 50 | 5.52 | 16.56 | 25 | 4140 | 50 | -40..85 | DCR max ASSUMED 3x typ |
| J30035@2.5V | 24.4 | 21.5 | 2.5 | 2.9e+06 | 38 | 0.47 | 1.41 | 8 | 1070 | 45 | -40..85 | onsemi MICROJ-SERIES/D Rev. 9 (Oct 2026), Tables 1-4 |
| S14160-6050HS | 38.0 | 34.0 | 2.7 | 2.5e+06 | 50 | 5.83 | 17.50 | 7 | 2000 | 50 | -40..85 | DCR calculated from dark current / (gain*e*(1+ct)); recharge 50 ns ASSUMED (not in datasheet) |
| S13360-6050PE | 53.0 | 54.0 | 3.0 | 1.7e+06 | 40 | 2.00 | 6.00 | 3 | 1280 | 50 | -20..60 | recharge 50 ns ASSUMED (not in datasheet) |
| NUV-MT 6x6 @12V | 32.5 | 30.0 | 12.0 | 7.3e+06 | 63 | 4.40 | 13.20 | 23 | 1550 | 55 | -20..60 | DCR max ASSUMED 3x typ |
| 4x J60035@2.5V | 24.4 | 21.5 | 2.5 | 2.9e+06 | 38 | 7.36 | 22.08 | 8 | 16560 | 50 | -40..85 | 4 devices in parallel (ASSUMED OEM option) |

### T2 Signal per photo-electron at each node (calculated; R_IN = 24.9 ohm, G1 = 11.0, G2 = 11.0, G3 = 5.01, pole-zero resistor matched to the recharge time)

| device | Q/p.e. pC | tau_in ns | R_PZ ohm | I pk uA/p.e. (beta) | node A uV/p.e. | preamp mV/p.e. | FAST mV/p.e. (beta) | t_peak ns | FWHM ns | resolving time ns | SLOW mV/p.e. (beta) | FAST mV/p.e. (alpha) | SLOW mV/p.e. (alpha) | SLOW t_peak us (alpha) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| J60035@2.5V | 0.465 | 103 | 227 | 8.0 | 56.8 | 0.62 | 2.76 | 66 | 126 | 155 | 0.437 | 0.766 | 0.275 | 0.62 |
| J60035@6V | 1.009 | 103 | 227 | 17.4 | 123.5 | 1.35 | 6.00 | 66 | 126 | 155 | 0.950 | 1.664 | 0.598 | 0.62 |
| J30035@2.5V | 0.465 | 27 | 205 | 8.8 | 120.1 | 1.30 | 6.68 | 48 | 62 | 69 | 0.494 | 1.175 | 0.285 | 0.50 |
| S14160-6050HS | 0.401 | 50 | 227 | 6.9 | 73.6 | 0.80 | 3.84 | 56 | 83 | 96 | 0.409 | 0.829 | 0.244 | 0.54 |
| S13360-6050PE | 0.272 | 32 | 227 | 4.7 | 61.4 | 0.67 | 3.32 | 50 | 67 | 76 | 0.285 | 0.620 | 0.166 | 0.52 |
| NUV-MT 6x6 @12V | 1.169 | 39 | 250 | 18.5 | 230.1 | 2.51 | 12.02 | 53 | 74 | 84 | 1.204 | 2.393 | 0.711 | 0.53 |
| 4x J60035@2.5V | 0.465 | 412 | 227 | 8.0 | 21.0 | 0.23 | 0.89 | 85 | 355 | 450 | 0.308 | 0.387 | 0.219 | 0.96 |

### T3 Amplitudes above baseline for the assumed photo-electron design range (calculated; linear values, 'CLIP' = exceeds the stage or clamp limit and saturates)

| device | pulse | p.e. | charge pC | I peak mA | node A | preamp out | FAST out | SLOW out |
|---|---|---|---|---|---|---|---|---|
| J60035@2.5V | single p.e. | 1 | 0.465 | 0.00799 | 5.68e-05 V | 0.000623 V | 0.00276 V | 0.000437 V |
| J60035@2.5V | beta min | 4 | 1.86 | 0.032 | 0.000227 V | 0.00249 V | 0.011 V | 0.00175 V |
| J60035@2.5V | beta typ | 15 | 6.97 | 0.12 | 0.000853 V | 0.00934 V | 0.0414 V | 0.00656 V |
| J60035@2.5V | beta max | 120 | 55.7 | 0.959 | 0.00682 V | 0.0747 V | 0.331 V | 0.0525 V |
| J60035@2.5V | alpha min | 150 | 69.7 | 0.161 | 0.00293 V | 0.0322 V | 0.115 V | 0.0413 V |
| J60035@2.5V | alpha typ | 1500 | 697 | 1.61 | 0.0293 V | 0.322 V | 1.15 V | 0.413 V |
| J60035@2.5V | alpha max | 15000 | 6.97e+03 | 16.1 | 0.293 V | 3.22 V | CLIP (11.5 V lin.) | CLIP (4.13 V lin.) |
| S14160-6050HS | single p.e. | 1 | 0.401 | 0.00689 | 7.36e-05 V | 0.000803 V | 0.00384 V | 0.000409 V |
| S14160-6050HS | beta min | 4 | 1.6 | 0.0275 | 0.000294 V | 0.00321 V | 0.0154 V | 0.00164 V |
| S14160-6050HS | beta typ | 15 | 6.01 | 0.103 | 0.0011 V | 0.012 V | 0.0576 V | 0.00614 V |
| S14160-6050HS | beta max | 120 | 48.1 | 0.826 | 0.00883 V | 0.0963 V | 0.461 V | 0.0491 V |
| S14160-6050HS | alpha min | 150 | 60.1 | 0.138 | 0.00303 V | 0.0333 V | 0.124 V | 0.0365 V |
| S14160-6050HS | alpha typ | 1500 | 601 | 1.38 | 0.0303 V | 0.333 V | 1.24 V | 0.365 V |
| S14160-6050HS | alpha max | 15000 | 6.01e+03 | 13.8 | 0.303 V | 3.33 V | CLIP (12.4 V lin.) | CLIP (3.65 V lin.) |
| S13360-6050PE | single p.e. | 1 | 0.272 | 0.00468 | 6.14e-05 V | 0.000667 V | 0.00332 V | 0.000285 V |
| S13360-6050PE | beta min | 4 | 1.09 | 0.0187 | 0.000246 V | 0.00267 V | 0.0133 V | 0.00114 V |
| S13360-6050PE | beta typ | 15 | 4.09 | 0.0702 | 0.000922 V | 0.01 V | 0.0498 V | 0.00428 V |
| S13360-6050PE | beta max | 120 | 32.7 | 0.562 | 0.00737 V | 0.0801 V | 0.398 V | 0.0342 V |
| S13360-6050PE | alpha min | 150 | 40.9 | 0.0941 | 0.0022 V | 0.0242 V | 0.093 V | 0.025 V |
| S13360-6050PE | alpha typ | 1500 | 409 | 0.941 | 0.022 V | 0.242 V | 0.93 V | 0.25 V |
| S13360-6050PE | alpha max | 15000 | 4.09e+03 | 9.41 | 0.22 V | 2.42 V | CLIP (9.3 V lin.) | 2.5 V |
| NUV-MT 6x6 @12V | single p.e. | 1 | 1.17 | 0.0185 | 0.00023 V | 0.00251 V | 0.012 V | 0.0012 V |
| NUV-MT 6x6 @12V | beta min | 4 | 4.68 | 0.0739 | 0.000921 V | 0.01 V | 0.0481 V | 0.00481 V |
| NUV-MT 6x6 @12V | beta typ | 15 | 17.5 | 0.277 | 0.00345 V | 0.0376 V | 0.18 V | 0.0181 V |
| NUV-MT 6x6 @12V | beta max | 120 | 140 | 2.22 | 0.0276 V | 0.301 V | 1.44 V | 0.144 V |
| NUV-MT 6x6 @12V | alpha min | 150 | 175 | 0.392 | 0.00902 V | 0.0991 V | 0.359 V | 0.107 V |
| NUV-MT 6x6 @12V | alpha typ | 1500 | 1.75e+03 | 3.92 | 0.0902 V | 0.991 V | CLIP (3.59 V lin.) | 1.07 V |
| NUV-MT 6x6 @12V | alpha max | 15000 | 1.75e+04 | 39.2 | 0.902 V | CLIP (9.91 V lin.) | CLIP (35.9 V lin.) | CLIP (10.7 V lin.) |
| 4x J60035@2.5V | single p.e. | 1 | 0.465 | 0.00799 | 2.1e-05 V | 0.000231 V | 0.000894 V | 0.000308 V |
| 4x J60035@2.5V | beta min | 4 | 1.86 | 0.032 | 8.4e-05 V | 0.000923 V | 0.00358 V | 0.00123 V |
| 4x J60035@2.5V | beta typ | 15 | 6.97 | 0.12 | 0.000315 V | 0.00346 V | 0.0134 V | 0.00462 V |
| 4x J60035@2.5V | beta max | 120 | 55.7 | 0.959 | 0.00252 V | 0.0277 V | 0.107 V | 0.037 V |
| 4x J60035@2.5V | alpha min | 150 | 69.7 | 0.161 | 0.00155 V | 0.017 V | 0.058 V | 0.0329 V |
| 4x J60035@2.5V | alpha typ | 1500 | 697 | 1.61 | 0.0155 V | 0.17 V | 0.58 V | 0.329 V |
| 4x J60035@2.5V | alpha max | 15000 | 6.97e+03 | 16.1 | 0.155 V | 1.7 V | CLIP (5.8 V lin.) | CLIP (3.29 V lin.) |

Linear limits above baseline: preamp 4.25 V, FAST/SLOW at the comparator (Schottky clamp) 3.00 V, highest threshold 2.50 V above ground = 1.90 V above baseline.

### T4 Threshold scale and DAC resolution (calculated)

| device | FAST mV/p.e. | DAC LSB p.e. (12 bit, 0.61 mV) | max BETA_ULD p.e. | comparator offset max p.e. (6.5 mV) | hysteresis p.e. (6 mV) | SLOW mV/p.e. (alpha) | max ALPHA threshold p.e. |
|---|---|---|---|---|---|---|---|
| J60035@2.5V | 2.76 | 0.221 | 688 | 2.35 | 2.17 | 0.275 | 6897 |
| J60035@6V | 6.00 | 0.102 | 317 | 1.08 | 1.00 | 0.598 | 3175 |
| J30035@2.5V | 6.68 | 0.091 | 285 | 0.97 | 0.90 | 0.285 | 6663 |
| S14160-6050HS | 3.84 | 0.159 | 494 | 1.69 | 1.56 | 0.244 | 7798 |
| S13360-6050PE | 3.32 | 0.184 | 573 | 1.96 | 1.81 | 0.166 | 11418 |
| NUV-MT 6x6 @12V | 12.02 | 0.051 | 158 | 0.54 | 0.50 | 0.711 | 2672 |
| 4x J60035@2.5V | 0.89 | 0.683 | 2125 | 7.27 | 6.71 | 0.219 | 8674 |

### T5 Electronic noise of the fast path (calculated)

| device | Ct pF | input-referred e_n nV/rtHz (amp + resistors) | FAST output noise mV rms | ENC p.e. rms |
|---|---|---|---|---|
| J60035@2.5V | 4140 | 1.99 | 0.54 | 0.197 |
| J60035@6V | 4140 | 1.99 | 0.54 | 0.091 |
| J30035@2.5V | 1070 | 1.99 | 0.55 | 0.082 |
| S14160-6050HS | 2000 | 1.99 | 0.55 | 0.142 |
| S13360-6050PE | 1280 | 1.99 | 0.55 | 0.165 |
| NUV-MT 6x6 @12V | 1550 | 1.99 | 0.55 | 0.046 |
| 4x J60035@2.5V | 16560 | 1.99 | 0.54 | 0.606 |

### T6 Lowest usable BETA_LLD from dark-count pile-up (calculated from datasheet DCR, crosstalk and the resolving time of T2; DCR(T) = DCR(25 C) * 2^((T-25)/8 C) assumed, range 7..10 C)

| device | DCR case | +25 C: LLD p.e. for <1/s (<0.1/s) | +10 C: LLD p.e. for <1/s (<0.1/s) | +0 C: LLD p.e. for <1/s (<0.1/s) | -20 C: LLD p.e. for <1/s (<0.1/s) |
|---|---|---|---|---|---|
| J60035@2.5V | typ | 11 (12)  [DCR 1.8e+06/s] | 9 (10)  [DCR 5e+05/s] | 8 (9)  [DCR 2.1e+05/s] | 7 (8)  [DCR 3.7e+04/s] |
| J60035@2.5V | max | 14 (16)  [DCR 5.5e+06/s] | 10 (12)  [DCR 1.5e+06/s] | 9 (10)  [DCR 6.3e+05/s] | 7 (9)  [DCR 1.1e+05/s] |
| J60035@6V | typ | 28 (32)  [DCR 5.5e+06/s] | 22 (26)  [DCR 1.5e+06/s] | 20 (24)  [DCR 6.3e+05/s] | 17 (20)  [DCR 1.1e+05/s] |
| J60035@6V | max | 37 (41)  [DCR 1.7e+07/s] | 27 (31)  [DCR 4.5e+06/s] | 23 (27)  [DCR 1.9e+06/s] | 19 (23)  [DCR 3.4e+05/s] |
| J30035@2.5V | typ | 8 (10)  [DCR 4.7e+05/s] | 7 (9)  [DCR 1.3e+05/s] | 7 (8)  [DCR 5.4e+04/s] | 6 (7)  [DCR 9.5e+03/s] |
| J30035@2.5V | max | 9 (11)  [DCR 1.4e+06/s] | 8 (9)  [DCR 3.9e+05/s] | 8 (9)  [DCR 1.6e+05/s] | 6 (8)  [DCR 2.9e+04/s] |
| S14160-6050HS | typ | 12 (14)  [DCR 5.8e+06/s] | 9 (11)  [DCR 1.6e+06/s] | 8 (10)  [DCR 6.7e+05/s] | 7 (8)  [DCR 1.2e+05/s] |
| S14160-6050HS | max | 17 (19)  [DCR 1.8e+07/s] | 12 (13)  [DCR 4.8e+06/s] | 10 (11)  [DCR 2e+06/s] | 8 (9)  [DCR 3.5e+05/s] |
| S13360-6050PE | typ | 8 (9)  [DCR 2e+06/s] | 6 (7)  [DCR 5.5e+05/s] | 6 (7)  [DCR 2.3e+05/s] | 5 (6)  [DCR 4.1e+04/s] |
| S13360-6050PE | max | 10 (11)  [DCR 6e+06/s] | 8 (8)  [DCR 1.6e+06/s] | 7 (7)  [DCR 6.9e+05/s] | 5 (6)  [DCR 1.2e+05/s] |
| NUV-MT 6x6 @12V | typ | 23 (26)  [DCR 4.4e+06/s] | 19 (23)  [DCR 1.2e+06/s] | 17 (21)  [DCR 5e+05/s] | 15 (18)  [DCR 8.9e+04/s] |
| NUV-MT 6x6 @12V | max | 28 (32)  [DCR 1.3e+07/s] | 22 (25)  [DCR 3.6e+06/s] | 20 (23)  [DCR 1.5e+06/s] | 16 (20)  [DCR 2.7e+05/s] |
| 4x J60035@2.5V | typ | 22 (24)  [DCR 7.4e+06/s] | 14 (15)  [DCR 2e+06/s] | 11 (12)  [DCR 8.4e+05/s] | 8 (9)  [DCR 1.5e+05/s] |
| 4x J60035@2.5V | max | 38 (40)  [DCR 2.2e+07/s] | 20 (22)  [DCR 6e+06/s] | 15 (16)  [DCR 2.5e+06/s] | 9 (11)  [DCR 4.5e+05/s] |

The table gives the integer n such that a threshold at (n - 0.5) p.e. has a dark trigger rate below the target.  Sensitivity to the assumed halving temperature (J60035@2.5V typ, -20 C): T_half 7 C -> 6 p.e., T_half 8 C -> 7 p.e., T_half 10 C -> 7 p.e.

Monte-Carlo check (J60035@2.5V, 25 C, 0.4 s of simulated dark pulses, real shaped pulse):

| n (threshold n-0.5 p.e.) | model rate 1/s | Monte-Carlo rate 1/s | MC / model |
|---|---|---|---|
| 3 | 1.18e+05 | 6.87e+04 | 0.58 |
| 4 | 2.6e+04 | 1.11e+04 | 0.43 |
| 5 | 5.43e+03 | 1.78e+03 | 0.33 |

### T7 Timing budget (calculated unless marked)

| item | value | evidence |
|---|---|---|
| SiPM recharge (J60035) | 50 ns | datasheet |
| Input pole R_IN*Ct (J60035, 24.9 ohm) | 103 ns | calculated |
| FAST peaking time / FWHM / resolving time | 66 / 126 / 155 ns | calculated |
| FAST undershoot after a beta pulse (fraction of peak) | -0.000 | calculated (pole-zero matched) |
| SLOW peaking time for a ZnS(Ag) alpha | 0.62 us | calculated (ZnS profile assumed) |
| Comparator propagation delay (100 mV / 5 mV overdrive) | 4.5 / 7.5 ns typ (12 ns max over T at 5 mV) | datasheet TLV3501 |
| Latch minimum clock pulse width (SN74LVC74A, 3.3 V) | 3.3 ns | datasheet |
| Smallest pulse/threshold ratio that still clocks the latch (TOT >= 4.3 ns) | 1.002 (i.e. effective threshold +0.2 %) | calculated |
| Timer capture resolution (144 MHz) | 6.94 ns | calculated |
| Acceptance window W | 4 us default | contract |
| Service interval | 10 us (100 kHz) | contract |
| Dead time per event: W + U(0, T_service) + ISR | mean 10.5 us, max 15.5 us | calculated; ISR allowance 1.5 us ASSUMED; measured per event in operation |

Non-paralysable live fraction with the mean dead time (calculated):

| true rate 1/s | live fraction | recorded rate 1/s | P(second event inside W) % | P(pile-up inside fast resolving time) % |
|---|---|---|---|---|
| 10 | 0.9999 | 10 | 0.00 | 0.000 |
| 100 | 0.9990 | 100 | 0.04 | 0.002 |
| 2000 | 0.9794 | 1959 | 0.80 | 0.031 |
| 10000 | 0.9050 | 9050 | 3.92 | 0.155 |
| 50000 | 0.6557 | 32787 | 18.13 | 0.773 |
| 100000 | 0.4878 | 48780 | 32.97 | 1.539 |

Rate at which the live fraction reaches 0.5: 9.52e+04 /s; hard ceiling 1 event per service tick = 100000 /s.

### T8 Bias set-point, trim and temperature compensation (calculated)

HV = 25.0 x V(HV_SET): full scale 62.5 V, 12-bit step 15.26 mV (16-bit DAC80508 drop-in: 0.95 mV). Anode trim step 0.61 mV, range 0.10..2.50 V usable.

| device | Vbias 25 C | Vbias -25 C | Vbias +40 C | max incl. Vbr tolerance | gain change %/C uncompensated | gain step per trim LSB % | IR drop in 1.1 k filter mV (dark typ) | = gain error % if uncorrected | inside 20-60 V |
|---|---|---|---|---|---|---|---|---|---|
| J60035@2.5V | 26.95 | 25.88 | 27.27 | 27.52 | 0.86 | 0.024 | 1.0 | 0.04 | yes |
| J60035@6V | 30.45 | 29.38 | 30.77 | 31.02 | 0.36 | 0.010 | 8.2 | 0.14 | yes |
| J30035@2.5V | 26.95 | 25.88 | 27.27 | 27.52 | 0.86 | 0.024 | 0.3 | 0.01 | yes |
| S14160-6050HS | 40.70 | 39.00 | 41.21 | 41.21 | 1.26 | 0.023 | 2.8 | 0.10 | yes |
| S13360-6050PE | 56.00 | 53.30 | 56.81 | 61.81 | 1.80 | 0.020 | n/a | n/a | NO (>60 V) |
| NUV-MT 6x6 @12V | 44.50 | 43.00 | 44.95 | 44.95 | 0.25 | 0.005 | 9.5 | 0.08 | yes |
| 4x J60035@2.5V | 26.95 | 25.88 | 27.27 | 27.52 | 0.86 | 0.024 | 4.0 | 0.16 | yes |

### T9 Heater (calculated; element 4.8 ohm = 30 W at 12.0 V)

| bus V at the element | I A | P W | duty % for 16 W (-20 C) | duty % for 19 W (-25 C) |
|---|---|---|---|---|
| 10.0 | 2.08 | 20.8 | 77 | 91 |
| 12.0 | 2.50 | 30.0 | 53 | 63 |
| 12.8 | 2.67 | 34.1 | 47 | 56 |
| 14.6 | 3.04 | 44.4 | 36 | 43 |
| 15.0 | 3.12 | 46.9 | 34 | 41 |

Slew-limited edge 1.2 ms: dI/dt = 2604 A/s; with an assumed 10 nH mutual inductance to a pigtail loop the induced voltage is 26.0 uV for 1.2 ms (an un-slewed 100 ns edge would give 0.31 V).
Edge spectrum corner 292 Hz; fast CR (22 ns) passes 4.0e-05 of it -> 4.60e-05 p.e. equivalent at the FAST output (J60035).  Switching energy per edge 0.5*V*I*t = 28 mJ at 15 V.

### T10 Power budget (calculated from datasheet typical/maximum quiescent currents; MCU current assumed)

| rail (from +5V6 pre-regulator) | loads mA typ/max | I typ mA | I max mA | LDO loss typ mW | LDO loss max mW |
|---|---|---|---|---|---|
| +5V_A (TPS7A2050) | 16 x OPA838 (preamp, fast) 15/17; 5 x OPA836 (slow x4, monitor) 5/7; 4 x TLV9062 trim buffers + 2 misc op-amps 7/9; 4 x DAC60508 10/16; 5 x TMUX1108, references, dividers 2/4 | 39 | 53 | 24 | 33 |
| +3V3_EVT (TLV76733) | 20 comparators TLV350x 64/100; 20 latches + OR gates, decoders 3/8 | 67 | 108 | 156 | 252 |
| +3V3 (TLV76733) | STM32G474 at 144 MHz 45/70; TPS61391 boost input (HV 66 V x 0.6 mA / 60 %) 20/45; ISO1430 logic side, TMP117 x2, EEPROM, TCXO, LEDs 12/20; REF3030, TLV7021 x2, misc 1/3 | 78 | 138 | 182 | 322 |

Pre-regulator output 5.63 V: 184 mA typ / 299 mA max -> input power 1.20 W typ (buck 88 %) / 2.10 W max (buck 82 %), including eFuse and input-filter loss.  Input current at 12.8 V: 93 mA typ; at 9.0 V and maximum load: 234 mA.  Bus side of the isolator (from BUS_5V on J2, not in this total): ~60 mA while transmitting into 60 ohm, <10 mA idle (datasheet class, UNVERIFIED exact figure).
Against the allocation: 1.20 W typ / 2.10 W max vs 5 W target and 10 W limit.

### T11 Charge-injection pulser (calculated)

| device | Q per p.e. pC | full-scale injection p.e. (100 pF x 2.5 V = 250 pC) | step per DAC LSB p.e. |
|---|---|---|---|
| J60035@2.5V | 0.465 | 538 | 0.13 |
| S14160-6050HS | 0.401 | 624 | 0.15 |
| S13360-6050PE | 0.272 | 918 | 0.22 |
| NUV-MT 6x6 @12V | 1.169 | 214 | 0.05 |

wrote head_afe_pulses.png
