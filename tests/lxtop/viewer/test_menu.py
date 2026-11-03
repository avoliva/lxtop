"""viewer.menu: the settings menu changes the running viewer at once and saves each change;
keys.handle hands it every key while it is open."""

from __future__ import annotations

import curses
import json
from pathlib import Path

import pytest

from lxtop.core import settings as st
from lxtop.looks import theme
from lxtop.viewer import app as view
from lxtop.viewer import keys, menu
from lxtop.viewer.prefs import Prefs
from tests.support.curses_win import make_app

pytestmark = pytest.mark.usefixtures("headless")

LOOK, CYCLE, EFFECTS, PAGE, BOOT, RESET = range(len(menu.ROWS))


def opened(tmp_path: Path, row: int = 0) -> tuple[view.App, Path]:
    """An app on the network page with the menu open at `row`, saving to a file in tmp_path."""
    app: view.App = make_app(theme.DEFAULT, "network", 40, 120)
    path = tmp_path / "s.json"
    app.prefs = Prefs(path, st.Settings())
    app.settings = app.prefs.settings
    app.fx_level = "light"  # make_app turns effects off and the cycle is 0; start at the defaults
    app.set_cycle(300.0)
    keys.handle(app, ord("o"))
    assert app.menu is not None
    app.menu.row = row
    return app, path


def saved(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text())
    assert isinstance(data, dict)
    return data


def test_o_opens_the_menu_and_esc_o_and_q_close_it(tmp_path: Path) -> None:
    for key in (27, ord("o"), ord("q")):
        app, _ = opened(tmp_path)

        assert keys.handle(app, key) is True  # q closes the menu, it does not quit

        assert app.menu is None


def test_up_and_down_move_round_the_rows(tmp_path: Path) -> None:
    app, _ = opened(tmp_path)
    assert app.menu is not None

    keys.handle(app, curses.KEY_UP)
    assert app.menu.row == RESET
    keys.handle(app, ord("j"))
    assert app.menu.row == LOOK


def test_other_keys_do_not_reach_the_page_or_the_look(tmp_path: Path) -> None:
    app, _ = opened(tmp_path)

    keys.handle(app, ord("t"))
    keys.handle(app, ord("\t"))

    assert (app.theme.name, app.page) == ("default", "network")


def test_the_look_changes_now_and_is_saved(tmp_path: Path) -> None:
    app, path = opened(tmp_path, LOOK)

    keys.handle(app, curses.KEY_RIGHT)

    nxt = theme.next_theme(theme.DEFAULT).name
    assert app.theme.name == nxt
    assert saved(path) == {"version": st.VERSION, "look": nxt}
    keys.handle(app, curses.KEY_LEFT)
    assert app.theme.name == "default"
    assert saved(path) == {"version": st.VERSION}


def test_the_cycle_changes_now_and_is_saved(tmp_path: Path) -> None:
    app, path = opened(tmp_path, CYCLE)

    keys.handle(app, curses.KEY_RIGHT)

    assert app.cycle_seconds == 600.0
    assert app.next_cycle_at == 1000.0 + 600.0  # the headless clock is at 1000
    assert saved(path)["cycle_seconds"] == 600.0
    app.menu = menu.Menu(CYCLE)
    for _ in range(4):
        keys.handle(app, curses.KEY_LEFT)
    assert app.cycle_seconds == 0.0
    assert app.next_cycle_at == float("inf")


def test_effects_page_and_boot_are_saved(tmp_path: Path) -> None:
    app, path = opened(tmp_path, EFFECTS)
    keys.handle(app, curses.KEY_RIGHT)
    app.menu = menu.Menu(PAGE)
    keys.handle(app, ord("l"))
    app.menu = menu.Menu(BOOT)
    keys.handle(app, 10)

    assert app.fx_level == "full"
    assert saved(path) == {
        "version": st.VERSION,
        "effects": "full",
        "start_page": "machines",
        "boot": False,
    }
    assert app.page == "network"  # the page showing stays; the setting is for the next start


def test_reset_goes_back_to_the_defaults_now_and_on_disk(tmp_path: Path) -> None:
    app, path = opened(tmp_path, LOOK)
    keys.handle(app, curses.KEY_RIGHT)
    app.menu = menu.Menu(CYCLE)
    keys.handle(app, curses.KEY_RIGHT)
    app.menu = menu.Menu(RESET)

    keys.handle(app, curses.KEY_LEFT)  # Left does nothing on the reset row
    assert app.theme.name != "default"
    keys.handle(app, 10)

    assert (app.theme.name, app.cycle_seconds, app.fx_level) == ("default", 300.0, "light")
    assert saved(path) == {"version": st.VERSION}


def test_the_menu_draws_every_row_with_its_value_and_where_it_saves(tmp_path: Path) -> None:
    app, path = opened(tmp_path, CYCLE)
    app.draw()

    grid = app.screen.win.grid()

    assert " settings " in grid
    rows = [
        ("  ", "Look", "< default >"),
        ("> ", "Change look every", "< 5 min >"),
        ("  ", "Effects", "< on (this look has none) >"),
        ("  ", "Open on page", "< network >"),
        ("  ", "Boot lines at start", "< on >"),
        ("  ", "Reset to defaults", "Enter"),
    ]
    for mark, label, value in rows:
        assert f" {mark}{label:<22}{value}" in grid
    assert str(path)[:40] in grid


def test_without_a_file_the_menu_says_changes_last_until_quitting(tmp_path: Path) -> None:
    app: view.App = make_app(theme.DEFAULT, "network", 40, 120)
    keys.handle(app, ord("o"))
    keys.handle(app, curses.KEY_RIGHT)
    app.draw()

    assert "changes last until you quit" in app.screen.win.grid()
    assert app.settings.look == theme.next_theme(theme.DEFAULT).name


def test_a_failed_save_is_shown_in_the_menu(tmp_path: Path) -> None:
    app, _ = opened(tmp_path, LOOK)
    assert app.prefs is not None
    app.prefs.put = lambda settings: "Permission denied"  # type: ignore[method-assign]

    keys.handle(app, curses.KEY_RIGHT)
    app.draw()

    assert "NOT SAVED: Permission denied" in app.screen.win.grid()
