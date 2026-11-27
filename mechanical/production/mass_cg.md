# RR-P production body: mass, centre of gravity, tip margins and hang angle (calculated)

Calculated on the production solids (CAD volume x density; SLS PA11 fully dense 1.04, 6061 2.70, cast PU 1.12 g/cm3; purchased masses from parts.yaml; lumped harness / fasteners / foam from the common budget). Heads: `mechanical/head/out/checks.json` (P.HEAD_MASS). Evidence class: calculated.

Body without head: 7.39 kg at x -90.2, z 81.5 mm.

| Head | Mass (kg) | CG x (mm) | CG z (mm) | Caster share | Tip margin fwd / rear / lateral (mm) | Hang angle on the grip (deg) |
|---|---|---|---|---|---|---|
| none (transport / LAB) | 7.39 | -90.2 | 81.5 | 44 % | 79.7 / 104.2 / 55.7 | -36.1 |
| prototype head RR-HD-X (1.862 kg) | 9.25 | -48.2 | 72.1 | 24 % | 39.0 / 147.3 / 79.7 | -11.2 |
| production head (2.082 kg) | 9.47 | -44.0 | 70.8 | 22 % | 34.9 / 151.6 / 82.1 | -8.5 |
| production head + 15 % margin | 9.78 | -38.8 | 69.6 | 19 % | 29.8 / 157.0 / 85.1 | -5.3 |

## Mass by group (kg, calculated)

| Group | Mass | x | z |
|---|---|---|---|
| cassette | 1.909 | -150.7 | 91.3 |
| lid | 0.683 | -87.6 | 108.2 |
| chassis | 0.544 | -65.6 | 35.2 |
| drive | 0.520 | -0.0 | 58.3 |
| lumped: harness (power, sensor, Ethernet, USB) | 0.450 | -60.0 | 85.0 |
| wheel | 0.407 | -0.0 | 52.0 |
| lower_hull | 0.327 | -105.0 | 46.9 |
| controls | 0.296 | -130.5 | 103.6 |
| grip | 0.286 | -28.1 | 134.2 |
| lumped: fasteners, inserts, standoffs | 0.250 | -60.0 | 70.0 |
| chs_main | 0.220 | -17.0 | 83.8 |
| battery_bay | 0.206 | -121.7 | 70.4 |
| receiver | 0.197 | 52.7 | 35.2 |
| compute | 0.165 | -111.5 | 62.3 |
| lidar | 0.160 | -150.0 | 190.0 |
| hatch | 0.157 | -242.3 | 102.6 |
| lumped: foam liner 5 mm + gaskets | 0.150 | -97.0 | 80.0 |
| bridge | 0.108 | -16.5 | 75.4 |
| caster | 0.096 | -196.3 | 32.6 |
| service_cover | 0.058 | -11.1 | 106.5 |
| bumper | 0.047 | -260.8 | 66.0 |
| lumped: RR-TOF harness ends, NTCs, cut-out, vent, light pipes | 0.040 | -120.0 | 95.0 |
| charge | 0.037 | -200.0 | 88.0 |
| connectors | 0.035 | 69.3 | 113.8 |
| tof | 0.027 | -151.0 | 93.2 |
| front_sensors | 0.012 | 50.3 | 26.0 |
