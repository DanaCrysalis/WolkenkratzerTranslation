#!/usr/bin/env python3
"""
build_final3.py - translated MAIN.EXE with half-width pair-glyph font hack.

Pipeline discovered by reverse engineering:
  print fns -> rasterizer(s) -> jal 0x80098140 (BIOS Krom2RawAdd stub, B(0x51))
  glyph = 16 rows x 2 bytes big-endian, msb = leftmost pixel; engine bolds
  with row|(row>>1) and paints ink=0xF on bg=0x2 into a 4bpp 16x16 cell.

Hack: hook the 4 jal sites. Codes 0xF0..0xF4 lead / 0x80..0xFB trail map to
our pair glyphs (two 5px letters in one 16px cell => 8px per character).
Everything else falls through to the BIOS kanji ROM.
"""
import json
import re
import struct

import build_final as bf
from pixfont import pair_glyph

LOAD, HDR = 0x80010000, 0x800
bf_dpath, bf_opath = bf.dpath, bf.opath

# ---- text config changes enabled by half-width ----
bf.TRIMS.clear()
bf.TRIMS[261] = ("Let's say you're smart. Magic works better for you. Not me.")
# TSV is the sole source of translatable strings: drop ALL id-based overrides.
# (SUPPLEMENT fixes below are NOT overrides -- they patch status-screen labels
#  and code at raw addresses that the TSV doesn't cover, so they remain.)
bf.OVERRIDES.clear()
bf.SUPPLEMENT[0x0F9814] = "Class"         # no ':' -- the window's dotted separator provides the fat colon
# HP/STR/INT are 2-cell labels; pad to 3 cells (like Level/MP/Speed) so the
# opaque text cells cover the stray glyph the JP labels used to hide at the
# old x. Every label row now spans 0x1C2..0x1CE, flush with the separator.
bf.SUPPLEMENT[0x006150] = "HP    "
bf.SUPPLEMENT[0x006140] = "STR   "
bf.SUPPLEMENT[0x006138] = "INT   "
bf.SUPPLEMENT[0x0FF088] = " Class"        # creation screen: 5-cell field
bf.SUPPLEMENT[0x0068C8] = "Knight"
bf.SUPPLEMENT[0x0068E0] = "Fighter"
# Equip labels: the JP originals are 15-cell full-line strings (label + 12
# fullwidth spaces) drawn FIRST to blank the whole line; the item name is
# drawn on top. Pad ours to 30 half-width chars so the enchant-bonus area
# after the item name gets cleared too (fixes "n the"/"l the" leftovers).
bf.SUPPLEMENT[0x006184] = "Shld :  ".ljust(28)   # 盾　：
bf.SUPPLEMENT[0x0061A4] = "Armor:  ".ljust(28)   # 防具：
bf.SUPPLEMENT[0x0061C4] = "Wpn  :  ".ljust(28)   # 武器：
for _o in (0x0F915C, 0x0F916C, 0x0F917C, 0x0F919C, 0x0F91AC,
           0x0F91EC, 0x0F91FC):
    bf.SUPPLEMENT[_o] = bf.SUPPLEMENT[_o].ljust(14)

_orig_wrap = bf.wrap_intro
bf.wrap_intro = lambda t, width=26: _orig_wrap(t, width)

# strings that must remain full-width, one char per cell
FW_ONLY = {
    # letter-grid rows (grid cell index == char index)
    0xFED3C, 0xFED48, 0xFED54, 0xFED60, 0xFED6C, 0xFED78,
    0xFEE4C, 0xFEE58, 0xFEE64, 0xFEE70, 0xFEE7C, 0xFEE88,
    # tabular headers aligned over FW numeric columns
    0x007044, 0x00706C, 0x007F6C, 0x0F9868, 0x0FEFE4,
}

# id ranges whose strings live in fixed-width cycling fields; padded to
# uniform width per group so shorter entries fully overwrite longer ones
PAD_GROUPS = [
    range(305, 323),          # techniques
    range(323, 331),          # magics
    range(331, 356),          # levelled spells
    range(356, 415),          # items
    range(177, 183),          # NPC names
    (124, 125),               # class names (with Knight/Fighter suppl.)
    (144, 145, 146),          # search status field
]
PAD_EXTRA = {0x0068C8: 0, 0x0068E0: 0}   # join class group by offset

# offset -> leading half-width spaces, re-applied after the TSV loader's
# .strip(). 2 spaces = one full-width cell.
LEAD_INDENT = {0x005FDC: 2}              # command screen "Inventory"


def apply_field_padding(trans, id_to_off):
    for grp in PAD_GROUPS:
        offs = [id_to_off[i] for i in grp if i in id_to_off
                and id_to_off[i] in trans]
        if grp == (124, 125):
            offs += [o for o in (0x0068C8, 0x0068E0) if o in trans]
        if not offs:
            continue
        w = max(len(trans[o]) for o in offs)
        w += w % 2
        for o in offs:
            trans[o] = trans[o].ljust(w)
    return trans


def apply_slot_padding(trans, strings_map, max_cells=10):
    """The UI draws label sprites at the original string's fixed width;
    shorter translations expose stale sheet texels. Pad every short,
    single-line label to at least the original JP cell count."""
    for off, en in list(trans.items()):
        if off in FW_ONLY or "\x0a" in en or "\\n" in en:
            continue
        s = strings_map.get(off)
        if not s:
            continue
        cells = (s["end"] - s["off"]) // 2
        if not (1 <= cells <= max_cells):
            continue
        want = 2 * cells
        w = _word_cols(en)
        if w < want:
            trans[off] = en + " " * (want - w)
    return trans


HOOK_SITES = (0x800347A8, 0x800347E4, 0x8003492C, 0x80034A6C)

# dialogue box is 15 cells wide; one cell = 2 half-width chars
WRAP_COLS = 28


def _word_cols(word):
    """column width: ascii char = 1, FW char (incl. X{2,} runs) = 2."""
    cols = 0
    for xseg in re.split(r"(X{2,})", word):
        if not xseg:
            continue
        if xseg[0] == "X" and re.fullmatch(r"X{2,}", xseg):
            cols += 2 * len(xseg)
        else:
            cols += sum(1 if 0x20 <= ord(c) <= 0x7E else 2 for c in xseg)
    return cols


def wrap_words(text, cols=WRAP_COLS):
    """Insert line breaks at word boundaries so no line exceeds `cols`
    half-char columns; existing breaks are preserved."""
    raw = text.replace("\\n", "\x0a")
    parts = re.split(r"(\x0a+)", raw)
    out = []
    for part in parts:
        if not part:
            continue
        if part[0] == "\x0a":
            out.append(part)
            continue
        lines, cur, curw = [], [], 0
        for word in part.split(" "):
            w = _word_cols(word)
            add = w if not cur else curw + 1 + w
            if cur and add > cols:
                lines.append(" ".join(cur))
                cur, curw = [word], w
            else:
                cur.append(word)
                curw = add
        if cur:
            lines.append(" ".join(cur))
        out.append("\x0a\x0a".join(lines))
    return "".join(out)


LEADS = 5          # 0xF0..0xF4
TRAILS = 124       # 0x80..0xFB
NSLOTS = LEADS * TRAILS


def idx_to_code(i):
    return ((0xF0 + i // TRAILS) << 8) | (0x80 + i % TRAILS)


# ---- segmentation shared by chunker and encoder ----

def segments(text):
    """yield (kind, s): kind in {'nl','fw','ascii'}; X-runs>=2 stay fw."""
    raw = text.replace("\\n", "\x0a")
    raw = re.sub(r"\x0a+",
                 lambda m: m.group(0) if len(m.group(0)) % 2 == 0
                 else m.group(0) + "\x0a", raw)
    for xseg in re.split(r"(X{2,})", raw):
        if not xseg:
            continue
        if xseg[0] == "X" and re.fullmatch(r"X{2,}", xseg):
            yield ("fw", xseg)
            continue
        for m in re.finditer(r"\x0a+|[ -~]+|[^\x0a -~]+", xseg):
            seg = m.group(0)
            if seg[0] == "\x0a":
                yield ("nl", seg)
            elif 0x20 <= ord(seg[0]) <= 0x7E:
                yield ("ascii", seg)
            else:
                yield ("fw", seg)


def chunk_pairs(seg):
    if len(seg) % 2:
        seg += " "
    return [seg[i:i+2] for i in range(0, len(seg), 2)]


def collect_chunks(trans):
    from collections import Counter
    c = Counter()
    for off, en in trans.items():
        if off in FW_ONLY:
            continue
        for kind, seg in segments(en):
            if kind == "ascii":
                for p in chunk_pairs(seg):
                    c[p] += 1
    return c


def encode2(text, codes):
    out = bytearray()
    for kind, seg in segments(text):
        if kind == "nl":
            out += seg.encode("ascii")
        elif kind == "fw":
            out += bf.fw(seg).encode("shift_jis")
        else:
            for p in chunk_pairs(seg):
                code = codes.get(p)
                if code is None:
                    out += bf.fw(p).encode("shift_jis")
                else:
                    out += bytes([code >> 8, code & 0xFF])
    out += b"\x00"
    if len(out) % 2:
        out += b"\x00"
    return bytes(out)


# ---- hook assembly ----

def hook_words(table_ram):
    hi = (table_ram + 0x8000) >> 16
    lo = table_ram & 0xFFFF
    return [
        0x00044A02,              # srl   t1,a0,8
        0x2529FF10,              # addiu t1,t1,-0xF0
        0x2D2A0005,              # sltiu t2,t1,5
        0x1140000E,              # beq   t2,zero,bios (+14)
        0x308B00FF,              # andi  t3,a0,0xFF
        0x256BFF80,              # addiu t3,t3,-0x80
        0x2D6A007C,              # sltiu t2,t3,124
        0x1140000A,              # beq   t2,zero,bios (+10)
        0x000951C0,              # sll   t2,t1,7
        0x00094880,              # sll   t1,t1,2
        0x01495023,              # subu  t2,t2,t1     (t1*124)
        0x014B5021,              # addu  t2,t2,t3
        0x000A5080,              # sll   t2,t2,2
        0x3C090000 | hi,         # lui   t1,%hi(table)
        0x012A4821,              # addu  t1,t1,t2
        0x8D220000 | lo,         # lw    v0,%lo(table)(t1)
        0x03E00008,              # jr    ra
        0x00000000,              # nop
        0x240A00B0,              # bios: li t2,0xB0
        0x01400008,              # jr    t2
        0x24090051,              # li    t1,0x51  (Krom2RawAdd)
    ]


# ---- main build ----

def build_main3():
    d = bytearray(open(bf_opath("MAIN.EXE.bak"), "rb").read())
    strings = json.load(open(bf_dpath("MAIN_script2.json", "MAIN.script2.json")))
    strings.sort(key=lambda s: s["off"])
    coderefs = {int(k, 16): v for k, v in
                json.load(open(bf_dpath("MAIN_code_refs2.json", "MAIN.code_refs2.json"))).items()}
    freespace = json.load(open(bf_dpath("MAIN_freespace.json", "MAIN.freespace.json")))
    trans = bf.load_translations()
    # The TSV loader strips leading whitespace, so the JP indent of the
    # command-screen list entries is lost. 0x5FDC (JP "　アイテム") must start
    # one full cell in, like the Magic/Skills SUPPLEMENT entries beside it, or
    # its first two half-width letters sit under the column's X icon.
    for _off, _lead in LEAD_INDENT.items():
        if _off in trans:
            trans[_off] = " " * _lead + trans[_off].lstrip()
    NORM = {"\u2019": "'", "\u2018": "'", "\u201C": '"', "\u201D": '"'}
    trans = {off: "".join(NORM.get(c, c) for c in en)
             for off, en in trans.items()}
    trans = {off: (en if off in FW_ONLY else wrap_words(en))
             for off, en in trans.items()}
    id_to_off = {}
    for line in open(bf.TSV, encoding="utf-8").read().splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) >= 6:
            id_to_off[int(cols[0])] = int(cols[1], 16)
    trans = apply_field_padding(trans, id_to_off)
    trans = apply_slot_padding(trans, {s["off"]: s for s in strings})
    bymap = {s["off"]: s for s in strings}

    # unaligned pointer rescan (id 261 case)
    for off, s in bymap.items():
        if off in trans and not s["refs"] and \
           not coderefs.get(off - HDR + LOAD):
            needle = struct.pack("<I", off - HDR + LOAD)
            p = d.find(needle)
            while p != -1:
                s["refs"].append(p)
                p = d.find(needle, p + 1)

    # glyph inventory; chunks appearing in short UI strings are protected
    chunk_counts = collect_chunks(trans)
    protected = set()
    for off, en in trans.items():
        if off in FW_ONLY or len(en) > 30:
            continue
        for kind, seg in segments(en):
            if kind == "ascii":
                protected.update(chunk_pairs(seg))
    ordered = sorted(chunk_counts,
                     key=lambda p: (p not in protected, -chunk_counts[p]))
    chunks = ordered[:NSLOTS]
    codes = {p: idx_to_code(i) for i, p in enumerate(chunks)}
    print(f"pair chunks: {len(chunk_counts)} unique, "
          f"{len(chunks)} given glyphs (cap {NSLOTS})")

    # build jobs
    jobs, inplace, skipped = [], [], []
    for off, en in sorted(trans.items()):
        s = bymap.get(off)
        if not s:
            skipped.append((off, "not in string map"))
            continue
        ram = off - HDR + LOAD
        crefs = coderefs.get(ram, [])
        payload = (bf.encode(en) if off in FW_ONLY
                   else encode2(en, codes))
        if s["refs"] or crefs:
            jobs.append({"s": s, "ram": ram, "payload": payload,
                         "crefs": crefs})
        else:
            budget = s["end"] - s["off"] + 1
            if len(payload) <= budget + 2:
                inplace.append({"s": s, "payload": payload,
                                "budget": budget})
            else:
                skipped.append((off, f"in-place too big "
                                     f"({len(payload)}>{budget})"))

    # shared-lui page locks
    lui_owner, shared_luis = {}, set()
    for ram, prs in coderefs.items():
        for l, _ in prs:
            if l in lui_owner and lui_owner[l] != ram:
                shared_luis.add(l)
            lui_owner[l] = ram
    for j in jobs:
        j["page_lock"] = any(l in shared_luis for l, _ in j["crefs"])

    # allocation pool: vacated string spans + audited free blocks
    all_offs = sorted(bymap)
    vacated = []
    for j in jobs:
        a, b = j["s"]["off"], j["s"]["end"] + 1
        nxt = next((o for o in all_offs if o > j["s"]["off"]), None)
        if nxt and 0 <= nxt - b <= 8 and all(x == 0 for x in d[b:nxt]):
            b = nxt
        vacated.append([a, b])
    vacated.sort()
    pool = []
    for a, b in vacated:
        if pool and a <= pool[-1][1]:
            pool[-1][1] = max(pool[-1][1], b)
        else:
            pool.append([a, b])
    for a, b in pool:
        d[a:b] = b"\x00" * (b - a)
    for off, ln in freespace:
        pool.append([off, off + ln])
    pool.sort()
    regions = []
    for a, b in pool:
        if regions and a <= regions[-1][1]:
            regions[-1][1] = max(regions[-1][1], b)
        else:
            regions.append([a, b])
    total_pool = sum(b - a for a, b in regions)
    print(f"pool: {total_pool} bytes in {len(regions)} regions "
          f"(largest {max(b-a for a,b in regions)})")

    def alloc(size, page=None, align=2):
        best = None
        for r in regions:
            a = (r[0] + align - 1) // align * align
            if r[1] - a < size:
                continue
            if page is not None and ((a - HDR + LOAD) + 0x8000) >> 16 != page:
                continue
            if best is None or (best[1] - best[0]) > (r[1] - r[0]):
                best = r
        if best is None:
            return None
        a = (best[0] + align - 1) // align * align
        best[0] = a + size
        return a

    # 1) hook code + pointer table + blank glyph
    hook_off = alloc(21 * 4, align=4)
    assert hook_off, "no room for hook"
    hook_ram = hook_off - HDR + LOAD
    table_off = alloc(NSLOTS * 4, align=4)
    assert table_off, "no room for glyph pointer table"
    table_ram = table_off - HDR + LOAD
    blank_off = alloc(32, align=4)
    d[blank_off:blank_off + 32] = b"\x00" * 32

    # 2) budget glyphs by simulating string placement on a pool copy
    import copy
    sim = copy.deepcopy(regions)

    def sim_alloc(size, page=None, align=2):
        best = None
        for r in sim:
            a = (r[0] + align - 1) // align * align
            if r[1] - a < size:
                continue
            if page is not None and \
               ((a - HDR + LOAD) + 0x8000) >> 16 != page:
                continue
            if best is None or (best[1] - best[0]) > (r[1] - r[0]):
                best = r
        if best is None:
            return None
        a = (best[0] + align - 1) // align * align
        best[0] = a + size
        return a

    for j in sorted(jobs, key=lambda x: -len(x["payload"])):
        page = ((j["ram"] + 0x8000) >> 16) if j["page_lock"] else None
        sim_alloc(len(j["payload"]), page)
    # glyphs pack at 28B stride (rows 0-2/14-15 are always zero and are
    # shared between neighbours); a run of n glyphs needs 28n+4 bytes
    capacity = sum((b - a - 4) // 28 for a, b in sim if b - a >= 32)
    nglyphs = max(0, min(len(chunks), capacity - 4))
    nprot = sum(1 for p in chunks if p in protected)
    assert nglyphs >= nprot, \
        f"pool too small even for protected UI chunks ({nglyphs}<{nprot})"
    if nglyphs < len(chunks):
        print(f"budget: {len(chunks) - nglyphs} rare chunks fall back to FW")
        chunks = chunks[:nglyphs]
        codes = {p: idx_to_code(i) for i, p in enumerate(chunks)}
        for j in jobs:
            off = j["s"]["off"]
            if off not in FW_ONLY:
                j["payload"] = encode2(trans[off], codes)
        for job in inplace:
            off = job["s"]["off"]
            if off not in FW_ONLY:
                job["payload"] = encode2(trans[off], codes)

    for i, w in enumerate(hook_words(table_ram)):
        struct.pack_into("<I", d, hook_off + i * 4, w)
    jal = 0x0C000000 | ((hook_ram >> 2) & 0x03FFFFFF)
    for site in HOOK_SITES:
        struct.pack_into("<I", d, site - LOAD + HDR, jal)

    # 3) strings
    placed = 0
    for j in sorted(jobs, key=lambda x: -len(x["payload"])):
        page = ((j["ram"] + 0x8000) >> 16) if j["page_lock"] else None
        a = alloc(len(j["payload"]), page)
        if a is None:
            skipped.append((j["s"]["off"], f"no space {len(j['payload'])}B"))
            continue
        d[a:a + len(j["payload"])] = j["payload"]
        new_ram = a - HDR + LOAD
        for ptr in j["s"]["refs"]:
            struct.pack_into("<I", d, ptr, new_ram)
        hi, lo = (new_ram + 0x8000) >> 16, new_ram & 0xFFFF
        for lui_off, use_off in j["crefs"]:
            w = struct.unpack_from("<I", d, lui_off)[0]
            struct.pack_into("<I", d, lui_off, (w & 0xFFFF0000) | hi)
            w2 = struct.unpack_from("<I", d, use_off)[0]
            struct.pack_into("<I", d, use_off, (w2 & 0xFFFF0000) | lo)
        placed += 1

    for job in inplace:
        s, payload, budget = job["s"], job["payload"], job["budget"]
        pad = max(budget, len(payload))
        d[s["off"]:s["off"] + pad] = payload + b"\x00" * (pad - len(payload))
        placed += 1

    # 4) pair glyphs, packed at 28B stride with shared zero rows
    glyph_ram = {}
    todo = list(chunks)
    for r in sorted(regions, key=lambda r: -(r[1] - r[0])):
        if not todo:
            break
        a = (r[0] + 1) // 2 * 2
        n = (r[1] - a - 4) // 28
        if n < 1:
            continue
        n = min(n, len(todo))
        d[a:a + 28 * n + 4] = b"\x00" * (28 * n + 4)
        for k in range(n):
            p = todo.pop(0)
            pay = a + 6 + 28 * k                 # payload = glyph rows 3-13
            d[pay:pay + 22] = pair_glyph(p[0], p[1])[6:28]
            glyph_ram[p] = (pay - 6) - HDR + LOAD
        r[0] = a + 28 * n + 4
    assert not todo, f"glyph pool exhausted: {len(todo)} left ({todo[:5]})"
    blank_ram = blank_off - HDR + LOAD
    code_to_chunk = {c: p for p, c in codes.items()}
    for i in range(NSLOTS):
        p = code_to_chunk.get(idx_to_code(i))
        struct.pack_into("<I", d, table_off + i * 4,
                         glyph_ram.get(p, blank_ram) if p else blank_ram)

    # 5) status screen label alignment: the JP layout draws 3-kanji labels
    # (レベル/魔法力/素早さ) at x=0x1C2 and 2-kanji ones (家系/体力/腕力/知力)
    # at x=0x1C4 -- one half-width char apart. Left-align every label at
    # Level's column (0x1C2) by patching the `ori $a0, $zero, 0x1C4`
    # immediates at the five draw sites.
    LABEL_X_PATCHES = (
        0x62108,   # 家系/Class  (status screen variant 1, RAM 0x80071908)
        0x627B8,   # 家系/Class  (status screen variant 2, RAM 0x80071FB8)
        0x622B0,   # 体力/HP     (RAM 0x80071AB0)
        0x622E8,   # 腕力/STR    (RAM 0x80071AE8)
        0x622FC,   # 知力/INT    (RAM 0x80071AFC)
    )
    for off in LABEL_X_PATCHES:
        w = struct.unpack_from("<I", d, off)[0]
        assert w == 0x340401C4, (
            f"label-x patch @0x{off:X}: expected ori $a0,$zero,0x1C4 "
            f"(0x340401C4), found 0x{w:08X}")
        struct.pack_into("<I", d, off, 0x340401C2)

    open("MAIN.EXE", "wb").write(d)
    left = sum(b - a for a, b in regions)
    print(f"MAIN.EXE: placed {placed} strings, skipped "
          f"{len(skipped)}; hook@0x{hook_ram:08X} table@0x{table_ram:08X} "
          f"glyphs={len(glyph_ram)}; pool left {left}B")
    for off, why in skipped:
        print(f"  skip 0x{off:06X}: {why}")
    json.dump({"codes": {p: c for p, c in codes.items()},
               "hook_ram": hook_ram, "table_ram": table_ram},
              open("fonthack.json", "w"))
    return d


if __name__ == "__main__":
    build_main3()
    bf.build_slps()
