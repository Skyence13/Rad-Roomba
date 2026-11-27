#!/usr/bin/env bash
# Rad Roomba chassis firmware: build and run everything. Exits non-zero on the first failure.
#   ./check.sh               pin map check, host build, unit tests, integration tests, STM32G474 build
#   ./check.sh --no-target   skip the STM32 build (machine without PlatformIO)
# Results of the host tests are SIMULATED (plant model); nothing here touches hardware.
set -euo pipefail
cd "$(dirname "$0")"
BUILD="${RR_CHASSIS_BUILD_DIR:-$PWD/build}"
JOBS="${RR_JOBS:-2}"
TARGET=1
[ "${1:-}" = "--no-target" ] && TARGET=0

step() { printf '\n=== %s ===\n' "$*"; }

step "1/5 pin map (tool-check against STM32G474RE LQFP64 pin data and the RR-CHS-MAIN netlist export, generated header up to date) and look-sensor geometry (frames.yaml)"
python3 tools/check_pinmap.py --emit-header "$BUILD.board_pins.h.tmp" --readme README.md --check
cmp "$BUILD.board_pins.h.tmp" port/stm32g474/include/board_pins.h || { echo "board_pins.h is stale: run tools/check_pinmap.py --emit-header port/stm32g474/include/board_pins.h"; exit 1; }
rm -f "$BUILD.board_pins.h.tmp"
python3 tools/look_geometry.py --check

step "2/5 host build (core + emulator + unit tests, -Werror, ASan/UBSan on the tests)"
cmake -S . -B "$BUILD" -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo >/dev/null
ninja -C "$BUILD" -j "$JOBS"

step "3/5 unit tests on the plant model"
"$BUILD/test_chain"
"$BUILD/test_state_machine"
"$BUILD/test_review"
"$BUILD/test_rearm"
"$BUILD/test_drive" "$BUILD/drive_report.txt"
echo "drive report written to $BUILD/drive_report.txt"

step "4/5 integration tests (rr_chassis_sim over TCP + UDP environment socket)"
python3 tests/test_integration.py "$BUILD/rr_chassis_sim"

if [ "$TARGET" = 1 ]; then
  step "5/5 STM32G474RE target build (PlatformIO, pinned platform/toolchain/framework)"
  command -v pio >/dev/null || { echo "PlatformIO Core (pio) not found"; exit 1; }
  ( cd port/stm32g474 && pio run -j "$JOBS" 2>&1 | grep -E "^(Processing|RAM:|Flash:)| error|\[(SUCCESS|FAILED)\]|SUCCESS|FAILED" ; exit "${PIPESTATUS[0]}" )
  SIZE="$HOME/.platformio/packages/toolchain-gccarmnoneeabi/bin/arm-none-eabi-size"
  for env in rr_chs_main rr_chs_main_24mhz; do
    elf="port/stm32g474/.pio/build/$env/firmware.elf"
    [ -f "$elf" ] || { echo "missing $elf"; exit 1; }
    read -r text data bss _ < <("$SIZE" "$elf" | tail -1)
    echo "$env: flash $((text + data)) bytes (text $text + data $data), static RAM $((data + bss)) bytes"
    # the image must stay in flash bank 1; the last pages of bank 2 hold the configuration
    [ $((text + data)) -lt 250000 ] || { echo "image too large for bank 1"; exit 1; }
  done
else
  step "5/5 STM32 target build SKIPPED (--no-target)"
fi

printf '\nALL CHASSIS FIRMWARE CHECKS PASSED (host results are simulated; no hardware was involved)\n'
