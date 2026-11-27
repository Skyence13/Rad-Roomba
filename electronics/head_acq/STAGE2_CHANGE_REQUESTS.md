# RR-HEAD-ACQ stage 2 - change requests and deviations from stage 1

Owner: head electronics stage 2.  `design/` (stage 1) is NOT edited.  Every netlist-level item below is applied by
`overrides.py` (data with expected-baseline checks, log in `reports/overrides_applied.json`); layout items by `layout.py`.
**Net changes: none in stage 2; stage 3 (review fixes, section "Stage 3" below) adds S3-01..S3-05.**  `scripts/netcheck.py` proves the generated KiCad netlist is pin-for-pin identical to
`design/circuit.py` (2987 pins, 581 nets, values / MPN / manufacturer / DNP state) apart from the S2-01 pad renumbering.

## A. Requests to the stage-1 owner (circuit.py / layout_guidance.md)

| ID | Kind | Change | Reason | Status |
|---|---|---|---|---|
| S2-01 | RENUM (no electrical change) | Exposed pad "EP" -> footprint pad number: U2001 17; U2103, U2104, U2402, U2403 7; U2201, U2301..U2304 17 | KiCad stock footprints number the exposed pad after the last lead | applied in overrides.py; please adopt the numbers in circuit.py |
| S2-02 | GROUP (no electrical change) | AFE_FLOOR / AFE_REF / LANE split per lane: LANEk_FLOOR, LANEk_REF, LANEk_LOGIC | four visibly identical schematic sheet sets; `board.replicate()` works on identical groups | applied |
| S2-03 | NOTE (IB-21) | J2002..J2004 pins 3/4, R2013..R2018, C2008..C2010, D2002..D2004: "zone identification NOT AVAILABLE in rev A" | single-pole rail switches; footprints and parts kept, inputs idle high | applied |
| S2-04 | NOTE (IB-38) | R2801 0 ohm FRAME-GND bond: FITTED IN BOTH BUILDS (stage-1 note "remove if the frame touches the chassis" replaced) | lead decision 2026-11-26 | applied; `mechanical/head/production/README.md` section 4 still describes the bonded-shoe scheme (head mechanical to correct, IB-38) |
| S2-05 | NOTE (IB-25) | SiPM breakdown spread within a head <= **2.0 V** | TRIM DAC range 0.10..2.50 V = 2.4 V; 0.4 V reserved for the per-lane temperature difference (beta x dT between lanes on one spreader) and the I x 4.99 kOhm floor of the trim buffer at higher dark current. 2.0 V = the RFQ value (CCR-HE-06 c); budget table line "<= 2.4 V" should read 2.0 V | applied as note on U2304 + DAC sheet; please update head_afe_budget.md section 1 |
| S2-06 | LIB | Symbols: stock where pin numbers AND functions match (74LVC2G53, OPA690xDBV for OPA838/OPA836, TLV3501AIDBV, TPS7A05xxPDBV for TPS7A2050, TLV76733DRVx, BZX84Cxx, TLV7041DBV for TLV7021, ASE-xxxMHz for the TCXO, TCA9534, SUD50P04-08, D_Zener for the unidirectional SMBJ16A); project-local typed symbols for TLV3502 (DCN), LMR51606, TPS61391, DAC60508, ISO1430, ISO7710, TMP117 (with EP), shield can. Footprints: local Harwin S1711-46R clip, TDK ACM4520 (both FROM MEMORY, verify), pad-less shield-can outline | 114 hints rejected by the importer trial; 4 parts without footprint (cans) plus 2 footprint names that do not exist (RF_Shielding:Harwin..., Inductor_SMD:L_CommonMode_TDK_ACM4520) | applied |
| S2-L1 | layout rule | HV net class clearance **1.0 mm** (stage 1: 1.5 mm) | the 0603/0805/1206 HV parts and the SOT-23 pass/clamp parts of the bias block cannot keep 1.5 mm between neighbouring pads of different HV nets; 1.0 mm is 1.6 x IPC-2221B B2 (0.6 mm, 51-100 V, uncoated). Pad spacing inside one HV component is the part's own and is waived as such | applied; stage 1 to confirm |
| S2-L2 | stack-up | **6 layers** (F sig / In1 GND / In2 sig / In3 sig / In4 power split / B sig), 1.6 mm; stage 1 and board_envelopes.yaml say 4 | 1008 fitted parts, four DAC/MCU buses and the guidance "no signals under the cans on L3": 4 layers leave one routing layer under the cans. In1 is an unbroken GND plane (except the isolated island), In4 carries the +5V_A / +3V3_EVT / +5V6 / +3V3 islands the guidance puts on L3 | applied; envelope record "layers: 4" to be updated (no mechanical effect) |
| S2-L3 | layout | Channel columns inside the can are a TRANSLATED copy (floor column origin du -18.0, reference du +4.25), not a mirror; anode inputs at du -10.38 and +11.87 = **22.25 mm apart** (guidance 12-22 mm); bias U.FLs at du -15.47 / +6.78; auxiliary GH-6 at du -1.80 | one placement/pre-route table serves both channels; the GH-6 (12 mm courtyard) only fits between the two U.FL pairs with this pitch | applied |
| S2-L4 | layout | Lane block shifted 2.75 mm forward: can v 8.25..40.25 (CR-M01), HV_BUS trunk on F.Cu at v 43.0 (guidance 39), lane logic v 45..67 (guidance 38..62); bias cell v 67..95 (guidance 62..82) | follows CR-M01 | applied |
| S2-L5 | layout | J2001 and J2601 side by side at the rear edge (J2601 body u 50.2..72.0, J2001 u 73.0..100.7), mating faces rearward | J1_LANDING (u 50..100, v 0..18 under the 8.9 mm blister) cannot hold J2001 (27.8 mm body) + J2601 (21.8 mm) + H1 (6 mm keep-out) as stage 1 assumed; see CR-M02/M03 | applied, needs CR-M02 + CR-M03 |
| S2-L6 | layout | J2004 (rail switch R) at u 144.6 (outside RAIL_SWITCH_LANDING u 150..176) | the H5 keep-out (u 159.5..166.5) leaves room for only two GH-4 in the landing | applied; rail-switch harness to reach u 140..149 |
| S2-L7 | layout | TMP117 U2402 at (53, 39), U2403 at (240, 34) (guidance (75, 20) / (250, 32)) | (75, 20) is now the heater switch cell | applied |

## B. Requests to head mechanical (shared parts; the board is built to these values)

| ID | Item | Request | Reason |
|---|---|---|---|
| CR-M01 | lane shield can RR-HEAD-SHLD-A position | Can outline v **8.25..40.25** (drawing / `parts.shield_can()`: 5.5..37.5), same 36 x 32 x 5 mm, 0.2 mm wall, 12 clips (rear wall clips at du -6.5, +2.5, +15.0; side walls at v 15.25 / 24.25 / 33.25; front wall du -12 / 0 / +12) | the lane auxiliary JST GH-6 (rear edge, 1.5 mm edge rule) reaches v 6.7 with its contact pads and v 7.25 with its courtyard; the can wall at v 5.5 would sit on the GH pads. Heights unchanged (can top 41.1 vs liner 42.5) |
| CR-M04 | mouse holes in the rear wall | Two 2.0 x 1.2 mm holes at du **-10.38 and +11.87** (drawing: +-6.0) | anode U.FL positions of the translated channel layout (S2-L3) |
| CR-M02 | mounting hole / standoff H1 | Move H1 from (u, v) = (75.5, 4.5) to **(75.5, 30.0)** (base_link x 113.2, y 87.5; still on the S0/S1 seam rib) | J2001 must sit at the rear edge centred near the J1 cable port; H1 at v 4.5 lies under the header body |
| CR-M03 | J1 port, rear-strip lid standoffs | (a) J1 cable port / grommet to y = **76.2** (board u 86.8, J2001 centre; was y 87.5 = u 75.5); (b) the rear-strip lid standoffs at (77.5, +70.5) and (77.5, +104.5) (board u 92.5 and 58.5, v -5.7) lie under the mated J2001 / J2601 receptacles (plug bodies over the rear strip u ~51..100, v -8.4..1.5): move them to y ~ +59 and +116 (board u ~104 / ~47, between the chimneys) together with the J1 P-clip | rear-strip space for the two mated Micro-Fit receptacles |
| CR-M05 | blister height | 8.9 mm blister over J1_LANDING kept; the board assumes the Micro-Fit RA headers seat <= 6.0 mm (CCR-HE-02, UNVERIFIED); the mated plugs overhang the rear edge | confirm with the Molex drawing |

Mechanical items checked as unchanged: all 35 lid screws, 18 wall bosses, 17 lid standoffs (except the two in CR-M03), EMI
fences and the desiccant strip lie outside the 326 x 96 board outline (`mechanical/head/hp.py`: rear standoffs x 77.5 <
board rear edge 83.2; front bosses x 184.2 > front edge 179.2; side bosses |y| 168.4 > 163); the 3 mm external foam
jacket sits on the lid (no effect on the board).

## Stage 3 (review fixes) - `docs/reviews/REVIEW_head_interference.md`, IB-57/58/61, CR-H9..H16

Owner: head electronics stage 3 (2026-11-27).  Netlist changes are applied by `overrides.py` (IDs S3-xx, kinds NET /
VALUE / ADD, each with an expected-baseline check); `python3 overrides.py` re-runs the stage-1 self-check on the overridden
netlist (PASS) and proves that the pin-level diff against `design/circuit.py` is exactly the listed S3 entries (39 pins moved,
21 values, 10 parts added); `scripts/netcheck.py` accepts exactly these in the KiCad netlist and nothing else.
**Net changes in rev A are no longer "none": see S3-01..S3-05.**

### S3-F: changes the head FIRMWARE must know (pins, mux control, polarities, scale factors, new nets)

| ID | Change | Firmware consequence |
|---|---|---|
| S3-01 (M2, CR-H10) | Lane-monitor taps moved off the comparator inputs: R125-class (all 8 channels, `xn_MFAST`) pin 1 `xn_FCMP` -> `xn_FAST` (OPA838 output); R134-class (4 floor channels, `Fn_MSLOW`) pin 1 `Fn_SCMP` -> `Fn_SLOW` (OPA836 output); R119-class preamp taps (`xn_MPRE`, all 8) stay on PRE. All three tap classes 1 k -> **10 k**. MCU pins unchanged. | Monitor = baseline / slow monitor only (10 k x 50-150 pF bus = 0.1-0.3 MHz). Mux code 000/001 shows the FAST op-amp output (before the 330 R + clamp, not clamped at 3.6 V). Monitor gain 0.98 (10 k into 1 M // 1 M). Settling after a mux change: allow 2 ms. |
| S3-02 (M2) | **True off state for the lane monitor**: decoder U2701 E3 (pin 6) from +3V3 to new net **`MON_LANE_EN`** = TCA9534 U2405 **P7** (was spare `EXP_P7`, renamed; test pad TP2402 on it). New pull-down **R2418 100 k** MON_LANE_EN -> GND. Polarity: active high. | MON_LANE_EN = 1: selected lane mux on (as before). 0, P7 left an input, expander absent or in reset: **all four lane muxes off**. Park 0 whenever armed (except engineering capture). TCA9534 output register powers up 0xFF (recalled, UNVERIFIED): write output bit 7 = 0 BEFORE configuring P7 as output. IMON mux U2703 (EN = +3V3) is independent: IMON scanning while armed is harmless once MON_LANE_EN = 0 (the MON_MUX_A2 toggling no longer reaches any closed switch). |
| S3-03 (M5) | **Frame-bond fuse + frame-potential monitor**: new fuse **F2801** (Littelfuse 0466.500NR, 0.5 A very fast, 1206; MPN/I2t UNVERIFIED) in series with the 0 R bond: FRAME - F2801 - new net `FRAME_F` - R2801 - GND. R2802 (1 M frame bleed) pin 2 GND -> **MON_BUS**; monitor-bus bleed **R2702 100 k -> 1 M, pin 2 GND -> VBL**. | With MON_LANE_EN = 0: **MON_ADC = 0.300 V + 0.5 x V(FRAME - GND)** (VBL/2 + V_FRAME/2). Store the reading at arm. Return-side heater-to-frame contact: +35..45 mV; feed-side contact: F2801 opens, frame floats at heater potential, MON_ADC rises to the BAT54S clamp. Suggested rule: > 15 mV above the armed value in a gate with MON_LANE_EN = 0 -> heater off, new health code (frame fault). With a lane mux on, the frame and VBL terms add < 1 %. |
| S3-04 (m2) | Pole-zero DC path removed: new **C150, C250 .. C850** (47 nF X7R 0402, GRM155R71C473KA01D) in series with R_PZ: R120-class pin 2 `xn_FS` -> new net `xn_PZ`; C `xn_PZ` - `xn_FS`. | No pin change. Post-alpha FAST tail after 15 000 p.e.: -0.5 p.e. at 150 us, +0.06 at 300 us (was -2.6 / -3.3, the stage-1 network plus the trim-node step; review model -3.1 / -0.1). The 300 us hold of 0.5.1 is conservative; 150 us would now do. |
| S3-05 (M3) | Frame copper islands per hole: hole pads H2802..H2808 move from `FRAME` to `FRAME_H2` .. `FRAME_H8`; C2801/C2803/C2804 on FRAME_H2/H5/H6, **C2802 moved from H3 to H8** (H3 is inside the isolated RS-485 island, which has no GND), C2504/R2505 (J2 shield) on FRAME_H3. H1 group stays `FRAME`. | None (no MCU-visible net). |
| S3-06 (IB-58, CR-H12) | BIAS_VMON read-back tops R2217/R2218 stay **1 %** (no 4.99 M 0.1 % part verified); only the bottom R2219 is 0.1 %. Read-back and OVP trip +-1.2 % worst case. | Calibrate BIAS_VMON per board against the HV_BUS pad at bring-up step 9; store the factor with the head identity (nominal 25.22). |
| S3-07 (IB-58, CR-H12) | "ramp HV_SET <= 5 V/s" means **5 V/s at HV_BUS** (0.2 V/s at the DAC output). Basis: ~9.8 uF on the bias bus (1 uF + 8 x 1.1 uF) takes 49 uA at 5 V/s but 1.2 mA at 125 V/s, and 12.5 V staircase steps inside the 6 Hz loop hit the 2.0 mA ISHORT limit. | `RRH_BIAS_RAMP_STEP_MV` 500 per 100 ms (0 -> 31.5 V in 6.3 s). |
| S3-08 (CR-H9) | DAC output 7 names: the stage-1 self-check maps LED_AMPL / DAC1_SPARE to `SPARE` already; the stage-3 check (`overrides.py`) also accepts `LED_AMPL` / `DAC1_SPARE` in `pinmap.yaml dac_map`. `design/` is not edited; request L-06 to stage 1. | Either name passes; no rename forced. |
| S3-09 (C1, firmware 0.5.1 question) | **No ALPHA-width / LLD-to-ALPHA capture pin in rev A** (decision). PF1 has no timer channel (pin DB `firmware/head/tools/stm32g474ve_lqfp100_pindb.json`: ADC2_IN10, COMP3_INM, SPI2_SCK, GPIO). A capture pin can only be freed by moving PULSER_A0 from PF2 (TIM20_CH3) to PF1 - which takes the contract-reserved SYNC_IN pin - plus a board-wide OR chain of the four floor ALPHA comparator outputs (new event line through all lanes, breaks lane identity). Not needed for the candidate single devices: T13 gives 130-170 ns between the brightest beta (240 p.e.) and the weakest alpha (150 p.e.) at the LLD. Rev-B request L-03. | **Make the TOT cut a per-device setup value, mid-gap** (head_afe_budget.md 2.5): J60035 ~290 ns, J30035 ~180, S14160 ~215, S13360 ~190, NUV-MT ~200, 4 x J60035 ~655 ns. The fixed 250 ns is too high for J30035/S13360 (weakest alpha 246/258 ns) and useless for arrays. The "27 ns margin" came from the review's >= 280 ns bound; this model gives 374 ns for J60035 at LLD 10. Optional amplitude-ratio aid (no hardware): BETA_ULD ~ 12 x ALPHA level. |
| S3-10 (M1) | Dark criterion 0.05 s^-1 per chain: default LLD for J60035 @2.5 V at +10 C = **10 p.e.** (11 at max DCR), not 8 (head_afe_calc_out.md T6). | CR-H16 defaults: LLD 10 p.e.; still placeholders until the device is known (O6: refuse ARM with placeholder thresholds once a device type is set). |

### S3-M: changes for HEAD MECHANICAL (`mechanical/head/asbuilt.py` reads `RR-HEAD-ACQ.kicad_pcb`)

| ID | Item | Change (board u, v mm; base_link = (83.2 + v, 163.0 - u)) |
|---|---|---|
| CR-M06 (IB-61) | J2001, J2601 (Micro-Fit RA) | **moved 7.0 mm forward**: pin rows v 10.57 -> **17.57** (u unchanged: J2001 pins u 97.34..76.34, J2601 u 68.58..53.58); courtyards v 8.11..19.11 (J2001 u 72.47..101.22, J2601 u 49.70..72.45); mating faces v ~8.5; **mated plugs v -1.4..8.5** (were -8.4..1.5): plug backs at base x 81.8 (was 74.8) = **9.0 mm** to the rear-wall inner face x 72.8 (2.0 / 1.4 mm before; ~8 mm needed). J1 port y 76.2 unchanged (J2001 centre u 86.8). Header bodies now reach v 19.1: the J1_LANDING blister zone (v 0..18, 8.0 mm) should extend to **v 20** (or the 6.0 mm general limit applies to the last 1.1 mm of the header body, seat height UNVERIFIED CCR-HE-02). Board keep-out `KO_PLUG_J1` (no footprints u 50.45..100.9, v 0..8.5). |
| CR-M07 (IB-61) | Lane shield cans RR-HEAD-SHLD-A, all four | **side-wall clips moved** from v 15.25 / 24.25 / 33.25 to **v 23.5 / 29.0 / 34.75** (CAN_V0 + 15.25 / 20.75 / 26.5), both side walls, all lanes; rear (du -6.5 / 2.5 / 15.0) and front (du -12 / 0 / +12) wall clips unchanged; can outline v 8.25..40.25, mouse holes unchanged. Reason: the forward headers stand beside the lane-0 right and lane-1 left walls up to v 19.1. Can drawing: clip dimples / tabs on the side walls follow. |
| CR-M08 (IB-61) | J2 header J2501 (GH-8 side entry, unchanged at (262.3, 4.0)) | plug overhang (not measured; GHR-08V-S housing depth ~4.5 mm + ~2 mm crimp/strain, recalled UNVERIFIED): plug back ~v -4, wires leave at ~v -6, i.e. ~4.5 mm to the wall inner face (v -10.4) for AWG 26 FEP (>= 2 x OD + 2 mm = 4 mm). Head mechanical to check against the nearest standoff (IB-61: 3.4 mm) with a plug keep-out u 255.0..269.6, v -6.5..0.75, z 36.1..40.4. |
| - | Holes, cans, other connectors, heights | H1..H8 unchanged; can outlines unchanged; U.FL / GH-6 positions unchanged (IB-57: coax pigtail length is not a pickup issue, T16); new parts all <= 1.0 mm high (fuse 1206, 0402/0603 passives); bottom side still empty. |
| - | Harness lengths for head mechanical / harness | W-101 and W-103 inside the head +7 mm (J2001/J2601 7 mm further forward). Drain W-101.S to TP2004 at (83.0, 29.1) - 9 mm in front of J2001 - about 45 mm (was 130); W-102.S to TP2501 at (241.5, 2.5) next to H3 / the J2 port - about 25 mm (was 110). |

### S3-H: harness / chassis requirement (review M4, IB-09) - owner: harness + chassis electronics

| ID | Requirement |
|---|---|
| H-01 | **Motor-terminal suppression at each gearmotor** (W-006 / W-007, chassis BOM): (a) one 47-100 nF capacitor across the two motor terminals (X7R >= 50 V 1206, or film), (b) one 4.7-10 nF capacitor from EACH terminal to the motor can (X7R >= 100 V), all soldered AT the motor terminals with <= 5 mm leads, (c) the can bonded to the chassis plate with a short strap (<= 30 mm, >= 2.5 mm wide braid or tab), (d) the motor pair twisted to the motor, the encoder pair routed away from the head side. Band that matters: **1-100 MHz** (commutation arcs ~5 ns, PWM edges 150 ns; the FAST shaper passes 1-30 MHz at full gain); the BLM31 bead + 1 nF at the chassis board connector acts only above ~50 MHz and only at the board end. Brush noise is PWM-independent: verify with the motors on a DC bench supply at 100 %, back-driven with the bridges asleep, and through brake-relay transitions (budget B11). |
| H-02 | Coax pigtails mandatory (IB-23 stands); their length is free (T16: the coax case does not depend on it); lay each anode/bias coax pair and the aux pigtail as one tight bundle tied every 10 mm; carrier ground never touching the spreader/frame (review m1). |
| H-03 | Heater conductors (IB-32, IB-61 decision below): W-101.3/.4 and W-103 heater conductors **AWG 20** with Micro-Fit 3.0 terminal **43030-0007 (20-24 AWG)** at the head end. |

### Heater-pair contact decision (IB-32 head end, IB-61)

* Same family as the chassis end (Mini-Fit Jr): **does not fit**. A Mini-Fit Jr right-angle header is ~12-13 mm tall (recalled, UNVERIFIED) against the
  8.0 mm J1_LANDING zone under the 8.9 mm blister (with the plug the lid would pass the 50 mm ceiling), and an 8-way Mini-Fit Jr (4.2 mm pitch, dual row)
  plus J2601 does not fit the 49.5 mm between the lane-0 and lane-1 can clips.
* Split the current over more contacts: **does not fit in rev A**. J2601 would need 7 contacts (2 feed, 2 return, cut-out, NTC, NTC return) = 3 mm more, and
  J2001 + J2601 already fill the space between the cans exactly (51.5 mm of courtyards in 51.5 mm); J2001 is bound to the contract J1 pin table (one contact
  per heater pole, pin 8 the only spare).
* **Decision: Micro-Fit 3.0 stays at the head end with one contact per heater pole; the head-end heater conductors become AWG 20 crimped into the 20-24 AWG
  terminal 43030-0007** (the terminal the harness already lists), which removes the recalled "18-24 AWG variant". Load: 3.13 A continuous at 15 V (4.8 ohm),
  2.5 A at 12 V; 4.35 A is only the upper trip limit of the chassis 4.05 A eFuse (3.6-4.4 A), a transient until it trips. Micro-Fit 3.0 rating at AWG 20
  recalled ~5 A per circuit (UNVERIFIED - the one Molex fetch failed, HTTP 503): margin 1.6 x continuous. Voltage drop: AWG 20 instead of 18 over 2 x 0.29 m
  adds ~7 mOhm (22 mV at 3.1 A). Lead request L-02: split the heater poles over two contacts each in the next J1 contract revision.

### S3-L: requests to the lead / stage 1 / other owners

| ID | To | Request |
|---|---|---|
| L-01 | Lead (IB-38) | Frame bond is now F2801 (0.5 A fuse) + R2801 0 R in series, still the single DC bond, fitted in both builds. Accept. |
| L-02 | Lead, interface | J1 contract revision: two contacts per heater pole (HEAD_HTR_P, HEAD_HTR_N) at the head end (IB-32). |
| L-03 | Lead, firmware (rev B) | A timer-capture input for OR(ALPHA comparator outputs F0..F3) (ALPHA width / LLD-to-ALPHA delay), and separate address lines for the IMON mux (review M2 rev-B item). |
| L-04 | Registers / RFQ owner (IB-22, M1) | RFQ: **>= 18 p.e. guaranteed at the MPV deposit of a normally incident MIP at the worst point of the 80 x 100 mm plate**, at the stated overvoltage and +10 C, position map >= 9 points (= 1.6 x LLD(0.05 s^-1, +10 C, max DCR) for another device); ZnS(Ag) decay time of the supplied layer (the alpha TOT cut depends on it). Radiometry to re-derive K_beta from the T17 efficiency. |
| L-05 | Head mechanical / BOM (M5) | Cut-out with isolated case (>= 100 MOhm case-to-terminals at 100 V, in the BOM line), NTC with isolated lug (or 0.1 mm polyimide pad); end-of-line check E2 of `head_design_review_checklist.md`. |
| L-06 | Stage 1 (`design/`) | (a) self-check: accept LED_AMPL / DAC1_SPARE for DAC output 7 (CR-H9); (b) `layout_guidance.md`: R2801 + F2801 at H1, C2801..C2804 at H2/H8/H5/H6, stack-up of README section 3, monitor bandwidth, heater-ground links (m5), base_link origin note (IB-27, README section 2). |
| L-07 | Test plan (docs/build) | Review M7 items into the T-sheets: averaged aggressor-synchronised capture at FCMP; MON_LANE_EN and IMON-scan states; motor states; CM clamp injection; assembled-head insulation check. |
