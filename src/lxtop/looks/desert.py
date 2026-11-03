"""Desert: amber, ochre and sand on dark brown. Grains blow left to right in gusts over a low
dune silhouette along the bottom rows that creeps with the wind, and now and then a long bulge
travels slowly under the sand, as if something large moved below (see theme.py for the rules
every look keeps)."""

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

GUST_SECONDS = 10.0  # one rise and fall of the wind
RIPPLE_EVERY = 50.0
RIPPLE_CROSSING = 22.0  # seconds a ripple takes to cross
DUNE_ROWS = 3  # the silhouette is at most this tall
DUNE_CREEP = 0.6  # columns per second the dunes shift at full wind
GRAINS = (".", ",", "-")  # slow, middling, fast
TONES = (FX_DIM, FX_MID, FX_HEAD)


class Sand:
    """Grains drifting right at a speed set by the wind, wrapping round; how many show follows
    the gust too. A ripple crosses once a minute."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.seed = rng.getrandbits(32)
        self.gust_phase = rng.uniform(0, 2 * math.pi)
        self.ripple_offset = rng.uniform(0, RIPPLE_EVERY)
        self.h = 0
        self.w = 0
        self.grains: list[list[float]] = []  # row, column, speed (columns per second), kind
        self.last: float | None = None
        self.drift = 0.0  # how far the dunes have crept, in columns

    def resize(self, h: int, w: int) -> None:
        self.h, self.w = h, w
        self.grains = []
        self.last = None
        self.drift = 0.0
        if h < 1 or w < 1:
            return
        r = self.rng
        n = max(2, min(300, h * w // 50))
        for _ in range(n):
            kind = r.choice((0, 0, 1, 1, 2))
            speed = (4.0, 9.0, 18.0)[kind] * r.uniform(0.8, 1.25)
            self.grains.append([float(r.randrange(h)), r.uniform(0, w), speed, float(kind)])

    def gust(self, now: float) -> float:
        """0 (calm) to 1 (full gust), a smooth swell every GUST_SECONDS."""
        return 0.5 + 0.5 * math.sin(2 * math.pi * now / GUST_SECONDS + self.gust_phase)

    def wind(self, now: float) -> float:
        return 0.3 + 0.7 * self.gust(now)

    def density(self, now: float) -> float:
        """The share of the grains showing at `now`."""
        return 0.1 + 0.9 * self.gust(now)

    def dune_height(self, x: int) -> int:
        """Rows of dune in column `x` (0 to the cap); the profile slides with the wind."""
        cap = min(DUNE_ROWS, self.h // 3)
        if cap < 1:
            return 0
        u = x - self.drift
        v = (
            0.55
            + 0.3 * math.sin(u / 11.0 + 1.0)
            + 0.2 * math.sin(u / 4.3)
            + 0.1 * math.sin(u / 1.9)
        )
        return max(0, min(cap, round(v * (cap + 0.6))))

    def dunes(self) -> list[Cell]:
        out: list[Cell] = []
        for x in range(self.w):
            height = self.dune_height(x)
            if height < 1:
                continue
            out.append((self.h - height, x, "▒", FX_MID))  # the crest
            if height > 1:
                out.append((self.h - 1, x, "░", FX_DIM))  # one shaded row at the foot
        return out

    def ripple(self, now: float) -> list[Cell]:
        """The bulge while it crosses (head first): a long mound pushing up the sand, else
        nothing. Two cells a column at most, so it is bounded by twice its length."""
        if self.h < 1 or self.w < 1:
            return []
        shifted = now + self.ripple_offset
        t = shifted % RIPPLE_EVERY
        if t >= RIPPLE_CROSSING:
            return []
        length = min(90, max(10, self.w // 2))
        head = t / RIPPLE_CROSSING * (self.w + length)
        r = random.Random((self.seed << 12) ^ (int(shifted // RIPPLE_EVERY) & 0xFFF))
        row = int(self.h * r.uniform(0.3, 0.75))
        amp = min(3, max(1, self.h // 8))
        out: list[Cell] = []
        for i in range(length):
            x = int(head) - i
            if not 0 <= x < self.w:
                continue
            swell = math.sin(math.pi * (i + 0.5) / length)  # 0 at the ends, 1 mid-body
            lift = round(amp * swell * (0.8 + 0.2 * math.sin(now * 1.3 - x / 5.0)))
            y = min(self.h - 1, max(0, row - lift))
            tone = FX_HEAD if i < 3 or abs(i - length / 2) < 2 else FX_MID
            out.append((y, x, "≈" if (x + int(now * 2)) % 3 else "~", tone))
            if lift > 0 and y + 1 < self.h:  # the bulge's shadow
                out.append((y + 1, x, "-", FX_DIM))
        return out

    def frame(self, now: float) -> list[Cell]:
        if self.h < 1 or self.w < 1:
            return []
        dt = 0.0 if self.last is None else max(0.0, min(1.0, now - self.last))
        self.last = now
        wind = self.wind(now)
        self.drift += DUNE_CREEP * wind * dt
        shown = int(len(self.grains) * self.density(now))
        out: dict[tuple[int, int], Cell] = {}
        for cell in self.dunes():
            out[(cell[0], cell[1])] = cell
        for i, grain in enumerate(self.grains):
            grain[1] = (grain[1] + grain[2] * wind * dt) % self.w
            if i < shown:
                kind = int(grain[3])
                y, x = int(grain[0]), int(grain[1])
                out[(y, x)] = (y, x, GRAINS[kind], TONES[kind])
        for cell in self.ripple(now):
            out[(cell[0], cell[1])] = cell
        return list(out.values())


def make(console: bool, rng: random.Random) -> Sand:
    return Sand(rng)


THEME = Theme(
    name="desert",
    colours={
        1: (172, GREEN_8),  # GREEN: ochre data
        2: (226, YELLOW_8),  # YELLOW: still a warning, a bright lemon against the ochre
        3: (196, RED_8),  # RED: still an alarm
        4: (180, CYAN_8),  # CYAN: labels, tan
        5: (137, MAGENTA_8),  # MAGENTA: upload, clay
        6: (101, MAGENTA_8),  # BLUE: frames and quiet text, dry khaki
        7: (223, WHITE_8),  # WHITE: sand
        # The grains stay darker than any text: they are the background, not the news.
        FX_DIM: (52, MAGENTA_8),
        FX_MID: (58, MAGENTA_8),
        FX_HEAD: (94, MAGENTA_8),
        BACKGROUND: (101, MAGENTA_8),
        FX_GLASS: (52, MAGENTA_8),
        FX_GLASS_HEAD: (58, MAGENTA_8),
    },
    background=BLACK,
    frame="╒╕╘╛═│",
    tick_ms=120,
    panels=True,
    glass=233,
    console_palette=(
        (BLUE_8, "140d08"),  # glass: a brown-black under the panels
        (8, "5c3d1c"),  # the sand, dark brown
        (GREEN_8, "c8761c"),  # ochre
        (8 + GREEN_8, "e8a040"),
        (MAGENTA_8, "a86a40"),  # clay
        (8 + MAGENTA_8, "c88c5c"),
        (CYAN_8, "d8b078"),  # tan
        (8 + CYAN_8, "ecd0a0"),
        (WHITE_8, "f0dcb0"),  # sand
        (8 + WHITE_8, "fff0cc"),
    ),
    backdrop=make,
    noise=("~≈-.,'`░▒", "~-.,'`"),
    meter_empty=("·", "·"),
    boot=(
        "wind from the west.",
        "sand in the hinges.",
        "something moves under the dunes.",
        "keep your water close.",
    ),
    title=Title(left="░≈", right="≈░", prompt="> ", cursor="▮"),
    accent=1,
    label="amber sand, gusting grains, creeping dunes, a thing below",
)
