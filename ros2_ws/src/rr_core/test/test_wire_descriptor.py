"""Baseline compatibility: wire codec, descriptor discovery, frame checks.
Traces: RQ-024, RQ-025, VT-019, VT-033 (tool-checked against examples/)."""
import copy, hashlib, json
import pytest
from rr_core import wire, descriptor, frames


def test_crc_check_value_and_example_wire(examples):
    from zlib import crc32
    assert f"{crc32(b'123456789'):08X}" == "CBF43926"
    raw = (examples / "head_response.wire").read_bytes()
    rec = wire.decode(raw)
    assert rec["body"]["sequence"] == 152
    assert wire.encode(rec) == raw           # byte-identical re-encode


def test_schema_copies_match_interface(repo):
    from pathlib import Path
    import rr_core
    pkg = Path(rr_core.__file__).parent / "schemas"
    for name in ("acquisition.schema.json", "head_descriptor.schema.json"):
        assert (pkg / name).read_bytes() == (repo / "interface" / name).read_bytes()


@pytest.mark.parametrize("bad", [b'{"a":1}\t00000000\n', b'{"a":1,"a":2}\tXXXXXXXX\n', b'{"a":NaN}\t00000000\n',
                                 b'{"a":1}\n', b'[1]\t0CB4C3AF\n'])
def test_decode_rejects(bad):
    with pytest.raises(wire.WireError):
        wire.decode(bad)


def test_duplicate_key_rejected_with_good_crc():
    from zlib import crc32
    data = b'{"a":1,"a":2}'
    with pytest.raises(wire.WireError):
        wire.decode(data + b"\t" + f"{crc32(data):08X}".encode() + b"\n")


def test_stream_decoder_resync_and_oversize():
    dec = wire.StreamDecoder(max_bytes=200)
    good = wire.encode({"x": 1})
    out = dec.feed(b"garbage without crc\n" + good[:5])
    assert out[0][1] is None and dec.pending == 5
    out = dec.feed(good[5:] + b"z" * 500)
    assert out[0][1] == {"x": 1}
    out = dec.feed(b"zz\n" + good)
    assert out[0][2] == "oversize record discarded" and out[1][1] == {"x": 1}


def test_transactions_example_handshake(examples, demo_registry):
    lines = [json.loads(l) for l in (examples / "head_transactions.ndjson").read_text().splitlines() if l.strip()]
    hello = lines[1]["body"]
    chunks = [l["body"] for l in lines if l["type"] == "RSP" and "bytes_b64" in l["body"]]
    data = descriptor.assemble_descriptor(hello, chunks)
    assert data == (examples / "head_descriptor.json").read_bytes()
    bench = json.loads((examples / "head_registry_bench.json").read_text())
    ok = descriptor.evaluate(hello, data, bench, "BENCH")
    assert ok["descriptor_sha256"] == hashlib.sha256(data).hexdigest()
    with pytest.raises(descriptor.DescriptorError) as e:
        descriptor.evaluate(hello, data, bench, "SURVEY")       # ICD section 9: must reject
    assert e.value.reason == "NOT_AUTHORIZED"
    with pytest.raises(descriptor.DescriptorError) as e:
        descriptor.evaluate(hello, data, demo_registry, "SURVEY")
    # authorised for commissioning only -> not SURVEY
    assert e.value.reason == "NOT_AUTHORIZED"
    assert descriptor.evaluate(hello, data, demo_registry, "COMMISSIONING")["calibration_id"]
    man = descriptor.attachment_manifest(hello, ok, "f723fc32-bf62-41c7-a75f-b0053bef75b8")
    assert man == json.loads((examples / "head_session.json").read_text())


def test_descriptor_rejections(examples, demo_registry):
    hello = json.loads((examples / "head_hello.json").read_text())
    data = (examples / "head_descriptor.json").read_bytes()
    with pytest.raises(descriptor.DescriptorError) as e:
        descriptor.evaluate(hello, data[:-1] + b" ", demo_registry, "BENCH")
    assert e.value.reason == "DESCRIPTOR_DIGEST"
    reg = copy.deepcopy(demo_registry); reg["records"][0]["serial"] = "OTHER"
    with pytest.raises(descriptor.DescriptorError) as e:
        descriptor.evaluate(hello, data, reg, "BENCH")
    assert e.value.reason == "UNKNOWN_HEAD"
    reg = copy.deepcopy(demo_registry); reg["records"][0]["firmware"] = "x"
    with pytest.raises(descriptor.DescriptorError) as e:
        descriptor.evaluate(hello, data, reg, "BENCH")
    assert e.value.reason == "REGISTRY_MISMATCH"
    # swapped lane order with a matching hash is still refused (geometry check)
    desc = json.loads(data); desc["segments"][0], desc["segments"][1] = desc["segments"][1], desc["segments"][0]
    d2 = json.dumps(desc).encode(); h2 = dict(hello, descriptor_sha256=hashlib.sha256(d2).hexdigest(), descriptor_bytes=len(d2))
    with pytest.raises(descriptor.DescriptorError):
        descriptor.evaluate(h2, d2, demo_registry, "BENCH")


def test_frame_examples(examples):
    good = json.loads((examples / "head_normal.json").read_text())
    bad = json.loads((examples / "head_degraded.json").read_text())
    hist = {}
    for frame, want in ((good, [0, 1, 2, 3]), (bad, [])):
        frames.validate_schema(frame); frames.validate_semantics(frame)
        assert frames.examine(frame, hist, 10000, "k") == (want, [])
    f = copy.deepcopy(bad); f["sync"] = copy.deepcopy(good["sync"])
    assert frames.examine(f, {}, 10000, "k")[0] == [0, 1, 3]
    f = copy.deepcopy(good); f["segments"][2]["alpha"]["live_us"] = f["span_us"] + 1
    with pytest.raises(frames.FrameError):
        frames.validate_semantics(f)
    f = copy.deepcopy(good); f["segments"][0]["alpha"] = None
    with pytest.raises(frames.FrameError):
        frames.validate_semantics(f)
    with pytest.raises(frames.FrameError):
        frames.examine(good, hist, 10000, "k")       # duplicate/out of order
