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
| J60035@2.5V | 0.465 | 41 | 227 | 8.0 | 37.5 | 0.76 | 6.93 | 59 | 80 | 91 | 0.369 | 1.467 | 0.218 | 0.53 |
| J60035@6V | 1.009 | 41 | 227 | 17.4 | 81.4 | 1.65 | 15.06 | 59 | 80 | 91 | 0.801 | 3.187 | 0.473 | 0.53 |
| J30035@2.5V | 0.465 | 11 | 205 | 8.8 | 65.6 | 1.21 | 12.21 | 43 | 51 | 55 | 0.383 | 1.854 | 0.219 | 0.49 |
| S14160-6050HS | 0.401 | 20 | 227 | 6.9 | 43.4 | 0.85 | 8.17 | 50 | 61 | 66 | 0.325 | 1.417 | 0.188 | 0.51 |
| S13360-6050PE | 0.272 | 13 | 227 | 4.7 | 34.0 | 0.64 | 6.33 | 45 | 54 | 58 | 0.222 | 0.998 | 0.128 | 0.50 |
| NUV-MT 6x6 @12V | 1.169 | 16 | 250 | 18.5 | 129.1 | 2.49 | 24.00 | 47 | 57 | 62 | 0.941 | 3.941 | 0.548 | 0.51 |
| 4x J60035@2.5V | 0.465 | 166 | 227 | 8.0 | 16.7 | 0.35 | 2.78 | 79 | 178 | 226 | 0.307 | 0.923 | 0.202 | 0.71 |

### T3 Amplitudes above baseline for the assumed photo-electron design range (calculated; linear values, 'CLIP' = exceeds the stage or clamp limit and saturates)

| device | pulse | p.e. | charge pC | I peak mA | node A | preamp out | FAST out | SLOW out |
|---|---|---|---|---|---|---|---|---|
| J60035@2.5V | single p.e. | 1 | 0.465 | 0.00799 | 3.75e-05 V | 0.000759 V | 0.00693 V | 0.000369 V |
| J60035@2.5V | beta min | 4 | 1.86 | 0.032 | 0.00015 V | 0.00304 V | 0.0277 V | 0.00148 V |
| J60035@2.5V | beta typ | 15 | 6.97 | 0.12 | 0.000562 V | 0.0114 V | 0.104 V | 0.00553 V |
| J60035@2.5V | beta max | 120 | 55.7 | 0.959 | 0.0045 V | 0.0911 V | 0.832 V | 0.0443 V |
| J60035@2.5V | alpha min | 150 | 69.7 | 0.161 | 0.00146 V | 0.0305 V | 0.22 V | 0.0326 V |
| J60035@2.5V | alpha typ | 1500 | 697 | 1.61 | 0.0146 V | 0.305 V | 2.2 V | 0.326 V |
| J60035@2.5V | alpha max | 15000 | 6.97e+03 | 16.1 | 0.146 V | 3.05 V | CLIP (22 V lin.) | CLIP (3.26 V lin.) |
| S14160-6050HS | single p.e. | 1 | 0.401 | 0.00689 | 4.34e-05 V | 0.000848 V | 0.00817 V | 0.000325 V |
| S14160-6050HS | beta min | 4 | 1.6 | 0.0275 | 0.000174 V | 0.00339 V | 0.0327 V | 0.0013 V |
| S14160-6050HS | beta typ | 15 | 6.01 | 0.103 | 0.000651 V | 0.0127 V | 0.123 V | 0.00488 V |
| S14160-6050HS | beta max | 120 | 48.1 | 0.826 | 0.00521 V | 0.102 V | 0.981 V | 0.039 V |
| S14160-6050HS | alpha min | 150 | 60.1 | 0.138 | 0.00135 V | 0.0282 V | 0.213 V | 0.0282 V |
| S14160-6050HS | alpha typ | 1500 | 601 | 1.38 | 0.0135 V | 0.282 V | 2.13 V | 0.282 V |
| S14160-6050HS | alpha max | 15000 | 6.01e+03 | 13.8 | 0.135 V | 2.82 V | CLIP (21.3 V lin.) | 2.82 V |
| S13360-6050PE | single p.e. | 1 | 0.272 | 0.00468 | 3.4e-05 V | 0.000642 V | 0.00633 V | 0.000222 V |
| S13360-6050PE | beta min | 4 | 1.09 | 0.0187 | 0.000136 V | 0.00257 V | 0.0253 V | 0.000887 V |
| S13360-6050PE | beta typ | 15 | 4.09 | 0.0702 | 0.000509 V | 0.00963 V | 0.0949 V | 0.00333 V |
| S13360-6050PE | beta max | 120 | 32.7 | 0.562 | 0.00408 V | 0.077 V | 0.759 V | 0.0266 V |
| S13360-6050PE | alpha min | 150 | 40.9 | 0.0941 | 0.000932 V | 0.0195 V | 0.15 V | 0.0192 V |
| S13360-6050PE | alpha typ | 1500 | 409 | 0.941 | 0.00932 V | 0.195 V | 1.5 V | 0.192 V |
| S13360-6050PE | alpha max | 15000 | 4.09e+03 | 9.41 | 0.0932 V | 1.95 V | CLIP (15 V lin.) | 1.92 V |
| NUV-MT 6x6 @12V | single p.e. | 1 | 1.17 | 0.0185 | 0.000129 V | 0.00249 V | 0.024 V | 0.000941 V |
| NUV-MT 6x6 @12V | beta min | 4 | 4.68 | 0.0739 | 0.000516 V | 0.00997 V | 0.096 V | 0.00377 V |
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
| J60035@2.5V | 6.93 | 0.088 | 274 | 0.94 | 0.87 | 0.218 | 8733 |
| J60035@6V | 15.06 | 0.041 | 126 | 0.43 | 0.40 | 0.473 | 4020 |
| J30035@2.5V | 12.21 | 0.050 | 156 | 0.53 | 0.49 | 0.219 | 8663 |
| S14160-6050HS | 8.17 | 0.075 | 233 | 0.80 | 0.73 | 0.188 | 10093 |
| S13360-6050PE | 6.33 | 0.096 | 300 | 1.03 | 0.95 | 0.128 | 14834 |
| NUV-MT 6x6 @12V | 24.00 | 0.025 | 79 | 0.27 | 0.25 | 0.548 | 3467 |
| 4x J60035@2.5V | 2.78 | 0.219 | 683 | 2.34 | 2.16 | 0.202 | 9384 |

### T5 Electronic noise of the fast path (calculated)

| device | Ct pF | input-referred e_n nV/rtHz (amp + resistors) | FAST output noise mV rms | ENC p.e. rms |
|---|---|---|---|---|
| J60035@2.5V | 4140 | 2.00 | 1.70 | 0.245 |
| J60035@6V | 4140 | 2.00 | 1.70 | 0.113 |
| J30035@2.5V | 1070 | 2.00 | 1.72 | 0.141 |
| S14160-6050HS | 2000 | 2.00 | 1.70 | 0.209 |
| S13360-6050PE | 1280 | 2.00 | 1.71 | 0.270 |
| NUV-MT 6x6 @12V | 1550 | 2.00 | 1.70 | 0.071 |
| 4x J60035@2.5V | 16560 | 2.00 | 1.69 | 0.608 |
