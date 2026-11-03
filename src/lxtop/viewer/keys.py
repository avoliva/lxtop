"""The viewer's own keys; every other key goes to the page showing (pages/base.py)."""

from __future__ import annotations

import curses
import time
from typing import TYPE_CHECKING

from lxtop.looks import theme as th
from lxtop.viewer.menu import Menu

if TYPE_CHECKING:
    from lxtop.viewer.app import App


def handle(app: App, key: int) -> bool:
    """Apply one key press; False means quit."""
    if key == -1:
        return True
    if time.monotonic() < app.boot_until:  # any key skips the boot
        app.boot_until = float("-inf")
        app.decode_from = time.monotonic()
        return True
    if app.menu is not None:  # the settings menu takes every key while it is open
        if not app.menu.handle(app, key):
            app.menu = None
        return True
    if key in (ord("t"), ord("T")):
        app.set_theme(th.next_theme(app.theme, 1 if key == ord("t") else -1), announce=True)
        app.remember(look=app.theme.name)
        return True
    if key == ord("r") and app.backdrop is not None:
        app.fx_level = th.next_fx(app.fx_level)
        app.remember(effects=app.fx_level)
        app.toast(f"effects: {th.FX_SHOWN.get(app.fx_level, app.fx_level)}")
        return True
    if app.help:
        app.help = False
        return True
    if key in (ord("q"), ord("Q")):
        return False
    if key == ord("\t") or key == curses.KEY_BTAB:
        app.page = app.next_page(-1 if key == curses.KEY_BTAB else 1).name
        app.decode_from = time.monotonic()
        return True
    number = key - ord("1")
    if 0 <= number < min(9, len(app.pages)):
        if app.page != app.pages[number].name:
            app.decode_from = time.monotonic()
        app.page = app.pages[number].name
        return True
    if key == ord("?"):
        app.help = True
        return True
    if key in (ord("o"), ord("O")):
        app.menu = Menu()
        return True
    app.current.handle(key, app.frame)
    return True
