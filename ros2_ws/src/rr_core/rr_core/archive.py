"""Immutable raw archive: append-only journal in atomically sealed segment files.

Layout of a run directory
    run.json                      run manifest (written once, atomically)
    journal/e<epoch>-<n>.seg      sealed segments (never modified after sealing)
    journal/e<epoch>-<n>.part     the segment being written (sealed on rotate/close)
    journal/index.ndjson          one line per sealed segment: name, entries, bytes, sha256
    checkpoint.json               latest mission checkpoint (atomic replace)

Entry framing (binary safe; raw wire bytes are preserved exactly):
    b"E <t_us> <kind> <nbytes>\n" + payload + b"\n"
kind: T/R raw head wire lines, C head control JSON, P pose JSON, J processing/journal
JSON, X auxiliary JSON (chassis events, audit...) that replay ignores.

Every process start opens a NEW epoch; segments of earlier epochs are sealed
as found (flag `recovered`) and never appended to (RQ-038, VT-026).
Free-space loss is explicit: `append` raises `ArchiveError` and the caller must
hold acquisition credit.

No ROS imports.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


class ArchiveError(IOError):
    pass


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, data: bytes):
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def encode_entry(entry) -> bytes:
    t, kind, payload = entry
    if not isinstance(payload, (bytes, bytearray)):
        payload = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return b"E %d %s %d\n" % (int(t), kind.encode(), len(payload)) + bytes(payload) + b"\n"


def decode_entries(data: bytes):
    pos = 0
    while pos < len(data):
        end = data.find(b"\n", pos)
        if end < 0:
            return                       # torn header at the end of a recovered segment
        head = data[pos:end].split(b" ")
        if len(head) != 4 or head[0] != b"E":
            raise ArchiveError("corrupt journal header")
        t, kind, n = int(head[1]), head[2].decode(), int(head[3])
        payload = data[end + 1:end + 1 + n]
        if len(payload) < n or data[end + 1 + n:end + 2 + n] != b"\n":
            return                       # torn final entry (power loss): ignored, stays on disk
        pos = end + 2 + n
        yield (t, kind, payload if kind in ("T", "R") else json.loads(payload))


class Archive:
    def __init__(self, run_dir, segment_bytes: int = 4 << 20, min_free_bytes: int = 16 << 20):
        self.dir = Path(run_dir)
        self.jdir = self.dir / "journal"
        self.jdir.mkdir(parents=True, exist_ok=True)
        self.segment_bytes, self.min_free_bytes = segment_bytes, min_free_bytes
        self.index_path = self.jdir / "index.ndjson"
        for part in sorted(self.jdir.glob("*.part")):       # previous process died: seal as found
            self._seal(part, recovered=True)
        epochs = [int(p.name[1:].split("-")[0]) for p in self.jdir.glob("e*.seg")]
        self.epoch = (max(epochs) + 1) if epochs else 0
        self._n = 0
        self._f = None
        self._count = 0
        self.entries_written = 0

    # ------------------------------------------------------------------ write
    def write_run_manifest(self, manifest: dict):
        path = self.dir / "run.json"
        if path.exists():
            raise ArchiveError("run manifest already exists (immutable)")
        atomic_write(path, json.dumps(manifest, indent=1, sort_keys=True).encode())

    def run_manifest(self) -> dict:
        return json.loads((self.dir / "run.json").read_text())

    def _open(self):
        self._path = self.jdir / f"e{self.epoch:03d}-{self._n:06d}.part"
        self._f = open(self._path, "ab")
        self._count = 0

    def append(self, entry, sync: bool = False):
        if self._f is None:
            self._open()
        data = encode_entry(entry)
        try:
            if self._f.tell() == 0 or sync:
                st = os.statvfs(self.jdir)
                if st.f_bavail * st.f_frsize < self.min_free_bytes:
                    raise ArchiveError("free space below the archive reserve")
            self._f.write(data)
            if sync:
                self._f.flush()
                os.fsync(self._f.fileno())
        except OSError as err:
            raise ArchiveError(str(err)) from err
        self._count += 1
        self.entries_written += 1
        if self._f.tell() >= self.segment_bytes:
            self.rotate()

    def flush(self):
        if self._f is not None:
            self._f.flush()
            os.fsync(self._f.fileno())

    def rotate(self):
        if self._f is None:
            return
        self.flush()
        self._f.close()
        self._f = None
        self._seal(self._path, recovered=False)
        self._n += 1

    def _seal(self, part: Path, recovered: bool):
        seg = part.with_suffix(".seg")
        os.replace(part, seg)
        data = seg.read_bytes()
        line = {"name": seg.name, "bytes": len(data), "entries": sum(1 for _ in decode_entries(data)),
                "sha256": hashlib.sha256(data).hexdigest(), "recovered": recovered}
        with open(self.index_path, "ab") as f:
            f.write(json.dumps(line, sort_keys=True).encode() + b"\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(seg, 0o444)

    def close(self):
        self.rotate()

    def write_checkpoint(self, state: dict):
        self.flush()
        atomic_write(self.dir / "checkpoint.json", json.dumps(state, sort_keys=True).encode())

    def read_checkpoint(self):
        path = self.dir / "checkpoint.json"
        return json.loads(path.read_text()) if path.exists() else None


def read_journal(run_dir, verify: bool = True, include_open: bool = True):
    """Yield (epoch, entry) over all segments in order; verifies sealed digests."""
    jdir = Path(run_dir) / "journal"
    index = {}
    ipath = jdir / "index.ndjson"
    if ipath.exists():
        for line in ipath.read_text().splitlines():
            rec = json.loads(line)
            index[rec["name"]] = rec
    names = sorted(p.name for p in jdir.glob("e*.seg"))
    if include_open:
        names += sorted(p.name for p in jdir.glob("e*.part"))
    for name in sorted(names):
        data = (jdir / name).read_bytes()
        if verify and name in index and hashlib.sha256(data).hexdigest() != index[name]["sha256"]:
            raise ArchiveError(f"segment {name} does not match its recorded SHA-256")
        epoch = int(name[1:4])
        for entry in decode_entries(data):
            yield epoch, entry


def file_manifest(root) -> dict:
    root = Path(root)
    return {str(p.relative_to(root)): {"bytes": p.stat().st_size, "sha256": _sha256_file(p)}
            for p in sorted(root.rglob("*")) if p.is_file() and p.name != "MANIFEST.sha256.json"}
