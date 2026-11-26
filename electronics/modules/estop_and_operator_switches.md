# E-stop, operator controls and chain switches (W24, W25, R05, R06, E10)

| Function | Part | Contacts used | Board connector | Tag |
|---|---|---|---|---|
| Emergency stop | Schneider Harmony **XB5AS8444**, 40 mm mushroom, trigger action, turn to release, 2 NC, 22 mm | NC 1 = chain high side (pole A), NC 2 = coil return (pole B) | J_ESTOP 1–2, 3–4 | [M] selected by mechanical; −40…+70 °C [M partial] |
| Selector OFF / SERVICE / RUN | Harmony XB5 3-position stay-put head with **one NC block on the OFF side (ZBE-102) and one NO block on the RUN side (ZBE-101)** | NC (closed in SERVICE and RUN) = EN contact; NO (closed in RUN) = MODE_RUN chain element | J_MODE 1–2, 3–4 | [U] the catalogue assembly XB5AD33 has 2 NO: one block must be exchanged; cam behaviour to be confirmed on the part |
| HANDS-ON inhibit | Harmony XB5 illuminated push-push (maintained) button, 1 NC, with 12 V LED block | NC = chain element; lamp fed from the chain (lit = contact open, upstream live, latch dropped) | J_HANDS 1–2, 3–4 | [U] exact reference (ZB5AH… head + ZBE-102 + 12 V light block) |
| REARM / Start | Harmony XB5 guarded flush momentary button, **2 NO**, 12 V LED block | NO 1 = set path (capacitor-coupled); NO 2 = REARM_BTN to the MCU | J_BTN 1–2, 3–4, lamp 6–7 | [U] reference |
| PAUSE / Stop | Harmony XB5 projecting momentary button, 1 NO, 12 V LED block | NO = PAUSE_BTN (program control, may be cleared remotely per owner decision) | J_BTN 3–5, lamp 6–8 | [U] reference |
| Body bumper L, R; head dock; inlet cover | Omron **D2HW-C201M** sealed SPDT, wired on NC | series chain elements | J_BUMP_L, J_BUMP_R, J_DOCK, J_COVER | [M]; −40…+85 °C [U] |
| External stop provision (E10) | any positive-opening 2 NC device | in series with both E-stop poles at J_ESTOP | — | site decision |
| Pre-motion sounder (optional, recommended) | 22 mm panel buzzer, 12 V self-driven, ≥ 85 dB(A) at 30 cm, −25 °C | switched low side | RR-PANEL J2 | [U] no part verified; the on-board piezo is estimated at about 60 dB at 1 m |

Electrical load on the contacts: 12 V, 80 mA when latched, about 0.1 mA before (readback dividers only): use gold-flashed or low-level contact blocks where offered [A]. Lamp blocks: 12 V, ≤ 20 mA each, from the 0.35 A V12_AUX PTC (REARM, PAUSE) or from the chain's 0.2 A PTC (HANDS-ON).

All contact devices are single-channel, non-monitored parts in a non-certified chain. Positive opening applies to the E-stop only.

**Prototype → production.** Same parts. For production, order the selector and HANDS-ON as complete catalogue assemblies once the contact arrangement is confirmed, and add engraved legends (symbols as well as text).
