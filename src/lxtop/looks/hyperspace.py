"""Hyperspace: stars stream outward from the screen centre, dots that stretch into streaks as
they speed up, white and pale blue on black (see theme.py for the rules every look keeps)."""

from __future__ import annotations

import math
import random

from lxtop.looks.theme import (
    BACKGROUND,
    BLACK,
    BLUE_8,
    CYAN_8,
    FX_DIM,
    FX_GLASS,
    FX_GLASS_HEAD,
    FX_HEAD,
    FX_MID,
    MAGENTA_8,
    RED_8,
    WHITE_8,
    YELLOW_8,
    Cell,
    Theme,
    Title,
)

ROW_SCALE = 0.5  # a cell is about twice as tall as wide
MAX_STREAK = 5
JUMP_EVERY = 31.0  # seconds between jumps
JUMP_LENGTH = 1.3  # seconds a jump lasts
JUMP_BOOST = 2.6  # how much longer streaks get at the peak of a jump
# Parallax layers: (share of stars, speed factor, streak factor). The far ones crawl and stay
# short and dim, the near ones race, stretch and take the brightest tone.
LAYERS = ((0.55, 0.6, 0.6), (0.3, 1.0, 1.0), (0.15, 1.7, 1.5))


def _line(vx: float, vy: float) -> str:
    ax, ay = abs(vx), abs(vy)
    if ay < 0.38 * ax:
        return "-"
    if ax < 0.38 * ay:
        return "|"
    return "\\" if vx * vy > 0 else "/"


def jump_level(now: float, offset: float = 0.0) -> float:
    """0 at cruise; during a jump a quick rise to 1, a short hold, then a snap back to 0."""
    t = (now + offset) % JUMP_EVERY
    if t >= JUMP_LENGTH:
        return 0.0
    f = t / JUMP_LENGTH
    if f < 0.2:
        return f / 0.2
    return 1.0 if f < 0.75 else 0.0  # then the streaks snap back to cruise


class Hyperspace:
    """Stars on rays from the centre in three parallax layers. Each star's progress u runs 0 to
    1 and repeats; its distance grows as u squared (so it speeds up) and its streak lengthens
    the same way, longer for near stars. Now and then a jump stretches every streak at once."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.h = 0
        self.w = 0
        self.cy = 0
        self.cx = 0
        self.rmax = 1.0
        self.stars: list[tuple[float, float, float]] = []  # angle, cycles per second, phase
        self.layer: list[int] = []
        self.offset = rng.uniform(JUMP_EVERY * 0.3, JUMP_EVERY * 0.9)

    def resize(self, h: int, w: int) -> None:
        self.h, self.w = h, w
        self.cy = h // 2
        self.cx = w // 2
        self.rmax = math.hypot(w / 2, h) + 1
        r = self.rng
        n = max(4, min(90, h * w // 100))
        self.stars = []
        self.layer = []
        for i in range(n):
            f = i / n
            lay = 0 if f < LAYERS[0][0] else 1 if f < LAYERS[0][0] + LAYERS[1][0] else 2
            self.layer.append(lay)
            rate = r.uniform(0.3, 0.7) * LAYERS[lay][1]
            self.stars.append((r.uniform(0, 2 * math.pi), rate, r.random()))

    def depth(self, i: int, now: float) -> float:
        """Progress of star `i` from the centre (0) to the edge (1) at `now`."""
        _, rate, phase = self.stars[i]
        return (now * rate + phase) % 1.0

    def frame(self, now: float) -> list[Cell]:
        if self.h < 1 or self.w < 1:
            return []
        jump = jump_level(now, self.offset)
        out: dict[tuple[int, int], tuple[str, int]] = {}
        for i, (th, _, _) in enumerate(self.stars):
            u = self.depth(i, now)
            d = self.rmax * u * u
            if d < 1.0:
                continue
            lay = self.layer[i]
            tone = FX_HEAD if lay == 2 and u > 0.35 else FX_MID if lay > 0 or u > 0.6 else FX_DIM
            if jump > 0.5 and lay == 1:
                tone = FX_HEAD
            cos, sin = math.cos(th), math.sin(th)
            stretch = LAYERS[lay][2] * (1.0 + JUMP_BOOST * jump)
            length = min(int(u * u * (MAX_STREAK + 1) * stretch), 4 * MAX_STREAK)
            char = "." if length == 0 else _line(cos, sin * ROW_SCALE)
            for k in range(length + 1):
                dd = d - k
                y = self.cy + round(dd * ROW_SCALE * sin)
                x = self.cx + round(dd * cos)
                if 0 <= y < self.h and 0 <= x < self.w:
                    # the head is brightest; the tail fades to the dimmest tone
                    t = tone if k == 0 else min(tone, FX_MID) if k <= length // 2 else FX_DIM
                    out[(y, x)] = (char, t)
        return [(y, x, c, t) for (y, x), (c, t) in out.items()]


def make(console: bool, rng: random.Random) -> Hyperspace:
    return Hyperspace(rng)


THEME = Theme(
    name="hyperspace",
    colours={
        1: (153, CYAN_8),  # GREEN: pale blue data
        2: (226, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (117, CYAN_8),  # CYAN: labels, sky blue
        5: (189, MAGENTA_8),  # MAGENTA: upload, a blue-lavender white
        6: (67, CYAN_8),  # BLUE: frames and quiet text, steel blue
        7: (231, WHITE_8),  # WHITE: pure white
        # The stars stay darker than any text: they are the background, not the news.
        FX_DIM: (17, BLUE_8),
        FX_MID: (18, BLUE_8),
        FX_HEAD: (24, BLUE_8),
        BACKGROUND: (67, CYAN_8),
        FX_GLASS: (17, BLUE_8),
        FX_GLASS_HEAD: (18, BLUE_8),
    },
    background=BLACK,
    frame="╒╕╘╛═│",
    tick_ms=80,
    panels=True,
    glass=233,
    console_palette=(
        (BLUE_8, "05081a"),  # glass: night blue under the panels
        (8, "1c3a78"),  # the stars, deep blue
        (CYAN_8, "9cc8ff"),
        (8 + CYAN_8, "c4e0ff"),
        (MAGENTA_8, "c4c8ff"),
        (8 + MAGENTA_8, "dcdcff"),
        (WHITE_8, "f2f6ff"),
        (8 + WHITE_8, "ffffff"),
    ),
    backdrop=make,
    noise=("·.-/\\|", ".-/\\|"),
    boot=(
        "plotting a course through the dark.",
        "stars stretch into lines.",
        "holding at light speed.",
    ),
    meter_empty=("·", "·"),
    title=Title(left="· ──", right="── ·", prompt="» ", cursor="█"),
    accent=7,
    label="white and pale blue, stars streaming from the centre",
)
