"""The curses viewer. It only reads the collector's snapshot file and draws it.

The pages are in `pages.PAGES`: Network (the home page), All machines, Memory & jobs and
Timers & services. Tab goes to the next, 1 2 3 4 jump. The app
owns the loop, the look and its effects, the title bar, the footer, the help and the settings
menu (`menu.py`); each page draws the rest and handles its own keys (`pages/base.py`).
"""

from __future__ import annotations

import contextlib
import curses
import dataclasses
import json
import os
import random
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxtop.core import settings as st
from lxtop.core.render import Glyphs
from lxtop.core.snapshot import Json, as_dict
from lxtop.looks import theme as th
from lxtop.viewer import chrome, colours, effects, keys
from lxtop.viewer.menu import Menu
from lxtop.viewer.pages import PAGES
from lxtop.viewer.pages.base import Frame, Page
from lxtop.viewer.screen import Screen

if TYPE_CHECKING:
    from lxtop.viewer.font import ConsoleFont
    from lxtop.viewer.prefs import Prefs

TOAST_SECONDS = 2.5  # how long the title bar names a look you switched to


class App:
    def __init__(
        self,
        win: Any,
        state: Path,
        glyphs: Glyphs,
        theme: th.Theme = th.DEFAULT,
        console: bool = False,
        rng: random.Random | None = None,
        cycle: float = 0.0,
        font: ConsoleFont | None = None,
        pages: Sequence[Page] | None = None,
        prefs: Prefs | None = None,
    ) -> None:
        # The saved settings; without a settings file, changes last until quitting.
        self.prefs = prefs
        self.settings = prefs.settings if prefs else st.Settings()
        self.save_error = ""
        self.menu: Menu | None = None
        self.rng = rng or random.Random()
        # The console's font with graph blocks, when lxtop runs on a Linux console.
        self.font = font
        self.screen = Screen(win, glyphs, rng=self.rng, console=console)
        self.console = console
        # The console's own palette, to put back when Matrix's is no longer showing.
        self.palette = colours.read_palette(sys.stdin.fileno()) if console else None
        self.g = glyphs
        self.base_glyphs = glyphs  # before a look swaps in its own meter character
        self.backdrop: th.Backdrop | None = None
        self.theme = th.DEFAULT
        self.decode_from = float("-inf")
        self.boot_until = float("-inf")
        self.glitch_at = 0.0
        self.toast_until = float("-inf")
        self.toast_text = ""
        # Seconds between automatic look changes; 0 keeps the look until t or T.
        self.cycle_seconds = max(0.0, cycle)
        self.next_cycle_at = float("inf")
        self.state = state
        self.snapshot: Json = {}
        self.mtime = 0.0
        self.load_error = ""
        self.help = False
        self.last_clear = 0.0
        self.pages: list[Page] = list(pages) if pages else [make() for make in PAGES]
        names = [p.name for p in self.pages]
        start = self.settings.start_page
        self.page = start if start in names else names[0]  # the page showing, by name
        self.frame = Frame(self.screen, {})  # what the last draw drew from
        self.fx_level = self.settings.effects
        self.set_theme(theme, boot=bool(theme.boot) and self.settings.boot)

    def write_palette(self, entries: tuple[tuple[int, str], ...]) -> None:
        """Show `entries` on the console's palette, or with none, put its own palette back."""
        colours.write_palette(entries, self.palette)

    def set_theme(self, theme: th.Theme, boot: bool = False, announce: bool = False) -> None:
        """Switch the look now; a glitching look arrives with the page decoding (and at start,
        its boot lines). `announce`: name it in the title bar for a moment."""
        self.theme = theme
        self.screen.theme = theme
        self.screen.noise = theme.noise[1 if self.console else 0]
        empty = theme.meter_empty[1 if self.console else 0]
        self.g = dataclasses.replace(self.base_glyphs, empty=empty) if empty else self.base_glyphs
        self.screen.glyphs = self.g
        self.backdrop = theme.backdrop(self.console, self.rng) if theme.backdrop else None
        with contextlib.suppress(curses.error):
            colours.init_colours(self.screen.win, theme, self.console)
        if self.console:
            self.write_palette(theme.console_palette)
        self.screen.win.timeout(theme.tick_ms)
        now = time.monotonic()
        self.decode_from = now + (th.BOOT_SECONDS if boot else 0)
        self.boot_until = now + th.BOOT_SECONDS if boot else float("-inf")
        self.glitch_at = now + 3
        if announce:
            names = list(th.THEMES)
            place = names.index(theme.name) + 1 if theme.name in names else 0
            self.toast(f"look: {theme.name}  {place}/{len(names)}")
        else:
            self.toast_until = float("-inf")
        self.next_cycle_at = now + self.cycle_seconds if self.cycle_seconds else float("inf")

    def set_cycle(self, seconds: float) -> None:
        """Change the look every `seconds` from now on; 0 keeps the look showing."""
        self.cycle_seconds = max(0.0, seconds)
        now = time.monotonic()
        self.next_cycle_at = now + self.cycle_seconds if self.cycle_seconds else float("inf")

    # ---- settings -----------------------------------------------------------------

    @property
    def start_page(self) -> str:
        return self.settings.start_page

    @property
    def boot_lines(self) -> bool:
        return self.settings.boot

    def remember(self, **changes: Any) -> None:
        """Keep changed settings for the next start, saving them when there is a file."""
        self.settings = dataclasses.replace(self.settings, **changes)
        if self.prefs is not None:
            self.save_error = self.prefs.put(self.settings)

    def reset_settings(self) -> None:
        """Back to the defaults, now and at the next start."""
        defaults = self.prefs.defaults if self.prefs else st.Settings()
        self.settings = defaults
        if self.prefs is not None:
            self.save_error = self.prefs.reset()
        self.set_theme(th.THEMES.get(defaults.look, th.DEFAULT))
        self.set_cycle(defaults.cycle_seconds)
        self.fx_level = defaults.effects
        self.toast("settings: defaults")

    def settings_note(self) -> str:
        """Where changes go, for the menu's last line."""
        if self.prefs is None:
            return "changes last until you quit (no settings file)"
        if self.save_error:
            return f"NOT SAVED: {self.save_error}"
        path = str(self.prefs.path)
        home = os.environ.get("HOME", "")
        if home not in ("", "/") and path.startswith(home.rstrip("/") + "/"):
            path = "~" + path[len(home.rstrip("/")) :]
        return f"saved in {path}"

    def toast(self, text: str) -> None:
        """Name a change in the title bar for a moment (a new look, the effects level)."""
        self.toast_text = text
        self.toast_until = time.monotonic() + TOAST_SECONDS

    def cycle(self, now: float) -> None:
        """Move on to the next look when it is time, skipping the plain default look."""
        if not self.cycle_seconds or now < self.next_cycle_at:
            return
        nxt = th.next_theme(self.theme)
        if nxt.name == th.DEFAULT.name:
            nxt = th.next_theme(nxt)
        if nxt.name == self.theme.name:
            self.next_cycle_at = now + self.cycle_seconds
            return
        self.set_theme(nxt, announce=True)

    # ---- data ---------------------------------------------------------------------------

    def load(self) -> None:
        try:
            mtime = self.state.stat().st_mtime
            if mtime == self.mtime:
                return
            self.snapshot = as_dict(json.loads(self.state.read_text()))
            self.mtime = mtime
            self.load_error = ""
        except FileNotFoundError:
            self.load_error = f"waiting for {self.state} (is lxtop-collect running?)"
        except (OSError, ValueError) as exc:
            self.load_error = f"cannot read {self.state}: {exc}"
        for page in self.pages:
            page.loaded(self.snapshot)

    @property
    def current(self) -> Page:
        return next((p for p in self.pages if p.name == self.page), self.pages[0])

    def page_named(self, name: str) -> Page:
        return next(p for p in self.pages if p.name == name)

    def next_page(self, step: int = 1) -> Page:
        """The page Tab (step 1) or Shift-Tab (step -1) goes to."""
        names = [p.name for p in self.pages]
        index = names.index(self.current.name)
        return self.pages[(index + step) % len(self.pages)]

    # ---- input --------------------------------------------------------------------------

    def handle(self, key: int) -> bool:
        """Apply one key press; False means quit."""
        return keys.handle(self, key)

    # ---- drawing ------------------------------------------------------------------------

    def draw(self) -> None:
        s = self.screen
        now = time.monotonic()
        if now - self.last_clear > 60:
            s.win.clear()  # wipes kernel messages printed over the console
            self.last_clear = now
        else:
            s.win.erase()
        self.cycle(now)
        s.begin()
        if now < self.boot_until:
            effects.draw_boot(self, now)
            s.win.refresh()
            return
        s.scramble = effects.decode_share(self, now)
        self.draw_page()
        s.scramble = 0.0
        effects.draw_fx(self, now)
        s.win.refresh()

    def draw_page(self) -> None:
        h, w = self.screen.size
        self.frame = Frame(self.screen, self.snapshot, self.load_error)
        page = self.current
        subtitle = page.subtitle(self.frame, h - 1, w)
        if subtitle is not None:
            chrome.draw_title(self, w, page.title, subtitle)
        page.draw(self.frame, h - 1, w)
        chrome.draw_footer(self, h, w)
        if self.help:
            chrome.draw_help(self, h, w)
        if self.menu is not None:
            self.menu.draw(self, h, w)


def run(
    win: Any,
    state: Path,
    glyphs: Glyphs,
    theme: th.Theme = th.DEFAULT,
    cycle: float = 0.0,
    font: ConsoleFont | None = None,
    prefs: Prefs | None = None,
) -> None:
    curses.curs_set(0)
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
    win.keypad(True)
    console = os.environ.get("TERM") == "linux"
    app = App(win, state, glyphs, theme, console=console, cycle=cycle, font=font, prefs=prefs)
    try:
        while True:
            app.load()
            app.draw()
            if not app.handle(win.getch()):
                return
    finally:
        if app.console and app.theme.console_palette:
            app.write_palette(())


def main(
    state: Path,
    glyphs: Glyphs,
    theme: th.Theme = th.DEFAULT,
    cycle: float = 0.0,
    font: ConsoleFont | None = None,
    prefs: Prefs | None = None,
) -> int:
    if os.environ.get("TERM") == "linux":
        # The Linux console blanks after 10 minutes by default; a dashboard should not.
        sys.stdout.write("\033[9;0]\033[14;0]")
        sys.stdout.flush()
    os.environ.setdefault("ESCDELAY", "25")
    with contextlib.suppress(KeyboardInterrupt):  # Ctrl-C quits like q
        curses.wrapper(run, state, glyphs, theme, cycle, font, prefs)
    if os.environ.get("TERM") == "linux":
        # The console has no alternate screen: without this the last frame stays behind.
        sys.stdout.write("\033[H\033[2J")
        sys.stdout.flush()
    return 0
