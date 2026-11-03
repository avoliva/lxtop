"""CRT: an amber phosphor terminal on black, a bright band that rolls down the screen every
few seconds and faint static specks (see theme.py for the rules every look keeps)."""

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

ROLL_SECONDS = 6.0  # one pass of the band, top to bottom
BAND = 4  # rows the band travels beyond the screen, so it enters and leaves smoothly
GHOST_SECONDS = 60.0  # a burn-in ghost fades over this long, then a new one appears elsewhere
GHOST_WORDS = ("host", "ready", "login", "host", "load", "disk", "net")
FLICKER_GAP = (14.0, 40.0)  # seconds between bursts of static across a few rows
FLICKER_SECONDS = 0.36
FLICKER_ROWS = (2, 4)
FLICKER_DENSITY = 0.25

Cells = dict[tuple[int, int], tuple[str, int]]


class Roll:
    """Amber phosphor glass: a rolling band (one row of light shade with a dim row each side),
    static specks, a burn-in ghost of old letters that fades away, and now and then a brief
    burst of static across a few rows."""

    def __init__(self, console: bool, rng: random.Random) -> None:
        self.rng = rng
        self.h = 0
        self.w = 0
        self.specks = 0
        self.ghost_cycle: int | None = None
        self.ghost: list[tuple[int, int, str, float]] = []  # row, col, letter, fades out at
        self.flicker_at: float | None = None
        self.flicker_rows: tuple[int, int] = (0, 0)  # first row, row count

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        self.specks = max(0, h * w // 400) if h >= 1 and w >= 1 else 0
        self.ghost_cycle = None  # placed again for the new size on the next frame
        self.flicker_at = None

    def band_row(self, now: float) -> int:
        """The row of the band's bright line at `now` (off screen part of each cycle)."""
        return int((now % ROLL_SECONDS) / ROLL_SECONDS * (self.h + BAND)) - BAND // 2

    def _place_ghost(self) -> None:
        """Three old words burnt in at random places; each letter has its own moment to
        fade, so a word thins out letter by letter."""
        self.ghost = []
        for _ in range(3):
            word = self.rng.choice(GHOST_WORDS)
            row = self.rng.randrange(self.h)
            col = self.rng.randrange(max(1, self.w - len(word) + 1))
            for i, letter in enumerate(word):
                if col + i < self.w:
                    self.ghost.append((row, col + i, letter, self.rng.uniform(0.15, 1.0)))

    def _ghost_cells(self, now: float, cells: Cells) -> None:
        cycle = int(now // GHOST_SECONDS)
        if cycle != self.ghost_cycle:
            self.ghost_cycle = cycle
            self._place_ghost()
        age = (now % GHOST_SECONDS) / GHOST_SECONDS
        for row, col, letter, until in self.ghost:
            if age < until:
                cells[(row, col)] = (letter, FX_DIM)

    def _flicker_cells(self, now: float, cells: Cells) -> None:
        if self.flicker_at is None or now >= self.flicker_at + FLICKER_SECONDS:
            self.flicker_at = now + self.rng.uniform(*FLICKER_GAP)
            count = min(self.h, self.rng.randint(*FLICKER_ROWS))
            self.flicker_rows = (self.rng.randrange(self.h - count + 1), count)
            return
        if now < self.flicker_at:
            return
        first, count = self.flicker_rows
        for row in range(first, first + count):
            for col in range(self.w):
                if self.rng.random() < FLICKER_DENSITY:
                    cells[(row, col)] = (self.rng.choice("▒:;"), FX_DIM)

    def frame(self, now: float) -> list[Cell]:
        if self.h < 1 or self.w < 1:
            return []
        cells: Cells = {}
        self._ghost_cells(now, cells)
        for _ in range(self.specks):  # a fresh handful each frame: static flickers
            tone = FX_MID if self.rng.random() < 0.2 else FX_DIM
            cells[(self.rng.randrange(self.h), self.rng.randrange(self.w))] = (
                self.rng.choice(".,"),
                tone,
            )
        self._flicker_cells(now, cells)
        mid = self.band_row(now)
        for row, tone in ((mid - 1, FX_DIM), (mid + 1, FX_DIM), (mid, FX_MID)):
            if 0 <= row < self.h:
                for col in range(self.w):
                    cells[(row, col)] = ("░", tone)
        return [(y, x, c, tone) for (y, x), (c, tone) in cells.items()]


def make(console: bool, rng: random.Random) -> Roll:
    return Roll(console, rng)


THEME = Theme(
    name="crt",
    colours={
        1: (214, GREEN_8),  # GREEN: bright amber data (console slot 2 is redefined)
        2: (226, YELLOW_8),  # YELLOW: still a warning, clearly yellow beside the amber
        3: (196, RED_8),  # RED: still an alarm
        4: (179, CYAN_8),  # CYAN: labels, soft gold-amber
        5: (208, MAGENTA_8),  # MAGENTA: upload, orange
        6: (130, CYAN_8),  # BLUE: frames and quiet text, burnt amber
        7: (223, WHITE_8),  # WHITE: pale amber
        # Every effect stays below the quietest text (pair 6): they are the glass, not the news.
        FX_DIM: (58, GREEN_8),
        FX_MID: (94, GREEN_8),
        FX_HEAD: (95, GREEN_8),
        BACKGROUND: (223, WHITE_8),
        FX_GLASS: (58, GREEN_8),
        FX_GLASS_HEAD: (94, GREEN_8),
    },
    meter_empty=("·", "·"),
    background=BLACK,
    frame="╓╖╙╜─║",
    tick_ms=120,
    panels=True,
    glass=234,
    console_palette=(
        (BLUE_8, "1a1005"),  # glass: warm black under the panels
        (8, "5a3300"),  # the console draws dim text in slot 8: the roll, dark amber
        (GREEN_8, "ffa81a"),  # amber
        (8 + GREEN_8, "ffc04d"),
        (CYAN_8, "b86a0f"),  # burnt amber
        (8 + CYAN_8, "d98a2a"),
        (MAGENTA_8, "ff7a14"),  # orange
        (8 + MAGENTA_8, "ff9a40"),
        (WHITE_8, "ffd9a0"),  # pale amber
        (8 + WHITE_8, "fff0d6"),
    ),
    backdrop=make,
    noise=("▒░.,:;", "#:;.,"),
    boot=("degaussing the tube", "phosphor warming up", "ready.", "login: host"),
    title=Title(left="▐ ", right=" ▌", prompt="> ", cursor="█"),
    accent=1,
    label="amber phosphor, rolling band, burn-in ghosts, static",
)
