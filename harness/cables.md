# Cable assemblies

GENERATED tables (by `harness/build.py` from `hdata_cables.py`) plus fixed text. One numbered item per assembly (W-xxx); each wire is W-xxx.n. Machine-readable form: `cables.csv`.

**Every length in this document is estimated from layout, confirm on first build.** Board connector positions are the stage-2 PLACED positions (`out/pinmap.json` of the chassis and head boards, +-20 mm until the boards are routed and the shell is built); sensor and device positions are from `frames.yaml` / `mechanical_interfaces.md`.

## 1. Rules for every assembly

### Colour scheme (colour is a class aid, not an identifier)

| Code | Colour | Used for |
|---|---|---|
| RD | red | positive supply of any voltage (VBAT_RAW, HEAD_PWR_P, V5_CM5, V12_LIDAR, V5_AUX, BUS_5V, ToF +3V3, encoder 5 V, VBUS, BTN_3V3, CHG_IN) |
| BK | black | supply return / GND of every class except the heater return |
| OG | orange | heater supply + (HEAD_HTR_P, CHS_HTR_P) |
| BN | brown | heater return and the heater mid-node (HEAD_HTR_N, CHS_HTR_MID) |
| YE | yellow | hardwired safety-chain conductor (CH_N*, COIL_RTN, EN_SRC/EN_SYS, SET_CAP/K1_SET, PLUG_LINK); matches the 'yellow wire' CLIK-Mate family |
| PK | pink | second positive supply on a cable that already has RD (V12_AUX, lamp +, HANDS_LAMP_P) |
| BU | blue | lamp return (switched low side), RS485_DN |
| WH | white | first signal of a pair (RS485_DP, USB D-, SCL, button contact returns) |
| GN | green | second signal (USB D+, SDA, SYNC_P, HEAD_LOOP_OUT, SiPM LED +) |
| GY | grey | third signal (HEAD_LOOP_RET, SYNC_N, GPIO1) |
| VT | violet | single-ended identity/status lines (HEAD_PRES_ID, J2_PRES, XSHUT) |
| bare | tinned drain | shield drain wire (sleeved and numbered) |

Duplicate colours on one cable (for example two BK conductors) are told apart by the wire number printed on every conductor at both ends and every 100 mm (heat-shrink or laser-printed sleeve): **W-xxx.n**. Motor leads keep the maker's colours (Pololu, modules sheet [D]).

### Conductor and insulation (cold-flexible, rated to at least -40 C)

| Code | Insulation | Where |
|---|---|---|
| SI | silicone-rubber insulated, tinned fine-strand copper (class value -60 C; supplier part TBD - not in sources; UNVERIFIED). PVC excluded (not rated -40 C) | all power, chain, heater and general conductors |
| FEP | FEP/ETFE insulated, tinned stranded copper (class value -65 C; supplier part TBD - not in sources; UNVERIFIED) | AWG 24-28 signal conductors, USB, ToF, NTC |
| COAX | 50 ohm micro-coax 1.13 mm class, FEP dielectric and jacket (class value -65 C; part TBD - not in sources; UNVERIFIED) | SiPM anode and bias pigtails |
| DEV | device lead as supplied by the device maker (insulation rating not in sources) | motor pigtails, device leads |

No source names a specific cable or wire part number; the class values are generic, UNVERIFIED, and the technician needs a supplier datasheet showing the rating at -40 C before purchase (open item OI-01). The outer jacket of external multicores is PUR or TPE rated to <= -40 C (type TBD). **PVC is excluded.** `power_budget.md` assumed 'PVC-free, 105 C' AWG 14: that rating is not a cold rating.

### Length method

Routed path along the reserved corridors (`layout_report.md` section 7) between the placed connector positions (stage 2) and the device positions in `frames.yaml` / `mechanical_interfaces.md`; plus 2 x end allowance for termination and strain relief (25 mm, 30 mm on large connectors, 15 mm on ToF) plus a service loop (50 mm, 30 mm on ToF), rounded up to 10 mm. Panel devices are reached at 45 mm behind the skin along the control axis. The path points are in `hdata_cables.py` (`path=`). Where the power budget assumed a length, it is shown for comparison.

### Labels

At **both ends** of every cable, within 30 mm of the connector: a sleeve with `W-xxx`, the connector ID (as in `connectors.yaml`) and pin 1 marker; on every conductor the wire number `W-xxx.n` and the net (`label_from_end` / `label_to_end` columns of `cables.csv` give the exact text). Chain (yellow) looms additionally carry a SAFETY CHAIN sleeve every 150 mm. LAB items carry a LAB ONLY sleeve (see `lab_extension.md`).

## 2. Summary

| Cable | Title | Wires | Length (mm) | Budget assumed (mm) | Flag |
|---|---|---|---|---|---|
| W-001 | Pack coupler (bay half) to main board J_PWR: pack feed with 20 A fuse and 1-to-2 splices | 7 | 300 | 300 |  |
| W-002 | Battery cassette internal wiring: pack F2 terminals to the cassette coupler half (NTC, presence link, optional cassette fuse) | 6 | 150 | 150 |  |
| W-003 | Pack coupler (bay half) auxiliary contacts to main board J_PAUX | 2 | 300 | - |  |
| W-004 | Charge inlet to main board J_PWR (24 V in, 0 V, plug-link pair) | 4 | 280 | 250 | exceeds length assumed by the source (250 mm) |
| W-005 | Inlet cover switch to main board J_COVER | 2 | 270 | - |  |
| W-006 | Left gearmotor and encoder to main board J_MOT_L | 6 | 190 | 250 |  |
| W-007 | Right gearmotor and encoder to main board J_MOT_R | 6 | 190 | 250 |  |
| W-008 | J1 chassis lead: main board J_HEAD1 (Mini-Fit Jr 2x5) to the J1 receptacle | 7 | 160 | 250 |  |
| W-009 | J2 chassis lead: main board J_HEAD2 to the J2 receptacle | 7 | 140 | - |  |
| W-010 | CM5 5.1 V feed: main board J_CM5 to the CM5 carrier 40-pin header | 4 | 190 | 250 |  |
| W-011 | LiDAR supply: main board J_LIDAR to the LiDAR | 2 | 290 | 400 |  |
| W-012 | LiDAR Ethernet: LiDAR pigtail to the CM5 carrier RJ45 (purchased) | 4 | 260 | - |  |
| W-013 | USB 2.0 FS chassis link (MCU CDC): main board J_USB_MCU to the CM5 carrier USB-A | 4 | 190 | - |  |
| W-014 | USB 2.0 FS head link (FT230X): main board J_USB_HEAD to the CM5 carrier USB-A | 5 | 200 | - |  |
| W-015 | E-stop (two poles) to main board J_ESTOP | 4 | 220 | - |  |
| W-016 | Mode selector OFF/SERVICE/RUN to main board J_MODE | 4 | 190 | - |  |
| W-017 | HANDS-ON button and lamp to main board J_HANDS | 4 | 250 | - |  |
| W-018 | REARM/Start button and lamp: main board J_BTN to the REARM button (left deck) | 6 | 240 | - |  |
| W-019 | PAUSE/Stop button and lamp: main board J_PAUSE (JST GH 5-way) to the PAUSE button (right deck) | 4 | 170 | - |  |
| W-020 | Head dock switch to main board J_DOCK | 2 | 270 | - |  |
| W-021 | Body bumper left to main board J_BUMP_L | 2 | 330 | - |  |
| W-022 | Body bumper right to main board J_BUMP_R | 2 | 310 | - |  |
| W-023 | RR-PANEL: main board J_PANEL to RR-PANEL J1 (straight 1:1) | 10 | 180 | - |  |
| W-024 | OPTIONAL external 22 mm sounder: RR-PANEL J2 to the panel sounder | 2 | 100 | - |  |
| W-030 | ToF carrier CLIFF_FL (RR-TOF #0): main board J_TOF0 to the carrier J1 | 6 | 190 | 300 |  |
| W-031 | ToF carrier CLIFF_FR (RR-TOF #1): main board J_TOF1 to the carrier J1 | 6 | 190 | 300 |  |
| W-032 | ToF carrier CLIFF_RL (RR-TOF #2): main board J_TOF2 to the carrier J1 | 6 | 290 | 300 |  |
| W-033 | ToF carrier CLIFF_RR (RR-TOF #3): main board J_TOF3 to the carrier J1 | 6 | 290 | 300 |  |
| W-034 | ToF carrier LOOK_FL (RR-TOF #4): main board J_TOF4 to the carrier J1 | 6 | 150 | 300 |  |
| W-035 | ToF carrier LOOK_FR (RR-TOF #5): main board J_TOF5 to the carrier J1 | 6 | 280 | 300 |  |
| W-036 | ToF carrier LOOK_RL (RR-TOF #6): main board J_TOF6 to the carrier J1 | 6 | 360 | 300 | ToF cable exceeds 300 mm |
| W-037 | ToF carrier LOOK_RR (RR-TOF #7): main board J_TOF7 to the carrier J1 | 6 | 350 | 300 | ToF cable exceeds 300 mm |
| W-038 | ToF carrier REAR_L (RR-TOF #8): main board J_TOF8 to the carrier J1 | 6 | 270 | 300 |  |
| W-039 | ToF carrier REAR_C (RR-TOF #9): main board J_TOF9 to the carrier J1 | 6 | 290 | 300 |  |
| W-040 | ToF carrier REAR_R (RR-TOF #10): main board J_TOF10 to the carrier J1 | 6 | 290 | 300 |  |
| W-041 | Chassis/bay heater with its bimetal cut-out: main board J_HTR to the heater plate | 3 | 220 | 300 |  |
| W-042 | Bay NTC and pack-surface NTC to main board J_NTC | 4 | 220 | - |  |
| W-101 | Head J1 captive pigtail: head board J2001 to the J1 plug | 8 | 290 | 350 |  |
| W-102 | Head J2 captive pigtail: head board J2501 to the J2 plug (plug link pin 7 to pin 4) | 9 | 300 | - |  |
| W-103 | Head heater film, bimetal cut-out and spreader NTC: head board J2601 to the heater assembly | 7 | 100 | 350 |  |
| W-104 | Head rail switch front (series element of the interlock loop): head board J2002 to the switch | 2 | 90 | - |  |
| W-105 | Head rail switch left (series element of the interlock loop): head board J2003 to the switch | 2 | 290 | - |  |
| W-106 | Head rail switch right (series element of the interlock loop): head board J2004 to the switch | 2 | 290 | - |  |
| W-107 | Head lid (light-leak) interlock switch: head board J2201 to the lid switch | 2 | 200 | - |  |
| W-108 | Head lane 0 auxiliary pigtail: head board J1001 to the SiPM carrier aux | 6 | 35 | - |  |
| W-109 | Head lane 1 auxiliary pigtail: head board J1101 to the SiPM carrier aux | 6 | 35 | - |  |
| W-110 | Head lane 2 auxiliary pigtail: head board J1201 to the SiPM carrier aux | 6 | 35 | - |  |
| W-111 | Head lane 3 auxiliary pigtail: head board J1301 to the SiPM carrier aux | 6 | 35 | - |  |
| W-112 | SiPM coaxial pair F0 (anode signal + bias): head board J101/J102 to SiPM carrier F0 | 4 | 50 | 35 | exceeds length assumed by the source (35 mm) |
| W-113 | SiPM coaxial pair F1 (anode signal + bias): head board J201/J202 to SiPM carrier F1 | 4 | 50 | 35 | exceeds length assumed by the source (35 mm) |
| W-114 | SiPM coaxial pair F2 (anode signal + bias): head board J301/J302 to SiPM carrier F2 | 4 | 50 | 35 | exceeds length assumed by the source (35 mm) |
| W-115 | SiPM coaxial pair F3 (anode signal + bias): head board J401/J402 to SiPM carrier F3 | 4 | 50 | 35 | exceeds length assumed by the source (35 mm) |
| W-116 | SiPM coaxial pair R0 (anode signal + bias): head board J501/J502 to SiPM carrier R0 | 4 | 45 | 35 | exceeds length assumed by the source (35 mm) |
| W-117 | SiPM coaxial pair R1 (anode signal + bias): head board J601/J602 to SiPM carrier R1 | 4 | 45 | 35 | exceeds length assumed by the source (35 mm) |
| W-118 | SiPM coaxial pair R2 (anode signal + bias): head board J701/J702 to SiPM carrier R2 | 4 | 45 | 35 | exceeds length assumed by the source (35 mm) |
| W-119 | SiPM coaxial pair R3 (anode signal + bias): head board J801/J802 to SiPM carrier R3 | 4 | 45 | 35 | exceeds length assumed by the source (35 mm) |
| W-200 | LAB ONLY: J1X extension, 2 m, M16 plug (robot end) to M16 socket (head end), straight through + 1.50 kohm LAB resistor | 9 | 2000 | 2000 |  |
| W-201 | LAB ONLY: J2X extension, 2 m, M12 plug (robot end) to M12 socket (head end), straight through | 8 | 2000 | 2000 |  |

Totals: **58 cable assemblies, 284 wires** (179 robot, 88 head, 17 LAB extension wires).

### Lengths that exceed a limit

| Cable | Length (mm) | Why flagged |
|---|---|---|
| W-004 | 280 | exceeds the length assumed in power_budget.md / mechanical (250 mm) |
| W-036 | 360 | ToF cable exceeds the 300 mm I2C design limit (modules/tof_vl53l4ed.md) |
| W-037 | 350 | ToF cable exceeds the 300 mm I2C design limit (modules/tof_vl53l4ed.md) |
| W-112 | 50 | exceeds the length assumed in power_budget.md / mechanical (35 mm) |
| W-113 | 50 | exceeds the length assumed in power_budget.md / mechanical (35 mm) |
| W-114 | 50 | exceeds the length assumed in power_budget.md / mechanical (35 mm) |
| W-115 | 50 | exceeds the length assumed in power_budget.md / mechanical (35 mm) |
| W-116 | 45 | exceeds the length assumed in power_budget.md / mechanical (35 mm) |
| W-117 | 45 | exceeds the length assumed in power_budget.md / mechanical (35 mm) |
| W-118 | 45 | exceeds the length assumed in power_budget.md / mechanical (35 mm) |
| W-119 | 45 | exceeds the length assumed in power_budget.md / mechanical (35 mm) |

Where lengths come from (stage 2): the board connector positions are the PLACED positions in `electronics/chassis_main/out/pinmap.json` (rear-right cluster J_PAUSE, J_TOF3, J_TOF10, J_BUMP_R, J_TOF6; J_PWR at u 142.5, v 24.1; J_HEAD1 Mini-Fit Jr at u 26.1, v 82.5), the head connector positions are those of `electronics/head_acq/out/pinmap.json`, the sensor positions are those of `mechanical/common/frames.yaml` read at the time of the build. The stage-1 rear-left allocation of the right-hand cables (W-022 430 mm, W-033 400 mm, W-040 400 mm, W-019 290 mm) is gone.

Open length items: (a) **IB-34 mapping**: with J_TOF4 = LOOK_FL, J_TOF5 = LOOK_FR, J_TOF6 = LOOK_RL, J_TOF7 = LOOK_RR (lead decision) the connectors J_TOF6 (rear-right) and J_TOF7 (front-right edge) are on the wrong side for their tail sensors, so W-036 and W-037 exceed 300 mm. The mapping J_TOF5 = LOOK_RL, J_TOF6 = LOOK_RR, J_TOF7 = LOOK_FR (same four connectors, different names) would give W-035 270, W-036 290, W-037 150 mm: see README open decision OD-1. (b) W-004 is 30 mm over the 250 mm of the power budget (about 1 mohm: no consequence). (c) The eight SiPM coax pairs (W-112..W-119) are 45-50 mm against the 35 mm of `board_envelopes.yaml` because the stage-2 translated channel layout (S2-L3) moved the U.FL jacks (bias at du -15.47 / +6.78, anode at -10.38 / +11.87).

## 3. Per-assembly detail

### W-001  Pack coupler (bay half) to main board J_PWR: pack feed with 20 A fuse and 1-to-2 splices

* **Length:** 300 mm (routed path 192 mm + 2 x 30 mm termination/strain relief + 40 mm service loop = 292 mm, rounded up to 300 mm). *Estimated from layout, confirm on first build.*
* **Construction:** Two AWG 14 trunk conductors (twisted pair) coupler to splices, then 2 x AWG 16 per pole to the Mini-Fit Jr 2x4 J_PWR (stage-2 position u 142.5, v 24.1: 18 mm in from the right edge, 15 mm clear of the rear-right cluster). Corridors: under_bridge_right then right_gutter (layout_report.md section 7). Pair twisted P1 over the trunk.
* **Shield / bonding:** none (power, unshielded)
* **Protection upstream:** Pack BMS (15 A continuous, 25 A/10 s, 30 A/3 s, short circuit 60 A/0.5 ms) [D 12120]; 20 A blade fuse (32 V, >= 1 kA) in the bay harness within 150 mm of the coupler; optional second 20 A fuse in the cassette. Board: LM74502 bidirectional switch (no current limit), OV cut-off 16.6 V
* **Strain relief:** Both AWG 16 wires per pole clipped within 50 mm of the housing; housing latch + board peg; cable support to the bridge tray within 80 mm
* **Labels:** both ends, `W-001` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** IB-36 CONTRADICTION (J_PWR gauge): power_budget.md assumes 2 x 0.30 m AWG 14 all the way to J_PWR, but electronics/chassis_main/design/connectors.yaml (unchanged by stage 2: overrides.py has no J_PWR entry) fits 39-00-0078 contacts for AWG 16 on pins 1/2/5/6. The harness FOLLOWS connectors.yaml (the board side is fixed): an AWG 14 trunk plus 2 x AWG 16 per pole through a crimp splice (about 1.3 mohm extra, not in the power budget). Splice, fuse holder and SBS50 contact wire range are TBD. The fuse position leaves <= 150 mm of unfused trunk.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-001.1 | CPL-B.P | FUSE-MAIN.1 | PACK_P | 14 | RD | SI | P1 | 120 |
| W-001.2 | FUSE-MAIN.2 | SPL-P.1 | VBAT_RAW | 14 | RD | SI | P1 | 300 |
| W-001.3 | SPL-P.2 | CHS.J_PWR.1 | VBAT_RAW | 16 | RD | SI | - | 80 |
| W-001.4 | SPL-P.3 | CHS.J_PWR.2 | VBAT_RAW | 16 | RD | SI | - | 80 |
| W-001.5 | CPL-B.N | SPL-N.1 | GND | 14 | BK | SI | P1 | 300 |
| W-001.6 | SPL-N.2 | CHS.J_PWR.5 | GND | 16 | BK | SI | - | 80 |
| W-001.7 | SPL-N.3 | CHS.J_PWR.6 | GND | 16 | BK | SI | - | 80 |

### W-002  Battery cassette internal wiring: pack F2 terminals to the cassette coupler half (NTC, presence link, optional cassette fuse)

* **Length:** 150 mm (cassette interior 156.5 x 109 x 104 mm (mechanical_interfaces.md section 5); lengths per wire are the cassette-internal runs (power_budget.md assumes 2 x 0.15 m AWG 12 cassette leads)). *Estimated from layout, confirm on first build.*
* **Construction:** Purchased/assembled with the pack (BOM R01/R02). AWG 12 leads on insulated fastons. The wire list is the specification for the cassette assembler.
* **Shield / bonding:** none
* **Protection upstream:** Optional cassette fuse (see FUSE-CASS); pack BMS (see W-001)
* **Strain relief:** Leads tied to the cassette wall within 40 mm of each terminal; terminals covered (insulated fastons); coupler half floats +-1 mm so keep 20 mm of slack
* **Labels:** both ends, `W-002` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** IB-37 (accepted offset): the NTC return and the presence link are made to PACK NEGATIVE inside the cassette, so the sense level rides the pack-negative power path (about 0.1 V at full load: NTC reads about 3.4 K warm while discharging, about 0.7 K cold while charging, both on the safe side; STAGE2_CHANGE_REQUESTS.md). J_PAUX pins 3/4 stay unwired unless the cassette provides a sense return ISOLATED from pack negative. Cassette half of the SBS50 coupler is UNVERIFIED; -20 C rating only in parts.yaml (IB-36, see open items).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-002.1 | PACK.+ | FUSE-CASS.1 | PACK_P_CELL | 12 | RD | SI | - | 150 |
| W-002.2 | FUSE-CASS.2 | CPL-C.P | PACK_P | 12 | RD | SI | - | 100 |
| W-002.3 | PACK.- | CPL-C.N | GND | 12 | BK | SI | - | 150 |
| W-002.4 | NTC-CASS.a | CPL-C.A1 | PACK_NTC | 26 | WH | FEP | - | 150 |
| W-002.5 | NTC-CASS.b | PACK.- | GND | 26 | BK | FEP | - | 120 |
| W-002.6 | CPL-C.A2 | CPL-C.N | PACK_PRES_N -> GND | 26 | VT | FEP | - | 60 |

### W-003  Pack coupler (bay half) auxiliary contacts to main board J_PAUX

* **Length:** 300 mm (routed path 219 mm + 2 x 20 mm termination/strain relief + 40 mm service loop = 299 mm, rounded up to 300 mm). *Estimated from layout, confirm on first build.*
* **Construction:** Two AWG 26 conductors, twisted pair, run in the same loom as W-001 (separate sleeve). J_PAUX pins 3 and 4 (GND) are NOT wired: the cassette returns NTC and presence to pack negative inside the cassette.
* **Shield / bonding:** none
* **Protection upstream:** No fuse; 10 kohm pull-up to the 3.000 V reference (<= 0.3 mA)
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board
* **Labels:** both ends, `W-003` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** IB-37 DECISION (chassis stage 2, accepted offset, no board change): the NTC/presence return flows through the pack-negative power path (up to 12.5 A): the J_PAUX GND level can differ from board GND by about 0.1 V at full load (NTC about 3.4 K warm on discharge, about 0.7 K cold on charge: safe side; PACK_PRES_N is logic level). J_PAUX pins 3/4 (GND) stay UNWIRED. They are wired ONLY if the cassette gets a sense return isolated from pack negative (W-002 change plus a third SBS50 auxiliary contact); wiring them to a return that is also tied to pack negative would put an AWG 26 wire in parallel with the pack return (about 1-2 % of pack current). J_PAUX is at u 118.0, v 21.8 (stage 2). AWG 26 for the aux contacts is a proposal; SBS50 auxiliary contact wire range is TBD.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-003.1 | CPL-B.A1 | CHS.J_PAUX.1 | PACK_NTC | 26 | WH | FEP | P1 | 300 |
| W-003.2 | CPL-B.A2 | CHS.J_PAUX.2 | PACK_PRES_N | 26 | VT | FEP | P1 | 300 |

### W-004  Charge inlet to main board J_PWR (24 V in, 0 V, plug-link pair)

* **Length:** 280 mm (routed path 174 mm + 2 x 25 mm termination/strain relief + 50 mm service loop = 274 mm, rounded up to 280 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 4 conductors: power pair (AWG 18) twisted P1, link pair (AWG 24) twisted P2, in one jacket. Corridor right_bay then right_gutter. Inlet FE contact = chassis through the receptacle flange (no wire).
* **Shield / bonding:** none; FE on the inlet bonds to the chassis through the flange
* **Protection upstream:** External supply 24 V / 3.75 A (UNVERIFIED); on board F_CHG 5 A fuse then LTC4162 input limit 4.0 A [U]. Charger limit 3.0 A. Three interlock channels open the traction chain
* **Strain relief:** Both AWG 16 wires per pole clipped within 50 mm of the housing; housing latch + board peg; cable support to the bridge tray within 80 mm; inlet end: clamp behind the receptacle (25 mm depth available)
* **Labels:** both ends, `W-004` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Inlet pin assignment is a PROPOSAL (external_24v_supply.md [M][U]). Layout length exceeds the 0.25 m of power_budget.md only if it comes out above 250 mm (see length column). Plug link opens even with an unpowered cable: pins 2 and 4 are linked inside the charge plug.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-004.1 | INLET.1 | CHS.J_PWR.3 | CHG_IN | 18 | RD | SI | P1 | 280 |
| W-004.2 | INLET.3 | CHS.J_PWR.7 | GND | 18 | BK | SI | P1 | 280 |
| W-004.3 | INLET.2 | CHS.J_PWR.4 | PLUG_LINK | 24 | YE | SI | P2 | 280 |
| W-004.4 | INLET.4 | CHS.J_PWR.8 | GND | 24 | BK | SI | P2 | 280 |

### W-005  Inlet cover switch to main board J_COVER

* **Length:** 270 mm (routed path 177 mm + 2 x 20 mm termination/strain relief + 50 mm service loop = 267 mm, rounded up to 270 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 2 x AWG 24 twisted pair, yellow safety loom. J_COVER pin 3 NC (not wired). D2HW NO lead cut back and insulated.
* **Shield / bonding:** none
* **Protection upstream:** Chain branch: F_CHAIN PTC 0.20 A hold / 0.40 A trip (circuit.py); relay coils and chain nodes 80 mA when latched
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing; P-clip within 50 mm; yellow sleeve/heat-shrink on the whole safety loom; kept in its own loom away from VBAT conductors (chassis_safety_chain.md fault #31)
* **Labels:** both ends, `W-005` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Chain element CHG_COVER: opens when the cover is open. Switch lead gauge/length not in sources (TBD): splice or direct crimp decided on the first build.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-005.1 | COVER-DEV.COM | CHS.J_COVER.1 | CH_N3 | 24 | YE | SI | P1 | 270 |
| W-005.2 | COVER-DEV.NC | CHS.J_COVER.2 | CH_N4A | 24 | YE | SI | P1 | 270 |

### W-006  Left gearmotor and encoder to main board J_MOT_L

* **Length:** 190 mm (routed path 89 mm + 2 x 25 mm termination/strain relief + 50 mm service loop = 189 mm, rounded up to 190 mm). *Estimated from layout, confirm on first build.*
* **Construction:** The motor's own six-wire pigtail re-terminated into a Micro-Fit 3.0 2x3 plug housing (43025-0600). Lead length and gauge are NOT published (TBD): if the pigtail is shorter than the length column, extend with an in-line splice at the motor, never with a connector. Colours are Pololu's, not this scheme (modules sheet [D], confirm on the part).
* **Shield / bonding:** none (motor leads and encoder lines unshielded; ferrite + 1 nF at the board connector, layout_guidance.md)
* **Protection upstream:** VMOT eFuse TPS25982 (RILIM 237 ohm) 6.5 A +/-8 %, bridges chop at 2.68 A each, DRV8874 OCP >= 6 A; latch removes VMOT; motor brake via K2/K3 NC + 1.0 ohm; Encoder 5 V through a 0.1 A PTC on the board (modules sheet); 10 kohm pull-ups
* **Strain relief:** Wires bundled and clipped (P-clip) within 50 mm of the housing; housing latch + board peg; heavier gauge fixed before the lighter ones; no cable weight on the header; motor end: leads clipped to the motor mount within 30 mm of the exit
* **Labels:** both ends, `W-006` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** IB-36 (motor lead gauge): the harness assumes AWG 22 as in power_budget.md (motor leads AWG 22, 0.25 m) because the leads are the maker's captive pigtail and its gauge is not published (gearmotor_pololu_2828.md); electronics/chassis_main/design/connectors.yaml J_MOT recommends AWG 20 for pins 1/2. Both fit the 43030-0007 contact (AWG 20-24). If the real pigtail is thinner than AWG 22 the 2.7 A pins are under-rated: measure on the first motor. Motor pins 1-2 max 2.7 A on AWG 22 (3 A table value): little margin. Motor terminals face y = +115 (gearbox) with the cable leaving the encoder end at y = +42.5 (parts.yaml envelope). Left/right swap is found by the first wheel-up test (connectors.yaml same_count_as).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-006.1 | MOTOR-L.1 | CHS.J_MOT_L.1 | MOTC_L_A | 22 | RD | DEV | M | 190 |
| W-006.2 | MOTOR-L.2 | CHS.J_MOT_L.2 | MOTC_L_B | 22 | BK | DEV | M | 190 |
| W-006.3 | MOTOR-L.3 | CHS.J_MOT_L.3 | ENC_L_5V | 26 | BU | DEV | E | 190 |
| W-006.4 | MOTOR-L.4 | CHS.J_MOT_L.4 | GND | 26 | GN | DEV | E | 190 |
| W-006.5 | MOTOR-L.5 | CHS.J_MOT_L.5 | ENCC_L_A | 26 | YE | DEV | E | 190 |
| W-006.6 | MOTOR-L.6 | CHS.J_MOT_L.6 | ENCC_L_B | 26 | WH | DEV | E | 190 |

### W-007  Right gearmotor and encoder to main board J_MOT_R

* **Length:** 190 mm (routed path 89 mm + 2 x 25 mm termination/strain relief + 50 mm service loop = 189 mm, rounded up to 190 mm). *Estimated from layout, confirm on first build.*
* **Construction:** The motor's own six-wire pigtail re-terminated into a Micro-Fit 3.0 2x3 plug housing (43025-0600). Lead length and gauge are NOT published (TBD): if the pigtail is shorter than the length column, extend with an in-line splice at the motor, never with a connector. Colours are Pololu's, not this scheme (modules sheet [D], confirm on the part).
* **Shield / bonding:** none (motor leads and encoder lines unshielded; ferrite + 1 nF at the board connector, layout_guidance.md)
* **Protection upstream:** VMOT eFuse TPS25982 (RILIM 237 ohm) 6.5 A +/-8 %, bridges chop at 2.68 A each, DRV8874 OCP >= 6 A; latch removes VMOT; motor brake via K2/K3 NC + 1.0 ohm; Encoder 5 V through a 0.1 A PTC on the board (modules sheet); 10 kohm pull-ups
* **Strain relief:** Wires bundled and clipped (P-clip) within 50 mm of the housing; housing latch + board peg; heavier gauge fixed before the lighter ones; no cable weight on the header; motor end: leads clipped to the motor mount within 30 mm of the exit
* **Labels:** both ends, `W-007` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** IB-36 (motor lead gauge): the harness assumes AWG 22 as in power_budget.md (motor leads AWG 22, 0.25 m) because the leads are the maker's captive pigtail and its gauge is not published (gearmotor_pololu_2828.md); electronics/chassis_main/design/connectors.yaml J_MOT recommends AWG 20 for pins 1/2. Both fit the 43030-0007 contact (AWG 20-24). If the real pigtail is thinner than AWG 22 the 2.7 A pins are under-rated: measure on the first motor. Motor pins 1-2 max 2.7 A on AWG 22 (3 A table value): little margin. Motor terminals face y = -115 (gearbox) with the cable leaving the encoder end at y = -42.5 (parts.yaml envelope). Left/right swap is found by the first wheel-up test (connectors.yaml same_count_as).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-007.1 | MOTOR-R.1 | CHS.J_MOT_R.1 | MOTC_R_A | 22 | RD | DEV | M | 190 |
| W-007.2 | MOTOR-R.2 | CHS.J_MOT_R.2 | MOTC_R_B | 22 | BK | DEV | M | 190 |
| W-007.3 | MOTOR-R.3 | CHS.J_MOT_R.3 | ENC_R_5V | 26 | BU | DEV | E | 190 |
| W-007.4 | MOTOR-R.4 | CHS.J_MOT_R.4 | GND | 26 | GN | DEV | E | 190 |
| W-007.5 | MOTOR-R.5 | CHS.J_MOT_R.5 | ENCC_R_A | 26 | YE | DEV | E | 190 |
| W-007.6 | MOTOR-R.6 | CHS.J_MOT_R.6 | ENCC_R_B | 26 | WH | DEV | E | 190 |

### W-008  J1 chassis lead: main board J_HEAD1 (Mini-Fit Jr 2x5) to the J1 receptacle

* **Length:** 160 mm (routed path 60 mm + 2 x 30 mm termination/strain relief + 40 mm service loop = 160 mm, rounded up to 160 mm). *Estimated from layout, confirm on first build.*
* **Construction:** Custom shielded multicore: individually insulated conductors AWG 20/20/18/18/24/24/24 (pin 8 not fitted), twisted pairs P1 (1-2 power), P2 (3-4 heater), P3 (5-6 loop), pin 7 single; overall tinned-copper braid (>= 85 % coverage is a PROPOSAL) and TPE/PUR jacket rated to <= -40 C (TBD), OD <= 7.5 mm to match the receptacle backshell. Pins 3-4 must be kept out of the electronics return (contract).
* **Shield / bonding:** Overall braid terminated 360 degrees on the J1R receptacle shell/ground tag = chassis (contract). OPEN at the J_HEAD1 end: Mini-Fit Jr has no shield pin; cut back and insulate the braid, no drain wire to the board.
* **Protection upstream:** HEAD_PWR eFuse TPS259470 (RILM 2.21 k) 1.51 A; contract limit 1.5 A; head side TPS26600 eFuse 1.0 A (pins 1-2); HEAD_HTR eFuse TPS259470 (RILM 825 ohm) 4.05 A (3.6-4.4 A), contract limit 4.0 A; independent low-side bimetal cut-out on the head heater (pins 3-4); No fuse: signal conductors, series-limited (loop through 1.00 kohm; PRES_ID through the 4.70 kohm pull-up) [circuit.py] (pins 5-7)
* **Strain relief:** Receptacle end: cable clamped and clipped within 50 mm of the backshell; plug end: backshell strain-relief clamp (supplier part TBD); bend radius >= 40 mm (J1) / 35 mm (J2) per parts.yaml
* **Labels:** both ends, `W-008` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** STAGE 2 (IB-32 / IB-44, S2-02): J_HEAD1 is now a Mini-Fit Jr 2x5 right-angle header 39-30-1100 (pins 1-8 = J1 pins 1-8, pins 9/10 not connected); the mating housing is 39-01-2100 class with 5556 terminals for AWG 18-24 (all seven wires fit, the heater pair AWG 18 included); this clears the AWG 18 on Micro-Fit error at the chassis end. The 10-way housing cannot mate the 8-way J_PWR. All of the Mini-Fit Jr numbers are recalled, not confirmed (stage-2 file: [U]). Lead length: the layout gives the length column (stage 1 said 150 mm; the board connector is now at u 26.1, v 82.5, 15 mm inside the front edge). J1 receptacle terminals sit about 22 mm behind the skin (parts.yaml depth_behind_panel). M16 8-pole contacts may accept only 0.5 mm2 (power_budget.md [U]): open (OI-06).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-008.1 | CHS.J_HEAD1.1 | J1R.1 | HEAD_PWR_P | 20 | RD | SI | P1 | 160 |
| W-008.2 | CHS.J_HEAD1.2 | J1R.2 | HEAD_PWR_N | 20 | BK | SI | P1 | 160 |
| W-008.3 | CHS.J_HEAD1.3 | J1R.3 | HEAD_HTR_P | 18 | OG | SI | P2 | 160 |
| W-008.4 | CHS.J_HEAD1.4 | J1R.4 | HEAD_HTR_N | 18 | BN | SI | P2 | 160 |
| W-008.5 | CHS.J_HEAD1.5 | J1R.5 | HEAD_LOOP_OUT | 24 | GN | SI | P3 | 160 |
| W-008.6 | CHS.J_HEAD1.6 | J1R.6 | HEAD_LOOP_RET | 24 | GY | SI | P3 | 160 |
| W-008.7 | CHS.J_HEAD1.7 | J1R.7 | HEAD_PRES_ID | 24 | VT | SI | - | 160 |

### W-009  J2 chassis lead: main board J_HEAD2 to the J2 receptacle

* **Length:** 140 mm (routed path 47 mm + 2 x 25 mm termination/strain relief + 40 mm service loop = 137 mm, rounded up to 140 mm). *Estimated from layout, confirm on first build.*
* **Construction:** Custom shielded 4-pair cable: P1 RS-485 (120 ohm twisted pair, 1 Mbaud), P2 BUS_5V/BUS_GND, P3 SYNC (reserved), P4 J2_PRES + one spare core (pin 8, trimmed and insulated at both ends). Overall braid + jacket as W-008, OD <= 6.5 mm (parts.yaml).
* **Shield / bonding:** Overall braid 360 degrees on the J2R shell = chassis; OPEN at the J_HEAD2 end (GH has no shield pin).
* **Protection upstream:** BUS_5V: TPS2553 (RILIM 150 k [U]) 0.15-0.20 A, short-proof; contract limit 0.15 A; No fuse: signal conductors, series-limited (loop through 1.00 kohm; PRES_ID through the 4.70 kohm pull-up) [circuit.py]
* **Strain relief:** Receptacle end: cable clamped and clipped within 50 mm of the backshell; plug end: backshell strain-relief clamp (supplier part TBD); bend radius >= 40 mm (J1) / 35 mm (J2) per parts.yaml
* **Labels:** both ends, `W-009` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Termination 120 ohm is on the boards at both ends, bias at the chassis end only: this cable must not add any. AWG 26 matches connectors.yaml; ampacity for AWG 26 is not in sources (load <= 0.2 A).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-009.1 | CHS.J_HEAD2.1 | J2R.1 | RS485_DP | 26 | WH | FEP | P1 | 140 |
| W-009.2 | CHS.J_HEAD2.2 | J2R.2 | RS485_DN | 26 | BU | FEP | P1 | 140 |
| W-009.3 | CHS.J_HEAD2.3 | J2R.3 | BUS_5V | 26 | RD | FEP | P2 | 140 |
| W-009.4 | CHS.J_HEAD2.4 | J2R.4 | GND -> BUS_GND | 26 | BK | FEP | P2 | 140 |
| W-009.5 | CHS.J_HEAD2.5 | J2R.5 | SYNC_P | 26 | GN | FEP | P3 | 140 |
| W-009.6 | CHS.J_HEAD2.6 | J2R.6 | SYNC_N | 26 | GY | FEP | P3 | 140 |
| W-009.7 | CHS.J_HEAD2.7 | J2R.7 | J2_PRES | 26 | VT | FEP | P4 | 140 |

### W-010  CM5 5.1 V feed: main board J_CM5 to the CM5 carrier 40-pin header

* **Length:** 190 mm (routed path 87 mm + 2 x 25 mm termination/strain relief + 50 mm service loop = 187 mm, rounded up to 190 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 4 x AWG 20 silicone (two per pole), twisted as two pairs: J_CM5 stays Micro-Fit 3.0 and the harness goes to AWG 20 (chassis stage 2, STAGE2_CHANGE_REQUESTS.md IB-32: 2.5 A per contact, 80 mV total drop at 5.0 A for a 180 mm cable: 6 mohm conductors + 10 mohm contacts per pole at 5.0 A, contact figure [U]). The earlier AWG 18 needed a terminal that the 43025 housing does not take. Corridors left_gutter / left_bay_over_cm5. Carrier-end termination of AWG 20 on 0.1 inch header contacts is UNRESOLVED (TBD): alternative USB-C power-only pigtail (modules sheet).
* **Shield / bonding:** none
* **Protection upstream:** V5_CM5 eFuse TPS259470 (RILM 665 ohm) 5.0 A (4.5-5.5 A) on the 5 V side
* **Strain relief:** Wires bundled and clipped (P-clip) within 50 mm of the housing; housing latch + board peg; heavier gauge fixed before the lighter ones; no cable weight on the header
* **Labels:** both ends, `W-010` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** power_budget.md assumed 2 x AWG 18 per pole (5.2 mohm for 0.25 m): AWG 20 is 3.8 -> 6.0 mohm for this length, 11 mV more at 5 A (accepted by chassis stage 2, follow electronics/chassis_main/STAGE2_CHANGE_REQUESTS.md). Check on the bench before the harness is drawn: carrier back-feed/protection behaviour and usb_max_current_enable (modules sheet [U]). Pi header pins 2/4 = 5 V, 6/9 = GND per the modules sheet.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-010.1 | CHS.J_CM5.1 | CM5-HDR.2 | V5_CM5 | 20 | RD | SI | P1 | 190 |
| W-010.2 | CHS.J_CM5.2 | CM5-HDR.4 | V5_CM5 | 20 | RD | SI | P1 | 190 |
| W-010.3 | CHS.J_CM5.3 | CM5-HDR.6 | GND | 20 | BK | SI | P2 | 190 |
| W-010.4 | CHS.J_CM5.4 | CM5-HDR.9 | GND | 20 | BK | SI | P2 | 190 |

### W-011  LiDAR supply: main board J_LIDAR to the LiDAR

* **Length:** 290 mm (routed path 181 mm + 2 x 25 mm termination/strain relief + 50 mm service loop = 281 mm, rounded up to 290 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 2 x AWG 22 twisted pair. Corridor hump_side_left, over the hump side to the LiDAR pad (-150, 0, 150). LiDAR connector exit and pinout are UNVERIFIED (parts.yaml): TBD.
* **Shield / bonding:** none
* **Protection upstream:** V12_LIDAR eFuse TPS259470 (RILM 2.21 k) 1.51 A (+/-10 %)
* **Strain relief:** Wires bundled and clipped (P-clip) within 50 mm of the housing; housing latch + board peg; heavier gauge fixed before the lighter ones; no cable weight on the header; LiDAR end: strain relief per the LiDAR connector (TBD)
* **Labels:** both ends, `W-011` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** power_budget.md assumes 2 x 0.40 m AWG 22. Inrush against the 1.5 A limit is an open item (lidar.md).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-011.1 | CHS.J_LIDAR.1 | LIDAR-PWR.1 | V12_LIDAR | 22 | RD | SI | P1 | 290 |
| W-011.2 | CHS.J_LIDAR.2 | LIDAR-PWR.2 | GND | 22 | BK | SI | P1 | 290 |

### W-012  LiDAR Ethernet: LiDAR pigtail to the CM5 carrier RJ45 (purchased)

* **Length:** 260 mm (routed path 152 mm + 2 x 25 mm termination/strain relief + 50 mm service loop = 252 mm, rounded up to 260 mm). *Estimated from layout, confirm on first build.*
* **Construction:** Purchased LiDAR pigtail (RJ45 or M12, TBD) straight to the carrier RJ45; not routed through the main board (lidar.md). Wire colours and gauge are the vendor's (TBD). If the pigtail is shorter than the length column, use a shielded Cat5e/6 RJ45 coupler is NOT allowed (no extra connector in the chain): order the longer pigtail.
* **Shield / bonding:** Vendor cable shield (TBD)
* **Protection upstream:** None (passive sensor / device-internal)
* **Strain relief:** LiDAR end: per pigtail; RJ45 end: boot plus tie to the carrier bracket within 50 mm
* **Labels:** both ends, `W-012` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Length is the minimum pigtail length needed along corridors hump_side_left and left_bay_over_cm5. Pigtail length is not in the sources.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-012.1 | LIDAR-ETH.TXP | CM5-RJ45.1 | ETH_TXP | 26 | per pigtail | DEV | P1 | 260 |
| W-012.2 | LIDAR-ETH.TXN | CM5-RJ45.2 | ETH_TXN | 26 | per pigtail | DEV | P1 | 260 |
| W-012.3 | LIDAR-ETH.RXP | CM5-RJ45.3 | ETH_RXP | 26 | per pigtail | DEV | P2 | 260 |
| W-012.4 | LIDAR-ETH.RXN | CM5-RJ45.6 | ETH_RXN | 26 | per pigtail | DEV | P2 | 260 |

### W-013  USB 2.0 FS chassis link (MCU CDC): main board J_USB_MCU to the CM5 carrier USB-A

* **Length:** 190 mm (routed path 91 mm + 2 x 20 mm termination/strain relief + 50 mm service loop = 181 mm, rounded up to 190 mm). *Estimated from layout, confirm on first build.*
* **Construction:** USB 2.0 full-speed shielded cable: D+/D- 90 ohm twisted pair, VBUS conductor NOT fitted (board pin 1 is NC; the MCU is self-powered): leave the plug VBUS pin unconnected, AWG 28 conductors (connectors.yaml), foil/braid + drain. USB-A plug (part TBD) on the carrier end. No hub: one cable per port so a fault on one link cannot take the other down.
* **Shield / bonding:** Foil/braid: drain to board pin 5 (USB_SHLD -> 1 Mohm || 10 nF), plug shell bonds to the carrier shell. Two terminations by design: one DC-isolated by the RC at the board.
* **Protection upstream:** No fuse; USB ESD array at the connector; VBUS to the FT230X bridge from the carrier port
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; USB-A end: boot plus tie within 50 mm
* **Labels:** both ends, `W-013` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Both USB-A ports of the CM5-IO-BASE-A are used: no port for a wired service adapter (CCR-E10, IB-07 open).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-013.1 | CHS.J_USB_MCU.2 | CM5-USB1.2 | MCUC_USB_DM | 28 | WH | FEP | P1 | 190 |
| W-013.2 | CHS.J_USB_MCU.3 | CM5-USB1.3 | MCUC_USB_DP | 28 | GN | FEP | P1 | 190 |
| W-013.3 | CHS.J_USB_MCU.4 | CM5-USB1.4 | GND | 28 | BK | FEP | - | 190 |
| W-013.4 | CHS.J_USB_MCU.5 | CM5-USB1.SH | USB_SHLD | 28 | bare | FEP | - | 190 |

### W-014  USB 2.0 FS head link (FT230X): main board J_USB_HEAD to the CM5 carrier USB-A

* **Length:** 200 mm (routed path 100 mm + 2 x 20 mm termination/strain relief + 50 mm service loop = 190 mm, rounded up to 200 mm). *Estimated from layout, confirm on first build.*
* **Construction:** USB 2.0 full-speed shielded cable: D+/D- 90 ohm twisted pair, VBUS and GND conductors included, AWG 28 conductors (connectors.yaml), foil/braid + drain. USB-A plug (part TBD) on the carrier end. No hub: one cable per port so a fault on one link cannot take the other down.
* **Shield / bonding:** Foil/braid: drain to board pin 5 (USB_SHLD -> 1 Mohm || 10 nF), plug shell bonds to the carrier shell. Two terminations by design: one DC-isolated by the RC at the board.
* **Protection upstream:** No fuse; USB ESD array at the connector; VBUS to the FT230X bridge from the carrier port
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; USB-A end: boot plus tie within 50 mm
* **Labels:** both ends, `W-014` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Both USB-A ports of the CM5-IO-BASE-A are used: no port for a wired service adapter (CCR-E10, IB-07 open).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-014.1 | CHS.J_USB_HEAD.1 | CM5-USB2.1 | HUSB_VBUS | 28 | RD | FEP | - | 200 |
| W-014.2 | CHS.J_USB_HEAD.2 | CM5-USB2.2 | HUSBC_DM | 28 | WH | FEP | P1 | 200 |
| W-014.3 | CHS.J_USB_HEAD.3 | CM5-USB2.3 | HUSBC_DP | 28 | GN | FEP | P1 | 200 |
| W-014.4 | CHS.J_USB_HEAD.4 | CM5-USB2.4 | GND | 28 | BK | FEP | - | 200 |
| W-014.5 | CHS.J_USB_HEAD.5 | CM5-USB2.SH | USB_SHLD | 28 | bare | FEP | - | 200 |

### W-015  E-stop (two poles) to main board J_ESTOP

* **Length:** 220 mm (routed path 119 mm + 2 x 25 mm termination/strain relief + 50 mm service loop = 219 mm, rounded up to 220 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 4 x AWG 24 in two twisted pairs (pole A, pole B), yellow, in the safety loom. An external stop provision (E10) goes in series with BOTH poles at the J_ESTOP end (CCR/E10), no board change.
* **Shield / bonding:** none
* **Protection upstream:** Chain branch: F_CHAIN PTC 0.20 A hold / 0.40 A trip (circuit.py); relay coils and chain nodes 80 mA when latched
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing; P-clip within 50 mm; yellow sleeve/heat-shrink on the whole safety loom; kept in its own loom away from VBAT conductors (chassis_safety_chain.md fault #31); device end: Cable clamped/clipped within 50 mm of the device terminals; drip loop at panel devices; ferrules or the device's own terminal type (TBD)
* **Labels:** both ends, `W-015` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Each pole is its own pair so a short between poles needs two failures. Chain wire short to +12 V is an undetected latent fault: keep this loom away from VBAT conductors (chassis_safety_chain.md #8, #31). Contact-block terminal numbers TBD.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-015.1 | ESTOP-DEV.NC1-a | CHS.J_ESTOP.1 | CH_N1 | 24 | YE | SI | P1 | 220 |
| W-015.2 | ESTOP-DEV.NC1-b | CHS.J_ESTOP.2 | CH_N2 | 24 | YE | SI | P1 | 220 |
| W-015.3 | ESTOP-DEV.NC2-a | CHS.J_ESTOP.3 | COIL_RTN | 24 | YE | SI | P2 | 220 |
| W-015.4 | ESTOP-DEV.NC2-b | CHS.J_ESTOP.4 | GND | 24 | YE | SI | P2 | 220 |

### W-016  Mode selector OFF/SERVICE/RUN to main board J_MODE

* **Length:** 190 mm (routed path 85 mm + 2 x 25 mm termination/strain relief + 50 mm service loop = 185 mm, rounded up to 190 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 4 x AWG 24, two twisted pairs, yellow safety loom. J_MODE pins 5, 6 not wired.
* **Shield / bonding:** none
* **Protection upstream:** Chain branch: F_CHAIN PTC 0.20 A hold / 0.40 A trip (circuit.py); relay coils and chain nodes 80 mA when latched
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing; P-clip within 50 mm; yellow sleeve/heat-shrink on the whole safety loom; kept in its own loom away from VBAT conductors (chassis_safety_chain.md fault #31); device end: Cable clamped/clipped within 50 mm of the device terminals; drip loop at panel devices; ferrules or the device's own terminal type (TBD)
* **Labels:** both ends, `W-016` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** The selector assembly XB5AD33 has 2 NO blocks: the OFF-side block must be exchanged for a ZBE-102 NC (UNVERIFIED, modules sheet).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-016.1 | MODE-DEV.EN-a | CHS.J_MODE.1 | EN_SRC | 24 | YE | SI | P1 | 190 |
| W-016.2 | MODE-DEV.EN-b | CHS.J_MODE.2 | EN_SYS | 24 | YE | SI | P1 | 190 |
| W-016.3 | MODE-DEV.RUN-a | CHS.J_MODE.3 | CH_N0 | 24 | YE | SI | P2 | 190 |
| W-016.4 | MODE-DEV.RUN-b | CHS.J_MODE.4 | CH_N1 | 24 | YE | SI | P2 | 190 |

### W-017  HANDS-ON button and lamp to main board J_HANDS

* **Length:** 250 mm (routed path 147 mm + 2 x 25 mm termination/strain relief + 50 mm service loop = 247 mm, rounded up to 250 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 4 x AWG 24; contact pair yellow (safety loom), lamp pair PK/BU in the same loom (lamp +12 V comes from the chain node: keep it in the safety loom). J_HANDS pin 5 not wired.
* **Shield / bonding:** none
* **Protection upstream:** Chain branch: F_CHAIN PTC 0.20 A hold / 0.40 A trip (circuit.py); relay coils and chain nodes 80 mA when latched
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing; P-clip within 50 mm; yellow sleeve/heat-shrink on the whole safety loom; kept in its own loom away from VBAT conductors (chassis_safety_chain.md fault #31); device end: Cable clamped/clipped within 50 mm of the device terminals; drip loop at panel devices; ferrules or the device's own terminal type (TBD)
* **Labels:** both ends, `W-017` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Lamp 12 V, <= 20 mA. Exact XB5 reference TBD (UNVERIFIED).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-017.1 | HANDS-DEV.NC-a | CHS.J_HANDS.1 | CH_N2 | 24 | YE | SI | P1 | 250 |
| W-017.2 | HANDS-DEV.NC-b | CHS.J_HANDS.2 | CH_N3 | 24 | YE | SI | P1 | 250 |
| W-017.3 | HANDS-DEV.LAMP+ | CHS.J_HANDS.3 | HANDS_LAMP_P | 24 | PK | SI | P2 | 250 |
| W-017.4 | HANDS-DEV.LAMP- | CHS.J_HANDS.4 | HANDS_LAMP_K | 24 | BU | SI | P2 | 250 |

### W-018  REARM/Start button and lamp: main board J_BTN to the REARM button (left deck)

* **Length:** 240 mm (routed path 138 mm + 2 x 25 mm termination/strain relief + 50 mm service loop = 238 mm, rounded up to 240 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 24, direct to the REARM button, no splices (stage 2, S2-01: the Y-loom with SPL-BTN3 / SPL-BTN6 is gone). Yellow safety loom for pins 1-2. J_BTN pins 5 and 8 are not connected on the board any more (the PAUSE signals moved to J_PAUSE): leave those housing cavities empty.
* **Shield / bonding:** none
* **Protection upstream:** Chain branch: F_CHAIN PTC 0.20 A hold / 0.40 A trip (circuit.py); relay coils and chain nodes 80 mA when latched; lamps: V12_AUX PTC F_AUX 0.35 A hold (lamps, fan, external sounder)
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing; P-clip within 50 mm; yellow sleeve/heat-shrink on the whole safety loom; kept in its own loom away from VBAT conductors (chassis_safety_chain.md fault #31); device end: Cable clamped/clipped within 50 mm of the device terminals; drip loop at panel devices; ferrules or the device's own terminal type (TBD)
* **Labels:** both ends, `W-018` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** A short between J_BTN 1-2 permanently sets the set path: the latch must still not set after an element cycles (chassis_safety_chain.md procedure 7). J_BTN stays an 8-way CLIK-Mate so that its circuit count stays unique among the safety headers (S2-01a/b).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-018.1 | REARM-DEV.SET-a | CHS.J_BTN.1 | SET_CAP | 24 | YE | SI | P1 | 240 |
| W-018.2 | REARM-DEV.SET-b | CHS.J_BTN.2 | K1_SET | 24 | YE | SI | P1 | 240 |
| W-018.3 | REARM-DEV.AUX-a | CHS.J_BTN.3 | BTN_3V3 | 24 | RD | SI | - | 240 |
| W-018.4 | REARM-DEV.AUX-b | CHS.J_BTN.4 | REARM_BTN_RAW | 24 | WH | SI | - | 240 |
| W-018.5 | REARM-DEV.LAMP+ | CHS.J_BTN.6 | V12_AUX | 24 | PK | SI | - | 240 |
| W-018.6 | REARM-DEV.LAMP- | CHS.J_BTN.7 | LAMP_REARM_K | 24 | BU | SI | - | 240 |

### W-019  PAUSE/Stop button and lamp: main board J_PAUSE (JST GH 5-way) to the PAUSE button (right deck)

* **Length:** 170 mm (routed path 78 mm + 2 x 20 mm termination/strain relief + 50 mm service loop = 168 mm, rounded up to 170 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 4 x AWG 26 (JST GH contacts take AWG 26-30: was AWG 24 on the CLIK-Mate Y-branch), own cable, no splices, no crossing of the board (stage 2, S2-01e). J_PAUSE pin 5 not connected. PAUSE is program control, not a chain element (CCR-E12), so it is a signal-family connector and the cable is not in the yellow safety loom.
* **Shield / bonding:** none
* **Protection upstream:** V12_AUX PTC F_AUX 0.35 A hold (lamps, fan, external sounder); contact supply current-limited by R_PAUSE 1 kohm
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; device end: Cable clamped/clipped within 50 mm of the device terminals; drip loop at panel devices; ferrules or the device's own terminal type (TBD)
* **Labels:** both ends, `W-019` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** STAGE 2 (IB-33): J_PAUSE (BM05B-GHS-TBT) is in the rear-right GH row at u 101.4, v 14.2, next to the PAUSE button on the right deck. 5 circuits: the same count as J_USB_MCU / J_USB_HEAD (rear-left), so a mis-plug would put V12_AUX on a USB pin: separate by 80 mm on the board and by the printed label. The stage-1 290 mm Y-branch from J_BTN is replaced by this own cable.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-019.1 | PAUSE-DEV.NO-a | CHS.J_PAUSE.1 | PAUSE_3V3 | 26 | RD | FEP | - | 170 |
| W-019.2 | PAUSE-DEV.NO-b | CHS.J_PAUSE.2 | PAUSE_BTN_RAW | 26 | WH | FEP | - | 170 |
| W-019.3 | PAUSE-DEV.LAMP+ | CHS.J_PAUSE.3 | V12_AUX | 26 | PK | FEP | - | 170 |
| W-019.4 | PAUSE-DEV.LAMP- | CHS.J_PAUSE.4 | LAMP_PAUSE_K | 26 | BU | FEP | - | 170 |

### W-020  Head dock switch to main board J_DOCK

* **Length:** 270 mm (routed path 162 mm + 2 x 25 mm termination/strain relief + 50 mm service loop = 262 mm, rounded up to 270 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 2 x AWG 24 twisted pair, yellow. Corridor front_bay then along the left receiver channel to the switch behind the channel (-3, 87.5, 23). J_DOCK pin 2 not wired. Switch NC wired so the loop is closed only when the shoe presses it.
* **Shield / bonding:** none
* **Protection upstream:** Chain branch: F_CHAIN PTC 0.20 A hold / 0.40 A trip (circuit.py); relay coils and chain nodes 80 mA when latched
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing; P-clip within 50 mm; yellow sleeve/heat-shrink on the whole safety loom; kept in its own loom away from VBAT conductors (chassis_safety_chain.md fault #31); switch end: clip to the channel within 30 mm, keep clear of the shoe sweep (head removal sweep +x is free per layout_report.md)
* **Labels:** both ends, `W-020` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Dock switch is in the head-removal path region: protect the leads from the shoe tip (x = 4.0).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-020.1 | DOCK-DEV.COM | CHS.J_DOCK.1 | CH_N4 | 24 | YE | SI | P1 | 270 |
| W-020.2 | DOCK-DEV.NC | CHS.J_DOCK.3 | CH_N5 | 24 | YE | SI | P1 | 270 |

### W-021  Body bumper left to main board J_BUMP_L

* **Length:** 330 mm (routed path 225 mm + 2 x 25 mm termination/strain relief + 50 mm service loop = 325 mm, rounded up to 330 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 2 x AWG 24 twisted pair, yellow. Along the rear edge of the board to the left corner, corridor hump_side_left, then the left rear quarter.
* **Shield / bonding:** none
* **Protection upstream:** Chain branch: F_CHAIN PTC 0.20 A hold / 0.40 A trip (circuit.py); relay coils and chain nodes 80 mA when latched
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing; P-clip within 50 mm; yellow sleeve/heat-shrink on the whole safety loom; kept in its own loom away from VBAT conductors (chassis_safety_chain.md fault #31); switch end: clip to the bumper band bracket within 30 mm with a service loop that allows the band stroke (>= 8 mm)
* **Labels:** both ends, `W-021` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Bumper switch D2HW NO lead cut back and insulated. J_BUMP_L is at u 61.8, v 3.7 (centre-left of the rear edge): the cable runs 45 mm along the rear edge to the left corridor.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-021.1 | BUMP-L-DEV.COM | CHS.J_BUMP_L.1 | CH_N7 | 24 | YE | SI | P1 | 330 |
| W-021.2 | BUMP-L-DEV.NC | CHS.J_BUMP_L.2 | CH_N8A | 24 | YE | SI | P1 | 330 |

### W-022  Body bumper right to main board J_BUMP_R

* **Length:** 310 mm (routed path 201 mm + 2 x 25 mm termination/strain relief + 50 mm service loop = 301 mm, rounded up to 310 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 2 x AWG 24 twisted pair, yellow. Stage 2: J_BUMP_R is in the rear-right CLIK-Mate row, so the cable goes straight to the right corner and right_bay to the right rear quarter without crossing the board.
* **Shield / bonding:** none
* **Protection upstream:** Chain branch: F_CHAIN PTC 0.20 A hold / 0.40 A trip (circuit.py); relay coils and chain nodes 80 mA when latched
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing; P-clip within 50 mm; yellow sleeve/heat-shrink on the whole safety loom; kept in its own loom away from VBAT conductors (chassis_safety_chain.md fault #31); switch end: clip to the bumper band bracket within 30 mm with a service loop that allows the band stroke (>= 8 mm)
* **Labels:** both ends, `W-022` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** STAGE 2 (IB-33): J_BUMP_R moved to the rear-right cluster (u 134.8, v 3.7); the stage-1 430 mm board crossing is gone. J_BUMP_L/R are interchangeable (series contacts) and now on opposite sides. Bumper switch D2HW NO lead cut back and insulated.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-022.1 | BUMP-R-DEV.COM | CHS.J_BUMP_R.1 | CH_N8A | 24 | YE | SI | P1 | 310 |
| W-022.2 | BUMP-R-DEV.NC | CHS.J_BUMP_R.2 | CH_N8 | 24 | YE | SI | P1 | 310 |

### W-023  RR-PANEL: main board J_PANEL to RR-PANEL J1 (straight 1:1)

* **Length:** 180 mm (routed path 89 mm + 2 x 20 mm termination/strain relief + 50 mm service loop = 179 mm, rounded up to 180 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 10 x AWG 26, round multicore jacket, pin n to pin n (circuit.py checks the 1:1 order). The two GND conductors (3 and 10) share one colour: distinguished by the printed wire numbers. Corridor hump_side_left.
* **Shield / bonding:** none
* **Protection upstream:** V12_AUX PTC F_AUX 0.35 A hold (lamps, fan, external sounder); V3V3_CHS / V5_AUX bucks (LMR51610, 1 A device, peak limit ~1.4 A [U]); no per-branch fuse
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board
* **Labels:** both ends, `W-023` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** STAGE 2 (panel P1): RR-PANEL J1 (SM10B-GHS-TB side entry) and J2 are fitted on the TOP side at (30, 20.6) and (49.5, 20.6), mating face toward the v = 24 edge, so the cable leaves over that long edge (not along the long axis as in stage 1; the top allows 8 mm, the bottom only 3 mm, CCR-E08(d) option b). Which end of the panel (u) faces +y in the robot, and so which long edge (fore or aft) the cable leaves over, is NOT confirmed by mechanical: the 45 mm of end allowance and 50 mm service loop cover either choice (the difference is about 24 mm).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-023.1 | CHS.J_PANEL.1 | PNL.J1.1 | V5_AUX | 26 | RD | FEP | - | 180 |
| W-023.2 | CHS.J_PANEL.2 | PNL.J1.2 | V12_AUX | 26 | PK | FEP | - | 180 |
| W-023.3 | CHS.J_PANEL.3 | PNL.J1.3 | GND | 26 | BK | FEP | - | 180 |
| W-023.4 | CHS.J_PANEL.4 | PNL.J1.4 | LED_READY_K | 26 | GN | FEP | - | 180 |
| W-023.5 | CHS.J_PANEL.5 | PNL.J1.5 | LED_MOVING_K | 26 | BU | FEP | - | 180 |
| W-023.6 | CHS.J_PANEL.6 | PNL.J1.6 | LED_HOLD_K | 26 | VT | FEP | - | 180 |
| W-023.7 | CHS.J_PANEL.7 | PNL.J1.7 | LED_FAULT_K | 26 | GY | FEP | - | 180 |
| W-023.8 | CHS.J_PANEL.8 | PNL.J1.8 | LED_CHARGE_K | 26 | WH | FEP | - | 180 |
| W-023.9 | CHS.J_PANEL.9 | PNL.J1.9 | BUZ_N | 26 | BN | FEP | - | 180 |
| W-023.10 | CHS.J_PANEL.10 | PNL.J1.10 | GND | 26 | BK | FEP | - | 180 |

### W-024  OPTIONAL external 22 mm sounder: RR-PANEL J2 to the panel sounder

* **Length:** 100 mm (routed path 18 mm + 2 x 20 mm termination/strain relief + 40 mm service loop = 98 mm, rounded up to 100 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 2 x AWG 26 twisted pair (JST GH contacts take AWG 26-30). The sounder position is not in the sources (assumed within 100 mm of the annunciator).
* **Shield / bonding:** none
* **Protection upstream:** V12_AUX PTC F_AUX 0.35 A hold (lamps, fan, external sounder); sounder <= 100 mA
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; Cable clamped/clipped within 50 mm of the device terminals; drip loop at panel devices; ferrules or the device's own terminal type (TBD)
* **Labels:** both ends, `W-024` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Recommended by the panel circuit (on-board piezo about 60 dB at 1 m). No part verified (TBD).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-024.1 | PNL.J2.1 | SOUNDER-EXT.+ | V12_AUX | 26 | PK | SI | P1 | 100 |
| W-024.2 | PNL.J2.2 | SOUNDER-EXT.- | BUZ_N | 26 | BU | SI | P1 | 100 |

### W-030  ToF carrier CLIFF_FL (RR-TOF #0): main board J_TOF0 to the carrier J1

* **Length:** 190 mm (routed path 123 mm + 2 x 15 mm termination/strain relief + 30 mm service loop = 183 mm, rounded up to 190 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 in 3 twisted pairs (3V3/GND, SDA/SCL, XSHUT/GPIO1), overall foil shield with drain, thin silicone/PUR jacket (type TBD). The I2C bus is specified for <= 300 mm of cable (about 30 pF, modules sheet).
* **Shield / bonding:** Foil + drain: drain crimped in J_TOF0 pin 2 (GND) at the board end ONLY; carrier end open (cut back, insulated). Two wires in one 26-30 AWG crimp: allowed only if the contact datasheet permits (TBD).
* **Protection upstream:** V3V3_CHS / V5_AUX bucks (LMR51610, 1 A device, peak limit ~1.4 A [U]); no per-branch fuse
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; carrier end: cable clamp to the window bracket within 30 mm
* **Labels:** both ends, `W-030` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** ToF CLIFF_FL (firmware id 0). CONTRADICTION: layout_guidance.md calls these '300 mm unshielded sensor cables' while the harness specification here calls for shields; with a single drain at the board end the shield costs nothing electrically.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-030.1 | CHS.J_TOF0.1 | TOF0.J1.1 | TOF0_3V3 -> +3V3 | 28 | RD | FEP | P1 | 190 |
| W-030.2 | CHS.J_TOF0.2 | TOF0.J1.2 | GND | 28 | BK | FEP | P1 | 190 |
| W-030.3 | CHS.J_TOF0.3 | TOF0.J1.3 | TOF0_SDA_C -> SDA | 28 | GN | FEP | P2 | 190 |
| W-030.4 | CHS.J_TOF0.4 | TOF0.J1.4 | TOF0_SCL_C -> SCL | 28 | WH | FEP | P2 | 190 |
| W-030.5 | CHS.J_TOF0.5 | TOF0.J1.5 | TOF0_XSHUT_C -> XSHUT | 28 | VT | FEP | P3 | 190 |
| W-030.6 | CHS.J_TOF0.6 | TOF0.J1.6 | TOF0_GPIO1 -> GPIO1 | 28 | GY | FEP | P3 | 190 |

### W-031  ToF carrier CLIFF_FR (RR-TOF #1): main board J_TOF1 to the carrier J1

* **Length:** 190 mm (routed path 123 mm + 2 x 15 mm termination/strain relief + 30 mm service loop = 183 mm, rounded up to 190 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 in 3 twisted pairs (3V3/GND, SDA/SCL, XSHUT/GPIO1), overall foil shield with drain, thin silicone/PUR jacket (type TBD). The I2C bus is specified for <= 300 mm of cable (about 30 pF, modules sheet).
* **Shield / bonding:** Foil + drain: drain crimped in J_TOF1 pin 2 (GND) at the board end ONLY; carrier end open (cut back, insulated). Two wires in one 26-30 AWG crimp: allowed only if the contact datasheet permits (TBD).
* **Protection upstream:** V3V3_CHS / V5_AUX bucks (LMR51610, 1 A device, peak limit ~1.4 A [U]); no per-branch fuse
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; carrier end: cable clamp to the window bracket within 30 mm
* **Labels:** both ends, `W-031` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** ToF CLIFF_FR (firmware id 1). CONTRADICTION: layout_guidance.md calls these '300 mm unshielded sensor cables' while the harness specification here calls for shields; with a single drain at the board end the shield costs nothing electrically.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-031.1 | CHS.J_TOF1.1 | TOF1.J1.1 | TOF1_3V3 -> +3V3 | 28 | RD | FEP | P1 | 190 |
| W-031.2 | CHS.J_TOF1.2 | TOF1.J1.2 | GND | 28 | BK | FEP | P1 | 190 |
| W-031.3 | CHS.J_TOF1.3 | TOF1.J1.3 | TOF1_SDA_C -> SDA | 28 | GN | FEP | P2 | 190 |
| W-031.4 | CHS.J_TOF1.4 | TOF1.J1.4 | TOF1_SCL_C -> SCL | 28 | WH | FEP | P2 | 190 |
| W-031.5 | CHS.J_TOF1.5 | TOF1.J1.5 | TOF1_XSHUT_C -> XSHUT | 28 | VT | FEP | P3 | 190 |
| W-031.6 | CHS.J_TOF1.6 | TOF1.J1.6 | TOF1_GPIO1 -> GPIO1 | 28 | GY | FEP | P3 | 190 |

### W-032  ToF carrier CLIFF_RL (RR-TOF #2): main board J_TOF2 to the carrier J1

* **Length:** 290 mm (routed path 221 mm + 2 x 15 mm termination/strain relief + 30 mm service loop = 281 mm, rounded up to 290 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 in 3 twisted pairs (3V3/GND, SDA/SCL, XSHUT/GPIO1), overall foil shield with drain, thin silicone/PUR jacket (type TBD). The I2C bus is specified for <= 300 mm of cable (about 30 pF, modules sheet).
* **Shield / bonding:** Foil + drain: drain crimped in J_TOF2 pin 2 (GND) at the board end ONLY; carrier end open (cut back, insulated). Two wires in one 26-30 AWG crimp: allowed only if the contact datasheet permits (TBD).
* **Protection upstream:** V3V3_CHS / V5_AUX bucks (LMR51610, 1 A device, peak limit ~1.4 A [U]); no per-branch fuse
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; carrier end: cable clamp to the window bracket within 30 mm
* **Labels:** both ends, `W-032` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** ToF CLIFF_RL (firmware id 2). CONTRADICTION: layout_guidance.md calls these '300 mm unshielded sensor cables' while the harness specification here calls for shields; with a single drain at the board end the shield costs nothing electrically.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-032.1 | CHS.J_TOF2.1 | TOF2.J1.1 | TOF2_3V3 -> +3V3 | 28 | RD | FEP | P1 | 290 |
| W-032.2 | CHS.J_TOF2.2 | TOF2.J1.2 | GND | 28 | BK | FEP | P1 | 290 |
| W-032.3 | CHS.J_TOF2.3 | TOF2.J1.3 | TOF2_SDA_C -> SDA | 28 | GN | FEP | P2 | 290 |
| W-032.4 | CHS.J_TOF2.4 | TOF2.J1.4 | TOF2_SCL_C -> SCL | 28 | WH | FEP | P2 | 290 |
| W-032.5 | CHS.J_TOF2.5 | TOF2.J1.5 | TOF2_XSHUT_C -> XSHUT | 28 | VT | FEP | P3 | 290 |
| W-032.6 | CHS.J_TOF2.6 | TOF2.J1.6 | TOF2_GPIO1 -> GPIO1 | 28 | GY | FEP | P3 | 290 |

### W-033  ToF carrier CLIFF_RR (RR-TOF #3): main board J_TOF3 to the carrier J1

* **Length:** 290 mm (routed path 229 mm + 2 x 15 mm termination/strain relief + 30 mm service loop = 289 mm, rounded up to 290 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 in 3 twisted pairs (3V3/GND, SDA/SCL, XSHUT/GPIO1), overall foil shield with drain, thin silicone/PUR jacket (type TBD). The I2C bus is specified for <= 300 mm of cable (about 30 pF, modules sheet).
* **Shield / bonding:** Foil + drain: drain crimped in J_TOF3 pin 2 (GND) at the board end ONLY; carrier end open (cut back, insulated). Two wires in one 26-30 AWG crimp: allowed only if the contact datasheet permits (TBD).
* **Protection upstream:** V3V3_CHS / V5_AUX bucks (LMR51610, 1 A device, peak limit ~1.4 A [U]); no per-branch fuse
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; carrier end: cable clamp to the window bracket within 30 mm
* **Labels:** both ends, `W-033` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** ToF CLIFF_RR (firmware id 3). CONTRADICTION: layout_guidance.md calls these '300 mm unshielded sensor cables' while the harness specification here calls for shields; with a single drain at the board end the shield costs nothing electrically.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-033.1 | CHS.J_TOF3.1 | TOF3.J1.1 | TOF3_3V3 -> +3V3 | 28 | RD | FEP | P1 | 290 |
| W-033.2 | CHS.J_TOF3.2 | TOF3.J1.2 | GND | 28 | BK | FEP | P1 | 290 |
| W-033.3 | CHS.J_TOF3.3 | TOF3.J1.3 | TOF3_SDA_C -> SDA | 28 | GN | FEP | P2 | 290 |
| W-033.4 | CHS.J_TOF3.4 | TOF3.J1.4 | TOF3_SCL_C -> SCL | 28 | WH | FEP | P2 | 290 |
| W-033.5 | CHS.J_TOF3.5 | TOF3.J1.5 | TOF3_XSHUT_C -> XSHUT | 28 | VT | FEP | P3 | 290 |
| W-033.6 | CHS.J_TOF3.6 | TOF3.J1.6 | TOF3_GPIO1 -> GPIO1 | 28 | GY | FEP | P3 | 290 |

### W-034  ToF carrier LOOK_FL (RR-TOF #4): main board J_TOF4 to the carrier J1

* **Length:** 150 mm (routed path 84 mm + 2 x 15 mm termination/strain relief + 30 mm service loop = 144 mm, rounded up to 150 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 in 3 twisted pairs (3V3/GND, SDA/SCL, XSHUT/GPIO1), overall foil shield with drain, thin silicone/PUR jacket (type TBD). The I2C bus is specified for <= 300 mm of cable (about 30 pF, modules sheet).
* **Shield / bonding:** Foil + drain: drain crimped in J_TOF4 pin 2 (GND) at the board end ONLY; carrier end open (cut back, insulated). Two wires in one 26-30 AWG crimp: allowed only if the contact datasheet permits (TBD).
* **Protection upstream:** V3V3_CHS / V5_AUX bucks (LMR51610, 1 A device, peak limit ~1.4 A [U]); no per-branch fuse
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; carrier end: cable clamp to the window bracket within 30 mm
* **Labels:** both ends, `W-034` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** ToF LOOK_FL (firmware id 4). IB-34 (lead decision): the four oblique look-ahead sensors are two forward-looking (grip cheeks: tof_look_fl, tof_look_fr) and two rearward-looking (tail: tof_look_rl, tof_look_rr) as placed in frames.yaml; same connectors J_TOF4..J_TOF7, names LOOK_FL / LOOK_FR / LOOK_RL / LOOK_RR (the old names LOOK_LO / LI / RI / RO are retired). The contract and firmware pinmap still carry the old names until the firmware owner renames them. Sensor position from frames.yaml tof_look_fwd_left. CONTRADICTION: layout_guidance.md calls these '300 mm unshielded sensor cables' while the harness specification here calls for shields; with a single drain at the board end the shield costs nothing electrically.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-034.1 | CHS.J_TOF4.1 | TOF4.J1.1 | TOF4_3V3 -> +3V3 | 28 | RD | FEP | P1 | 150 |
| W-034.2 | CHS.J_TOF4.2 | TOF4.J1.2 | GND | 28 | BK | FEP | P1 | 150 |
| W-034.3 | CHS.J_TOF4.3 | TOF4.J1.3 | TOF4_SDA_C -> SDA | 28 | GN | FEP | P2 | 150 |
| W-034.4 | CHS.J_TOF4.4 | TOF4.J1.4 | TOF4_SCL_C -> SCL | 28 | WH | FEP | P2 | 150 |
| W-034.5 | CHS.J_TOF4.5 | TOF4.J1.5 | TOF4_XSHUT_C -> XSHUT | 28 | VT | FEP | P3 | 150 |
| W-034.6 | CHS.J_TOF4.6 | TOF4.J1.6 | TOF4_GPIO1 -> GPIO1 | 28 | GY | FEP | P3 | 150 |

### W-035  ToF carrier LOOK_FR (RR-TOF #5): main board J_TOF5 to the carrier J1

* **Length:** 280 mm (routed path 210 mm + 2 x 15 mm termination/strain relief + 30 mm service loop = 270 mm, rounded up to 280 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 in 3 twisted pairs (3V3/GND, SDA/SCL, XSHUT/GPIO1), overall foil shield with drain, thin silicone/PUR jacket (type TBD). The I2C bus is specified for <= 300 mm of cable (about 30 pF, modules sheet).
* **Shield / bonding:** Foil + drain: drain crimped in J_TOF5 pin 2 (GND) at the board end ONLY; carrier end open (cut back, insulated). Two wires in one 26-30 AWG crimp: allowed only if the contact datasheet permits (TBD).
* **Protection upstream:** V3V3_CHS / V5_AUX bucks (LMR51610, 1 A device, peak limit ~1.4 A [U]); no per-branch fuse
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; carrier end: cable clamp to the window bracket within 30 mm
* **Labels:** both ends, `W-035` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** ToF LOOK_FR (firmware id 5). IB-34 (lead decision): the four oblique look-ahead sensors are two forward-looking (grip cheeks: tof_look_fl, tof_look_fr) and two rearward-looking (tail: tof_look_rl, tof_look_rr) as placed in frames.yaml; same connectors J_TOF4..J_TOF7, names LOOK_FL / LOOK_FR / LOOK_RL / LOOK_RR (the old names LOOK_LO / LI / RI / RO are retired). The contract and firmware pinmap still carry the old names until the firmware owner renames them. Sensor position from frames.yaml tof_look_fwd_right. CONTRADICTION: layout_guidance.md calls these '300 mm unshielded sensor cables' while the harness specification here calls for shields; with a single drain at the board end the shield costs nothing electrically.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-035.1 | CHS.J_TOF5.1 | TOF5.J1.1 | TOF5_3V3 -> +3V3 | 28 | RD | FEP | P1 | 280 |
| W-035.2 | CHS.J_TOF5.2 | TOF5.J1.2 | GND | 28 | BK | FEP | P1 | 280 |
| W-035.3 | CHS.J_TOF5.3 | TOF5.J1.3 | TOF5_SDA_C -> SDA | 28 | GN | FEP | P2 | 280 |
| W-035.4 | CHS.J_TOF5.4 | TOF5.J1.4 | TOF5_SCL_C -> SCL | 28 | WH | FEP | P2 | 280 |
| W-035.5 | CHS.J_TOF5.5 | TOF5.J1.5 | TOF5_XSHUT_C -> XSHUT | 28 | VT | FEP | P3 | 280 |
| W-035.6 | CHS.J_TOF5.6 | TOF5.J1.6 | TOF5_GPIO1 -> GPIO1 | 28 | GY | FEP | P3 | 280 |

### W-036  ToF carrier LOOK_RL (RR-TOF #6): main board J_TOF6 to the carrier J1

* **Length:** 360 mm (routed path 296 mm + 2 x 15 mm termination/strain relief + 30 mm service loop = 356 mm, rounded up to 360 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 in 3 twisted pairs (3V3/GND, SDA/SCL, XSHUT/GPIO1), overall foil shield with drain, thin silicone/PUR jacket (type TBD). The I2C bus is specified for <= 300 mm of cable (about 30 pF, modules sheet).
* **Shield / bonding:** Foil + drain: drain crimped in J_TOF6 pin 2 (GND) at the board end ONLY; carrier end open (cut back, insulated). Two wires in one 26-30 AWG crimp: allowed only if the contact datasheet permits (TBD).
* **Protection upstream:** V3V3_CHS / V5_AUX bucks (LMR51610, 1 A device, peak limit ~1.4 A [U]); no per-branch fuse
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; carrier end: cable clamp to the window bracket within 30 mm
* **Labels:** both ends, `W-036` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** ToF LOOK_RL (firmware id 6). IB-34 (lead decision): the four oblique look-ahead sensors are two forward-looking (grip cheeks: tof_look_fl, tof_look_fr) and two rearward-looking (tail: tof_look_rl, tof_look_rr) as placed in frames.yaml; same connectors J_TOF4..J_TOF7, names LOOK_FL / LOOK_FR / LOOK_RL / LOOK_RR (the old names LOOK_LO / LI / RI / RO are retired). The contract and firmware pinmap still carry the old names until the firmware owner renames them. Sensor position from frames.yaml tof_look_rev_left. CONTRADICTION: layout_guidance.md calls these '300 mm unshielded sensor cables' while the harness specification here calls for shields; with a single drain at the board end the shield costs nothing electrically.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-036.1 | CHS.J_TOF6.1 | TOF6.J1.1 | TOF6_3V3 -> +3V3 | 28 | RD | FEP | P1 | 360 |
| W-036.2 | CHS.J_TOF6.2 | TOF6.J1.2 | GND | 28 | BK | FEP | P1 | 360 |
| W-036.3 | CHS.J_TOF6.3 | TOF6.J1.3 | TOF6_SDA_C -> SDA | 28 | GN | FEP | P2 | 360 |
| W-036.4 | CHS.J_TOF6.4 | TOF6.J1.4 | TOF6_SCL_C -> SCL | 28 | WH | FEP | P2 | 360 |
| W-036.5 | CHS.J_TOF6.5 | TOF6.J1.5 | TOF6_XSHUT_C -> XSHUT | 28 | VT | FEP | P3 | 360 |
| W-036.6 | CHS.J_TOF6.6 | TOF6.J1.6 | TOF6_GPIO1 -> GPIO1 | 28 | GY | FEP | P3 | 360 |

### W-037  ToF carrier LOOK_RR (RR-TOF #7): main board J_TOF7 to the carrier J1

* **Length:** 350 mm (routed path 284 mm + 2 x 15 mm termination/strain relief + 30 mm service loop = 344 mm, rounded up to 350 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 in 3 twisted pairs (3V3/GND, SDA/SCL, XSHUT/GPIO1), overall foil shield with drain, thin silicone/PUR jacket (type TBD). The I2C bus is specified for <= 300 mm of cable (about 30 pF, modules sheet).
* **Shield / bonding:** Foil + drain: drain crimped in J_TOF7 pin 2 (GND) at the board end ONLY; carrier end open (cut back, insulated). Two wires in one 26-30 AWG crimp: allowed only if the contact datasheet permits (TBD).
* **Protection upstream:** V3V3_CHS / V5_AUX bucks (LMR51610, 1 A device, peak limit ~1.4 A [U]); no per-branch fuse
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; carrier end: cable clamp to the window bracket within 30 mm
* **Labels:** both ends, `W-037` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** ToF LOOK_RR (firmware id 7). IB-34 (lead decision): the four oblique look-ahead sensors are two forward-looking (grip cheeks: tof_look_fl, tof_look_fr) and two rearward-looking (tail: tof_look_rl, tof_look_rr) as placed in frames.yaml; same connectors J_TOF4..J_TOF7, names LOOK_FL / LOOK_FR / LOOK_RL / LOOK_RR (the old names LOOK_LO / LI / RI / RO are retired). The contract and firmware pinmap still carry the old names until the firmware owner renames them. Sensor position from frames.yaml tof_look_rev_right. CONTRADICTION: layout_guidance.md calls these '300 mm unshielded sensor cables' while the harness specification here calls for shields; with a single drain at the board end the shield costs nothing electrically.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-037.1 | CHS.J_TOF7.1 | TOF7.J1.1 | TOF7_3V3 -> +3V3 | 28 | RD | FEP | P1 | 350 |
| W-037.2 | CHS.J_TOF7.2 | TOF7.J1.2 | GND | 28 | BK | FEP | P1 | 350 |
| W-037.3 | CHS.J_TOF7.3 | TOF7.J1.3 | TOF7_SDA_C -> SDA | 28 | GN | FEP | P2 | 350 |
| W-037.4 | CHS.J_TOF7.4 | TOF7.J1.4 | TOF7_SCL_C -> SCL | 28 | WH | FEP | P2 | 350 |
| W-037.5 | CHS.J_TOF7.5 | TOF7.J1.5 | TOF7_XSHUT_C -> XSHUT | 28 | VT | FEP | P3 | 350 |
| W-037.6 | CHS.J_TOF7.6 | TOF7.J1.6 | TOF7_GPIO1 -> GPIO1 | 28 | GY | FEP | P3 | 350 |

### W-038  ToF carrier REAR_L (RR-TOF #8): main board J_TOF8 to the carrier J1

* **Length:** 270 mm (routed path 210 mm + 2 x 15 mm termination/strain relief + 30 mm service loop = 270 mm, rounded up to 270 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 in 3 twisted pairs (3V3/GND, SDA/SCL, XSHUT/GPIO1), overall foil shield with drain, thin silicone/PUR jacket (type TBD). The I2C bus is specified for <= 300 mm of cable (about 30 pF, modules sheet).
* **Shield / bonding:** Foil + drain: drain crimped in J_TOF8 pin 2 (GND) at the board end ONLY; carrier end open (cut back, insulated). Two wires in one 26-30 AWG crimp: allowed only if the contact datasheet permits (TBD).
* **Protection upstream:** V3V3_CHS / V5_AUX bucks (LMR51610, 1 A device, peak limit ~1.4 A [U]); no per-branch fuse
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; carrier end: cable clamp to the window bracket within 30 mm
* **Labels:** both ends, `W-038` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** ToF REAR_L (firmware id 8). CONTRADICTION: layout_guidance.md calls these '300 mm unshielded sensor cables' while the harness specification here calls for shields; with a single drain at the board end the shield costs nothing electrically.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-038.1 | CHS.J_TOF8.1 | TOF8.J1.1 | TOF8_3V3 -> +3V3 | 28 | RD | FEP | P1 | 270 |
| W-038.2 | CHS.J_TOF8.2 | TOF8.J1.2 | GND | 28 | BK | FEP | P1 | 270 |
| W-038.3 | CHS.J_TOF8.3 | TOF8.J1.3 | TOF8_SDA_C -> SDA | 28 | GN | FEP | P2 | 270 |
| W-038.4 | CHS.J_TOF8.4 | TOF8.J1.4 | TOF8_SCL_C -> SCL | 28 | WH | FEP | P2 | 270 |
| W-038.5 | CHS.J_TOF8.5 | TOF8.J1.5 | TOF8_XSHUT_C -> XSHUT | 28 | VT | FEP | P3 | 270 |
| W-038.6 | CHS.J_TOF8.6 | TOF8.J1.6 | TOF8_GPIO1 -> GPIO1 | 28 | GY | FEP | P3 | 270 |

### W-039  ToF carrier REAR_C (RR-TOF #9): main board J_TOF9 to the carrier J1

* **Length:** 290 mm (routed path 225 mm + 2 x 15 mm termination/strain relief + 30 mm service loop = 285 mm, rounded up to 290 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 in 3 twisted pairs (3V3/GND, SDA/SCL, XSHUT/GPIO1), overall foil shield with drain, thin silicone/PUR jacket (type TBD). The I2C bus is specified for <= 300 mm of cable (about 30 pF, modules sheet).
* **Shield / bonding:** Foil + drain: drain crimped in J_TOF9 pin 2 (GND) at the board end ONLY; carrier end open (cut back, insulated). Two wires in one 26-30 AWG crimp: allowed only if the contact datasheet permits (TBD).
* **Protection upstream:** V3V3_CHS / V5_AUX bucks (LMR51610, 1 A device, peak limit ~1.4 A [U]); no per-branch fuse
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; carrier end: cable clamp to the window bracket within 30 mm
* **Labels:** both ends, `W-039` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** ToF REAR_C (firmware id 9). CONTRADICTION: layout_guidance.md calls these '300 mm unshielded sensor cables' while the harness specification here calls for shields; with a single drain at the board end the shield costs nothing electrically.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-039.1 | CHS.J_TOF9.1 | TOF9.J1.1 | TOF9_3V3 -> +3V3 | 28 | RD | FEP | P1 | 290 |
| W-039.2 | CHS.J_TOF9.2 | TOF9.J1.2 | GND | 28 | BK | FEP | P1 | 290 |
| W-039.3 | CHS.J_TOF9.3 | TOF9.J1.3 | TOF9_SDA_C -> SDA | 28 | GN | FEP | P2 | 290 |
| W-039.4 | CHS.J_TOF9.4 | TOF9.J1.4 | TOF9_SCL_C -> SCL | 28 | WH | FEP | P2 | 290 |
| W-039.5 | CHS.J_TOF9.5 | TOF9.J1.5 | TOF9_XSHUT_C -> XSHUT | 28 | VT | FEP | P3 | 290 |
| W-039.6 | CHS.J_TOF9.6 | TOF9.J1.6 | TOF9_GPIO1 -> GPIO1 | 28 | GY | FEP | P3 | 290 |

### W-040  ToF carrier REAR_R (RR-TOF #10): main board J_TOF10 to the carrier J1

* **Length:** 290 mm (routed path 223 mm + 2 x 15 mm termination/strain relief + 30 mm service loop = 283 mm, rounded up to 290 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 in 3 twisted pairs (3V3/GND, SDA/SCL, XSHUT/GPIO1), overall foil shield with drain, thin silicone/PUR jacket (type TBD). The I2C bus is specified for <= 300 mm of cable (about 30 pF, modules sheet).
* **Shield / bonding:** Foil + drain: drain crimped in J_TOF10 pin 2 (GND) at the board end ONLY; carrier end open (cut back, insulated). Two wires in one 26-30 AWG crimp: allowed only if the contact datasheet permits (TBD).
* **Protection upstream:** V3V3_CHS / V5_AUX bucks (LMR51610, 1 A device, peak limit ~1.4 A [U]); no per-branch fuse
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board; carrier end: cable clamp to the window bracket within 30 mm
* **Labels:** both ends, `W-040` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** ToF REAR_R (firmware id 10). CONTRADICTION: layout_guidance.md calls these '300 mm unshielded sensor cables' while the harness specification here calls for shields; with a single drain at the board end the shield costs nothing electrically.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-040.1 | CHS.J_TOF10.1 | TOF10.J1.1 | TOF10_3V3 -> +3V3 | 28 | RD | FEP | P1 | 290 |
| W-040.2 | CHS.J_TOF10.2 | TOF10.J1.2 | GND | 28 | BK | FEP | P1 | 290 |
| W-040.3 | CHS.J_TOF10.3 | TOF10.J1.3 | TOF10_SDA_C -> SDA | 28 | GN | FEP | P2 | 290 |
| W-040.4 | CHS.J_TOF10.4 | TOF10.J1.4 | TOF10_SCL_C -> SCL | 28 | WH | FEP | P2 | 290 |
| W-040.5 | CHS.J_TOF10.5 | TOF10.J1.5 | TOF10_XSHUT_C -> XSHUT | 28 | VT | FEP | P3 | 290 |
| W-040.6 | CHS.J_TOF10.6 | TOF10.J1.6 | TOF10_GPIO1 -> GPIO1 | 28 | GY | FEP | P3 | 290 |

### W-041  Chassis/bay heater with its bimetal cut-out: main board J_HTR to the heater plate

* **Length:** 220 mm (routed path 113 mm + 2 x 25 mm termination/strain relief + 50 mm service loop = 213 mm, rounded up to 220 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 3 x AWG 20 silicone. The independent bimetal cut-out is in series in this harness, on the heater plate (CCR-E08(e)); element 7.2 ohm, 20 W. The cut-out must be rated for >= 3.04 A at 14.4 V DC (TBD part).
* **Shield / bonding:** none
* **Protection upstream:** CHS_HTR eFuse TPS259470 (RILM 1.10 k) 3.04 A; series bimetal cut-out in this harness (rating TBD)
* **Strain relief:** Wires bundled and clipped (P-clip) within 50 mm of the housing; housing latch + board peg; heavier gauge fixed before the lighter ones; no cable weight on the header; plate end: leads secured with high-temperature tape/clips to the plate within 30 mm
* **Labels:** both ends, `W-041` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Heater pad leads are not in the sources. The return conductor goes to GND (not a separate heater return net on this board).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-041.1 | CHS.J_HTR.1 | HTR-CHS.1 | CHS_HTR_P | 20 | OG | SI | - | 220 |
| W-041.2 | HTR-CHS.2 | CUT-CHS.1 | CHS_HTR_MID | 20 | BN | SI | - | 220 |
| W-041.3 | CUT-CHS.2 | CHS.J_HTR.2 | GND | 20 | BN | SI | - | 220 |

### W-042  Bay NTC and pack-surface NTC to main board J_NTC

* **Length:** 220 mm (routed path 126 mm + 2 x 20 mm termination/strain relief + 50 mm service loop = 216 mm, rounded up to 220 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 2 twisted pairs AWG 26. NTCs 10 kohm B3435 (parts TBD). The two GND returns stay separate (pins 2 and 4) so the pair stays Kelvin.
* **Shield / bonding:** none
* **Protection upstream:** No fuse; 10 kohm pull-up to the 3.000 V reference (<= 0.3 mA)
* **Strain relief:** Adhesive-lined heat-shrink boot over the housing and the first 15 mm of jacket; P-clip or saddle tie within 60 mm; no tension on crimps; cable leaves sideways below 12 mm on the board
* **Labels:** both ends, `W-042` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** NTC positions are not given beyond 'beside the heater' and 'pack surface'; length is for the bay near the heater plate.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-042.1 | NTC-BAY.a | CHS.J_NTC.1 | NTC_BAY | 26 | WH | FEP | P1 | 220 |
| W-042.2 | NTC-BAY.b | CHS.J_NTC.2 | GND | 26 | BK | FEP | P1 | 220 |
| W-042.3 | NTC-PACKSURF.a | CHS.J_NTC.3 | NTC_PACK | 26 | GN | FEP | P2 | 220 |
| W-042.4 | NTC-PACKSURF.b | CHS.J_NTC.4 | GND | 26 | BK | FEP | P2 | 220 |

### W-101  Head J1 captive pigtail: head board J2001 to the J1 plug

* **Length:** 290 mm (inside the head: board J2001 (u 86.8, v 10.6, mating face rearward, stage 2) to the rear-wall port = 17.6 mm path + 2 x 25 mm + 20 mm; outside: 200 mm free length (mechanical_interfaces.md allows 150..200; straight-line port to plug rear is 142 mm, plus bends at 40 mm radius, so 150 mm is too short)). *Estimated from layout, confirm on first build.*
* **Construction:** Same construction as W-008 (shielded multicore, twisted pairs P1 power, P2 heater, P3 loop), captive: sealed strain relief in the head rear wall at (71.7, 76.2, 39) (CR-M03, moved from y 87.5), cable leaves toward -x/+z, clipped to the shoe root. OD <= 7.5 mm.
* **Shield / bonding:** Braid: 360 degrees to the J1 plug backshell (-> chassis through the mated shell) AND drain wire to the head board pad TP2004. This is the contract: hard bond at the chassis, 1 Mohm || 10 nF at the head.
* **Protection upstream:** HEAD_PWR eFuse TPS259470 (RILM 2.21 k) 1.51 A; contract limit 1.5 A; head side TPS26600 eFuse 1.0 A (pins 1-2); HEAD_HTR eFuse TPS259470 (RILM 825 ohm) 4.05 A (3.6-4.4 A), contract limit 4.0 A; independent low-side bimetal cut-out on the head heater (pins 3-4); No fuse: signal conductors, series-limited (loop through 1.00 kohm; PRES_ID through the 4.70 kohm pull-up) [circuit.py]
* **Strain relief:** Sealed strain-relief gland in the rear wall (inside the head wall); plug backshell clamp; clip to the shoe root; head cover 0.9 mm clearance must not trap the cable
* **Labels:** both ends, `W-101` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** IB-36 (head pigtail length): the harness specifies 200 mm free length outside the head plus about 90 mm inside = 290 mm, against the 2 x 0.35 m of the head power_budget.md (head side calculation); the geometry-based 200 mm follows mechanical_interfaces.md (150..200 mm) and the 142 mm straight-line check: the shorter pigtail lowers the resistance (conservative for the budget). The loop is potential-free: no conductor of pins 5-6 may touch the shield or any other pin. J2001 and J2601 sit side by side at the rear edge (stage 2, S2-L5: J2601 u 50.2..72.0, J2001 u 73.0..100.7) with the mating faces rearward; this needs CR-M02/CR-M03 (not yet accepted by head mechanical, IB-52). CCR-HE-02: J2001 header height 8 mm zone open.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-101.1 | HEAD.J2001.1 | J1P.1 | HEAD_PWR_P | 20 | RD | SI | P1 | 290 |
| W-101.2 | HEAD.J2001.2 | J1P.2 | HEAD_PWR_N | 20 | BK | SI | P1 | 290 |
| W-101.3 | HEAD.J2001.3 | J1P.3 | HEAD_HTR_P | 18 | OG | SI | P2 | 290 |
| W-101.4 | HEAD.J2001.4 | J1P.4 | HEAD_HTR_N | 18 | BN | SI | P2 | 290 |
| W-101.5 | HEAD.J2001.5 | J1P.5 | HEAD_LOOP_OUT | 24 | GN | SI | P3 | 290 |
| W-101.6 | HEAD.J2001.6 | J1P.6 | HEAD_LOOP_RET | 24 | GY | SI | P3 | 290 |
| W-101.7 | HEAD.J2001.7 | J1P.7 | HEAD_PRES_ID | 24 | VT | SI | - | 290 |
| W-101.S | HEAD.TP2004.1 | J1P.SH | SHLD_J1 | 24 | bare | SI | - | 130 |

### W-102  Head J2 captive pigtail: head board J2501 to the J2 plug (plug link pin 7 to pin 4)

* **Length:** 300 mm (inside the head: board J2501 (u 262.3, v 5.2) to the rear-wall port (u 250.5) = about 21 mm + 2 x 25 mm + 20 mm; outside: 200 mm free length (150..200 allowed; port to plug rear 142 mm straight)). *Estimated from layout, confirm on first build.*
* **Construction:** Same as W-009: shielded 4-pair, 7 conductors + link. Captive, sealed strain relief at (71.7, -87.5, 39).
* **Shield / bonding:** As W-101 with TP2501 / J2P backshell.
* **Protection upstream:** BUS_5V: TPS2553 (RILIM 150 k [U]) 0.15-0.20 A, short-proof; contract limit 0.15 A; No fuse: signal conductors, series-limited (loop through 1.00 kohm; PRES_ID through the 4.70 kohm pull-up) [circuit.py]
* **Strain relief:** Sealed strain-relief gland in the rear wall; plug backshell clamp; clip to the shoe root
* **Labels:** both ends, `W-102` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** J2_PRES link: pin 7 and pin 4 are linked inside the plug; the chassis sees J2_PRES low when mated.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-102.1 | HEAD.J2501.1 | J2P.1 | RS485_DP | 26 | WH | FEP | P1 | 300 |
| W-102.2 | HEAD.J2501.2 | J2P.2 | RS485_DN | 26 | BU | FEP | P1 | 300 |
| W-102.3 | HEAD.J2501.3 | J2P.3 | BUS_5V | 26 | RD | FEP | P2 | 300 |
| W-102.4 | HEAD.J2501.4 | J2P.4 | BUS_GND | 26 | BK | FEP | P2 | 300 |
| W-102.5 | HEAD.J2501.5 | J2P.5 | SYNC_P | 26 | GN | FEP | P3 | 300 |
| W-102.6 | HEAD.J2501.6 | J2P.6 | SYNC_N | 26 | GY | FEP | P3 | 300 |
| W-102.7 | HEAD.J2501.7 | J2P.7 | J2_PRES | 26 | VT | FEP | P4 | 300 |
| W-102.L | J2P.7 | J2P.4 | J2_PRES -> BUS_GND | 26 | VT | FEP | - | 20 |
| W-102.S | HEAD.TP2501.1 | J2P.SH | SHLD_J2 | 26 | bare | FEP | - | 110 |

### W-103  Head heater film, bimetal cut-out and spreader NTC: head board J2601 to the heater assembly

* **Length:** 100 mm (routed path 28 mm + 2 x 20 mm termination/strain relief + 30 mm service loop = 98 mm, rounded up to 100 mm). *Estimated from layout, confirm on first build.*
* **Construction:** Heater circuit AWG 18 pair (supply and return twisted) plus AWG 24 sense and an AWG 26 NTC pair. Assembly (per J2601): HTR_SW -> 4.8 ohm element -> CUTOUT_SENSE -> bimetal cut-out (low side) -> HEAD_HTR_N. Tail comes up the rear chimney at y = +87.5. J2601 pin 6 not wired.
* **Shield / bonding:** none inside the shielded head
* **Protection upstream:** HEAD_HTR eFuse TPS259470 (RILM 825 ohm) 4.05 A (3.6-4.4 A), contract limit 4.0 A; independent low-side bimetal cut-out on the head heater; cut-out status reads 'tripped' when the feed is off (by design)
* **Strain relief:** Leads clipped to the spreader with Kapton/high-temperature tape within 20 mm of the film tail
* **Labels:** both ends, `W-103` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Heater film, cut-out and NTC parts are not in the sources (TBD). CCR-HE-02 (connector height) open.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-103.1 | HEAD.J2601.1 | HEAD-HEATER.1 | HTR_SW | 18 | OG | SI | - | 100 |
| W-103.2 | HEAD.J2601.3 | SPL-HCUT.1 | HTR_CUT | 24 | VT | SI | - | 100 |
| W-103.3 | HEAD-HEATER.2 | SPL-HCUT.2 | HTR_CUT | 18 | BN | SI | - | 100 |
| W-103.4 | SPL-HCUT.3 | HEAD-CUTOUT.1 | HTR_CUT | 18 | BN | SI | - | 100 |
| W-103.5 | HEAD-CUTOUT.2 | HEAD.J2601.2 | HEAD_HTR_N | 18 | BN | SI | - | 100 |
| W-103.6 | NTC-SPR.a | HEAD.J2601.4 | NTC_HTR | 24 | WH | FEP | P1 | 100 |
| W-103.7 | NTC-SPR.b | HEAD.J2601.5 | GND | 24 | BK | FEP | P1 | 100 |

### W-104  Head rail switch front (series element of the interlock loop): head board J2002 to the switch

* **Length:** 90 mm (routed path 21 mm + 2 x 15 mm termination/strain relief + 30 mm service loop = 81 mm, rounded up to 90 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 2 x AWG 26 twisted pair in the front wall channel (JST GH contacts take AWG 26-30). Connector pins 3 and 4 (AUX_N/AUX_GND zone read-back) are NOT wired: the D2HW is single-pole and its NO throw is not potential-free from the loop (CCR-HE-04). The NO lead is cut back and insulated.
* **Shield / bonding:** none (inside the shielded head)
* **Protection upstream:** No fuse: signal conductors, series-limited (loop through 1.00 kohm; PRES_ID through the 4.70 kohm pull-up) [circuit.py]
* **Strain relief:** Clip in the front wall channel every 50 mm; switch end clipped within 20 mm
* **Labels:** both ends, `W-104` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Loop is a potential-free series chain; see the loop diagram in cables.md. Stage 2: the connector order on the board (J2004 at u 144.6, J2002 at u 154.5, J2003 at u 171.5) puts the RIGHT-rail connector on the left of the centre line and the LEFT-rail connector on the right, so cables W-105 and W-106 cross once in the front channel (about 30 mm of extra length); the zone read-back is not available in rev A, so swapping the left and right switch cables between J2003 and J2004 would cost nothing functionally (it would only exchange the idle BUMP_ZONE_L/R labels) and avoids the crossing: decision for head electronics, not taken here.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-104.1 | RAIL-F.COM | HEAD.J2002.1 | HEAD_LOOP_OUT | 26 | GN | FEP | P1 | 90 |
| W-104.2 | RAIL-F.NC | HEAD.J2002.2 | LOOP_A | 26 | GY | FEP | P1 | 90 |

### W-105  Head rail switch left (series element of the interlock loop): head board J2003 to the switch

* **Length:** 290 mm (routed path 221 mm + 2 x 15 mm termination/strain relief + 30 mm service loop = 281 mm, rounded up to 290 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 2 x AWG 26 twisted pair in the front wall channel (JST GH contacts take AWG 26-30). Connector pins 3 and 4 (AUX_N/AUX_GND zone read-back) are NOT wired: the D2HW is single-pole and its NO throw is not potential-free from the loop (CCR-HE-04). The NO lead is cut back and insulated.
* **Shield / bonding:** none (inside the shielded head)
* **Protection upstream:** No fuse: signal conductors, series-limited (loop through 1.00 kohm; PRES_ID through the 4.70 kohm pull-up) [circuit.py]
* **Strain relief:** Clip in the front wall channel every 50 mm; switch end clipped within 20 mm
* **Labels:** both ends, `W-105` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Loop is a potential-free series chain; see the loop diagram in cables.md. Stage 2: the connector order on the board (J2004 at u 144.6, J2002 at u 154.5, J2003 at u 171.5) puts the RIGHT-rail connector on the left of the centre line and the LEFT-rail connector on the right, so cables W-105 and W-106 cross once in the front channel (about 30 mm of extra length); the zone read-back is not available in rev A, so swapping the left and right switch cables between J2003 and J2004 would cost nothing functionally (it would only exchange the idle BUMP_ZONE_L/R labels) and avoids the crossing: decision for head electronics, not taken here.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-105.1 | RAIL-L.COM | HEAD.J2003.1 | LOOP_A | 26 | GN | FEP | P1 | 290 |
| W-105.2 | RAIL-L.NC | HEAD.J2003.2 | LOOP_B | 26 | GY | FEP | P1 | 290 |

### W-106  Head rail switch right (series element of the interlock loop): head board J2004 to the switch

* **Length:** 290 mm (routed path 230 mm + 2 x 15 mm termination/strain relief + 30 mm service loop = 290 mm, rounded up to 290 mm). *Estimated from layout, confirm on first build.*
* **Construction:** 2 x AWG 26 twisted pair in the front wall channel (JST GH contacts take AWG 26-30). Connector pins 3 and 4 (AUX_N/AUX_GND zone read-back) are NOT wired: the D2HW is single-pole and its NO throw is not potential-free from the loop (CCR-HE-04). The NO lead is cut back and insulated.
* **Shield / bonding:** none (inside the shielded head)
* **Protection upstream:** No fuse: signal conductors, series-limited (loop through 1.00 kohm; PRES_ID through the 4.70 kohm pull-up) [circuit.py]
* **Strain relief:** Clip in the front wall channel every 50 mm; switch end clipped within 20 mm
* **Labels:** both ends, `W-106` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Loop is a potential-free series chain; see the loop diagram in cables.md. Stage 2: the connector order on the board (J2004 at u 144.6, J2002 at u 154.5, J2003 at u 171.5) puts the RIGHT-rail connector on the left of the centre line and the LEFT-rail connector on the right, so cables W-105 and W-106 cross once in the front channel (about 30 mm of extra length); the zone read-back is not available in rev A, so swapping the left and right switch cables between J2003 and J2004 would cost nothing functionally (it would only exchange the idle BUMP_ZONE_L/R labels) and avoids the crossing: decision for head electronics, not taken here.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-106.1 | RAIL-R.COM | HEAD.J2004.1 | LOOP_B | 26 | GN | FEP | P1 | 290 |
| W-106.2 | RAIL-R.NC | HEAD.J2004.2 | LOOP_C | 26 | GY | FEP | P1 | 290 |

### W-107  Head lid (light-leak) interlock switch: head board J2201 to the lid switch

* **Length:** 200 mm (PLACEHOLDER: switch position and part are not in the sources; 200 mm assumed (J2201 is on the front edge, board_envelopes BIAS zone)). *Estimated from layout, confirm on first build.*
* **Construction:** 2 x AWG 26 twisted pair. Bench bypass is the solder jumper JP2201 on the board (record in the build sheet).
* **Shield / bonding:** none
* **Protection upstream:** No fuse: signal conductors, series-limited (loop through 1.00 kohm; PRES_ID through the 4.70 kohm pull-up) [circuit.py]
* **Strain relief:** Clip every 50 mm; switch end clipped within 20 mm
* **Labels:** both ends, `W-107` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Switch type/location TBD - not in sources.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-107.1 | LID-SW.a | HEAD.J2201.1 | LID_IN | 26 | WH | FEP | P1 | 200 |
| W-107.2 | LID-SW.b | HEAD.J2201.2 | GND | 26 | BK | FEP | P1 | 200 |

### W-108  Head lane 0 auxiliary pigtail: head board J1001 to the SiPM carrier aux

* **Length:** 35 mm (mechanical interfaces: pigtails < 35 mm from the rear edge into the chimney (drop 17-25 mm + lateral offset from the GH-6 at lane du -1.80 to the carrier at the lane centre = 1.8 mm, so at most 27 mm routed + 7 mm termination): 35 mm cut length is the maximum (stage 2: JST GH-6 J1001/J1101/J1201/J1301 at the rear edge, u 29.9 / 117.5 / 204.9 / 292.4, v 5.0, S2-L3)). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 flat/round micro-cable, 3 twisted pairs (NTC, LED, 3V3). The lane SiPM NTC (10 kohm within 5 mm of the SiPM, CCR-HE-06) is the lane temperature sensor. LED and 3V3 pins feed an optional pulser/active sensor.
* **Shield / bonding:** none; inside the lane shield can region: keep leads < 35 mm
* **Protection upstream:** No fuse; 10 kohm pull-up to the 3.000 V reference (<= 0.3 mA)
* **Strain relief:** Adhesive/tack at the carrier end; no loop > 10 mm (pickup, IB-23)
* **Labels:** both ends, `W-108` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Carrier connector TBD (not in sources).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-108.1 | CARR-AUX0.1 | HEAD.J1001.1 | NTC_SIPM0 | 28 | WH | FEP | P1 | 35 |
| W-108.2 | CARR-AUX0.2 | HEAD.J1001.2 | GND | 28 | BK | FEP | P1 | 35 |
| W-108.3 | CARR-AUX0.3 | HEAD.J1001.3 | L0_LED_A | 28 | GN | FEP | P2 | 35 |
| W-108.4 | CARR-AUX0.4 | HEAD.J1001.4 | L0_LED_K | 28 | BN | FEP | P2 | 35 |
| W-108.5 | CARR-AUX0.5 | HEAD.J1001.5 | L0_AUX3V3 | 28 | RD | FEP | P3 | 35 |
| W-108.6 | CARR-AUX0.6 | HEAD.J1001.6 | GND | 28 | BK | FEP | P3 | 35 |

### W-109  Head lane 1 auxiliary pigtail: head board J1101 to the SiPM carrier aux

* **Length:** 35 mm (mechanical interfaces: pigtails < 35 mm from the rear edge into the chimney (drop 17-25 mm + lateral offset from the GH-6 at lane du -1.80 to the carrier at the lane centre = 1.8 mm, so at most 27 mm routed + 7 mm termination): 35 mm cut length is the maximum (stage 2: JST GH-6 J1001/J1101/J1201/J1301 at the rear edge, u 29.9 / 117.5 / 204.9 / 292.4, v 5.0, S2-L3)). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 flat/round micro-cable, 3 twisted pairs (NTC, LED, 3V3). The lane SiPM NTC (10 kohm within 5 mm of the SiPM, CCR-HE-06) is the lane temperature sensor. LED and 3V3 pins feed an optional pulser/active sensor.
* **Shield / bonding:** none; inside the lane shield can region: keep leads < 35 mm
* **Protection upstream:** No fuse; 10 kohm pull-up to the 3.000 V reference (<= 0.3 mA)
* **Strain relief:** Adhesive/tack at the carrier end; no loop > 10 mm (pickup, IB-23)
* **Labels:** both ends, `W-109` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Carrier connector TBD (not in sources).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-109.1 | CARR-AUX1.1 | HEAD.J1101.1 | NTC_SIPM1 | 28 | WH | FEP | P1 | 35 |
| W-109.2 | CARR-AUX1.2 | HEAD.J1101.2 | GND | 28 | BK | FEP | P1 | 35 |
| W-109.3 | CARR-AUX1.3 | HEAD.J1101.3 | L1_LED_A | 28 | GN | FEP | P2 | 35 |
| W-109.4 | CARR-AUX1.4 | HEAD.J1101.4 | L1_LED_K | 28 | BN | FEP | P2 | 35 |
| W-109.5 | CARR-AUX1.5 | HEAD.J1101.5 | L1_AUX3V3 | 28 | RD | FEP | P3 | 35 |
| W-109.6 | CARR-AUX1.6 | HEAD.J1101.6 | GND | 28 | BK | FEP | P3 | 35 |

### W-110  Head lane 2 auxiliary pigtail: head board J1201 to the SiPM carrier aux

* **Length:** 35 mm (mechanical interfaces: pigtails < 35 mm from the rear edge into the chimney (drop 17-25 mm + lateral offset from the GH-6 at lane du -1.80 to the carrier at the lane centre = 1.8 mm, so at most 27 mm routed + 7 mm termination): 35 mm cut length is the maximum (stage 2: JST GH-6 J1001/J1101/J1201/J1301 at the rear edge, u 29.9 / 117.5 / 204.9 / 292.4, v 5.0, S2-L3)). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 flat/round micro-cable, 3 twisted pairs (NTC, LED, 3V3). The lane SiPM NTC (10 kohm within 5 mm of the SiPM, CCR-HE-06) is the lane temperature sensor. LED and 3V3 pins feed an optional pulser/active sensor.
* **Shield / bonding:** none; inside the lane shield can region: keep leads < 35 mm
* **Protection upstream:** No fuse; 10 kohm pull-up to the 3.000 V reference (<= 0.3 mA)
* **Strain relief:** Adhesive/tack at the carrier end; no loop > 10 mm (pickup, IB-23)
* **Labels:** both ends, `W-110` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Carrier connector TBD (not in sources).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-110.1 | CARR-AUX2.1 | HEAD.J1201.1 | NTC_SIPM2 | 28 | WH | FEP | P1 | 35 |
| W-110.2 | CARR-AUX2.2 | HEAD.J1201.2 | GND | 28 | BK | FEP | P1 | 35 |
| W-110.3 | CARR-AUX2.3 | HEAD.J1201.3 | L2_LED_A | 28 | GN | FEP | P2 | 35 |
| W-110.4 | CARR-AUX2.4 | HEAD.J1201.4 | L2_LED_K | 28 | BN | FEP | P2 | 35 |
| W-110.5 | CARR-AUX2.5 | HEAD.J1201.5 | L2_AUX3V3 | 28 | RD | FEP | P3 | 35 |
| W-110.6 | CARR-AUX2.6 | HEAD.J1201.6 | GND | 28 | BK | FEP | P3 | 35 |

### W-111  Head lane 3 auxiliary pigtail: head board J1301 to the SiPM carrier aux

* **Length:** 35 mm (mechanical interfaces: pigtails < 35 mm from the rear edge into the chimney (drop 17-25 mm + lateral offset from the GH-6 at lane du -1.80 to the carrier at the lane centre = 1.8 mm, so at most 27 mm routed + 7 mm termination): 35 mm cut length is the maximum (stage 2: JST GH-6 J1001/J1101/J1201/J1301 at the rear edge, u 29.9 / 117.5 / 204.9 / 292.4, v 5.0, S2-L3)). *Estimated from layout, confirm on first build.*
* **Construction:** 6 x AWG 28 flat/round micro-cable, 3 twisted pairs (NTC, LED, 3V3). The lane SiPM NTC (10 kohm within 5 mm of the SiPM, CCR-HE-06) is the lane temperature sensor. LED and 3V3 pins feed an optional pulser/active sensor.
* **Shield / bonding:** none; inside the lane shield can region: keep leads < 35 mm
* **Protection upstream:** No fuse; 10 kohm pull-up to the 3.000 V reference (<= 0.3 mA)
* **Strain relief:** Adhesive/tack at the carrier end; no loop > 10 mm (pickup, IB-23)
* **Labels:** both ends, `W-111` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Carrier connector TBD (not in sources).

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-111.1 | CARR-AUX3.1 | HEAD.J1301.1 | NTC_SIPM3 | 28 | WH | FEP | P1 | 35 |
| W-111.2 | CARR-AUX3.2 | HEAD.J1301.2 | GND | 28 | BK | FEP | P1 | 35 |
| W-111.3 | CARR-AUX3.3 | HEAD.J1301.3 | L3_LED_A | 28 | GN | FEP | P2 | 35 |
| W-111.4 | CARR-AUX3.4 | HEAD.J1301.4 | L3_LED_K | 28 | BN | FEP | P2 | 35 |
| W-111.5 | CARR-AUX3.5 | HEAD.J1301.5 | L3_AUX3V3 | 28 | RD | FEP | P3 | 35 |
| W-111.6 | CARR-AUX3.6 | HEAD.J1301.6 | GND | 28 | BK | FEP | P3 | 35 |

### W-112  SiPM coaxial pair F0 (anode signal + bias): head board J101/J102 to SiPM carrier F0

* **Length:** 50 mm (rear-edge U.FL to the carrier in the chimney (assumed at the lane centre): drop up to 25 mm + lateral offset (anode du -10.38 -> 45 mm, bias du -15.47 -> 50 mm; stage-2 translated channel layout S2-L3) + 7 mm termination, rounded up to 5 mm. board_envelopes.yaml AFE_STRIP assumed < 35 mm with the stage-1 pitch; the stage-2 anode pitch of 22.25 mm and bias U.FL at du -15.47 make the longest coax 50 mm). *Estimated from layout, confirm on first build.*
* **Construction:** Two 50 ohm 1.13 mm micro-coax (one for the anode signal, one for the bias), each terminated in a U.FL-compatible plug at the board and the carrier-side termination TBD. Mandatory: coax pigtails and per-lane shield cans (IB-23: open pigtail loop picks up about 10 p.e. per motor-PWM edge at 65 mm, about 0.4 p.e. with coax). Carrier coax gauge is 'AWG ~32' class: AWG column 0 = not applicable.
* **Shield / bonding:** Each coax shield bonded to GND at the U.FL jack and at the carrier; the two shields are separate conductors. Shield cans are on board ground through their clips.
* **Protection upstream:** Bias current limit 2.0 mA at the source (head circuit_description.md section 3); no fuse
* **Strain relief:** Adhesive tack at both ends; lay in the chimney channel; locking MHF-LK plugs fit the same U.FL receptacle
* **Labels:** both ends, `W-112` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Stage-2 U.FL positions (S2-L3, translated channel copy): F anode du -10.38 / F bias -15.47, R bias +6.78 / R anode +11.87 around the lane centre (the stage-1 layout guidance had F at -11/-6, R at +6/+11), U.FL at the rear edge v 3.9, mouse holes in the rear wall at du -10.38 / +11.87 (CR-M04, not yet accepted by head mechanical, IB-52). 60 V AC rating of U.FL against 62.5 V DC bias is datasheet-class, UNVERIFIED for DC (circuit_description.md). Zero slack: a longer pigtail increases the pickup loop (IB-23): the per-wire lengths are the minimum, cut to the length column of the wire.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-112.1 | CARR-F0.A | HEAD.J101.1 | F0_A | coax | coax centre | COAX | X1 | 45 |
| W-112.2 | CARR-F0.A-SH | HEAD.J101.2 | GND | coax | coax shield | COAX | X1 | 45 |
| W-112.3 | CARR-F0.B | HEAD.J102.1 | F0_HVF | coax | coax centre | COAX | X2 | 50 |
| W-112.4 | CARR-F0.B-SH | HEAD.J102.2 | GND | coax | coax shield | COAX | X2 | 50 |

### W-113  SiPM coaxial pair F1 (anode signal + bias): head board J201/J202 to SiPM carrier F1

* **Length:** 50 mm (rear-edge U.FL to the carrier in the chimney (assumed at the lane centre): drop up to 25 mm + lateral offset (anode du -10.38 -> 45 mm, bias du -15.47 -> 50 mm; stage-2 translated channel layout S2-L3) + 7 mm termination, rounded up to 5 mm. board_envelopes.yaml AFE_STRIP assumed < 35 mm with the stage-1 pitch; the stage-2 anode pitch of 22.25 mm and bias U.FL at du -15.47 make the longest coax 50 mm). *Estimated from layout, confirm on first build.*
* **Construction:** Two 50 ohm 1.13 mm micro-coax (one for the anode signal, one for the bias), each terminated in a U.FL-compatible plug at the board and the carrier-side termination TBD. Mandatory: coax pigtails and per-lane shield cans (IB-23: open pigtail loop picks up about 10 p.e. per motor-PWM edge at 65 mm, about 0.4 p.e. with coax). Carrier coax gauge is 'AWG ~32' class: AWG column 0 = not applicable.
* **Shield / bonding:** Each coax shield bonded to GND at the U.FL jack and at the carrier; the two shields are separate conductors. Shield cans are on board ground through their clips.
* **Protection upstream:** Bias current limit 2.0 mA at the source (head circuit_description.md section 3); no fuse
* **Strain relief:** Adhesive tack at both ends; lay in the chimney channel; locking MHF-LK plugs fit the same U.FL receptacle
* **Labels:** both ends, `W-113` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Stage-2 U.FL positions (S2-L3, translated channel copy): F anode du -10.38 / F bias -15.47, R bias +6.78 / R anode +11.87 around the lane centre (the stage-1 layout guidance had F at -11/-6, R at +6/+11), U.FL at the rear edge v 3.9, mouse holes in the rear wall at du -10.38 / +11.87 (CR-M04, not yet accepted by head mechanical, IB-52). 60 V AC rating of U.FL against 62.5 V DC bias is datasheet-class, UNVERIFIED for DC (circuit_description.md). Zero slack: a longer pigtail increases the pickup loop (IB-23): the per-wire lengths are the minimum, cut to the length column of the wire.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-113.1 | CARR-F1.A | HEAD.J201.1 | F1_A | coax | coax centre | COAX | X1 | 45 |
| W-113.2 | CARR-F1.A-SH | HEAD.J201.2 | GND | coax | coax shield | COAX | X1 | 45 |
| W-113.3 | CARR-F1.B | HEAD.J202.1 | F1_HVF | coax | coax centre | COAX | X2 | 50 |
| W-113.4 | CARR-F1.B-SH | HEAD.J202.2 | GND | coax | coax shield | COAX | X2 | 50 |

### W-114  SiPM coaxial pair F2 (anode signal + bias): head board J301/J302 to SiPM carrier F2

* **Length:** 50 mm (rear-edge U.FL to the carrier in the chimney (assumed at the lane centre): drop up to 25 mm + lateral offset (anode du -10.38 -> 45 mm, bias du -15.47 -> 50 mm; stage-2 translated channel layout S2-L3) + 7 mm termination, rounded up to 5 mm. board_envelopes.yaml AFE_STRIP assumed < 35 mm with the stage-1 pitch; the stage-2 anode pitch of 22.25 mm and bias U.FL at du -15.47 make the longest coax 50 mm). *Estimated from layout, confirm on first build.*
* **Construction:** Two 50 ohm 1.13 mm micro-coax (one for the anode signal, one for the bias), each terminated in a U.FL-compatible plug at the board and the carrier-side termination TBD. Mandatory: coax pigtails and per-lane shield cans (IB-23: open pigtail loop picks up about 10 p.e. per motor-PWM edge at 65 mm, about 0.4 p.e. with coax). Carrier coax gauge is 'AWG ~32' class: AWG column 0 = not applicable.
* **Shield / bonding:** Each coax shield bonded to GND at the U.FL jack and at the carrier; the two shields are separate conductors. Shield cans are on board ground through their clips.
* **Protection upstream:** Bias current limit 2.0 mA at the source (head circuit_description.md section 3); no fuse
* **Strain relief:** Adhesive tack at both ends; lay in the chimney channel; locking MHF-LK plugs fit the same U.FL receptacle
* **Labels:** both ends, `W-114` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Stage-2 U.FL positions (S2-L3, translated channel copy): F anode du -10.38 / F bias -15.47, R bias +6.78 / R anode +11.87 around the lane centre (the stage-1 layout guidance had F at -11/-6, R at +6/+11), U.FL at the rear edge v 3.9, mouse holes in the rear wall at du -10.38 / +11.87 (CR-M04, not yet accepted by head mechanical, IB-52). 60 V AC rating of U.FL against 62.5 V DC bias is datasheet-class, UNVERIFIED for DC (circuit_description.md). Zero slack: a longer pigtail increases the pickup loop (IB-23): the per-wire lengths are the minimum, cut to the length column of the wire.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-114.1 | CARR-F2.A | HEAD.J301.1 | F2_A | coax | coax centre | COAX | X1 | 45 |
| W-114.2 | CARR-F2.A-SH | HEAD.J301.2 | GND | coax | coax shield | COAX | X1 | 45 |
| W-114.3 | CARR-F2.B | HEAD.J302.1 | F2_HVF | coax | coax centre | COAX | X2 | 50 |
| W-114.4 | CARR-F2.B-SH | HEAD.J302.2 | GND | coax | coax shield | COAX | X2 | 50 |

### W-115  SiPM coaxial pair F3 (anode signal + bias): head board J401/J402 to SiPM carrier F3

* **Length:** 50 mm (rear-edge U.FL to the carrier in the chimney (assumed at the lane centre): drop up to 25 mm + lateral offset (anode du -10.38 -> 45 mm, bias du -15.47 -> 50 mm; stage-2 translated channel layout S2-L3) + 7 mm termination, rounded up to 5 mm. board_envelopes.yaml AFE_STRIP assumed < 35 mm with the stage-1 pitch; the stage-2 anode pitch of 22.25 mm and bias U.FL at du -15.47 make the longest coax 50 mm). *Estimated from layout, confirm on first build.*
* **Construction:** Two 50 ohm 1.13 mm micro-coax (one for the anode signal, one for the bias), each terminated in a U.FL-compatible plug at the board and the carrier-side termination TBD. Mandatory: coax pigtails and per-lane shield cans (IB-23: open pigtail loop picks up about 10 p.e. per motor-PWM edge at 65 mm, about 0.4 p.e. with coax). Carrier coax gauge is 'AWG ~32' class: AWG column 0 = not applicable.
* **Shield / bonding:** Each coax shield bonded to GND at the U.FL jack and at the carrier; the two shields are separate conductors. Shield cans are on board ground through their clips.
* **Protection upstream:** Bias current limit 2.0 mA at the source (head circuit_description.md section 3); no fuse
* **Strain relief:** Adhesive tack at both ends; lay in the chimney channel; locking MHF-LK plugs fit the same U.FL receptacle
* **Labels:** both ends, `W-115` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Stage-2 U.FL positions (S2-L3, translated channel copy): F anode du -10.38 / F bias -15.47, R bias +6.78 / R anode +11.87 around the lane centre (the stage-1 layout guidance had F at -11/-6, R at +6/+11), U.FL at the rear edge v 3.9, mouse holes in the rear wall at du -10.38 / +11.87 (CR-M04, not yet accepted by head mechanical, IB-52). 60 V AC rating of U.FL against 62.5 V DC bias is datasheet-class, UNVERIFIED for DC (circuit_description.md). Zero slack: a longer pigtail increases the pickup loop (IB-23): the per-wire lengths are the minimum, cut to the length column of the wire.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-115.1 | CARR-F3.A | HEAD.J401.1 | F3_A | coax | coax centre | COAX | X1 | 45 |
| W-115.2 | CARR-F3.A-SH | HEAD.J401.2 | GND | coax | coax shield | COAX | X1 | 45 |
| W-115.3 | CARR-F3.B | HEAD.J402.1 | F3_HVF | coax | coax centre | COAX | X2 | 50 |
| W-115.4 | CARR-F3.B-SH | HEAD.J402.2 | GND | coax | coax shield | COAX | X2 | 50 |

### W-116  SiPM coaxial pair R0 (anode signal + bias): head board J501/J502 to SiPM carrier R0

* **Length:** 45 mm (rear-edge U.FL to the carrier in the chimney (assumed at the lane centre): drop up to 25 mm + lateral offset (anode du +11.87 -> 45 mm, bias du +6.78 -> 40 mm; stage-2 translated channel layout S2-L3) + 7 mm termination, rounded up to 5 mm. board_envelopes.yaml AFE_STRIP assumed < 35 mm with the stage-1 pitch; the stage-2 anode pitch of 22.25 mm and bias U.FL at du -15.47 make the longest coax 45 mm). *Estimated from layout, confirm on first build.*
* **Construction:** Two 50 ohm 1.13 mm micro-coax (one for the anode signal, one for the bias), each terminated in a U.FL-compatible plug at the board and the carrier-side termination TBD. Mandatory: coax pigtails and per-lane shield cans (IB-23: open pigtail loop picks up about 10 p.e. per motor-PWM edge at 65 mm, about 0.4 p.e. with coax). Carrier coax gauge is 'AWG ~32' class: AWG column 0 = not applicable.
* **Shield / bonding:** Each coax shield bonded to GND at the U.FL jack and at the carrier; the two shields are separate conductors. Shield cans are on board ground through their clips.
* **Protection upstream:** Bias current limit 2.0 mA at the source (head circuit_description.md section 3); no fuse
* **Strain relief:** Adhesive tack at both ends; lay in the chimney channel; locking MHF-LK plugs fit the same U.FL receptacle
* **Labels:** both ends, `W-116` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Stage-2 U.FL positions (S2-L3, translated channel copy): F anode du -10.38 / F bias -15.47, R bias +6.78 / R anode +11.87 around the lane centre (the stage-1 layout guidance had F at -11/-6, R at +6/+11), U.FL at the rear edge v 3.9, mouse holes in the rear wall at du -10.38 / +11.87 (CR-M04, not yet accepted by head mechanical, IB-52). 60 V AC rating of U.FL against 62.5 V DC bias is datasheet-class, UNVERIFIED for DC (circuit_description.md). Zero slack: a longer pigtail increases the pickup loop (IB-23): the per-wire lengths are the minimum, cut to the length column of the wire.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-116.1 | CARR-R0.A | HEAD.J501.1 | R0_A | coax | coax centre | COAX | X1 | 45 |
| W-116.2 | CARR-R0.A-SH | HEAD.J501.2 | GND | coax | coax shield | COAX | X1 | 45 |
| W-116.3 | CARR-R0.B | HEAD.J502.1 | R0_HVF | coax | coax centre | COAX | X2 | 40 |
| W-116.4 | CARR-R0.B-SH | HEAD.J502.2 | GND | coax | coax shield | COAX | X2 | 40 |

### W-117  SiPM coaxial pair R1 (anode signal + bias): head board J601/J602 to SiPM carrier R1

* **Length:** 45 mm (rear-edge U.FL to the carrier in the chimney (assumed at the lane centre): drop up to 25 mm + lateral offset (anode du +11.87 -> 45 mm, bias du +6.78 -> 40 mm; stage-2 translated channel layout S2-L3) + 7 mm termination, rounded up to 5 mm. board_envelopes.yaml AFE_STRIP assumed < 35 mm with the stage-1 pitch; the stage-2 anode pitch of 22.25 mm and bias U.FL at du -15.47 make the longest coax 45 mm). *Estimated from layout, confirm on first build.*
* **Construction:** Two 50 ohm 1.13 mm micro-coax (one for the anode signal, one for the bias), each terminated in a U.FL-compatible plug at the board and the carrier-side termination TBD. Mandatory: coax pigtails and per-lane shield cans (IB-23: open pigtail loop picks up about 10 p.e. per motor-PWM edge at 65 mm, about 0.4 p.e. with coax). Carrier coax gauge is 'AWG ~32' class: AWG column 0 = not applicable.
* **Shield / bonding:** Each coax shield bonded to GND at the U.FL jack and at the carrier; the two shields are separate conductors. Shield cans are on board ground through their clips.
* **Protection upstream:** Bias current limit 2.0 mA at the source (head circuit_description.md section 3); no fuse
* **Strain relief:** Adhesive tack at both ends; lay in the chimney channel; locking MHF-LK plugs fit the same U.FL receptacle
* **Labels:** both ends, `W-117` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Stage-2 U.FL positions (S2-L3, translated channel copy): F anode du -10.38 / F bias -15.47, R bias +6.78 / R anode +11.87 around the lane centre (the stage-1 layout guidance had F at -11/-6, R at +6/+11), U.FL at the rear edge v 3.9, mouse holes in the rear wall at du -10.38 / +11.87 (CR-M04, not yet accepted by head mechanical, IB-52). 60 V AC rating of U.FL against 62.5 V DC bias is datasheet-class, UNVERIFIED for DC (circuit_description.md). Zero slack: a longer pigtail increases the pickup loop (IB-23): the per-wire lengths are the minimum, cut to the length column of the wire.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-117.1 | CARR-R1.A | HEAD.J601.1 | R1_A | coax | coax centre | COAX | X1 | 45 |
| W-117.2 | CARR-R1.A-SH | HEAD.J601.2 | GND | coax | coax shield | COAX | X1 | 45 |
| W-117.3 | CARR-R1.B | HEAD.J602.1 | R1_HVF | coax | coax centre | COAX | X2 | 40 |
| W-117.4 | CARR-R1.B-SH | HEAD.J602.2 | GND | coax | coax shield | COAX | X2 | 40 |

### W-118  SiPM coaxial pair R2 (anode signal + bias): head board J701/J702 to SiPM carrier R2

* **Length:** 45 mm (rear-edge U.FL to the carrier in the chimney (assumed at the lane centre): drop up to 25 mm + lateral offset (anode du +11.87 -> 45 mm, bias du +6.78 -> 40 mm; stage-2 translated channel layout S2-L3) + 7 mm termination, rounded up to 5 mm. board_envelopes.yaml AFE_STRIP assumed < 35 mm with the stage-1 pitch; the stage-2 anode pitch of 22.25 mm and bias U.FL at du -15.47 make the longest coax 45 mm). *Estimated from layout, confirm on first build.*
* **Construction:** Two 50 ohm 1.13 mm micro-coax (one for the anode signal, one for the bias), each terminated in a U.FL-compatible plug at the board and the carrier-side termination TBD. Mandatory: coax pigtails and per-lane shield cans (IB-23: open pigtail loop picks up about 10 p.e. per motor-PWM edge at 65 mm, about 0.4 p.e. with coax). Carrier coax gauge is 'AWG ~32' class: AWG column 0 = not applicable.
* **Shield / bonding:** Each coax shield bonded to GND at the U.FL jack and at the carrier; the two shields are separate conductors. Shield cans are on board ground through their clips.
* **Protection upstream:** Bias current limit 2.0 mA at the source (head circuit_description.md section 3); no fuse
* **Strain relief:** Adhesive tack at both ends; lay in the chimney channel; locking MHF-LK plugs fit the same U.FL receptacle
* **Labels:** both ends, `W-118` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Stage-2 U.FL positions (S2-L3, translated channel copy): F anode du -10.38 / F bias -15.47, R bias +6.78 / R anode +11.87 around the lane centre (the stage-1 layout guidance had F at -11/-6, R at +6/+11), U.FL at the rear edge v 3.9, mouse holes in the rear wall at du -10.38 / +11.87 (CR-M04, not yet accepted by head mechanical, IB-52). 60 V AC rating of U.FL against 62.5 V DC bias is datasheet-class, UNVERIFIED for DC (circuit_description.md). Zero slack: a longer pigtail increases the pickup loop (IB-23): the per-wire lengths are the minimum, cut to the length column of the wire.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-118.1 | CARR-R2.A | HEAD.J701.1 | R2_A | coax | coax centre | COAX | X1 | 45 |
| W-118.2 | CARR-R2.A-SH | HEAD.J701.2 | GND | coax | coax shield | COAX | X1 | 45 |
| W-118.3 | CARR-R2.B | HEAD.J702.1 | R2_HVF | coax | coax centre | COAX | X2 | 40 |
| W-118.4 | CARR-R2.B-SH | HEAD.J702.2 | GND | coax | coax shield | COAX | X2 | 40 |

### W-119  SiPM coaxial pair R3 (anode signal + bias): head board J801/J802 to SiPM carrier R3

* **Length:** 45 mm (rear-edge U.FL to the carrier in the chimney (assumed at the lane centre): drop up to 25 mm + lateral offset (anode du +11.87 -> 45 mm, bias du +6.78 -> 40 mm; stage-2 translated channel layout S2-L3) + 7 mm termination, rounded up to 5 mm. board_envelopes.yaml AFE_STRIP assumed < 35 mm with the stage-1 pitch; the stage-2 anode pitch of 22.25 mm and bias U.FL at du -15.47 make the longest coax 45 mm). *Estimated from layout, confirm on first build.*
* **Construction:** Two 50 ohm 1.13 mm micro-coax (one for the anode signal, one for the bias), each terminated in a U.FL-compatible plug at the board and the carrier-side termination TBD. Mandatory: coax pigtails and per-lane shield cans (IB-23: open pigtail loop picks up about 10 p.e. per motor-PWM edge at 65 mm, about 0.4 p.e. with coax). Carrier coax gauge is 'AWG ~32' class: AWG column 0 = not applicable.
* **Shield / bonding:** Each coax shield bonded to GND at the U.FL jack and at the carrier; the two shields are separate conductors. Shield cans are on board ground through their clips.
* **Protection upstream:** Bias current limit 2.0 mA at the source (head circuit_description.md section 3); no fuse
* **Strain relief:** Adhesive tack at both ends; lay in the chimney channel; locking MHF-LK plugs fit the same U.FL receptacle
* **Labels:** both ends, `W-119` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** Stage-2 U.FL positions (S2-L3, translated channel copy): F anode du -10.38 / F bias -15.47, R bias +6.78 / R anode +11.87 around the lane centre (the stage-1 layout guidance had F at -11/-6, R at +6/+11), U.FL at the rear edge v 3.9, mouse holes in the rear wall at du -10.38 / +11.87 (CR-M04, not yet accepted by head mechanical, IB-52). 60 V AC rating of U.FL against 62.5 V DC bias is datasheet-class, UNVERIFIED for DC (circuit_description.md). Zero slack: a longer pigtail increases the pickup loop (IB-23): the per-wire lengths are the minimum, cut to the length column of the wire.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-119.1 | CARR-R3.A | HEAD.J801.1 | R3_A | coax | coax centre | COAX | X1 | 45 |
| W-119.2 | CARR-R3.A-SH | HEAD.J801.2 | GND | coax | coax shield | COAX | X1 | 45 |
| W-119.3 | CARR-R3.B | HEAD.J802.1 | R3_HVF | coax | coax centre | COAX | X2 | 40 |
| W-119.4 | CARR-R3.B-SH | HEAD.J802.2 | GND | coax | coax shield | COAX | X2 | 40 |

### W-200  LAB ONLY: J1X extension, 2 m, M16 plug (robot end) to M16 socket (head end), straight through + 1.50 kohm LAB resistor

* **Length:** 2000 mm (2.0 m by the head ICD section 7 ('2 m as a harness design trial'); 1.7 m fallback in CCR-E07). *Estimated from layout, confirm on first build.*
* **Construction:** See lab_extension.md.
* **Shield / bonding:** Continuous braid end to end.
* **Protection upstream:** Same upstream protection as W-008/W-101 (eFuses 1.51 A and 4.05 A); LAB mode adds no fuse
* **Strain relief:** Strain-relief clamps in both backshells; support the head and cable independently of the entrance window (head_icd.md section 7)
* **Labels:** both ends, `W-200` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** LAB ONLY. Mark both plugs with the LAB label. Not part of the robot BOM.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-200.1 | J1X-P.1 | J1X-S.1 | HEAD_PWR_P | 18 | RD | SI | P1 | 2000 |
| W-200.2 | J1X-P.2 | J1X-S.2 | HEAD_PWR_N | 18 | BK | SI | P1 | 2000 |
| W-200.3 | J1X-P.3 | J1X-S.3 | HEAD_HTR_P | 18 | OG | SI | P2 | 2000 |
| W-200.4 | J1X-P.4 | J1X-S.4 | HEAD_HTR_N | 18 | BN | SI | P2 | 2000 |
| W-200.5 | J1X-P.5 | J1X-S.5 | HEAD_LOOP_OUT | 24 | GN | SI | P3 | 2000 |
| W-200.6 | J1X-P.6 | J1X-S.6 | HEAD_LOOP_RET | 24 | GY | SI | P3 | 2000 |
| W-200.7 | J1X-P.7 | J1X-S.7 | HEAD_PRES_ID | 24 | VT | SI | - | 2000 |
| W-200.S | J1X-P.SH | J1X-S.SH | CHASSIS -> SHLD_J1 | 24 | bare | SI | - | 2000 |
| W-200.R | J1X-P.7 | J1X-P.2 | HEAD_PRES_ID -> HEAD_PWR_N | 24 | VT | SI | - | 30 |

### W-201  LAB ONLY: J2X extension, 2 m, M12 plug (robot end) to M12 socket (head end), straight through

* **Length:** 2000 mm (2.0 m (head ICD section 7)). *Estimated from layout, confirm on first build.*
* **Construction:** See lab_extension.md. 120 ohm twisted pair P1 straight through: NO terminator, NO stub; the two terminations stay at the chassis board and the head board.
* **Shield / bonding:** Continuous braid end to end.
* **Protection upstream:** As W-009/W-102
* **Strain relief:** Strain-relief clamps in both backshells
* **Labels:** both ends, `W-201` + connector ID + pin-1 mark; per-conductor `W-xxx.n` (see `cables.csv`).
* **Notes:** LAB ONLY.

| Wire | From (conn.pin) | To (conn.pin) | Net (from -> to) | AWG | Colour | Insulation | Pair | Length |
|---|---|---|---|---|---|---|---|---|
| W-201.1 | J2X-P.1 | J2X-S.1 | RS485_DP | 26 | WH | FEP | P1 | 2000 |
| W-201.2 | J2X-P.2 | J2X-S.2 | RS485_DN | 26 | BU | FEP | P1 | 2000 |
| W-201.3 | J2X-P.3 | J2X-S.3 | BUS_5V | 26 | RD | FEP | P2 | 2000 |
| W-201.4 | J2X-P.4 | J2X-S.4 | BUS_GND | 26 | BK | FEP | P2 | 2000 |
| W-201.5 | J2X-P.5 | J2X-S.5 | SYNC_P | 26 | GN | FEP | P3 | 2000 |
| W-201.6 | J2X-P.6 | J2X-S.6 | SYNC_N | 26 | GY | FEP | P3 | 2000 |
| W-201.7 | J2X-P.7 | J2X-S.7 | J2_PRES | 26 | VT | FEP | P4 | 2000 |
| W-201.S | J2X-P.SH | J2X-S.SH | CHASSIS -> SHLD_J2 | 26 | bare | FEP | - | 2000 |

## 4. The head interlock loop (potential-free pair): J1 pins 5 and 6

```
  chassis                     J1 cable (W-008 / W-101)                          head board                       head rail switches (D2HW-C201M, NC)
  ------                      ------------------------                          ----------                       -----------------------------------
  RR-CHS-MAIN                                                                   RR-HEAD-ACQ
  J_HEAD1.5 HEAD_LOOP_OUT ==== J1R.5 -- J1P.5 ==== W-101.5 ====> J2001.5 ----+
     (source: ~chassis loop sense)                                              |
                                                                                +--> J2002.1 --[ RAIL-F  COM-NC ]--> J2002.2 = LOOP_A
                                                                                                                         |
                                                                                +--> J2003.1 <-----------------------LOOP_A
                                                                                     J2003.1 --[ RAIL-L  COM-NC ]--> J2003.2 = LOOP_B
                                                                                                                         |
                                                                                     J2004.1 <-----------------------LOOP_B
                                                                                     J2004.1 --[ RAIL-R  COM-NC ]--> J2004.2 = LOOP_C
                                                                                                                         |
                                                                                                               R2019 1.00 kohm 0.1 %
                                                                                                                         |
  J_HEAD1.6 HEAD_LOOP_RET ==== J1R.6 -- J1P.6 ==== W-101.6 <==== J2001.6 <------------- HEAD_LOOP_RET ----------------+

  Healthy = 0.6 .. 1.6 kohm (window comparator, contract); open = rail pressed or J1 unplugged; short < 0.6 kohm = wiring fault.
  The pair shares no conductor with power or data. Shield and every other pin stay isolated from pins 5 and 6.
  The J2002/3/4 pins 3 and 4 (zone read-back) are NOT wired, and the D2HW NO lead stays cut back: using the NO throw would tie the loop to head logic (CCR-HE-04).
```

The 1.00 kohm resistor is on the head board at the FAR end of the switch string (chassis_safety_chain.md fault #24): do not move it into the harness.

## 5. Unconnected connector pins

(The complete list with reasons is also in `connectors.yaml: unconnected_pins`.)

| Connector | Pin | Net | Reason |
|---|---|---|---|
| CHS.J_AUX | 1 | V12_AUX | spare fan/spare connector: no cable in rev A |
| CHS.J_AUX | 2 | GND | spare fan/spare connector: no cable in rev A |
| CHS.J_AUX | 3 | SPARE_IO | spare fan/spare connector: no cable in rev A |
| CHS.J_BTN | 5 | NC | NC by design (net NC) |
| CHS.J_BTN | 8 | NC | NC by design (net NC) |
| CHS.J_COVER | 3 | NC | NC by design (net NC) |
| CHS.J_DBG | 1 | DBG_3V3 | debug UART service port: plug a lead when needed |
| CHS.J_DBG | 2 | DBG_TX_C | debug UART service port: plug a lead when needed |
| CHS.J_DBG | 3 | DBG_RX_C | debug UART service port: plug a lead when needed |
| CHS.J_DBG | 4 | GND | debug UART service port: plug a lead when needed |
| CHS.J_DOCK | 2 | NC | NC by design (net NC) |
| CHS.J_HANDS | 5 | NC | NC by design (net NC) |
| CHS.J_HEAD1 | 8 | NC | NC by design (net NC) |
| CHS.J_HEAD1 | 9 | NC | NC by design (net NC) |
| CHS.J_HEAD1 | 10 | NC | NC by design (net NC) |
| CHS.J_HEAD2 | 8 | NC | NC by design (net NC) |
| CHS.J_MODE | 5 | NC | NC by design (net NC) |
| CHS.J_MODE | 6 | NC | NC by design (net NC) |
| CHS.J_PAUSE | 5 | NC | NC by design (net NC) |
| CHS.J_PAUX | 3 | GND | no wire by decision (IB-37, chassis stage 2): NTC and presence return to pack negative inside the cassette (W-002/W-003); the accepted offset is about 0.1 V at full load (NTC about 3.4 K warm on discharge, about 0.7 K cold on charge, safe side). Wire pins 3/4 only if the cassette gets an isolated sense return |
| CHS.J_PAUX | 4 | GND | no wire by decision (IB-37, as pin 3) |
| CHS.J_SWD | 1 | 3V3 | SWD service port: ribbon only when programming |
| CHS.J_SWD | 2 | SWDIO | SWD service port: ribbon only when programming |
| CHS.J_SWD | 3 | GND | SWD service port: ribbon only when programming |
| CHS.J_SWD | 4 | SWCLK | SWD service port: ribbon only when programming |
| CHS.J_SWD | 5 | GND | SWD service port: ribbon only when programming |
| CHS.J_SWD | 6 | SWO_SPARE | SWD service port: ribbon only when programming |
| CHS.J_SWD | 7 | NC | NC by design (net NC) |
| CHS.J_SWD | 8 | NC | NC by design (net NC) |
| CHS.J_SWD | 9 | GND | SWD service port: ribbon only when programming |
| CHS.J_SWD | 10 | NRST | SWD service port: ribbon only when programming |
| CHS.J_USB_MCU | 1 | NC | NC by design (net NC) |
| HEAD.J2001 | 8 | NC | NC by design (net NC) |
| HEAD.J2002 | 3 | BZ_F_IN | no wire by decision: CCR-HE-04 (single-pole switch, NO throw not potential-free) |
| HEAD.J2002 | 4 | GND | as pin 3 |
| HEAD.J2003 | 3 | BZ_L_IN | as J2002 pin 3 |
| HEAD.J2003 | 4 | GND | as J2002 pin 3 |
| HEAD.J2004 | 3 | BZ_R_IN | as J2002 pin 3 |
| HEAD.J2004 | 4 | GND | as J2002 pin 3 |
| HEAD.JP2201 | 1 | LID_IN | solder jumper (lid bypass): bench only |
| HEAD.JP2201 | 2 | GND | solder jumper (lid bypass): bench only |
| HEAD.J2401 | 1 | +3V3 | SWD pads (no component fitted): Tag-Connect cable only when programming |
| HEAD.J2401 | 2 | SWDIO | SWD pads (no component fitted): Tag-Connect cable only when programming |
| HEAD.J2401 | 3 | NRST | SWD pads (no component fitted): Tag-Connect cable only when programming |
| HEAD.J2401 | 4 | SWCLK | SWD pads (no component fitted): Tag-Connect cable only when programming |
| HEAD.J2401 | 5 | GND | SWD pads (no component fitted): Tag-Connect cable only when programming |
| HEAD.J2401 | 6 | NC | NC by design (net NC) |
| HEAD.J2402 | 1 | DBG_TX | debug UART service port |
| HEAD.J2402 | 2 | DBG_RX | debug UART service port |
| HEAD.J2402 | 3 | GND | debug UART service port |
| HEAD.J2501 | 8 | NC | NC by design (net NC) |
| HEAD.J2601 | 6 | NC | NC by design (net NC) |
| HEAD.J2701 | 1 | MON_OUT | monitor output test port: coax only on the bench |
| HEAD.J2701 | 2 | GND | monitor output test port: coax only on the bench |
| J1R | 8 | NC_RESERVED | NC by design (net NC_RESERVED) |
| J1R | SH | CHASSIS | shield bonded to the chassis through the receptacle shell (no wire) |
| J1P | 8 | NC_RESERVED | NC by design (net NC_RESERVED) |
| J2R | 8 | NC_RESERVED | NC by design (net NC_RESERVED) |
| J2R | SH | CHASSIS | as J1R |
| J2P | 8 | NC_RESERVED | NC by design (net NC_RESERVED) |
| J1X-P | 8 | NC_RESERVED | NC by design (net NC_RESERVED) |
| J1X-S | 8 | NC_RESERVED | NC by design (net NC_RESERVED) |
| J2X-P | 8 | NC_RESERVED | NC by design (net NC_RESERVED) |
| J2X-S | 8 | NC_RESERVED | NC by design (net NC_RESERVED) |
| INLET | FE | CHASSIS | chassis bond through the receptacle flange (no wire) |
| CHGPLUG | 1 | CHG_IN | supply-side plug: belongs to the external 24 V supply, not to the robot harness |
| CHGPLUG | 2 | PLUG_LINK | supply-side plug: belongs to the external 24 V supply, not to the robot harness |
| CHGPLUG | 3 | GND | supply-side plug: belongs to the external 24 V supply, not to the robot harness |
| CHGPLUG | 4 | GND | supply-side plug: belongs to the external 24 V supply, not to the robot harness |
| CHGPLUG | FE | CHASSIS | supply-side plug: belongs to the external 24 V supply, not to the robot harness |
| CM5-USB1 | 1 | NC | NC by design (net NC) |
| BUMP-L-DEV | NO | UNUSED | NC by design (net UNUSED) |
| BUMP-R-DEV | NO | UNUSED | NC by design (net UNUSED) |
| DOCK-DEV | NO | UNUSED | NC by design (net UNUSED) |
| COVER-DEV | NO | UNUSED | NC by design (net UNUSED) |
| CHS.W1 | 1 | CLAMP_F | DNP wire pads of the on-board clamp circuit: NO cable by decision (the board carries its own 2 x 9.1 ohm clamp resistors; no bolt-on 50 W part, IB-26 / IB-36) |
| CHS.W1 | 2 | CLAMP_R | DNP wire pads of the on-board clamp circuit: NO cable by decision (the board carries its own 2 x 9.1 ohm clamp resistors; no bolt-on 50 W part, IB-26 / IB-36) |
| RAIL-F | NO | UNUSED | NC by design (net UNUSED) |
| RAIL-L | NO | UNUSED | NC by design (net UNUSED) |
| RAIL-R | NO | UNUSED | NC by design (net UNUSED) |

