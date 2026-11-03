"""Handheld: a small old game console's LCD, dark ink on a pale green screen, and behind the
data a tiny puzzle: four-block shapes fall down a narrow well, settle into a small pile and
now and then a full row blinks and clears (a light look; see theme.py for the rules every
look keeps)."""

from __future__ import annotations

import random

from lxtop.looks.theme import (
    BACKGROUND,
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

# Four-cell shapes as (row, column) offsets; each cell is drawn two columns wide.
SHAPES = (
    ((0, 0), (0, 1), (0, 2), (0, 3)),
    ((0, 0), (0, 1), (1, 0), (1, 1)),
    ((0, 0), (0, 1), (0, 2), (1, 1)),
    ((0, 0), (1, 0), (2, 0), (2, 1)),
    ((0, 1), (1, 1), (2, 0), (2, 1)),
    ((0, 1), (0, 2), (1, 0), (1, 1)),
    ((0, 0), (0, 1), (1, 1), (1, 2)),
)


STEP = 0.1  # seconds per game step: a piece falls one row (and slides one column) a step
WELL = 10  # cells across; each cell is two columns wide
FLASH_STEPS = 5  # how long a full row blinks before it goes
SWEEP_ROWS_PER_SECOND = 7.0
SWEEP_GAP = 160  # rows of quiet between two refresh sweeps


def _rotations(shape: tuple[tuple[int, int], ...]) -> list[tuple[tuple[int, int], ...]]:
    seen: list[tuple[tuple[int, int], ...]] = []
    cells = shape
    for _ in range(4):
        cells = tuple((c, -r) for r, c in cells)
        r0 = min(r for r, _ in cells)
        c0 = min(c for _, c in cells)
        norm = tuple(sorted((r - r0, c - c0) for r, c in cells))
        if norm not in seen:
            seen.append(norm)
    return seen


ROTATIONS = tuple(_rotations(s) for s in SHAPES)


class _Well:
    """One narrow well: a piece falls, slides to a spot it picked, locks into the pile; a full
    row blinks and clears; a pile that grows too tall blinks and clears whole."""

    def __init__(self, rng: random.Random, x0: int, bw: int, h: int) -> None:
        self.rng = rng
        self.x0, self.bw, self.h = x0, bw, h
        self.cap = max(2, min(6, h // 3))
        self.grid = [[False] * bw for _ in range(h)]
        self.piece: tuple[tuple[int, int], ...] | None = None
        self.r = self.c = self.target = 0
        self.flash: list[int] = []
        self.flash_left = 0
        self.acc = 0.0
        self.clears = 0  # rows cleared so far (for tests)

    def _fits(self, cells: tuple[tuple[int, int], ...], r: int, c: int) -> bool:
        grid, h, bw = self.grid, self.h, self.bw
        return all(
            0 <= r + dr < h and 0 <= c + dc < bw and not grid[r + dr][c + dc] for dr, dc in cells
        )

    def _top(self) -> int:
        for r, row in enumerate(self.grid):
            if any(row):
                return r
        return self.h

    def _score(self, cells: tuple[tuple[int, int], ...], r: int, c: int) -> float:
        grid = self.grid
        for dr, dc in cells:
            grid[r + dr][c + dc] = True
        top = self._top()
        full = sum(all(grid[r + dr]) for dr in {dr for dr, _ in cells})
        holes = 0
        for col in range(self.bw):
            seen = False
            for row in range(top, self.h):
                if grid[row][col]:
                    seen = True
                elif seen:
                    holes += 1
        for dr, dc in cells:
            grid[r + dr][c + dc] = False
        return full * 20 - holes * 7 - (self.h - top)

    def _spawn(self) -> None:
        rng = self.rng
        options = [
            rot
            for rot in rng.choice(ROTATIONS)
            if max(r for r, _ in rot) < self.h and max(c for _, c in rot) < self.bw
        ] or [ROTATIONS[0][0]]
        best: list[tuple[float, tuple[tuple[int, int], ...], int]] = []
        top = self._top()
        for rot in options:
            width = max(c for _, c in rot) + 1
            height = max(r for r, _ in rot) + 1
            r0 = max(0, top - 14 - height)
            for c in range(self.bw - width + 1):
                if not self._fits(rot, r0, c):
                    continue
                r = r0
                while self._fits(rot, r + 1, c):
                    r += 1
                best.append((self._score(rot, r, c), rot, c))
        if not best:
            self._wipe()
            return
        pick = rng.choice(best) if rng.random() < 0.25 else max(best, key=lambda b: b[0])
        _, rot, self.target = pick
        height = max(r for r, _ in rot) + 1
        self.piece = rot
        self.r = max(0, top - 14 - height)
        self.c = rng.randrange(self.bw - max(c for _, c in rot))

    def _wipe(self) -> None:
        self.piece = None
        self.flash = [r for r, row in enumerate(self.grid) if any(row)]
        self.flash_left = FLASH_STEPS + 2

    def _lock(self) -> None:
        assert self.piece is not None
        for dr, dc in self.piece:
            self.grid[self.r + dr][self.c + dc] = True
        rows = sorted({self.r + dr for dr, _ in self.piece})
        self.flash = [r for r in rows if all(self.grid[r])]
        self.piece = None
        if self.flash:
            self.flash_left = FLASH_STEPS
            self.clears += len(self.flash)
        elif self.h - self._top() > self.cap:
            self._wipe()

    def step(self) -> None:
        if self.flash_left:
            self.flash_left -= 1
            if not self.flash_left:
                gone = set(self.flash)
                kept = [row for r, row in enumerate(self.grid) if r not in gone]
                self.grid = [[False] * self.bw for _ in gone] + kept
                self.flash = []
            return
        if self.piece is None:
            self._spawn()
            return
        if self.c != self.target:
            nxt = self.c + (1 if self.target > self.c else -1)
            if self._fits(self.piece, self.r, nxt):
                self.c = nxt
        if self._fits(self.piece, self.r + 1, self.c):
            self.r += 1
        else:
            self._lock()

    def cells(self, char: str, pile: str, ghost: str) -> list[Cell]:
        out: list[Cell] = []
        x0 = self.x0

        def put(row: int, col: int, ch: str, tone: int) -> None:
            out.append((row, x0 + 2 * col, ch, tone))
            out.append((row, x0 + 2 * col + 1, ch, tone))

        blink = FX_HEAD if self.flash_left % 2 else FX_DIM
        for r, row in enumerate(self.grid):
            if not any(row):
                continue
            for c, on in enumerate(row):
                if on:
                    if r in self.flash:
                        put(r, c, char, blink)
                    else:
                        put(r, c, pile, FX_MID)
        if self.piece is not None:
            land = self.r
            while self._fits(self.piece, land + 1, self.c):
                land += 1
            mine = {(self.r + dr, self.c + dc) for dr, dc in self.piece}
            for dr, dc in self.piece:
                if (land + dr, self.c + dc) not in mine:
                    put(land + dr, self.c + dc, ghost, FX_DIM)
            for r, c in sorted(mine):
                put(r, c, char, FX_HEAD)
        return out


class Blocks:
    """A faint LCD dot grid with a rare refresh sweep, and one or two small wells where shapes
    fall, settle into a pile and clear a full row now and then."""

    def __init__(self, console: bool, rng: random.Random) -> None:
        self.char, self.pile, self.ghost = "█", "▒", "░"
        self.dot = "·"
        self.rng = rng
        self.h = 0
        self.w = 0
        self.wells: list[_Well] = []
        self.lattice: list[tuple[int, int]] = []
        self.last: float | None = None

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        self.wells = []
        self.lattice = []
        if h < 1 or w < 1:
            return
        bw = min(WELL, (w - 2) // 2)
        spots: list[int] = []
        if bw >= 4:
            spots = [w - 2 * bw - 1]
            if w >= 100:
                spots.append(1)
        for x0 in spots:
            self.wells.append(_Well(random.Random(self.rng.random()), x0, bw, h))
        walls = [(x0 - 1, x0 + 2 * bw + 1) for x0 in spots]
        for r in range(1, h, 4):
            for c in range(3, w, 8):
                if not any(a <= c <= b for a, b in walls):
                    self.lattice.append((r, c))

    def frame(self, now: float) -> list[Cell]:
        dt = 0.0 if self.last is None else max(0.0, min(1.0, now - self.last))
        self.last = now
        out: list[Cell] = []
        sweep = (now * SWEEP_ROWS_PER_SECOND) % (self.h + SWEEP_GAP) - 2
        for r, c in self.lattice:
            out.append((r, c, self.dot, FX_MID if abs(r - sweep) <= 1.5 else FX_DIM))
        for well in self.wells:
            well.acc += dt
            while well.acc >= STEP:
                well.acc -= STEP
                well.step()
            out += well.cells(self.char, self.pile, self.ghost)
        return out


def make(console: bool, rng: random.Random) -> Blocks:
    return Blocks(console, rng)


THEME = Theme(
    name="handheld",
    colours={
        1: (22, GREEN_8),  # GREEN: data, the darkest green
        2: (130, YELLOW_8),  # YELLOW: warning, burnt amber; nothing else on screen is orange
        3: (160, RED_8),  # RED: alarm, a strong pure red
        4: (58, CYAN_8),  # CYAN: labels, dark olive
        5: (54, MAGENTA_8),  # MAGENTA: upload, a dark violet
        6: (65, MAGENTA_8),  # BLUE: frames and quiet text, a muted sage
        7: (235, 0),  # WHITE: plain text, near black (black on the console)
        # The puzzle sits between the screen and the text: shades of the LCD, never the news.
        FX_DIM: (151, GREEN_8),
        FX_MID: (108, GREEN_8),
        FX_HEAD: (71, GREEN_8),
        BACKGROUND: (235, 0),
        FX_GLASS: (108, GREEN_8),
        FX_GLASS_HEAD: (72, GREEN_8),
    },
    background=WHITE_8,  # console slot 7, redefined below as the pale LCD green
    background_rich=194,
    frame="╔╗╚╝═║",
    tick_ms=120,
    panels=True,
    glass=157,
    console_palette=(
        (BLUE_8, "b4e6a6"),  # glass: a slightly deeper green under the panels
        (8, "9cc78e"),  # the console draws dim text in slot 8: the puzzle, between screen and ink
        (GREEN_8, "0c4a14"),  # dark green
        (8 + GREEN_8, "0c4a14"),
        (CYAN_8, "3a4a0c"),  # dark olive
        (8 + CYAN_8, "3a4a0c"),
        (MAGENTA_8, "3f5a22"),  # muted green for quiet text
        (8 + MAGENTA_8, "3f5a22"),
        (WHITE_8, "d6f2c8"),  # the LCD's pale green
        (8 + WHITE_8, "d6f2c8"),
    ),
    backdrop=make,
    noise=("█▒░■·", "#=+-"),
    meter_empty=("·", "·"),
    boot=("inserting cartridge", "lcd warming up", "dropping blocks", "press start"),
    title=Title(left="■ ", right=" ■", prompt="> ", cursor="█"),
    accent=1,
    label="pale green lcd, dark ink, a tiny falling-block puzzle",
)
