"""The title bar, footer and help overlay, which every page shares."""

from __future__ import annotations

import curses
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from lxtop.core import snapshot as sn
from lxtop.core.render import clean, duration, fit
from lxtop.looks import theme as th
from lxtop.viewer.pages.common import host_line
from lxtop.viewer.screen import (
    BLUE,
    CYAN,
    RED,
    WHITE,
    color,
)

if TYPE_CHECKING:
    from lxtop.viewer.app import App
    from lxtop.viewer.pages.base import Page


# The viewer's own keys at the end of the help; each page adds its section (pages/base.py).
LOOK_KEYS = (
    ("t  T", "next look, previous look (--theme NAME starts in one)"),
    ("", "the look changes by itself; o sets how often (--cycle SECONDS: one run)"),
    ("r", "effects: on, max, off (they start on; the footer shows which)"),
    ("o", "settings: look, how often it changes, effects, first page; saved"),
    ("?", "this help"),
    ("q  Ctrl-C", "quit"),
)


def help_lines(pages: Sequence[Page]) -> list[tuple[str, str]]:
    """The help: moving between pages, each page's own keys, then the looks and quitting."""
    labels = [p.label for p in pages]
    out = [
        ("Tab", "next page: " + ", ".join(labels)),
        ("  ".join(str(i) for i in range(1, len(pages) + 1)), "  /  ".join(labels)),
    ]
    for page in pages:
        if page.help:
            out += [("", ""), *page.help]
    return [*out, ("", ""), *LOOK_KEYS]


def draw_title(app: App, w: int, title: str, subtitle: str) -> None:
    """Row 0 of every page with a subtitle: name, clock, and any data problem in red."""
    s = app.screen
    snap = app.snapshot
    if app.theme.title is not None:
        x = draw_styled_title(app, w, title, subtitle, app.theme.title)
    else:
        s.put(0, 0, " " * w, color(BLUE) | curses.A_REVERSE)
        x = s.put(0, 0, title, color(WHITE, True) | curses.A_REVERSE)
        if w >= 120:
            x = s.put(0, x + 2, subtitle, color(WHITE) | curses.A_REVERSE)
        clock = time.strftime(" %a %d %b  %H:%M:%S ")
        s.right(0, w, clock, color(WHITE, True) | curses.A_REVERSE)
    age = time.time() - sn.taken_at(snap, time.time())
    problem = app.load_error
    if not problem and age > 3 * sn.interval(snap):
        problem = f"NO NEW DATA FOR {duration(age)}: is lxtop-collect running?"
    if problem:
        s.put(0, x + 3, " " + clean(problem) + " ", color(RED, True) | curses.A_REVERSE)
    elif time.monotonic() < app.toast_until:
        toast = f" {app.toast_text} "
        s.right(0, w - 24, toast, color(app.theme.accent, True) | curses.A_REVERSE)


def draw_styled_title(app: App, w: int, title: str, subtitle: str, style: th.Title) -> int:
    """A look's own bar on black, e.g. `█▒░ NETWORK ░▒█ > subtitle█`. In a glitching look,
    every few seconds a few letters flip and the bar slips one column for a moment.
    Returns where the text ends."""
    s = app.screen
    now = time.monotonic()
    accent = app.theme.accent
    glitching = app.theme.glitch and app.glitch_at <= now < app.glitch_at + 0.15
    if now >= app.glitch_at + 0.15:
        app.glitch_at = now + app.rng.uniform(3, 8)
    before = s.scramble
    if glitching:
        s.scramble = max(before, 0.3)
    shift = 1 if glitching else 0
    s.put(0, 0, " " * w, color(BLUE))
    x = s.put(0, shift, style.left, color(accent))
    x = s.put(0, x, f" {title.strip()} ", color(accent, True) | curses.A_REVERSE)
    x = s.put(0, x, style.right, color(accent))
    if w >= 120:
        x = s.put(0, x + 2, style.prompt + subtitle, color(CYAN))
        if style.cursor:
            cursor = style.cursor if int(now * 2) % 2 else " "
            x = s.put(0, x, cursor, color(accent, True))
    clock = time.strftime(" %a %d %b  %H:%M:%S ")
    s.right(0, w, clock, color(accent, True))
    s.scramble = before
    return x


def draw_footer(app: App, h: int, w: int) -> None:
    page = app.current
    keys = page.footer(app.frame, app.next_page(), app.pages)
    if app.backdrop:
        keys += f"   t look   r effects: {th.FX_SHOWN.get(app.fx_level, app.fx_level)}"
    else:
        keys += "   t look"
    keys += "   o settings   q quit"
    attr = color(app.theme.accent) | curses.A_REVERSE
    app.screen.put(h - 1, 0, fit(" " + keys, w), attr)
    if page.host_line and app.snapshot:
        line = " " + host_line(app.snapshot) + " "
        if len(keys) + len(line) + 4 < w:
            app.screen.right(h - 1, w - 1, line, attr)


def draw_help(app: App, h: int, w: int) -> None:
    s = app.screen
    lines = help_lines(app.pages)
    box_w = 74
    x = max(0, (w - box_w) // 2)
    y = max(0, (h - len(lines) - 4) // 2)
    s.put(y, x, fit(" keys (any key closes) ", box_w), color(WHITE, True) | curses.A_REVERSE)
    for i, (key, what) in enumerate(lines, start=1):
        attr = curses.A_REVERSE | (curses.A_BOLD if key and not what else 0)
        s.put(y + i, x, fit(f"  {key:<20}{what}", box_w), attr)
    s.put(y + len(lines) + 1, x, fit("", box_w), curses.A_REVERSE)
