# Contract change requests from the mechanical lead

Owner of `interface/system/contract.yaml`: integration lead. All numbers are design values (calculated / tool-checked).

**Status against contract 0.4.0-draft4:** CCR-01, 02, 03 adopted (DEC-039); CCR-04, 05, 06, 07 applied; CCR-08, 09, 10 noted.
**Open requests: CCR-11 to CCR-14 below** (12 Ah pack growth, DEC-040, and head mount option C from the DEC-041 trade study,
`out/head_mount_trade_study.md`). `params.py` already carries the requested values next to the loaded contract values; `frames.yaml`,
`board_envelopes.yaml`, the layout and all calculations are built with them.

## Open requests (2026-11-26)

| ID | Key | Contract now (0.4.0-draft4) | Requested (exact values) | Why | Who is affected |
|---|---|---|---|---|---|
| CCR-11a | `frames.head_mount.xyz_mm` | [138.5, 0.0, 32.0] | **[65.7, 0.0, 32.0]** (rpy unchanged [0, 0, 0]) | Mount option C: twin-shoe receiver on the lane seams, overhang shortened by 72.8 mm. Datum = x-stop plane of the receiver, z kept so the head-internal offsets are unchanged. | TF tree, head descriptor origin, route-hold footprint |
| CCR-11b | `frames.optics.row_center_x_mm` | 204.0 | **131.2** | same; the row stays 65.5 mm ahead of `head_mount` (aperture in the head_mount frame is still (+65.5, y, -22.0)) | mapping offset, coverage planner, `expose_spot_reverse_offset_m` check |
| CCR-11c | `frames.head_envelope_rev_e_mm` | x [138.8, 265.0], y [-175, 175], z [5.0, 50.0] | **x [66.0, 192.2], y [-175.0, 175.0], z [5.0, 50.0]**; `head_design_top_z_mm` 45.0 unchanged; add `head_shoes_mm: {x: [4.0, 66.0], y_center: [87.5, -87.5], width: 16.0, z: [16.0, 30.0]}` | rigid -72.8 mm shift of the head; the two bearing shoes extend behind the envelope into the receiver channels | head descriptor envelope, swept volume |
| CCR-11d | `boards.RR-HEAD-ACQ.position` | origin (156.0, 163.0, 34.5) | **origin (83.2, 163.0, 34.5)**; board coordinates, holes, zones, limits unchanged | follows the head | head electronics (none in board coordinates), harness length J1/J2 (pigtails about 150 mm) |
| CCR-11e | `frames.head_mount_review` | "until it closes, the values below stand" | close with: receiver = two channels under the chassis front beam, envelope x 2..64, 24 wide about y = +-87.5, z 12..33; bearing lands at x 8 and 62; one draw latch under the nose tip; HEAD_DOCK switch at (-3.0, 87.5, 23.0) | DEC-041 | chassis electronics (dock switch lead), body engineers |
| CCR-12 | `frames.body_rev_e` | shell z [32.9, 143.0]; overall [537, 350, 216] | **shell_envelope_mm unchanged in x and y; z [32.9, 143.0] plus battery hump x [-233.0, -70.5], \|y\| <= 60.5, top z 150.0 and sensor brow to z 166.0; overall_mm [464, 350, 230]** (length now tail -271.9 to leading rail 192.2; height = LiDAR top) ; add `nose: lower hull ends at x = 62 below z = 50` | 12 Ah pack lying 99 mm tall needs a cassette top at z 144 (DEC-040): local dorsal hump, LiDAR base raised 136 -> 150; nose chin removed for the shortened head | renders, transport tray, route-hold model |
| CCR-13 | `motion.max_yaw_rate_radps` comment | "keeps the outer head corner (r = 0.318 m) at <= 0.095 m/s" | outer head corner r = **0.260 m** (0.078 m/s at 0.30 rad/s); the tail corner r = **0.278 m** now sets the swept circle (0.083 m/s) | option C | chassis firmware caps, protective field shapes |
| CCR-14 | sensors (frames.yaml only, no contract key) | front cliff pair on the nose chine; look-ahead 14 deg | front cliff pair at (46.0, +-109.5, 31.0) on the chassis front beam beside the tyres; forward look-ahead depression 18 deg (centre ray reaches the floor at x 497, range 524 mm); rear-centre proximity at (-236.0, 0.0, 158.0) | receiver channels occupy the old cliff positions; head edge is closer; hatch is taller | chassis firmware field distances, robot software |

## Earlier requests (text as submitted against 0.4.0-draft1)

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
