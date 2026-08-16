# WOLKENKRATZER (SLPS-00197) English Translation — Project Knowledge

Complete, self-contained reference for the fan-translation of the PS1 JRPG
**Wolkenkratzer: Shinpan no Tou** (1996, Asmik/Westone roguelite RPG).
A fresh conversation with this file plus the listed project files can continue
the work without re-deriving anything.

The project has **two independent tracks**:
- **Track A** — the MAIN.EXE / SLPS_001.97 text hack (custom half-width font).
- **Track B** — the TIM image-text overlays (endings, credits, UI).

Assets touched: MAIN.EXE, SLPS_001.97, END/ROLL/OMAKE overlays, and TIM images.

────────────────────────────────────────────────────────────────────────
## 0. ENVIRONMENT / REPOSITORY LAYOUT

The project now lives in a **git repository** (`wolkenkratzer-en/`) rather than
loose files. Everything below is relative to the repo root.

```
build.sh          one-shot pipeline (ODS -> TSV -> build -> patch -> verify)
script/           script_traduit.ods (source of truth), .tsv (generated), ods2tsv.py
tools/            build_final.py, build_final3.py, pixfont.py,
                  patch_levelup.py, patch_dayhour_ui.py, verify_build.py,
                  sjis_scan.py, overlays/{timcodec.py, make_english_ui.py}
data/             MAIN_script2.json, MAIN_code_refs2.json, MAIN_freespace.json,
                  fonthack.json
docs/             this file
orig/             PRISTINE Japanese originals -- user-supplied, gitignored
build/            outputs -- gitignored
```

- **Pristine originals (NEVER overwrite):** `orig/MAIN.EXE.bak` (1085440 B) and
  `orig/SLPS_001.97.bak` (333824 B). A build must start from these exact bytes.
  **NOTE:** plain `MAIN.EXE` / `SLPS_001.97` files are already-built copies,
  **NOT pristine** — do not seed a build from them. If in doubt, check
  `struct.unpack_from("<I", d, 0x62108)` — pristine reads `0x340401C4`, a built
  binary reads `0x340401C2`; a built binary also has the four rasteriser JALs
  pointing at `0x800D1F68`.
- Path resolution: `build_final.py` exposes `dpath()` / `opath()`, overridable
  with the env vars **`WK_DATA`**, **`WK_SCRIPT`**, **`WK_ORIG`** (build.sh sets
  all three). This is what lets the tools live in `tools/` while the data lives
  in `data/`.
- In a container session: copy the repo to a writable dir, drop the two pristine
  originals into `orig/`, `pip install odfpy --break-system-packages`, run
  `./build.sh`. Deliverables go to `/mnt/user-data/outputs/` then
  `present_files`. Other packages used across the project: `capstone` (MIPS
  disasm), `pillow`, `numpy`, `scipy` (Track B only).
- **The build is deterministic.** Reference build from `script_traduit.ods` as
  of 2026-08-16: `MAIN.EXE` md5 `4c2605e3e1a2d58f59d55e45dab40b09`,
  `SLPS_001.97` md5 `97781c0e7602fbbbc178eff81358fa76`.

### Disc workflow (user side)
- Extract: `dumpsxiso "game.bin" -x extracted -s rebuild.xml`
  (older notes used `mkpsxiso`/`dumpsxiso`; either toolchain is fine).
- Claude patches files in the container and outputs `MAIN.EXE` (and, when
  needed, `SLPS_001.97` and/or TIM overlays).
- User drops them into `extracted/`, rebuilds (`mkpsxiso rebuild.xml`), tests
  in an emulator, and reports back with screenshots.
- To view translated TIMs, they must be placed back in the disc image and the
  disc mounted; overlays can be direct-booted (see Track B).

────────────────────────────────────────────────────────────────────────
# TRACK A — MAIN.EXE / SLPS TEXT HACK  (stable, shipping)

## A.1 Build

```
./build.sh          # ODS -> TSV -> build_final3 -> patch_levelup -> patch_dayhour_ui -> verify
```
Stage 2 alone (no post-build patches, no ODS conversion):
```
WK_DATA=$PWD/data WK_SCRIPT=$PWD/script WK_ORIG=$PWD/orig \
  sh -c 'cd build && python3 ../tools/build_final3.py'
```
`build_final3.py` imports `build_final.py` (the base engine) and mutates its
config. A good build prints something like:

```
placed 485 strings, skipped 0; hook@0x800D1F68 table@0x801076D0
glyphs≈606; pool ~2.4KB left
SLPS intro: 704/877
```

**Constants:** `HDR=0x800`, `LOAD=0x80010000`, so
`file_off = ram − LOAD + HDR` and **`RAM = 0x80010000 + (file_off − 0x800)`**.
Output sizes **MUST match originals**: MAIN = **1085440**, SLPS = **333824**.
Exe image ends at RAM **0x80118800** (BSS follows — do not extend past it).

## A.2 Text system

- Both executables are PS-X EXEs (load 0x80010000, 0x800-byte header). All text
  is **uncompressed Shift-JIS**.
- The translatable corpus: **462 TSV strings + ~40 kanji-only labels**
  ("SUPPLEMENT", found later). The intro also exists as a **second copy** in
  SLPS_001.97 at file offset 0x878 (877-byte budget, edited in place).
- **Reference types** (how the game finds each string):
  - most strings have one or more **32-bit data pointers** (`refs`);
  - **19 use lui/addiu code refs** (patch hi/lo halves). Beware **shared-lui
    pages**: if two strings share one `lui`, the relocation must stay in the
    same 64K page ("page_lock");
  - a few are referenced by nothing findable → they **must fit in place**.
- The renderer consumes strict **2-byte tokens**: text must be full-width SJIS
  or our pair codes. **Newlines are `0x0A 0x0A` pairs** — a lone `0x0A` breaks
  token alignment, so runs of `0x0A` are forced to even length.
- `ＸＸ` placeholders (SJIS `0x82 0x77` ×2) are substituted at runtime with stat
  values. They must stay literal full-width Ｘ runs — **never pair-encode
  `X{2,}`**.
- **Name-entry grid rows** map grid-cell index = character index, so they must
  stay **one full-width char per cell** (offsets 0xFED3C–0xFED78,
  0xFEE4C–0xFEE88; TSV ids 418–423 / 435–440, kept as 5 packed chars/row).

## A.3 Rendering pipeline (fully reverse-engineered)

- **There is no font in any disc file** — the game reads glyphs from the
  **PlayStation BIOS kanji ROM** via kernel function **B(0x51)
  Krom2RawAdd(sjis_code)**, through a stub at RAM **0x80098140**
  (`li t2,0xB0; jr t2; li t1,0x51`). It returns a pointer to a **32-byte glyph**
  (16 rows × 2 bytes big-endian, bit15 = leftmost pixel), or −1 if unmapped.
- **Glyph rasterizer** at 0x80034904 (file 0x25104): `a0`=string ptr,
  `a1`=out buf. Builds `code=(b1<<8)|b2`, calls the stub, then per row applies
  **bold: `row |= row>>1`**, and writes a 4bpp 16×16 cell (128 bytes):
  ink nibble = 0xF, background = 0x2. Unmapped code fills 0x22.
- **Exactly 4 JAL sites** call the stub — **0x800347A8, 0x800347E4,
  0x8003492C, 0x80034A6C** — all with identical setup
  (`lbu/lbu/sll 8 / jal / or a0,a0,v0` in the delay slot). Hooking these 4
  covers every text path (two rasterizer variants).
- **Print function** 0x80036360 (file 0x26B60): `a0`=x (VRAM words),
  `a1`=y, `a2`=str ptr. Loops: rasterize glyph → LoadImage a 4-words×16-rows
  rect to VRAM → advance string +2, x +4 words (16px). Sibling entry
  0x800362C8. **1 x-unit = 4px; rows step y by 0x10.** Bold is also
  double-struck at prim level (each glyph drawn at x and x+1).
- VRAM sheets stream per frame into pages (320,256) and (384,256) (4bpp, CLUTs
  at (0,496)/(64,496)), alternating per frame. Labels rasterize into
  **fixed-width slots sized for the original JP string**; the sprite draws the
  whole slot (→ the padding rules in A.6).

## A.4 The font hack (implemented, working)

Goal achieved: **8px-per-character English** with zero changes to advance,
wrapping, or prim logic.

- **Hook:** the 4 JALs redirect to a 21-instruction stub (84 B) in free exe
  space. Codes with lead byte **0xF0–0xF4** and trail **0x80–0xFB** (5×124 =
  620 slots) index a pointer table; anything else tail-jumps to the BIOS stub.
  `idx = (lead−0xF0)*124 + (trail−0x80)`; `idx_to_code = ((0xF0+i//124)<<8) |
  (0x80 + i%124)`.
- **Pair glyphs:** each custom code renders **two letters in one 16px cell**
  (letters ~5px wide; m/w/M/W 7px). Char A at col ~1, char B at col ~9. Drawn
  at 1px strokes; the engine's `row|row>>1` bold makes them 2px, so the font is
  **bold-aware** — strokes that must stay separate need a **≥2px pre-bold gap**
  (1px gaps get filled). `pixfont.py` holds the font; `pair_glyph(a,b)` returns
  the 32-byte bitmap. Glyphs are **5px wide × 9 rows**; descenders g/j/p/q/y
  reach row 9. Fixed special glyphs: `'W'` (baseline tweak), `':'` (fat).
- **Storage:** pointer table = 620×4 B contiguous. Glyphs pack at a **28-byte
  stride**: rows 0–2 and 14–15 are always blank, so each table pointer aims 6
  bytes before its 22-byte payload and neighbours share the zero gaps (a run of
  n glyphs = 28n+4 bytes). This recovered ~2.3 KB and lets **all glyphs have a
  bitmap — zero fallbacks**.
- **Encoder (`encode2` in build_final3.py):** printable-ASCII runs are chunked
  into 2-char pairs (odd tail padded with a trailing space) and emitted as pair
  codes; `X{2,}` runs and non-ASCII stay full-width; `0x0A` runs kept even.
  Curly quotes `’ ‘ “ ”` are normalized to ASCII `'` and `"` first (else they
  break ASCII runs and render as fat full-width cells).
- **Chunk priority:** chunks in any string ≤30 chars (UI labels) are protected
  first, then by frequency. Capacity is computed by simulating string placement
  on a pool copy, then glyphs pack the leftovers. All fit with ~2 KB spare.
- **SLPS_001.97 has no hook** — its intro stays full-width (a condensed version
  fitting the 877-byte budget, rebuilt by `bf.build_slps()`).

## A.5 The spreadsheet is authoritative

`script/script_traduit.ods` is the **human-facing source of truth**;
`script/ods2tsv.py` flattens it to `script/script_traduit.tsv`, which is what the
builder actually reads. Re-run the converter (or just `./build.sh`) after every
spreadsheet edit. The converter expands LibreOffice `<text:s c="n">` run-length
spaces and `<text:line-break>`, and leaves a literal backslash-n as a literal
backslash-n. Current sheet: **462 translation rows**.

`script_traduit.tsv` is the **sole source of translatable strings** for the
build. Columns:
`id, offset, bytes, ref_type, japanese, english`. `offset` = file offset in
MAIN.EXE; `bytes` = original record length; literal `\n` in text = one `0x0A`.

- In `build_final3.py`, **`bf.OVERRIDES.clear()`** removes ALL id-based
  overrides — item/menu names now come from the TSV. Item field width = 14.
- Base `build_final.py` still has **structural OVERRIDES that SHADOW the TSV**
  (these are **layout requirements, not translations**): menu cmds 61–75,
  MAX/Slowly 158/159, bonus prompt 457/458, and the name-entry letter grids
  418–423 / 435–440 (must stay 5 packed chars/row — cell index = char index).

## A.6 Text layout rules (all learned from in-game bugs)

- **Word wrap** (`wrap_words`, `WRAP_COLS=28`): every non-FW string is
  pre-wrapped at word boundaries to ≤28 half-char columns (14 cells). The
  dialogue box is 15 cells wide and the engine force-splits when a line
  *reaches* 15 cells; wrapping at 15 causes double breaks — hence 14.
- **Slot padding** (`apply_slot_padding`): every short single-line label
  (original ≤10 cells) is space-padded to its **original JP cell width**.
  Reason: label sprites draw the original fixed slot; shorter text exposes stale
  VRAM texels that look like small bordered squares. Fixed offenders: HP/MP/STR/
  INT/OK/Psn/Sex/Male/Female/Knight/Fighter/creation-form columns.
- **Field-group padding** (`apply_field_padding`): strings cycling in the same
  screen field are padded to a uniform group width so shorter entries fully
  overwrite longer ones (the box doesn't repaint): techniques (305–322 → 18),
  magics (323–330 → 10), spells (331–355 → 10), items (356–414 → 14),
  NPC names (177–182 → 10), classes (124,125 + Knight/Fighter → 10 via slot
  rule), search status (144–146 → 10). Renames to fit the 14-char item field
  include: "Confusion pot.", "Strength pot.", "Speed potion", "Wisdom potion",
  "Hero's Emblem", "Secret scroll".
- **FW_ONLY strings** (never pair-encoded): the 12 grid rows, plus tabular
  headers aligned over FW columns: 0x007044, 0x00706C, 0x007F6C, 0x0F9868,
  0x0FEFE4.
- Menu labels restored to full words where they fit at half-width: Search,
  Command, Inventory, Status, Run away, Examine, To the inn, To town, Accident,
  Found it., Searching. Still short by necessity: "Next" (61), "Tower" (70),
  MAX/Slowly (158/159), 457/458 split.
- **TRIMS** all removed except **id 261** (pointer-less, in-place only).
  **This string has a hard 77-byte budget** (the builder allows `budget + 2`, so
  79 bytes of encoded payload). It is set in `build_final3.py`, which SHADOWS
  the spreadsheet — editing the ODS row for 261 does nothing. Current text:
  `"Let's say you're smart. Magic works better for you. Not me."`
  A longer wording overflows and the build reports
  `skip 0x0F7E80: in-place too big (N>77)`; the fix is to shorten the TRIM in
  `build_final3.py`, not the spreadsheet. Remember the encoded size includes the
  `0x0A 0x0A` pairs inserted by `wrap_words` at 28 half-columns.

## A.7 SUPPLEMENT entries (status screen; keyed by raw file offset, not in TSV)

- 0x0F9814 "Class" — no colon; the window's dotted separator *is* the colon.
  (Earlier the 2-cell field forced "Type"; alignment patches below widened it.)
- 0x006150 "HP    ", 0x006140 "STR   ", 0x006138 "INT   " — pad 2→3 cells so
  the opaque text cell covers a stray underlay box left by alignment.
- 0x006184 / 0x0061A4 / 0x0061C4 = Shld / Armor / Wpn labels `ljust(28)` —
  full-line clears so the equipment enchant-bonus area ("+1") is blanked before
  the item draws.

## A.8 Status-screen label x-alignment code patches

Applied post-encode in `build_final3.py` (assert the old word `0x340401C4`
first). File offsets **0x62108, 0x627B8** (Class), **0x622B0** (HP),
**0x622E8** (STR), **0x622FC** (INT) → change `ori $a0` immediate
**0x1C4 → 0x1C2**, left-aligning all labels to Level's column. (MP/Speed/Level
are already 0x1C2.) DrawText = 0x80036360(a0=x, a1=y, a2=strptr); 1 x-unit =
4px; rows step y by 0x10.

## A.9 Verification pattern (run after every build)

`build.sh` ends with **`tools/verify_build.py`**, which automates checks 1-4 and
6 below and prints `ALL PASS`. Run it manually as
`python3 tools/verify_build.py build/MAIN.EXE build/SLPS_001.97`.

1. Output sizes match originals (MAIN 1085440 / SLPS 333824).
2. All 4 hook JAL sites now point to the hook (0x800D1F68).
3. Every live glyph-table entry byte-matches `pixfont.pair_glyph`. **The
   comparison alphabet must be the full printable ASCII range 0x20-0x7E** — an
   earlier narrow alphabet produced three false "unmatched" glyphs (`"; "`,
   `"d;"`, `"s;"`, i.e. semicolon pairs).
4. The 5 alignment patches read `0x340401C2`.
5. Decode every string back from the binary via its pointer / code-ref /
   in-place location and compare to the expected pipeline output
   (NORM -> wrap_words -> field padding -> slot padding -> segments).
   Last known-good: 485/485 clean.
6. Post-build patches present: the corner DAY/HOUR templates decode to
   `"   Day "` / `"   hr "`, and both shared level-up writers have been
   re-routed away from 0x80097DA4 / 0x80097C50.

## A.10 Deferred / known-benign (Track A)

- The day/hour kanji box (１日目 / ０時) — **NOW TRANSLATED**, see A.11–A.14.
  (It was NOT graphic/code-composed as previously thought; it is editable SJIS
  template data + separate number sprites.)
- General-menu bleedthrough behind status windows is intentional game layering.
- Narrow boxes (save/confirm dialogs) still use engine mid-word wrap if a manual
  line exceeds their width — fix by adding per-string wrap widths if reported.
- If new stale-texel squares appear on an unvisited screen, the cause is a
  translation shorter than its original slot — let `apply_slot_padding` cover it
  (raise `max_cells` if the original was >10 cells).
- If a pair glyph looks wrong, edit its letterform in `pixfont.py` (remember the
  engine bolds with `row|row>>1`; separate strokes need 2px gaps).

## A.11 ⚠ GLYPH-TABLE REALITY — fonthack.json code map can be STALE

**The pair→code map in `fonthack.json` may NOT match the shipping binary.** It
records `table_ram = 0x80126B10`, but the running (already-translated) MAIN.EXE's
glyph table is **in-file at RAM 0x801076D0** (the value the build actually
prints; see A.1). They are different builds. Using fonthack codes to hand-edit
strings in the shipped binary renders **garbage** (e.g. `0xF1E0` decoded as
`ov`, `0xF09F` as ` o`, `0xF1B5` as `oi`).

**Always reverse-engineer the real map from the binary's own table:**
- The table at 0x801076D0 is 620 × 4-byte pointers; entry `i` → a 32-byte glyph.
- `idx_to_code(i) = ((0xF0 + i//124)<<8) | (0x80 + i%124)`;
  `code_to_idx(c)  = ((c>>8)−0xF0)*124 + ((c&0xFF)−0x80)`.
- The full 32 bytes at a glyph pointer **equal `pixfont.pair_glyph(a,b)`**
  (verified). Match `glyph[6:28]` against `pair_glyph(a,b)[6:28]` for every ASCII
  pair to recover which code = which letter-pair *in this binary*.
- Pair codes are stored **big-endian in the string data** (hi byte, lo byte),
  e.g. `Da`=`0xF1D9` → bytes `f1 d9`. Full-width space = `81 40`, term = `00 00`.

`patch_dayhour_ui.py` does this reverse-mapping automatically. Codes recovered
for the current shipped build: `Da`=0xF1D9, `y `=0xF09E, `hr`=0xF1BB,
` h`=0xF0B1, `r `=0xF08F, `d `=0xF089. (`D `+space did NOT exist — see A.14.)

## A.12 Corner time box (top-right "N日目 / N時") — TRANSLATED

Two editable SJIS **template strings**, drawn as text; the numbers are separate
**sprites** drawn on top of the leading-space fields.

- **DAY template**  @ RAM **0x800E48EC** (file 0x0D50EC). Pristine
  `81 40 ×3, 93 fa(日), 96 da(目), 00 00` = "　　　日目".
- **HOUR template** @ RAM **0x800E48F8** (file 0x0D50F8). Pristine
  `81 40 ×2, 8e 9e(時), 81 40, 00 00` = "　　時　".
- Drawn by **DrawText 0x80036360** (which internally calls the hooked rasterizer
  0x80034904 — `jal 0x80034904` at 0x80036394 — so pair-font codes DO render
  here). Three draw sites each (three screens); the day `addiu …,0x48EC` sits at
  **0x800333C0 / 0x80033570 / 0x800339A8**, hour `addiu …,0x48F8` at the paired
  sites just after. Coords: day x=0x19C, hour x=0x1A0.
- The **number** is drawn by sprite routines **0x80037754** (and 0x800373AC),
  `a0`=value, `a1`=x, `a2`=y — a custom bitmap number font, right-aligned into
  the leading-space field so it sits adjacent to the kanji.

**Fix (in place, no relocation):** DAY 日目 → `Da`+`y ` = "Day"; HOUR 時 → the
`" h"`+`"r "` cells = " hr". Both keep their original slot length. Renders
"1Day" / "19 hr". (An earlier attempt relocated DAY to a freespace slot in the
0x800E page and repointed the 3 `addiu`; reverted — in-place fits once the label
is 2 cells like the kanji it replaces.)

## A.13 Camp / status / inventory day-hour labels — TRANSLATED to half-width

Other screens (full-status, inventory, light-sleep) draw day/hour from **their
own** label strings — NOT the corner templates — and the build left them
**full-width** (fat, widely spaced). They use the abbreviations `ｄｙ`
(full-width d y = `82 84 82 99`) and `ｈｒ` (`82 88 82 92`).

⚠ **These addresses MOVE on every build.** They are relocated string data, so
any change to the script reshuffles the allocation pool and invalidates a
hardcoded address. `patch_dayhour_ui.py` therefore **scans for them** rather
than hardcoding: it walks every full-width `ｄｙ` (`82 84 82 99`) in the image
and classifies by the bytes around it —

| signature after the `ｄｙ` | which label |
|---|---|
| terminator `00 00` | standalone day label → "Day" |
| `81 40` ×2 then `ｈｒ` | camp light-sleep combined label (start = first of the leading `81 40` run) |
| one `81 40` then `ｈｒ` | status / inventory readout |
| preceded by `ｍｏ` + `81 40` | **birthday month/day input — SKIP** |

Occurrences (values for the 2026-08-16 build, illustrative only — do not
hardcode):
- **0x800DCB44** (was 0x800C0942) — standalone day label → "Day".
- **0x800CCF5C** (was 0x800C8B60) — the **camp light-sleep** combined label
  (see A.14). Loaded via pointer-table slot 0x80110020, drawn at 0x80096184.
- **0x800D5C30 / 0x800D5C36** (was 0x800D2A24 / 0x800D2A2A) — status/inventory
  readout → "Day" / " hr".
- **SKIP** the "　　　ｍｏ　ｄｙ" **birthday month/day** input (right before
  "What is your sex?"), NOT game-time. Leave it alone.

Everything the patcher touches in *code* (draw-site immediates, the number-sprite
x values) is at a fixed address and is still hardcoded — only string data moves.

## A.14 Camp light-sleep box + the new "D " glyph

The light-sleep window ("Please select which type / Press a button to wake up",
heals by the hour) draws its own day/hour + HP. Number sprites via routine
**0x800967E8**: day# `a1`=0x1C2 (imm @0x80096804), hour# `a1`=0x1D2 (imm
@0x80096864), HP# 0x1C6, HPmax 0x1D6 (y=0x1A8). Label x @0x80096178 = 0x1C2.

This box is **1 cell too narrow** for a full "Day…hr" line with a 2-digit hour
(hours reach 2 digits here; days never do — you'd be healed first). Solution:
shorten the day label to a single **capital "D"**. The font had **no `"D "`
glyph** (only A F I K P R T exist as letter+space cells), so one was **added**:

- Generated `pixfont.pair_glyph('D',' ')` (32 B), written to the first 32-byte
  all-zero run found from 0x800D8000 upward (**0x800D9464** in the current
  build — also build-dependent, and the scan explicitly avoids the level-up
  writer region); the in-file glyph-table entry for the free code **0xF4FA**
  (idx 618) @ file table 0x80108078 is repointed to it. (0xF4FB still free.)
  If `patch_levelup.py` runs first its relocated writers are non-zero, so the
  two allocators cannot collide in either order.
- Sleep label @0x800C8B60 → `81 40 ×3, [D=F4FA], 81 40 ×2, [ h=F0B1], [r =F08F],
  00 00` = "　　　D　　 hr" (18 B; freed tail nulled).
- Hour-number x nudged **0x1D2 → 0x1CE** (@0x80096864) so the 2-cell hour field
  clears the "hr" label. Renders "0D  3 hr" / "0D 16 hr".

Reproduce all of A.12–A.14 with **`patch_dayhour_ui.py IN.EXE OUT.EXE`**
(independent of the level-up patch; any order).

## A.15 Level-up stat messages — FIXED (patch_levelup.py)

Five stat-raise messages + the learn-magic message stamped the stat number at a
**hardcoded byte offset = where the JP placeholder ＸＸ (`82 77`) sat**. English
keeps "XX" at sentence end, so the number landed mid-word and literal "XX"
remained. Fix repoints each digit-writer's `sb` store offsets to the English XX
position (found by scanning for the `82 77 82 77` run):

- Writers: HP inline @0x80097948; shared W1 @0x80097C50 (STR via `j`@0x80097B9C +
  INT fall-through); shared W2 @0x80097DA4 (magic via `j`@0x80097AEC + SPD);
  learn-magic @0x8009804C. All tail-jump to 0x80097E48.
- Shared writers are split by re-routing the `j`-entered stat: STR's `j`
  repointed to the HP writer (same XX offset); a private 168-byte copy of the
  magic writer is placed at freespace **0x800D988C** (all-zero, vetted).
- Digit values via div-by-10 (`0x66666667`); DrawText = 0x80036360.

Run **`patch_levelup.py`** (self-verifying: asserts the un-patched known build,
discovers offsets dynamically, applies, re-verifies). No TSV/text change needed.
**Independent of `patch_dayhour_ui.py`.**

────────────────────────────────────────────────────────────────────────
# TRACK B — TIM IMAGE-TEXT OVERLAYS  (ending, credits, UI)

Text is baked as **pixels** in `.TIM` images (NOT encoded strings — confirmed:
the known line そなたは神の力を得た appears in NO file as SJIS bytes). To
translate, **repaint the pixels and re-encode, preserving structure exactly**.

## B.1 Toolchain (in `/mnt/user-data/outputs/english_overlays/`)

- **timcodec.py** — 4-bit TIM decode/encode; byte-identical round-trip verified.
  `decode()` → dict(flag, clut_hdr, clut_raw, clut[list of BGR555],
  img_hdr=(ix,iy,iw,ih), W=iw*4, H, idx[bytearray W*H], clen, ilen, orig_size).
  `encode(meta, idx)` → bytes. CLUT + all headers preserved verbatim.
- **timtext.py** — WE ending text renderer (band-matched horizontals + rotated
  vertical strips): `build_hmask` / `build_vmask` / `build_ramp` / `_quantize` /
  `compose`.
- **make_english_we.py** — driver for WE_5F0/5F1/FF0/FF1/FF2. Edit the `LINES`
  and `VSTRIP_SEGMENTS` dicts and re-run.
- **make_english_yesno.py** — YESNO.TIM (はい/いいえ → Yes/No).
- **make_english_ui.py** — MEMORY.TIM (mem-card messages) + PC_MAKE1.TIM
  (charset buttons).

## B.2 TIM format (all these are 4-bit, mode 0, CLUT present)

Header: `00`:magic 0x10  `04`:flag (bits0-2 mode, bit3 clut) → then CLUT block
(len u32, x,y,w,h u16, data) → then IMG block (len u32, x,y,w,h u16, pixdata).
4-bit: **2 px/byte, low-nibble-first**; `iw` is in 16-bit words so real width =
`iw*4`. Colour is **BGR555**; **index 0 = transparent**.

## B.3 The ending display model (hard-won; END256.EXE / END50x.EXE)

- Each `WE_*.TIM` is **256×256**, uploaded to the VRAM coords in its own header,
  so replacements land in the right place automatically — **never change size or
  coords.**
- Overlays are self-contained PS-EXE programs (own C startup, clear BSS, init
  gfx, read TIMs from CD). They can be **direct-booted** in an emulator with the
  disc mounted (PCSX-Redux ideal; no$psx; DuckStation) to view a specific ending
  without a playthrough. Translated TIMs must be in the disc image to appear.
- **Ending choice** in MAIN.EXE: selector halfword @0x801ADC84 + var
  @0x8017EBD8, then LoadExec wrapper 0x800981F0(a0=filename, a1=0x8001FF00,
  a2=0). Filenames `cdrom:\ENDxxx.EXE;1` clustered at MAIN file 0x1F74 / 0x7A60
  / 0x7E40.
- **Text is shown band-by-band:** the game displays ONE sentence-group at a time
  by windowing a horizontal **band** of the texture. The originals are a clean
  ~16px line grid (**WE_5F0=14 lines, 5F1=15, FF0=16, FF1=16, FF2=15**). Fade
  in/out animates the **CLUT through 16 sub-palettes** (pal0 = full brightness,
  pal15 = black); a washed-out screenshot is just a mid-fade frame.
- **Display window spans texture x≈16..240 (~224px usable).** Anything inside
  shows next to the lines; anything **outside** (x<16 or x>240) is hidden during
  horizontal groups. So horizontal lines must fit within x16..240 (cap ~214px
  centre; FF0 tighter at 198). Vertical side-column phrases must live in the
  **outer columns** (x<16 left, x>240 right) or they leak in as sideways
  fragments.
- **Vertical strips** are shown by the strip's own sequence step, which
  **rotates** the outer column to a horizontal line. Correct rotation = **90°
  CCW** (verified). Put the whole phrase in the single primary outer column;
  leave the others empty.
- **Strip-vs-line-edge test:** a TRUE vertical strip has ink in the gaps
  *between* line bands (5F1 far-left 185px, far-right 130px; FF1 far-left
  119px); line-edge false positives show ~0 gap ink (FF0, FF2). Use this to
  decide whether an apparent side column is real.
- **Variants share textures.** Multiple ending variants use the same WE textures
  and each windows a different subset. END500/503 differ only by ROLL.EXE vs
  ROLL2.EXE (7 bytes); END501/504 likewise, and additionally load
  EXPL_00/TOWN_01 (the town-destruction "defeat" variant showing WE_5F1 lines
  4–15 + strips). The full script is split across variants **by design** —
  "missing" text is another variant's. The FF set (END256–269) analogously
  windows WE_FF0/1/2 + YESNO.

## B.4 Ending translation status — **COMPLETE** (user text = Ending_Wolken.txt)

All **five pages use the user's translation**, group-mapped from their numbered
annotation screenshots. Band/strip layout:

- **WE_5F0** (14 bands): g1→2 bands, g2→3, g3→3, g4→2, g5→1, g6→2, g7→1;
  g8 "This is yours." → **RIGHT outer col** (x248, y6–135).
- **WE_5F1** (15 bands): g1..g15 one each;
  g16 "Do you think you can dominate it?" → **LEFT outer col** (x8, y61–247);
  g17 "Sadly, that is impossible for you." → **RIGHT outer col** (x248, y4–198).
- **WE_FF0** (16 bands): g1..g16 one each. **No vertical strip** (verified: the
  apparent left strip is just the left edge of wide lines).
- **WE_FF1** (16 bands): g1..g16 one each;
  g17 "You have earned the power of a god." → **LEFT outer col** (x7, y18–197).
  Right side has no strip.
- **WE_FF2** (15 bands): g1..g15 one each. **No vertical strip.**

**Width:** cap ~214px (JP's own widest strip-free line = 211). Lines exceeding
it **auto-render at 8px or 7px** rather than being reworded (FF0 g1,g2,g14,g16;
FF1 g2,g4,g9,g10,g11,g14; FF2 g1,g2,g11 — "Wolkenkratzer" is the usual culprit).
Earlier 5F trims flagged in the README: "laws I had established"→"laws I
established"; "vastly surpassed"→"surpassed all"; strip17 "most likely" dropped.
Other mechanical edits only: 5F0 g1 split over its 2 bands; 5F0 g6 re-broken as
"You shall seed life, intelligence and" / "governance on those wastelands.";
French spaces before "?" removed; FF2 g13 trailing space trimmed.
**FF endings also use the YESNO prompt.**

## B.5 YESNO.TIM (choice prompt はい/いいえ) — SHIPPED English

4-bit, CLUT 16×1 @vram(192,496), img @vram(512,256). Two copies of the text:
on the blue bar (y18–30) and a bar-less copy (y2–15), plus a ▶ cursor triangle.
The cursor is **code-positioned**, so "Yes"/"No" must be centred exactly where
はい/いいえ were: bar-copy word centres x≈48 / x≈103; top-copy x≈22 / x≈73.
Edited text pixels only; bar + cursor art untouched (asserted 0 stray edits).

## B.6 MEMORY.TIM (memory-card system messages) — SHIPPED English

4-bit, CLUT 16×1 @vram(0,511). Grayscale/blue message boxes. Index roles:
1=lt-gray text, 2=dark, 5=white text, 3=box purple, 4=box blue, 6=cyan bar.
Content (top→bottom), translated as:
- y0–32  (blue)  "No memory card is inserted." / "The game cannot be saved."
- y32–48 (blue)  "The memory card is not formatted."
- y48–64 (purple)"Format the memory card?"
- y64–80 (purple)"Yes" (cx50) / "No" (cx121)  [these track a ▶ cursor too]
- y80–112(blue)  "There are not enough free blocks." / "The game cannot be saved."
- y112–128(cyan) "Data error" + ▶ cursor arrow at x101–108 (idx5 on idx3 block)
  — erase JP only to x95 to preserve the arrow; draw text left of it.
Rendered white(5) + gray-AA(1) + dark-outline(2). Only box interiors edited.

## B.7 PC_MAKE1.TIM (character-creation charset buttons) — SHIPPED English

4-bit, CLUT 16×16 @vram(64,496), img @vram(384,256). Big olive top box, two
character portraits (**DO NOT TOUCH**), and 4 charset buttons at y178–198:
- box x1–63    ひらがな → "Hiragana"
- box x65–127  カタカナ → "Katakana"
- box x129–191 英大文字 → "ABC"  (capital English)
- box x193–255 英小文字 → "abc"  (lower-case English)

Button glyph indices: 15=bright text, drawn white(15)+AA(1) on the button
interior (bevel-safe inset ±5px, erase old idx{15,1}→2 fill). Portraits and the
pink decorative strips (right/bottom) untouched. Text centred; only the
y182–194 interior of each button edited (asserted).

## B.8 Rendering style (all overlays)

White fill + solid dark outline, tuned so **0% of white pixels touch the
background directly** (measured) → legible over any background and fades
correctly with the palette animation. Font: DejaVu Sans Bold. Supersample 4×,
LANCZOS down, threshold body ≥0.30 / AA ≥0.14, dilate for outline.

## B.9 Other ending assets (context; not yet translated)

Backgrounds / scene art (color, mostly no text): 256F+256FB / 50F+50FB
(320-wide split ending BGs), TOWN_00/01, GOD, SAT, LUCI, HACK, HAKKO, EXPL_00.
ROLL_00/ROLL_01 = credit-roll images (English staff names already; mostly
Latin). OMAKE.EXE = Sound Test bonus, menu already English (ORDINARY LIFE,
APOCALYPSE, etc.). Translate remaining scene TIMs only if they actually contain
JP text.

────────────────────────────────────────────────────────────────────────
# PROJECT FILES REFERENCE

**Pipeline (`build.sh`)**
`script/ods2tsv.py` → `tools/build_final3.py` → `tools/patch_levelup.py` →
`tools/patch_dayhour_ui.py` → `tools/verify_build.py`.
Stages 3 and 4 are **post-build patchers, not part of the build**: a rebuild that
skips them silently loses A.12–A.15. Their order relative to each other does not
matter (disjoint regions, non-colliding allocators).

**Code — `tools/`**
- **build_final.py** — base builder: TSV loader (`load_translations` with FIXES
  regex cleanup, OVERRIDES, SUPPLEMENT dict of kanji-only labels, `wrap_intro`),
  `fw()` ASCII→full-width mapping (`'`→U+2019, `"`→U+201D, `-`→U+2212,
  `~`→U+301C), `encode()` FW encoder, allocator, pointer/code-ref rewriting,
  `build_slps()`. Also hosts the repo path helpers `dpath()` / `opath()` and the
  `WK_DATA` / `WK_SCRIPT` / `WK_ORIG` env overrides. build_final3 imports and
  mutates its config.
- **build_final3.py** — THE production build (the font hack, encoder `encode2`,
  hook assembly `hook_words`, alignment patches, verification dump to
  `fonthack.json`). Run this to produce both executables.
- **pixfont.py** — 5×9 pixel font (m/w/M/W 7-wide); `pair_glyph(a,b)` → 32-byte
  bitmap. Bit15 of each row = leftmost pixel; char A at cols ~1–5, char B at
  ~9–13; engine bold spreads +1 right.
- **verify_build.py** — the A.9 pass as a tool: sizes, the 4 hook JALs, the 5
  alignment immediates, glyph-table integrity against `pair_glyph` over full
  printable ASCII, the day/hour templates, and both level-up writer re-routes.
  Exit 0 = clean.
- **sjis_scan.py** — standalone Shift-JIS text hunter for PS1 files
  (`python sjis_scan.py FILE...` or `-d folder`, `-m N` min chars, `-o out`).
  Prints `FILE @ 0xOFFSET : <japanese>`. Use if new strings ever need finding.
- **patch_levelup.py** — POST-BUILD patcher for the level-up stat/learn messages
  (A.15). Self-verifying; discovers the ＸＸ offsets dynamically. Resolves
  `MAIN_freespace.json` via `WK_DATA` → `../data` → input dir → cwd; **if it
  cannot find that file the fallback zero-run scan picks a different slot and
  the build stops being reproducible** (this was a real 4-byte drift bug).
- **patch_dayhour_ui.py** — POST-BUILD patcher for the corner time box, the
  camp/status/inventory day-hour labels, the new "D " glyph, and the light-sleep
  box layout (A.12–A.14). `python3 patch_dayhour_ui.py IN.EXE OUT.EXE` (needs
  pixfont.py). Reverse-engineers the real code map from the binary (A.11) and
  **locates the day/hour label strings by signature scan** (A.13), so it is
  robust both to fonthack.json drift and to script changes moving the strings.
  **NOT YET FOLDED INTO build_final3.py** — merging would require adding the
  "D " glyph to the atlas at build time and moving the level-up writer
  relocation into the allocator.
- **overlays/timcodec.py**, **overlays/make_english_ui.py** — Track B; see B.1.
  ⚠ **`timtext.py`, `make_english_we.py` and `make_english_yesno.py` are NOT in
  the repo** — they exist only in the earlier `english_overlays/` output bundle,
  along with the translated `.TIM` files themselves. Recover them from that
  download before doing any further Track B work.

**Data — `data/`**
- **MAIN_script2.json** — string map: list of 534 entries, keys
  `off, end, ram, refs[], text, code_ref`. (462 TSV strings + kanji-only labels.)
- **MAIN_code_refs2.json** — dict of 41 entries, key = RAM addr (e.g.
  `"0x800133b4"`) → list of `[lui_off, use_off]` lui/addiu ref pairs.
- **MAIN_freespace.json** — list of 258 `[offset, length]` audited safe zero
  blocks. Runtime buffers (e.g. 0x107184, 0x108528) are already excluded — do
  not re-add them.
- **fonthack.json** — last build's output: `{codes: {pair→code}, hook_ram,
  table_ram}`. **Informational only** — see A.11 before trusting it.

**Script — `script/`**
- **script_traduit.ods** — the translation, human-facing source of truth.
- **script_traduit.tsv** — generated; 462 translation rows (see A.5).
- **ods2tsv.py** — converter.

**Docs — `docs/`**
- **PROJECT_KNOWLEDGE.md** — this file (supersedes older KNOWLEDGE.md).

────────────────────────────────────────────────────────────────────────
# KEY ADDRESSES (RAM; file = RAM − 0x80010000 + 0x800)

| What | RAM |
|---|---|
| Krom2RawAdd kernel stub | 0x80098140 |
| Glyph rasterizer | 0x80034904 |
| Hook JAL sites | 0x800347A8, 0x800347E4, 0x8003492C, 0x80034A6C |
| Print (per-glyph VRAM upload) | 0x80036360 (alt 0x800362C8); calls rasterizer at 0x80036394 |
| Hook / glyph table (last build) | 0x800D1F68 / 0x801076D0 |
| **Glyph table used by SHIPPED binary (in-file)** | **0x801076D0** (NOT fonthack's 0x80126B10 — see A.11) |
| Number-sprite draw routines | 0x80037754, 0x800373AC (a0=value, a1=x, a2=y) |
| Corner box DAY / HOUR templates | 0x800E48EC / 0x800E48F8 |
| Corner box day `addiu 0x48EC` sites | 0x800333C0, 0x80033570, 0x800339A8 |
| Camp light-sleep number routine | 0x800967E8 (day# x@0x80096804, hour# x@0x80096864) |
| Camp/status/inv day-hour labels | **BUILD-DEPENDENT — scanned, never hardcoded** (A.13); 2026-08-16 build: 0x800DCB44, 0x800CCF5C, 0x800D5C30 |
| Added "D " glyph / its table entry / free code | **build-dependent slot** (0x800D9464 on 2026-08-16) / file 0x80108078 / 0xF4FA |
| Level-up digit writers | HP 0x80097948, W1 0x80097C50, W2 0x80097DA4, learn 0x8009804C; tail 0x80097E48 |
| Level-up relocated writers (STR / magic) | **build-dependent** — 0x800D988C / 0x800D9E08 on 2026-08-16 |
| Exe image end (BSS after — do not extend) | 0x80118800 |
| Ending selector halfword / var | 0x801ADC84 / 0x8017EBD8 |
| LoadExec wrapper | 0x800981F0 |

────────────────────────────────────────────────────────────────────────
# CHANGE LOG

**2026-08-16 — repo packaging + rebuild from the updated spreadsheet**
- Rebuilt Track A from the current `script_traduit.ods`: **485/485 strings
  placed, 0 skipped**, 612 unique pair chunks all given glyphs (cap 620),
  ~2.6 KB of pool left. SLPS intro 704/877 bytes.
- **id 261 overflowed** at 80 bytes against its 77-byte in-place budget; the
  `build_final3.py` TRIM was shortened (see A.6). This is the one string whose
  length is a hard constraint the spreadsheet cannot express.
- **`patch_dayhour_ui.py` was broken by the rebuild.** Its ｄｙ/ｈｒ label
  addresses were hardcoded from an older build; a script change moves those
  strings. Replaced with a signature scan (A.13). This was a latent failure —
  it would have hit any future script edit.
- **`patch_levelup.py` freespace lookup made explicit** (`WK_DATA` → `../data` →
  input dir → cwd). Previously, if `MAIN_freespace.json` was not adjacent to the
  input the fallback zero-scan chose slots 4 bytes off, so the same source
  produced two different binaries.
- Verified the whole pipeline is **byte-reproducible** end to end.
- Added `tools/verify_build.py`; found and fixed a false negative in the glyph
  check (narrow comparison alphabet, semicolon pairs — see A.9 §3).
- Reorganised into a git repo (`build.sh`, `tools/`, `data/`, `script/`,
  `docs/`, `orig/`, `build/`) with env-var path resolution so the tools no
  longer assume a flat working directory.

────────────────────────────────────────────────────────────────────────
# SAVE-STATE FORENSICS (reference, if ever needed again)

DuckStation `.sav`: magic "DUCCT", zstd frames; the state frame decompresses
from ~file offset 36812. In the decompressed blob: RAM 2MB at offset 0x1A62;
VRAM 1MB at 0x22AE62, **2048 bytes per row** (1024 words). Framebuffers at rows
0 and 240. Texture page (tx,ty) from the E1 word: x=(tp&0xF)*64 words,
y=bit4*256, depth bits 7–8. GPU packets in RAM ~0x180000–0x1A0000:
`[hdr len<<24|next][E1][cmd][xy][uv|clut][wh]`; prim coords use draw offset
(160,120). (This is how the BIOS-kanji-ROM font discovery was originally made.)

────────────────────────────────────────────────────────────────────────
# OUTSTANDING / NEXT STEPS

1. **(DONE)** FF ending translated and shipped — all 5 ending pages complete.
2. **Confirm in-game:** the WE_5F1 g16 strip shows on the LEFT outer column
   (if blank, its primary column is the other side); WE_FF1 g17 on the left;
   the YESNO cursor still aligns; PC_MAKE1 buttons and MEMORY messages read
   correctly.
3. **Check auto-shrunk lines** (the 8px/7px ones listed in B.4) look acceptable;
   if any is too small, reword that line and re-run `make_english_we.py`.
4. **Optional:** patch the END50x persistent-window left edge if edge fragments
   bug the user (now a findable one-constant change).
5. Consider translating remaining scene TIMs only if they contain JP text.
6. **Fold `patch_levelup.py` + `patch_dayhour_ui.py` into `build_final3.py`** so
   A.12–A.15 survive a rebuild. Order after string placement; the "D " glyph
   (A.14) must be added to the atlas/table at build time (a free code slot 0xF4FB
   still remains). Until then, run both patchers on the freshly-built MAIN.EXE.
7. **Build pipeline should half-width the day-hour labels directly** — the
   `ｄｙ`/`ｈｒ` abbreviations (A.13) were left full-width by `encode2`; making the
   build emit them as pair-font would remove the need for that part of the patch.
8. Post-patch verification quick-check (final shipped diff vs pristine = 177
   bytes): day/hour regions decode as "Day"/" hr"/"D"; the birthday "mo/dy"
   @0x800CD032 stays full-width; the added glyph @0x800D9E04 decodes as ('D',' ').
