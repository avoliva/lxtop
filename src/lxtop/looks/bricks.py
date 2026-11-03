"""Bricks: a brick-breaker. A wall of bricks hangs near the top; a ball bounces between the
walls and a paddle at the bottom that follows it, knocking bricks out one by one until the
wall is gone and a new one is built. Now and then the ball splits into three for a while (see
theme.py for the rules every look keeps). An original look in the spirit of the paddle games."""

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

BRICK = 3  # columns a brick spans
BRICK_GAP = 3
WALL_ROWS = 3
GROUND = 2  # the paddle's row, counted from the bottom: clear of the status bar
SPEED = (18.0, 7.0)  # columns, rows a second
PADDLE = 6
MULTI_GAP = (30.0, 50.0)
MULTI_SECONDS = 10.0


class Ball:
    def __init__(self, y: float, x: float, vy: float, vx: float) -> None:
        self.y, self.x, self.vy, self.vx = y, x, vy, vx


class Breakout:
    def __init__(self, console: bool, rng: random.Random) -> None:
        self.rng = rng
        self.h = 0
        self.w = 0
        self.bricks: set[tuple[int, int]] = set()  # row, left column
        self.balls: list[Ball] = []
        self.last: float | None = None
        self.paddle = 0.0
        self.multi_at = 0.0

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        self.build()
        self.balls = [self.serve()]
        self.paddle = w / 2

    def build(self) -> None:
        top = self.h // 2  # the wall hangs mid-screen, below the headline numbers
        rows = range(top, min(top + WALL_ROWS, max(0, self.h - GROUND - 3)))
        cols = range(1, self.w - BRICK, BRICK + BRICK_GAP)
        self.bricks = {(y, x) for y in rows for x in cols}

    def serve(self) -> Ball:
        vx = SPEED[0] * self.rng.choice((-1, 1))
        return Ball(max(0, self.h - GROUND - 1), self.w / 2, -SPEED[1], vx)

    def brick_at(self, y: int, x: int) -> tuple[int, int] | None:
        for left in range(x - BRICK + 1, x + 1):
            if (y, left) in self.bricks:
                return (y, left)
        return None

    def step(self, ball: Ball, dt: float) -> None:
        ball.x += ball.vx * dt
        ball.y += ball.vy * dt
        if ball.x < 0 or ball.x > self.w - 1:
            ball.vx = -ball.vx
            ball.x = min(self.w - 1, max(0.0, ball.x))
        if ball.y < 0:
            ball.vy, ball.y = abs(ball.vy), 0.0
        bottom = max(0, self.h - GROUND - 1)
        if ball.y >= bottom and ball.vy > 0:  # the paddle always gets there
            ball.vy, ball.y = -abs(ball.vy), float(bottom)
        hit = self.brick_at(int(ball.y), int(ball.x))
        if hit is not None:
            self.bricks.discard(hit)
            ball.vy = -ball.vy

    def frame(self, now: float) -> list[Cell]:
        if self.h < 1 or self.w < 1:
            return []
        dt = 0.0 if self.last is None else min(0.2, max(0.0, now - self.last))
        self.last = now
        self._multi(now)
        for ball in self.balls:
            self.step(ball, dt)
        if not self.bricks:
            self.build()
        lead = self.balls[0].x
        self.paddle += (lead - self.paddle) * min(1.0, dt * 8)
        cells: dict[tuple[int, int], tuple[str, int]] = {}
        for y, left in self.bricks:
            for i in range(BRICK):
                if 0 <= left + i < self.w and 0 <= y < self.h:
                    cells[(y, left + i)] = ("▄", FX_MID)
        left = min(self.w - PADDLE, int(self.paddle) - PADDLE // 2)
        for x in range(max(0, left), max(0, left) + min(PADDLE, self.w)):
            cells[(max(0, self.h - GROUND), x)] = ("▀", FX_DIM)
        for ball in self.balls:
            y, x = int(ball.y), int(ball.x)
            if 0 <= y < self.h and 0 <= x < self.w:
                cells[(y, x)] = ("●", FX_HEAD)
        return [(y, x, c, tone) for (y, x), (c, tone) in cells.items()]

    def _multi(self, now: float) -> None:
        """Three balls for a while, then back to one."""
        if self.multi_at == 0.0:
            self.multi_at = now + self.rng.uniform(*MULTI_GAP)
        if now >= self.multi_at and len(self.balls) == 1 and self.balls:
            b = self.balls[0]
            self.balls += [Ball(b.y, b.x, b.vy, -b.vx), Ball(b.y, b.x, -b.vy, b.vx * 0.7)]
        if now - self.multi_at > MULTI_SECONDS and len(self.balls) > 1:
            self.balls = self.balls[:1]
            self.multi_at = now + self.rng.uniform(*MULTI_GAP)


def make(console: bool, rng: random.Random) -> Breakout:
    return Breakout(console, rng)


THEME = Theme(
    name="bricks",
    colours={
        1: (87, CYAN_8),  # GREEN: data, neon aqua (console slot 6, redefined)
        2: (226, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (215, MAGENTA_8),  # CYAN: labels, brick orange (console slot 5, redefined)
        5: (213, GREEN_8),  # MAGENTA: secondary, neon pink (console slot 2, redefined)
        6: (75, WHITE_8),  # BLUE: frames and quiet text, paddle blue
        7: (255, WHITE_8),  # WHITE: plain text
        # Bricks, the ball and the paddle stay darker than any text.
        FX_DIM: (237, WHITE_8),
        FX_MID: (60, MAGENTA_8),
        FX_HEAD: (243, WHITE_8),
        BACKGROUND: (255, WHITE_8),
        FX_GLASS: (237, WHITE_8),
        FX_GLASS_HEAD: (243, WHITE_8),
    },
    background=BLACK,
    frame="┏┓┗┛━┃",
    tick_ms=60,
    panels=True,
    glass=234,
    console_palette=(
        (BLUE_8, "16141e"),  # glass: arcade dusk under the panels
        (8, "3a3a6a"),  # the console draws every effect dim in slot 8: brick violet
        (CYAN_8, "5fffff"),  # neon aqua
        (8 + CYAN_8, "a0ffff"),
        (MAGENTA_8, "ffaf5f"),  # brick orange
        (8 + MAGENTA_8, "ffd0a0"),
        (GREEN_8, "ff87ff"),  # neon pink
        (8 + GREEN_8, "ffb8ff"),
    ),
    backdrop=make,
    meter_empty=("·", "·"),
    noise=("▄▀●·", "▄▀●·"),
    boot=("stage 1", "break the wall.", "the servers keep the ball up."),
    title=Title(left="▀▄▀ ", right=" ▄▀▄", prompt="", cursor="●"),
    accent=4,
    label="brick breaker: a bouncing ball, a paddle and a wall to clear",
)
