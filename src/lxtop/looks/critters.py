"""Critters: a pocket-creature adventure in the tall grass. Patches of grass sway in the wind
and birds cross the sky; every so often a "!" pops over a patch and a little creature peeks
out, blinks, and hides again (see theme.py for the rules every look keeps). An original look
in the spirit of the creature-collecting games, with no creatures copied."""

from __future__ import annotations

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
    GREEN_8,
    MAGENTA_8,
    RED_8,
    WHITE_8,
    YELLOW_8,
    Cell,
    Theme,
    Title,
)

PATCH = (3, 7)  # rows, columns of a grass patch
GRASS = '"wW'
SWAY = 2.0  # sways a second
BIRD_SPEED = 5.0
ENCOUNTER_GAP = (12.0, 25.0)
ALERT_SECONDS = 1.0
PEEK_SECONDS = 4.0
FACES = ("(^.^)", "(^.^)", "(-.-)", "(^o^)")


class Meadow:
    def __init__(self, console: bool, rng: random.Random) -> None:
        self.rng = rng
        self.h = 0
        self.w = 0
        self.patches: list[tuple[int, int, list[str]]] = []  # top, left, the grass chars
        self.birds: list[tuple[int, float]] = []
        self.encounter_at = 0.0
        self.patch = 0

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        rows, cols = PATCH
        self.patches = [
            (
                self.rng.randrange(max(1, h - rows)),
                self.rng.randrange(max(1, w - cols)),
                [self.rng.choice(GRASS) for _ in range(rows * cols)],
            )
            for _ in range(max(1, w // 30))
        ]
        self.birds = [
            (self.rng.randrange(max(1, h // 4)), self.rng.uniform(0, w)) for _ in range(2)
        ]

    def frame(self, now: float) -> list[Cell]:
        if self.h < 1 or self.w < 1:
            return []
        cols = PATCH[1]
        cells: dict[tuple[int, int], tuple[str, int]] = {}
        sway = int(now * SWAY)
        for top, left, grass in self.patches:
            for i, char in enumerate(grass):
                y, x = top + i // cols, left + i % cols
                if (i + sway) % 5 == 0:  # the wind moves through the patch
                    char, tone = ("W" if char != "W" else "w"), FX_MID
                else:
                    tone = FX_DIM
                if 0 <= y < self.h and 0 <= x < self.w:
                    cells[(y, x)] = (char, tone)
        for row, start in self.birds:
            x = int(start - now * BIRD_SPEED) % (self.w + 1) - 1
            if 0 <= x < self.w:
                cells[(row, x)] = ("v" if int(now * 4) % 2 else "^", FX_DIM)
        self._encounter(now, cells)
        return [(y, x, c, tone) for (y, x), (c, tone) in cells.items()]

    def _encounter(self, now: float, cells: dict[tuple[int, int], tuple[str, int]]) -> None:
        """A "!" over a patch, then a creature peeking out of it, then quiet again."""
        if self.encounter_at == 0.0:
            self.encounter_at = now + self.rng.uniform(*ENCOUNTER_GAP)
        t = now - self.encounter_at
        if t < 0:
            return
        if t > ALERT_SECONDS + PEEK_SECONDS:
            self.encounter_at = now + self.rng.uniform(*ENCOUNTER_GAP)
            self.patch = self.rng.randrange(len(self.patches)) if self.patches else 0
            return
        if not self.patches:
            return
        top, left, _ = self.patches[self.patch % len(self.patches)]
        if t < ALERT_SECONDS:
            y, x = top - 1, left + PATCH[1] // 2
            if 0 <= y < self.h and 0 <= x < self.w:
                cells[(y, x)] = ("!", FX_HEAD)
            return
        face = FACES[int(t * 2) % len(FACES)]
        for i, char in enumerate(face):
            x = left + 1 + i
            if 0 <= top < self.h and 0 <= x < self.w:
                cells[(top, x)] = (char, FX_HEAD)


def make(console: bool, rng: random.Random) -> Meadow:
    return Meadow(console, rng)


THEME = Theme(
    name="critters",
    colours={
        1: (231, WHITE_8),  # GREEN: data, bright white like a status box
        2: (220, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (153, CYAN_8),  # CYAN: labels, sky blue (console slot 6, redefined)
        5: (183, MAGENTA_8),  # MAGENTA: secondary, lavender (console slot 5, redefined)
        6: (71, GREEN_8),  # BLUE: frames and quiet text, leaf green (console slot 2, redefined)
        7: (255, WHITE_8),  # WHITE: plain text
        # Grass, birds and creatures stay darker than any text.
        FX_DIM: (22, GREEN_8),
        FX_MID: (28, GREEN_8),
        FX_HEAD: (64, GREEN_8),
        BACKGROUND: (255, WHITE_8),
        FX_GLASS: (22, GREEN_8),
        FX_GLASS_HEAD: (64, GREEN_8),
    },
    background=BLACK,
    frame="╭╮╰╯─│",
    tick_ms=100,
    panels=True,
    glass=234,
    console_palette=(
        (BLUE_8, "14201a"),  # glass: a dusky meadow under the panels
        (8, "2a5a10"),  # the console draws every effect dim in slot 8: deep grass
        (GREEN_8, "5faf5f"),  # leaf green
        (8 + GREEN_8, "8fd08f"),
        (MAGENTA_8, "d7afff"),  # lavender
        (8 + MAGENTA_8, "e8d0ff"),
        (CYAN_8, "afd7ff"),  # sky blue
        (8 + CYAN_8, "d0e8ff"),
    ),
    backdrop=make,
    meter_empty=("·", "·"),
    noise=('"wW!v', '"wW!v'),
    boot=("a wild server appeared!", "go, servers!", "it's super effective."),
    title=Title(left="▶ ", right="", prompt="", cursor="▼"),
    accent=4,
    label="tall grass adventure: swaying grass and shy creatures",
)
