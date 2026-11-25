#!/usr/bin/env python3
"""Reproducible synthetic mapping demonstration. Uses Python's standard library."""
import argparse
import bisect
import csv
from dataclasses import dataclass, field
import math
from pathlib import Path
import random

# All geometry is expressed in metres. Calibration and rates are invented.
CENTRES = (0.13125, 0.04375, -0.04375, -0.13125)
ACTIVE_LENGTH, ACTIVE_WIDTH = 0.10, 0.08
HEAD_X = 0.204  # Concept fore-aft offset from axle; replace with measured as-built transform.
GRID = 0.025
XMIN, YMIN, NX, NY = 0, -0.25, 44, 20
HOT_PATCH = (0.48, 0.57, -0.030, 0.030)  # x min/max, y min/max; straddles first-pass seam.
BIN_SECONDS = 0.50
CHANNELS = ("alpha", "beta")
CAL = {
    "alpha": {"K": (21, 22, 20, 21.5), "k": .010, "b": .12},
    "beta": {"K": (29, 31, 28.5, 30), "k": .38, "b": .25},
}

def rect_area(poly):
    if len(poly) < 3:
        return 0.0
    return abs(sum(a[0]*b[1] - a[1]*b[0] for a,b in zip(poly, poly[1:] + poly[:1]))) / 2

def overlap(poly, bounds):
    """Clip a convex footprint to a cell with four half-plane boundaries."""
    xmin, xmax, ymin, ymax = bounds
    for axis, limit, sign in ((0,xmin,1), (0,xmax,-1), (1,ymin,1), (1,ymax,-1)):
        if not poly:
            return 0.0
        clipped = []
        prev = poly[-1]
        for here in poly:
            inside_prev = (prev[axis]-limit)*sign >= 0
            inside_here = (here[axis]-limit)*sign >= 0
            if inside_prev != inside_here:
                f = (limit-prev[axis])/(here[axis]-prev[axis])
                clipped.append((prev[0] + f*(here[0]-prev[0]), prev[1] + f*(here[1]-prev[1])))
            if inside_here:
                clipped.append(here)
            prev = here
        poly = clipped
    return rect_area(poly)

def footprint(pose, segment):
    x, y, yaw = pose
    c, s = math.cos(yaw), math.sin(yaw)
    corners = []
    for front, left in ((1,1),(-1,1),(-1,-1),(1,-1)):
        u = HEAD_X + front*ACTIVE_LENGTH/2
        v = CENTRES[segment] + left*ACTIVE_WIDTH/2
        corners.append((x + c*u - s*v, y + s*u + c*v))
    return corners

def pose_at(poses, timestamps, t):
    i = bisect.bisect_right(timestamps, t) - 1
    if i < 0 or t > timestamps[-1]:
        return None
    if t == timestamps[i]:
        return poses[i][1:]
    a, b = poses[i], poses[i+1]
    if b[0]-a[0] > 0.35:
        return None
    f = (t-a[0])/(b[0]-a[0])
    yaw_step = math.atan2(math.sin(b[3]-a[3]), math.cos(b[3]-a[3]))
    return (a[1]+f*(b[1]-a[1]), a[2]+f*(b[2]-a[2]), a[3]+f*yaw_step)

def sampled_footprints(poses, timestamps, start, dt, segment):
    samples = []
    # Reject intervals outside pose support including boundaries.
    if pose_at(poses, timestamps, start) is None or pose_at(poses, timestamps, start+dt) is None:
        return []
    for frac in (1/6, 1/2, 5/6):
        p = pose_at(poses, timestamps, start+frac*dt)
        if p is None:
            return []
        samples.append(footprint(p, segment))
    return samples

def poisson(rng, mean):
    # Exact inverse waiting-time algorithm; synthetic means are deliberately small.
    product, n = 1.0, 0
    threshold = math.exp(-mean)
    while product > threshold:
        product *= rng.random()
        n += 1
    return max(0, n-1)

def cell_fractions(polys):
    """Time-average the fraction of each cell underneath this segment in the bin."""
    weights = {}
    for poly in polys:
        x, y = zip(*poly)
        ix0, ix1 = math.floor((min(x)-XMIN)/GRID), math.floor((max(x)-XMIN)/GRID)
        iy0, iy1 = math.floor((min(y)-YMIN)/GRID), math.floor((max(y)-YMIN)/GRID)
        for ix in range(max(0,ix0), min(NX,ix1+1)):
            for iy in range(max(0,iy0), min(NY,iy1+1)):
                x0, y0 = XMIN+ix*GRID, YMIN+iy*GRID
                frac = overlap(poly,(x0,x0+GRID,y0,y0+GRID)) / (GRID**2*len(polys))
                if frac > 1e-9:
                    weights[ix,iy] = weights.get((ix,iy),0) + frac
    return weights

def write_csv(path, names, rows):
    with path.open("w", newline="", encoding="utf-8") as output:
        w = csv.writer(output)
        w.writerow(names)
        w.writerows(rows)

def simulate(outdir):
    rng = random.Random(10283)
    poses, bins = [], []
    for run in range(2):
        start = 20*run
        ys = (0.0,.04375)[run]  # offset by half a lane pitch to fill seam in central area
        yaw = (0.0,math.pi)[run]
        for j in range(49):
            t = j*.25
            # Forward-driven passes, opposite headings. Base-to-head arm rotates on return.
            head_x = (.08 + .075*t) if run == 0 else (.98 - .075*t)
            poses.append((start+t, head_x-math.cos(yaw)*HEAD_X, ys, yaw))
        times = [p[0] for p in poses]
        for i in range(24):
            t = start+i*BIN_SECONDS
            for seg in range(4):
                polyset = sampled_footprints(poses,times,t,BIN_SECONDS,seg)
                patch_weight = sum(overlap(p,HOT_PATCH) for p in polyset)/(len(polyset)*ACTIVE_LENGTH*ACTIVE_WIDTH)
                x_mid = sum(p[0] for p in polyset[1])/4
                ref_rate = 18 + 16*x_mid  # spatially varying synthetic photon field
                live, ref_live = .49,.485
                quality = "ok"
                if run == 0 and i in (4,5,6) and seg == 0:
                    quality = "head_fault"
                if run == 1 and i in (10,11,12) and seg == 3:
                    quality = "pose_uncertain"
                counts = []
                for ch, amplitude in (("alpha",1.0),("beta",2.4)):
                    c = CAL[ch]
                    raw_rate = c["b"]+c["k"]*ref_rate+c["K"][seg]*amplitude*patch_weight
                    counts.append(poisson(rng,live*raw_rate))
                bins.append((run,i,seg,t,BIN_SECONDS,live,ref_live,*counts,poisson(rng,ref_live*ref_rate),quality))
    write_csv(outdir/"poses.csv",["t_s","x_m","y_m","yaw_rad"],poses)
    write_csv(outdir/"bins.csv",["pass_id","seq","segment","start_s","period_s","floor_live_s","ref_live_s",
                                 "alpha_counts","beta_counts","reference_counts","quality"],bins)

@dataclass
class Cell:
    exposure: float = 0.0
    sums: dict = field(default_factory=lambda:{c:0.0 for c in CHANNELS})
    variances: dict = field(default_factory=lambda:{c:0.0 for c in CHANNELS})

def map_data(outdir):
    with (outdir/"poses.csv").open(encoding="utf-8") as fp:
        poses = [tuple(float(r[key]) for key in ("t_s","x_m","y_m","yaw_rad")) for r in csv.DictReader(fp)]
    times = [p[0] for p in poses]
    cells, seen, excluded = {}, set(), {}
    with (outdir/"bins.csv").open(encoding="utf-8") as fp:
        for r in csv.DictReader(fp):
            seg = int(r["segment"])
            key = (r["pass_id"],r["seq"],seg)
            if key in seen:
                raise ValueError(f"duplicate acquisition {key}")
            seen.add(key)
            why = r["quality"]
            dt, live, ref_live = (float(r[k]) for k in ("period_s","floor_live_s","ref_live_s"))
            if not (0 < live <= dt and 0 < ref_live <= dt):
                why = "invalid_live_time"
            polys = sampled_footprints(poses,times,float(r["start_s"]),dt,seg)
            if not polys:
                why = "missing_pose"
            if why != "ok":
                excluded[why] = excluded.get(why,0) + 1
                continue
            estimates = {}
            ref = int(r["reference_counts"])
            for ch in CHANNELS:
                gross, c = int(r[ch+"_counts"]), CAL[ch]
                K, k = c["K"][seg],c["k"]
                rate = gross/live - k*ref/ref_live - c["b"]
                variance = gross/live**2 + k**2*ref/ref_live**2
                estimates[ch] = (rate/K,variance/K**2)
            for cell_id, frac in cell_fractions(polys).items():
                cell = cells.setdefault(cell_id,Cell())
                weight = live*frac
                cell.exposure += weight
                for ch, (value, variance) in estimates.items():
                    cell.sums[ch] += weight*value
                    cell.variances[ch] += weight**2*variance
    return cells, excluded

def write_map(outdir, cells):
    cols = ["x_center_m","y_center_m","projection_status","weighted_live_s","alpha_Bq_cm2","alpha_stat_sd",
            "beta_Bq_cm2","beta_stat_sd"]
    rows = []
    for iy in range(NY):
        for ix in range(NX):
            cell = cells.get((ix,iy))
            vals = []
            for ch in CHANNELS:
                vals.extend(("", "") if cell is None else (round(cell.sums[ch]/cell.exposure,5),
                            round(math.sqrt(cell.variances[ch])/cell.exposure,5)))
            rows.append((round(XMIN+(ix+.5)*GRID,4),round(YMIN+(iy+.5)*GRID,4),
                        "no_valid_exposure" if cell is None else "has_valid_exposure",
                        round(cell.exposure,5) if cell else 0,*vals))
    write_csv(outdir/"cells.csv",cols,rows)
    w = 16
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 768 438">',
             '<rect width="768" height="438" fill="white"/>',
             '<g font-family="sans-serif" fill="#162c3b"><text x="28" y="28" font-size="20">Synthetic beta-window projection</text>',
             '<text x="28" y="49" font-size="13">Trailer x increases right, y increases upward. Cell size 25 mm.</text>']
    for iy in range(NY):
        for ix in range(NX):
            c = cells.get((ix,iy))
            if not c:
                col = "#a4aab1"
            else:
                value = c.sums["beta"]/c.exposure
                # Clamp only in the display. CSV retains negative estimates.
                q = min(max(value/1.5,0),1)
                col = "rgb(%d,%d,%d)" % (214+round(22*q),244-round(165*q),245-round(216*q))
            lines.append(f'<rect x="{28+ix*w}" y="{61+(NY-iy-1)*w}" width="{w}" height="{w}" fill="{col}"/>')
    xmin,xmax,ymin,ymax=HOT_PATCH
    lines.append(f'<rect x="{28+(xmin-XMIN)/GRID*w:.2f}" y="{61+(YMIN+NY*GRID-ymax)/GRID*w:.2f}" '
                 f'width="{(xmax-xmin)/GRID*w:.2f}" height="{(ymax-ymin)/GRID*w:.2f}" '
                 'fill="none" stroke="#23384c" stroke-width="2" stroke-dasharray="4 3"/>')
    lines += ['<text x="28" y="402" font-size="13">Grey = no valid exposure. Blue to orange = ≤0 to ≥1.5 Bq/cm² (synthetic calibration).</text>',
              '<text x="28" y="424" font-size="13">Dashed line = injected patch. Values describe the segment footprint. Offline demonstration only.</text></g></svg>']
    (outdir/"beta_map.svg").write_text("\n".join(lines),encoding="utf-8")

def self_test():
    import tempfile
    assert abs(rect_area(footprint((0,0,math.pi/3),0))-ACTIVE_LENGTH*ACTIVE_WIDTH) < 1e-12
    assert footprint((0,0,0),0)[0][1] > footprint((0,0,0),3)[0][1]
    assert footprint((0,0,math.pi),0)[0][1] < footprint((0,0,math.pi),3)[0][1]
    a = footprint((.3,.0,0),0)
    assert abs(sum(cell_fractions([a]).values())*GRID**2-rect_area(a)) < 1e-12
    assert pose_at([(0,0,0,0),(1,1,0,0)],[0,1],.5) is None
    with tempfile.TemporaryDirectory() as path:
        p = Path(path)
        simulate(p)
        cells, omissions = map_data(p)
        assert omissions == {"head_fault":3,"pose_uncertain":3}
        assert (0,0) not in cells
        assert max(c.sums["beta"]/c.exposure for c in cells.values()) > 0.6
        write_map(p,cells)
        with (p/"cells.csv").open() as fp:
            rs = list(csv.DictReader(fp))
        assert len(rs) == NX*NY
        assert all(r["beta_Bq_cm2"]=="" for r in rs if r["projection_status"]=="no_valid_exposure")
        # A duplicate frame must fail closed rather than contributing counts twice.
        with (p/"bins.csv").open() as fp:
            first = fp.readlines()[1]
        with (p/"bins.csv").open("a") as fp:
            fp.write(first)
        try:
            map_data(p)
        except ValueError as err:
            assert "duplicate" in str(err)
        else:
            raise AssertionError("duplicate acquisition accepted")
    print("PASS: footprint geometry, orientation, time gaps, quality exclusions, duplicate detection and raster outputs")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,default=Path("demo_output"))
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    if args.self_test:
        self_test()
        return
    args.out.mkdir(parents=True,exist_ok=True)
    simulate(args.out)
    cells,excluded=map_data(args.out)
    write_map(args.out,cells)
    print(f"Valid exposure in {len(cells)} of {NX*NY} display cells. Excluded segment bins: {excluded}.")
    print(f"Review {args.out/'beta_map.svg'} and {args.out/'cells.csv'}.")

if __name__ == "__main__":
    main()
