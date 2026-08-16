"""make_english_we.py - build the five English ending overlays.

Targets the PATCHED display model (see timtext.py): 16 uniform bands per file,
full-width window, no vertical strips.

SPILLOVER
---------
Ending_Wolken.txt gives WE_5F1 and WE_FF1 seventeen groups each, but a page
holds only 16 bands. Their final group is carried on the spare band 16 of the
matching 15-group page - which is what the shipped English build does:

    WE_5F1 g17 "No, sadly that is most likely impossible."  -> WE_5F0 band 16
    WE_FF1 g17 "You have earned the power of a god."        -> WE_FF2 band 16

Edit LINES and re-run. Each list must contain at most 16 entries; "" leaves a
band blank.
"""
import os
import numpy as np
import timcodec
import timtext

UNIFORM = False                           # see build(): per-line vs page-wide sizing
SRC = "orig"                              # Japanese originals (input)
OUT = "/mnt/user-data/outputs/english_overlays"

LINES = {
 "WE_5F0": [
    "An actual human,",
    "reaching this place?",
    "You transcended the laws I established.",
    "You surpassed what I thought possible.",
    "Thus you are standing before me.",
    "You spilled blood, again and again.",
    "You fell down, again and again.",
    "Yet in the end, here you are, standing up.",
    "You passed my test.",
    "You shall guide a brand new creation.",
    "This is what the power of a god truly is.",
    "You shall seed life, intelligence and",
    "governance on those wastelands.",
    "This is what the power of a god truly is.",
    "This is yours.",
    "No, sadly that is most likely impossible.",   # spillover: WE_5F1 g17
 ],
 "WE_5F1": [
    "The time to hesitate is now far gone.",
    "Everything is in your hands now.",
    "Everything is in your heart.",
    "You faced adversity, again and again.",
    "I see the courage in you.",
    "But it is way too late.",
    "You are too late.",
    "Is it even possible?",
    "For a human, such as you?",
    "Look at it, now that you lost.",
    "Look at the confusion of the world.",
    "Look at the discord amongst humans.",
    "Look at the destroyed order.",
    "Look with your eyes...",
    "at the manifestation of my will.",
    "Do you think you can dominate it?",
 ],
 "WE_FF0": [
    "What were you asking of the Wolkenkratzer?",
    "What were you hoping from the Wolkenkratzer?",
    "What did you earn from it?",
    "All those answers",
    "you now possess them",
    "The wounds engraved in your body",
    "cut the humans from their confusion;",
    "the dismay engraved in your heart",
    "neutered the unbalance of the world;",
    "and the courage you nurtured",
    "allowed you to get the power of a god.",
    "But...",
    "You can decline all of it",
    "and become the master of the Wolkenkratzer.",
    "With the advent of a new master",
    "the skies will tremble, the Earth will shake.",
 ],
 "WE_FF1": [
    "It is now time for you to decide.",
    "Will you become the master of the Wolkenkratzer?",
    "The world will change.",
    "Cities will collapse. The order will be shattered.",
    "All will return to dust.",
    "No matter what hopes",
    "there still have might been left.",
    "A power than can grant",
    "anything you think of, anything you wish for.",
    "Your courage and dedication know no limits.",
    "They should allow you to guide the world.",
    "And then, when the time comes...",
    "a new judgement day shall occur.",
    "I do not know how you reached this place.",
    "What you were thinking, or imagining,",
    "and I do not care.",
 ],
 "WE_FF2": [
    "To walk this neverending path of massacre,",
    "you bathed your heart in the desire to live,",
    "in the impulse of death, and in hopes.",
    "Those were your beliefs.",
    "Those are what motivated you,",
    "and how you came here.",
    "But you have been vanquished.",
    "With your defeat, my will",
    "is now resolved.",
    "It is unaffected by you,",
    "your courage, your efforts or your tenacity.",
    "My will only considers the result.",
    "Look at it, now that you lost.",
    "Look, with your dried-up eyes,",
    "at the manifestation of my will.",
    "You have earned the power of a god.",         # spillover: WE_FF1 g17
 ],
}


def build(name, lines):
    m = timcodec.decode(f"{SRC}/{name}.TIM")
    a = np.array(m["idx"], dtype=np.uint8).reshape(m["H"], m["W"])
    timtext.clear_text(a)

    assert len(lines) <= timtext.N_BANDS, f"{name}: {len(lines)} > 16 bands"

    # UNIFORM=False (default, matches the shipped build): each line takes the
    # largest size that fits, so short lines stay big and only long lines
    # shrink. UNIFORM=True drops the whole page to the worst line's size --
    # tidier, but it makes every line as small as the longest one.
    if UNIFORM:
        base = min(timtext.fit_size(t, timtext.MAXW) for t in lines if t)
    else:
        base = timtext.FS_START
    widths, sizes = [], []
    for n, text in enumerate(lines):
        r = timtext.draw_band(a, text, n, start=base)
        if r:
            sizes.append(r[0])
            widths.append(r[1])

    data = timcodec.encode(m, a.flatten())
    os.makedirs(OUT, exist_ok=True)
    open(f"{OUT}/{name}.TIM", "wb").write(data)

    orig = open(f"{SRC}/{name}.TIM", "rb").read()
    hdr = 8 + m["clen"]
    ok_size = len(data) == len(orig)
    ok_hdr = data[:hdr] == orig[:hdr]          # CLUT + coords preserved
    print(f"{name}: size_ok={ok_size} clut/coords_preserved={ok_hdr} "
          f"lines={len(lines)} font={min(sizes)}-{max(sizes)}px "
          f"widest={max(widths)}px")
    return ok_size and ok_hdr


if __name__ == "__main__":
    allok = all(build(n, l) for n, l in LINES.items())
    print("\nALL OK" if allok else "\nFAILURES PRESENT")
