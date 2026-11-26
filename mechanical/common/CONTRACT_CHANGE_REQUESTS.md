# Contract change requests from the mechanical lead

Target: `interface/system/contract.yaml` 0.4.0-draft1 (owner: integration lead). Nothing below has been applied; `mechanical/common/params.py`
carries the proposed values next to the loaded contract values. All numbers are design values (calculated / tool-checked).

| ID | Key | Contract now | Requested | Why | Who is affected |
|---|---|---|---|---|---|
| CCR-01 | `frames.wheel.track_mm` | 220.0 | 270.0 | Body proposal D-1 widens the flank at the wheel station; wheels stay on the flanks as in Rev D. | chassis firmware caps, odometry calibration default, ROS footprint |
| CCR-02 | `frames.caster` | swivel -100, wheel -116 | swivel -195, wheel -204 (forward travel; 9 mm trail, 21.5 mm swivel radius) | Longer wheelbase halves the pitch term of the gap budget (1.76 -> 1.00 mm per mm at the caster) and the Rev D position is inside the battery bay. | footprint, gap model |
| CCR-03 | (new) `frames.body_envelope_rev_e_mm` | absent (Rev D body 267 x 225 x 85 mm shell) | x [-271.9, 102.4], y [-146.4, 146.4], z [32.9, 143.0]; grip bar top z 175; LiDAR top z 216 | The Rev D body cannot contain the selected hardware (out/layout_report.md section 3). Lead decision D-1. | swept-volume/route-hold model, transport tray, renders |
| CCR-04 | `boards.RR-HEAD-ACQ.position` | "PCB underside nominally z = 33.0" | "PCB underside z = 34.5; origin (156.0, 163.0, 34.5)" | 2.0 mm structural spreader + 1.5 mm pad/heater + 2.5 mm bottom-side gap above the reference guides (z 28.5). Outline, 8 x M2.5, 6.0 / 2.0 mm limits confirmed. | head electronics, head mechanical |
| CCR-05 | `frames.head_envelope_rev_e_mm.z` | [5.0, 50.0] (ceiling) | keep the ceiling; record the design value z max = 45.0 | Stack-up in board_envelopes.yaml. 5 mm of ceiling stays in reserve. | head descriptor envelope, look-ahead sight lines |
| CCR-06 | `boards.RR-CHS-MAIN` | outline only | add origin (-67.0, 80.0, 83.0), 6 x M3 pattern, connector edge allocation from board_envelopes.yaml | Confirmed 160 x 100, 18 / 3 mm, valid only with D-1. | chassis electronics, harness |
| CCR-07 | `power.battery.capacity_ah_trial` | 8.0 | note: nearest verified catalogue pack is 9.0 Ah (Power-Sonic PSL-SC-1290, 151 x 65 x 94/99 mm, 1.0 kg) | No 8 Ah monobloc with a datasheet was found; the bay is sized for the 151 x 65 x 99 format. The 12 Ah alternative does not fit (needs +34 mm bay height). | power budget, BOM W28/E01 |
| CCR-08 | `motion.stop_model` / rail design | t = 0.15 s, a = 0.40 m/s2 | add a requirement for rail stroke or tighter stop inputs | 27.5 mm travel after rail contact at 0.10 m/s vs 11 mm lead and no designed stroke (mech_calcs.md section 8). | head mechanical, chassis firmware, VT-003/004 |
| CCR-09 | `planning/prototype_bom.csv` W24 | 5 switches | 7 x D2HW-C201M | HEAD_DOCK and CHG_COVER chain elements also need a sealed switch. | registers owner |
| CCR-10 | `power.average_budget_w.heaters_combined` | 15.0 | about 21 W at -20 C (head +10 C set-point 16 W + bay 6 W), 30 W at -25 C | Lumped thermal model, mech_calcs.md section 7; or lower the head set-point to +5 C (12 + 6 = 18 W). | power budget owner |

Notes for other owners (no contract key):
- The CM5 carrier candidate has one RJ45, used by the LiDAR; a wired service port needs a USB-Ethernet adapter or another carrier (chassis electronics).
- Forward look-ahead ToF pair moves from the nose to the grip cheeks (frames.yaml); the Rev D nose position is blocked by the z = 45 head.
