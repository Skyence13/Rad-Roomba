#!/usr/bin/env bash
# Rebuild and re-run everything for firmware/common and firmware/head. Exits non-zero on the
# first failure.
#
#   firmware/head/check.sh              all checks, including the STM32G474 image
#   firmware/head/check.sh --no-target  host checks only (no PlatformIO, no network)
#
# Needs: gcc, cmake >= 3.16, ninja, python3 with jsonschema >= 4.18 and PyYAML, and (for the
# target image) PlatformIO Core with access to registry.platformio.org.
set -euo pipefail
HEAD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HEAD/../.." && pwd)"
BUILD="${RRH_BUILD_DIR:-$HEAD/build/host}"
JOBS="${RRH_JOBS:-2}"
TARGET=1
[ "${1:-}" = "--no-target" ] && TARGET=0

step() { printf '\n==== %s\n' "$*"; }

step "pin map against the ST pin database; generated header and README table are current"
python3 "$HEAD/tools/check_pinmap.py"
python3 "$HEAD/tools/gen_pinmap.py" --check

step "baseline 0.3 interface package is unmodified and its own tests still pass"
(cd "$REPO" && grep -E '  (interface|examples)/' SHA256SUMS.txt | sha256sum -c --quiet -)
(cd "$REPO/interface" && python3 test_interface.py 2>&1 | tail -3)

step "host build: -std=c11 -Wall -Wextra -Werror -Wconversion, AddressSanitizer + UBSan"
cmake -S "$HEAD" -B "$BUILD" -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo >/dev/null
cmake --build "$BUILD" -j"$JOBS"

step "host tests: common unit + interop, head core, event capture, emulator against the baseline host tools"
RRH_TEST_RESULTS="$BUILD/emulator_measurements.json" ctest --test-dir "$BUILD" --output-on-failure -j1
echo "emulator measurements: $BUILD/emulator_measurements.json"

if [ "$TARGET" = 1 ]; then
    step "STM32G474VET6 image (PlatformIO, pinned versions)"
    (cd "$HEAD" && pio run -e rr_head_acq -e nucleo_bringup -j"$JOBS" | grep -E 'warning|error|RAM:|Flash:|SUCCESS|FAILED|Processing' || true)
    ELF="$HEAD/.pio/build/rr_head_acq/firmware.elf"
    test -s "$ELF" && test -s "$HEAD/.pio/build/rr_head_acq/firmware.bin" && test -s "$HEAD/.pio/build/nucleo_bringup/firmware.elf"
    SIZE="$(ls "$HOME"/.platformio/packages/toolchain-gccarmnoneeabi/bin/arm-none-eabi-size)"
    "$SIZE" "$ELF"
    # flash = text + data, RAM = data + bss (static; the stack grows down from the end of RAM)
    "$SIZE" "$ELF" | awk 'NR==2 {printf "flash %d bytes of 524288 (%.1f %%), static RAM %d bytes of 131072 (%.1f %%)\n", $1+$2, ($1+$2)/5242.88, $2+$3, ($2+$3)/1310.72}'
else
    step "STM32 image skipped (--no-target)"
fi

printf '\nALL CHECKS PASSED\n'
