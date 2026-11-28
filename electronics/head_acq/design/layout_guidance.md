# RR-HEAD-ACQ rev A — layout guidance for stage 2

Source of truth for nets and parts: `circuit.py` (net classes and per-class rules in `circuit.NET_CLASSES`, board data in `circuit.BOARD`).
Mechanical frame, holes, zones and height limits: `mechanical/common/board_envelopes.yaml` (authoritative).
Board frame: origin at the rear-left corner seen from above, **+u toward robot right, +v forward**, 326 × 96 mm, 1.6 mm, 4 layers, parts on top only
(6.0 mm top, 2.0 mm bottom — the bottom side is left empty and faces the spreader plate through an insulating film).

## 1. Floorplan

```
 v=96 +-----------------------------------------------------------------------------------------------+
      | H4            SERVICE strip (v 84..96): SWD pads, debug UART, J2701 monitor U.FL,   H5      H6 |
      |               test pads, rail-switch connectors J2002..J2004 at u 150..176                     |
 v=84 |-----------------------------------------------------------------------------------------------|
      |  lane 0 digital | HEATER  | REG     | lane 1 dig. | BIAS (front) | DAC  MCU  TCXO | lane 2 dig. | COMM     | l.3 |
      |  (latches, OR,  | switch  | buck +  |             | u 100..140   | u 140..190     |             | isolator | dig.|
 H7   |   mux)          | shunt   | LDOs    |             | v 62..82     | v 40..84       |             | u228-274 | H8  |
      |  du +-18        | u52-98  | u 60-98 |             |              |                |             | v 2..30  |     |
      |  v 38..62       | v 2-40  | v 40-60 |             |              |                |             |          |     |
 v=38 |- - lane cans end - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -|
      | [ lane-0 can ]  | J1 landing        | [ lane-1 can ]        | [ lane-2 can ] | J2 landing | [lane-3 can]|
      |  u 13.75..49.75 | J2001, J2601      | u 101.25..137.25      | u188.75..224.75| J2501      | u276.25..312.25|
 v=5.5|  UFL UFL GH UFL UFL  (rear edge)    |  UFL UFL GH UFL UFL   |                |            |             |
 v=0  +---H1(75.5)----------------------------------H2(163)------------------------H3(250.5)----------+
        S0 centre u=31.75                 S1 centre u=119.25        S2 centre u=206.75        S3 u=294.25
        (rear edge = SiPM pigtail chimney; J1 cable enters at u~75.5, J2 at u~250.5)
```

Lane block (identical for the four lanes; place lane 0, then copy with Δu = 87.5 mm):

| Region (du relative to the lane centre, v) | Contents |
|---|---|
| du −13…+13, v 1.5…5.5 (rear edge) | Floor pair `J(100c+1)` anode and `J(100c+2)` bias U.FL at du −11 and −6; lane auxiliary JST GH-6 `J(1000+100k+1)` at du 0 (cable exits rearward, body may not overhang the edge); reference pair at du +6 and +11. Centre-to-centre ≥ 4.5 mm so that locking MHF plugs fit. |
| du −18…+18, v 5.5…37.5 = **lane shield can** | Left half (du < 0) floor channel, right half reference channel, mirror-ordered so that the two anode inputs are 12–22 mm apart. From rear to front: bias filter and anode clamp/R_IN/trim node (v 6–11), test-injection switch (v 8–12, next to its anode node), preamp (v 11–16), fast CR and gain stage (v 16–22), slow stage for the floor channel (v 22–27), clamps and comparators (v 28–36), with the comparator outputs leaving through the front wall. |
| du −18…+18, v 38…62 (outside the can, same width so that the block clears the J1/J2 landings and the heater/regulator cells in every lane) | OR gates U(1000+100k+2/3), latches U…4–6, 47 Ω source resistors, lane monitor mux U…7, trim buffer U…1, LED pulser parts. Shield-clip bodies stay inside the can outline (lane 0 can ends at u = 49.75, the J1 landing starts at u = 50). |

Board-level blocks:

| Block (`circuit.py` instance) | Place at | Notes |
|---|---|---|
| POWER_IN (2000) | J1 landing u 52–98, v 2–18 | J2001 (8-way) at the rear edge next to H1; TVS, CM choke, eFuse and π filter in a line going forward; rail-switch connectors are the exception (front edge, u 150–176). |
| HEATER (2600) | u 52–98, v 2–40 beside POWER_IN | J2601 heater/NTC connector at the rear edge; shunt, P-FET, TVS. The complete heater current loop (J2001.3 → shunt → FET → J2601.1 … J2601.2 → J2001.4) must stay inside u 52–98, v 0–40 and is routed as a tight feed/return pair. |
| POWER_REG (2100) | u 60–98, v 40–60 | Buck with its input/output capacitors and inductor in a 12 × 12 mm cell; LDOs fan out from it: +5V_A toward the rear, +3V3_EVT along v 40, +3V3 toward the MCU. |
| BIAS (2200) | u 100–140, v 62–82 (front, between lanes 0/1 digital areas) | Boost cell (U2201, L2201, D2201, C) as far forward as possible; linear regulator and dividers between boost and the HV_BUS trunk; lid connector J2201 on the front edge. Board NTC next to the boost inductor. |
| DAC (2300) | u 140–190, v 40–62 | Four DACs in a row; threshold/trim outputs leave toward both sides along v 38–40 on layer 4. |
| MCU (2400) | u 150–185, v 62–84 | LQFP100 with pin 1 toward the rear-left; TCXO within 15 mm of pin 12; SWD pads and debug connector in the SERVICE strip. TMP117 U2402/U2403 at the rear edge at u ≈ 75 (v 20) and u ≈ 250 (v 32) — away from the regulators. |
| COMM (2500) | J2 landing u 228–274, v 2–30 | J2501 at the rear edge next to H3; isolated island = u 228–274, v 0–14; ISO1430 straddles the barrier at v 14–18. |
| MONITOR (2700) | decoders and IMON mux next to the DACs; monitor buffer and J2701 in the SERVICE strip at u ≈ 200 | |
| MECH (2800) | holes at the envelope coordinates; R2801 (0 Ω frame bond) and R2802 at H1; the four 10 nF frame capacitors at H2, H3, H5, H6; fiducials at three corners | |

## 2. Stack-up

| Layer | Use |
|---|---|
| L1 (top, 1 oz) | all components; ANALOG_SENSITIVE and HV routing; short local routes |
| L2 | **unbroken GND plane over the whole board** except the isolation barrier at J2 and the BUS_GND island |
| L3 | power: +5V_A island under the AFE strip (v 0–40), +3V3_EVT under the lane digital areas (v 38–60), +3V3 under the MCU/DAC area, +5V6 trunk; no signals under the lane cans |
| L4 (bottom, 1 oz) | long digital and DC analogue runs (BUSY/ULD/ALPHA/LLD/CLR to the MCU, thresholds, trims, baseline, monitor bus); GND pour elsewhere; no components; **no HV** (it faces the spreader through 0.25 mm of film) |

Standard 1.6 mm FR-4, 0.2 mm L1–L2 prepreg preferred (tight coupling of the sensitive nets to ground). Controlled impedance is needed only for the RS-485 pair (120 Ω differential, short) and is not critical at 1 Mbaud.

## 3. Grounding and return currents

* **One ground net.** The only DC connection to the robot is J2001 pin 2 (J1 pin 2) through the common-mode choke. Do not split the plane; partition by placement:
  rear 38 mm analogue, front digital/power, with the lane digital areas as the buffer between them.
* **Heater return is not ground.** `HEAD_HTR_N` appears only on J2001.4, J2601.2, the heater TVS and bypass capacitor. It must not touch the GND plane; keep 1 mm clearance to pours. The only links between the heater domain and ground are the 100 kΩ sense resistors and the INA180 inputs.
* **Isolated island.** `BUS_GND`, `BUS_5V(F)`, the RS-485 and sync pairs live on all four layers inside u 228–274, v 0–14; ≥ 4 mm copper-free barrier on every layer, crossed only by the ISO1430 (and the DNP ISO7710). J2501 mounting pads are on BUS_GND.
* **Frame / spreader bond (single defined DC point).** All eight mounting-hole pads are on net `FRAME`, not on GND. `FRAME` is tied to GND by R2801 (0 Ω, fitted) next to H1, the hole nearest the J1 entry, plus 1 MΩ and four 10 nF capacitors (H2, H3, H5, H6) for RF. The EMI cover bonds to the spreader/`FRAME`, not to the board ground. Cable shields go to `FRAME` through 1 MΩ ∥ 10 nF (contract).
  If the docked head frame turns out to touch chassis metal, R2801 is removed (CCR-HE-03).
* **Lane shield cans** are on GND (board ground), through their 12 clips, with a via to L2 at every clip pad.
* **Return paths to respect:** comparator and latch supply currents close through +3V3_EVT decoupling inside the lane digital area — the +3V3_EVT island must not extend under the can. Boost switching loop (L2201, U2201.SW, D2201, C at HV_RAW) < 60 mm² with its own via cluster to L2. Buck hot loop (C2101/C2102, U2101, L2101) likewise.

## 4. Shielding — what the board needs from the head mechanical EMI cover (IB-09)

The prototype housing is plastic, so the board assumes no screening from it.

On the board (already in `circuit.py`): one formed can per lane, **36.0 × 32.0 mm outside, 5.0 mm high, 0.2 mm wall**, covering du −18…+18, v 5.5…37.5, held by 12 SMT clips (3 per side) on GND.
The rear wall has two 2 mm mouse-holes for the anode traces (L1, with ground on both sides and vias under the wall) and the HV feeds; the front wall has the comparator outputs and the DC control lines on L4 (they pass under the wall, not through it). Drawing of the can is owed by head mechanical (custom part `RR-HEAD-SHLD-A`).

From the EMI cover (requirement to head mechanical):

| Item | Requirement |
|---|---|
| Coverage | the whole board top, and — more important — the **rear chimney** with the SiPM carriers and the 35 mm pigtails (base x 151.4–152.9, z 11–28.5), which no board-level can reach. Closed on five sides with the spreader plate as the sixth. |
| Internal height | ≥ 6.3 mm above the PCB top everywhere (6.0 mm parts + 0.3); ≥ 8.3 mm over J1_LANDING (u 50–100, v 0–18) **if** the Micro-Fit right-angle headers exceed 6 mm (CCR-HE-02, open). Lane cans are 5.0 mm + clips. |
| Material | ≥ 0.3 mm aluminium, or plastic with a conductive coat of ≤ 0.1 Ω/□; seams and the cable entries are the weak points, not the wall. |
| Bond | to the spreader plate along the perimeter at ≤ 50 mm pitch (screws or fingers). The spreader is the board's `FRAME` net through the eight M2.5 standoffs; the single DC bond to board ground is R2801 at H1. No other electrical contact between cover/spreader and the board. |
| Openings | J1 and J2 cable entries only; cable shields terminate on the board `SHLD_J1` / `SHLD_J2` pads (1 MΩ ∥ 10 nF to `FRAME`). No slot longer than 20 mm elsewhere. |
| Light | the cover is not the light seal; the lid interlock switch (J2201) must open before any light path to a SiPM does. |
| Isolation from the chassis | state whether the spreader/cover can touch chassis metal when docked (decides R2801). |

## 5. Critical routes — hand-place and hand-route before autorouting, then lock

1. **Anode input, per channel:** U.FL centre → BAV99 → R_IN pair → trim capacitors (their ground vias directly at the pads) → 22 Ω → 100 nF → preamp pin 3: total < 12 mm, L1 only, 0.2 mm, no vias. C_INJ and the 74LVC2G53 within 4 mm of this node; the PULSER_STROBE trace arrives on L4 and comes up next to the switch.
2. **Preamp and fast-stage feedback** (R_F, R_G, C to ground/baseline): parts touching the op-amp pads; baseline capacitors (10 µF + 100 nF) with their own vias.
3. **Fast CR node and comparator inputs:** FAST → 100 Ω → BAT54S → comparator + inputs < 8 mm; threshold RC at the − pins.
4. **Comparator outputs → OR → latch clock:** < 25 mm, leave the can through the front wall, never parallel to an anode trace; the 100 Ω raw-LLD resistor sits at the comparator pin.
5. **HV:** HV_BUS trunk on L1 along v ≈ 39 with 1.5 mm clearance and a GND guard trace each side (stitched every 5 mm); drops to each channel filter enter the can from the front; per-channel filter nodes ringed by GND; the HV_RAW/boost nets stay in the BIAS cell. 100 V parts only; no HV under any connector shell or shield wall without 1.5 mm.
6. **Bias dividers** (2 × 1.2 MΩ, 2 × 4.99 MΩ): straight lines, guarded, nothing else within 1.5 mm; the FB node (R/C at U2202 pin 3) is the highest-impedance node on the board — keep it < 5 mm and away from the boost.
7. **Heater loop** (section 1) on L1 + L4 in parallel, ≥ 2.5 mm wide each, feed over return.
8. **Buck and boost cells** per the datasheet layouts.
9. **Isolation barrier.**
10. **TCXO → PF0** < 20 mm with the 33 Ω at the source; no route under the TCXO.
11. **MON_BUS** (one line visiting the four lane muxes) along v ≈ 40 on L4, GND each side; IMON_x and threshold/trim/baseline DC lines in the same corridor.

Autorouter constraints: keep-out for all signals on all layers under each lane can except the nets of that lane; no digital net inside v < 38; HV class rules; no vias in the sensitive class.

## 6. Coating and keep-outs

Conformal coat the top (and bottom) after bring-up values are final. Mask: U.FL, GH and Micro-Fit contacts, TC2030 pads, production test pads, mounting pads, shield clips (coat before fitting the cans, clips masked), lid-bypass jumper.

## 7. Bring-up sequence for the first powered board (stop conditions in bold)

Bench supply 12.0 V with a 0.3 A limit, no SiPMs, no heater, lid input open, no pigtails.

| Step | Action | Expect | **Stop if** |
|---|---|---|---|
| 0 | Unpowered: resistance J2001.1–.2, HV_BUS–GND, +5V_A–GND, +3V3–GND; J2001.7–.2; J2001.5–.6 with the three rail-switch connectors shorted pin 1–2; J2001.4 to GND | > 10 kΩ; > 1 MΩ; > 100 Ω; > 100 Ω; 4.70 kΩ ± 0.1 %; 1.00 kΩ ± 0.1 %; open (> 1 MΩ) | any short; presence or loop resistor wrong; heater return connected to GND |
| 1 | Reverse polarity −12 V on J2001.1/.2 at 10 mA limit | < 1 mA | current flows |
| 2 | +12 V, 0.3 A limit | 60–110 mA with the MCU blank; VIN_F 11.9 V; +5V6 5.63 ± 0.11 V; +5V_A 5.00 ± 0.10; +3V3 and +3V3_EVT 3.30 ± 0.07; VREF_ADC 3.000 ± 0.006; VBL 0.600 ± 0.004 (needs the DAC reference: 0.6 V appears only after power-up of U2302 — it is on by default) | any rail out; **input current > 0.25 A**; any part warm to the touch |
| 3 | Sweep the input 15 → 7 → 15 V | rails hold to < 8.0 V, drop out at 8.0 ± 0.3 V, return at 8.8 ± 0.3 V | UVLO outside the window |
| 4 | Scope +5V6, +5V_A, VBL (20 MHz limit and full bandwidth) | +5V6 ripple < 30 mV p-p at 1.1 MHz; +5V_A and VBL < 1 mV p-p | visible switching ripple on +5V_A |
| 5 | Program the MCU (SWD); HELLO over RS-485 through an isolated adapter powering J2501.3/.4 with 5 V | reply; BUS_5V current < 80 mA transmitting; isolation J2501.4 to GND > 10 MΩ | no link → check polarity DP/DN (ICD asks for a scope capture) |
| 6 | Latch self-test (LATCH_TEST), CLR lines, read-backs | all 20 latches set and clear; BUSY captures on TIM2/TIM5 | any latch stuck |
| 7 | DACs: write thresholds mid-scale, read MON and test pads; baseline scan of every comparator (threshold swept through the noise edge) | FAST baselines 0.60 V ± 30 mV; noise edge width ≈ 2 × 1.7 mV rms; raw LLD shows no chatter | baseline outside 0.45–0.80 V; oscillation |
| 8 | Pulser on each channel in turn, amplitude scan, rate sweep 10 Hz – 200 kHz | counts = strobes at low rate; live time measured; FAST amplitude ≈ linear in PULSER_AMPL; record mV at FAST per pC | missing/double counts; crosstalk counts on other channels at 5 p.e.-equivalent |
| 9 | **Bias, no SiPM, straps as built (37 V boost, 31.5 V OVP).** Lid input closed (or bypass jumper recorded). HV_SET = 0, HV_EN high | HV_RAW 37 ± 1 V; HV_BUS < 0.5 V; then HV_SET 0.4 V → HV_BUS 10.0 V; 1.0 V → 25.0 V ± 0.2; step response without overshoot > 0.3 V; BIAS_VMON = HV_BUS/25.22; BIAS_IMON ≈ 0.25–0.35 V (dividers + mirror bias) | **HV_BUS above set-point by > 1 V at any time**; oscillation; HV present with HV_EN low |
| 10 | Interlocks: open the lid input; pull +5V_A down through its test pad current-limited (or lift L2102); raise HV_SET until OVP | bias drops to < 1 V in < 2 s each time and stays off until HV_EN is toggled; OVP at 31.5 ± 0.7 V | bias recovers by itself |
| 11 | Output short: 10 kΩ, then 1 kΩ, then a short from a channel bias connector to ground | current limited at 2.0 ± 0.3 mA; firmware flags; no part hot | current > 3 mA |
| 12 | Trim: each TRIM DAC 0.1 → 2.5 V, read the trim node on the anode U.FL centre and IMON_CH with a 100 kΩ test load from bias to anode connector | node = code ± 3 mV; IMON_CH = (25 V − trim)/100 kΩ within 3 % | trim buffer oscillation (check the node with a scope) |
| 13 | Heater: 4.7 Ω 50 W dummy on J2601.1/.2 with the cut-out sense wired, HEAD_HTR_P from a second supply; toggle HTR_EN | edges ≈ 0.6 ms on / 3 ms off; HTR_SENSE 0.5 V/A; HTR_CUTOUT_OK follows the cut-out link in both states; dark-channel counts unchanged | edge faster than 0.2 ms; FET hot after 100 cycles at 1 Hz |
| 14 | Only now: fit the straps for the purchased SiPM family, connect one lane's SiPMs in the dark box, I–V sweep at 10 µA limit by firmware, then dark scans (budget §1 column 3) | breakdown within the family range; dark current within the datasheet range | current above the family maximum → light leak or wrong strap |

Then continue with the bench tests B1–B12 of `head_afe_budget.md` §11, and conformal coat last.
