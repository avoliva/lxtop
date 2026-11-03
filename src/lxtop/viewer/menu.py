"""The settings menu: `o` opens it over any page. Up and Down pick a setting, Left and
Right (or Enter) change it, and each change shows at once and is saved (`viewer/prefs.py`).
Esc, o or q closes it. Text is ASCII only, so it reads the same with the console's font."""

from __future__ import annotations

import curses
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lxtop.core import settings as st
from lxtop.core.render import fit
from lxtop.looks import theme as th
from lxtop.viewer.screen import WHITE, color

if TYPE_CHECKING:
    from lxtop.viewer.app import App

BOX_WIDTH = 66
CLOSE = (27, ord("o"), ord("O"), ord("q"), ord("Q"))
UP = (curses.KEY_UP, ord("k"))
DOWN = (curses.KEY_DOWN, ord("j"))
LEFT = (curses.KEY_LEFT, ord("h"))
RIGHT = (curses.KEY_RIGHT, ord("l"), 10, 13, curses.KEY_ENTER, ord(" "))


@dataclass(frozen=True)
class Row:
    label: str
    value: Callable[[App], str]  # what it is set to now
    change: Callable[[App, int], None]  # step it by +1 or -1


def change_look(app: App, by: int) -> None:
    app.set_theme(th.next_theme(app.theme, by))
    app.remember(look=app.theme.name)


def change_cycle(app: App, by: int) -> None:
    app.set_cycle(st.step_cycle(app.cycle_seconds, by))
    app.remember(cycle_seconds=app.cycle_seconds)


def change_effects(app: App, by: int) -> None:
    app.fx_level = st.step(st.EFFECTS, app.fx_level, by)
    app.remember(effects=app.fx_level)


def change_start_page(app: App, by: int) -> None:
    names = tuple(p.name for p in app.pages)
    app.remember(start_page=st.step(names, app.start_page, by))


def change_boot(app: App, by: int) -> None:
    app.remember(boot=not app.boot_lines)


def reset(app: App, by: int) -> None:
    app.reset_settings()


def effects_value(app: App) -> str:
    shown = th.FX_SHOWN.get(app.fx_level, app.fx_level)
    return shown if app.backdrop is not None else f"{shown} (this look has none)"


def look_value(app: App) -> str:
    return app.theme.name


def cycle_value(app: App) -> str:
    return st.cycle_label(app.cycle_seconds)


def boot_value(app: App) -> str:
    return "on" if app.boot_lines else "off"


def reset_value(app: App) -> str:
    return "Enter"


def page_label(app: App) -> str:
    return next((p.label for p in app.pages if p.name == app.start_page), app.start_page)


ROWS = (
    Row("Look", look_value, change_look),
    Row("Change look every", cycle_value, change_cycle),
    Row("Effects", effects_value, change_effects),
    Row("Open on page", page_label, change_start_page),
    Row("Boot lines at start", boot_value, change_boot),
    Row("Reset to defaults", reset_value, reset),
)


@dataclass
class Menu:
    row: int = 0

    def handle(self, app: App, key: int) -> bool:
        """Apply a key while the menu is open; False closes it."""
        if key in CLOSE:
            return False
        if key in UP:
            self.row = (self.row - 1) % len(ROWS)
        elif key in DOWN:
            self.row = (self.row + 1) % len(ROWS)
        elif key in LEFT and ROWS[self.row].change is not reset:
            ROWS[self.row].change(app, -1)
        elif key in RIGHT:
            ROWS[self.row].change(app, 1)
        return True

    def lines(self, app: App) -> list[tuple[str, bool]]:
        """The menu's text, one (line, selected) a row."""
        out = []
        for i, row in enumerate(ROWS):
            value = row.value(app)
            shown = value if row.change is reset else f"< {value} >"
            mark = ">" if i == self.row else " "
            out.append((f" {mark} {row.label:<22}{shown}", i == self.row))
        return out

    def draw(self, app: App, h: int, w: int) -> None:
        s = app.screen
        lines = self.lines(app)
        notes = [
            "   Up/Down choose   Left/Right change   Esc closes",
            "   " + app.settings_note(),
        ]
        x = max(0, (w - BOX_WIDTH) // 2)
        y = max(0, (h - len(lines) - len(notes) - 4) // 2)
        s.put(y, x, fit(" settings ", BOX_WIDTH), color(WHITE, True) | curses.A_REVERSE)
        y += 1
        s.put(y, x, fit("", BOX_WIDTH), curses.A_REVERSE)
        for text, selected in lines:
            y += 1
            attr = curses.A_REVERSE | (curses.A_BOLD if selected else 0)
            if selected:
                attr |= color(app.theme.accent, True)
            s.put(y, x, fit(text, BOX_WIDTH), attr)
        s.put(y + 1, x, fit("", BOX_WIDTH), curses.A_REVERSE)
        for i, note in enumerate(notes, start=2):
            s.put(y + i, x, fit(note, BOX_WIDTH), curses.A_REVERSE)
        s.put(y + len(notes) + 2, x, fit("", BOX_WIDTH), curses.A_REVERSE)
