import json, os, sys
from pathlib import Path
import pytest

SRC = Path(__file__).resolve().parents[2]
for pkg in sorted(SRC.iterdir()):
    if (pkg / pkg.name).is_dir() and str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
REPO = Path(os.environ.get("RR_REPO", SRC.parents[1]))
EXAMPLES = REPO / "examples"


@pytest.fixture(scope="session")
def repo():
    return REPO


@pytest.fixture(scope="session")
def examples():
    return EXAMPLES


@pytest.fixture()
def demo_registry():
    reg = json.loads((EXAMPLES / "head_registry_bench.json").read_text())
    reg["records"][0]["authorized_uses"] = ["BENCH", "COMMISSIONING"]
    reg["records"][0]["calibration_id"] = "DEMO-CAL-SYNTH-0001"
    reg["records"][0]["mount_transform"] = {"xyz_m": [0.1385, 0.0, 0.032], "rpy_rad": [0, 0, 0],
                                            "basis": "contract nominal (not measured)"}
    return reg
