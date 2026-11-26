# RR-HEAD-ACQ rev A — what an independent reviewer should try to break

Each item: the attack, then my own answer and its evidence class. "Open" means I could not close it at stage 1.
Files: `electronics/head_acq/design/circuit.py`, `head_afe_budget.md`, `head_afe_calc.py`.

## A. Arithmetic and models

| # | Try to break | Own answer |
|---|---|---|
| A1 | Re-run `python3 electronics/analysis/head_afe_calc.py` and `python3 electronics/head_acq/design/circuit.py`; compare with the quoted tables. Do the circuit values in the two files agree (R_IN 10 Ω, gains 21/21/5, CR 220 pF/100 Ω, 1 kΩ/1 nF)? | `head_afe_calc.py` table T12 imports `circuit.py` and compares 13 values of channel F0 (R_IN, gains, shaping R/C, C_INJ); it reports none different. The clamp series resistors and the monitor path are not in the pulse model. |
| A2 | The pulse model uses single-pole op-amps and ideal parts. Is the fast pulse really 80 ns FWHM with a decompensated OPA838 at gain 21 (two 14 MHz poles)? | Calculated only; no SPICE run. The TI model predicts peaking at low gains, not at 21. Bench step 8 measures it. |
| A3 | Dark-count threshold: the resolving-time factor 0.50 was fitted at n = 3…5 and 25 °C for one device, then extrapolated four decades in rate to 1 s⁻¹ and to other devices. Afterpulsing and delayed crosstalk are not modelled. | Correct; the table is good to about ±1 p.e. at best. The DCR temperature law (halving per 8 °C) is assumed. The real number comes from the dark threshold scan. |
| A4 | S14160 DCR is derived from dark current, not a datasheet count rate. | Yes, labelled calculated; surface leakage would make it pessimistic. |
| A5 | Photo-electron yields (beta 4–120, alpha 150–15 000) have no measurement behind them. | Correct, labelled assumed with the basis shown. Everything downstream scales with them. |
| A6 | Bias loop: crossover 6 Hz / 70° assumes a follower transconductance of ~1 mS at 30–100 µA and ignores the mirror's output impedance. | Calculated, not simulated. Bring-up step 9 (step response, stop if overshoot > 1 V). The boost strap bounds any overshoot. |
| A7 | Heater edge times assume a 3 V Miller plateau; SOA of SUD50P04-08 for 3 ms at 15 V × 3 A not checked. | Open; datasheet not opened. Bring-up step 13 has a temperature stop. |
| A8 | Power: MCU current 45/70 mA assumed; buck efficiency assumed. | Total 1.2/2.1 W has a factor-of-two margin to the 5 W target. |

## B. Circuit faults to look for

| # | Try to break | Own answer |
|---|---|---|
| B1 | Pin-outs. Which were read from a datasheet and which recalled? | Read: OPA838, TLV3501/3502, DAC60508, TMUX1108, SN74LVC2G53, ISO1430, TPS26600, TPS61391, LMR51606, TLV767. Standard-family (74x74/32/00/138/238, dual op-amp SOIC-8): from memory, low risk. **Recalled, verify=True**: TLV7021, TPS7A20 (DBV), REF3030, INA180, TMP117, TCA9534, 24AA025E64, ISO7710, THVD1420, BZX84/BAV199/BAT54S/BAV99 pin order, BSS123/BSS138/MMBTA42/MMBT3904 (G/B-S/E-D/C order), ACM4520, TCXO pads, OPA836 (assumed equal to OPA838). |
| B2 | TPS61391: CAP-pin capacitor connection, MON1 compliance at 2 V, behaviour of the mirror with a regulator instead of an APD behind it, ISHORT at start-up into 9 µF. | Datasheet says MON pins go to 2.5 V; CAP connection and start-up into a capacitive load are **unverified**. Fallback if the mirror misbehaves: bypass it (0 Ω from HV_RAWF to HV_MIR is not provided — rework), rely on IMON_CH. Open. |
| B3 | TPS26600: RTN is separate from GND in my netlist (EF_RTN). Is the PowerPAD allowed to float with respect to the plane? SHDN and MODE left open. | Per the datasheet pin table (RTN reference, pad to RTN). SHDN/MODE defaults are **unverified**; pads provided. |
| B4 | TLV3501 SHDN tied to ground = enabled? | Yes per datasheet (disabled only within 0.9 V of V+). |
| B5 | Comparator inputs see up to 4.9 V from 5 V op-amps. | 330 Ω + BAT54S to +3V3_EVT: ≤ 4 mA into the rail during overload, clamp drop ≈ 0.3 V against a common-mode range of V+ + 0.2 V (datasheet) — still 0.1 V beyond the specified range for the duration of a saturating pulse, inside the usual absolute limit (*UNVERIFIED*). The 330 Ω adds a ~5 ns pole that the pulse model does not include. |
| B6 | ADC pins: MON_ADC can see 4.9 V; IMON_CH buffer runs from 5 V. | MON_ADC has 1 kΩ + BAT54S to +3V3A; IMON_CH has 1 kΩ only (≤ 2 mA injection). Acceptable; note for firmware not to select faults blindly. |
| B7 | Wired-OR of the two TLV7021 and the lid FET on HV_INH_N; latch clear is asynchronous — can a glitch on HV_EN set PERMIT? | PERMIT needs a rising edge while the inhibit bus is high; a glitch during a fault cannot set it. A reset glitch on HV_EN with no fault sets PERMIT but HV_ON still needs HV_EN high. |
| B8 | With HV_SET stuck at full scale (DAC fault) what limits the bias? | Boost strap (max HV_RAW − ~5 V) and the OVP comparator through an independent divider and reference. A shorted follower gives HV_RAW − 2.5 V, then OVP trips. For a J-series strap: 34.6 V transiently = 10 V overvoltage at ≤ 2 mA until the comparator acts (µs) and the bleeder discharges (0.4 s). |
| B9 | Trim node: the buffer cannot go below ~10 mV; what if a trim code is below I × 4.99 kΩ? | Loop saturates, anode rises, overvoltage drops (safe direction); firmware keeps trim ≥ 0.1 V + margin. |
| B10 | ALPHA latch set without BUSY; BUSY cleared while LLD is high; ULD without LLD. | First: CCR-HE-09. Second: firmware waits for LLD low (raw line provided). Third: impossible for a positive pulse (ULD > LLD) unless the thresholds are mis-set. |
| B11 | Unused logic inputs and flip-flops. | Tied (see `lane()`: spare FF D/CLK to ground, PRE/CLR high; NAND spare inputs grounded). The self-check verifies that every pin of every listed package is defined. |
| B12 | Heater return isolation. | `HEAD_HTR_N` touches only J2001.4, J2601.2, TVS and bypass capacitor (check `circuit.NETS['HEAD_HTR_N']`). Bring-up step 0 measures it. |
| B13 | Isolation barrier: is anything other than the isolators connected to both sides? | `BUS_GND`/`BUS_5VF` nets contain only J2501, the bus side of U2501, TVS, capacitors and the DNP sync parts. J2501's mounting pads are on BUS_GND. |
| B14 | SiPM hot-plug or short with bias on. | 2 mA limit, 1.1 kΩ, clamp, R_IN pulse (≈ 0.55 A for ~100 µs from 1.1 µF at 60 V) — resistor pulse rating not checked. Procedure is bias off before touching pigtails. |
| B15 | U.FL at 62.5 V DC and in a damp box. | 60 V AC rated; creepage inside the connector is small. Coat around, not inside. Risk accepted for rev A; MMCX is the fallback. |

## C. System-level

| # | Try to break | Own answer |
|---|---|---|
| C1 | Does the board fit? | 7600 mm² of courtyards on 30 000 mm² (25 %); lane block fits ±18 mm × (5.5–62 mm) by estimate, not by placement. The J1 connector height is open (CCR-HE-02). |
| C2 | 1008 fitted parts on a 4-layer board with a scripted autorouter. | The identical lane block should be placed and routed once and replicated; critical routes are listed for hand-routing (layout guidance §5). Risk for stage 2. |
| C3 | Is the single-ground rule kept? | J1 pin 2 is the only DC ground entry; frame bond R2801 is conditional (CCR-HE-03); J2 is isolated. |
| C4 | Motor noise in the plastic prototype. | Budget §3.4: coax + lane can + cover are needed; an open pigtail loop fails by calculation. Only test B11 can close it. |
| C5 | Cold: parts below −25 °C? Condensation? | Board sits at ~+10 °C; JST GH (−25 °C), LEDs, TCXO grade unverified; two SiPM families stop at −20 °C; no humidity sensor. |
| C6 | Can a dead front end produce authoritative zeros? | Not by hardware alone — firmware must use BIAS_VMON/IMON/rails and the pulser/self-test. The per-channel monitor (PE15) was added for this. |
| C7 | Availability / lifecycle of the parts. | **Not checked** (distributor sites blocked). All TI datasheets were retrieved from ti.com on 2026-11-25/26, which shows the parts are documented, not that they are in stock. |

## D. Not done at stage 1

No SPICE simulation; no placement; no thermal calculation of the board; no EMC calculation beyond the estimates shown; no check of the eFuse inrush slew; no orderable-suffix verification for 24 part numbers (listed by the self-check).
