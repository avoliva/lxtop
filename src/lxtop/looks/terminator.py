"""Terminator: a red-tinted machine-vision HUD. Amber and pale-pink text, reticle brackets in
the corners, a scan line down and another across, target locks whose brackets close in, and
now and then a lock box that flashes as if analysing (see theme.py for the rules every look
keeps)."""

from __future__ import annotations

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
    GREEN_8,
    RED_8,
    YELLOW_8,
    Cell,
    Theme,
    Title,
)

SWEEP_PERIOD = 7.0  # seconds from one horizontal sweep's start to the next
SWEEP_TIME = 3.0  # seconds a sweep takes to cross the screen
VSWEEP_PERIOD = 11.0  # the vertical scan line is slower and out of step with the first
VSWEEP_TIME = 5.5
TARGETS = 3
LOCK_IN = 0.9  # seconds a target's brackets take to close in
SPAN_FAR, SPAN_NEAR = 18, 6  # columns between the brackets: first seen, locked
HOLD = (0.8, 1.6)  # seconds a lock holds before it lets go
ANALYSE_EVERY = (18.0, 34.0)  # a rare moment: one lock box flashes as if analysing
ANALYSE_TIME = 0.9
ANALYSE_BLINK = 0.15
RETICLE_PULSE = 6.0  # the corner brackets brighten for a moment this often

# Console palette slots: 5 pale pink, 6 amber, 7 grey, 2 orange (their bold twins 8 higher).
CYAN_8, MAGENTA_8, WHITE_8 = 6, 5, 7


class Scan:
    """A machine-vision HUD: reticle brackets in the corners, a horizontal and a vertical scan
    line, target locks whose brackets close in, and now and then a lock that flashes."""

    def __init__(self, console: bool, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.hline, self.vline = ("-", "|") if console else ("─", "│")
        self.flash_h, self.flash_v = ("=", "|") if console else ("═", "║")
        self.h = 0
        self.w = 0
        self.last = 0.0
        # row, column, born, hold seconds
        self.targets: list[tuple[int, int, float, float]] = []
        self.next_analyse = 0.0
        self.analyse: tuple[int, int, float] | None = None  # row, column, start

    def resize(self, h: int, w: int) -> None:
        if (h, w) != (self.h, self.w):
            self.h, self.w = h, w
            self.targets = []
            self.analyse = None
            self.next_analyse = 0.0

    def _spot(self, now: float) -> tuple[int, int, float, float]:
        r = self.rng
        col = r.randrange(0, max(1, self.w - SPAN_FAR))
        return (r.randrange(0, max(1, self.h)), col, now, r.uniform(*HOLD))

    @staticmethod
    def _span(age: float) -> int:
        """Columns between a lock's brackets: wide, then closing in to SPAN_NEAR."""
        left = max(0.0, 1.0 - age / LOCK_IN)
        return SPAN_NEAR + 2 * round(left * left * (SPAN_FAR - SPAN_NEAR) / 2)

    def frame(self, now: float) -> list[Cell]:
        h, w = self.h, self.w
        if h < 1 or w < 1:
            return []
        if now < self.last:  # the clock restarted: forget the old schedule
            self.targets, self.analyse, self.next_analyse = [], None, 0.0
        self.last = now
        cells: dict[tuple[int, int], tuple[str, int]] = {}

        def put(y: int, x: int, ch: str, tone: int) -> None:
            if 0 <= y < h and 0 <= x < w and tone >= cells.get((y, x), ("", 0))[1]:
                cells[(y, x)] = (ch, tone)

        # Reticle: an L of heavy line in each corner, brighter for a moment now and then.
        tone = FX_MID if now % RETICLE_PULSE < 0.4 else FX_DIM
        for y, x, dy, dx, corner in (
            (0, 0, 1, 1, "┏"),
            (0, w - 1, 1, -1, "┓"),
            (h - 1, 0, -1, 1, "┗"),
            (h - 1, w - 1, -1, -1, "┛"),
        ):
            put(y, x, corner, tone)
            for i in range(1, 4):
                put(y, x + dx * i, "━", tone)
            for i in range(1, 3):
                put(y + dy * i, x, "┃", tone)
        # The vertical scan line, quieter than the horizontal one.
        vphase = now % VSWEEP_PERIOD
        if vphase < VSWEEP_TIME:
            col = min(w - 1, int(vphase / VSWEEP_TIME * w))
            for y in range(h):
                put(y, col, self.vline, FX_MID)
        # The horizontal sweep, with a faint dotted wake.
        phase = now % SWEEP_PERIOD
        if phase < SWEEP_TIME:
            row = min(h - 1, int(phase / SWEEP_TIME * h))
            for x in range(w):
                put(row, x, self.hline, FX_HEAD)
            for x in range(0, w, 2):
                put(row - 1, x, "·", FX_MID)
        # Target locks: brackets close in, hold, let go.
        self.targets = [t for t in self.targets if now - t[2] < LOCK_IN + t[3]]
        while len(self.targets) < TARGETS:
            self.targets.append(self._spot(now))
        for row, col, born, _ in self.targets:
            age = now - born
            span = self._span(age)
            locked = age >= LOCK_IN
            tone = FX_HEAD if locked else FX_MID
            put(row, col, "[", tone)
            put(row, col + span, "]", tone)
            if locked:
                put(row, col + span // 2, "+", FX_HEAD)
            elif age > LOCK_IN / 2:
                put(row, col + span // 2, "·", FX_MID)
        # The rare moment: one lock box blinks its whole outline as if analysing.
        if self.next_analyse == 0.0:
            self.next_analyse = now + self.rng.uniform(*ANALYSE_EVERY)
        if self.analyse is None and now >= self.next_analyse and self.targets:
            row, col, _, _ = self.targets[0]
            self.analyse = (row, col, now)
            self.next_analyse = now + ANALYSE_TIME + self.rng.uniform(*ANALYSE_EVERY)
        if self.analyse is not None:
            row, col, start = self.analyse
            if now - start >= ANALYSE_TIME:
                self.analyse = None
            elif int((now - start) / ANALYSE_BLINK) % 2 == 0:
                for x in range(col, col + SPAN_NEAR + 1):
                    put(row - 2, x, self.flash_h, FX_HEAD)
                    put(row + 2, x, self.flash_h, FX_HEAD)
                for y in range(row - 1, row + 2):
                    put(y, col - 1, self.flash_v, FX_HEAD)
                    put(y, col + SPAN_NEAR + 1, self.flash_v, FX_HEAD)
        return [(y, x, ch, tone) for (y, x), (ch, tone) in cells.items()]


def scan(console: bool, rng: random.Random) -> Scan:
    return Scan(console, rng)


THEME = Theme(
    name="terminator",
    colours={
        1: (214, CYAN_8),  # GREEN: amber readout
        2: (190, YELLOW_8),  # YELLOW: lime-yellow warning, far from the amber
        3: (196, RED_8),  # RED: the only pure saturated red
        4: (217, MAGENTA_8),  # CYAN: labels, pale pink
        5: (173, GREEN_8),  # MAGENTA: upload, burnt salmon
        6: (245, WHITE_8),  # BLUE: frames and quiet text, grey
        7: (252, WHITE_8),  # WHITE: light grey
        # Dark reds, dimmer than any text: the sweep and brackets are background.
        FX_DIM: (52, GREEN_8),
        FX_MID: (88, GREEN_8),
        FX_HEAD: (94, GREEN_8),
        BACKGROUND: (214, CYAN_8),
        FX_GLASS: (52, GREEN_8),
        FX_GLASS_HEAD: (88, GREEN_8),
    },
    background=BLACK,
    frame="┏┓┗┛━┃",
    meter_empty=("·", "·"),
    tick_ms=100,
    panels=True,
    glass=233,
    console_palette=(
        (BLUE_8, "1c0808"),  # glass: a very dark red
        (8, "5a1410"),  # dim text on the console: the effects, dark red
        (GREEN_8, "d9650a"),  # orange
        (8 + GREEN_8, "ff8a2a"),
        (MAGENTA_8, "ffb4b4"),  # pale pink
        (8 + MAGENTA_8, "ffd8d8"),
        (CYAN_8, "ffb000"),  # amber
        (8 + CYAN_8, "ffd060"),
        (WHITE_8, "a8a8a8"),  # grey
        (8 + WHITE_8, "d8d8d8"),
    ),
    backdrop=scan,
    glitch=True,
    noise=("▌▐▀░▒#%&*+<>=/|", "#%&*+<>=/|:"),
    boot=(
        "vision system online",
        "acquiring targets",
        "range: locked, hosts tracked",
        "threat level: none",
    ),
    title=Title(left="┏━[", right="]━┓", prompt="> ", cursor="▌"),
    accent=1,
    label="machine-vision HUD: reticle, scan lines, target locks",
)
