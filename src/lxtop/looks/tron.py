"""Tron: electric cyan lines on black, an orange counterpart, light cycles that leave straight
trails and turn at right angles (see theme.py for the rules every look keeps)."""

from __future__ import annotations

import math
import random
from collections import deque

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
    MAGENTA_8,
    RED_8,
    WHITE_8,
    YELLOW_8,
    Cell,
    Theme,
    Title,
)

Dir = tuple[int, int]  # (row step, column step)
Pos = tuple[int, int]
UP, DOWN, LEFT, RIGHT = (-1, 0), (1, 0), (0, -1), (0, 1)
HEAVY = {
    frozenset((LEFT, RIGHT)): "━",
    frozenset((UP, DOWN)): "┃",
    frozenset((RIGHT, DOWN)): "┏",
    frozenset((LEFT, DOWN)): "┓",
    frozenset((RIGHT, UP)): "┗",
    frozenset((LEFT, UP)): "┛",
}
LIGHT = {
    frozenset((LEFT, RIGHT)): "─",
    frozenset((UP, DOWN)): "│",
    frozenset((RIGHT, DOWN)): "┌",
    frozenset((LEFT, DOWN)): "┐",
    frozenset((RIGHT, UP)): "└",
    frozenset((LEFT, UP)): "┘",
}
PLAIN = {
    k: ("-" if k == frozenset((LEFT, RIGHT)) else "|" if v == "┃" else "+")
    for k, v in HEAVY.items()
}
MIN_RUN = 4  # cells straight before the next voluntary turn
TURN_CHANCE = 0.08
CRASH_CHANCE = 0.55  # facing a trail (not the edge): derez, else swerve
BRIGHT = 3  # trail cells behind the head drawn in the head tone: the glowing end of the wall
FADE_FROM = 0.6  # the older part of a trail turns to thin lines
LATTICE = (4, 8)  # a faint grid dot every 4 rows and 8 columns
FRAGMENTS = 9  # pieces in a derez
FRAGMENT_SECONDS = 0.75
MAX_FRAGMENTS = 90
PULSE_EVERY = (20.0, 45.0)  # seconds between the rare light-line sweeps
PULSE_LENGTH = 10
SHARDS = (("■", "▒", "░", "·"), ("*", "+", ":", "."))  # a fragment's glyphs as it fades

# Two teams tell apart by tone: cyan (FX_DIM) and orange (FX_MID); heads and fresh sparks FX_HEAD.
TEAM_TONES = (FX_DIM, FX_MID)


class _Cycle:
    """One light cycle: a head moving at constant speed, a trail of the cells it just left."""

    def __init__(self, rng: random.Random, team: int = 0) -> None:
        self.rng = rng
        self.team = team
        self.tone = TEAM_TONES[team % 2]
        self.trail: deque[Pos] = deque()
        self.d: Dir = RIGHT
        self.speed = 0.0
        self.acc = 0.0
        self.life = 0
        self.maxlen = 0
        self.since_turn = 0
        self.dead = False
        self.burst: Pos | None = None  # set on a crash; the grid turns it into a derez

    def spawn(self, h: int, w: int, occ: set[Pos], pre_steps: int = 0) -> None:
        r = self.rng
        cell = (r.randrange(h), r.randrange(w))
        for _ in range(8):
            if cell not in occ:
                break
            cell = (r.randrange(h), r.randrange(w))
        self.trail = deque([cell])
        occ.add(cell)
        self.d = r.choice((UP, DOWN, LEFT, RIGHT))
        self.speed = r.uniform(8.0, 22.0)
        self.acc = 0.0
        self.life = r.randint(120, 300)
        self.maxlen = r.randint(30, 60)
        self.since_turn = MIN_RUN
        self.dead = False
        self.burst = None
        for _ in range(pre_steps):
            self.step(h, w, occ)
        self.burst = None

    def _free(self, cell: Pos, h: int, w: int, occ: set[Pos]) -> bool:
        y, x = cell
        return 0 <= y < h and 0 <= x < w and cell not in occ

    def _crash(self) -> None:
        self.dead = True
        self.burst = self.trail[-1]

    def step(self, h: int, w: int, occ: set[Pos]) -> None:
        if self.dead:  # the wall dissolves from its tail, two cells a step
            for _ in range(2):
                if self.trail:
                    occ.discard(self.trail.popleft())
            if not self.trail:
                self.spawn(h, w, occ)
            return
        self.life -= 1
        if self.life <= 0:
            self.dead = True
            return
        y, x = self.trail[-1]
        ahead = (y + self.d[0], x + self.d[1])
        straight_ok = self._free(ahead, h, w, occ)
        on_grid = 0 <= ahead[0] < h and 0 <= ahead[1] < w
        if not straight_ok and on_grid and self.rng.random() < CRASH_CHANCE:
            self._crash()  # ran into a wall of light
            return
        turn = not straight_ok or (self.since_turn >= MIN_RUN and self.rng.random() < TURN_CHANCE)
        options: list[Dir] = [self.d] if straight_ok and not turn else []
        if turn or not options:
            sides = [(self.d[1], self.d[0]), (-self.d[1], -self.d[0])]
            options = [s for s in sides if self._free((y + s[0], x + s[1]), h, w, occ)]
            if not options and straight_ok:
                options = [self.d]
        if not options:  # boxed in
            self._crash()
            return
        nd = self.rng.choice(options)
        self.since_turn = 0 if nd != self.d else self.since_turn + 1
        self.d = nd
        head = (y + nd[0], x + nd[1])
        self.trail.append(head)
        occ.add(head)
        while len(self.trail) > self.maxlen:
            occ.discard(self.trail.popleft())

    def cells(
        self, heavy: dict[frozenset[Dir], str], light: dict[frozenset[Dir], str]
    ) -> list[Cell]:
        trail = list(self.trail)
        last = len(trail) - 1
        fade = int(len(trail) * FADE_FROM)
        out: list[Cell] = []
        for i, (y, x) in enumerate(trail):
            around: set[Dir] = set()
            if i > 0:
                around.add((trail[i - 1][0] - y, trail[i - 1][1] - x))
            if i < last:
                around.add((trail[i + 1][0] - y, trail[i + 1][1] - x))
            if len(around) == 1:  # an end of the trail: straight along its one neighbour
                (a,) = around
                around = {a, (-a[0], -a[1])}
            elif not around:
                around = {LEFT, RIGHT}
            age = last - i
            glowing = not self.dead and age < BRIGHT
            old = self.dead or age >= len(trail) - fade
            glyphs = light if old and not glowing else heavy
            out.append((y, x, glyphs[frozenset(around)], FX_HEAD if glowing else self.tone))
        return out


class _Fragment:
    """One scrap of a derezzed cycle, flying out from where it hit and fading."""

    def __init__(self, rng: random.Random, y: int, x: int, t0: float, tone: int) -> None:
        angle = rng.uniform(0.0, 6.2832)
        speed = rng.uniform(5.0, 16.0)
        self.y, self.x, self.t0, self.tone = y, x, t0, tone
        self.vy = math.sin(angle) * speed * 0.5  # cells are about twice as tall as wide
        self.vx = math.cos(angle) * speed


class _Pulse:
    """The rare event: a short bright line that sweeps once across the whole grid."""

    def __init__(self, rng: random.Random, h: int, w: int, t0: float) -> None:
        self.vertical = rng.random() < 0.4
        self.line = rng.randrange(h if not self.vertical else w)
        self.t0 = t0
        self.speed = 28.0 if self.vertical else 70.0
        self.reverse = rng.random() < 0.5
        self.extent = h if self.vertical else w

    def cells(self, now: float, light: dict[frozenset[Dir], str]) -> list[Cell] | None:
        pos = (now - self.t0) * self.speed
        if pos - PULSE_LENGTH > self.extent:
            return None
        glyph = light[frozenset((UP, DOWN) if self.vertical else (LEFT, RIGHT))]
        out: list[Cell] = []
        for k in range(PULSE_LENGTH):
            at = int(pos) - k
            if not 0 <= at < self.extent:
                continue
            at = self.extent - 1 - at if self.reverse else at
            y, x = (at, self.line) if self.vertical else (self.line, at)
            out.append((y, x, glyph, FX_HEAD if k < 2 else FX_MID if k < 5 else FX_DIM))
        return out


class Cycles:
    """Light cycles in two teams on the character grid, leaving glowing walls that other cycles
    crash into, bursting into fragments; a faint lattice behind, and now and then a sweep."""

    def __init__(self, console: bool, rng: random.Random, count: int | None = None) -> None:
        self.glyphs = PLAIN if console else HEAVY
        self.light = PLAIN if console else LIGHT
        self.shards = SHARDS[1 if console else 0]
        self.dot = "." if console else "·"
        self.rng = rng
        self.count = count
        self.h = 0
        self.w = 0
        self.cycles: list[_Cycle] = []
        self.occ: set[Pos] = set()
        self.fragments: list[_Fragment] = []
        self.lattice: list[Cell] = []
        self.pulse: _Pulse | None = None
        self.next_pulse: float | None = None
        self.last: float | None = None

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        self.cycles = []
        self.occ = set()
        self.fragments = []
        self.pulse = None
        self.lattice = [
            (y, x, self.dot, FX_DIM)
            for y in range(LATTICE[0] // 2, h, LATTICE[0])
            for x in range(LATTICE[1] // 2, w, LATTICE[1])
        ]
        if h < 1 or w < 1:
            return
        n = self.count if self.count is not None else max(2, min(6, h * w // 800))
        for i in range(n):
            cycle = _Cycle(self.rng, i)
            cycle.spawn(h, w, self.occ, self.rng.randint(0, 60))
            self.cycles.append(cycle)

    def _derez(self, cycle: _Cycle, now: float) -> None:
        assert cycle.burst is not None
        y, x = cycle.burst
        cycle.burst = None
        for _ in range(FRAGMENTS):
            self.fragments.append(_Fragment(self.rng, y, x, now, cycle.tone))
        del self.fragments[:-MAX_FRAGMENTS]

    def frame(self, now: float) -> list[Cell]:
        dt = 0.0 if self.last is None else max(0.0, min(1.0, now - self.last))
        self.last = now
        if self.h < 1 or self.w < 1:
            return []
        lit: dict[Pos, Cell] = {(c[0], c[1]): c for c in self.lattice}
        if self.next_pulse is None:
            self.next_pulse = now + self.rng.uniform(*PULSE_EVERY)
        elif self.pulse is None and now >= self.next_pulse:
            self.pulse = _Pulse(self.rng, self.h, self.w, now)
        if self.pulse is not None:
            cells = self.pulse.cells(now, self.light)
            if cells is None:
                self.pulse = None
                self.next_pulse = now + self.rng.uniform(*PULSE_EVERY)
            else:
                lit.update({(c[0], c[1]): c for c in cells})
        for cycle in self.cycles:
            cycle.acc += cycle.speed * dt
            steps = min(int(cycle.acc), 60)
            cycle.acc -= int(cycle.acc)
            for _ in range(steps):
                cycle.step(self.h, self.w, self.occ)
                if cycle.burst is not None:
                    self._derez(cycle, now)
            lit.update({(c[0], c[1]): c for c in cycle.cells(self.glyphs, self.light)})
        alive: list[_Fragment] = []
        for f in self.fragments:
            age = now - f.t0
            if age >= FRAGMENT_SECONDS:
                continue
            alive.append(f)
            y, x = round(f.y + f.vy * age), round(f.x + f.vx * age)
            if not (0 <= y < self.h and 0 <= x < self.w):
                continue
            share = age / FRAGMENT_SECONDS
            glyph = self.shards[min(3, int(share * 4))]
            lit[(y, x)] = (y, x, glyph, FX_HEAD if share < 0.3 else f.tone)
        self.fragments = alive
        return list(lit.values())


def make(console: bool, rng: random.Random) -> Cycles:
    return Cycles(console, rng)


THEME = Theme(
    name="tron",
    colours={
        1: (51, CYAN_8),  # GREEN: electric cyan data
        2: (226, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (123, CYAN_8),  # CYAN: labels, pale cyan
        5: (208, MAGENTA_8),  # MAGENTA: upload, orange (console slot 5 is redefined)
        6: (37, CYAN_8),  # BLUE: frames and quiet text, a teal
        7: (195, WHITE_8),  # WHITE: ice white
        # Walls stay darker than any text: they are the background, not the news. Two teams by
        # tone: cyan (FX_DIM) and orange (FX_MID); heads and derez sparks are the brightest.
        FX_DIM: (30, CYAN_8),
        FX_MID: (94, MAGENTA_8),
        FX_HEAD: (130, MAGENTA_8),
        BACKGROUND: (37, CYAN_8),
        FX_GLASS: (23, CYAN_8),
        FX_GLASS_HEAD: (94, MAGENTA_8),
    },
    background=BLACK,
    frame="┏┓┗┛━┃",
    tick_ms=90,
    panels=True,
    glass=233,
    console_palette=(
        (BLUE_8, "06141c"),  # glass: a blue-black under the panels
        (8, "0b5963"),  # the console draws dim text in slot 8: trails, dark teal
        (CYAN_8, "00d2e6"),  # cyan text
        (8 + CYAN_8, "6ff6ff"),  # bold cyan
        (MAGENTA_8, "ff7a14"),  # orange
        (8 + MAGENTA_8, "ffa23c"),  # bold orange
        (WHITE_8, "d6f6ff"),  # ice
        (8 + WHITE_8, "f2fcff"),  # bold ice
    ),
    backdrop=make,
    glitch=True,
    noise=("┃━┏┓┗┛╋┣┫", "-|+<>"),
    meter_empty=("─", "-"),
    boot=("entering the grid", "two teams, light cycles online", "walls of light armed", "go"),
    title=Title(left="▮━┫", right="┣━▮", prompt="» ", cursor="▮"),
    accent=1,
    label="cyan and orange light cycles, glowing walls, derez bursts",
)
