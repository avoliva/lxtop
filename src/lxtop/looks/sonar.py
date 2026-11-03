"""Sonar: a submarine sonar screen in deep sea green and teal on black. A sweep turns round a
centre point over faint range rings; contacts light up as it passes and fade until the next
pass; bubbles rise, and now and then a large contact crosses slowly (see theme.py for the rules
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

TURN_SECONDS = 4.0  # one revolution
# Rays behind the sweep as (angle behind in radians, tone, draw every nth cell): the last
# quarter turn, nearest first.
WAKE = (
    (0.10, FX_MID, 1),
    (0.20, FX_MID, 1),
    (0.40, FX_DIM, 2),
    (0.70, FX_DIM, 2),
    (1.10, FX_DIM, 2),
    (1.50, FX_DIM, 2),
)
ASPECT = 0.5  # a character cell is about twice as tall as wide
TAU = 2 * math.pi
# A rare large contact crosses slowly: one every EVENT_PERIOD seconds, taking EVENT_SECONDS.
EVENT_PERIOD = 90.0
EVENT_SECONDS = 36.0
BIG = (
    "    __.-.__    ",
    " <(___   ___)=> ",
    "     `-'-'     ",
)
MIRROR = str.maketrans("<>()", "><)(")


def afterglow(age: float) -> tuple[str, int] | None:
    """What a contact shows `age` turns after the sweep passed it: bright, then fading out
    until the next pass (a scope's persistence)."""
    if age < 0.08:
        return "*", FX_HEAD
    if age < 0.30:
        return "+", FX_MID
    if age < 0.65:
        return ":", FX_DIM
    return None


class Sweep:
    """A line from the centre turning round once per TURN_SECONDS, its wake fading behind it,
    faint range rings, contacts that light up as the sweep passes and fade until the next pass,
    a few bubbles rising slowly, and now and then a large contact crossing."""

    def __init__(self, console: bool, rng: random.Random) -> None:
        self.rng = rng
        self.h = 0
        self.w = 0
        self.offset = rng.uniform(5.0, 40.0)  # when the first large contact comes
        # (column, rows per second, start offset in rows, sway phase)
        self.bubbles: list[tuple[int, float, float, float]] = []
        # (column, row, columns per second, rows per second)
        self.contacts: list[tuple[float, float, float, float]] = []
        # (row, column, angle from the centre) of the faint range rings
        self.rings: list[tuple[int, int, float]] = []

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        self.bubbles = []
        self.contacts = []
        self.rings = []
        if h < 1 or w < 1:
            return
        for _ in range(max(1, min(10, h * w // 1500))):
            self.bubbles.append(
                (
                    self.rng.randrange(w),
                    self.rng.uniform(1.0, 2.5),
                    self.rng.uniform(0, h + 3),
                    self.rng.uniform(0, 6.28),
                )
            )
        for _ in range(max(1, min(14, h * w // 700))):
            speed = self.rng.uniform(0.05, 0.25)
            heading = self.rng.uniform(0, TAU)
            self.contacts.append(
                (
                    self.rng.uniform(0, w),
                    self.rng.uniform(0, h),
                    math.cos(heading) * speed,
                    math.sin(heading) * speed * ASPECT,
                )
            )
        reach = min(w / 2, h / (2 * ASPECT))
        seen: set[tuple[int, int]] = set()
        for frac in (1 / 3, 2 / 3, 1.0):
            radius = reach * frac
            steps = max(8, int(TAU * radius))
            for i in range(0, steps, 3):
                ang = TAU * i / steps
                y = h // 2 + round(math.sin(ang) * radius * ASPECT)
                x = w // 2 + round(math.cos(ang) * radius)
                if 0 <= y < h and 0 <= x < w and (y, x) not in seen:
                    seen.add((y, x))
                    self.rings.append((y, x, ang))

    @staticmethod
    def angle(now: float) -> float:
        """The sweep's direction in radians: 0 points right, growing clockwise on screen."""
        return (now / TURN_SECONDS % 1.0) * TAU

    def age(self, head: float, y: float, x: float) -> float:
        """Turns since the sweep last passed the point (row y, column x): 0 just now."""
        there = math.atan2((y - self.h // 2) / ASPECT, x - self.w // 2)
        return ((head - there) % TAU) / TAU

    def event(self, now: float) -> tuple[int, float] | None:
        """(which event, progress 0..1) while a large contact is crossing, else None."""
        shifted = now + self.offset
        index = int(shifted // EVENT_PERIOD)
        into = shifted - index * EVENT_PERIOD
        if index < 0 or into >= EVENT_SECONDS:
            return None
        return index, into / EVENT_SECONDS

    def large(self, now: float, head: float) -> dict[tuple[int, int], tuple[str, int]]:
        """The large contact: dim all the time, brighter as the sweep lights it."""
        out: dict[tuple[int, int], tuple[str, int]] = {}
        crossing = self.event(now)
        if crossing is None or self.h < 1 or self.w < 1:
            return out
        index, progress = crossing
        rightwards = index % 2 == 0
        width = len(BIG[0])
        left = round(-width + progress * (self.w + width))
        if not rightwards:
            left = self.w - width - left
        top = (index * 7919) % max(1, self.h - len(BIG) + 1)
        age = self.age(head, top + 1, left + width / 2)
        tone = FX_HEAD if age < 0.08 else FX_MID if age < 0.3 else FX_DIM
        for dy, line in enumerate(BIG):
            text = line if rightwards else line[::-1].translate(MIRROR)
            for dx, char in enumerate(text):
                y, x = top + dy, left + dx
                if char != " " and 0 <= y < self.h and 0 <= x < self.w:
                    out[(y, x)] = (char, tone)
        return out

    def _ray(
        self, angle: float, tone: int, step: int, cells: dict[tuple[int, int], tuple[str, int]]
    ) -> None:
        cx, cy = self.w // 2, self.h // 2
        cos, sin = math.cos(angle), math.sin(angle)
        ax, ay = abs(cos), abs(sin) * ASPECT
        char = "|" if ay > 2 * ax else "-" if ax > 2 * ay else "\\" if cos * sin > 0 else "/"
        for r in range(step, self.w + 2 * self.h, step):
            x = cx + round(cos * r)
            y = cy + round(sin * r * ASPECT)
            if not (0 <= x < self.w and 0 <= y < self.h):
                if r > max(self.w, 2 * self.h):
                    break
                continue
            cells[(y, x)] = (char, tone)

    def bubble_cells(self, now: float) -> dict[tuple[int, int], tuple[str, int]]:
        cells: dict[tuple[int, int], tuple[str, int]] = {}
        for x, speed, start, sway in self.bubbles:
            progress = (now * speed + start) % (self.h + 3)
            row = self.h - 1 - int(progress)
            if row < 0:
                continue
            col = min(self.w - 1, max(0, x + round(math.sin(now * 0.7 + sway))))
            rise = progress / (self.h + 3)
            cells[(row, col)] = (
                ("o", FX_MID) if rise < 0.4 else ("°", FX_DIM) if rise < 0.75 else (".", FX_DIM)
            )
        return cells

    def frame(self, now: float) -> list[Cell]:
        if self.h < 1 or self.w < 1:
            return []
        head = self.angle(now)
        cells: dict[tuple[int, int], tuple[str, int]] = {}
        for y, x, ang in self.rings:  # faint rings, flaring where the sweep just passed
            near = ((head - ang) % TAU) / TAU < 0.05
            cells[(y, x)] = ("·", FX_MID if near else FX_DIM)
        cells.update(self.bubble_cells(now))
        for behind, tone, step in reversed(WAKE):
            self._ray(head - behind, tone, step, cells)
        self._ray(head, FX_HEAD, 1, cells)
        for cx, cy, vx, vy in self.contacts:  # drifting contacts with afterglow
            x = int((cx + vx * now) % self.w)
            y = int((cy + vy * now) % self.h)
            glow = afterglow(self.age(head, y, x))
            if glow is not None:
                cells[(y, x)] = glow
        cells.update(self.large(now, head))
        return [(y, x, c, tone) for (y, x), (c, tone) in cells.items()]


def make(console: bool, rng: random.Random) -> Sweep:
    return Sweep(console, rng)


THEME = Theme(
    name="sonar",
    colours={
        1: (48, GREEN_8),  # GREEN: bright sea green data
        2: (226, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (86, WHITE_8),  # CYAN: labels, aqua (console slot 7 is redefined)
        5: (44, MAGENTA_8),  # MAGENTA: upload, a bright teal (console slot 5 is redefined)
        6: (37, CYAN_8),  # BLUE: frames and quiet text, teal
        7: (158, WHITE_8),  # WHITE: pale mint
        # The sweep and bubbles stay darker than any text: they are the water, not the news.
        FX_DIM: (22, GREEN_8),
        FX_MID: (23, GREEN_8),
        FX_HEAD: (29, GREEN_8),
        BACKGROUND: (158, WHITE_8),
        FX_GLASS: (22, GREEN_8),
        FX_GLASS_HEAD: (23, GREEN_8),
    },
    background=BLACK,
    frame="╭╮╰╯─│",
    tick_ms=80,
    panels=True,
    glass=233,
    thin=False,
    console_palette=(
        (BLUE_8, "04161a"),  # glass: deep-sea blue-black under the panels
        (8, "0b5a40"),  # the console draws dim text in slot 8: the sweep, dark sea green
        (GREEN_8, "10e08a"),  # sea green
        (8 + GREEN_8, "5affc0"),
        (CYAN_8, "10a8a8"),  # teal
        (8 + CYAN_8, "4bd6d6"),
        (MAGENTA_8, "20c0b0"),  # bright teal
        (8 + MAGENTA_8, "5de6d6"),
        (WHITE_8, "a8ffe0"),  # aqua mint
        (8 + WHITE_8, "d8fff0"),
    ),
    backdrop=make,
    noise=("o°.~≈", "o.~:"),
    boot=("trimming ballast", "pinging the deep", "contact bearing clear"),
    meter_empty=("·", "·"),
    title=Title(left="─·((", right="))·─", prompt="ping> ", cursor="▮"),
    accent=1,
    label="sea-green sonar: range rings, fading contacts, bubbles",
)
