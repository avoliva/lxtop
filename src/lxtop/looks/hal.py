"""Hal: a calm ship-computer look in the spirit of a long space voyage. White and grey on black,
a slow starfield, and one dim red eye that breathes. No decode, no flicker (see matrix.py
for the model look and theme.py for the rules every look keeps)."""

from __future__ import annotations

import math
import random

from lxtop.looks.theme import (
    BACKGROUND,
    BLACK,
    BLUE_8,
    FX_DIM,
    FX_GLASS,
    FX_GLASS_HEAD,
    FX_HEAD,
    FX_MID,
    RED_8,
    WHITE_8,
    YELLOW_8,
    Cell,
    Theme,
    Title,
)

# Every character exists in the console font (the dot is U+00B7).
STAR_CHARS = (".", ".", ".", "·", "·", "*", "+")
EYE = "●"
GLOW = ("▒", "░", "·")  # rings around the eye, nearest first
EYE_SECONDS = 6.0  # one slow breath
STAR_SHARE = 0.025  # stars per cell; the viewer thins them further
RING_RADII = (1.5, 2.6, 3.6)  # in rows; a column counts half a row, cells being twice as tall
# The shooting star: at most one every SLOT_SECONDS (chance SLOT_CHANCE), SHOT_SECONDS long.
SLOT_SECONDS = 40.0
SLOT_CHANCE = 0.75
SHOT_SECONDS = 1.8
SHOT_TRAIL = ("-", "·", ".")


def glow_cells() -> list[tuple[int, int, int]]:
    """(row offset, column offset, ring 0-2) around the eye, the ring being the smallest
    one whose radius holds the cell."""
    out = []
    for dy in range(-4, 5):
        for dx in range(-8, 9):
            if dy == 0 and dx == 0:
                continue
            dist = math.hypot(dy, dx / 2)
            for ring, radius in enumerate(RING_RADII):
                if dist <= radius:
                    out.append((dy, dx, ring))
                    break
    return out


GLOW_CELLS = glow_cells()


class Stars:
    """A sparse field of stars that drift sideways very slowly and twinkle between two grey
    tones, one eye near the lower right that breathes (a centre and rings of glow that swell
    and fade, dim grey to dark red), and now and then a shooting star across the sky."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.seed = self.rng.getrandbits(32)  # the shooting stars follow from it and the time
        self.h = 0
        self.w = 0
        # row, column, character, drift in columns per second, twinkle phase, twinkle rate
        self.stars: list[tuple[int, int, str, float, float, float]] = []
        self.eye = (0, 0)

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        r = self.rng
        self.eye = (min(h - 1, int(h * 0.78)), min(w - 1, int(w * 0.82)))
        count = int(h * w * STAR_SHARE)
        self.stars = [
            (
                r.randrange(h),
                r.randrange(w),
                r.choice(STAR_CHARS),
                r.uniform(0.15, 0.6),
                r.uniform(0.0, math.tau),
                r.uniform(0.3, 1.2),
            )
            for _ in range(count)
        ]

    def breath(self, now: float) -> float:
        """How full the eye is, 0 to 1 and back, once every EYE_SECONDS."""
        return (1 - math.cos(math.tau * now / EYE_SECONDS)) / 2

    def eye_tone(self, now: float) -> int:
        level = self.breath(now)
        return FX_DIM if level < 0.33 else FX_MID if level < 0.75 else FX_HEAD

    def glow(self, now: float) -> list[Cell]:
        """The rings: the more the eye has breathed in, the more rings show; nearer is redder."""
        level = self.breath(now)
        rings = 0 if level < 0.2 else 1 if level < 0.5 else 2 if level < 0.8 else 3
        tones = (FX_HEAD if level >= 0.5 else FX_MID, FX_MID, FX_DIM)
        ey, ex = self.eye
        out: list[Cell] = []
        for dy, dx, ring in GLOW_CELLS:
            y, x = ey + dy, ex + dx
            if ring < rings and 0 <= y < self.h and 0 <= x < self.w:
                out.append((y, x, GLOW[ring], tones[ring]))
        return out

    def shooting_star(self, now: float) -> list[Cell]:
        """The shooting star of this moment, if one is crossing: a bright head and a short
        trail, slanting down to the right. Which slots have one, and where, follow from the seed."""
        slot = int(now // SLOT_SECONDS)
        r = random.Random(self.seed ^ (slot * 2654435761))
        if r.random() > SLOT_CHANCE:
            return []
        age = now - slot * SLOT_SECONDS - r.uniform(2.0, SLOT_SECONDS - 10.0)
        if not 0 <= age < SHOT_SECONDS:
            return []
        row0 = r.uniform(0, max(1, self.h * 0.5))
        col0 = r.uniform(0, self.w * 0.6)
        speed = self.w * 0.3  # columns per second
        out: list[Cell] = []
        for i in range(len(SHOT_TRAIL) * 2 + 1):  # the head, then the trail behind it
            col = int(col0 + age * speed) - i
            row = int(row0 + (age * speed - i) * 0.35)
            if 0 <= row < self.h and 0 <= col < self.w:
                char = "*" if i == 0 else SHOT_TRAIL[(i - 1) // 2]
                out.append((row, col, char, FX_MID if i < 3 else FX_DIM))
        return out

    def frame(self, now: float) -> list[Cell]:
        if not self.h or not self.w:
            return []
        glow = self.glow(now)
        seen = {self.eye, *((y, x) for y, x, _, _ in glow)}
        out: list[Cell] = []
        for y, x, char, drift, phase, rate in self.stars:
            col = int(x + now * drift) % self.w
            if (y, col) in seen:
                continue
            seen.add((y, col))
            bright = math.sin(now * rate + phase) > 0.85
            out.append((y, col, char, FX_MID if bright else FX_DIM))
        for cell in self.shooting_star(now):
            if cell[:2] not in seen:
                seen.add(cell[:2])
                out.append(cell)
        out += glow
        out.append((*self.eye, EYE, self.eye_tone(now)))
        return out


def stars(console: bool, rng: random.Random) -> Stars:
    return Stars(rng)


THEME = Theme(
    name="hal",
    colours={
        1: (255, WHITE_8),  # GREEN: data, bright white
        2: (220, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (250, 2),  # CYAN: labels, light grey (console slot 2, redefined)
        5: (153, 6),  # MAGENTA: upload, pale cold blue (console slot 6, redefined)
        6: (244, 5),  # BLUE: frames and quiet text, mid grey (console slot 5, redefined)
        7: (252, WHITE_8),  # WHITE: plain text, soft white
        # The sky stays darker than any text; only the eye (head) turns dark red.
        FX_DIM: (236, BLACK),
        FX_MID: (240, BLACK),
        FX_HEAD: (88, BLACK),
        BACKGROUND: (250, WHITE_8),
        FX_GLASS: (236, BLACK),
        FX_GLASS_HEAD: (52, BLACK),
    },
    background=BLACK,
    frame="┌┐└┘─│",
    tick_ms=200,
    panels=True,
    glass=234,
    console_palette=(
        (BLUE_8, "121212"),  # glass: very dark grey under the panels
        (8, "3c3c3c"),  # dim text on the console: the stars, dark grey
        (2, "b4b4b4"),  # light grey labels
        (5, "808080"),  # mid grey frames and quiet text
        (6, "a8c4e4"),  # pale cold blue
        (WHITE_8, "dcdcdc"),  # soft white
        (8 + WHITE_8, "ffffff"),  # bold white
    ),
    backdrop=stars,
    glitch=False,
    noise=(".:", ".:"),
    boot=(
        "good evening.",
        "all hosts are accounted for.",
        "the host is running smoothly.",
    ),
    meter_empty=("·", "·"),
    title=Title(left="●", right="·", prompt="", cursor=""),
    accent=7,
    label="grey starfield, a breathing red eye, shooting stars",
)
