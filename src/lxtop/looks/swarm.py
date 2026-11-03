"""Swarm: a fixed-cannon space shooter. A formation of aliens marches side to side, stepping
down at each edge, while a cannon on the ground slides back and forth and fires; hits burst
and leave gaps. Now and then a saucer crosses the top (see theme.py for the rules every look
keeps). An original look in the spirit of the arcade shooters."""

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

ROWS = 4
COLS = 11
GAP_X = 5  # columns between aliens
GAP_Y = 2  # rows between alien rows
MARCH = 2.0  # steps a second
SHOT_EVERY = 1.4  # seconds between shots
SHOT_SPEED = 25.0  # rows a second
BURST_SECONDS = 0.4
SAUCER_GAP = (25.0, 45.0)
SAUCER_SECONDS = 8.0
STARS = 0.004
GROUND = 2  # the cannon's row, counted from the bottom: clear of the status bar


class Invasion:
    def __init__(self, console: bool, rng: random.Random) -> None:
        self.rng = rng
        self.h = 0
        self.w = 0
        self.stars: list[tuple[int, int]] = []
        self.dead: set[tuple[int, int]] = set()
        self.wave = -1
        self.shot_at = 0.0
        self.shot_x = 0
        self.burst: tuple[int, int, float] | None = None
        self.saucer_at = 0.0

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        n = int(h * w * STARS)
        self.stars = [(self.rng.randrange(h), self.rng.randrange(w)) for _ in range(n)]
        self.dead = set()

    def cols(self) -> int:
        return max(1, min(COLS, (self.w - 1) // GAP_X))

    def formation(self, now: float) -> tuple[int, int, int, int]:
        """(wave, top row, left column, step) of the formation at `now`."""
        width = (self.cols() - 1) * GAP_X + 1
        travel = max(1, self.w - width)
        steps = int(now * MARCH)
        phase = steps % (2 * travel)
        left = phase if phase < travel else 2 * travel - phase
        depth = max(1, self.h // 3)
        sweeps = steps // travel
        return sweeps // depth, 1 + sweeps % depth, left, steps

    def aliens(self, now: float) -> list[tuple[int, int, int, int]]:
        """(row index, column index, y, x) of each alien still alive."""
        wave, top, left, _ = self.formation(now)
        if wave != self.wave or len(self.dead) >= ROWS * self.cols():
            self.wave, self.dead = wave, set()
        return [
            (r, c, top + r * GAP_Y, left + c * GAP_X)
            for r in range(ROWS)
            for c in range(self.cols())
            if (r, c) not in self.dead and top + r * GAP_Y < self.h - GROUND - 1
        ]

    def cannon(self, now: float) -> int:
        return int((self.w - 1) * (0.5 + 0.5 * math.sin(now * 0.45)))

    def frame(self, now: float) -> list[Cell]:
        if self.h < 1 or self.w < 1:
            return []
        cells: dict[tuple[int, int], tuple[str, int]] = {}
        for y, x in self.stars:
            cells[(y, x)] = ("·", FX_DIM)
        _, _, _, step = self.formation(now)
        legs = "W" if step % 2 else "M"
        aliens = self.aliens(now)
        for _, _, y, x in aliens:
            if 0 <= x < self.w:
                cells[(y, x)] = (legs, FX_MID)
        self._shoot(now, aliens, cells)
        self._saucer(now, cells)
        gun = self.cannon(now)
        cells[(max(0, self.h - GROUND), gun)] = ("▲", FX_HEAD)
        return [(y, x, c, tone) for (y, x), (c, tone) in cells.items()]

    def _shoot(
        self,
        now: float,
        aliens: list[tuple[int, int, int, int]],
        cells: dict[tuple[int, int], tuple[str, int]],
    ) -> None:
        if now - self.shot_at >= SHOT_EVERY or now < self.shot_at:
            self.shot_at, self.shot_x = now, self.cannon(now)
        y = self.h - GROUND - 1 - int((now - self.shot_at) * SHOT_SPEED)
        hit = next((a for a in aliens if a[3] == self.shot_x and y <= a[2] <= y + 2), None)
        if hit is not None:
            self.dead.add((hit[0], hit[1]))
            self.burst = (hit[2], hit[3], now)
            self.shot_at = now - SHOT_EVERY / 2  # the next shot comes sooner
        elif y >= 0:
            cells[(y, self.shot_x)] = ("|", FX_HEAD)
        if self.burst and now - self.burst[2] < BURST_SECONDS:
            by, bx, _ = self.burst
            for dy, dx in ((0, 0), (0, -1), (0, 1)):
                if 0 <= by + dy < self.h and 0 <= bx + dx < self.w:
                    cells[(by + dy, bx + dx)] = ("*", FX_HEAD)

    def _saucer(self, now: float, cells: dict[tuple[int, int], tuple[str, int]]) -> None:
        if self.saucer_at == 0.0:
            self.saucer_at = now + self.rng.uniform(*SAUCER_GAP)
        t = now - self.saucer_at
        if t < 0:
            return
        if t > SAUCER_SECONDS:
            self.saucer_at = now + self.rng.uniform(*SAUCER_GAP)
            return
        left = int((self.w + 3) * t / SAUCER_SECONDS) - 3
        for i, char in enumerate("<■>"):
            if 0 <= left + i < self.w:
                cells[(0, left + i)] = (char, FX_MID)


def make(console: bool, rng: random.Random) -> Invasion:
    return Invasion(console, rng)


THEME = Theme(
    name="swarm",
    colours={
        1: (231, WHITE_8),  # GREEN: data, phosphor white
        2: (226, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (120, GREEN_8),  # CYAN: labels, arcade green (console slot 2, redefined)
        5: (213, MAGENTA_8),  # MAGENTA: secondary, saucer pink (console slot 5, redefined)
        6: (70, CYAN_8),  # BLUE: frames and quiet text, bunker green (console slot 6, redefined)
        7: (252, WHITE_8),  # WHITE: plain text
        # Aliens, shots and stars stay darker than any text.
        FX_DIM: (238, WHITE_8),
        FX_MID: (65, GREEN_8),
        FX_HEAD: (243, WHITE_8),
        BACKGROUND: (252, WHITE_8),
        FX_GLASS: (238, WHITE_8),
        FX_GLASS_HEAD: (243, WHITE_8),
    },
    background=BLACK,
    frame="┌┐└┘─│",
    tick_ms=80,
    panels=True,
    glass=233,
    console_palette=(
        (BLUE_8, "101410"),  # glass: the screen's dark under the panels
        (8, "3a5a3a"),  # the console draws every effect dim in slot 8: dim green
        (GREEN_8, "87ff87"),  # arcade green
        (8 + GREEN_8, "b8ffb8"),
        (MAGENTA_8, "ff87ff"),  # saucer pink
        (8 + MAGENTA_8, "ffb8ff"),
        (CYAN_8, "5faf00"),  # bunker green
        (8 + CYAN_8, "87d75f"),
    ),
    backdrop=make,
    meter_empty=("·", "·"),
    noise=("WM|*▲", "WM|*▲"),
    boot=("player 1", "the swarm descends.", "the servers hold the line."),
    title=Title(left="▲ ", right=" W M W", prompt="", cursor="▮"),
    accent=4,
    label="space shooter: a marching swarm, a cannon, a saucer",
)
