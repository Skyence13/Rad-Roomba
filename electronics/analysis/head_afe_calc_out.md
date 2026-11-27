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

### T2 Signal per photo-electron at each node (calculated; R_IN = 10.0 ohm, G1 = 21.0, G2 = 21.0, G3 = 5.01, pole-zero resistor matched to the recharge time)

| device | Q/p.e. pC | tau_in ns | R_PZ ohm | I pk uA/p.e. (beta) | node A uV/p.e. | preamp mV/p.e. | FAST mV/p.e. (beta) | t_peak ns | FWHM ns | resolving time ns | SLOW mV/p.e. (beta) | FAST mV/p.e. (alpha) | SLOW mV/p.e. (alpha) | SLOW t_peak us (alpha) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| J60035@2.5V | 0.465 | 41 | 227 | 8.0 | 37.5 | 0.76 | 6.92 | 59 | 80 | 90 | 0.369 | 1.464 | 0.218 | 0.53 |
| J60035@6V | 1.009 | 41 | 227 | 17.4 | 81.4 | 1.65 | 15.04 | 59 | 80 | 90 | 0.801 | 3.181 | 0.473 | 0.53 |
| J30035@2.5V | 0.465 | 11 | 205 | 8.8 | 65.6 | 1.21 | 12.20 | 43 | 51 | 55 | 0.383 | 1.850 | 0.219 | 0.49 |
| S14160-6050HS | 0.401 | 20 | 227 | 6.9 | 43.4 | 0.85 | 8.17 | 50 | 61 | 66 | 0.325 | 1.416 | 0.188 | 0.51 |
| S13360-6050PE | 0.272 | 13 | 227 | 4.7 | 34.0 | 0.64 | 6.33 | 45 | 54 | 58 | 0.222 | 0.996 | 0.128 | 0.50 |
| NUV-MT 6x6 @12V | 1.169 | 16 | 250 | 18.5 | 129.1 | 2.49 | 23.98 | 47 | 57 | 61 | 0.941 | 3.938 | 0.548 | 0.51 |
| 4x J60035@2.5V | 0.465 | 166 | 227 | 8.0 | 16.7 | 0.35 | 2.78 | 79 | 176 | 217 | 0.307 | 0.919 | 0.202 | 0.71 |

### T3 Amplitudes above baseline for the assumed photo-electron design range (calculated; linear values, 'CLIP' = exceeds the stage or clamp limit and saturates)

| device | pulse | p.e. | charge pC | I peak mA | node A | preamp out | FAST out | SLOW out |
|---|---|---|---|---|---|---|---|---|
| J60035@2.5V | single p.e. | 1 | 0.465 | 0.00799 | 3.75e-05 V | 0.000759 V | 0.00692 V | 0.000369 V |
| J60035@2.5V | beta min | 4 | 1.86 | 0.032 | 0.00015 V | 0.00304 V | 0.0277 V | 0.00148 V |
| J60035@2.5V | beta typ | 15 | 6.97 | 0.12 | 0.000562 V | 0.0114 V | 0.104 V | 0.00553 V |
| J60035@2.5V | beta max | 120 | 55.7 | 0.959 | 0.0045 V | 0.0911 V | 0.831 V | 0.0443 V |
| J60035@2.5V | alpha min | 150 | 69.7 | 0.161 | 0.00146 V | 0.0305 V | 0.22 V | 0.0326 V |
| J60035@2.5V | alpha typ | 1500 | 697 | 1.61 | 0.0146 V | 0.305 V | 2.2 V | 0.326 V |
| J60035@2.5V | alpha max | 15000 | 6.97e+03 | 16.1 | 0.146 V | 3.05 V | CLIP (22 V lin.) | CLIP (3.26 V lin.) |
| S14160-6050HS | single p.e. | 1 | 0.401 | 0.00689 | 4.34e-05 V | 0.000848 V | 0.00817 V | 0.000325 V |
| S14160-6050HS | beta min | 4 | 1.6 | 0.0275 | 0.000174 V | 0.00339 V | 0.0327 V | 0.0013 V |
| S14160-6050HS | beta typ | 15 | 6.01 | 0.103 | 0.000651 V | 0.0127 V | 0.123 V | 0.00488 V |
| S14160-6050HS | beta max | 120 | 48.1 | 0.826 | 0.00521 V | 0.102 V | 0.981 V | 0.039 V |
| S14160-6050HS | alpha min | 150 | 60.1 | 0.138 | 0.00135 V | 0.0282 V | 0.212 V | 0.0282 V |
| S14160-6050HS | alpha typ | 1500 | 601 | 1.38 | 0.0135 V | 0.282 V | 2.12 V | 0.282 V |
| S14160-6050HS | alpha max | 15000 | 6.01e+03 | 13.8 | 0.135 V | 2.82 V | CLIP (21.2 V lin.) | 2.82 V |
| S13360-6050PE | single p.e. | 1 | 0.272 | 0.00468 | 3.4e-05 V | 0.000642 V | 0.00633 V | 0.000222 V |
| S13360-6050PE | beta min | 4 | 1.09 | 0.0187 | 0.000136 V | 0.00257 V | 0.0253 V | 0.000887 V |
| S13360-6050PE | beta typ | 15 | 4.09 | 0.0702 | 0.000509 V | 0.00963 V | 0.095 V | 0.00333 V |
| S13360-6050PE | beta max | 120 | 32.7 | 0.562 | 0.00408 V | 0.077 V | 0.76 V | 0.0266 V |
| S13360-6050PE | alpha min | 150 | 40.9 | 0.0941 | 0.000932 V | 0.0195 V | 0.149 V | 0.0192 V |
| S13360-6050PE | alpha typ | 1500 | 409 | 0.941 | 0.00932 V | 0.195 V | 1.49 V | 0.192 V |
| S13360-6050PE | alpha max | 15000 | 4.09e+03 | 9.41 | 0.0932 V | 1.95 V | CLIP (14.9 V lin.) | 1.92 V |
| NUV-MT 6x6 @12V | single p.e. | 1 | 1.17 | 0.0185 | 0.000129 V | 0.00249 V | 0.024 V | 0.000941 V |
| NUV-MT 6x6 @12V | beta min | 4 | 4.68 | 0.0739 | 0.000516 V | 0.00997 V | 0.0959 V | 0.00377 V |
| NUV-MT 6x6 @12V | beta typ | 15 | 17.5 | 0.277 | 0.00194 V | 0.0374 V | 0.36 V | 0.0141 V |
| NUV-MT 6x6 @12V | beta max | 120 | 140 | 2.22 | 0.0155 V | 0.299 V | 2.88 V | 0.113 V |
| NUV-MT 6x6 @12V | alpha min | 150 | 175 | 0.392 | 0.00387 V | 0.0809 V | 0.591 V | 0.0822 V |
| NUV-MT 6x6 @12V | alpha typ | 1500 | 1.75e+03 | 3.92 | 0.0387 V | 0.809 V | CLIP (5.91 V lin.) | 0.822 V |
| NUV-MT 6x6 @12V | alpha max | 15000 | 1.75e+04 | 39.2 | 0.387 V | CLIP (8.09 V lin.) | CLIP (59.1 V lin.) | CLIP (8.22 V lin.) |
| 4x J60035@2.5V | single p.e. | 1 | 0.465 | 0.00799 | 1.67e-05 V | 0.000349 V | 0.00278 V | 0.000307 V |
| 4x J60035@2.5V | beta min | 4 | 1.86 | 0.032 | 6.69e-05 V | 0.0014 V | 0.0111 V | 0.00123 V |
| 4x J60035@2.5V | beta typ | 15 | 6.97 | 0.12 | 0.000251 V | 0.00523 V | 0.0417 V | 0.00461 V |
| 4x J60035@2.5V | beta max | 120 | 55.7 | 0.959 | 0.00201 V | 0.0419 V | 0.334 V | 0.0369 V |
| 4x J60035@2.5V | alpha min | 150 | 69.7 | 0.161 | 0.000986 V | 0.0207 V | 0.138 V | 0.0304 V |
| 4x J60035@2.5V | alpha typ | 1500 | 697 | 1.61 | 0.00986 V | 0.207 V | 1.38 V | 0.304 V |
| 4x J60035@2.5V | alpha max | 15000 | 6.97e+03 | 16.1 | 0.0986 V | 2.07 V | CLIP (13.8 V lin.) | CLIP (3.04 V lin.) |

Linear limits above baseline: preamp 4.25 V, FAST/SLOW at the comparator (Schottky clamp) 3.00 V, highest threshold 2.50 V above ground = 1.90 V above baseline.

### T4 Threshold scale and DAC resolution (calculated)

| device | FAST mV/p.e. | DAC LSB p.e. (12 bit, 0.61 mV) | max BETA_ULD p.e. | comparator offset max p.e. (6.5 mV) | hysteresis p.e. (6 mV) | SLOW mV/p.e. (alpha) | max ALPHA threshold p.e. |
|---|---|---|---|---|---|---|---|
| J60035@2.5V | 6.92 | 0.088 | 274 | 0.94 | 0.87 | 0.218 | 8733 |
| J60035@6V | 15.04 | 0.041 | 126 | 0.43 | 0.40 | 0.473 | 4020 |
| J30035@2.5V | 12.20 | 0.050 | 156 | 0.53 | 0.49 | 0.219 | 8663 |
| S14160-6050HS | 8.17 | 0.075 | 232 | 0.80 | 0.73 | 0.188 | 10093 |
| S13360-6050PE | 6.33 | 0.096 | 300 | 1.03 | 0.95 | 0.128 | 14834 |
| NUV-MT 6x6 @12V | 23.98 | 0.025 | 79 | 0.27 | 0.25 | 0.548 | 3467 |
| 4x J60035@2.5V | 2.78 | 0.220 | 684 | 2.34 | 2.16 | 0.202 | 9384 |

### T5 Electronic noise of the fast path (calculated)

| device | Ct pF | input-referred e_n nV/rtHz (amp + resistors) | FAST output noise mV rms | ENC p.e. rms |
|---|---|---|---|---|
| J60035@2.5V | 4140 | 2.00 | 1.70 | 0.245 |
| J60035@6V | 4140 | 2.00 | 1.70 | 0.113 |
| J30035@2.5V | 1070 | 2.00 | 1.72 | 0.141 |
| S14160-6050HS | 2000 | 2.00 | 1.70 | 0.209 |
| S13360-6050PE | 1280 | 2.00 | 1.71 | 0.270 |
| NUV-MT 6x6 @12V | 1550 | 2.00 | 1.71 | 0.071 |
| 4x J60035@2.5V | 16560 | 2.00 | 1.69 | 0.609 |

### T6 Lowest usable BETA_LLD from dark-count pile-up (calculated from datasheet DCR, crosstalk and the resolving time of T2 x 0.50 (factor fitted to the Monte-Carlo below); DCR(T) = DCR(25 C) * 2^((T-25)/8 C) assumed, range 7..10 C)

| device | DCR case | +25 C: LLD p.e. for <1/s (<0.1/s) [<0.05/s] | +10 C: LLD p.e. for <1/s (<0.1/s) [<0.05/s] | +0 C: LLD p.e. for <1/s (<0.1/s) [<0.05/s] | -20 C: LLD p.e. for <1/s (<0.1/s) [<0.05/s] |
|---|---|---|---|---|---|
| J60035@2.5V | typ | 10 (11) [11]  DCR 1.8e+06/s | 8 (10) [10]  DCR 5e+05/s | 8 (9) [9]  DCR 2.1e+05/s | 7 (8) [8]  DCR 3.7e+04/s |
| J60035@2.5V | max | 11 (13) [13]  DCR 5.5e+06/s | 9 (11) [11]  DCR 1.5e+06/s | 8 (10) [10]  DCR 6.3e+05/s | 7 (9) [9]  DCR 1.1e+05/s |
| J60035@6V | typ | 25 (29) [30]  DCR 5.5e+06/s | 21 (25) [26]  DCR 1.5e+06/s | 20 (23) [25]  DCR 6.3e+05/s | 17 (20) [21]  DCR 1.1e+05/s |
| J60035@6V | max | 29 (33) [34]  DCR 1.7e+07/s | 24 (28) [29]  DCR 4.5e+06/s | 22 (26) [27]  DCR 1.9e+06/s | 18 (22) [23]  DCR 3.4e+05/s |
| J30035@2.5V | typ | 8 (9) [10]  DCR 4.7e+05/s | 7 (9) [9]  DCR 1.3e+05/s | 7 (8) [9]  DCR 5.4e+04/s | 6 (7) [8]  DCR 9.5e+03/s |
| J30035@2.5V | max | 9 (10) [11]  DCR 1.4e+06/s | 8 (9) [10]  DCR 3.9e+05/s | 7 (9) [9]  DCR 1.6e+05/s | 6 (8) [8]  DCR 2.9e+04/s |
| S14160-6050HS | typ | 10 (12) [12]  DCR 5.8e+06/s | 9 (10) [10]  DCR 1.6e+06/s | 8 (9) [10]  DCR 6.7e+05/s | 7 (8) [8]  DCR 1.2e+05/s |
| S14160-6050HS | max | 13 (15) [15]  DCR 1.8e+07/s | 10 (11) [12]  DCR 4.8e+06/s | 9 (10) [11]  DCR 2e+06/s | 8 (9) [9]  DCR 3.5e+05/s |
| S13360-6050PE | typ | 7 (8) [8]  DCR 2e+06/s | 6 (7) [7]  DCR 5.5e+05/s | 6 (6) [7]  DCR 2.3e+05/s | 5 (6) [6]  DCR 4.1e+04/s |
| S13360-6050PE | max | 8 (9) [10]  DCR 6e+06/s | 7 (8) [8]  DCR 1.6e+06/s | 6 (7) [7]  DCR 6.9e+05/s | 5 (6) [6]  DCR 1.2e+05/s |
| NUV-MT 6x6 @12V | typ | 21 (25) [26]  DCR 4.4e+06/s | 19 (22) [23]  DCR 1.2e+06/s | 17 (21) [22]  DCR 5e+05/s | 15 (18) [19]  DCR 8.9e+04/s |
| NUV-MT 6x6 @12V | max | 25 (28) [29]  DCR 1.3e+07/s | 21 (24) [25]  DCR 3.6e+06/s | 19 (23) [24]  DCR 1.5e+06/s | 16 (20) [21]  DCR 2.7e+05/s |
| 4x J60035@2.5V | typ | 14 (16) [16]  DCR 7.4e+06/s | 10 (12) [12]  DCR 2e+06/s | 9 (11) [11]  DCR 8.4e+05/s | 8 (9) [9]  DCR 1.5e+05/s |
| 4x J60035@2.5V | max | 20 (22) [23]  DCR 2.2e+07/s | 13 (15) [15]  DCR 6e+06/s | 11 (12) [13]  DCR 2.5e+06/s | 8 (10) [10]  DCR 4.5e+05/s |

The table gives the integer n such that a threshold at (n - 0.5) p.e. has a dark trigger rate below the target.  Stage 3 design criterion (review M1): dark triggers <= 0.05 1/s per chain = 10 %% of the radiometry beta-window background b_beta = 0.5 1/s, i.e. the [square-bracket] column.  Sensitivity to the assumed halving temperature (J60035@2.5V typ, -20 C): T_half 7 C -> 6 p.e., T_half 8 C -> 7 p.e., T_half 10 C -> 7 p.e.

Monte-Carlo check (J60035@2.5V, 25 C, 0.2 s of simulated dark pulses, real shaped pulse):

| n (threshold n-0.5 p.e.) | model, resolving time = area/peak 1/s | model, fitted factor 1/s | Monte-Carlo 1/s | MC / fitted model |
|---|---|---|---|---|
| 3 | 6.99e+04 | 4.1e+04 | 4.46e+04 | 1.09 |
| 4 | 1.29e+04 | 6.62e+03 | 6.77e+03 | 1.02 |
| 5 | 2.38e+03 | 1.1e+03 | 1e+03 | 0.91 |

### T7 Timing budget (calculated unless marked)

| item | value | evidence |
|---|---|---|
| SiPM recharge (J60035) | 50 ns | datasheet |
| Input pole R_IN*Ct (J60035, 10.0 ohm) | 41 ns | calculated |
| FAST peaking time / FWHM / resolving time | 59 / 80 / 90 ns | calculated |
| FAST undershoot after a beta pulse (fraction of peak) | 0.006 | calculated (pole-zero matched) |
| SLOW peaking time for a ZnS(Ag) alpha | 0.53 us | calculated (ZnS profile assumed) |
| Comparator propagation delay (100 mV / 5 mV overdrive) | 4.5 / 7.5 ns typ (12 ns max over T at 5 mV) | datasheet TLV3501 |
| Latch minimum clock pulse width (SN74LVC74A, 3.3 V) | 3.3 ns | datasheet |
| Smallest pulse/threshold ratio that still clocks the latch (TOT >= 4.3 ns) | 1.003 (i.e. effective threshold +0.3 %) | calculated |
| Timer capture resolution (144 MHz) | 6.94 ns | calculated |
| Acceptance window W | 4 us default | contract |
| Service interval | 10 us (100 kHz) | contract |
| Dead time per event: W + U(0, T_service) + ISR | mean 10.5 us, max 15.5 us | calculated; ISR allowance 1.5 us ASSUMED; measured per event in operation |

Non-paralysable live fraction with the mean dead time (calculated):

| true rate 1/s | live fraction | recorded rate 1/s | P(second event inside W) % | P(pile-up inside fast resolving time) % |
|---|---|---|---|---|
| 10 | 0.9999 | 10 | 0.00 | 0.000 |
| 100 | 0.9990 | 100 | 0.04 | 0.001 |
| 2000 | 0.9794 | 1959 | 0.80 | 0.018 |
| 10000 | 0.9050 | 9050 | 3.92 | 0.090 |
| 50000 | 0.6557 | 32787 | 18.13 | 0.448 |
| 100000 | 0.4878 | 48780 | 32.97 | 0.894 |

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
Edge spectrum corner 292 Hz; fast CR (22 ns) passes 4.0e-05 of it -> 6.71e-05 p.e. equivalent at the FAST output (J60035).  Switching energy per edge 0.5*V*I*t = 28 mJ at 15 V.

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

### T13 Time over threshold at the raw LLD (C1): FAST pulse clamped at 3.0 V above baseline, threshold in beta-p.e. units (as the LLD is set); TOT in ns (calculated, pulse model of T2, C_PZ = 47 nF)

| device | LLD p.e. | beta 30 / 120 / 240 p.e. TOT ns | alpha 150 / 300 / 1500 / 15000 p.e. TOT ns | gap: weakest alpha - brightest beta ns | FAST/SLOW per p.e. beta / alpha |
|---|---|---|---|---|---|
| J60035@2.5V | 8 | 119 / 183 / 211 | 428 / 578 / 920 / 1360 | 217 | 18.8 / 6.7 |
| J60035@2.5V | 10 | 107 / 173 / 202 | 374 / 528 / 872 / 1326 | 172 | 18.8 / 6.7 |
| J60035@6V | 8 | 119 / 183 / 211 | 428 / 578 / 920 / 1360 | 217 | 18.8 / 6.7 |
| J60035@6V | 10 | 107 / 173 / 202 | 374 / 528 / 872 / 1326 | 172 | 18.8 / 6.7 |
| J30035@2.5V | 8 | 73 / 106 / 120 | 298 / 446 / 780 / 1196 | 178 | 31.8 / 8.4 |
| J30035@2.5V | 10 | 66 / 101 / 115 | 246 / 396 / 732 / 1160 | 131 | 31.8 / 8.4 |
| S14160-6050HS | 8 | 88 / 128 / 145 | 342 / 492 / 832 / 1288 | 197 | 25.1 / 7.5 |
| S14160-6050HS | 10 | 79 / 122 / 139 | 290 / 440 / 784 / 1250 | 151 | 25.1 / 7.5 |
| S13360-6050PE | 8 | 77 / 112 / 126 | 310 / 458 / 800 / 1262 | 184 | 28.5 / 7.8 |
| S13360-6050PE | 10 | 70 / 106 / 121 | 258 / 408 / 748 / 1218 | 137 | 28.5 / 7.8 |
| NUV-MT 6x6 @12V | 8 | 82 / 119 / 134 | 324 / 474 / 822 / 1338 | 190 | 25.5 / 7.2 |
| NUV-MT 6x6 @12V | 10 | 74 / 113 / 129 | 272 / 424 / 770 / 1288 | 143 | 25.5 / 7.2 |
| 4x J60035@2.5V | 8 | 296 / 510 / 600 | 798 / 972 / 1340 / 1682 | 198 | 9.0 / 4.5 |
| 4x J60035@2.5V | 10 | 256 / 477 / 571 | 738 / 916 / 1292 / 1662 | 167 | 9.0 / 4.5 |

Capture tick 6.94 ns on each edge (two timers): TOT uncertainty +-7 ns, i.e. a cut must sit >= 2 ticks from both populations.  The alpha TOT is set by the ZnS decay (assumed 200 ns) and the beta TOT by R_IN*Ct and the fast CR; the cut has to be chosen per device type from this table and confirmed with Sr-90 and Am-241.

### T14 Low-frequency FAST tail after a large alpha (m2; calculated, J60035, values in p.e. at FAST)

| network | alpha p.e. | 5 us | 50 us | 100 us | 150 us | 200 us | 300 us | 500 us | minimum after 2 us |
|---|---|---|---|---|---|---|---|---|---|
| stage-1 PZ (DC 0.307), no trim node (review model) | 15000 | 14.40 | -10.82 | -6.03 | -3.19 | -1.55 | -0.10 | 0.32 | -13.8 at 23 us |
| stage-1 PZ (DC 0.307), no trim node (review model) | 1500 | 1.44 | -1.08 | -0.60 | -0.32 | -0.15 | -0.01 | 0.03 | -1.4 at 23 us |
| stage-1 PZ, with trim-node step | 15000 | 38.16 | 3.06 | -0.73 | -2.57 | -3.32 | -3.28 | -1.89 | -3.5 at 242 us |
| stage-1 PZ, with trim-node step | 1500 | 3.82 | 0.31 | -0.07 | -0.26 | -0.33 | -0.33 | -0.19 | -0.3 at 242 us |
| S3-04: C_PZ 47 nF, with trim-node step | 15000 | -23.24 | -5.31 | -1.16 | -0.49 | -0.19 | 0.06 | 0.10 | -32.8 at 10 us |
| S3-04: C_PZ 47 nF, with trim-node step | 1500 | -2.32 | -0.53 | -0.12 | -0.05 | -0.02 | 0.01 | 0.01 | -3.3 at 10 us |
| C_PZ 100 nF, with trim-node step | 15000 | 4.73 | -10.59 | -4.08 | -1.74 | -0.71 | 0.06 | 0.22 | -19.0 at 18 us |
| C_PZ 100 nF, with trim-node step | 1500 | 0.47 | -1.06 | -0.41 | -0.17 | -0.07 | 0.01 | 0.02 | -1.9 at 18 us |

The trim node (4.8 uF, recovering through 4.99 k in ~24 ms) takes the alpha charge as a slow step at the anode; the input coupling turns it into a long negative tail that the review's model (first row) does not contain.

### T15 Lane-monitor tap loading and switching charge at the comparator input (M2; calculated, J60035 6.56 mV/p.e. at FCMP; C_bus 50-150 pF, source node 10 pF, switch charge 0.3-3 pC, OPA838 |Z_out| <= 30 ohm at 20 MHz - all assumed)

| tap | amplitude loss while connected (C_bus 50 / 150 pF) | charge sharing at closure, p.e. | switch charge 0.3 / 3 pC, p.e. | monitor bandwidth (C_bus 150 / 50 pF) |
|---|---|---|---|---|
| 1 k at FCMP (stage 1), review mux.py | -14 / -18 % | +1.3 (40 mV) | +0.7 / +7.1 | 1-3 MHz |
| 4.99 k at FAST (op-amp output) | -0.60 % | +0.035 | +0.026 / +0.260 | 213-638 kHz |
| 4.99 k at PRE (x FAST/PRE gain 9.1) (op-amp output) | -5.48 % | +0.317 | +0.237 / +2.374 | 213-638 kHz |
| 10.00 k at FAST (op-amp output) | -0.30 % | +0.017 | +0.013 / +0.130 | 106-318 kHz |
| 10.00 k at PRE (x FAST/PRE gain 9.1) (op-amp output) | -2.74 % | +0.158 | +0.118 / +1.185 | 106-318 kHz |

With MON_LANE_EN = 0 (S3-02) no lane switch is closed or toggled while armed: all three effects are zero. The 10 k numbers apply only to engineering captures with the monitor enabled.

### T16 Motor pickup into the SiPM loop (M4; calculated, J60035; coaxial-dipole mutual inductance; aggressor values assumed as stated)

| aggressor | open pigtail 0.5 cm2 (35 mm): EMF / FAST p.e. | open pigtail 0.68 cm2 (47.5 mm) | coax, 2 mm2 launch |
|---|---|---|---|
| budget case: 1 A in 100 ns, 10 cm2 lead loop at 65 mm | 364 uV / 7.10 | 495 uV / 9.66 | 14.6 uV / 0.28 |
| same with 150 ns edges (DRV8874) | 243 uV / 4.69 | 330 uV / 6.38 | 9.71 uV / 0.19 |
| real differential lead ripple 60 mA p-p (L = 2.5 mH) in 150 ns | 14.6 uV / 0.28 | 19.8 uV / 0.38 | 0.583 uV / 0.01 |
| bridge hot loop on RR-CHS-MAIN: 2.68 A / 150 ns, 2 cm2 at 90 mm | 49 uV / 0.95 | 66.7 uV / 1.29 | 1.96 uV / 0.04 |
| common-mode lead current 80 mA (80 V/us x 1 nF) / 150 ns, 10 cm2 at 74 mm | 13.2 uV / 0.25 | 17.9 uV / 0.35 | 0.526 uV / 0.01 |
| brush commutation arc ~0.1 A common mode in ~5 ns, 10 cm2 at 74 mm | 494 uV / 2.76 | 671 uV / 3.75 | 19.7 uV / 0.11 |

The coax column does not depend on the pigtail length (only the launch loop at the U.FL and the carrier pads remains); the shield-loop term of review m1 (~0.3 p.e.) comes on top.  The band that matters is 1-100 MHz (edges of 5-150 ns): the FAST shaper passes 1-30 MHz with full gain.

### T17 Beta efficiency vs photoelectron yield and the minimum yield for the optics RFQ (M1; calculated: Poisson photostatistics x Moyal energy loss, MPV = 0.70 x mean, assumed)

| p.e. at the MPV deposit (one point of the plate) | eff. LLD 8 | eff. LLD 10 (J60035 typ, +10 C, 0.05/s) | eff. LLD 11 (J60035 max DCR, +10 C, 0.05/s) | eff. LLD 12 |
|---|---|---|---|---|
| 4 | 0.26 | 0.15 | 0.11 | 0.08 |
| 8 | 0.68 | 0.54 | 0.47 | 0.41 |
| 10 | 0.80 | 0.68 | 0.62 | 0.56 |
| 15 | 0.93 | 0.88 | 0.84 | 0.80 |
| 20 | 0.97 | 0.95 | 0.93 | 0.91 |
| 25 | 0.99 | 0.98 | 0.97 | 0.96 |
| 30 | 0.99 | 0.99 | 0.98 | 0.98 |
| 45 | 1.00 | 1.00 | 1.00 | 1.00 |

Minimum yield so that the WORST point of the plate keeps >= 90 % efficiency: LLD 10 -> 16.2 p.e. at the MPV deposit; LLD 11 -> 17.7 p.e.  With the +-50 % light-collection variation (assumed) the plate average at the MPV is then 2 x / 1.5 x that, and the plate-average MEAN yield 1/0.70 x higher.

### T12 Cross-check against circuit.py (channel F0)

Board netlist = design/circuit.py + electronics/head_acq/overrides.py (stage 2/3).  Values in this script that differ from it: none.  Pole-zero resistor fitted: 226 ohm (matched value for a 50 ns recharge time: 227 ohm), in series with C_PZ = 47 nF.  Lane-monitor taps: FAST tap 10000 ohm, SLOW tap 10000 ohm, PRE tap 10000 ohm (all at op-amp outputs).
