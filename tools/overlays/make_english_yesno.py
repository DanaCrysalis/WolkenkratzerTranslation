"""make_english_yesno.py - English YESNO.TIM (choice prompt).

The texture holds TWO copies of the prompt: a bar-less copy at y2..15 and a
copy on the blue bar at y16..31, plus cursor triangles further down and to the
right. The cursor is positioned by CODE, not art, so "Yes"/"No" must be centred
exactly where the JP words were, or the highlight lands off the word.

Word centres (measured from the shipped English build):
    top copy : Yes cx=21   No cx=72
    bar copy : Yes cx=48   No cx=103

Index roles: 0 transparent, 1 anti-alias, 2 outline, 3 bar fill, 4 text core.
Only the text pixels are touched; bar and cursor art are asserted unchanged.
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_dilation
import timcodec

SRC = "orig/YESNO.TIM"
OUT = "/mnt/user-data/outputs/english_overlays"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
S = 4
CORE, AA, OUTLINE, BARFILL, CLEAR = 4, 1, 2, 3, 0

# (y0, y1, background fill, erase_x1, [(text, cx, cy)])
# erase_x1 is where erasing stops: the TOP copy has a cursor triangle at
# x>=113 that must survive; the BAR copy has no cursor, so it erases wider to
# clear the tail of the JP kana that sits past "No".
REGIONS = [
    (2,  16, CLEAR,   113, [("Yes", 21, 8),  ("No", 72, 8)]),
    (16, 32, BARFILL, 132, [("Yes", 48, 23), ("No", 103, 23)]),
]


def text_cov(text, fs, pad=3):
    f = ImageFont.truetype(FONT, fs * S)
    probe = ImageDraw.Draw(Image.new("L", (4, 4)))
    tw = max(1, int(probe.textlength(text, font=f)))
    img = Image.new("L", (tw + pad * 2 * S, (fs + pad * 2) * S), 0)
    ImageDraw.Draw(img).text((pad * S, pad * S), text, fill=255, font=f)
    small = img.resize((img.width // S, img.height // S), Image.LANCZOS)
    return np.asarray(small).astype(np.float32) / 255.0


def stamp(a, text, cx, cy, fs=11):
    cov = text_cov(text, fs)
    body = cov >= 0.30
    aa = (cov >= 0.14) & ~body
    ring = binary_dilation(body | aa) & ~(body | aa)
    h, w = cov.shape
    x0, y0 = int(round(cx - w / 2)), int(round(cy - h / 2))
    for yy in range(h):
        for xx in range(w):
            X, Y = x0 + xx, y0 + yy
            if not (0 <= X < 256 and 0 <= Y < 256):
                continue
            if body[yy, xx]:
                a[Y, X] = CORE
            elif aa[yy, xx]:
                a[Y, X] = AA
            elif ring[yy, xx]:
                a[Y, X] = OUTLINE


def main():
    m = timcodec.decode(SRC)
    a = np.array(m["idx"], dtype=np.uint8).reshape(256, 256)
    orig = a.copy()

    for y0, y1, fill, ex1, words in REGIONS:
        sub = a[y0:y1, 0:ex1]
        sub[np.isin(sub, [CORE, AA, OUTLINE])] = fill
        for text, cx, cy in words:
            stamp(a, text, cx, cy)

    # nothing outside the two text rects may change (protects bar + cursors)
    delta = (a != orig)
    for y0, y1, _f, ex1, _w in REGIONS:
        delta[y0:y1, 0:ex1] = False
    assert delta.sum() == 0, f"stray edits: {delta.sum()}"

    data = timcodec.encode(m, a.flatten())
    os.makedirs(OUT, exist_ok=True)
    open(f"{OUT}/YESNO.TIM", "wb").write(data)

    raw = open(SRC, "rb").read()
    hdr = 8 + m["clen"]
    print(f"YESNO.TIM: size_ok={len(data) == len(raw)} "
          f"clut/coords_preserved={data[:hdr] == raw[:hdr]} stray_edits=0")


if __name__ == "__main__":
    main()
