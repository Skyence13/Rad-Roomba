"""Survey pipeline: one ordered journal -> interpreter -> trajectory -> processor.

The live system appends every input to the archive journal and feeds it here;
`replay()` feeds the archived journal through the same code, so every product
is rebuilt bit-for-bit (RQ-026, VT-020, VT-026).

Journal entry kinds consumed: T, R, C (head stream), P (pose sample),
J (processing op: mark | advance | blocked | evaluate | epoch | resume).

No ROS imports.
"""
from __future__ import annotations

from .head_link import HeadLinkConfig, HeadStreamInterpreter
from .processing import SurveyConfig, SurveyProcessor
from .profiles import Calibration
from .trajectory import TrajectoryBuffer


class SurveyPipeline:
    def __init__(self, survey_cfg: SurveyConfig, calibration: Calibration, profile: dict,
                 link_cfg: HeadLinkConfig | None = None, method: dict | None = None, interp=None,
                 archive=None, traj_kwargs: dict | None = None):
        self.interp = interp or HeadStreamInterpreter(link_cfg or HeadLinkConfig())
        self.traj = TrajectoryBuffer(**(traj_kwargs or {}))
        self.proc = SurveyProcessor(survey_cfg, calibration, profile, self.traj, method)
        self.archive = archive
        self.fits, self.sessions, self.closes, self.link_notes = [], [], [], []
        self.epoch_log = []
        self.archive_error = None

    # ------------------------------------------------------------ live inputs
    def archive_entry(self, entry, sync=False):
        """Sink for the head master (raw stream is durable before interpretation)."""
        if self.archive is not None:
            kind, payload = entry[1], entry[2]
            sync = sync or (kind == "C" and payload.get("c") in ("SESSION_OPEN", "SESSION_CLOSE"))
            self.archive.append(entry, sync=sync)

    def on_head_events(self, events):
        for ev in events:
            kind = ev["ev"]
            if kind == "session_open":
                self.proc.open_session(ev["manifest"])
                self.sessions.append(ev["manifest"])
            elif kind == "gate":
                self.proc.add_gate(ev["gate"])
            elif kind == "gap":
                self.proc.add_gap(ev)
            elif kind == "fit":
                self.fits.append(ev["fit"] | {"attachment": ev["attachment"]})
            elif kind == "session_close":
                self.closes.append(ev)
            elif kind in ("fault", "bad_line", "duplicate", "unassigned_frame", "stale_reply"):
                self.link_notes.append(ev)

    def record(self, t_us, kind, payload):
        """Archive and apply a non-head journal entry (P or J)."""
        entry = (t_us, kind, payload)
        self.archive_entry(entry)
        return self.apply(entry)

    # --------------------------------------------------------------- dispatch
    def apply(self, entry):
        t, kind, payload = entry
        if kind == "P":
            self.traj.add(**payload)
        elif kind == "J":
            op = payload["op"]
            if op == "mark":
                self.proc.add_mark(payload["t_us"], **{k: v for k, v in payload.items() if k not in ("op", "t_us")})
            elif op == "advance":
                self.proc.advance(payload["w"])
            elif op == "blocked":
                self.proc.add_blocked_region(payload["rect"], payload.get("reason", "BLOCKED"), payload.get("t_us"))
            elif op == "evaluate":
                return self.proc.evaluate()
            elif op in ("epoch", "resume"):
                self.traj.new_epoch(payload.get("t_us"), payload.get("reason", op.upper()))
                self.epoch_log.append(payload)
        return None

    def feed(self, entry):
        """Replay path: any journal entry."""
        if entry[1] in ("T", "R", "C"):
            self.on_head_events(self.interp.feed(entry))
            return None
        return self.apply(entry)


def build_from_run(run_dir, calibration=None, profile=None, archive=None):
    """Rebuild a pipeline from an archived run (replay, or resume after a reboot)."""
    from .archive import read_journal
    import json
    from pathlib import Path
    run = json.loads((Path(run_dir) / "run.json").read_text())
    calibration = calibration or Calibration(run["calibration_record"])
    profile = profile or run["profile"]
    cfg = SurveyConfig(**run["survey_config"])
    link = HeadLinkConfig(**run.get("link_config", {}))
    pipe = SurveyPipeline(cfg, calibration, profile, link, run.get("method"), archive=None,
                          traj_kwargs=run.get("trajectory_config"))
    n = 0
    for _epoch, entry in read_journal(run_dir):
        pipe.feed(entry)
        n += 1
    pipe.archive = archive
    pipe.replayed_entries = n
    return pipe, run


def replay(run_dir, out_dir, calibration=None, profile=None):
    """Offline replay: rebuild every product under the archived (or a given) profile version."""
    from .export import export_survey
    pipe, run = build_from_run(run_dir, calibration, profile)
    if profile is not None:
        run = dict(run, profile=profile)
    return export_survey(pipe, run, out_dir, run_dir=None)
