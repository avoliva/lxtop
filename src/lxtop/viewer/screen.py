"""Clipped curses drawing and the colours both pages share."""

from __future__ import annotations

import contextlib
import curses
import random
from dataclasses import dataclass, field
from typing import Any

from lxtop.core.render import Glyphs, bar, big, fit
from lxtop.looks.theme import DEFAULT, GLASS, Theme, scramble, tinted

GREEN, YELLOW, RED, CYAN, MAGENTA, BLUE, WHITE = range(1, 8)
# One colour per series (a machine, a site), in order; red and yellow stay for warnings.
SERIES_COLOURS = (CYAN, MAGENTA, GREEN, BLUE, WHITE, YELLOW)
# What a frame did with each cell: nothing (the rain may fall there), drew ink, or covered it with
# a panel (glass: the rain shows through, darker).
OPEN, INK, GLASS_CELL = 0, 1, 2
# A big-number tile: title, value, unit, note, colour pair (None: coloured by `fraction`, with a
# meter), fraction.
Tile = tuple[str, str, str, str, int | None, float]


@dataclass
class Screen:
    """Clipped drawing on a curses window; never raises for text past the edge. It remembers
    which cells this frame drew (a box reserves its inside) so effects fill only empty ones, and
    while `scramble` is above 0 it swaps that share of each text for random `noise`."""

    win: Any
    glyphs: Glyphs
    theme: Theme = DEFAULT
    scramble: float = 0.0
    noise: str = "01"
    rng: random.Random = field(default_factory=random.Random)
    used: list[bytearray] = field(default_factory=list)
    solid: list[bytearray] = field(default_factory=list)
    glass: list[tuple[int, int, int, int]] = field(default_factory=list)  # panel insides
    tinting: bool = False  # panels get the glass background this frame
    console: bool = False  # the Linux console, where glass needs the theme's palette

    def begin(self) -> None:
        """A new frame: nothing drawn yet."""
        h, w = self.size
        self.used = [bytearray(w) for _ in range(h)]
        # What each cell visibly holds: 0 blank, 1 a mark (frame, plot, symbol, or anything in
        # reverse video), 2 a letter or digit. Effects drawn in front stop only at these.
        self.solid = [bytearray(w) for _ in range(h)]
        self.glass = []
        try:
            self.tinting = curses.has_colors() and tinted(self.theme, curses.COLORS, self.console)
        except curses.error:  # no screen yet (tests)
            self.tinting = False

    def solid_at(self, y: int, x: int) -> int:
        """0 blank, 1 a visible mark, 2 a letter or digit; 0 off the screen."""
        if 0 <= y < len(self.solid) and 0 <= x < len(self.solid[y]):
            return self.solid[y][x]
        return 0

    def inside(self, y: int, x: int) -> bool:
        """Whether (y, x) is inside a panel drawn this frame."""
        return any(t <= y < t + h and c <= x < c + w for t, c, h, w in self.glass)

    def on_glass(self, attr: int) -> int:
        """`attr` with its colour pair swapped for the same colour on the glass background."""
        pair = curses.pair_number(attr & curses.A_COLOR)
        glass = GLASS + pair if pair <= 11 else pair
        return (attr & ~curses.A_COLOR) | curses.color_pair(glass)

    def mark(self, y: int, x: int, n: int, kind: int = INK) -> None:
        """Record cells as ink, or as glass (which never covers ink already drawn)."""
        if 0 <= y < len(self.used):
            row = self.used[y]
            start, end = max(0, x), min(len(row), x + n)
            if end <= start:
                return
            if kind == INK:
                row[start:end] = b"\x01" * (end - start)
            else:
                for i in range(start, end):
                    if row[i] == OPEN:
                        row[i] = kind

    def kind(self, y: int, x: int) -> int:
        """OPEN, INK or GLASS_CELL; -1 off the screen."""
        if 0 <= y < len(self.used) and 0 <= x < len(self.used[y]):
            return self.used[y][x]
        return -1

    def free(self, y: int, x: int) -> bool:
        return self.kind(y, x) == OPEN

    @property
    def size(self) -> tuple[int, int]:
        h, w = self.win.getmaxyx()
        return int(h), int(w)

    def put(self, y: int, x: int, value: str, attr: int = 0, width: int | None = None) -> int:
        h, w = self.size
        if y < 0 or y >= h or x >= w or x < 0:
            return x
        room = w - x if width is None else min(width, w - x)
        out = fit(value, room, self.glyphs.ellipsis) if width is not None else value[:room]
        if y == h - 1 and x + len(out) >= w:
            out = out[: max(0, w - x - 1)]
        if self.tinting and self.inside(y, x):
            attr = self.on_glass(attr)
        self.mark(y, x, len(out))
        if 0 <= y < len(self.solid) and out:
            row = self.solid[y]
            end = min(len(row), x + len(out))
            if attr & curses.A_REVERSE:  # a bar or a highlight: solid even where blank
                row[x:end] = b"\x01" * (end - x)
            else:
                row[x:end] = bytes(2 if c.isalnum() else c != " " for c in out[: end - x])
        if self.scramble > 0:
            out = scramble(out, self.scramble, self.rng, self.noise)
        with contextlib.suppress(curses.error):
            self.win.addstr(y, x, out, attr)
        return x + len(out)

    def cell(self, y: int, x: int, char: str, attr: int = 0) -> None:
        """Characters with no bookkeeping, for effects and backgrounds."""
        h, w = self.size
        if 0 <= y < h and 0 <= x < w:
            char = char[: w - x - (1 if y == h - 1 else 0)]
            with contextlib.suppress(curses.error):
                self.win.addstr(y, x, char, attr)

    def right(self, y: int, x_end: int, value: str, attr: int = 0) -> int:
        """`value` ending at column `x_end` (exclusive); returns where it starts."""
        start = max(0, x_end - len(value))
        self.put(y, start, value, attr)
        return start

    def box(self, y: int, x: int, h: int, w: int, attr: int = 0) -> None:
        if h < 2 or w < 2:
            return
        tl, tr, bl, br, hl, vl = tuple(self.theme.frame)
        self.put(y, x, tl + hl * (w - 2) + tr, attr)
        inside = GLASS_CELL if self.theme.panels else INK
        for row in range(y + 1, y + h - 1):
            self.put(row, x, vl, attr)
            self.put(row, x + w - 1, vl, attr)
            self.mark(row, x + 1, w - 2, inside)  # the panel's, not the open rain's
        self.put(y + h - 1, x, bl + hl * (w - 2) + br, attr)
        if self.theme.panels and h > 2 and w > 2:
            self.glass.append((y + 1, x + 1, h - 2, w - 2))
            if self.tinting:  # the glass background, under whatever the panel draws next
                for row in range(y + 1, y + h - 1):
                    self.cell(row, x + 1, " " * (w - 2), curses.color_pair(GLASS))

    def panel(self, y: int, x: int, h: int, w: int, attr: int = 0) -> None:
        """In a theme with panels, frame a section drawn at rows y .. y+h-1, columns x .. x+w-1
        whose first row is its title: the frame's top runs along that row (the title is drawn
        over it), its sides are columns x-1 and x+w, its bottom row y+h. Call it before the
        section draws. Without panels it draws nothing."""
        if self.theme.panels:
            self.box(y, x - 1, h + 1, w + 2, attr)


def color(pair: int, bold: bool = False) -> int:
    attr = curses.color_pair(pair) if curses.has_colors() else 0
    return attr | (curses.A_BOLD if bold else 0)


def level(fraction: float) -> int:
    if fraction >= 0.85:
        return color(RED, True)
    if fraction >= 0.6:
        return color(YELLOW, True)
    return color(GREEN, True)


def series_colour(index: int) -> int:
    return SERIES_COLOURS[index % len(SERIES_COLOURS)]


def tile(s: Screen, y: int, x: int, width: int, spec: Tile) -> None:
    """A boxed big-number tile, 6 rows tall: title, value in big digits (plain text on a console
    without eighth blocks), unit, a note, and for a tile with no colour of its own, a meter."""
    title, value, unit, note, pair, frac = spec
    attr = color(pair, True) if pair is not None else level(frac)
    s.box(y, x, 6, width, color(BLUE))
    s.put(y, x + 2, f" {title} ", color(WHITE, True))
    digits = big(value) if s.glyphs.eighths else ("", value, "")
    for row, line in enumerate(digits):
        s.put(y + 1 + row, x + 3, line, attr)
    s.put(y + 3, x + 4 + len(digits[1]), unit, attr)
    s.put(y + 4, x + 3, note, color(BLUE), width - 5)
    if pair is None:
        start = x + 6 + len(digits[1]) + len(unit)
        meter = max(4, x + width - 3 - start)
        s.put(y + 2, start, bar(frac, meter, s.glyphs), attr)
        s.right(y + 3, x + width - 2, f"{frac * 100:.0f}%", attr)
