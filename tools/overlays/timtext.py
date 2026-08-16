"""timtext.py - render English text onto the WE ending overlays.

TARGETS THE PATCHED (REPOINTED) DISPLAY MODEL
---------------------------------------------
The ending overlay EXEs were patched to repoint how the WE_*.TIM textures are
read, which bought two things:

  * a uniform 16-band grid (band n centred at y = 8 + 16n) on EVERY file,
    replacing the JP originals' irregular pacing (WE_5F0 JP had only 11 bands
    with 23/24/25/32px pacing gaps);
  * a display window widened to effectively the full 256px texture, replacing
    the JP window of x=16..240 (~214px usable). Measured English lines run
    x4..250 (247px wide), which the unpatched window would have clipped.

Consequence: vertical side-column strips are NO LONGER USED. In the JP art a
group could be parked in an outer column and rotated back to horizontal on its
own sequence step (WE_5F0 right, WE_5F1 both, WE_FF1 left). Under the patch
every group is simply another horizontal line. `draw_vstrip` is retained only
for regenerating unpatched/legacy output.

Style matches the JP CLUT ramp: white core (15) + light anti-alias (1) +
dark outline (13); index 0 = transparent. Rendering is DejaVu Sans Bold,
4x supersampled then LANCZOS-downsampled into a 3-level quantiser.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_dilation

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
S = 4                                   # supersample factor
BODY, AA, OUTLINE, CLEAR = 15, 1, 13, 0

# --- patched display geometry ---
N_BANDS, GRID_Y0, GRID_DY = 16, 8, 16   # band n centre = GRID_Y0 + GRID_DY*n
CX, MAXW = 128, 248                     # full-width window after the repoint
FS_START, FS_FLOOR = 12, 7              # auto-shrink range for long lines

# --- unpatched geometry, kept for legacy regeneration ---
LEGACY_MAXW = 214                       # old x16..240 window


def band_y(n):
    """Centre y of band n on the patched uniform grid."""
    return GRID_Y0 + GRID_DY * n


# ---------------- rasterisation ----------------

def text_cov(text, fs, pad=3):
    """Greyscale coverage field (0..1) for `text` at font size `fs`."""
    f = ImageFont.truetype(FONT, fs * S)
    probe = ImageDraw.Draw(Image.new("L", (4, 4)))
    tw = max(1, int(probe.textlength(text, font=f)))
    img = Image.new("L", (tw + pad * 2 * S, (fs + pad * 2) * S), 0)
    ImageDraw.Draw(img).text((pad * S, pad * S), text, fill=255, font=f)
    small = img.resize((max(1, img.width // S), max(1, img.height // S)),
                       Image.LANCZOS)
    return np.asarray(small).astype(np.float32) / 255.0


def _mask3(cov):
    """Split a coverage field into body / anti-alias / outline-ring masks."""
    body = cov >= 0.30
    aa = (cov >= 0.14) & ~body
    ring = binary_dilation(body | aa) & ~(body | aa)
    return body, aa, ring


def fit_size(text, maxw, start=FS_START, floor=FS_FLOOR):
    """Largest font size in [floor, start] whose rendered width fits maxw."""
    fs = start
    while fs > floor and text_cov(text, fs).shape[1] > maxw:
        fs -= 1
    return fs


def _blit(a, body, aa, ring, x0, y0):
    H, W = a.shape
    h, w = body.shape
    for yy in range(h):
        Y = y0 + yy
        if not (0 <= Y < H):
            continue
        for xx in range(w):
            X = x0 + xx
            if not (0 <= X < W):
                continue
            if body[yy, xx]:
                a[Y, X] = BODY
            elif aa[yy, xx]:
                a[Y, X] = AA
            elif ring[yy, xx]:
                a[Y, X] = OUTLINE


# ---------------- public drawing ----------------

def clear_text(a):
    """Erase all JP pixels to transparent. CLUT and headers are preserved by
    the codec, so the palette fade animation still works on the new pixels."""
    a[:] = CLEAR
    return a


def draw_hline(a, text, cy, cx=CX, maxw=MAXW, start=FS_START):
    """Draw one horizontal line centred at (cx, cy), auto-shrinking to fit.
    Returns (font_size, rendered_width)."""
    if not text:
        return None
    fs = fit_size(text, maxw, start)
    cov = text_cov(text, fs)
    body, aa, ring = _mask3(cov)
    h, w = cov.shape
    _blit(a, body, aa, ring, int(round(cx - w / 2)), int(round(cy - h / 2)))
    return fs, w


def draw_band(a, text, n, **kw):
    """Draw `text` into band n of the patched 16-band grid."""
    return draw_hline(a, text, band_y(n), **kw)


def draw_vstrip(a, text, x_center, y0, y1, start=FS_START):
    """LEGACY (unpatched only): render text rotated 90 deg CCW into an outer
    column. Unused under the repointed model - kept for regenerating old art."""
    if not text:
        return None
    cov = text_cov(text, fit_size(text, y1 - y0, start))
    cov = np.rot90(cov, 1)
    body, aa, ring = _mask3(cov)
    h, w = cov.shape
    _blit(a, body, aa, ring,
          int(round(x_center - w / 2)), int(round((y0 + y1) / 2 - h / 2)))
    return True
