#!/bin/bash
# Usage: mechanical/tools/slice.sh MANIFEST [slice_plates.py options]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/slice_plates.py" "$@"
