"""view_chrome: the help overlay."""

from __future__ import annotations

import pytest

from lxtop.looks import theme
from lxtop.viewer import app as view
from lxtop.viewer import chrome as view_chrome
from tests.support.curses_win import make_app

pytestmark = pytest.mark.usefixtures("headless")


def test_help_overlay_lists_the_keys() -> None:
    app: view.App = make_app(theme.DEFAULT, "machines", 40, 120)
    app.screen.begin()

    view_chrome.draw_help(app, 40, 120)

    grid = app.screen.win.grid()
    lines = view_chrome.help_lines(app.pages)
    assert " keys (any key closes)" in grid
    assert all(f"  {key:<20}{what}"[:60].rstrip() in grid for key, what in lines)  # 74 wide


def test_the_help_is_built_from_the_pages_in_order() -> None:
    """The help lists every page in order, then each page's own keys."""
    app = make_app(theme.DEFAULT, "network", 40, 120)

    assert view_chrome.help_lines(app.pages) == [
        (
            "Tab",
            "next page: network, all machines, memory & jobs, timers & services",
        ),
        (
            "1  2  3  4",
            "network  /  all machines  /  memory & jobs  /  timers & services",
        ),
        ("", ""),
        ("All machines page", ""),
        ("↑ ↓  j k", "select"),
        ("PgUp PgDn  g G", "page, first, last"),
        ("→ ←  l h  Enter", "open or fold an instance, jump to parent"),
        ("e  c", "open all, fold all"),
        ("s", "sort by name, CPU, memory"),
        ("d", "detail page (narrow screens)"),
        ("", ""),
        ("t  T", "next look, previous look (--theme NAME starts in one)"),
        ("", "the look changes by itself; o sets how often (--cycle SECONDS: one run)"),
        ("r", "effects: on, max, off (they start on; the footer shows which)"),
        ("o", "settings: look, how often it changes, effects, first page; saved"),
        ("?", "this help"),
        ("q  Ctrl-C", "quit"),
    ]
