#!/usr/bin/env python3
"""
verify_build.py - the PROJECT_KNOWLEDGE A.9 verification pass, as a tool.

  python3 tools/verify_build.py build/MAIN.EXE build/SLPS_001.97

Checks:
  1. output sizes match the originals (MAIN 1085440 / SLPS 333824)
  2. all four rasterizer JAL sites redirect to the font hook
  3. the five status-screen label-x immediates read 0x340401C2
  4. every live glyph-table entry byte-matches pixfont.pair_glyph()
  5. the day/hour UI strings decode to "Day" / " hr" (post-patch)
  6. the level-up patch is present (both relocated writers wired up)
Exit code 0 = all pass.
"""
import os
import string
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pixfont import pair_glyph

BASE, HDR = 0x80010000, 0x800
HOOK = 0x800D1F68
TBL = 0x801076D0
TRAILS = 124
JAL_SITES = (0x800347A8, 0x800347E4, 0x8003492C, 0x80034A6C)
ALIGN_OFFS = (0x62108, 0x627B8, 0x622B0, 0x622E8, 0x622FC)
DAY_TPL, HOUR_TPL = 0x800E48EC, 0x800E48F8

fo = lambda va: va - BASE + HDR
fails = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


def sigmap():
    letters = "".join(chr(c) for c in range(0x20, 0x7F))
    sig = {}
    for a in letters:
        for b in letters:
            try:
                sig.setdefault(bytes(pair_glyph(a, b)[6:28]), a + b)
            except Exception:
                pass
    return sig


def main(main_exe, slps):
    d = open(main_exe, "rb").read()
    print(f"verifying {main_exe}")
    check("MAIN.EXE size", len(d) == 1085440, f"{len(d)}")
    if slps and os.path.exists(slps):
        n = os.path.getsize(slps)
        check("SLPS_001.97 size", n == 333824, f"{n}")

    for va in JAL_SITES:
        w = struct.unpack_from("<I", d, fo(va))[0]
        tgt = 0x80000000 | ((w & 0x03FFFFFF) << 2)
        check(f"hook JAL @{va:#x}", tgt == HOOK, f"-> {tgt:#x}")

    for off in ALIGN_OFFS:
        w = struct.unpack_from("<I", d, off)[0]
        check(f"label-x @{off:#x}", w == 0x340401C2, f"{w:#010x}")

    sig = sigmap()
    live = bad = 0
    for i in range(5 * TRAILS):
        ram = struct.unpack_from("<I", d, fo(TBL) + i * 4)[0]
        o = ram - BASE + HDR
        if not (0 <= o < len(d) - 32):
            continue
        if d[o:o + 32] == b"\x00" * 32:
            continue
        live += 1
        if bytes(d[o:o + 32][6:28]) not in sig:
            bad += 1
    check("glyph table integrity", bad == 0, f"{live} live glyphs, {bad} unmatched")

    def decode(va, n):
        out = []
        for i in range(0, n, 2):
            w = d[fo(va) + i:fo(va) + i + 2]
            if w == b"\x00\x00":
                break
            if w == b"\x81\x40":
                out.append(" ")
                continue
            if 0xF0 <= w[0] <= 0xF4:
                ix = (w[0] - 0xF0) * TRAILS + (w[1] - 0x80)
                ram = struct.unpack_from("<I", d, fo(TBL) + ix * 4)[0]
                o = ram - BASE + HDR
                out.append(sig.get(bytes(d[o:o + 32][6:28]), "?") if 0 <= o < len(d) - 32 else "?")
            else:
                out.append("<%s>" % w.hex())
        return "".join(out)

    day, hour = decode(DAY_TPL, 12), decode(HOUR_TPL, 10)
    check("corner DAY template", day.strip() == "Day", repr(day))
    check("corner HOUR template", hour.strip() == "hr", repr(hour))

    # level-up: both shared writers must have been split off to relocated copies
    magic_j = struct.unpack_from("<I", d, fo(0x80097AEC))[0]
    str_j = struct.unpack_from("<I", d, fo(0x80097B9C))[0]
    tgt_m = 0x80000000 | ((magic_j & 0x03FFFFFF) << 2)
    tgt_s = 0x80000000 | ((str_j & 0x03FFFFFF) << 2)
    check("level-up magic writer re-routed", tgt_m != 0x80097DA4, f"j -> {tgt_m:#x}")
    check("level-up STR writer re-routed", tgt_s != 0x80097C50, f"j -> {tgt_s:#x}")

    print("ALL PASS" if not fails else f"{len(fails)} FAILURE(S): " + ", ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "build/MAIN.EXE"
    s = sys.argv[2] if len(sys.argv) > 2 else "build/SLPS_001.97"
    sys.exit(main(m, s))
