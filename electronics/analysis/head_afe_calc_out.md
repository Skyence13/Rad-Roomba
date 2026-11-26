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

