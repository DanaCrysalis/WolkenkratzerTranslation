#!/usr/bin/env bash
# build.sh — full Track A pipeline: ODS -> TSV -> MAIN.EXE + SLPS_001.97
#
#   ./build.sh            normal build
#   ./build.sh --no-ods   skip the ODS->TSV conversion (edit the TSV directly)
#
# Requires the PRISTINE Japanese originals in orig/ :
#   orig/MAIN.EXE.bak      (1085440 bytes)
#   orig/SLPS_001.97.bak   ( 333824 bytes)
# Outputs land in build/ :
#   build/MAIN.EXE  build/SLPS_001.97
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

for f in orig/MAIN.EXE.bak orig/SLPS_001.97.bak; do
  [ -f "$f" ] || { echo "MISSING $f — see README (pristine JP originals)"; exit 1; }
done

# 1. spreadsheet -> TSV (authoritative translation source)
if [ "${1:-}" != "--no-ods" ]; then
  ( cd script && python3 ods2tsv.py )
fi

# 2. text build + font hack  -> build/MAIN.EXE, build/SLPS_001.97
mkdir -p build
export WK_DATA="$ROOT/data" WK_SCRIPT="$ROOT/script" WK_ORIG="$ROOT/orig"
( cd build && python3 "$ROOT/tools/build_final3.py" )

# 3. post-build code patches (order irrelevant; regions are disjoint)
python3 tools/patch_levelup.py    build/MAIN.EXE build/MAIN.lv.EXE
python3 tools/patch_dayhour_ui.py build/MAIN.lv.EXE build/MAIN.EXE
rm -f build/MAIN.lv.EXE

# 4. sanity
python3 - <<'PY'
import os
for f, n in (("build/MAIN.EXE", 1085440), ("build/SLPS_001.97", 333824)):
    s = os.path.getsize(f)
    assert s == n, f"{f}: {s} != {n}"
print("sizes OK")
PY
python3 tools/verify_build.py build/MAIN.EXE build/SLPS_001.97
echo "==> build/MAIN.EXE  build/SLPS_001.97"
