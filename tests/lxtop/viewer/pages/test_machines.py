"""The all-machines page: what each of its keys does to the selection, the folding and the
detail, and that the tree is the page's own state."""

from __future__ import annotations

import curses

import pytest

from lxtop.core.model import Row
from lxtop.looks import theme
from lxtop.viewer import app as view
from lxtop.viewer.pages.machines import MachinesPage
from tests.support.curses_win import frame_of, machines_page, make_app

pytestmark = pytest.mark.usefixtures("headless")


def shown(h: int = 40, w: int = 120) -> tuple[view.App, MachinesPage, list[Row]]:
    """The machines page drawn once: the app, the page and its rows (host, app, demo, idle at
    40x120)."""
    app: view.App = make_app(theme.DEFAULT, "machines", h, w)
    app.draw()
    page = machines_page(app)
    return app, page, page.rows


@pytest.mark.parametrize(
    ("key", "start", "expected"),
    (
        (curses.KEY_DOWN, 0, 1),
        (ord("j"), 0, 1),
        (curses.KEY_UP, 1, 0),
        (ord("k"), 1, 0),
        (curses.KEY_NPAGE, 0, 3),  # a page is the screen less 8 rows: past the end
        (curses.KEY_PPAGE, 3, 0),
        (curses.KEY_HOME, 2, 0),
        (curses.KEY_END, 0, 3),
    ),
    ids=("down", "j", "up", "k", "page down", "page up", "home", "end"),
)
def test_a_movement_key_selects_a_row(key: int, start: int, expected: int) -> None:
    app, page, rows = shown()
    page.selected = rows[start].key

    assert page.handle(key, frame_of(app)) is True

    assert page.selected == rows[expected].key


def test_right_expands_and_left_collapses_a_machine() -> None:
    app, page, rows = shown()
    page.expanded = set()
    page.selected = rows[0].key

    page.handle(curses.KEY_RIGHT, frame_of(app))
    opened = set(page.expanded)
    page.handle(curses.KEY_LEFT, frame_of(app))

    assert opened == {rows[0].key}
    assert page.expanded == set()


def test_left_on_a_child_selects_its_parent() -> None:
    app, page, rows = shown(60, 213)
    page.handle(ord("e"), frame_of(app))
    app.draw()
    rows = page.rows
    child = next(r for r in rows if r.depth == 1)
    page.selected = child.key

    page.handle(ord("h"), frame_of(app))

    assert (child.key, page.selected) == ("i:apps/app/c:4a8290f0069f", "i:apps/app")


def test_enter_toggles_a_machine_and_opens_the_detail_for_a_child() -> None:
    app, page, rows = shown(60, 213)
    page.expanded = set()
    page.selected = rows[0].key
    page.handle(curses.KEY_ENTER, frame_of(app))
    toggled_open = rows[0].key in page.expanded
    page.handle(ord("e"), frame_of(app))
    app.draw()
    rows = page.rows
    page.selected = next(r.key for r in rows if r.depth == 1)

    page.handle(ord(" "), frame_of(app))

    assert toggled_open is True
    assert page.detail_page is True


def test_e_expands_every_machine() -> None:
    app, page, rows = shown()
    page.expanded = set()

    page.handle(ord("e"), frame_of(app))

    assert page.expanded == {r.key for r in rows if r.depth == 0}


def test_d_toggles_the_detail_page() -> None:
    app, page, _ = shown()

    page.handle(ord("d"), frame_of(app))
    on = page.detail_page
    page.handle(ord("d"), frame_of(app))

    assert (on, page.detail_page) == (True, False)


def test_a_key_that_is_not_the_pages_own_is_left_alone() -> None:
    app, page, _ = shown()
    before = (page.selected, set(page.expanded), page.sort)

    assert page.handle(ord("z"), frame_of(app)) is False

    assert (page.selected, page.expanded, page.sort) == before


def test_s_cycles_the_sort() -> None:
    app, page, _ = shown()

    page.handle(ord("s"), frame_of(app))
    first = page.sort
    page.handle(ord("s"), frame_of(app))

    assert (first, page.sort) == ("cpu", "mem")


def test_an_instance_seen_for_the_first_time_starts_open_and_stays_folded_once_folded() -> None:
    app, page, rows = shown()
    instance = next(r.key for r in rows if r.depth == 0 and r.key != "host")
    page.loaded(app.snapshot)
    opened = instance in page.expanded

    page.expanded.discard(instance)
    page.loaded(app.snapshot)

    assert opened and instance in page.seen and instance not in page.expanded
