#!/usr/bin/env python3
"""
sjis_scan.py - Hunt for Shift-JIS Japanese text in PS1 game files.

Usage:
    python sjis_scan.py FILE [FILE ...]        scan specific files
    python sjis_scan.py -d extracted/          scan every file in a folder
    python sjis_scan.py -m 6 FILE              require at least 6 JP chars per hit
    python sjis_scan.py -o dump.txt FILE       write results to a file (UTF-8)

Output lines look like:
    FILE.DAT @ 0x0001A4C0 : こんにちは勇者よ

The offset is where the string starts, which you'll need later for
pointer hunting and reinsertion.
"""

import argparse
import os
import sys

REQUIRE_KANA = True


def is_sjis_lead(b):
    """First byte of a two-byte Shift-JIS sequence."""
    return (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xEF)


def is_sjis_trail(b):
    """Second byte of a two-byte Shift-JIS sequence."""
    return (0x40 <= b <= 0x7E) or (0x80 <= b <= 0xFC)


def is_halfwidth_katakana(b):
    return 0xA1 <= b <= 0xDF


def decodable(pair):
    """Check the two-byte pair actually decodes to a Japanese-ish char."""
    try:
        ch = pair.decode("shift_jis")
    except UnicodeDecodeError:
        return None
    cp = ord(ch)
    # Accept: hiragana, katakana, CJK ideographs, JP punctuation/symbols,
    # full-width Latin/digits (games use these for stats, item names, etc.)
    if (0x3040 <= cp <= 0x30FF      # kana
            or 0x4E00 <= cp <= 0x9FFF   # kanji
            or 0x3000 <= cp <= 0x303F   # JP punctuation
            or 0xFF00 <= cp <= 0xFFEF): # full-width forms
        return ch
    return None


def scan_file(path, min_chars, include_hw_kana):
    data = open(path, "rb").read()
    results = []
    i = 0
    n = len(data)
    while i < n - 1:
        b = data[i]
        if is_sjis_lead(b) and is_sjis_trail(data[i + 1]):
            # Try to grow a run of valid Japanese two-byte chars
            start = i
            chars = []
            j = i
            while j < n - 1:
                bj = data[j]
                if is_sjis_lead(bj) and is_sjis_trail(data[j + 1]):
                    ch = decodable(data[j:j + 2])
                    if ch is None:
                        break
                    chars.append(ch)
                    j += 2
                elif include_hw_kana and is_halfwidth_katakana(bj):
                    chars.append(bytes([bj]).decode("shift_jis"))
                    j += 1
                elif 0x20 <= bj <= 0x7E:
                    # ASCII mixed into the string (numbers, codes) - allow
                    # short runs inside a Japanese string, but don't let
                    # pure ASCII start or dominate a match.
                    if chars:
                        chars.append(chr(bj))
                        j += 1
                    else:
                        break
                else:
                    break
            # Trim trailing ASCII noise
            while chars and ord(chars[-1]) < 0x80:
                chars.pop()
                j -= 1
            jp_count = sum(1 for c in chars if ord(c) > 0xFF)
            has_kana = any(0x3040 <= ord(c) <= 0x30FF for c in chars)
            if jp_count >= min_chars and (has_kana or not REQUIRE_KANA):
                results.append((start, "".join(chars)))
                i = j
                continue
        i += 1
    return results


def main():
    ap = argparse.ArgumentParser(description="Scan files for Shift-JIS Japanese text")
    ap.add_argument("paths", nargs="*", help="files to scan")
    ap.add_argument("-d", "--dir", help="scan all files under this directory")
    ap.add_argument("-m", "--min-chars", type=int, default=4,
                    help="minimum Japanese characters per hit (default 4)")
    ap.add_argument("-o", "--out", help="write results to this file (UTF-8)")
    ap.add_argument("--hw-kana", action="store_true",
                    help="also accept half-width katakana (more hits, more noise)")
    ap.add_argument("--no-kana-filter", action="store_true",
                    help="keep strings with no kana (pure-kanji menu labels, but noisier)")
    args = ap.parse_args()
    global REQUIRE_KANA
    REQUIRE_KANA = not args.no_kana_filter

    targets = list(args.paths)
    if args.dir:
        for root, _, files in os.walk(args.dir):
            for f in sorted(files):
                targets.append(os.path.join(root, f))
    if not targets:
        ap.error("give me files or -d DIRECTORY")

    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    total = 0
    per_file = {}
    for path in targets:
        if not os.path.isfile(path):
            continue
        hits = scan_file(path, args.min_chars, args.hw_kana)
        per_file[path] = len(hits)
        for off, text in hits:
            out.write(f"{path} @ 0x{off:08X} : {text}\n")
        total += len(hits)

    print(f"\n--- summary ---", file=sys.stderr)
    for path, count in sorted(per_file.items(), key=lambda kv: -kv[1]):
        if count:
            print(f"{count:6d} strings  {path}", file=sys.stderr)
    print(f"{total} strings total", file=sys.stderr)
    if args.out:
        out.close()


if __name__ == "__main__":
    main()
