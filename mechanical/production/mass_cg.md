# RR-P production body: mass, centre of gravity, tip margins and hang angle (calculated)

Calculated on the production solids (CAD volume x density; SLS PA11 fully dense 1.04, 6061 2.70, cast PU 1.12 g/cm3; purchased masses from parts.yaml; lumped harness / fasteners / foam from the common budget). Heads: `mechanical/head/out/checks.json` (P.HEAD_MASS). Evidence class: calculated.

Body without head: 7.35 kg at x -90.6, z 81.2 mm.

| Head | Mass (kg) | CG x (mm) | CG z (mm) | Caster share | Tip margin fwd / rear / lateral (mm) | Hang angle on the grip (deg) |
|---|---|---|---|---|---|---|
| none (transport / LAB) | 7.35 | -90.6 | 81.2 | 44 % | 80.2 / 103.8 / 55.5 | -36.2 |
| prototype head RR-HD-X (1.881 kg) | 9.23 | -46.2 | 71.6 | 23 % | 37.0 / 149.4 / 80.8 | -9.9 |
| production head (2.100 kg) | 9.45 | -42.0 | 70.4 | 21 % | 33.0 / 153.6 / 83.2 | -7.3 |
| production head + 15 % margin | 9.76 | -36.6 | 69.1 | 18 % | 27.7 / 159.3 / 86.4 | -4.0 |

## Mass by group (kg, calculated)

| Group | Mass | x | z |
|---|---|---|---|
| cassette | 1.909 | -150.7 | 91.3 |
| lid | 0.676 | -86.3 | 108.3 |
| chassis | 0.540 | -66.3 | 35.2 |
| drive | 0.520 | -0.0 | 58.3 |
| lumped: harness (power, sensor, Ethernet, USB) | 0.450 | -60.0 | 85.0 |
| wheel | 0.407 | -0.0 | 52.0 |
| lower_hull | 0.301 | -120.0 | 46.2 |
| controls | 0.296 | -130.5 | 103.4 |
| grip | 0.283 | -28.5 | 133.9 |
| lumped: fasteners, inserts, standoffs | 0.250 | -60.0 | 70.0 |
| chs_main | 0.220 | -17.0 | 83.8 |
| battery_bay | 0.207 | -121.7 | 70.3 |
| receiver | 0.196 | 53.3 | 35.3 |
| lidar | 0.160 | -150.0 | 190.0 |
| compute | 0.159 | -111.6 | 49.3 |
| hatch | 0.157 | -242.3 | 102.6 |
| lumped: foam liner 5 mm + gaskets | 0.150 | -97.0 | 80.0 |
| bridge | 0.111 | -16.4 | 75.0 |
| caster | 0.096 | -196.3 | 32.6 |
| service_cover | 0.058 | -11.1 | 106.5 |
| bumper | 0.047 | -260.8 | 66.0 |
| lumped: RR-TOF harness ends, NTCs, cut-out, vent, light pipes | 0.040 | -120.0 | 95.0 |
| charge | 0.037 | -200.0 | 88.0 |
| connectors | 0.035 | 84.3 | 92.2 |
| tof | 0.028 | -152.8 | 92.1 |
| front_sensors | 0.014 | 49.9 | 27.0 |
