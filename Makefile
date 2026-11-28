# Rad Roomba design 0.4 - build and check entry points.
# Every target runs the subsystem's own script; nothing here adds logic.
# See README_0.4.md for prerequisites and for what each result does and does not prove.
#
#   make check-fast     baseline, registers, harness, both firmwares        (about 3 min)
#   make check          check-fast + radiometry + small boards + mechanical + robot software
#   make CQ_PY=/path/to/python mechanical
#
# CQ_PY: a Python 3.12 with the packages of mechanical/common/requirements.txt (CadQuery 2.7).
# Create one with:  make cq-venv   (needs `uv`)

SHELL := /bin/bash
ROOT  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
CQ_PY ?= $(ROOT)/mechanical/common/.venv/bin/python

.PHONY: help check check-fast baseline registers harness firmware firmware-head firmware-chassis \
        radiometry boards-small boards-large-noroute mechanical mech-common mech-head mech-prototype \
        mech-production ros-image ros-unit ros-scenarios ros-native cq-venv

help:
	@sed -n '1,12p' $(ROOT)/Makefile

check-fast: baseline registers harness firmware
check: check-fast radiometry boards-small mechanical ros-unit ros-scenarios

# --- frozen 0.3 baseline (must never change)
baseline:
	cd $(ROOT) && sha256sum -c --quiet SHA256SUMS.txt
	cd $(ROOT) && python3 software/map_demo.py --self-test
	cd $(ROOT) && python3 interface/test_interface.py

# --- registers (requirements, verification, risks, decisions, BOM, RFQ cross-references)
registers:
	cd $(ROOT) && python3 planning/bom_0.4/extract_board_boms.py
	cd $(ROOT) && python3 planning/check_registers_0.4.py

# --- harness tables and cross-check against contract, boards and frames
harness:
	cd $(ROOT) && python3 harness/build.py
	cd $(ROOT) && python3 harness/cross_check.py

# --- firmware: host tests under sanitizers, emulator integration tests, STM32 images (PlatformIO)
firmware: firmware-head firmware-chassis
firmware-head:
	$(ROOT)/firmware/head/check.sh
firmware-chassis:
	$(ROOT)/firmware/chassis/check.sh

# --- radiometry study (unit tests, tables, figures, reports; deterministic; about 8 min)
radiometry:
	cd $(ROOT)/analysis/radiometry && ./run_all.sh

# --- boards (docker: kicad/kicad:9.0 and ghcr.io/freerouting/freerouting)
# Small boards: generate, route (cached), ERC, DRC with schematic parity, fabrication outputs.
boards-small:
	cd $(ROOT) && python3 tools/eda/rrkicad.py build electronics/tof_carrier/board.py
	cd $(ROOT) && python3 tools/eda/rrkicad.py build electronics/panel/board.py
# Large boards: schematic + placement only. They are NOT routed; the command exits non-zero
# because of the unconnected count. Read reports/summary.json for ERC / DRC / parity.
boards-large-noroute:
	cd $(ROOT) && python3 electronics/chassis_main/overrides.py
	-cd $(ROOT) && python3 tools/eda/rrkicad.py build electronics/chassis_main/board.py --no-route
	cd $(ROOT) && python3 electronics/head_acq/overrides.py
	-cd $(ROOT) && python3 tools/eda/rrkicad.py build electronics/head_acq/board.py --no-route
	cd $(ROOT) && python3 electronics/head_acq/scripts/netcheck.py

# --- mechanical (CadQuery). mech-head deletes and regenerates its outputs: always pass a working CQ_PY.
mechanical: mech-common mech-head mech-prototype mech-production
cq-venv:
	cd $(ROOT)/mechanical/common && uv venv --python 3.12 .venv && \
	  uv pip install --python .venv/bin/python -r requirements.txt
mech-common:
	cd $(ROOT)/mechanical/common && RR_PY=$(CQ_PY) ./build.sh
mech-head:
	cd $(ROOT) && RR_PY=$(CQ_PY) mechanical/head/build.sh
mech-prototype:
	cd $(ROOT) && PY=$(CQ_PY) mechanical/prototype_x1c/build.sh
mech-production:
	cd $(ROOT) && PY=$(CQ_PY) RR_PY=$(CQ_PY) mechanical/production/build.sh

# --- robot software (docker image rad-roomba/ros2-ws:0.4)
ros-image:
	cd $(ROOT)/ros2_ws && tools/build.sh
ros-unit:
	cd $(ROOT)/ros2_ws && tools/test.sh unit
ros-scenarios:
	cd $(ROOT)/ros2_ws && tools/test.sh scenarios
ros-native:
	cd $(ROOT)/ros2_ws && tools/test.sh native
