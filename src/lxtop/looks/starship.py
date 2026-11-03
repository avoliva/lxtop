"""Starship: a bridge console in rounded blocks of orange, peach, lavender and periwinkle on
black, with indicator lights, a slow scanner bar and rare alert ripples (see theme.py for the rules
every look keeps)."""

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

PATTERNS = ("1100", "10", "1110100", "100", "11010000", "110", "1000")
STEPS = (0.6, 0.9, 1.2, 1.6)  # seconds per pattern step

Light = tuple[int, int, int, float, float, str, int]  # row, column, width, step, phase, bits, tone


SCAN_SPEED = 7.0  # cells per second: the scanner bar sweeps slowly
SCAN_TRAIL = 5
RIPPLE_SLOT = 18.0  # seconds: each slot may hold one alert ripple
RIPPLE_CHANCE = 0.45
RIPPLE_SPEED = 38.0  # cells per second along the row
RIPPLE_GAP = 2  # a lamp every this many cells
RIPPLE_TAIL = 14  # cells behind the front that still glow


class Lights:
    """A bridge console: rows of indicator blocks that blink in slow patterns, a scanner bar
    that sweeps back and forth along its own row, and now and then an alert ripple, where the
    lamps of one row light up one after another and fade out behind the front."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.seed = rng.getrandbits(32)
        self.h = 0
        self.w = 0
        self.lights: list[Light] = []
        self.rows: list[int] = []
        self.scan_row = -1

    def resize(self, h: int, w: int) -> None:
        self.h, self.w = h, w
        self.lights = []
        self.rows = []
        self.scan_row = -1
        if h < 1 or w < 1:
            return
        r = self.rng
        rows = min(5, max(1, h // 4))
        for k in range(rows):
            y = min(h - 1, (k + 1) * h // (rows + 1))
            self.rows.append(y)
            x = r.randint(0, 3)
            while x < w:
                width = r.choice((1, 2, 2, 3, 4))
                self.lights.append(
                    (
                        y,
                        x,
                        min(width, w - x),
                        r.choice(STEPS),
                        r.uniform(0, 20),
                        r.choice(PATTERNS),
                        r.choice((FX_MID, FX_HEAD)),
                    )
                )
                x += width + r.randint(4, 10)
        # The scanner takes the gap above the first row of lights (or the row itself if none).
        self.scan_row = self.rows[0] // 2 if self.rows[0] >= 2 else -1

    @staticmethod
    def is_on(light: Light, now: float) -> bool:
        _, _, _, step, phase, bits, _ = light
        return bits[int((now + phase) / step) % len(bits)] == "1"

    def scanner(self, now: float) -> list[Cell]:
        """A bright head sweeping to and fro, a fading trail behind it, a dotted track."""
        y, w = self.scan_row, self.w
        if y < 0:
            return []
        out: list[Cell] = [(y, x, "·", FX_DIM) for x in range(0, w, 4)]
        span = max(1, w - 1)
        pos = (now * SCAN_SPEED) % (2 * span)
        forward = pos <= span
        head = min(w - 1, int(pos if forward else 2 * span - pos))
        back = -1 if forward else 1
        out.append((y, head, "■", FX_HEAD))
        for i in range(1, SCAN_TRAIL + 1):
            x = head + back * i
            if 0 <= x < w:
                out.append((y, x, "━" if i <= 2 else "╸" if back < 0 else "╺", FX_MID))
        return out

    def ripple(self, now: float) -> list[Cell]:
        """Rarely, lamps along one row light up in turn, front first, then fade."""
        if not self.rows or self.w < 1:
            return []
        slot = int(now // RIPPLE_SLOT)
        r = random.Random(self.seed * 1009 + slot)
        if r.random() >= RIPPLE_CHANCE:
            return []
        start = slot * RIPPLE_SLOT + r.uniform(0, RIPPLE_SLOT / 3)
        y = r.choice(self.rows)
        flip = r.random() < 0.5
        front = (now - start) * RIPPLE_SPEED
        if front < 0 or front > self.w + RIPPLE_TAIL:
            return []
        out: list[Cell] = []
        for x in range(0, self.w, RIPPLE_GAP):
            behind = front - (self.w - 1 - x if flip else x)
            if 0 <= behind < RIPPLE_TAIL:
                out.append((y, x, "●" if behind < 4 else "■", FX_HEAD if behind < 4 else FX_MID))
        return out

    def frame(self, now: float) -> list[Cell]:
        cells: dict[tuple[int, int], tuple[str, int]] = {}
        for light in self.lights:
            y, x, width, _, _, _, tone = light
            if self.is_on(light, now):
                for i in range(width):
                    cells[(y, x + i)] = ("■", tone)
            else:
                cells[(y, x)] = ("·", FX_DIM)
        for y, x, ch, tone in (*self.scanner(now), *self.ripple(now)):
            cells[(y, x)] = (ch, tone)
        return [(y, x, ch, tone) for (y, x), (ch, tone) in cells.items()]


def make(console: bool, rng: random.Random) -> Lights:
    return Lights(rng)


THEME = Theme(
    name="starship",
    colours={
        1: (208, GREEN_8),  # GREEN: orange data
        2: (226, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (183, MAGENTA_8),  # CYAN: labels, lavender
        5: (216, CYAN_8),  # MAGENTA: upload, peach
        6: (105, WHITE_8),  # BLUE: frames and quiet text, periwinkle
        7: (224, CYAN_8),  # WHITE: pale peach
        # The lights stay darker than any text: they are the background, not the news.
        FX_DIM: (53, MAGENTA_8),
        FX_MID: (60, MAGENTA_8),
        FX_HEAD: (96, MAGENTA_8),
        BACKGROUND: (105, WHITE_8),
        FX_GLASS: (53, MAGENTA_8),
        FX_GLASS_HEAD: (60, MAGENTA_8),
    },
    background=BLACK,
    frame="╭╮╰╯━┃",
    tick_ms=150,
    panels=True,
    glass=234,
    console_palette=(
        (BLUE_8, "120c1a"),  # glass: a violet-black under the panels
        (8, "5a3f78"),  # the lights, a muted purple
        (GREEN_8, "ff9a1f"),  # orange
        (8 + GREEN_8, "ffb857"),
        (MAGENTA_8, "cc99dd"),  # lavender
        (8 + MAGENTA_8, "e4c2f0"),
        (CYAN_8, "ffc9a0"),  # peach
        (8 + CYAN_8, "ffe0c8"),
        (WHITE_8, "9a9cff"),  # periwinkle
        (8 + WHITE_8, "c0c0ff"),
    ),
    backdrop=make,
    noise=("▮■●━┃╸╺", "-|=o*"),
    boot=(
        "bridge systems nominal.",
        "scanner sweeping, panels lit.",
        "ready for your orders.",
    ),
    title=Title(left="▐█▌▐▌", right="▐▌▐█▌", prompt="» ", cursor="▮"),
    meter_empty=("·", "·"),
    accent=1,
    label="orange and lavender panels, scanner bar, alert ripples",
)
