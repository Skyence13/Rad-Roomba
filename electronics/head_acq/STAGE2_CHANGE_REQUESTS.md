# RR-HEAD-ACQ stage 2 - change requests and deviations from stage 1

Owner: head electronics stage 2.  `design/` (stage 1) is NOT edited.  Every netlist-level item below is applied by
`overrides.py` (data with expected-baseline checks, log in `reports/overrides_applied.json`); layout items by `layout.py`.
**Net changes in rev A: none.**  `scripts/netcheck.py` proves the generated KiCad netlist is pin-for-pin identical to
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
VALUE / ADD / NOTE, each with an expected-baseline check); `scripts/netcheck.py` now accepts exactly these and nothing else.
Status of this section: **being implemented - values marked (prov.) may still change; re-read before coding.**

### S3-F: changes the head FIRMWARE must know (pins, polarities, scale factors, new nets)

| ID | Change | Firmware consequence |
|---|---|---|
| S3-01 (M2, CR-H10) | Lane-monitor taps moved off the comparator inputs: R125-class (all 8 channels, `Fn/Rn_MFAST`) pin 1 `xn_FCMP` -> `xn_FAST` (op-amp output); R134-class (4 floor channels, `Fn_MSLOW`) pin 1 `Fn_SCMP` -> `Fn_SLOW`; R119-class preamp taps (`xn_MPRE`, all 8) stay on PRE. All three tap classes 1 k -> **10 k**. | Monitor is a baseline / slow monitor only (bandwidth 10 k x 50-150 pF bus = 0.1-0.3 MHz). FAST code 000/001 now shows the op-amp output (before the 330 R / clamp), i.e. not clamped at 3.6 V. Settling after a mux change ~1 ms (allow 2 ms). |
| S3-02 (M2) | **True off state for the lane monitor**: decoder U2701 E3 (pin 6) moves from +3V3 to new net **`MON_LANE_EN`** = TCA9534 U2405 **P7** (was spare `EXP_P7`; test pad TP2402 stays on it). New pull-down **R2418 100 k** MON_LANE_EN -> GND. | MON_LANE_EN = 1 (P7 output high): selected lane mux on, as before. MON_LANE_EN = 0 or P7 left as input / expander absent / reset: **all four lane muxes off**. Park 0 whenever armed (no engineering capture). TCA9534 output register powers up 0xFF (recalled, UNVERIFIED): write output bit 7 = 0 BEFORE making P7 an output. The IMON mux U2703 (EN = +3V3) is unaffected, so IMON scanning may continue while armed once P7 = 0. |
| S3-03 (M5) | **Frame-bond fuse + frame-potential monitor**: new fuse **F2801** (Littelfuse 0466.500NR, 0.5 A very fast, 1206; MPN UNVERIFIED) in series with R2801 (FRAME - F2801 - new net `FRAME_F` - R2801 0 R - GND). R2802 (1 M frame bleed) pin 2 moves GND -> **MON_BUS**; monitor-bus bleed **R2702 100 k -> 1 M and its pin 2 GND -> VBL**. | With MON_LANE_EN = 0: **MON_ADC = VBL/2 + V(FRAME)/2 = 0.300 V + 0.5 x V(FRAME - GND)** (nominal 0.300 V; firmware stores the value at arm). Heater-to-frame fault: return-side contact gives V(FRAME) up to ~+70..90 mV (MON_ADC +35..45 mV); feed-side contact blows F2801 and the frame then floats at heater potential (MON_ADC up to ~VBL/2 + 7 V/2, clamped by the BAT54S on MON_ADC). Suggested rule: MON_ADC - stored value > 15 mV in a gate with MON_LANE_EN = 0 -> heater off + new health code (frame fault); compare readings with heater on/off. With a lane mux on the monitor gain is 0.98 (10 k into 1 M // 1 M) and the frame/VBL terms add < 1 %. |
| S3-04 (m2) | Pole-zero DC path removed: new **C(base+50)** (C150, C250 ... C850) in series with R_PZ (R120-class): R120-class pin 2 `xn_FS` -> new net `xn_PZ`, C xn_PZ -> xn_FS, **47 nF** (prov.) X7R. | No pin change. Post-alpha FAST undershoot reduced (numbers in head_afe_budget.md 2.3); the firmware 300 us alpha hold stays valid (conservative). |
| S3-05 (IB-58, CR-H12) | BIAS_VMON read-back divider R2217/R2218 stay **1 %** (no 0.1 % 4.99 M part found that I could verify); OVP trip and read-back are +-1.2 % worst case. | Calibrate BIAS_VMON per board against the HV_BUS pad (bring-up step 9), store the factor with the head identity; nominal 25.22. |
| S3-06 (IB-58, CR-H12) | "ramp HV_SET <= 5 V/s" means **5 V/s at HV_BUS** (= 0.2 V/s at the DAC output). Basis: ~9.8 uF of bias-bus capacitance (1 uF + 8 x (1 uF + 100 nF)) needs 49 uA at 5 V/s but 1.2 mA at 125 V/s (staircase steps of 12.5 V would hit the 2.0 mA ISHORT limit inside the 6 Hz loop). | `RRH_BIAS_RAMP_STEP_MV` 500 per 100 ms period (0 -> 31.5 V in ~6.3 s). |
| S3-07 (CR-H9, IB-58) | DAC output 7 of U_DAC0 = LED_AMPL, of U_DAC1 = DAC1_SPARE: the stage-1 self-check already maps both to `SPARE` when comparing with `pinmap.yaml`; the stage-3 check of the overridden netlist (`python3 overrides.py`) accepts `SPARE`, `LED_AMPL` and `DAC1_SPARE`. | Either name in `pinmap.yaml dac_map` passes; no rename forced. |
| S3-08 (C1) | **No new pin for an ALPHA-width / LLD-to-ALPHA capture in rev A** (decision, reasons in head_afe_budget.md 2.5): PF1 has no timer channel (pin DB: ADC2_IN10, COMP3_INM, SPI2_SCK, GPIO); freeing a capture pin means moving PULSER_A0 from PF2 (TIM20_CH3) to PF1 (takes the contract-reserved SYNC_IN pin) plus a 4-lane OR chain of the ALPHA comparator outputs (new board-wide event line, breaks lane identity). Recorded as rev-B request. | Keep TOT >= 250 ns on raw LLD; amplitude-ratio aid with the existing ULD comparator: see head_afe_budget.md 2.5 (firmware rule option, no hardware change). |

### S3-M: changes for HEAD MECHANICAL (`mechanical/head/asbuilt.py` reads the board file)

(filled in as the placement is done - see below)
