"""A window that records what is drawn, for lxtop's view tests."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from lxtop.core import render
from lxtop.viewer import app as view
from lxtop.viewer.pages.base import Frame
from lxtop.viewer.pages.machines import MachinesPage
from lxtop.viewer.pages.network import NetworkPage
from tests.support.snapshot import full_snapshot


class FakeWin:
    def __init__(self, h: int = 10, w: int = 40) -> None:
        self.h, self.w = h, w
        self.cells: dict[tuple[int, int], str] = {}

    def getmaxyx(self) -> tuple[int, int]:
        return self.h, self.w

    def addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        for i, char in enumerate(text):
            self.cells[(y, x + i)] = char

    # What view.App.draw / set_theme call on a real window:
    def timeout(self, ms: int) -> None:
        self.ms = ms

    def bkgd(self, *args: object) -> None:
        pass

    def clear(self) -> None:
        self.cells.clear()

    erase = clear

    def refresh(self) -> None:
        pass

    def grid(self) -> str:
        """The screen as text: one line per row, trailing spaces trimmed."""
        rows = [
            "".join(self.cells.get((y, x), " ") for x in range(self.w)).rstrip()
            for y in range(self.h)
        ]
        return "\n".join(rows).rstrip() + "\n"


class KeyedWin(FakeWin):
    """A FakeWin that hands `view.run` its keys one by one."""

    def __init__(self, h: int, w: int, keys: list[int]) -> None:
        super().__init__(h, w)
        self.keys = list(keys)
        self.keypad_on: bool | None = None

    def getch(self) -> int:
        if not self.keys:
            raise AssertionError("run read more keys than the test gave it")
        return self.keys.pop(0)

    def keypad(self, flag: bool) -> None:
        self.keypad_on = flag


def make_app(th: Any, page: str, h: int, w: int) -> Any:
    """A view.App on a FakeWin, showing `page` with the full snapshot and every time-driven
    effect (boot screen, decoding, title glitch, rain) switched off."""
    app = view.App(FakeWin(h, w), Path("/nonexistent"), render.UNICODE, th, rng=random.Random(1))
    app.snapshot = full_snapshot()
    app.page = page
    app.boot_until = app.decode_from = float("-inf")
    app.glitch_at = float("inf")
    app.fx_level = "off"
    return app


def frame_of(app: Any) -> Frame:
    """What a page draws from, built from `app`'s screen and snapshot as App.draw does."""
    return Frame(app.screen, app.snapshot, app.load_error)


def network_page(app: Any) -> NetworkPage:
    page = app.page_named("network")
    assert isinstance(page, NetworkPage)
    return page


def machines_page(app: Any) -> MachinesPage:
    page = app.page_named("machines")
    assert isinstance(page, MachinesPage)
    return page
