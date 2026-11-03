"""Screen: which cells hold text, boxes and glass, and how a scrambled put draws."""

from __future__ import annotations

import random

from lxtop.core import render
from lxtop.looks.matrix import THEME as MATRIX
from lxtop.viewer.screen import GLASS_CELL, INK, OPEN, Screen
from tests.support.curses_win import FakeWin


def test_screen_marks_text_and_box_insides_so_rain_misses_them() -> None:
    s = Screen(FakeWin(), render.UNICODE, theme=MATRIX)
    s.begin()
    s.put(0, 2, "hello")
    s.box(3, 10, 4, 8)
    assert not s.free(0, 2) and not s.free(0, 6) and s.free(0, 7)
    assert not s.free(4, 13)  # inside the box
    assert s.free(4, 20) and not s.free(-1, 0) and not s.free(0, 99)
    assert s.win.cells[(3, 10)] == "╔" and s.win.cells[(6, 17)] == "╝"
    s.put(1, 35, "past the edge")  # clipped, never raises
    assert not s.free(1, 39)


def test_screen_scramble_changes_what_is_drawn_not_where() -> None:
    win = FakeWin()
    s = Screen(win, render.UNICODE, scramble=1.0, noise="#", rng=random.Random(2))
    s.begin()
    assert s.put(2, 0, "AB CD") == 5
    assert [win.cells[(2, i)] for i in range(5)] == ["#", "#", " ", "#", "#"]


def test_panel_frames_a_section_around_its_title_row_and_its_inside_is_glass() -> None:
    win = FakeWin(20, 40)
    s = Screen(win, render.UNICODE, theme=MATRIX)
    s.begin()
    s.panel(2, 5, 6, 10)  # a section at rows 2..7, columns 5..14
    assert win.cells[(2, 4)] == "╔" and win.cells[(2, 15)] == "╗"
    assert win.cells[(8, 4)] == "╚" and win.cells[(8, 15)] == "╝"
    assert s.kind(5, 9) == GLASS_CELL and s.kind(5, 4) == INK and s.kind(5, 16) == OPEN
    assert s.glass == [(3, 5, 5, 10)]
    s.put(5, 6, "42")  # text drawn on glass is ink; glass marked later never covers it
    s.mark(5, 0, 20, GLASS_CELL)
    assert s.kind(5, 6) == INK and s.kind(5, 1) == GLASS_CELL


def test_without_panels_nothing_is_framed_and_box_insides_stay_ink() -> None:
    win = FakeWin(20, 40)
    s = Screen(win, render.UNICODE)
    s.begin()
    s.panel(2, 5, 6, 10)
    assert win.cells == {} and s.glass == []
    s.box(2, 5, 4, 6)
    assert s.kind(3, 7) == INK and s.glass == []
