"""Dungeon: a top-down quest by torchlight. Torches flicker on the walls, bats flap across the
dark and a lone adventurer wanders the stone floor. Now and then a treasure chest appears,
sparkling, until the adventurer moves on (see theme.py for the rules every look keeps). An
original look in the spirit of the old top-down adventure games."""

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
    GREEN_8,
    MAGENTA_8,
    RED_8,
    WHITE_8,
    YELLOW_8,
    Cell,
    Theme,
    Title,
)

TORCH_EVERY = 34  # columns between torches
FLAME = "*^'^"
FLOOR = 0.015  # share of cells with a floor stone
BATS = 2
BAT_SPEED = 6.0  # columns a second
STEP = 0.35  # seconds per adventurer step
CHEST_GAP = (25.0, 50.0)
CHEST_SECONDS = 8.0


class Dungeon:
    def __init__(self, console: bool, rng: random.Random) -> None:
        self.rng = rng
        self.h = 0
        self.w = 0
        self.stones: list[tuple[int, int]] = []
        self.bats: list[tuple[int, float, float]] = []  # row, start column, phase
        self.hero = (0, 0)
        self.stepped = 0.0
        self.chest_at = 0.0
        self.chest = (0, 0)

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        n = int(h * w * FLOOR)
        self.stones = [(self.rng.randrange(h), self.rng.randrange(w)) for _ in range(n)]
        self.bats = [
            (self.rng.randrange(max(1, h)), self.rng.uniform(0, w), self.rng.uniform(0, 6.28))
            for _ in range(BATS)
        ]
        self.hero = (h // 2, w // 2)

    def torches(self) -> list[tuple[int, int]]:
        rows = sorted({self.h // 4, (3 * self.h) // 4})
        return [(y, x) for y in rows for x in range(TORCH_EVERY // 2, self.w, TORCH_EVERY)]

    def walk(self, now: float) -> None:
        while now - self.stepped >= STEP:
            self.stepped = now if now - self.stepped > 10 * STEP else self.stepped + STEP
            y, x = self.hero
            dy, dx = self.rng.choice(((0, 1), (0, -1), (1, 0), (-1, 0), (0, 1), (0, -1)))
            self.hero = (min(self.h - 1, max(0, y + dy)), min(self.w - 1, max(0, x + dx)))

    def frame(self, now: float) -> list[Cell]:
        if self.h < 1 or self.w < 1:
            return []
        cells: dict[tuple[int, int], tuple[str, int]] = {}
        for y, x in self.stones:
            cells[(y, x)] = ("·", FX_DIM)
        for i, (y, x) in enumerate(self.torches()):
            flicker = int(now * 7 + i * 3)
            cells[(y, x)] = (FLAME[flicker % len(FLAME)], FX_HEAD)
            if flicker % 3:  # the glow comes and goes
                for dx in (-1, 1):
                    if 0 <= x + dx < self.w:
                        cells[(y, x + dx)] = ("·", FX_MID)
        for row, start, phase in self.bats:
            left = int(start + now * BAT_SPEED) % (self.w + 3) - 3
            y = min(self.h - 1, max(0, row + round(math.sin(now * 2 + phase))))
            wings = "^v^" if int(now * 5 + phase) % 2 else "-v-"
            for i, char in enumerate(wings):
                if 0 <= left + i < self.w:
                    cells[(y, left + i)] = (char, FX_MID)
        self._chest(now, cells)
        self.walk(now)
        cells[self.hero] = ("@", FX_HEAD)
        return [(y, x, c, tone) for (y, x), (c, tone) in cells.items()]

    def _chest(self, now: float, cells: dict[tuple[int, int], tuple[str, int]]) -> None:
        if self.chest_at == 0.0:
            self.chest_at = now + self.rng.uniform(*CHEST_GAP)
        if now < self.chest_at:
            return
        if now - self.chest_at > CHEST_SECONDS:
            self.chest_at = now + self.rng.uniform(*CHEST_GAP)
            self.chest = (0, 0)
            return
        if self.chest == (0, 0):
            self.chest = (
                self.rng.randrange(1, max(2, self.h)),
                self.rng.randrange(max(1, self.w - 3)),
            )
        y, x = self.chest
        for i, char in enumerate("[■]"):
            if 0 <= y < self.h and 0 <= x + i < self.w:
                cells[(y, x + i)] = (char, FX_MID)
        if int(now * 4) % 2 and 0 <= y - 1 < self.h and 0 <= x + 1 < self.w:
            cells[(y - 1, x + 1)] = ("¤", FX_HEAD)


def make(console: bool, rng: random.Random) -> Dungeon:
    return Dungeon(console, rng)


THEME = Theme(
    name="dungeon",
    colours={
        1: (120, GREEN_8),  # GREEN: data, potion green
        2: (220, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (180, MAGENTA_8),  # CYAN: labels, parchment (console slot 5, redefined)
        5: (81, CYAN_8),  # MAGENTA: secondary, magic blue (console slot 6, redefined)
        6: (245, WHITE_8),  # BLUE: frames and quiet text, stone grey
        7: (253, WHITE_8),  # WHITE: plain text
        # Torches, bats and floor stones stay darker than any text.
        FX_DIM: (238, WHITE_8),
        FX_MID: (94, YELLOW_8),
        FX_HEAD: (130, YELLOW_8),
        BACKGROUND: (253, WHITE_8),
        FX_GLASS: (238, WHITE_8),
        FX_GLASS_HEAD: (94, YELLOW_8),
    },
    background=BLACK,
    frame="┏┓┗┛━┃",
    tick_ms=100,
    panels=True,
    glass=234,
    console_palette=(
        (BLUE_8, "1c1a16"),  # glass: smoky stone under the panels
        (8, "6a4010"),  # the console draws every effect dim in slot 8: torch amber
        (GREEN_8, "87ff87"),  # potion green
        (8 + GREEN_8, "b8ffb8"),
        (MAGENTA_8, "d7af87"),  # parchment
        (8 + MAGENTA_8, "e8c8a0"),
        (CYAN_8, "5fd7ff"),  # magic blue
        (8 + CYAN_8, "a0e8ff"),
    ),
    backdrop=make,
    meter_empty=("·", "·"),
    noise=("*^·¤@", "*^·¤@"),
    boot=("you enter the dungeon.", "a torch flickers.", "the servers explore."),
    title=Title(left="♦♦♦ ", right=" ♦", prompt="▸ ", cursor="▮"),
    accent=4,
    label="torchlit dungeon: flickering torches, bats and treasure",
)
