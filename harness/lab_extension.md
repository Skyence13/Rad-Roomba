# LAB ONLY extension pair J1X / J2X (2 m)

Purpose: run the detached head on the bench against the actual robot (head ICD section 7). **LAB ONLY: not part of the robot BOM; never fitted in survey, never left in a robot.** Sources: `interface/system/contract.yaml` (`connectors.J1`, `connectors.J2`, `lab_extension`, `safety_chain.LAB_KEY_N`), `interface/head_icd.md` sections 3 and 7, `electronics/analysis/power_budget.md` section 6, `electronics/chassis_main/design/CONTRACT_CHANGE_REQUESTS.md` CCR-E07, `electronics/analysis/chassis_safety_chain.md`. Machine-readable wire list: `cables.csv` items **W-200** (J1X) and **W-201** (J2X); connectors `J1X-P`, `J1X-S`, `J2X-P`, `J2X-S` in `connectors.yaml`.

## 1. Construction

| Item | Specification | Status |
|---|---|---|
| J1X | One cable, **2.0 m** (head ICD: '2 m as a harness design trial'), M16 8-pole **plug** (male) at the robot end `J1X-P`, M16 8-pole **socket** (female) at the head end `J1X-S`. Straight through. | length from the head ICD; binder M16 part numbers TBD - not in sources |
| J2X | One cable, **2.0 m**, M12 A-coded 8-pole **plug** `J2X-P` (robot end) to **socket** `J2X-S` (head end). Straight through. | part numbers TBD - not in sources |
| Mating | `J1X-P` into the robot's `J1R`; the head's own `J1P` into `J1X-S`. Same for J2. The extension replaces nothing: head, receptacle and pigtail are used unchanged. | contract |
| LAB resistor | **1.50 kohm, 1 %**, from **pin 7 to pin 2**, inside the **`J1X-P` (chassis-end) backshell**. Nothing else is in either backshell. | contract; resistor part TBD - not in sources (any 1 % part; dissipation is 0.23 mW, see section 4) |
| J1X cable | Shielded multicore, individually insulated cold-flexible conductors (silicone or FEP class, rated to <= -40 C, type TBD, `cables.md` section 1), twisted pairs: P1 pins 1-2, P2 pins 3-4, P3 pins 5-6, pin 7 single; overall tinned-copper braid; PUR/TPE jacket rated to <= -40 C. **Pins 1-4 are AWG 18 (0.75 mm2 class)**, pins 5-7 AWG 24. | CCR-E07 |
| J2X cable | Shielded 4-pair cable as W-009, AWG 26, P1 = RS-485 120 ohm twisted pair. Pin 8 not fitted. | contract |
| Colours | As the robot harness (`cables.md` colour scheme): 1 RD, 2 BK, 3 OG, 4 BN, 5 GN, 6 GY, 7 VT. | harness proposal |

### Straight-through pin tables (J1X-P pin n = J1X-S pin n; J2X likewise)

| J1X pin | Net (contract) | AWG | | J2X pin | Net (contract) | AWG |
|---|---|---|---|---|---|---|
| 1 | HEAD_PWR_P (10-15 V, 1.5 A limit) | 18 | | 1 | RS485_DP | 26 |
| 2 | HEAD_PWR_N (the only DC ground between head and chassis; PRES_ID return) | 18 | | 2 | RS485_DN | 26 |
| 3 | HEAD_HTR_P (4 A limit) | 18 | | 3 | BUS_5V | 26 |
| 4 | HEAD_HTR_N (kept out of the electronics return) | 18 | | 4 | BUS_GND | 26 |
| 5 | HEAD_LOOP_OUT (potential-free) | 24 | | 5 | SYNC_P (reserved) | 26 |
| 6 | HEAD_LOOP_RET (potential-free) | 24 | | 6 | SYNC_N (reserved) | 26 |
| 7 | HEAD_PRES_ID (+ 1.50 kohm to pin 2 in `J1X-P`) | 24 | | 7 | J2_PRES (linked to pin 4 in the head plug `J2P`) | 26 |
| 8 | NC_RESERVED: no conductor, contact not fitted or unwired and insulated | - | | 8 | NC_RESERVED: as J1X | - |
| shell | braid, continuous | - | | shell | braid, continuous | - |

AWG 18 is also specified for pins 1 and 2 (the contract table says AWG 20 there): it makes both power pairs meet the 0.125 ohm budget (section 3). AWG 20 on pins 1/2 would be acceptable electrically (0.215 V at 1.5 A) but is **not** within the 0.125 ohm text of the ICD.

## 2. Wiring diagram

```
   robot end                                                       head end
   ---------                                                       --------
   J1R (robot) <-- J1X-P ========= 2.0 m, braid continuous ========= J1X-S <-- J1P (head pigtail)
                    |  pin 1..4 AWG18  pins 5,6,7 AWG24 straight through |
                    |  pin 7 ---[ 1.50 kohm 1 % ]--- pin 2   (in the J1X-P backshell ONLY)
   J2R (robot) <-- J2X-P ========= 2.0 m, braid continuous ========= J2X-S <-- J2P (head pigtail)
                       pins 1..7 straight through, pin 8 not fitted, NO terminator, NO stub
```

## 3. Conductor size: the 0.125 ohm arithmetic

Budget (head ICD section 7): 0.5 V round-trip drop allowance at 4 A on the supply pair, so the **entire added supply-return path including contacts is <= 0.125 ohm**. Current: heater up to 4 A (HEAD_HTR eFuse 4.05 A, 3.6-4.4 A, `power_budget.md` section 5); M16 contact 5 A (contract).

Copper resistance used: **AWG 12 5.21, 14 8.29, 16 13.2, 18 20.9, 20 33.3, 22 53.0, 24 84.2 mohm/m at 20 C** (`electronics/analysis/power_budget.py`, line `AWG = {...}  # [D] copper, mohm/m at 20 C`; consistent with rho = 1.724e-8 ohm m over 0.823 mm2 = 20.9 mohm/m for AWG 18). Extra mated contact pair: **2 contacts x 5 mohm = 10 mohm** (`power_budget.md` section 6 [A]: 'extra M16 contact pair x2 10.0 mohm' - an assumption, to be replaced by the measured value, section 6 below).

R_added = 2 conductors x length x R/m + 10 mohm.

| Case (supply pair) | Wire | + contacts | Total | V at 4.0 A | V at 4.4 A | Loss at 4 A | vs 0.125 ohm |
|---|---|---|---|---|---|---|---|
| **AWG 18, 2.0 m (SPECIFIED)** | 2 x 2.0 x 20.9 = 83.6 mohm | 10 | **93.6 mohm** | 0.374 V | 0.412 V | 1.50 W | **meets, 31.4 mohm (25 %) margin** |
| AWG 20, 2.0 m | 2 x 2.0 x 33.3 = 133.2 | 10 | 143.2 mohm | 0.573 V | 0.630 V | 2.29 W | exceeds by 18.2 mohm (15 %) |
| AWG 24, 2.0 m (moulded cordset) | 2 x 2.0 x 84.2 = 336.8 | 10 | 346.8 mohm | 1.387 V | 1.526 V | 5.55 W | fails by a factor 2.8 |
| AWG 20, 1.7 m (CCR-E07 fallback 1) | 2 x 1.7 x 33.3 = 113.2 | 10 | 123.2 mohm | 0.493 V | 0.542 V | 1.97 W | meets with 1.8 mohm (1.4 %): too thin, measure first |
| AWG 20, 2.0 m with budget relaxed to 0.15 ohm (CCR-E07 fallback 2) | 133.2 | 10 | 143.2 mohm | 0.573 V | 0.630 V | 2.29 W | meets 0.15 ohm; costs 9 % of the heater power at 12 V and nothing else |

At -20 C copper is 16 % lower (`power_budget.md` section 6): AWG 18 wire part 83.6 x 0.84 = 70.2 mohm, total 80.2 mohm: more margin, not relied on.

The electronics pair at <= 1.5 A (1.0 A typical): AWG 18 gives 0.140 V at 1.5 A; the head supply floor in `power_budget.md` section 6 (needs >= 10.3 V at the pack in LAB at full head load) was computed for AWG 20 and holds with AWG 18 (lower drop).

**Open (CCR-E07, UNVERIFIED): the M16 8-pole contacts must accept 0.75 mm2 (AWG 18).** `power_budget.md`: 'binder 8-pole solder cups may be limited to 0.5 mm2'. If they do not, use the CCR-E07 fallbacks above (1.7 m, or 0.15 ohm budget), or paralleled AWG 20 only after the lead agrees. The chassis-side crimp conflict is closed by stage 2 (J_HEAD1 is a Mini-Fit Jr 2x5, terminals for AWG 18-24 [UNVERIFIED, recalled], S2-02); the head board J2001/J2601 still rely on a recalled '43030 18-24 AWG variant' for the heater pair (see `README.md` OD-3).

PRES_ID and loop pairs (AWG 24): added pin 7 path 2 x 2.0 m x 84.2 mohm = 0.337 ohm in series with a 4.70 kohm source (0.007 %), and 0.337 ohm + 10 mohm on a 1.00 kohm loop (0.03 %): negligible against the windows below.

## 4. The 1.50 kohm LAB resistor and the presence decode

| Item | Value | Source |
|---|---|---|
| Value | **1.50 kohm, 1 %** | contract `lab_extension` |
| Position | pin 7 (HEAD_PRES_ID) to pin 2 (HEAD_PWR_N), **inside the J1X-P chassis-end backshell** | contract |
| Head in place | 4.70 kohm 0.1 % (head board R2001, pin 7 to pin 2) in parallel: 4.70k || 1.50k = **1.137 kohm** | contract |
| Pull-up | 4.70 kohm 0.1 % to VREF 3.000 V (chassis R77) | circuit.py, CCR-E03 |
| Dissipation in R_LAB | node 0.584 V, 0.514 mA total: P = 0.584^2 / 1500 = **0.23 mW** | calculated here |
| Tolerance stack | R_LAB 1485-1515 ohm with 4.695-4.705 kohm gives 1.128-1.146 kohm: inside the 0.95-1.33 kohm window | calculated here |

R_LAB is at the CHASSIS end deliberately: with the head removed (extension alone) the chassis still reads 1.50 kohm.

## 5. Shield handling: no third termination, no stub

* The braid of each extension is **one continuous conductor** from backshell to backshell, 360 degrees in both backshells. It connects to **no pin** and to nothing else.
* Bonding stays exactly as in the contract: chassis end hard-bonded through the mated J1X-P / J1R shells; head end to the head frame through 1 Mohm || 10 nF on the head board (pads TP2004 / TP2501). The extension adds no ground connection: do not bond the J1X-S / J2X-S shells to anything on the bench (no clamp to a bench ground).
* **RS-485 (J2X pins 1-2)**: straight-through twisted pair. **No terminator, no bias, no tap** in either J2X backshell; the two 120 ohm terminations stay on the chassis board and on the head board (contract; head ICD section 7: 'no terminated stub or extra third termination'). Fail-safe bias stays at the chassis end only.
* J2_PRES: the link pin 7 to pin 4 stays in the head plug `J2P`; nothing is linked in the extension.
* Pin 8 of both connectors has no conductor.
* Power and heater pairs are twisted pairs inside the braid; HEAD_HTR_N (pin 4) must never be joined to pin 2 anywhere in the extension.

## 6. Labelling

* Both plugs/sockets of both cables carry a **LAB ONLY** sleeve (red/white), the text `J1X-P ROBOT END`, `J1X-S HEAD END`, `J2X-P ROBOT END`, `J2X-S HEAD END`, the **marked length (2.0 m)**, the extension serial number, and the date of the last acceptance test. The marked maximum length is recorded in the run log (head ICD section 7: 'qualify the maximum marked cable length/connectors and keep that identity in the run log').
* The `J1X-P` backshell carries an extra label **'LAB KEY 1.50 kohm'** (the key that the chassis reads as LAB). No jumper may bridge the mount or the drive inhibit (head ICD section 7).
* Conductors carry W-200.n / W-201.n at both ends (`cables.csv`).

## 7. Acceptance test (per extension, before first use and after any repair)

Values marked [source] come from the sources; values marked [proposal] are this document's proposals and need the lead's approval.

| # | Test | Method | Pass |
|---|---|---|---|
| 1 | Continuity, straight through | Each pin 1-7 of J1X-P to the same pin of J1X-S, and J2X pins 1-7; each pin against every other pin at the same end | each pin to its own pin < 0.5 ohm (excluding the LAB resistor path); no pin-to-pin short; pin 8 open |
| 2 | Resistor | Measure J1X-P pin 7 to pin 2 with J1X-S **unplugged** (both ends open) | **1.485-1.515 kohm [source: 1.50 kohm 1 %]**; the same measurement at J1X-S pin 7 to pin 2 must read the same (path through the cable) |
| 3 | Presence decode | Plug J1X-P into the robot with no head: read PRES_ID; then with the head: read again | `LAB_EXTENSION_ONLY` at 1.50k (window 1.33-1.8k) and `HEAD_VIA_LAB_EXTENSION` at 1.137k (window 0.95-1.33k) [source] |
| 4 | Loop resistance, supply pairs | 4-wire (Kelvin) measurement of each of pins 1-2 and 3-4 as a loop, plug to socket, including both contact pairs, with a mating plug/socket stub | **<= 0.125 ohm [source]; expect 0.094 ohm** (section 3); loop pair 5-6 expect 0.34 ohm + 10 mohm |
| 5 | Insulation | 500 V DC [proposal], each pin to every other pin and to the braid | > 100 Mohm [proposal]; power/heater pairs, loop and PRES_ID mutually isolated |
| 6 | Shield | Braid end to end; braid to every pin | braid < 1 ohm end to end [proposal]; braid isolated from all pins (> 100 Mohm [proposal]); no connection to the bench ground |
| 7 | No third termination | J2X-P pins 1-2 with J2X-S unplugged, then with the robot and the head both connected (powered off) | extension alone: open (> 1 Mohm); installed: about 60 ohm (two 120 ohm in parallel). About 40 ohm means a third 120 ohm exists: reject |
| 8 | Pull test | Static pull on the cable at each backshell strain relief | acceptance force is not in the sources: TBD [proposal: 50 N for 60 s with no change in tests 1 and 4] |
| 9 | Heated run | 4 A heater (40 W trial combined load) with the head on the extension; measure the voltage at the head and cable and contact temperature rise | loaded voltage at the head >= 10 V (head minimum) [source: head ICD, power_budget.md section 6]; V drop <= 0.5 V at 4 A; no connector warm to the touch [proposal] |

## 8. What the robot must report when the extension is fitted

From `contract.yaml` (`enums.head_presence`, `lab_extension.presence_decode_on_pin7_to_pin2_ohm`, `enums.hw_inhibit_reason`, `enums.chassis_mode`, `enums.op_mode`):

| Condition | PRES_ID pin 7 to pin 2 | Window | `head_presence` | Chassis hardware chain |
|---|---|---|---|---|
| Nothing connected to J1 | > 20 kohm | > 20k | `ABSENT` | `J1_ABSENT` / `HEAD_LOOP_OPEN` |
| Head docked directly | 4.70 kohm | 3.9k-5.6k (chassis comparator 3.92-5.64k) | `HEAD_DIRECT` | LAB_KEY_N element closed (no LAB resistor) |
| **Head on the LAB extension** | **1.137 kohm** | **0.95k-1.33k** | **`HEAD_VIA_LAB_EXTENSION`** | **LAB_KEY_N element OPEN: `hw_inhibit_reason` includes `LAB_KEY`; HEAD_DOCK is open (head is not seated): `HEAD_UNDOCKED`; traction inhibited in hardware** |
| Extension fitted, head absent | 1.50 kohm | 1.33k-1.8k | `LAB_EXTENSION_ONLY` | as above |
| Short, or value between windows | < 0.8 kohm or between windows | - | `FAULT` | chain open |

Also: `chassis_mode` = `LAB`, `op_mode` = `LAB` (survey and motion refused); `STATE.j2_present` true when the J2 link is made; head acquisition proceeds in maintenance mode only; the data are tagged as bench records without floor coverage or release status (head ICD section 7). **A charging plug has priority over LAB** (head ICD, 'Charging and laboratory mode precedence'): with both connected the robot goes to `SERVICE_CHARGE`, keeps the hardware inhibit and keeps head acquisition and heating off.

## 9. Open items specific to the extension

1. M16 8-pole contact wire range (0.75 mm2) and the solder-cup/crimp variant: TBD (CCR-E07).
2. All connector part numbers and the cable part number: not in the sources.
3. Contact resistance 5 mohm per contact pair is an assumption: measure on the first extension (test 4).
4. Pull-test force and insulation-test values are proposals.
5. Whether the resistor goes in a moulded backshell or a potted insert: not in the sources (the extension must stay serviceable and the resistor visible for test 2).
