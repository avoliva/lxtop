"""Coffee: a cozy coffeehouse. Browns, cream and caramel on espresso dark: wisps of steam curling
up from the bottom, aroma motes drifting, and now and then a slow ripple across a cup. See
matrix.py for the model look and theme.py for the rules every look keeps."""

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

PLUME_HEIGHT = 16  # rows a wisp climbs before it is gone
PLUME_EVERY = 20  # one steam spot per this many columns
RISE = 2.0  # rows per second
MOTE_EVERY = 500  # one drifting aroma mote per this many cells
RIPPLE_EVERY = 37.0  # seconds between ripples on the cup surface (one per window)
RIPPLE_LEN = 10.0  # seconds a ripple lives
# Along a plume, from the bottom: 0 is a curl, 1 a wave, None a gap. It shifts up with time.
PATTERN: tuple[int | None, ...] = (0, None, 1, None, None, 0, None, None, 1, None)


def wisp_kind(d: int, now: float, offset: int = 0) -> int | None:
    """What is `d` rows above the bottom of a plume at `now`: 0 curl, 1 wave, None nothing.
    A wisp keeps its kind as it climbs: kind(d + 1, now + 1 / RISE) == kind(d, now)."""
    return PATTERN[(d - int(now * RISE) + offset) % len(PATTERN)]


def sway(spot: Spot, d: float, now: float) -> float:
    """How far left or right of its spot a plume is `d` rows up: a slow lean of the whole plume
    plus a curl that grows with height, so the path is smooth rather than zig-zag."""
    reach = min(3.5, 0.4 + d * 0.3)
    lean = 1.5 * math.sin(now * 0.23 + spot.phase * 1.7) * min(1.0, d / 8)
    return reach * math.sin(spot.phase + d * 0.45 - now * 0.7) + lean


@dataclass
class Spot:
    col: int
    phase: float
    offset: int


class Steam:
    """Layers: plumes of steam that curl as they climb (glyphs follow the lean of the path), a
    few aroma motes drifting up behind them, and now and then a ripple spreading across the cup
    surface. The steam is a shade brighter low down; everything is darker than any text."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.seed = self.rng.getrandbits(32)
        self.h = 0
        self.w = 0
        self.spots: list[Spot] = []
        self.motes: list[tuple[float, float, float, float]] = []
        self._ripple: tuple[int, float, float, float] | None = None

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        r = self.rng
        count = max(1, w // PLUME_EVERY)
        self.spots = [
            Spot(r.randrange(w), r.uniform(0, math.tau), r.randrange(len(PATTERN)))
            for _ in range(count)
        ]
        # (column, row, rows per second, sway phase)
        self.motes = [
            (r.uniform(0, w), r.uniform(0, h), r.uniform(0.15, 0.5), r.uniform(0, math.tau))
            for _ in range(max(1, h * w // MOTE_EVERY))
        ]
        self._ripple = None

    def ripple_at(self, now: float) -> tuple[float, float, float] | None:
        """(row, column, seconds since it began) of the ripple alive at `now`, if any. One
        window every RIPPLE_EVERY seconds holds at most one, at a seeded time and place."""
        k = math.floor(now / RIPPLE_EVERY)
        if self._ripple is None or self._ripple[0] != k:
            r = random.Random(self.seed * 7919 + k)
            start = k * RIPPLE_EVERY + r.uniform(0, RIPPLE_EVERY - RIPPLE_LEN)
            self._ripple = (k, start, r.uniform(0.35, 0.8) * self.h, r.uniform(0.1, 0.9) * self.w)
        _, start, y, x = self._ripple
        rel = now - start
        return (y, x, rel) if 0 <= rel < RIPPLE_LEN else None

    def frame(self, now: float) -> list[Cell]:
        if not self.h or not self.w:
            return []
        cells: dict[tuple[int, int], tuple[str, int]] = {}
        self._motes(now, cells)
        self._ripples(now, cells)
        self._plumes(now, cells)
        return [(y, x, c, t) for (y, x), (c, t) in cells.items()]

    def _motes(self, now: float, cells: dict[tuple[int, int], tuple[str, int]]) -> None:
        for i, (x, y, speed, phase) in enumerate(self.motes):
            row = int((y - now * speed) % self.h)
            col = int(x + 2.0 * math.sin(now * 0.3 + phase)) % self.w
            cells[(row, col)] = ("." if i % 2 else "'", FX_DIM)

    def _ripples(self, now: float, cells: dict[tuple[int, int], tuple[str, int]]) -> None:
        found = self.ripple_at(now)
        if found is None:
            return
        cy, cx, rel = found
        age = rel / RIPPLE_LEN
        thin = age > 0.65  # the last stretch breaks up into dashes before it is gone
        for scale in (1.0, 0.55):
            if scale < 1 and rel < 2.5:
                continue
            ry = (rel - (0 if scale == 1 else 2.0)) * 0.7 * scale
            rx = ry * 2.2
            if ry < 0.5:
                continue
            tone = FX_DIM if scale < 1 or age > 0.55 else (FX_HEAD if age < 0.25 else FX_MID)
            for i in range(int(rx) * 2 + 1):
                dx = i - int(rx)
                top = ry * math.sqrt(max(0.0, 1 - (dx / rx) ** 2))
                for sign in (-1, 1):
                    self._put(cells, cy + sign * top, cx + dx, "-" if i % 2 else "~", tone, thin)
            for j in range(int(ry) * 2 + 1):
                dy = j - int(ry)
                side = rx * math.sqrt(max(0.0, 1 - (dy / ry) ** 2))
                self._put(cells, cy + dy, cx - side, "(", tone, thin)
                self._put(cells, cy + dy, cx + side, ")", tone, thin)

    def _put(
        self,
        cells: dict[tuple[int, int], tuple[str, int]],
        y: float,
        x: float,
        char: str,
        tone: int,
        thin: bool,
    ) -> None:
        row, col = round(y), round(x)
        if 0 <= row < self.h and 0 <= col < self.w and not (thin and (row + col) % 2):
            cells[(row, col)] = (char, tone)

    def _plumes(self, now: float, cells: dict[tuple[int, int], tuple[str, int]]) -> None:
        height = min(self.h, PLUME_HEIGHT)
        for spot in self.spots:
            for d in range(height):
                kind = wisp_kind(d, now, spot.offset)
                if kind is None:
                    continue
                col = spot.col + round(sway(spot, d, now))
                if not 0 <= col < self.w:
                    continue
                band = min(2, d * 3 // height)
                slope = sway(spot, d + 1, now) - sway(spot, d - 1, now)
                if band == 2:
                    char = "." if kind == 1 else "'"
                elif kind == 1:
                    char = "~"
                elif abs(slope) > 0.7:
                    char = "/" if slope > 0 else "\\"
                else:
                    char = ")" if slope > 0 else "("
                cells[(self.h - 1 - d, col)] = (char, FX_MID if band == 0 else FX_DIM)


def steam(console: bool, rng: random.Random) -> Steam:
    return Steam(rng)


THEME = Theme(
    name="coffee",
    colours={
        1: (180, 2),  # GREEN: data, latte (console slot 2, redefined)
        2: (226, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (138, 5),  # CYAN: labels, dusty roast brown (console slot 5, redefined)
        5: (173, 6),  # MAGENTA: upload, caramel (console slot 6, redefined)
        6: (137, 5),  # BLUE: frames and quiet text, tan mocha
        7: (223, WHITE_8),  # WHITE: cream
        # Every effect stays darker than the quietest text: dim coffee browns.
        FX_DIM: (52, BLACK),
        FX_MID: (94, BLACK),
        FX_HEAD: (130, BLACK),
        BACKGROUND: (223, WHITE_8),
        FX_GLASS: (52, BLACK),
        FX_GLASS_HEAD: (58, BLACK),
    },
    background=BLACK,
    frame="╒╕╘╛═│",
    tick_ms=200,
    panels=True,
    glass=234,
    console_palette=(
        (BLUE_8, "1e140e"),  # glass: espresso under the panels
        (8, "5a3d2a"),  # the console draws all effects here: dark roast
        (2, "e0b88a"),  # latte
        (5, "a07a55"),  # mocha
        (6, "d98e4a"),  # caramel
        (WHITE_8, "f5e6cc"),  # cream
        (8 + WHITE_8, "fff6e4"),  # bold cream
    ),
    backdrop=steam,
    glitch=False,
    noise=("~()'.", "~()'."),
    meter_empty=("·", "·"),
    boot=(
        "grinding the beans.",
        "water hot, filter in.",
        "first cup is pouring.",
        "steam on the window.",
    ),
    title=Title(left="(~ ", right=" ~)", prompt="~ ", cursor="▮"),
    accent=1,
    label="coffeehouse browns, curling steam, slow cup ripples",
)
