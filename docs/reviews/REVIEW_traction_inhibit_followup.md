# Follow-up review: traction inhibit after chassis stage 3 and two firmware rounds

Reviewer: the same independent engineer as `REVIEW_traction_inhibit.md`. Date: 2026-11-27. Status: **in progress**, written step by step; sections not yet filled are marked TODO.

Tags as before: **[N]** netlist (circuit.py + overrides.py stage 3), **[P]** placement data, **[F]** firmware source, **[E]** emulator run with my own fault models (scratchpad only), **[C]** my calculation, **[I]** inferred or recalled.

## 1. Method so far

- `python3 electronics/chassis_main/overrides.py`: exit 0, stage-1 self-check on the overridden netlist PASSED (log in scratchpad `review_chain/ovr_s3.log`).
- Netlist queried with `review_chain/q.py` for every new net of S3-C1, S3-C2, S3-M1, S3-M2, S3-M6.

## 2. Stage-3 latch topology as built [N]

- Set request: J_BTN 1 = REARM_SET_SRC (V5_AUX via R_SSRC 1 k) → set contact → J_BTN 2 = REARM_SET_RAW (R_SPD 47 k down, D_SET 15 V ESD) → R_SSER 10 k → REARM_SET (C_SF 10 n, D_SCL to V5_AUX) → C_SC 1 µF → SET_G (R_SG 100 k, D_SGN) → Q_SETA gate. Aux contact: BTN_3V3 → J_BTN 4 = REARM_BTN_RAW → R_AG 10 k → REARM_AUX_G (R_AGP 100 k, C_AG 10 n) → Q_SETB gate. Q_SETA and Q_SETB in series sink the U_SET LED (V5_AUX → R_USA 470 → U_SET).
- U_SET output joins SET_CAP to K1_SET → R96 → K1_COIL_P. The coil node no longer leaves the board.
- Q_HSET (BSS84, gate U_SET_K, source V5_AUX) feeds the U_HOLD LED through R_HS 470 only while the U_SET LED conducts.
- K1 pole B (NO2) now feeds K1_RUN → U_HOLD (photo-MOS) → RUN_HD → D_RUN (B160) → RUN_12V. U_HOLD self-holds from RUN_HD through R_HA 1.5 k.
- RUN_HD (before D_RUN) feeds U8 EN (R133), U9's own tap (R_U9T1 → HW_LATCH_G) and the U_LS LED (R_LSA 1.5 k). RUN_12V (after D_RUN) feeds the K2/K3 coils and HW_LATCH_RB (R117 22 k / R118 15 k → PD2).
- K2/K3 coil return: RELAY_RTN → U_LS → COIL_RTN → E-stop pole B → GND. K1 coil still returns to COIL_RTN.
- C_SET charges from CHAIN_END through D_RSET + R_SET 22 k. It is discharged through R_SDIS 1 k by Q_SDIS whenever Q_SDISB is off, i.e. whenever CHAIN_END_RB (the 100 k/56 k tap, also IOX_B P17) is below Q_SDISB's threshold.
- K1 NC1 (pin 3) is read back: K1_SEAL_A is biased from 3V3 through R_K1B 47 k → LATCH_NC_RB (IOX_D P0). K1_RUN is tapped → LATCH_RUN_RB (IOX_D P1).

TODO: closure table, new failure modes, §6.1 completeness, timing, decision table, host claim.
