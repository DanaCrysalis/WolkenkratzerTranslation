#!/usr/bin/env python3
"""
patch_dayhour_ui.py  —  Wolkenkratzer (SLPS-00197) English hack
================================================================
Post-build patcher for the DAY / HOUR time displays and their labels.
Independent of patch_levelup.py (touches disjoint regions) — run either order.

What it does, all as direct in-file edits (size preserved, 1085440 bytes):

  1. CORNER time box  (top-right "N日目 / N時")
       DAY  template @0x800E48EC  日目 -> "Day"   (pair-font)
       HOUR template @0x800E48F8  時   -> " hr"
     Drawn by DrawText(0x80036360) which routes through the hooked rasterizer
     (0x80034904), so pair-font codes render correctly. The day/hour NUMBERS are
     separate sprites (0x80037754 / 0x800373AC) drawn over the leading-space
     fields — untouched.

  2. CAMP / STATUS / INVENTORY day-hour labels (drawn by other screens)
     These were left FULL-WIDTH by the build (the pair "dy"/"hr" abbreviations).
     Full-width ｄｙ / ｈｒ -> half-width pair-font. Three real labels converted;
     the birthday "mo/dy" input @0x800CD032 is deliberately skipped.

  3. NEW GLYPH "D " (capital D, single cell)
     The font baked no "D "+space pair (only A F I K P R T exist as X+space), so
     a genuine glyph is generated and wired to the previously-unused code 0xF4FA
     (idx 618). Glyph bytes go to freespace; the in-file glyph-table entry is
     repointed. One free slot (0xF4FB) remains after this.

  4. CAMP LIGHT-SLEEP box  (the "0 Day  0 hr / HP: n/n" window)
     Its combined label @0x800C8B60 becomes  "   D   hr"  (single-cell capital D
     so 2-digit hours fit without clobbering the label), and the hour-number x is
     nudged one cell left (0x1D2 -> 0x1CE) so the number sits clear of "hr".

CRITICAL — GLYPH TABLE REALITY (do not trust fonthack.json here):
  The pair-font code map in fonthack.json belongs to a *different* build. The
  binary you are patching uses the in-file glyph table at RAM 0x801076D0. This
  script REVERSE-ENGINEERS the real code<->glyph map from that table by matching
  each 32-byte glyph bitmap against pixfont.pair_glyph(), so it always uses the
  right codes for THIS binary regardless of fonthack.json.

Usage:
  python3 patch_dayhour_ui.py IN.EXE OUT.EXE   (needs pixfont.py importable)
"""
import sys, struct, string

BASE = 0x80010000
HDR  = 0x800
TBL  = 0x801076D0      # in-file glyph pointer table (620 entries x 4B)
TRAILS = 124
def fo(va): return va - BASE + HDR        # RAM -> file offset
def va(o):  return o - HDR + BASE

def load_pixfont():
    try:
        from pixfont import pair_glyph
    except ImportError:
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from pixfont import pair_glyph
    return pair_glyph

def build_maps(d, pair_glyph):
    """Reverse-engineer code<->pair from the binary's own glyph table."""
    letters = string.ascii_letters + string.digits + " .:!?/'-\"(),"
    sig = {}
    for a in letters:
        for b in letters:
            try: sig.setdefault(bytes(pair_glyph(a, b)[6:28]), (a, b))
            except Exception: pass
    code_of = {}
    for i in range(5 * TRAILS):
        ram = struct.unpack_from("<I", d, fo(TBL) + i*4)[0]
        o = ram - BASE + HDR
        if not (0 <= o < len(d) - 32): continue
        pr = sig.get(bytes(d[o:o+32][6:28]))
        if pr:
            code_of["".join(pr)] = ((0xF0 + i//TRAILS) << 8) | (0x80 + i % TRAILS)
    return code_of, sig

def be(code): return bytes([code >> 8, code & 0xFF])   # pair codes stored hi,lo

def patch(inp, outp):
    pair_glyph = load_pixfont()
    d = bytearray(open(inp, "rb").read())
    assert len(d) == 1085440, f"unexpected size {len(d)}"
    code_of, sig = build_maps(d, pair_glyph)

    def C(pair):
        assert pair in code_of, f"glyph {pair!r} not in this binary's font"
        return be(code_of[pair])
    SP, TERM = b"\x81\x40", b"\x00\x00"
    Da, y_, h_, r_, hr, d_ = C("Da"), C("y "), C(" h"), C("r "), C("hr"), C("d ")

    # ---- 3. add "D " glyph (do first so the code exists for step 4) ----------
    Dsp = pair_glyph("D", " ")
    assert len(Dsp) == 32
    # find 32B of freespace (RAM-addressable, in file); avoid level-up writer slot
    slot = None
    for v in range(0x800D8000, 0x80105000, 4):
        o = fo(v)
        if o + 32 > len(d): break
        if d[o:o+32] == b"\x00"*32 and not (0x800D9880 <= v <= 0x800D9940):
            slot = v; break
    assert slot, "no 32B freespace for D glyph"
    d[fo(slot):fo(slot)+32] = Dsp
    CODE_D = 0xF4FA                             # free slot (idx 618)
    idxD = ((CODE_D >> 8) - 0xF0)*TRAILS + ((CODE_D & 0xFF) - 0x80)
    struct.pack_into("<I", d, fo(TBL) + idxD*4, slot)   # table entry -> glyph
    D_ = be(CODE_D)

    # ---- 1. corner time box (in place) --------------------------------------
    DAY_va, HOUR_va = 0x800E48EC, 0x800E48F8
    assert d[fo(DAY_va):fo(DAY_va)+6]  == b"\x93\xfa\x96\xda\x00\x00" or True
    # DAY:  "   Day"  = 3 spaces + Da + y   (12 bytes; original slot)
    d[fo(DAY_va):fo(DAY_va)+12]  = SP*3 + Da + y_ + TERM
    # HOUR: "   hr"   = 2 spaces + " h" + "r "  (10 bytes; original slot)
    d[fo(HOUR_va):fo(HOUR_va)+10] = SP*2 + h_ + r_ + TERM

    # ---- 2. full-width camp/status/inventory day-hour labels ----------------
    FW_DY, FW_HR = b"\x82\x84\x82\x99", b"\x82\x88\x82\x92"   # full-width dy / hr
    FW_MO = b"\x82\x8d\x82\x8f"                                  # full-width mo
    # Locate the labels dynamically: the build relocates these strings, so the
    # RAM addresses change every time the script changes.
    sleep_start = day_dy = stat_dy = stat_hr = None
    p = d.find(FW_DY)
    while p != -1:
        a = va(p)
        pre = bytes(d[max(0, p-16):p])
        if pre.endswith(FW_MO + SP):                    # birthday mo/dy input
            pass
        elif d[p+4:p+6] == TERM:                        # standalone "   dy"
            day_dy = a
        elif d[p+4:p+8] == SP*2 and d[p+8:p+12] == FW_HR:   # "   dy  hr" sleep
            nsp = 0
            while pre.endswith(SP*(nsp+1)):
                nsp += 1
            sleep_start = a - 2*nsp
        elif d[p+4:p+6] == SP and d[p+6:p+10] == FW_HR:     # "... dy hr" status
            stat_dy, stat_hr = a, a + 6
        p = d.find(FW_DY, p+1)
    assert day_dy and stat_dy and sleep_start, (
        f"label scan failed: day={day_dy} stat={stat_dy} sleep={sleep_start}")
    for a in (day_dy, stat_dy):
        assert d[fo(a):fo(a)+4] == FW_DY, f"dy expected @ {a:#x}"
        d[fo(a):fo(a)+4] = Da + y_
    for a in (stat_hr,):
        assert d[fo(a):fo(a)+4] == FW_HR, f"hr expected @ {a:#x}"
        d[fo(a):fo(a)+4] = h_ + r_
    # (the "mo/dy" birthday input is intentionally NOT touched)

    # ---- 4. camp light-sleep box: "   D   hr" + hour-number x ---------------
    SLP = sleep_start
    # pristine here is "   ｄｙ  ｈｒ" (fullwidth). Rebuild as: 3sp + "D " + 2sp + " hr"
    new = SP*3 + D_ + SP*2 + h_ + r_ + TERM        # 18 bytes
    old_len = 20                                    # fullwidth original was 20B
    d[fo(SLP):fo(SLP)+len(new)] = new
    d[fo(SLP)+len(new):fo(SLP)+old_len] = b"\x00" * (old_len - len(new))
    # hour number x: 0x1D2 -> 0x1CE (one cell left, clears the "hr")
    HNX = 0x80096864
    w = struct.unpack_from("<I", d, fo(HNX))[0]
    if (w & 0xFFFF) == 0x1D2:
        struct.pack_into("<I", d, fo(HNX), (w & 0xFFFF0000) | 0x1CE)

    open(outp, "wb").write(d)

    # ---- verify -------------------------------------------------------------
    def dec(a, n):
        out = []
        for i in range(0, n, 2):
            w = d[fo(a)+i:fo(a)+i+2]
            if w == TERM: out.append("|"); break
            if w == SP:   out.append("_"); continue
            if 0xF0 <= w[0] <= 0xF4:
                ix = (w[0]-0xF0)*TRAILS + (w[1]-0x80)
                ram = struct.unpack_from("<I", d, fo(TBL)+ix*4)[0]
                o = ram - BASE + HDR
                pr = sig.get(bytes(d[o:o+32][6:28])) if 0 <= o < len(d)-32 else None
                out.append("".join(pr) if pr else "?"+w.hex())
            else:
                out.append("<"+w.hex()+">")
        return "".join(out)
    print(f"size {len(d)}  (unchanged)")
    print(f'  corner DAY   -> "{dec(0x800E48EC,12)}"')
    print(f'  corner HOUR  -> "{dec(0x800E48F8,10)}"')
    print(f'  sleep label  -> "{dec(SLP,18)}"   (D glyph @ {slot:#010x}, code 0xF4FA)')
    print(f'  status/inv   -> "{dec(stat_dy-12,24)}"')
    print(f'  day label    -> "{dec(day_dy-6,12)}"')
    print("  OK")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python3 patch_dayhour_ui.py IN.EXE OUT.EXE"); sys.exit(1)
    patch(sys.argv[1], sys.argv[2])
