"""Aquarium: the dashboard as a fish tank. Sea blues and teals on deep blue-black, orange
accents, small fish swimming sideways, bubbles rising, seaweed swaying from the bottom row, a
crab that scuttles along the floor now and then, and rarely a big slow fish crossing the tank
(see matrix.py for the model look and theme.py for the rules every look keeps)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

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

# All of these exist in the console font (the degree sign is U+00B0).
SMALL_RIGHT, SMALL_LEFT = "><>", "<><"
BIG_RIGHT, BIG_LEFT = "><(((°>", "<°)))><"
FISH_PER_CELL = 1 / 900
BUBBLES_PER_CELL = 1 / 450
WEED_EVERY = 13  # about one strand of seaweed per this many columns
CRAB_LEFT, CRAB_RIGHT = "/o\\", "\\o/"  # the two leg positions
CRAB_EVERY = (30.0, 80.0)  # seconds between crab walks
WHALE_RIGHT, WHALE_LEFT = "><((((((((°>", "<°))))))))><"
WHALE_EVERY = (150.0, 400.0)  # seconds between the big fish


@dataclass
class Fish:
    row: int
    x: float  # column of the leftmost cell
    speed: float  # columns per second
    heading: int  # +1 swims right, -1 swims left
    big: bool
    tone: int
    turn_in: float  # seconds until it turns round

    def shape(self) -> str:
        if self.big:
            return BIG_RIGHT if self.heading > 0 else BIG_LEFT
        return SMALL_RIGHT if self.heading > 0 else SMALL_LEFT


@dataclass
class Bubble:
    col: int
    y: float  # row, counted from the top; rises
    speed: float  # rows per second
    phase: float


@dataclass
class Weed:
    col: int
    height: int
    phase: float


@dataclass
class Crab:
    x: float
    heading: int
    leg: int = 0
    run: float = 1.0  # seconds of walking left before a pause
    rest: float = 0.0  # seconds of standing still left


@dataclass
class Whale:
    row: int
    x: float
    heading: int

    def shape(self) -> str:
        return WHALE_RIGHT if self.heading > 0 else WHALE_LEFT


class Tank:
    """Fish that swim along their row at their own pace, now and then turn round, and bubbles
    that rise from the bottom, growing from a dot to a ring."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.h = 0
        self.w = 0
        self.fish: list[Fish] = []
        self.bubbles: list[Bubble] = []
        self.last: float | None = None
        self.clock = 0.0
        self.weeds: list[Weed] = []
        self.crab: Crab | None = None
        self.whale: Whale | None = None
        self.next_crab = self.rng.uniform(8.0, 30.0)
        self.next_whale = self.rng.uniform(40.0, 120.0)

    def _fish(self, scatter: bool) -> Fish:
        r = self.rng
        big = r.random() < 0.2
        heading = r.choice((-1, 1))
        size = len(BIG_RIGHT if big else SMALL_RIGHT)
        edge = -float(size) if heading > 0 else float(self.w)
        x = r.uniform(-size, self.w) if scatter else edge
        tone = FX_HEAD if big or r.random() < 0.25 else FX_MID
        return Fish(
            row=r.randrange(self.h),
            x=x,
            speed=r.uniform(2.0, 5.0) if big else r.uniform(3.0, 9.0),
            heading=heading,
            big=big,
            tone=tone,
            turn_in=r.uniform(15.0, 60.0),
        )

    def _bubble(self, scatter: bool) -> Bubble:
        r = self.rng
        y = r.uniform(0, self.h) if scatter else self.h - 1 + r.uniform(0, 4)
        return Bubble(r.randrange(self.w), y, r.uniform(1.5, 4.5), r.uniform(0, math.tau))

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        self.fish = [self._fish(True) for _ in range(max(1, int(h * w * FISH_PER_CELL)))]
        self.bubbles = [self._bubble(True) for _ in range(max(1, int(h * w * BUBBLES_PER_CELL)))]
        tall = max(1, min(8, h // 4))
        self.weeds = [
            Weed(
                min(w - 1, int(c + self.rng.uniform(0, WEED_EVERY))),
                self.rng.randint(max(1, tall // 2), tall),
                self.rng.uniform(0, math.tau),
            )
            for c in range(0, w, WEED_EVERY)
        ]
        self.crab = None
        self.whale = None

    def _advance(self, dt: float) -> None:
        for i, fish in enumerate(self.fish):
            fish.x += fish.heading * fish.speed * dt
            fish.turn_in -= dt
            if fish.turn_in <= 0:
                fish.heading = -fish.heading
                fish.turn_in = self.rng.uniform(25.0, 70.0)
            size = len(fish.shape())
            if (fish.heading > 0 and fish.x >= self.w) or (fish.heading < 0 and fish.x + size <= 0):
                fresh = self._fish(False)
                fresh.heading = fish.heading
                fresh.x = -float(size) if fish.heading > 0 else float(self.w)
                self.fish[i] = fresh
        for i, bubble in enumerate(self.bubbles):
            bubble.y -= bubble.speed * dt
            if bubble.y < -1:
                self.bubbles[i] = self._bubble(False)

    def _events(self, dt: float) -> None:
        """The rare visitors: one crab on the floor and one big fish at a time, each gone once it
        has left the tank."""
        r = self.rng
        crab = self.crab
        if crab is None:
            if self.clock >= self.next_crab:
                heading = r.choice((-1, 1))
                self.crab = Crab(-3.0 if heading > 0 else float(self.w), heading)
                self.next_crab = math.inf
        else:
            if crab.rest > 0:
                crab.rest -= dt
            else:
                crab.x += crab.heading * 7.0 * dt
                crab.run -= dt
                if crab.run <= 0:
                    crab.rest, crab.run = r.uniform(0.4, 2.0), r.uniform(0.6, 2.0)
            crab.leg = int(crab.x * 1.5) & 1
            if crab.x > self.w + 1 or crab.x < -4:
                self.crab = None
                self.next_crab = self.clock + r.uniform(*CRAB_EVERY)
        whale = self.whale
        size = len(WHALE_RIGHT)
        if whale is None:
            if self.clock >= self.next_whale:
                heading = r.choice((-1, 1))
                row = r.randrange(self.h // 4, max(self.h // 4 + 1, self.h * 3 // 4))
                self.whale = Whale(
                    min(row, self.h - 1), -float(size) if heading > 0 else self.w, heading
                )
                self.next_whale = math.inf
        else:
            whale.x += whale.heading * 2.5 * dt
            if whale.x > self.w or whale.x + size < 0:
                self.whale = None
                self.next_whale = self.clock + r.uniform(*WHALE_EVERY)

    def frame(self, now: float) -> list[Cell]:
        dt = 0.0 if self.last is None else max(0.0, min(1.0, now - self.last))
        self.last = now
        if not self.h or not self.w:
            return []
        self._advance(dt)
        self.clock += dt
        self._events(dt)
        cells: dict[tuple[int, int], tuple[str, int]] = {}
        # Ripples on the surface, drifting along the top row.
        shift = int(self.clock * 2.0)
        for col in range(self.w):
            if (col - shift) % 9 < 2:
                cells[(0, col)] = ("~", FX_DIM)
        for weed in self.weeds:
            for k in range(min(weed.height, self.h)):
                lean = math.sin(self.clock * 0.9 + weed.phase + k * 0.5)
                col = weed.col + (round(lean * min(1.0, k * 0.5)) if k else 0)
                char = "(" if lean < -0.35 else ")" if lean > 0.35 else "|"
                if 0 <= col < self.w:
                    cells[(self.h - 1 - k, col)] = (char, FX_MID if k % 2 else FX_DIM)
        for bubble in self.bubbles:
            row = int(bubble.y)
            if not 0 <= row < self.h:
                continue
            col = bubble.col + round(0.6 * math.sin(bubble.y * 0.7 + bubble.phase))
            rise = (self.h - 1 - bubble.y) / max(1, self.h - 1)
            char, tone = (
                (".", FX_DIM) if rise < 0.35 else ("o", FX_DIM) if rise < 0.7 else ("°", FX_MID)
            )
            if 0 <= col < self.w:
                cells[(row, col)] = (char, tone)
        for fish in self.fish:
            left = math.floor(fish.x)
            for i, char in enumerate(fish.shape()):
                if 0 <= left + i < self.w:
                    cells[(fish.row, left + i)] = (char, fish.tone)
        crab = self.crab
        if crab is not None:
            legs = CRAB_RIGHT if crab.leg else CRAB_LEFT
            for i, char in enumerate(legs):
                if 0 <= math.floor(crab.x) + i < self.w:
                    cells[(self.h - 1, math.floor(crab.x) + i)] = (char, FX_HEAD)
        whale = self.whale
        if whale is not None:
            for i, char in enumerate(whale.shape()):
                if 0 <= math.floor(whale.x) + i < self.w:
                    cells[(whale.row, math.floor(whale.x) + i)] = (char, FX_HEAD)
        return [(y, x, c, t) for (y, x), (c, t) in cells.items()]


def tank(console: bool, rng: random.Random) -> Tank:
    return Tank(rng)


THEME = Theme(
    name="aquarium",
    colours={
        1: (86, 2),  # GREEN: data, sea green (console slot 2, redefined)
        2: (226, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (117, WHITE_8),  # CYAN: labels, pale water blue
        5: (208, 5),  # MAGENTA: upload, orange (console slot 5, redefined)
        6: (31, 6),  # BLUE: frames and quiet text, teal (console slot 6, redefined)
        7: (195, WHITE_8),  # WHITE: foam white
        # The tank stays quieter than any text: teal fish, dark orange fish, dim bubbles.
        FX_DIM: (24, BLACK),
        FX_MID: (30, BLACK),
        FX_HEAD: (130, BLACK),
        BACKGROUND: (195, WHITE_8),
        FX_GLASS: (23, BLACK),
        FX_GLASS_HEAD: (94, BLACK),
    },
    background=BLACK,
    frame="╭╮╰╯─│",
    tick_ms=150,
    panels=True,
    glass=17,
    console_palette=(
        (BLUE_8, "06183a"),  # glass: deep blue under the panels
        (8, "1a5a78"),  # the console draws all effects here: dim sea blue
        (2, "20d0a0"),  # sea green
        (5, "ff8c1a"),  # orange
        (6, "2a9ab8"),  # teal
        (WHITE_8, "c6ecf6"),  # foam
        (8 + WHITE_8, "f0ffff"),  # bold foam
    ),
    backdrop=tank,
    glitch=False,
    noise=("<>o~°", "<>o~°"),
    meter_empty=("≈", "~"),
    boot=("filling the tank.", "feeding the fish.", "all hosts swimming.", "mind the crab."),
    title=Title(left="~ ><>", right="<>< ~", prompt="~ ", cursor="o"),
    accent=4,
    label="a fish tank: swaying weed, orange fish, bubbles, a crab",
)
