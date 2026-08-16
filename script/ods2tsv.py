#!/usr/bin/env python3
"""
ods2tsv.py - convert the translator's spreadsheet into the TSV the builder reads.

script_traduit.ods is the human-facing source of truth; script_traduit.tsv is the
machine-facing one. Run this after every spreadsheet edit (build.sh does it for
you). Columns: id, offset, bytes, ref_type, japanese, english.

Cell text is flattened with LibreOffice's <text:s c="n"> run-length spaces and
<text:line-break> expanded; a literal backslash-n in a cell stays a literal
backslash-n (the builder turns it into one 0x0A byte).

  python3 ods2tsv.py [in.ods] [out.tsv]

Needs: pip install odfpy
"""
import os
import sys

from odf.opendocument import load
from odf.table import Table, TableRow
from odf.text import P

HERE = os.path.dirname(os.path.abspath(__file__))


def celltext(cell):
    parts = []

    def walk(node):
        for k in node.childNodes:
            if k.nodeType == 3:                       # text node
                parts.append(k.data)
            elif k.qname[1] == "s":                   # <text:s c="n">
                parts.append(" " * int(k.getAttribute("c") or 1))
            elif k.qname[1] == "line-break":
                parts.append("\\n")
            else:
                walk(k)

    for p in cell.getElementsByType(P):
        walk(p)
        parts.append("\n")
    return "".join(parts).rstrip("\n")


def convert(src, dst):
    doc = load(src)
    table = doc.spreadsheet.getElementsByType(Table)[0]
    rows = []
    for r in table.getElementsByType(TableRow):
        cells = []
        for c in r.childNodes:
            if c.qname[1] != "table-cell":
                continue
            rep = int(c.getAttribute("numbercolumnsrepeated") or 1)
            v = celltext(c)
            cells.extend([v] * min(rep, 50))          # cap runaway repeats
        while cells and cells[-1] == "":
            cells.pop()
        if cells:
            rows.append(cells)
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write("\n".join("\t".join(r) for r in rows) + "\n")
    data = [r for r in rows[1:] if r and r[0].isdigit()]
    print(f"{os.path.basename(dst)}: {len(data)} translation rows")
    return rows


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "script_traduit.ods")
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "script_traduit.tsv")
    convert(src, dst)
