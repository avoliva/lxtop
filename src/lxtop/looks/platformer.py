"""Platformer: a sunny side-scroller. A light look on sky blue: clouds drift by, pipes stand
on a brick floor, coins spin in the air and a little hero runs right, jumping every pipe. Now
and then a question block appears and pops coins when the hero bumps it (see theme.py for the
rules every look keeps). An original look in the spirit of the platform games."""

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

RUN = 9.0  # the hero's columns a second
JUMP = 1.1  # seconds a jump lasts
JUMP_HEIGHT = 3
PIPE_EVERY = 38  # columns between pipes
CLOUD = "(~~~)"
CLOUD_SPEED = 1.5  # columns a second, leftwards
COIN_SPIN = "oO|O"
BLOCK_GAP = (20.0, 40.0)  # seconds between question blocks
POP_SECONDS = 1.2  # how long popped coins fly
LIFT = 1  # the floor sits this many rows up, clear of the status bar


class Level:
    """The scrolling scene. The floor is the bottom row; everything else stands on it."""

    def __init__(self, console: bool, rng: random.Random) -> None:
        self.rng = rng
        self.h = 0
        self.w = 0
        self.clouds: list[tuple[int, float]] = []  # row, starting column
        self.coins: list[tuple[int, int]] = []
        self.block_at = 0.0
        self.block_col = -1  # -1: no block placed yet
        self.pop_col = 0
        self.popped_at = float("-inf")

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        self.popped_at = float("-inf")
        if h < 1 or w < 1:
            self.clouds, self.coins = [], []
            return
        top = max(1, h // 3)
        self.clouds = [
            (self.rng.randrange(top), self.rng.uniform(0, w)) for _ in range(max(1, w // 40))
        ]
        self.coins = [
            (max(0, h - 4 - LIFT - self.rng.randrange(2)), self.rng.randrange(w))
            for _ in range(max(1, w // 25))
        ]
        self.popped_at = float("-inf")

    def pipes(self) -> list[int]:
        return list(range(PIPE_EVERY // 2, self.w - 1, PIPE_EVERY))

    def hero(self, now: float) -> tuple[int, int]:
        """(row, column): running right along the floor, up over each pipe."""
        col = int(now * RUN) % max(1, self.w)
        floor = self.h - 2 - LIFT
        lift = 0
        for pipe in self.pipes():
            ahead = pipe - col
            if -2 <= ahead <= 4:  # the jump spans the pipe
                t = (4 - ahead) / 6
                lift = round(JUMP_HEIGHT * 4 * t * (1 - t))
        return max(0, floor - lift), col

    def frame(self, now: float) -> list[Cell]:
        if self.h < 1 or self.w < 1:
            return []
        cells: dict[tuple[int, int], tuple[str, int]] = {}
        for row, start in self.clouds:
            left = int(start - now * CLOUD_SPEED) % (self.w + len(CLOUD)) - len(CLOUD)
            for i, char in enumerate(CLOUD):
                if 0 <= left + i < self.w:
                    cells[(row, left + i)] = (char, FX_DIM)
        floor = max(0, self.h - 1 - LIFT)
        for x in range(0, self.w, 2):
            cells[(floor, x)] = ("▄", FX_MID)
        for pipe in self.pipes():
            for dy, (side_l, side_r) in enumerate((("║", "║"), ("╔", "╗"))):
                y = floor - 1 - dy
                if y >= 0:
                    cells[(y, pipe)] = (side_l, FX_MID)
                    if pipe + 1 < self.w:
                        cells[(y, pipe + 1)] = (side_r, FX_MID)
        spin = COIN_SPIN[int(now * 6) % len(COIN_SPIN)]
        for y, x in self.coins:
            cells[(y, x)] = (spin, FX_HEAD)
        self._block(now, cells)
        y, x = self.hero(now)
        cells[(y, x)] = ("@", FX_HEAD)
        return [(y, x, c, tone) for (y, x), (c, tone) in cells.items()]

    def _block(self, now: float, cells: dict[tuple[int, int], tuple[str, int]]) -> None:
        """The question block: it waits above the hero's path; when the hero passes under
        it, coins pop up and fall, and the block goes until the next one."""
        if self.block_at == 0.0:
            self.block_at = now + self.rng.uniform(*BLOCK_GAP)
        row = max(0, self.h - 6 - LIFT)
        if now - self.popped_at < POP_SECONDS:
            t = (now - self.popped_at) / POP_SECONDS
            rise = round(4 * 4 * t * (1 - t))
            for dx in (-1, 0, 1):
                x = self.pop_col + dx * 2
                if 0 <= x < self.w and row - rise >= 0:
                    cells[(row - rise, x)] = ("¤", FX_HEAD)
            return
        if now < self.block_at:
            return
        if self.block_col < 0:
            self.block_col = (int(now * RUN) + 15) % max(1, self.w)
        _, hero_col = self.hero(now)
        if 0 <= hero_col - self.block_col <= 2:  # the hero runs under it
            self.popped_at, self.pop_col = now, self.block_col
            self.block_at = now + self.rng.uniform(*BLOCK_GAP)
            self.block_col = -1
            return
        if 0 <= self.block_col < self.w:
            cells[(row, self.block_col)] = ("?", FX_HEAD)


def make(console: bool, rng: random.Random) -> Level:
    return Level(console, rng)


THEME = Theme(
    name="platformer",
    colours={
        1: (52, BLACK),  # GREEN: data, dark brick red on the sky
        2: (94, YELLOW_8),  # YELLOW: a warning, dark gold so it reads on light blue
        3: (160, RED_8),  # RED: an alarm, strong red
        4: (22, GREEN_8),  # CYAN: labels, pipe green (console slot 2, redefined)
        5: (18, MAGENTA_8),  # MAGENTA: secondary, navy (console slot 5, redefined)
        6: (24, CYAN_8),  # BLUE: frames and quiet text, deep teal (console slot 6, redefined)
        7: (232, BLACK),  # WHITE: plain text, near black ink
        # Clouds, bricks and coins sit between the sky and the text: present, never louder.
        FX_DIM: (255, WHITE_8),
        FX_MID: (180, WHITE_8),
        FX_HEAD: (179, WHITE_8),
        BACKGROUND: (232, BLACK),
        FX_GLASS: (255, WHITE_8),
        FX_GLASS_HEAD: (180, WHITE_8),
    },
    background=WHITE_8,
    background_rich=117,
    frame="┏┓┗┛━┃",
    tick_ms=100,
    panels=True,
    glass=153,
    console_palette=(
        (BLUE_8, "b0dcff"),  # glass: a paler sky under the panels
        (8, "e8c890"),  # the console draws every effect dim in slot 8: sandy gold
        (WHITE_8, "87d0ff"),  # the sky itself, the background
        (8 + WHITE_8, "c0e8ff"),
        (GREEN_8, "005f00"),  # pipe green
        (8 + GREEN_8, "1a7a1a"),
        (MAGENTA_8, "00005f"),  # navy
        (8 + MAGENTA_8, "1a1a80"),
        (CYAN_8, "005f87"),  # deep teal
        (8 + CYAN_8, "1a7aa0"),
    ),
    backdrop=make,
    meter_empty=("·", "·"),
    noise=("oO|?¤", "oO|?¤"),
    boot=("a new level loads.", "coins everywhere.", "the servers run right."),
    title=Title(left="¤ ", right=" ¤", prompt="", cursor="▮"),
    accent=6,
    label="sunny side-scroller: clouds, pipes, coins and a jump",
)
