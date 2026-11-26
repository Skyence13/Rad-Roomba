"""Stopping distance versus rail lead / overtravel at the contract speeds (calculated)."""
from __future__ import annotations

import math

from .. import params as P
from . import f, inputs_table, table

RAIL_LEAD = 11.0      # mm, leading rail front face ahead of the forward film edge (cad/README.md, Rev D)
RAIL_STROKE_REV_D = 0.4   # mm, gap between the leading rail and the frame in the Rev D model = no designed stroke yet


def stop(v, t=P.STOP_T_DELAY, a=P.STOP_A_MIN, m=P.STOP_MARGIN_M):
    return v * t + v * v / (2 * a) + m


def vmax_for(x_mm, t=P.STOP_T_DELAY, a=P.STOP_A_MIN):
    x = x_mm / 1000
    return a * (-t + math.sqrt(t * t + 2 * x / a))


def run():
    md, key = [], {}
    md.append("## 8. Stopping distance versus rail lead and overtravel\n")
    md.append(inputs_table([("Stop model", "d = v t + v^2/(2a) + m", "", "contract motion.stop_model"), ("t_delay / a_min / margin", f"{P.STOP_T_DELAY} s / {P.STOP_A_MIN} m/s2 / {P.STOP_MARGIN_M * 1000:.0f} mm", "", "contract design inputs (to be replaced by measurements)"),
                            ("Rail lead ahead of the film edge", RAIL_LEAD, "mm", "cad/README.md Rev D"), ("Rail stroke in the Rev D model", RAIL_STROKE_REV_D, "mm", "Rev D solids (rail to frame gap) -- no stroke designed yet"),
                            ("Outer head corner radius", f(math.hypot(P.HEAD_ENV_E["x"][1], 175.0), 0), "mm", "calculated from the proposed head envelope (contract comment: 318)")]))
    speeds = [("survey", P.V_SURVEY), ("max forward", P.V_MAX_FWD), ("max reverse", P.V_MAX_REV), ("outer head corner at max yaw", P.YAW_MAX * math.hypot(P.HEAD_ENV_E["x"][1], 175.0) / 1000)]
    rows = []
    for n, v in speeds:
        d0 = (v * P.STOP_T_DELAY + v * v / (2 * P.STOP_A_MIN)) * 1000
        rows.append((n, f(v, 3), f(d0), f(stop(v) * 1000), f(max(0.0, d0 - RAIL_LEAD)), "yes" if d0 <= RAIL_LEAD else "NO"))
    md.append("\n" + table(["Case", "Speed (m/s)", "Travel after contact, no margin (mm)", "With 20 mm margin (mm)", "Rail stroke needed beyond the 11 mm lead (mm)", "Stops inside the lead alone?"], rows))
    rows = [(x, f(vmax_for(x), 3), f(vmax_for(x, 0.05, 1.0), 3)) for x in (3.0, 5.0, RAIL_LEAD, 20.0, 30.0)]
    md.append("\n" + table(["Available travel after rail contact (mm)", "Max speed with contract inputs (m/s)", "Max speed with t = 0.05 s, a = 1.0 m/s2 (m/s)"], rows))
    d_s = (P.V_SURVEY * P.STOP_T_DELAY + P.V_SURVEY ** 2 / (2 * P.STOP_A_MIN)) * 1000
    md.append(f"\n**Finding (calculated).** At the {P.V_SURVEY} m/s survey speed the base travels {d_s:.1f} mm after the rail switch opens (47.5 mm with the contract margin). The Rev D geometry offers 11 mm of lead and essentially no rail stroke, "
              f"so a rigid obstacle taller than the film height reaches the frame/film before the robot stops. Options for the lead: (a) give the leading rail >= {d_s - RAIL_LEAD + 3:.0f} mm of sprung stroke ahead of the frame (head mechanical, costs head length or "
              f"coverage at walls), (b) prove t_delay <= 0.05 s and a >= 1.0 m/s2 (then 0.10 m/s needs 10 mm), or (c) limit speed to {vmax_for(RAIL_LEAD):.3f} m/s near obstacles. Reverse at {P.V_MAX_REV} m/s needs {(P.V_MAX_REV * P.STOP_T_DELAY + P.V_MAX_REV ** 2 / (2 * P.STOP_A_MIN)) * 1000:.1f} mm of body-bumper stroke.")
    key.update(travel_survey_mm=d_s, travel_max_mm=(P.V_MAX_FWD * P.STOP_T_DELAY + P.V_MAX_FWD ** 2 / (2 * P.STOP_A_MIN)) * 1000, vmax_in_lead=vmax_for(RAIL_LEAD))
    # look-ahead geometry
    md.append("\n## 9. Look-ahead and cliff sight lines against the raised Rev E head\n")
    s = P.TOF_SENSORS["tof_look_fl"]
    half = P.TOF_FOV_FULL_DEG / 2
    dep = P.LOOKAHEAD_FWD_DEPRESSION
    xs, zs = s["xyz"][0], s["xyz"][2]
    edge_x = P.HEAD_COVER_X[1]
    XLEAD = P.HEAD_ENV_E["x"][1]
    def z_at(x, ang):
        return zs - (x - xs) * math.tan(math.radians(ang))
    def floor_x(ang):
        return xs + zs / math.tan(math.radians(ang))
    rows = [("centre ray", dep, f(z_at(edge_x, dep) - P.HEAD_TOP_Z), f(floor_x(dep), 0), f(floor_x(dep) - XLEAD, 0)),
            ("lower cone edge", dep + half, f(z_at(edge_x, dep + half) - P.HEAD_TOP_Z), f(floor_x(dep + half), 0), f(floor_x(dep + half) - XLEAD, 0)),
            ("upper cone edge", dep - half, f(z_at(edge_x, dep - half) - P.HEAD_TOP_Z), f(floor_x(dep - half), 0), f(floor_x(dep - half) - XLEAD, 0))]
    md.append(f"Rev D sight line for reference: sensor at (90, +-23, 92), 17 deg down -> passes the Rev D cover edge (x 260.6, z 39.0) with {92 - (260.6 - 90) * math.tan(math.radians(17)) - 39.0:.2f} mm, "
              f"and would hit a z = {P.HEAD_TOP_Z} head by {P.HEAD_TOP_Z - (92 - (260.6 - 90) * math.tan(math.radians(17))):.1f} mm. The forward look-ahead pair therefore sits on the grip cheeks (x {xs:.1f}, y +-91, z {zs:.0f}).\n")
    md.append(table(["Ray (vertical plane)", "Depression (deg)", f"Clearance over the head front edge x {edge_x}, z {P.HEAD_TOP_Z} (mm)", "Floor intersection x (mm)", "Ahead of the leading rail (mm)"], rows))
    lead = floor_x(dep + half) - XLEAD
    md.append(f"\nThe nearest floor the forward look-ahead can see is {lead:.0f} mm ahead of the leading rail; stopping distance at {P.V_MAX_FWD} m/s is {stop(P.V_MAX_FWD) * 1000:.0f} mm, so a drop-off is seen "
              f"{'before' if lead > stop(P.V_MAX_FWD) * 1000 else 'AFTER'} the stopping point with {lead - stop(P.V_MAX_FWD) * 1000:.0f} mm to spare (centre ray range {zs / math.sin(math.radians(dep)):.0f} mm, grazing incidence {dep:.0f} deg: return strength on dark or wet floors is a test item). "
              "The full 3D check of all 11 sensors (centre ray + 8 cone-edge rays against every solid, and the LiDAR scan plane) is run by layout.py; see out/layout_report.md section 8. "
              "The two front cliff sensors now sit on the chassis front beam at (46, +-109.5), 13 mm inboard of the tyres and 6 mm ahead of the tyre front, so each wheel has its own drop-off sensor.")
    key.update(lookahead_edge_clearance=z_at(edge_x, dep + half) - P.HEAD_TOP_Z, lookahead_lead_mm=lead)
    return "\n".join(md), key
