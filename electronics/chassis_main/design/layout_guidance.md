# RR-CHS-MAIN rev A layout guidance (for the stage-2 engineer)

Source of truth for nets and parts: `circuit.py` (run it: self-check must pass). Envelope: `mechanical/common/board_envelopes.yaml` (authoritative). Frame: origin at the rear-left corner seen from above, +u to the robot's right, +v forward, top side up. All values mm. Tags as elsewhere: [C] calculated, [A] assumed.

## 1. Does it fit?

| Item | Value |
|---|---|
| Parts | 768 (755 fitted); 132 carry `verify=True` |
| Estimated placed area incl. courtyards | 10 030 mm² = 63 % of one side, 31 % of both sides [C, `circuit.py`] |
| Parts ≥ 100 mm² (relays, electrolytics, power connectors, MCU) | 3 590 mm², top side only |
| Verdict | **160 × 100 mm holds only as a two-sided assembly** (passives, small ICs and discretes up to 3 mm on the bottom). One-sided it would be 63 % full with 35 connectors, which will not route. If two-sided assembly is not acceptable the board needs about 180 × 110 mm. |

Bottom side: 0603/0805 passives, SOT-23, SOD-123, the tap networks, ESD arrays, test pads. Not on the bottom: anything over 3 mm, the THERMAL_TO_BRIDGE pad area (u 50–110, v 30–70) apart from thermal vias.

## 2. Floorplan

```
 v=100 ┌──[J_HEAD1 u12-31]──────[J_TOF0][J_DOCK][J_TOF1] u50-110──────[J_HEAD2 u125-140]──┐  front
       │ head branch          TOF muxes U50/U51                 RS-485 U62, L60, D60       │
       │ U15 U16 U17 L5       (u 60-100, v 80-90)               (u 118-145, v 84-96)       │
 [J_MOT_L]                                                                         [J_MOT_R]
 v74-90│ K2 (u18-47,v62-76)        IMU U42 @ (80,67)            K3 (u113-142, v62-76)      │v74-90
       │ U35 U37  J_TOF4/5         keep 8 mm clear              U36 U38  J_TOF6/7          │
       │─────────────── no connectors on side edges v 34..70 ───────────────────────────── │
       │ MCU U20M (u25-45,v40-58)  ┌── THERMAL_TO_BRIDGE u50-110, v30-70 ──┐  charger U3   │
       │ U43 U44 U45 Y1 J_SWD      │ U5  U6 (v 44-56)  U8   VMOT caps     │  L1 Q3 Q4 Q5  │
       │ U11 U12 U14 (u 8-45,      │ U10 + L2 (u 52-72, v 32-44)  U33 Q40 │  (u 112-140,  │
       │  v 22-36)                 └───────────────────────────────────────┘   v 34-58)    │
 [J_CM5 v8-21]  U13 U19  U61 U41                                  Q1 Q2 R_SH1 U1 U2 [J_PWR │
 [J_LIDAR v23-33] J_USB_MCU J_USB_HEAD                            C(VBAT_SW) D(TVS)  v8-31]│
       │ rear-left corner (u 0-45, v 0-20):          rear-right corner (u 112-160, v 0-22):│
       │ J_PANEL J_MODE J_BTN J_BUMP_L/R             K1 U20-U24 U30-U32 U40  J_ESTOP       │
       │ J_TOF2,3,8,9,10  J_DBG                      J_HANDS J_COVER J_NTC J_PAUX [J_HTR]  │
 v=0   └─H1──────── no connectors on rear edge u 26..134 ──────H2────────────────────H3────┘  rear
        u=0                                                                           u=160
```

- **Power end = right rear** (mechanical lead's allocation): J_PWR, pack switch, shunt, charger, VBAT_SW bulk, the latch relay and all chain logic. Pack current enters and leaves within 40 mm of J_PWR.
- **Centre on the gap pad**: both H-bridges, the VMOT eFuse and bulk capacitors, the 5 V buck, the clamp FET and resistors (U33, Q40, R on the pad edge). The charger straddles the pad's right edge (u 110–125): its QFN and L1 must be on the pad.
- **Brake relays next to their motor connectors**, long axis along u, outside the 12 mm front-corner zones (u < 14 or u > 146 with v > 88). Bridge output → relay NO → relay COM → ferrite → connector is one short, paired, wide route per motor (≤ 60 mm).
- **Logic end = left**: MCU, expanders, regulators, USB. The IMU sits alone at (80, 67) on the top side with no copper pour cut under it and no part within 4 mm; keep the bridges' switching nodes ≥ 10 mm away (v ≤ 56).
- **Connector rule**: only the right-angle Mini-Fit and Micro-Fit headers sit on the board edge. JST GH and CLIK-Mate headers are top-entry, ≤ 6 mm high, in rows 6–20 mm inboard of the edge named for them; their cables leave over the edge. Group by family: safety (CLIK-Mate, yellow silk box, legend "SAFETY CHAIN") never share a row with signal (GH).
- Side edges v 34–70 and the rear edge u 26–134: nothing overhangs, no connector faces them.

## 3. Stack-up

4 layers, 1.6 mm, 35 µm copper on all layers (JLC-class rules in `tools/eda`), ENIG.

| Layer | Use |
|---|---|
| L1 top | parts, power pours (VBAT_SW, VMOT, VSYS, V5), chain routes, short signal routes |
| L2 | solid GND, no splits. Only cut: none. |
| L3 | power planes as islands (VBAT_SW right half, VMOT centre, VSYS and 3V3 left), plus the long UART and I²C runs between planes |
| L4 bottom | small parts, signal routing, GND fill, exposed copper under the gap pad tied to GND through via arrays |

One ground. Return currents are steered by placement and by three net ties, not by plane cuts: (1) HEAD_HTR_N joins GND only at the VBAT_SW bulk capacitor (NT1); (2) the motor-stage ground (bridges' PGND, VMOT capacitors, clamp) connects to the rest of L2 through the continuous plane but all its decoupling loops close on L1 next to the parts; (3) VSSA/VREF decoupling returns to the MCU's ground pins directly.

## 4. Copper for current (outer layer, 35 µm, 20 K rise, IPC-2221 [C])

| Net class (`circuit.py NET_CLASSES`) | Design current | Minimum width | Use |
|---|---:|---:|---|
| HC_PACK | 20 A (fuse) | 12.3 mm, or pours on L1 + L3 stitched with ≥ 12 vias of 0.3 mm per transition | J_PWR → Q1/Q2 → R_SH1 → VBAT_SW bulk; GND return under it |
| HC_VMOT | 6.5 A | 2.6 mm | U8 → VMOT caps → U5/U6 → K2/K3 → J_MOT |
| HC_BRANCH | 5 A | 1.8 mm | heater branches, V5, VSYS, charger paths |
| PWR_1A5 | 1.5 A | 0.35 mm (use 0.5) | HEAD_PWR, LiDAR, logic rails |
| SAFETY_CHAIN | 0.1 A | 0.4 mm | chain nodes and coil nets |

Vias: 0.3 mm drill carries about 1 A at 20 K [A]; never fewer than 2 per power connection. Thermal vias (0.3 mm, 1 mm pitch) under U3, U5, U6, U8, U10, Q1, Q2 to the bottom-side copper under the gap pad.

## 5. Clearances

Highest working voltage is 26.4 V (VSYS while charging); everything is SELV. Electrical minimum is the fab rule (0.15 mm). Functional clearances that matter:

| Between | Clearance | Why |
|---|---:|---|
| SAFETY_CHAIN nets and any other net | ≥ 0.5 mm | a conductive bridge must not bypass an element |
| SAFETY_CHAIN nets and VBAT_SW / VMOT / VSYS / V12_AUX copper | ≥ 1.0 mm, no parallel run longer than 10 mm | a bridge to +12 V bypasses every element upstream of it (single-fault table #31) |
| Adjacent chain nodes (e.g. CH_N5 and CH_N6 at a photo-MOS) | ≥ 1.0 mm between the output pads; no via between them | a bridge closes that element |
| J_HEAD1 pins 5/6 routes and heater copper | ≥ 2 mm | heater edges couple into the loop sense |
| Relay contact pads (K2/K3) to coil pads | as the footprint (≥ 3 mm) | — |
| Switching nodes to SENSITIVE_ANALOG | ≥ 3 mm and a GND plane between | — |

## 6. Place and route these before the autorouter runs (in this order)

1. J_PWR, D(TVS), Q1, Q2, R_SH1, U1, U2 Kelvin pair, VBAT_SW bulk: pours, no thermals on power pads.
2. Charger hot loop: C(CHG_VIN/VSYS) – U3 – PGND; SW – L1 – R_SNSB – VBAT_SW; Kelvin pairs CLP/CLN and CSP/CSN routed as differential pairs from the inside of the sense pads.
3. U10 hot loops (VIN1–PGND1 and VIN2–PGND2 capacitors symmetric, < 3 mm from the pins), SW to L2 short; FB taken at the output capacitors, away from L2.
4. U11, U12 with their inductors and capacitors as compact cells.
5. U8, the three VMOT capacitors, U5 and U6 with their 100 nF + 10 µF at the VM pins; OUT1/OUT2 pairs to K2/K3; relay COM to the ferrites and J_MOT; 1 nF capacitors at the connector pins.
6. Brake resistors directly between the NC pads of each relay.
7. The whole chain as one L1 route in element order (F_CHAIN → J_MODE → J_ESTOP → J_HANDS → J_COVER → U20 → J_DOCK → U21 → U22 → J_BUMP_L → J_BUMP_R → U23 → U24 → K1), coil nets, COIL_RTN back to J_ESTOP. Taps branch off through their 100 kΩ resistor placed **at the chain node**, so everything after the resistor is high-impedance.
8. Shunts R_SH2–R_SH4 with Kelvin routes to U15; IPROPI resistors at the bridges with a quiet return; VREF_3V0 as a star from U14.
9. USB pairs (90 Ω), RS-485 pair (120 Ω) from U62 through R, L60, D60 to J_HEAD2 with the TVS at the connector.
10. Crystal Y1 with its capacitors within 5 mm of PF0/PF1, guard ground, nothing routed under it on L1.
11. IMU: SPI lines from the left, decoupling at the pins, no vias under the package.
12. ToF branches: each connector's ESD array and series resistors at the connector; mux in the middle of its group.

## 7. EMC measures built into the netlist (do not optimise away)

| Measure | Parts | Purpose |
|---|---|---|
| LC filter on the head electronics feed | L5, 2 × 10 µF | keeps 20 kHz ripple and bridge edges off HEAD_PWR |
| Slew-limited branch turn-on | DVDT capacitors on U13, U16–U19, U8 | no inrush steps on the shared bus when a heater or the head switches |
| Separate heater return | NT1 | 4 A heater current stays out of the J1 electronics return and out of the PRES_ID reference |
| Ferrite + 1 nF at each motor terminal | FB, C at J_MOT | bridge edges (150 ns [D]) stopped at the connector |
| Common-mode choke, TVS, series resistors on RS-485 | L60, D60, 2 × 10 Ω | motor-induced common mode on the 2.3 m data cable |
| Series 100 Ω + ESD array on every ToF line, ferrite on every ToF supply | per connector | 300 mm unshielded sensor cables next to the motors |
| RBOOT option on the 5 V buck | 0 Ω → up to 100 Ω | slows the SW edge if the scope shows ringing on VSYS |
| Chassis bonds | H1, H3 hard to GND; H2, H4–H6 through 1 MΩ ∥ 10 nF | one low-impedance bond at the power end, no ground loop through the tray |

## 8. Silkscreen and assembly notes

- Legends at every connector: function name and pin 1; safety connectors inside a yellow box.
- JP1 (watchdog → NRST) and JP2 (PB3 spare) labelled with their default state.
- "NOT A SAFETY-RATED CIRCUIT" near K1.
- K1–K3, J_PWR, the Micro-Fit headers and the electrolytics are the hand/selective-solder parts; everything else reflow.
- Conformal coating: allowed everywhere except connectors, relays (sealed types only), test points and the IMU; decide after the humid-return test.
