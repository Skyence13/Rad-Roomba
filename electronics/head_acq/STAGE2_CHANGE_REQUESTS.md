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
