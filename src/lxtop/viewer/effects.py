"""A look's effects: decoding, its backdrop, its boot screen."""

from __future__ import annotations

import curses
from typing import TYPE_CHECKING

from lxtop.looks import theme as th
from lxtop.viewer.screen import (
    GLASS_CELL,
    INK,
    OPEN,
    color,
)

if TYPE_CHECKING:
    from lxtop.viewer.app import App


def decode_share(app: App, now: float) -> float:
    """How much of the page is still scrambled: all of it when it appears, none 0.8 s on."""
    if not app.theme.glitch or now < app.decode_from:
        return 0.0
    left = 1 - (now - app.decode_from) / th.DECODE_SECONDS
    return max(0.0, left) ** 2


def draw_fx(app: App, now: float) -> None:
    """The look's backdrop, only in cells nothing was drawn in and not beside text. Inside a
    panel a see-through look (Matrix) shows it darker, behind the glass; every other look
    draws it in front, in its own colours on the panel's background."""
    if app.backdrop is None or app.fx_level == "off":
        return
    s = app.screen
    h, w = s.size
    app.backdrop.resize(h, w)
    # On the console every effect is dim text, which takes the look's dim palette slot (8):
    # with 8 colours that is the only way to keep effects darker than any text.
    dim = curses.A_DIM if curses.has_colors() and curses.COLORS < 256 else 0
    attrs = {
        th.FX_HEAD: color(th.FX_HEAD) | dim,
        th.FX_MID: color(th.FX_MID) | dim,
        th.FX_DIM: color(th.FX_DIM) | dim,
    }
    behind = color(th.FX_GLASS) | dim
    glass = {th.FX_HEAD: color(th.FX_GLASS_HEAD) | dim, th.FX_MID: behind}
    glass[th.FX_DIM] = behind
    see_through = app.theme.see_through
    for y, x, char, tone in app.backdrop.frame(now):
        if tone in attrs:
            text, attr = char[:1], attrs[tone]
        else:
            continue
        end = x + len(text)  # the column just after it
        if x < 0 or end > w or not text:
            continue
        here = s.kind(y, x)
        if see_through:  # Matrix: only where nothing was drawn, never beside it, darker in panels
            if any(s.kind(y, c) not in (OPEN, GLASS_CELL) for c in range(x, end)):
                continue
            if INK in (s.kind(y, x - 1), s.kind(y, end)):
                continue
            if app.theme.thin and not th.fx_falls(app.fx_level, x, here == GLASS_CELL):
                continue
            if here == GLASS_CELL:
                attr = glass[tone] if tone in glass else s.on_glass(attr)
            s.cell(y, x, text, attr)
            continue
        # In front: anywhere that looks empty, including the empty parts of charts and
        # the padding of text, but never on a visible character or right beside a letter or
        # digit (an effect must not read as part of a word or a number).
        if any(s.solid_at(y, c) for c in range(x, end)):
            continue
        if 2 in (s.solid_at(y, x - 1), s.solid_at(y, end)):
            continue
        front = attr
        if s.tinting and s.inside(y, x):
            front = s.on_glass(front)
        s.cell(y, x, text, front)


def draw_boot(app: App, now: float) -> None:
    """A look's first seconds: its effects everywhere and its boot lines typed out."""
    s = app.screen
    h, w = s.size
    draw_fx(app, now)
    start = app.boot_until - th.BOOT_SECONDS
    typed = int((now - start) * 30)
    y = h // 2 - len(app.theme.boot)
    cursor_char = app.theme.title.cursor if app.theme.title else "_"
    for line in app.theme.boot:
        shown = line[: max(0, typed)]
        typed -= len(line) + 8
        if shown:
            cursor = cursor_char if len(shown) < len(line) or int(now * 3) % 2 else " "
            text_ = " " + shown + (cursor or " ") + " "
            s.put(y, max(0, (w - len(line)) // 2 - 1), text_, color(app.theme.accent, True))
        y += 2
