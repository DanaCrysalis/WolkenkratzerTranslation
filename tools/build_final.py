#!/usr/bin/env python3
"""
build_final.py - Build translated MAIN.EXE + SLPS_001.97 from script_traduit.tsv
"""
import json
import re
import struct

LOAD, HDR = 0x80010000, 0x800

# ---------- path resolution (repo layout friendly) ----------
import os
_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("WK_DATA", os.path.join(_HERE, "..", "data"))
SCRIPT_DIR = os.environ.get("WK_SCRIPT", os.path.join(_HERE, "..", "script"))
ORIG_DIR = os.environ.get("WK_ORIG", "test_extracted")


def dpath(*names, dirs=None):
    """Find the first existing candidate among dirs x names ('.' always tried)."""
    dirs = list(dirs or (DATA_DIR, SCRIPT_DIR)) + ["."]
    for n in names:
        for base in dirs:
            p = os.path.join(base, n)
            if os.path.exists(p):
                return p
    raise FileNotFoundError(names[0])


def opath(name):
    return os.path.join(ORIG_DIR, name)


TSV = dpath("script_traduit.tsv")


# ---------- text handling ----------

def fw(s):
    out = []
    for c in s:
        if c in "\x0a":
            out.append(c)
        elif c == " ":
            out.append("\u3000")
        elif c == "'":
            out.append("\u2019")
        elif c == '"':
            out.append("\u201D")
        elif c == "-":
            out.append("\u2212")
        elif c == "~":
            out.append("\u301C")
        elif 0x21 <= ord(c) <= 0x7E:
            out.append(chr(ord(c) + 0xFEE0))
        else:
            out.append(c)
    return "".join(out)


def encode(text):
    """literal \\n in TSV = one 0x0A byte; enforce even 0A runs; FW-convert."""
    raw = text.replace("\\n", "\x0a")
    # make every run of 0A bytes even-length (renderer reads 2-byte tokens)
    def fix(m):
        r = m.group(0)
        return r if len(r) % 2 == 0 else r + "\x0a"
    raw = re.sub(r"\x0a+", fix, raw)
    payload = fw(raw).encode("shift_jis") + b"\x00"
    if len(payload) % 2:
        payload += b"\x00"
    return payload


def wrap_intro(text, width=14):
    """Rewrap intro crawl lines to <=width cells, preserving blank-line pacing."""
    raw = text.replace("\\n", "\x0a")
    parts = re.split(r"(\x0a+)", raw)
    out = []
    for p in parts:
        if not p:
            continue
        if p[0] == "\x0a":
            out.append(p)
            continue
        line = p.strip()
        if not line:
            continue
        words, cur = line.split(), ""
        wrapped = []
        for w in words:
            cand = (cur + " " + w).strip()
            if len(cand) <= width:
                cur = cand
            else:
                if cur:
                    wrapped.append(cur)
                cur = w
        if cur:
            wrapped.append(cur)
        out.append("\x0a\x0a".join(wrapped))
    return "".join(out).replace("\x0a", "\\n")


# ---------- load and clean the fan translation ----------

FIXES = [
    (r"\s*\(wildy adapted\)", ""),
    (r"\s*\(sp\?[^)]*\)", ""),
    (r"\s*\(this reads phonetically[^)]*\)", ""),
    (r"\s*\(\?\?\?\?\)", ""),
    (r"\s*\(same\)", ""),
    (r"\s*\(in front of it\)", ""),
    (r"D\(ragon\?\)fly", "D-Fly"),
    (r"[Dd]\(ragon\) [Ff]ly", "D-Fly"),
    (r"[Dd]\(ragon\) [Aa]ttack", "D-Attack"),
    (r"E\(lec\) [Ss]word", "E-Sword"),
    (r"I\(ce\) [Ss]word", "I-Sword"),
    (r"F\(lare\) [Ss]word", "F-Sword"),
    (r"\(galblaze\)", "Galblaze"),
    (r"\(mana/magical energy\)", "magic energy"),
    (r"Etc\. \(Other\)", "Other:"),
    (r"Left \(Next\)", "Left"),
    (r"fulll", "full"),
    (r"t hen demand", "then demand"),
    (r"everexpending", "ever-expanding"),
    (r"Datas", "Data"),
]

# id -> replacement (menu/box width constraints proven by screenshots)
OVERRIDES = {
    61: "Next", 62: "Sleep", 63: "Seek", 64: "Cmds", 65: "Items",
    66: "Stats", 67: "Flee", 68: "Open", 69: "Check", 70: "Tower",
    71: "Inn", 72: "Save", 73: "Town", 74: "Talk", 75: " Items",
    144: "Trouble", 145: "Found!", 146: "Seeking",
    158: "MAX", 159: "Slowly",
    457: "Please split\\nthe bonus", 458: "points left.",
    # letter grid rows: exactly 5 chars per row (cell index = char index)
    418: "ABCDE", 419: "FGHIJ", 420: "KLMNO", 421: "PQRST", 422: "UVWXY",
    423: "Z    ",
    435: "abcde", 436: "fghij", 437: "klmno", 438: "pqrst", 439: "uvwxy",
    440: "z    ",
}
SKIP_IDS = {174, 175, 176}

TRIMS = {
    195: "Wild thrusts chains many high, middle and low thrusts in quick succession.",
    202: "Not sure the jump counts as a technique, but it exists. Guess what it's about.",
    235: "Coat a shield with mirror powder and you won't have to worry about poison anymore.",
    261: "Smart guys get more out of magic, see.",
    279: "Some drunkard at the bar was whining about being suddenly thrown out of the tower!",
    289: "I am Mahanole. If war is your trade, you may not gain much from addressing me.",
    299: "Two healing magics exist: heal and high heal. But high heal is no easy feat to learn.",
}

# supplemental kanji-only labels (keyed by file offset)
SUPPLEMENT = {
    0x002298: " Psn ", 0x0022A0: "OK ",
    0x005F84: "Info", 0x005FB4: "Setup", 0x005FBC: "List",
    0x005FE8: "  Magic", 0x005FF4: "  Skills",
    0x006120: "DEF", 0x006128: "ATK", 0x006138: "INT", 0x006140: "STR",
    0x006148: "MP", 0x006150: "HP",
    0x006164: " Psn ", 0x006170: " OK ",
    0x006184: "Shield: ", 0x0061A4: "Armor:  ", 0x0061C4: "Weapon: ",
    0x006634: "Name:", 0x006644: "DP:", 0x00664C: "AP:", 0x006668: "Bonus:",
    0x0068C8: "Knight", 0x0068E0: "Fighter",
    0x007044: " Fl  Time   Gate", 0x00706C: "       dy hr",
    0x007F6C: "   dy  hr", 0x007F80: "HP:",
    0x0F915C: "Great medicine", 0x0F916C: "Magic potion",
    0x0F917C: "Great poison", 0x0F919C: "Poison", 0x0F91AC: "Antidote",
    0x0F91EC: "Atk. up powder", 0x0F91FC: "Def. up powder",
    0x0F9814: "Family", 0x0F9868: "   dy",
    0x0FEFE4: "    mo dy",
    0x0FF04C: " HP", 0x0FF054: " MP", 0x0FF05C: "STR", 0x0FF064: "INT",
    0x0FF074: "Name", 0x0FF07C: "Sex", 0x0FF088: " Family",
    0x0FF094: " Sex", 0x0FF0A0: " Male", 0x0FF0AC: "Female",
}


def load_translations():
    trans = {}   # offset -> english
    rows = open(TSV, encoding="utf-8").read().splitlines()
    for line in rows[1:]:
        cols = line.split("\t")
        if len(cols) < 6:
            continue
        sid = int(cols[0])
        off = int(cols[1], 16)
        en = cols[5].strip()
        if sid in SKIP_IDS or not en:
            continue
        if sid in TRIMS:
            en = TRIMS[sid]
        elif sid in OVERRIDES:
            en = OVERRIDES[sid]
        else:
            for pat, rep in FIXES:
                en = re.sub(pat, rep, en)
            en = en.strip()
        if not en:
            continue
        if sid == 0:
            en = wrap_intro(en)
        trans[off] = en
    for off, en in SUPPLEMENT.items():
        trans.setdefault(off, en)
    return trans


# ---------- build ----------

def build_main():
    d = bytearray(open(opath("MAIN.EXE.bak"), "rb").read())
    strings = json.load(open(dpath("MAIN_script2.json", "MAIN.script2.json")))
    strings.sort(key=lambda s: s["off"])
    coderefs = {int(k, 16): v for k, v in
                json.load(open(dpath("MAIN_code_refs2.json", "MAIN.code_refs2.json"))).items()}
    freespace = json.load(open(dpath("MAIN_freespace.json", "MAIN.freespace.json")))
    trans = load_translations()

    bymap = {s["off"]: s for s in strings}

    # unaligned pointer rescan for strings believed unreferenced (id 261 case)
    for off, s in bymap.items():
        if off in trans and not s["refs"] and \
           not coderefs.get(off - HDR + LOAD):
            needle = struct.pack("<I", off - HDR + LOAD)
            p = d.find(needle)
            while p != -1:
                s["refs"].append(p)
                p = d.find(needle, p + 1)
            if s["refs"]:
                print(f"unaligned/odd ptr found for 0x{off:06X}: "
                      f"{[hex(x) for x in s['refs']]}")

    jobs, inplace, skipped = [], [], []
    for off, en in sorted(trans.items()):
        s = bymap.get(off)
        if not s:
            skipped.append((off, "not in string map"))
            continue
        ram = off - HDR + LOAD
        crefs = coderefs.get(ram, [])
        payload = encode(en)
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
    lui_owner = {}
    shared_luis = set()
    for ram, prs in coderefs.items():
        for l, _ in prs:
            if l in lui_owner and lui_owner[l] != ram:
                shared_luis.add(l)
            lui_owner[l] = ram
    for j in jobs:
        j["page_lock"] = any(l in shared_luis for l, _ in j["crefs"])

    # allocation pool
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
    merged = []
    for a, b in pool:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    regions = merged

    def alloc(size, page=None):
        best = None
        for r in regions:
            a = r[0] + (r[0] % 2)
            if r[1] - a < size:
                continue
            if page is not None and ((a - HDR + LOAD) + 0x8000) >> 16 != page:
                continue
            if best is None or (best[1] - best[0]) > (r[1] - r[0]):
                best = r
        if best is None:
            return None
        a = best[0] + (best[0] % 2)
        best[0] = a + size
        return a

    placed = 0
    for j in sorted(jobs, key=lambda x: -len(x["payload"])):
        page = ((j["ram"] + 0x8000) >> 16) if j["page_lock"] else None
        a = alloc(len(j["payload"]), page)
        if a is None:
            skipped.append((j["s"]["off"], f"no space {len(j['payload'])}B"))
            continue
        d[a:a + len(j["payload"])] = j["payload"]
        new_ram = a - HDR + LOAD
        for p in j["s"]["refs"]:
            struct.pack_into("<I", d, p, new_ram)
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

    open("MAIN.EXE", "wb").write(d)
    print(f"MAIN.EXE: placed {placed}, skipped {len(skipped)}")
    for off, why in skipped:
        print(f"  skip 0x{off:06X}: {why}")
    return d, bymap, trans


SLPS_INTRO = """\\n\\n\\n\\n\\n\\nFrom the words\\nof the prophet:\\n\\n\u201CYou humans\\nshall wander\\nwhen the\\nworld\u2019s balance\\nis thrown like\\ngravel by the\\nwind. Then\\nshall our Lord\\nsubmit you to\\nan ordeal.\\n\\nAll that came\\nfrom the tower\\nshall return\\nto it.\\n\\nStrength? Defy\\nit. Wits?\\nQuestion it.\\nAmbition?\\nDemand of it.\\n\\nBefore the one\\nwho seizes the\\nWolkenkratzer,\\nour Lord shall\\nreveal\\nHimself.\u201D"""


def build_slps():
    d = bytearray(open(opath("SLPS_001.97.bak"), "rb").read())
    off = 0x878
    end = d.index(0, off)
    budget = end - off + 1
    payload = encode(SLPS_INTRO)
    print(f"SLPS intro: {len(payload)}/{budget} bytes")
    assert len(payload) <= budget
    d[off:off + budget] = payload + b"\x00" * (budget - len(payload))
    open("SLPS_001.97", "wb").write(d)


if __name__ == "__main__":
    build_main()
    build_slps()
