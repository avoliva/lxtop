from __future__ import annotations

import curses
import time

import pytest

from lxtop.looks import theme
from lxtop.looks.theme import FX_MID, GLASS
from lxtop.viewer import app as view
from lxtop.viewer import effects as view_effects
from lxtop.viewer.screen import GLASS_CELL
from tests.support.curses_win import FakeWin, make_app

pytestmark = pytest.mark.usefixtures("headless")


class AttrWin(FakeWin):
    """A FakeWin that also remembers the attribute each cell was drawn with."""

    def __init__(self, h: int, w: int) -> None:
        super().__init__(h, w)
        self.attrs: dict[tuple[int, int], int] = {}

    def addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        super().addstr(y, x, text, attr)
        for i in range(len(text)):
            self.attrs[(y, x + i)] = attr


class Cells:
    """A backdrop that shows the same cells at every moment."""

    def __init__(self, cells: list[tuple[int, int, str, int]]) -> None:
        self.cells = cells

    def resize(self, h: int, w: int) -> None:
        pass

    def frame(self, now: float) -> list[tuple[int, int, str, int]]:
        return self.cells


def effects_app(
    monkeypatch: pytest.MonkeyPatch,
    cells: list[tuple[int, int, str, int]],
    colours: bool = False,
    look: str = "tron",
) -> view.App:
    """A Tron App on an AttrWin that shows `cells` as its backdrop and is ready for a frame.
    `colours`: a 256-colour terminal, patched in after the App is built (building it sets the
    colour pairs, which needs a real screen)."""
    app: view.App = make_app(theme.THEMES[look], "network", 40, 120)
    app.screen.win = AttrWin(40, 120)
    app.fx_level = "full"
    app.backdrop = Cells(cells)
    if colours:
        monkeypatch.setattr(curses, "has_colors", lambda: True)
        monkeypatch.setattr(curses, "COLORS", 256, raising=False)
        monkeypatch.setattr(curses, "color_pair", lambda pair: pair << 8)
        monkeypatch.setattr(curses, "pair_number", lambda attr: attr >> 8)
    app.screen.begin()
    return app


def test_a_cell_with_an_unknown_tone_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    app = effects_app(monkeypatch, [(5, 10, "x", 99), (5, 20, "y", FX_MID)])

    view_effects.draw_fx(app, 0.0)

    assert app.screen.win.cells == {(5, 20): "y"}


def test_an_effect_over_a_tinted_panel_takes_the_glass_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = effects_app(monkeypatch, [(5, 10, "*", FX_MID)], colours=True)
    app.screen.box(2, 2, 10, 30)
    assert app.screen.kind(5, 10) == GLASS_CELL

    view_effects.draw_fx(app, 0.0)

    assert app.screen.win.cells[(5, 10)] == "*"
    assert app.screen.win.attrs[(5, 10)] == (GLASS + FX_MID) << 8


def test_an_effect_outside_a_tinted_panel_keeps_its_plain_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = effects_app(monkeypatch, [(20, 50, "*", FX_MID)], colours=True)
    app.screen.box(2, 2, 10, 30)

    view_effects.draw_fx(app, 0.0)

    assert app.screen.win.cells[(20, 50)] == "*"
    assert app.screen.win.attrs[(20, 50)] == FX_MID << 8


def _glass_marks(look: theme.Theme) -> int:
    """How many characters the effects leave inside panels over a few seconds of frames."""
    app = make_app(look, "network", 40, 120)
    app.fx_level = "full"
    marks = 0
    start = time.monotonic()
    for step in range(40):
        app.screen.win.clear()
        app.screen.begin()
        app.draw_page()
        before = dict(app.screen.win.cells)
        view_effects.draw_fx(app, start + step * 0.25)
        for (y, x), char in app.screen.win.cells.items():
            if before.get((y, x)) != char and app.screen.kind(y, x) == 2 and char != " ":
                marks += 1
    return marks


def test_matrix_effects_leave_marks_inside_panels_behind_the_glass() -> None:
    assert theme.THEMES["matrix"].see_through
    assert _glass_marks(theme.THEMES["matrix"]) > 0


@pytest.mark.parametrize("name", ["tron", "aquarium", "snow"])
def test_effects_in_front_leave_marks_inside_panels(name: str) -> None:
    assert not theme.THEMES[name].see_through
    assert _glass_marks(theme.THEMES[name]) > 0


def test_effects_in_front_cross_empty_chart_space_but_never_touch_characters() -> None:
    app = make_app(theme.THEMES["tron"], "network", 60, 213)
    app.fx_level = "light"
    start = time.monotonic()
    over_blank_ink = 0
    touched = []
    for step in range(30):
        app.screen.win.clear()
        app.screen.begin()
        app.draw_page()
        before = dict(app.screen.win.cells)
        s = app.screen
        view_effects.draw_fx(app, start + step * 0.3)
        for (y, x), char in s.win.cells.items():
            if before.get((y, x)) == char:
                continue
            if s.solid_at(y, x) != 0 or 2 in (s.solid_at(y, x - 1), s.solid_at(y, x + 1)):
                touched.append((y, x))  # over a visible character
            if s.kind(y, x) == 1:  # drawn on but blank: chart space, padding
                over_blank_ink += 1
    assert touched == []
    assert over_blank_ink > 0
