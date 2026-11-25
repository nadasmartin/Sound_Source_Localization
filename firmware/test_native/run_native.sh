#!/usr/bin/env bash
# Run the ESP32's on-board TDOA pipeline on the PC, on a saved recording.
#   ./run_native.sh <recording.npz> [temp_C] [threshold]
# The .npz holds "x": raw ADC samples, shape [n][4] (4 mics, 44.1 kHz).
# Output: the same JSON event lines the ESP32 prints.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
lib="$here/../lib/tdoa"
build="$here/build"
mkdir -p "$build"

g++ -O2 -std=c++17 -Wall -Wextra -I"$lib" "$here/native_main.cpp" "$lib"/*.cpp -o "$build/tdoa_native"

npz="$1"; shift
raw="$build/$(basename "${npz%.npz}").u16"
python3 - "$npz" "$raw" <<'EOF'
import sys, numpy as np
rec = np.load(sys.argv[1])
rec["x"].round().astype("<u2").tofile(sys.argv[2])
EOF
"$build/tdoa_native" "$raw" "$@"  # extra args: temp_C threshold [template.i16 k_lo k_hi]
