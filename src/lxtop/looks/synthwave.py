"""Synthwave: hot magenta, cyan and purple on a night-black screen, an outrun grid floor that
scrolls toward the viewer under a striped setting sun and twinkling stars (see theme.py for the
rules every look keeps)."""

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

LINES = 4  # horizontal grid lines on the floor at once
RUN_SECONDS = 1.6  # how long one line takes to move one line-spacing toward the viewer
VERTICALS = 3  # converging lines on each side of the centre one
SUN_ROWS = 10  # at most this many rows tall (a half disc, twice as wide as tall)
SUN_SECONDS = 7.0  # the sun's stripes take this long to slide down one stripe
EVENT_FIRST = (3.0, 8.0)  # seconds until the first rare event
EVENT_EVERY = (14.0, 28.0)  # seconds between rare events
STAR_SECONDS = 1.3  # a shooting star's flight
STREAK_SECONDS = 2.6  # a neon streak's run along the horizon
STREAK_TAIL = 12  # cells behind the streak's head

Pos = tuple[int, int]
Painted = dict[Pos, tuple[str, int]]


class Outrun:
    """A perspective floor in the bottom third (lines drift down and spread apart, lines fan out
    from the horizon centre), a striped sun sinking into the horizon centre (its gaps widen
    toward the bottom and slide down), twinkling stars above, and now and then a shooting star
    or a neon streak along the horizon."""

    def __init__(self, console: bool, rng: random.Random) -> None:
        self.console = console
        self.rng = rng
        self.h = 0
        self.w = 0
        self.stars: list[tuple[int, int, float, float, str]] = []
        self.next_at: float | None = None
        self.event: tuple[str, float, int, int] | None = None  # kind, start, a, b

    @property
    def floor(self) -> int:
        """Rows of floor: the bottom third."""
        return self.h // 3

    @property
    def horizon(self) -> int:
        return self.h - self.floor

    @property
    def sun(self) -> int:
        """Rows of sun above the horizon (0: none fits)."""
        return min(SUN_ROWS, self.h // 6)

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        self.stars = []
        self.event = None
        self.next_at = None
        if h < 1 or w < 1:
            return
        top = max(1, h // 3)
        for _ in range(max(1, min(44, h * w // 400))):
            self.stars.append(
                (
                    self.rng.randrange(top),
                    self.rng.randrange(w),
                    self.rng.uniform(0, 6.28),
                    self.rng.uniform(0.6, 1.8),
                    self.rng.choice(".+*."),
                )
            )

    def phase(self, now: float) -> float:
        return (now / RUN_SECONDS) % 1.0

    def frame(self, now: float) -> list[Cell]:
        if self.h < 1 or self.w < 1:
            return []
        cells: Painted = {}
        for y, x, shift, speed, char in self.stars:
            v = math.sin(now * speed + shift)
            if v > 0.3:
                cells[(y, x)] = (char, FX_HEAD if v > 0.9 else FX_MID if v > 0.6 else FX_DIM)
        self._sun(now, cells)
        fl = self.floor
        if fl > 0:
            self._floor(now, fl, cells)
        self._events(now, cells)
        return [(y, x, c, tone) for (y, x), (c, tone) in cells.items()]

    def _sun(self, now: float, cells: Painted) -> None:
        r = self.sun
        if r < 1:
            return
        centre = (self.w - 1) / 2
        char = "▒" if self.console else "▓"
        acc = (now / SUN_SECONDS) % 1.0  # the stripes slide down as this grows
        for d in range(1, r + 1):  # d rows above the horizon
            t = (d - 1) / max(1, r - 1)  # 0 at the horizon, 1 at the top
            acc += 0.7 * (1 - t) + 0.12
            if acc >= 1.0:
                acc -= 1.0
                continue  # a gap: wider near the bottom
            half = 2 * math.sqrt(max(0.0, r * r - (d - 0.5) ** 2))
            tone = FX_HEAD if t < 0.45 else FX_MID
            row = self.horizon - d
            for col in range(math.ceil(centre - half), math.floor(centre + half) + 1):
                if 0 <= col < self.w and 0 <= row < self.h:
                    cells[(row, col)] = (char, tone)

    def _floor(self, now: float, fl: int, cells: Painted) -> None:
        horizon = self.horizon
        centre = (self.w - 1) / 2
        spread = max(2.0, self.w / 10)
        for i in range(-VERTICALS, VERTICALS + 1):
            char = "|" if i == 0 else "/" if i < 0 else "\\"
            tone = FX_MID if abs(i) < 2 else FX_DIM
            for row in range(horizon, self.h):
                col = round(centre + i * spread * (row - horizon + 1) / fl)
                if 0 <= col < self.w:
                    cells[(row, col)] = (char, tone)
        bar = "-" if self.console else "─"
        phase = self.phase(now)
        for k in range(LINES):
            depth = (k + phase) / LINES  # 0 at the horizon, 1 at the viewer
            row = min(self.h - 1, horizon + int(depth * depth * fl))
            tone = FX_HEAD if depth > 0.75 else FX_MID if depth > 0.4 else FX_DIM
            step = 1 if depth > 0.3 else 2  # far lines are dashed: they fade into the haze
            for col in range(0, self.w, step):
                cells[(row, col)] = (bar, tone)

    def _events(self, now: float, cells: Painted) -> None:
        """One rare event at a time: a shooting star or a streak along the horizon."""
        if self.next_at is None:
            self.next_at = now + self.rng.uniform(*EVENT_FIRST)
        if self.event is None and now >= self.next_at:
            kind = self.rng.choice(("star", "streak"))
            self.event = (kind, now, self.rng.randrange(max(1, self.w)), self.rng.randrange(2))
            self.next_at = now + self.rng.uniform(*EVENT_EVERY)
        if self.event is None:
            return
        kind, start, a, b = self.event
        age = now - start
        if age < 0 or age > (STAR_SECONDS if kind == "star" else STREAK_SECONDS):
            if age > 0:
                self.event = None
            return
        if kind == "star":
            self._shooting_star(age / STAR_SECONDS, a, cells)
        else:
            self._streak(age / STREAK_SECONDS, b, cells)

    def _shooting_star(self, p: float, x0: int, cells: Painted) -> None:
        rows = max(1, min(self.horizon, self.h // 3))
        trail = ((FX_HEAD, "*"), (FX_HEAD, "/"), (FX_MID, "/"), (FX_MID, "/"), (FX_DIM, "."))
        for i, (tone, char) in enumerate(trail):
            y = round(p * rows) - i
            x = x0 - round(p * rows * 2) + 2 * i
            if 0 <= y < rows and 0 <= x < self.w:
                cells[(y, x)] = (char, tone)

    def _streak(self, p: float, right: int, cells: Painted) -> None:
        row = self.horizon - 1
        if row < 0 or self.h < 3:
            return
        bar = "-" if self.console else "━"
        span = self.w + 2 * STREAK_TAIL
        head = round(p * span) - STREAK_TAIL
        for i in range(STREAK_TAIL):
            col = head - i if right else self.w - 1 - head + i
            tone = FX_HEAD if i < 3 else FX_MID if i < 7 else FX_DIM
            if 0 <= col < self.w:
                cells[(row, col)] = (bar if i else ("=" if self.console else "━"), tone)


def make(console: bool, rng: random.Random) -> Outrun:
    return Outrun(console, rng)


THEME = Theme(
    name="synthwave",
    colours={
        1: (51, CYAN_8),  # GREEN: neon cyan data
        2: (226, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (213, MAGENTA_8),  # CYAN: labels, bubblegum pink
        5: (201, MAGENTA_8),  # MAGENTA: upload, hot magenta
        6: (99, GREEN_8),  # BLUE: frames and quiet text, purple (console slot 2 is redefined)
        7: (189, WHITE_8),  # WHITE: pale lavender
        # The grid and stars stay darker than any text: they are the sky, not the news.
        FX_DIM: (54, MAGENTA_8),
        FX_MID: (90, MAGENTA_8),
        FX_HEAD: (125, MAGENTA_8),
        BACKGROUND: (189, WHITE_8),
        FX_GLASS: (54, MAGENTA_8),
        FX_GLASS_HEAD: (90, MAGENTA_8),
    },
    background=BLACK,
    frame="╒╕╘╛═│",
    tick_ms=100,
    panels=True,
    glass=234,
    console_palette=(
        (BLUE_8, "1a0b2e"),  # glass: night violet under the panels
        (8, "6a1b8a"),  # the console draws dim text in slot 8: the grid, deep purple
        (GREEN_8, "9b5cff"),  # purple
        (8 + GREEN_8, "b78cff"),
        (CYAN_8, "00e5ff"),  # neon cyan
        (8 + CYAN_8, "7dfaff"),
        (MAGENTA_8, "ff2bd6"),  # hot magenta
        (8 + MAGENTA_8, "ff7aea"),
        (WHITE_8, "e6d8ff"),  # lavender
        (8 + WHITE_8, "f6f0ff"),
    ),
    backdrop=make,
    noise=("▀▄█▌▐░▒", "-=/\\|*"),
    meter_empty=("·", "·"),
    boot=(
        "rolling out of the city",
        "the grid is awake",
        "the sun sinks into the horizon",
        "pedal to the neon",
    ),
    title=Title(left="▲═", right="═▲", prompt="» ", cursor="█"),
    accent=5,
    label="striped sun, neon grid floor, shooting stars",
)
