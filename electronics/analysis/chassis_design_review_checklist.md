# RR-CHS-MAIN / RR-PANEL design review checklist (before layout release)

Status of every line at the end of stage 1: **open** unless marked. "Evidence" names the file or test that closes it. This list is for the independent reviewer and the stage-2 engineer; it does not replace the verification register.

## A. Netlist integrity
- [x] `python3 electronics/chassis_main/design/circuit.py` passes (768 parts, 430 nets, no single-pin nets, no duplicate references). Evidence: tool-checked.
- [x] `python3 electronics/panel/design/circuit.py` passes (24 parts).
- [x] J_HEAD1 and J_HEAD2 pin tables equal `contract.yaml` J1/J2 (checked by the self-check).
- [x] RR-PANEL J1 equals RR-CHS-MAIN J_PANEL (checked by the panel self-check).
- [ ] Every `verify=True` part (132) checked against its datasheet: pin numbers, orderable code, footprint. Priority: U3, K1–K3, U13/U16–U19 pins 3 and 4, U42, U43–U45, U61, U20–U24, U1.
- [ ] MCU pin numbers cross-checked once more against `firmware/chassis/tools/check_pinmap.py` output.
- [ ] `connectors.yaml` regenerated after any netlist change (`gen_connectors.py`).

## B. Power
- [ ] Pack path resistance and fuse choice confirmed with the harness lead (20 A, AWG 14, Mini-Fit HCS terminals).
- [ ] LM74502 thresholds: UVLO 9.0 V, OV 16.5 V with the fitted resistors.
- [ ] Inrush at selector-on into 500 µF + the VSYS path: < 5 A peak (scope).
- [ ] Charger: all items of `chassis_design_notes.md` §1.
- [ ] 5 V rail at the carrier ≥ 4.85 V at 5 A; survives MCU reset.
- [ ] Each eFuse limit measured: 5.0, 1.5, 3.96 (HEAD_HTR after S2-04, R46 845 Ω), 3.04, 1.5 A (±10 %), VMOT 6.5 A.
- [ ] Branch defaults with the MCU held in reset: V5 on, LiDAR on, head and heaters off.
- [ ] Head branches forced off with 24 V on the inlet; both heaters off with the watchdog unsatisfied.
- [ ] LAB extension drop at 4 A ≤ 0.5 V with the real cable.
- [ ] Thermal: U3, U10, U5, U6 case temperatures at the worst sustained state on the gap pad.

## C. Safety chain (not a certified function)
- [ ] First power-up procedure, `chassis_safety_chain.md` §8, steps 1–15, with scope records of every drop time.
- [ ] Each of the 73 single-fault rows reviewed (stage 3 table); the five "no hardware barrier" faults of §6.1 and the latent ones accepted, or mitigated, by the hazard owner in writing.
- [ ] REARM cannot set, hold or re-set the latch through any single W-018 short or a held/welded contact (§8 step 7 a-f); set margin at 10 V / 12 V pack and hot coil (T11).
- [ ] K1 weld simulation on both poles (§8 step 9) and RUN_12V-to-supply simulation (§8 step 10).
- [ ] Head loop: each channel alone opens the chain (§8 step 3); U30 pins 1/7/8, U46 pins, R74 and the loop resistors on the AOI / inspection list.
- [ ] Firmware has the stage-3 readbacks (IOX_D: LATCH_NC_RB, LATCH_RUN_RB, HEAD_LOOP2_OK_RB, REARM_SET_RB) and the rules F1-F15 of `STAGE2_CHANGE_REQUESTS.md`.
- [ ] No tap, lamp or test point bridges any chain element (review the routed board, not only the netlist).
- [ ] Chain-to-supply clearances of `layout_guidance.md` §5: enforced by DRC since stage 3 (`RR-CHS-MAIN.kicad_dru` from `placement.chain_rules()`: 1.0 mm high-side chain to supply, 0.5 mm class, 2.0 mm loop to heater, 10 mm chain test-point spacing); re-run DRC on the routed board with zones filled.
- [ ] Brake readback thresholds measured (isolated < 0.1 V, connected > 0.4 V with VMOT at 0 V).
- [ ] Wheel spin-down with and without the brake resistor: rotor inertia and friction replace the assumed values; stopping-distance table regenerated.
- [ ] Slope holding angle measured.
- [ ] Watchdog: falling edge every 1, 10, 40 ms (TPS3430 WDI is falling-edge triggered [D]); JP1 behaviour with SWD and DFU.

## D. Drive
- [ ] Current limit 2.68 A, IPROPI scale, stall temperature rise.
- [ ] Encoder count integrity under PWM noise.
- [ ] Bus clamp threshold 15.6 V and behaviour with the pack switched off.
- [ ] Brake relays never break more than 2.7 A; contact wear plan (relay life at 80 mA coil-driven cycles is mechanical: 10⁶–10⁷ operations [U]).

## E. Interfaces
- [ ] RS-485: TXDEN timing, 10⁷ error-free records with motors and heaters active, presence events.
- [ ] USB: both devices enumerate through 0.3 m GH-to-USB-A cables; ESD.
- [ ] ToF: all 11 branches at 400 kHz with 300 mm cables; one branch shorted; one mux removed.
- [ ] PRES_ID decode at all five contract codes; loop window at 0.6 / 1.0 / 1.6 kΩ, open, short.
- [ ] Panel LEDs legible in daylight through the real light pipes; sounder level at 1 m.

## F. Mechanical / EMC / environment
- [ ] Height: nothing over 18 mm (12 mm in the front corners); bottom ≤ 3 mm.
- [ ] Connector positions against `board_envelopes.yaml`; top-entry connector clearance (CCR-E08).
- [ ] Cold soak −20 °C and −25 °C: all rails start, relays pick up at 10.5 V, GH and CLIK-Mate connectors mate and hold.
- [ ] Conducted noise on HEAD_PWR and the bit-error and ESD tests of `chassis_design_notes.md` §9.
- [ ] Humid return: no leakage across chain nodes (insulation > 10 MΩ between CH_N nodes and +12 V with the board damp).

## G. Documents
- [ ] Contract change requests CCR-E01…E12 answered.
- [ ] Module sheets: every [U] ordering detail confirmed before purchase.
- [ ] Power budget regenerated with measured loads; pack runtime confirmed on the 12 Ah pack at −20 °C.
