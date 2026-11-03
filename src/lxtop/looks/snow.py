"""Snow: a snowy winter night. Ice blue, white and silver on dark navy. Flakes fall at three
depths with a gentle wobble, a gust now and then pushes them sideways, they settle in a thin
drift along the bottom rows that slowly melts away, and once in a long while a quiet, heavier
flurry comes through (see matrix.py for the model look and theme.py for the rules every
look keeps). Every effect colour is quieter than all the text."""

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

# Every character exists in the console font (the dot is U+00B7).
FAR, NEAR, CLOSE = (".",), ("·", "+"), ("*", "+")
FLAKES_PER_CELL = 0.02
PILE_MAX = 2.0  # rows of settled snow in a column
PILE_PER_FLAKE = 0.3  # what one landing flake adds, spread over its column and the two beside
MELT_SECONDS = 45.0  # the drift loses 1/e of its height in this long
FLURRY_EXTRA = 1.2  # a flurry adds up to this many times the usual flakes (stays under 10%)


@dataclass
class Flake:
    x: float
    y: float  # row, counted from the top
    speed: float  # rows per second
    amp: float  # wobble width in columns
    rate: float  # wobble speed
    phase: float
    char: str
    tone: int
    extra: bool = False  # a flurry flake: gone once it lands


class Snowfall:
    """Flakes at three depths: small slow dim ones far away, bigger faster brighter ones near.
    A gust now and then pushes them sideways for a few seconds, the near ones harder."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.h = 0
        self.w = 0
        self.flakes: list[Flake] = []
        self.last: float | None = None
        self.wind = 0.0  # columns per second, for a flake of speed 3
        self.target = 0.0
        self.gust_left = 0.0
        self.next_gust = self.rng.uniform(5.0, 20.0)
        self.pile: list[float] = []  # settled snow per column, in rows
        self.flurry_left = 0.0
        self.flurry_len = 1.0
        self.next_flurry = self.rng.uniform(90.0, 200.0)

    def _flake(self, scatter: bool, extra: bool = False) -> Flake:
        r = self.rng
        depth = r.choices((0, 1, 2), weights=(55, 35, 10))[0]
        speed = (r.uniform(0.8, 1.6), r.uniform(1.8, 2.8), r.uniform(3.0, 4.5))[depth]
        char = r.choice((FAR, NEAR, CLOSE)[depth])
        tone = (FX_DIM, FX_MID, FX_HEAD)[depth]
        y = r.uniform(0, self.h) if scatter else -r.uniform(0, 3)
        return Flake(
            r.uniform(0, self.w), y, speed, r.uniform(0.5, 1.5), r.uniform(0.8, 2.0),
            r.uniform(0, math.tau), char, tone, extra,
        )  # fmt: skip

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        self.flakes = [self._flake(True) for _ in range(max(1, int(h * w * FLAKES_PER_CELL)))]
        self.pile = [0.0] * w
        self.flurry_left = 0.0

    def _land(self, flake: Flake) -> None:
        col = int(flake.x) % self.w
        for dx, share in ((-1, 0.25), (0, 0.5), (1, 0.25)):
            c = (col + dx) % self.w
            self.pile[c] = min(PILE_MAX, self.pile[c] + PILE_PER_FLAKE * share * 2)

    def _flurry(self, dt: float) -> float:
        """The strength of the flurry, 0..1: a rare quiet stretch of heavier, steadier snow."""
        if self.flurry_left > 0:
            self.flurry_left -= dt
            if self.flurry_left <= 0:
                self.flurry_left = 0.0
                self.next_flurry = self.rng.uniform(90.0, 200.0)
                return 0.0
        else:
            self.next_flurry -= dt
            if self.next_flurry <= 0 and self.gust_left <= 0:
                self.flurry_len = self.rng.uniform(8.0, 14.0)
                self.flurry_left = self.flurry_len
        if self.flurry_left <= 0:
            return 0.0
        return float(math.sin(math.pi * (1 - self.flurry_left / self.flurry_len)) ** 0.5)

    def _advance(self, dt: float) -> None:
        env = self._flurry(dt)
        self.next_gust -= dt
        if self.gust_left > 0:
            self.gust_left -= dt
            if self.gust_left <= 0:
                self.target = 0.0
        elif self.next_gust <= 0 and self.flurry_left <= 0:
            self.gust_left = self.rng.uniform(3.0, 5.0)
            self.target = self.rng.choice((-1, 1)) * self.rng.uniform(8.0, 16.0)
            self.next_gust = self.rng.uniform(15.0, 40.0)
        self.wind += (self.target - self.wind) * min(1.0, dt * 1.5)
        keep = math.exp(-dt / MELT_SECONDS)
        self.pile = [p * keep for p in self.pile]
        alive: list[Flake] = []
        extras = 0
        for flake in self.flakes:
            flake.y += flake.speed * (1 + 0.3 * env) * dt
            flake.x = (flake.x + self.wind * flake.speed / 3 * dt) % self.w
            if flake.y >= self.h:
                self._land(flake)
                if flake.extra:
                    continue
                flake = self._flake(False)
            extras += flake.extra
            alive.append(flake)
        self.flakes = alive
        base = max(1, int(self.h * self.w * FLAKES_PER_CELL))
        want = int(base * FLURRY_EXTRA * env)
        for _ in range(min(max(0, want - extras), max(1, base // 8))):
            self.flakes.append(self._flake(False, True))

    def frame(self, now: float) -> list[Cell]:
        dt = 0.0 if self.last is None else max(0.0, min(1.0, now - self.last))
        self.last = now
        if not self.h or not self.w:
            return []
        self._advance(dt)
        cells: dict[tuple[int, int], tuple[str, int]] = {}
        for col, height in enumerate(self.pile):
            if height < 0.15:
                continue
            cells[(self.h - 1, col)] = (".", FX_DIM) if height < 0.5 else (":", FX_MID)
            if height >= 1.2 and self.h > 1:
                cells[(self.h - 2, col)] = (".", FX_DIM) if height < 1.6 else (":", FX_DIM)
        for flake in self.flakes:
            row = int(flake.y)
            if row < 0:
                continue
            col = int(flake.x + flake.amp * math.sin(flake.phase + flake.rate * now)) % self.w
            cells[(row, col)] = (flake.char, flake.tone)
        return [(y, x, c, t) for (y, x), (c, t) in cells.items()]


def snowfall(console: bool, rng: random.Random) -> Snowfall:
    return Snowfall(rng)


THEME = Theme(
    name="snow",
    colours={
        1: (117, 6),  # GREEN: data, ice blue (console slot 6, redefined)
        2: (226, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (110, 2),  # CYAN: labels, steel blue (console slot 2, redefined)
        5: (147, 5),  # MAGENTA: upload, periwinkle (console slot 5, redefined)
        6: (67, 2),  # BLUE: frames and quiet text, slate blue
        7: (255, WHITE_8),  # WHITE: snow white
        # The snow stays darker than all text (contrast on black 3.5 / 4.1 / 4.6, on the glass
        # at most 3.97; the quietest text is 4.5): slate, periwinkle, cold grey for the near ones.
        FX_DIM: (60, BLACK),
        FX_MID: (62, BLACK),
        FX_HEAD: (243, BLACK),
        BACKGROUND: (255, WHITE_8),
        FX_GLASS: (59, BLACK),
        FX_GLASS_HEAD: (61, BLACK),
    },
    background=BLACK,
    frame="┏┓┗┛━┃",
    tick_ms=150,
    panels=True,
    glass=17,
    console_palette=(
        (BLUE_8, "0a1230"),  # glass: dark navy under the panels
        (8, "3a4a6c"),  # the console draws all effects here: grey-blue
        (2, "6f9bc9"),  # steel blue
        (5, "aaaaf0"),  # periwinkle
        (6, "9fe0ff"),  # ice blue
        (WHITE_8, "eef4ff"),  # snow
        (8 + WHITE_8, "ffffff"),  # bold snow
    ),
    backdrop=snowfall,
    glitch=False,
    noise=("*+.", "*+."),
    meter_empty=("·", "·"),
    boot=("shaking off the snow.", "all hosts tucked in.", "the servers are warm."),
    title=Title(left="·:*", right="*:·", prompt="+ ", cursor="▮"),
    accent=1,
    label="a snowy night: flakes, a melting drift, a rare flurry",
)
