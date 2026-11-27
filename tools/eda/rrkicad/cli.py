"""rrkicad command line: orchestrates the containerised KiCad / Freerouting steps.

Host side (needs only python3 + docker):
    python3 tools/eda/rrkicad.py build electronics/<board>/board.py [--no-route] [--reroute]
    python3 tools/eda/rrkicad.py check electronics/<board>/board.py
    python3 tools/eda/rrkicad.py sch   electronics/<board>/board.py     (schematic + ERC only)

The host process re-invokes itself inside the KiCad container (tools/docker/kicad.sh)
for the stages ``_gen`` / ``_post`` / ``_check`` and runs Freerouting in its own
container (tools/docker/freerouting.sh) in between.
"""
import argparse
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EDA = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(EDA))
KICAD_SH = os.path.join(REPO, "tools", "docker", "kicad.sh")
FREEROUTING_SH = os.path.join(REPO, "tools", "docker", "freerouting.sh")


def in_container():
    return bool(os.environ.get("RR_REPO")) and shutil.which("kicad-cli") is not None


def log(msg):
    print("[rrkicad] " + msg, flush=True)


class Paths:
    def __init__(self, board_py, name=None):
        self.board_py = os.path.abspath(board_py)
        self.dir = os.path.dirname(self.board_py)
        self.name = name

    def set_name(self, name):
        self.name = name
        return self

    def f(self, ext):
        return os.path.join(self.dir, self.name + ext)

    @property
    def pro(self): return self.f(".kicad_pro")
    @property
    def sch(self): return self.f(".kicad_sch")
    @property
    def pcb(self): return self.f(".kicad_pcb")
    @property
    def route_dir(self): return os.path.join(self.dir, "route")
    @property
    def dsn(self): return os.path.join(self.route_dir, self.name + ".dsn")
    @property
    def ses(self): return os.path.join(self.route_dir, self.name + ".ses")
    @property
    def unrouted(self): return os.path.join(self.route_dir, self.name + ".unrouted.kicad_pcb")
    @property
    def retry_dsn(self): return os.path.join(self.route_dir, self.name + ".retry.dsn")
    @property
    def retry_ses(self): return os.path.join(self.route_dir, self.name + ".retry.ses")
    @property
    def reports(self): return os.path.join(self.dir, "reports")
    @property
    def out(self): return os.path.join(self.dir, "out")
    @property
    def netlist(self): return os.path.join(self.out, self.name + ".net")
    @property
    def state(self): return os.path.join(self.reports, "build_state.json")


def load_board(board_py):
    from .model import Board, DefinitionError
    board_py = os.path.abspath(board_py)
    if not os.path.exists(board_py):
        raise SystemExit("board definition not found: %s" % board_py)
    sys.path.insert(0, os.path.dirname(board_py))
    try:
        ns = runpy.run_path(board_py, run_name="__rrkicad_board__")
    finally:
        sys.path.pop(0)
    b = ns.get("board")
    if not isinstance(b, Board):
        cands = [v for v in ns.values() if isinstance(v, Board)]
        if len(cands) != 1:
            raise DefinitionError("%s must define a module-level variable 'board' (a rrkicad.Board)" % board_py)
        b = cands[0]
    return b


def read_state(paths):
    try:
        with open(paths.state) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_state(paths, **kw):
    st = read_state(paths)
    st.update(kw)
    os.makedirs(paths.reports, exist_ok=True)
    with open(paths.state, "w") as f:
        json.dump(st, f, indent=2, sort_keys=True)
        f.write("\n")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


# --------------------------------------------------------------------- stages
def stage_gen(board_py, route=True, sch_only=False):
    """Schematic + project + netlist cross-check + unrouted PCB (+ DSN)."""
    from . import symlib, schematic, project, locallib, netlist
    from .model import resolve
    board = load_board(board_py)
    paths = Paths(board_py, board.name)
    for d in (paths.reports, paths.out, paths.route_dir):
        os.makedirs(d, exist_ok=True)
    libs = symlib.SymbolLibs()
    # local symbols must exist before parts are resolved
    w = schematic.SchematicWriter(board, libs, None)
    w.prepare_libs()
    nets = resolve(board, libs)
    board._nets = nets
    w.nets = nets
    log("definition: %d parts, %d nets, %d groups" % (len(board.parts), len(nets), len(board.groups)))
    # stale generated sheets from a previous definition
    _clean_generated(paths)
    pages = w.build(paths.dir)
    lib_text = w.local_library_text()
    sym_path = os.path.join(paths.dir, locallib.NICK + ".kicad_sym")
    if lib_text:
        with open(sym_path, "w", encoding="utf-8") as f:
            f.write(lib_text)
    elif os.path.exists(sym_path):
        os.remove(sym_path)
    fp_names = _write_local_footprints(board, paths)
    locallib.write_tables(paths.dir, bool(lib_text), bool(fp_names))
    sheets = [(w.root_uuid, "Root")] + [(p.uuid, p.name) for p in pages]
    pro = project.build_project(board, sheets)
    project.write_project(paths.pro, pro)
    log("schematic: %d sheet(s): %s" % (len(pages) + 1, ", ".join(p.name for p in pages)))
    netlist.export_netlist(paths.sch, paths.netlist)
    nl = netlist.Netlist(paths.netlist)
    netlist.crosscheck(board, nets, nl)
    log("netlist cross-check OK (%d components, %d nets incl. unconnected)" % (len(nl.components), len(nl.nets)))
    single = sorted(n for n, pins in nets.items() if len(pins) < 2)
    write_state(paths, routing=dict(board.routing, layers=board.layers))
    write_state(paths, name=board.name, generated_files=sorted([p.file for p in pages] + [board.name + ".kicad_sch"]),
                pwr_flags=w.flag_nets, single_pin_nets=single,
                counts={"parts": len(board.parts), "nets": len(nets), "sheets": len(pages) + 1})
    if sch_only:
        return 0
    from . import pcb
    info = pcb.build_pcb(board, paths, nl, pages, w.root_uuid)
    # the project file is re-written last: pcbnew must not have the final say
    project.write_project(paths.pro, pro)
    if info["fanout"]["plane_nets"]:
        log("plane fan-out: %d via(s) on %s, %d long fan-out(s) (maze-routed to the plane), %d pad(s) without" % (
            info["fanout"]["vias"], ", ".join(info["fanout"]["plane_nets"]), len(info["fanout"].get("long_fanout", [])),
            len(info["fanout"]["failed"])))
    esc = info.get("escape") or {}
    if esc.get("enabled"):
        log("escape: %d via(s), %d direct pre-route(s) on %s; %d pad(s) skipped %s" % (
            esc["vias"], esc["direct"], ", ".join(sorted(r for r, v in esc["parts"].items() if "pitch" in v)) or "no fine-pitch part",
            len(esc["skipped"]), json.dumps(esc["skipped_by_reason"], sort_keys=True)))
    if info.get("block_copies"):
        log("replicate: %d fixed track/via item(s) from route/blocks.json" % info["block_copies"])
    write_state(paths, plane_fanout=info["fanout"], escape=info.get("escape"), block_copies=info.get("block_copies", 0),
                finisher=None)
    write_state(paths, placement=info["placement"], autoplaced=info["autoplaced"],
                pcb_page_origin=info["origin"], board_bbox=info["bbox"], routed=False,
                gen_warnings=info["warnings"])
    with open(os.path.join(paths.reports, "placement.txt"), "w") as f:
        f.write("# %s placement (board frame: X right, Y up, mm; rot = KiCad orientation).\n"
                "# Lines marked [auto] were auto-arranged; copy the at=(...) value into board.py to freeze them.\n" % board.name)
        for ref, (x, y, rot, side) in info["placement"].items():
            f.write('%-8s at=(%s, %s, %s, "%s")%s\n' % (ref, x, y, ("%g" % rot), side,
                                                       "   [auto]" if ref in info["autoplaced"] else ""))
    if info["autoplaced"]:
        log("auto-arranged %d part(s): see reports/placement.txt" % len(info["autoplaced"]))
    if route and board.routing["enabled"]:
        shutil.copyfile(paths.pcb, paths.unrouted)
        new_dsn = paths.dsn + ".new"
        ignored = pcb.export_dsn(paths.pcb, new_dsn, board)
        write_state(paths, dsn_ignore_classes=ignored)
        same = os.path.exists(paths.dsn) and sha256(paths.dsn) == sha256(new_dsn)
        os.replace(new_dsn, paths.dsn)
        write_state(paths, dsn_sha256=sha256(paths.dsn), dsn_unchanged=bool(same))
        log("DSN exported (%s)" % ("unchanged" if same else "changed"))
    _cleanup(paths)
    return 0


def _clean_generated(paths):
    st = read_state(paths)
    for fn in st.get("generated_files", []):
        p = os.path.join(paths.dir, fn)
        if os.path.exists(p) and fn.endswith(".kicad_sch"):
            os.remove(p)


def _write_local_footprints(board, paths):
    from . import locallib
    pretty = os.path.join(paths.dir, locallib.NICK + ".pretty")
    files = {}
    for name, spec in board.local_footprints.items():
        files[name] = locallib.make_footprint(name, spec)
    for h in board.holes:
        name, text = locallib.make_hole_footprint(h["drill"], h["plated"], h["pad"])
        files[name] = text
        h["footprint"] = name
    if os.path.isdir(pretty):
        for fn in os.listdir(pretty):
            if fn.endswith(".kicad_mod") and fn[:-10] not in files:
                os.remove(os.path.join(pretty, fn))
    if files:
        os.makedirs(pretty, exist_ok=True)
        for name, text in files.items():
            with open(os.path.join(pretty, name + ".kicad_mod"), "w", encoding="utf-8") as f:
                f.write(text)
    elif os.path.isdir(pretty) and not os.listdir(pretty):
        os.rmdir(pretty)
    return sorted(files)


def _cleanup(paths):
    """Remove per-user/local KiCad files that must not be committed."""
    for ext in (".kicad_prl",):
        p = paths.f(ext)
        if os.path.exists(p):
            os.remove(p)
    for fn in os.listdir(paths.dir):
        if fn.endswith(".lck") or fn.startswith("~") or fn == "fp-info-cache" or fn.endswith("-backups"):
            p = os.path.join(paths.dir, fn)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)


def stage_post(board_py, routed=True, outputs=True, route_info=None, ses=None, quick=False):
    """SES import, zone fill, fab notes, checks, outputs, summary."""
    from . import pcb, checks, outputs as outmod, project
    board = load_board(board_py)
    paths = Paths(board_py, board.name)
    _resolve_for_post(board)
    st = read_state(paths)
    for ref, (x, y, rot, side) in (st.get("placement") or {}).items():   # incl. auto-arranged positions
        if ref in board._refs:
            pt = board.part(ref)
            pt.x, pt.y, pt.rot, pt.side = x, y, rot, side
    if routed and os.path.exists(paths.unrouted):
        shutil.copyfile(paths.unrouted, paths.pcb)     # always import into the pristine generated board
    write_state(paths, imported_ses_sha256=None)
    info = pcb.finish_pcb(board, paths, ses=(ses or paths.ses) if routed else None)
    if routed:
        write_state(paths, imported_ses_sha256=sha256(ses or paths.ses))
    # keep the project file exactly as generated (pcbnew may have re-saved it)
    with open(paths.pro) as f:
        pro = json.load(f)
    project.write_project(paths.pro, pro)
    write_state(paths, routed=bool(routed), route_stats=info, route_info=route_info or st.get("route_info"))
    if quick:          # intermediate import during routing: connectivity count only, no ERC/DRC/outputs
        log("import: %s connection(s) open" % info.get("unconnected_after_fill"))
        _cleanup(paths)
        return 0
    rc = stage_check(board_py, board=board, do_outputs=outputs)
    _cleanup(paths)
    return rc


def _resolve_for_post(board):
    from . import symlib, schematic
    from .model import resolve
    libs = symlib.SymbolLibs()
    w = schematic.SchematicWriter(board, libs, None)
    w.prepare_libs()
    board._nets = resolve(board, libs)
    return board._nets


def stage_check(board_py, board=None, do_outputs=False):
    from . import checks, outputs as outmod
    if board is None:
        board = load_board(board_py)
        _resolve_for_post(board)
    paths = Paths(board_py, board.name)
    os.makedirs(paths.reports, exist_ok=True)
    summary = checks.run_checks(board, paths, read_state(paths))
    if do_outputs:
        os.makedirs(paths.out, exist_ok=True)
        summary["outputs"] = outmod.generate(board, paths, summary)
    checks.write_summary(paths, summary)
    _cleanup(paths)
    checks.print_summary(summary)
    return 0 if summary["status"] == "pass" else 1


def stage_retrydsn(board_py):
    """DSN of the *routed* board: the autorouter continues from the current result."""
    from . import pcb
    board = load_board(board_py)
    paths = Paths(board_py, board.name)
    ignored = pcb.export_dsn(paths.pcb, paths.retry_dsn, board)
    write_state(paths, dsn_ignore_classes=ignored)
    return 0


def stage_finish(board_py):
    """Finisher: grid maze router for the connections still open after autorouting."""
    from . import pcb, finisher
    board = load_board(board_py)
    paths = Paths(board_py, board.name)
    _resolve_for_post(board)
    st = read_state(paths)
    for ref, (x, y, rot, side) in (st.get("placement") or {}).items():
        if ref in board._refs:
            pt = board.part(ref)
            pt.x, pt.y, pt.rot, pt.side = x, y, rot, side
    with open(os.path.join(paths.reports, "summary.json")) as f:
        summ = json.load(f)
    unrouted = (summ.get("drc") or {}).get("unrouted") or []
    paper, pw, ph, ox, oy = pcb.page_and_origin(board)
    res = finisher.run(board, paths, pcb.Frame(ox, oy), sha256(paths.ses), unrouted)
    log("finisher: %d of %d open connection(s) routed (%d item(s)) in %.1f s%s" % (
        len(res["routed"]), len(unrouted), res["items"], res["seconds"],
        "".join("\n    not routed: %s (%s)" % (f["net"], f["why"]) for f in res["failed"])))
    write_state(paths, finisher=res)
    return 0


def stage_sch(board_py):
    from . import checks
    stage_gen(board_py, route=False, sch_only=True)
    board = load_board(board_py)
    _resolve_for_post(board)
    paths = Paths(board_py, board.name)
    erc = checks.run_erc(board, paths)
    from . import outputs as outmod
    outmod.schematic_pdf(paths)
    _cleanup(paths)
    print(json.dumps({k: erc[k] for k in ("errors", "warnings", "waived")}, indent=1))
    return 0 if erc["errors"] == 0 else 1


# ----------------------------------------------------------------------- host
def _container(args):
    cmd = [KICAD_SH, "python3", os.path.join(EDA, "rrkicad.py")] + args
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in p.stdout:
        if "Debug: Adding duplicate image handler" in line:
            continue  # wxWidgets start-up noise from the pcbnew module
        sys.stdout.write(line)
        sys.stdout.flush()
    return p.wait()


def host_build(a):
    board_py = os.path.abspath(a.board)
    lock = os.path.join(os.path.dirname(board_py), ".rrkicad.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            pid = int(open(lock).read().strip() or 0)
            os.kill(pid, 0)
            alive = True
        except (ValueError, OSError):
            alive = False
        if alive:
            raise SystemExit("another rrkicad build of this board is running (pid %d); two builds of one board "
                             "at the same time corrupt each other" % pid)
        os.remove(lock)
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    try:
        return _host_build(a, board_py)
    finally:
        if os.path.exists(lock):
            os.remove(lock)


class _Router:
    """Host-side routing session: first run, continue runs, restarts, finisher - within an
    optional wall-clock budget.  route/<name>.ses only ever holds the best result so far (every
    Freerouting run writes a scratch SES that replaces it only when it leaves fewer connections
    open), and every step is appended to route/progress.log, so an interrupted multi-hour job
    still leaves its best state on disk."""

    def __init__(self, a, board_py, st):
        self.a, self.board_py = a, board_py
        self.bdir = os.path.dirname(board_py)
        self.state_p = os.path.join(self.bdir, "reports", "build_state.json")
        name = st["name"]
        rd = os.path.join(self.bdir, "route")
        self.dsn = os.path.join(rd, name + ".dsn")
        self.ses = os.path.join(rd, name + ".ses")
        self.rdsn = os.path.join(rd, name + ".retry.dsn")
        self.rses = os.path.join(rd, name + ".retry.ses")
        self.progress = os.path.join(rd, "progress.log")
        self.opts = st.get("routing", {})
        self.t0 = time.time()
        b = self.opts.get("budget")
        self.deadline = (self.t0 + float(b)) if b else None
        self.attempts = []

    def remaining(self):
        return None if self.deadline is None else self.deadline - time.time()

    def note(self, **kw):
        kw = dict(kw, t=time.strftime("%Y-%m-%d %H:%M:%S"), elapsed_s=round(time.time() - self.t0, 1))
        with open(self.progress, "a") as f:
            f.write(json.dumps(kw, sort_keys=True) + "\n")

    def run_timeout(self):
        """Job timeout for the next Freerouting run (None = the definition's / CLI timeout)."""
        t = self.a.timeout or self.opts.get("timeout")
        if self.deadline is not None:
            chunk = float(self.opts.get("chunk") or 900)
            t = min(float(t) if t else chunk, chunk, max(60.0, self.remaining() - 120.0))
        return int(t) if t else None

    def post(self, info, quick):
        args = ["_post", self.board_py, "--route-info", json.dumps(info)] + (["--quick"] if quick else [])
        rc = _container(args)
        st = json.load(open(self.state_p))
        ok = st.get("imported_ses_sha256") == sha256(self.ses)
        return rc, (st.get("route_stats") or {}).get("unconnected_after_fill") if ok else None

    def fr(self, dsn, seed):
        more = ["--router.autorouter.item_order_seed=%d" % seed] if seed else []
        return run_freerouting(self.board_py, dsn, self.rses, self.a, more, timeout=self.run_timeout())

    def adopt(self, info, kind, seed, best_open, best_info):
        """Scratch SES -> candidate; keep it if better.  Returns (open, info, kept)."""
        if os.path.exists(self.ses):
            shutil.copyfile(self.ses, self.ses + ".prev")
        shutil.copyfile(self.rses, self.ses)
        rc, o = self.post(info, quick=True)
        self.attempts.append({"run": len(self.attempts) + 1, "kind": kind, "seed": seed,
                              "seconds": info["seconds"], "unconnected": o})
        kept = o is not None and (best_open is None or o < best_open)
        self.note(event="run", kind=kind, seed=seed, seconds=info["seconds"], unconnected=o, kept=kept,
                  best=o if kept else best_open)
        if kept:
            if os.path.exists(self.ses + ".prev"):
                os.remove(self.ses + ".prev")
            log("routing: %s run -> %s open (kept)" % (kind, o))
            return o, info, True
        if os.path.exists(self.ses + ".prev"):
            shutil.copyfile(self.ses + ".prev", self.ses)
            os.remove(self.ses + ".prev")
            self.post(best_info, quick=True)          # board back to the best result
        log("routing: %s run -> %s open (not better, discarded)" % (kind, o))
        return best_open, best_info, False

    def out_of_time(self):
        r = self.remaining()
        return r is not None and r < 180

    def route(self, dsn_sha):
        """Returns (route_info, open) of the best result; route/<name>.ses holds it."""
        retries = int(self.opts.get("retries", 0))
        restarts = int(self.opts.get("restarts", 1))
        stall_max = int(self.opts.get("stall", 2))
        self.note(event="start", budget_s=self.opts.get("budget"), retries=retries, restarts=restarts)
        info = self.fr(self.dsn, 0)
        if info is None:
            return None, None
        info["dsn_sha256"] = dsn_sha
        best_open, best_info, _ = self.adopt(info, "first", 0, None, None)
        for r in range(0, restarts + 1):
            if r > 0:
                if not best_open or self.out_of_time():
                    break
                log("routing: %d connection(s) open -> fresh restart %d with another item-order seed" % (best_open, r))
                info = self.fr(self.dsn, 1000 * r)
                if info is None:
                    break
                info["dsn_sha256"] = dsn_sha
                info["restart"] = r
                best_open, best_info, _ = self.adopt(info, "restart", 1000 * r, best_open, best_info)
            # continue runs from the current best routed board (with a budget: until it stalls)
            n, stall = 0, 0
            while best_open and not self.out_of_time():
                if self.deadline is None and n >= retries:
                    break
                if self.deadline is not None and stall >= stall_max:
                    break
                n += 1
                log("routing: %d connection(s) open -> continue run %d" % (best_open, len(self.attempts) + 1))
                if _container(["_retrydsn", self.board_py]) != 0:
                    break
                info = self.fr(self.rdsn, 1000 * r + n)
                if info is None:
                    break
                merged = dict(best_info, seconds=round(best_info.get("seconds", 0) + info["seconds"], 1),
                              log_tail=info.get("log_tail"))
                best_open, best_info, kept = self.adopt(merged, "continue", 1000 * r + n, best_open, best_info)
                stall = 0 if kept else stall + 1
        for f in (self.rdsn, self.rses):
            if os.path.exists(f):
                os.remove(f)
        best_info = dict(best_info, attempts=self.attempts)
        self.note(event="autorouter done", unconnected=best_open)
        return best_info, best_open


def _host_build(a, board_py):
    t0 = time.time()
    rc = _container(["_gen", board_py] + (["--no-route"] if a.no_route else []))
    if rc != 0:
        return rc
    route_info = None
    routed = False
    bdir = os.path.dirname(board_py)
    state_p = os.path.join(bdir, "reports", "build_state.json")
    if not a.no_route:
        with open(state_p) as f:
            st = json.load(f)
        name = st["name"]
        if "dsn_sha256" in st:
            ses = os.path.join(bdir, "route", name + ".ses")
            meta_p = os.path.join(bdir, "route", "route_meta.json")
            meta = {}
            if os.path.exists(meta_p):
                with open(meta_p) as f:
                    meta = json.load(f)
            reuse = (not a.reroute and os.path.exists(ses) and meta.get("dsn_sha256") == st["dsn_sha256"]
                     and not a.passes and not a.threads and not a.timeout and not a.budget)
            if a.budget:
                st["routing"]["budget"] = a.budget
                with open(state_p, "w") as f:
                    json.dump(st, f, indent=2, sort_keys=True)
                    f.write("\n")
            if reuse:
                log("routing: DSN unchanged -> re-using %s" % os.path.relpath(ses, REPO))
                route_info = dict(meta, reused=True)
            else:
                router = _Router(a, board_py, st)
                route_info, _ = router.route(st["dsn_sha256"])
                if route_info is None:
                    return 3
                with open(meta_p, "w") as f:
                    json.dump(route_info, f, indent=2, sort_keys=True)
                    f.write("\n")
                route_info = dict(route_info, reused=False)
            routed = True
    args = ["_post", board_py]
    if not routed:
        args.append("--no-route")
    if route_info:
        args += ["--route-info", json.dumps(route_info)]
    rc = _container(args)
    # finisher: built-in maze router for what the autorouter left open (checked by DRC like the rest)
    if routed and route_info:
        st = json.load(open(state_p))
        open_now = (st.get("route_stats") or {}).get("unconnected_after_fill", 0)
        ses_p = os.path.join(bdir, "route", st["name"] + ".ses")
        imported = os.path.exists(ses_p) and st.get("imported_ses_sha256") == sha256(ses_p)
        if not imported:
            log("routing: the SES import did not complete (see above) - finisher not started")
        elif open_now > 0 and st.get("routing", {}).get("finisher", True):
            log("routing: %d connection(s) still open -> finisher" % open_now)
            if _container(["_finish", board_py]) == 0:
                rc = _container(["_post", board_py, "--route-info", json.dumps(route_info)])
    log("total build time %.1f s" % (time.time() - t0))
    return rc


def run_freerouting(board_py, dsn, ses, a, more_args=(), timeout=None):
    """Run the autorouter container; returns stats dict or None on failure."""
    # routing options come from the board definition via reports/build_state.json
    # (the definition itself is only ever evaluated inside the KiCad container).
    with open(os.path.join(os.path.dirname(board_py), "reports", "build_state.json")) as f:
        st = json.load(f)
    opts = st["routing"]
    passes = a.passes or opts["passes"]
    threads = a.threads or opts["threads"] or (os.cpu_count() or 2)
    extra = list(opts.get("extra_args") or []) + list(more_args)
    if st.get("dsn_ignore_classes"):
        # nets with copper zones: connected by zone fill + plane fan-out, never routed as tracks
        extra.append("--router.autorouter.ignore_net_classes=%s" % ",".join(st["dsn_ignore_classes"]))
    if not opts.get("optimizer", True):
        extra.append("--router.optimizer.enabled=false")
    fanout = bool(opts.get("fanout"))
    extra.append("--router.fanout.enabled=%s" % ("true" if fanout else "false"))
    timeout = timeout or a.timeout or opts["timeout"]
    if timeout:
        # ask Freerouting to stop by itself (it then still writes the SES); hard kill 3 min later
        extra.append("--router.job_timeout=%02d:%02d:%02d" % (timeout // 3600, (timeout % 3600) // 60, timeout % 60))
    logf = os.path.join(os.path.dirname(dsn), "freerouting.log")
    if os.path.exists(ses):
        os.remove(ses)
    cmd = [FREEROUTING_SH, dsn, ses, str(passes), str(threads)] + extra
    log("routing: freerouting passes<=%d threads=%d%s" % (passes, threads, (" timeout=%ds" % timeout) if timeout else ""))
    t0 = time.time()
    timed_out = False
    with open(logf, "w") as lf:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            keep = []
            deadline = (t0 + timeout + 180) if timeout else None
            for line in p.stdout:
                if "\tat " in line or line.startswith("\tat ") or "ERROR Could not determine local host" in line \
                        or "UnknownHostException" in line or line.strip().startswith("... "):
                    continue
                # strip wall-clock timestamps so the log is diff-friendly
                keep.append(line)
                lf.write(line)
                lf.flush()
                if "Auto-routing pass #" in line and "was completed" in line:
                    sys.stdout.write("    " + line.split("INFO", 1)[-1].strip()[:150] + "\n")
                    sys.stdout.flush()
                if deadline and time.time() > deadline:
                    timed_out = True
                    p.terminate()
                    break
            p.wait()
        finally:
            if p.poll() is None:
                p.kill()
    dt = time.time() - t0
    info = {"seconds": round(dt, 1), "passes_limit": passes, "threads": threads, "timed_out": timed_out,
            "freerouting": _fr_version(keep)}
    for line in keep:
        if "Auto-routing stage completed" in line or "Optimization stage completed" in line or "finished with state" in line:
            info.setdefault("log_tail", []).append(line.split("INFO", 1)[-1].strip()[:400])
    if not os.path.exists(ses):
        log("routing FAILED: no SES written (see %s)" % logf)
        return None
    log("routing finished in %.1f s" % dt)
    return info


def _fr_version(lines):
    for line in lines:
        if "Freerouting v" in line:
            return line.split("Freerouting", 1)[1].strip()
    return "?"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rrkicad", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "check", "sch", "_gen", "_post", "_check", "_sch", "_retrydsn", "_finish"):
        sp = sub.add_parser(name)
        sp.add_argument("board")
        sp.add_argument("--no-route", action="store_true", help="skip autorouting (PCB stays unrouted)")
        sp.add_argument("--reroute", action="store_true", help="ignore the cached route/<name>.ses")
        sp.add_argument("--passes", type=int, help="override Freerouting max passes")
        sp.add_argument("--threads", type=int, help="override Freerouting thread count")
        sp.add_argument("--timeout", type=int, help="kill Freerouting after N seconds")
        sp.add_argument("--budget", type=int, help="wall-clock budget (s) for all autorouter runs; "
                        "continue runs repeat until it is used up or they stop improving")
        sp.add_argument("--quick", action="store_true", help=argparse.SUPPRESS)
        sp.add_argument("--route-info", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    from .model import DefinitionError
    try:
        if a.cmd.startswith("_"):
            if not in_container():
                raise SystemExit("internal stage commands must run inside the KiCad container")
            if a.cmd == "_gen":
                return stage_gen(a.board, route=not a.no_route)
            if a.cmd == "_post":
                return stage_post(a.board, routed=not a.no_route,
                                  route_info=json.loads(a.route_info) if a.route_info else None, quick=a.quick)
            if a.cmd == "_retrydsn":
                return stage_retrydsn(a.board)
            if a.cmd == "_finish":
                return stage_finish(a.board)
            if a.cmd == "_check":
                return stage_check(a.board)
            if a.cmd == "_sch":
                return stage_sch(a.board)
        if in_container():
            raise SystemExit("run build/check/sch from the host (they start the containers themselves)")
        if a.cmd == "build":
            return host_build(a)
        if a.cmd == "check":
            return _container(["_check", os.path.abspath(a.board)])
        if a.cmd == "sch":
            return _container(["_sch", os.path.abspath(a.board)])
    except DefinitionError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    return 0
