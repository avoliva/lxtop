from __future__ import annotations

import curses
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from lxtop.core import render
from lxtop.core import settings as st
from lxtop.looks import theme
from lxtop.viewer import app as view
from lxtop.viewer import colours
from lxtop.viewer.prefs import Prefs
from tests.support.curses_win import FakeWin, KeyedWin, machines_page, make_app
from tests.support.snapshot import collector

pytestmark = pytest.mark.usefixtures("headless")

GOLDEN = Path(__file__).parents[1] / "golden"
SIZES = {"network": (40, 120), "machines": (40, 120), "memory": (40, 120), "services": (40, 120)}
LOOKS = list(theme.THEMES.values())
LOOK_IDS = list(theme.THEMES)
TITLES = {
    "network": "NETWORK",
    "machines": "ALL MACHINES",
    "memory": "MEMORY",
    "services": "TIMERS & SERVICES",
}


@pytest.mark.parametrize("th", LOOKS, ids=LOOK_IDS)
@pytest.mark.parametrize("page", list(SIZES))
def test_every_page_draws_in_every_look(th: theme.Theme, page: str) -> None:
    app = make_app(th, page, *SIZES[page])
    app.draw()
    assert TITLES[page] in app.screen.win.grid().splitlines()[0]
    assert len(app.screen.win.cells) > 500


@pytest.mark.parametrize("th", LOOKS, ids=LOOK_IDS)
@pytest.mark.parametrize("page", list(SIZES))
@pytest.mark.parametrize("size", [(1, 1), (3, 20), (5, 5)])
def test_a_tiny_window_draws_only_inside_the_window(
    th: theme.Theme, page: str, size: tuple[int, int]
) -> None:
    h, w = size
    app = make_app(th, page, h, w)
    app.draw()
    outside = [pos for pos in app.screen.win.cells if not (0 <= pos[0] < h and 0 <= pos[1] < w)]
    assert outside == []


def test_r_does_nothing_in_a_look_without_a_backdrop() -> None:
    app = make_app(theme.DEFAULT, "machines", 40, 120)
    app.fx_level = "light"
    app.handle(ord("r"))
    assert app.fx_level == "light"


def test_r_cycles_the_effects_level_in_a_look_with_a_backdrop() -> None:
    app = make_app(theme.THEMES["tron"], "machines", 40, 120)
    app.fx_level = "light"
    levels = []
    for _ in range(3):
        app.handle(ord("r"))
        levels.append(app.fx_level)
    assert levels == ["full", "off", "light"]


def test_question_mark_opens_help() -> None:
    app = make_app(theme.DEFAULT, "machines", 40, 120)
    assert app.handle(ord("?")) is True
    assert app.help


def test_any_key_closes_help() -> None:
    app = make_app(theme.DEFAULT, "machines", 40, 120)
    app.help = True
    app.handle(ord("x"))
    assert not app.help


def test_q_quits() -> None:
    app = make_app(theme.DEFAULT, "machines", 40, 120)
    assert app.handle(ord("q")) is False


@pytest.mark.parametrize(("key", "start", "want"), [("j", 0, 1), ("G", 0, -1), ("g", -1, 0)])
def test_a_movement_key_selects_a_row(key: str, start: int, want: int) -> None:
    app = make_app(theme.DEFAULT, "machines", 40, 120)
    app.draw()
    rows = machines_page(app).rows
    machines_page(app).selected = rows[start].key
    app.handle(ord(key))
    assert machines_page(app).selected == rows[want].key


def test_s_changes_the_sort_order() -> None:
    app = make_app(theme.DEFAULT, "machines", 40, 120)
    app.draw()
    before = machines_page(app).sort
    app.handle(ord("s"))
    assert machines_page(app).sort != before


def test_c_folds_every_machine() -> None:
    app = make_app(theme.DEFAULT, "machines", 40, 120)
    app.draw()
    assert machines_page(app).expanded == {"host"}
    app.handle(ord("c"))
    assert not machines_page(app).expanded


def test_any_key_ends_the_boot() -> None:
    app = make_app(theme.DEFAULT, "machines", 40, 120)
    app.boot_until = 2000.0
    assert app.handle(ord("x")) is True
    assert app.boot_until == float("-inf")


CASES = [
    ("default", "services", 40, 120), ("default", "network", 40, 120),
    ("default", "machines", 40, 120), ("default", "machines", 60, 213),
    ("default", "machines", 30, 100), ("matrix", "services", 40, 120),
    ("matrix", "network", 40, 120), ("matrix", "machines", 40, 120),
    ("matrix", "machines", 60, 213), ("matrix", "machines", 30, 100),
]  # fmt: skip


@pytest.mark.parametrize(("look", "page", "h", "w"), CASES)
def test_draw_output_is_unchanged(look: str, page: str, h: int, w: int) -> None:
    app = make_app(theme.THEMES[look], page, h, w)
    app.draw()
    got = app.screen.win.grid()
    path = GOLDEN / f"{look}-{page}-{h}x{w}.txt"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        if os.environ.get("CI"):
            pytest.fail("UPDATE_GOLDEN is for a local, deliberate drawing change")
        path.parent.mkdir(exist_ok=True)
        path.write_text(got)
        pytest.skip(f"rewrote {path.name}; review the diff and rerun without UPDATE_GOLDEN")
    want = path.read_text()
    assert got == want, f"{path.name} differs; UPDATE_GOLDEN=1 only for a deliberate look change"


def test_every_golden_file_belongs_to_a_case() -> None:
    cases = {f"{look}-{page}-{h}x{w}.txt" for look, page, h, w in CASES}
    assert {p.name for p in GOLDEN.glob("*.txt")} == cases


def test_a_light_look_can_set_its_own_background() -> None:
    light = theme.Theme(
        name="light", colours=dict(theme.DEFAULT.colours), background=7, background_rich=230
    )
    assert {bg for _, bg in theme.pairs(light, 256).values()} == {230}
    assert {bg for _, bg in theme.pairs(light, 8).values()} == {7}
    assert {bg for _, bg in theme.pairs(theme.DEFAULT, 256).values()} == {-1}


def tron_app() -> view.App:
    """A Tron-look App with its own random source, the boot screen and decoding over, and no
    title glitch; effects are at their starting level."""
    app = view.App(FakeWin(40, 160), Path("/x"), render.UNICODE, theme.THEMES["tron"])
    app.rng = random.Random(1)
    app.boot_until = app.decode_from = float("-inf")
    app.glitch_at = float("inf")
    return app


def test_effects_start_on_and_the_footer_says_so() -> None:
    app = tron_app()
    assert app.fx_level == "light"
    app.draw()
    assert "r effects: on" in app.screen.win.grid().splitlines()[-1]


def test_two_presses_of_r_turn_effects_off_and_the_title_names_the_change() -> None:
    app = tron_app()
    app.handle(ord("r"))
    app.handle(ord("r"))
    assert app.fx_level == "off"
    app.draw()
    lines = app.screen.win.grid().splitlines()
    assert "r effects: off" in lines[-1]
    assert "effects: off" in lines[0]  # the title names the change for a moment


def test_a_third_press_of_r_turns_effects_on_again() -> None:
    app = tron_app()
    app.fx_level = "off"
    app.handle(ord("r"))
    app.draw()
    assert "r effects: on" in app.screen.win.grid().splitlines()[-1]


def test_the_footer_bars_count_as_solid_for_the_effects() -> None:
    app = make_app(theme.THEMES["tron"], "network", 60, 213)
    app.draw()
    footer = app.screen.size[0] - 1
    assert all(app.screen.solid_at(footer, x) for x in range(5, 60))  # bars count as solid


def run_with(monkeypatch: pytest.MonkeyPatch, win: KeyedWin, state: Path, *args: Any) -> None:
    """`view.run` on a keyed window, with curses' terminal setup stubbed out."""
    monkeypatch.setattr(curses, "curs_set", lambda visibility: 0)
    view.run(win, state, render.UNICODE, *args)


def test_run_draws_before_each_key_and_returns_when_q_is_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    win = KeyedWin(30, 100, [-1, ord("q")])
    run_with(monkeypatch, win, tmp_path / "none.json")
    assert "NETWORK" in win.grid()
    assert win.keys == []


def test_run_follows_the_page_keys_it_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    win = KeyedWin(30, 100, [ord("\t"), ord("q")])
    run_with(monkeypatch, win, tmp_path / "none.json")
    assert "Tab memory & jobs" in win.grid()


class ConsoleWrites:
    """The bytes `view.run` writes to the console's file descriptor, in order."""

    def __init__(self) -> None:
        self.data: list[bytes] = []

    def __call__(self, fd: int, data: bytes) -> int:
        self.data.append(data)
        return len(data)


def run_on_the_console(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, palette: list[str] | None
) -> ConsoleWrites:
    """`view.run` in the Matrix look on a Linux console whose own palette is `palette`."""
    monkeypatch.setenv("TERM", "linux")
    monkeypatch.setattr(colours, "read_palette", lambda fd: palette)
    writes = ConsoleWrites()
    monkeypatch.setattr(os, "write", writes)
    win = KeyedWin(30, 100, [ord("x"), ord("q")])  # the first key ends the boot
    with (tmp_path / "stdin").open("w+") as stdin:  # App reads the console palette from stdin
        monkeypatch.setattr(sys, "stdin", stdin)
        run_with(monkeypatch, win, tmp_path / "none.json", theme.THEMES["matrix"])
    return writes


def test_run_on_the_console_puts_the_looks_palette_back_on_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    writes = run_on_the_console(monkeypatch, tmp_path, None)
    assert writes.data[0].startswith(b"\x1b]P4")
    assert writes.data[-1] == b"\x1b]R"


def test_run_on_the_console_restores_the_consoles_own_palette(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    writes = run_on_the_console(monkeypatch, tmp_path, ["000000"] * 16)
    own = colours.palette_codes(list(enumerate(["000000"] * 16))).encode()
    assert writes.data[-1] == own


def wrapper_stub(calls: list[tuple[Any, ...]], raises: type[BaseException] | None = None) -> Any:
    def wrapper(func: Any, *args: Any) -> None:
        calls.append((func, *args))
        if raises is not None:
            raise raises

    return wrapper


def unset_escape_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ESCDELAY, and whatever `view.main` sets is removed again at teardown."""
    monkeypatch.setenv("ESCDELAY", "restore-me")  # records the original, set or not
    monkeypatch.delenv("ESCDELAY")


def test_main_on_the_console_stops_blanking_and_clears_the_screen_after(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("TERM", "linux")
    unset_escape_delay(monkeypatch)
    monkeypatch.setattr(curses, "wrapper", wrapper_stub([], KeyboardInterrupt))
    assert view.main(tmp_path / "s.json", render.UNICODE) == 0
    assert capsys.readouterr().out == "\x1b[9;0]\x1b[14;0]\x1b[H\x1b[2J"


def test_main_on_a_terminal_writes_nothing_and_hands_run_the_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("TERM", "xterm")
    unset_escape_delay(monkeypatch)
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(curses, "wrapper", wrapper_stub(calls))
    state = tmp_path / "s.json"
    assert view.main(state, render.UNICODE) == 0
    assert capsys.readouterr().out == ""
    assert calls == [(view.run, state, render.UNICODE, theme.DEFAULT, 0.0, None, None)]


def test_main_sets_a_short_escape_delay_when_none_is_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TERM", "xterm")
    unset_escape_delay(monkeypatch)
    monkeypatch.setattr(curses, "wrapper", wrapper_stub([]))
    view.main(tmp_path / "s.json", render.UNICODE)
    assert os.environ["ESCDELAY"] == "25"


def test_main_keeps_an_escape_delay_that_is_already_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setenv("ESCDELAY", "99")
    monkeypatch.setattr(curses, "wrapper", wrapper_stub([]))
    view.main(tmp_path / "s.json", render.UNICODE)
    assert os.environ["ESCDELAY"] == "99"


def app_on(path: Path) -> view.App:
    """An App on a FakeWin that reads `path`, with the boot screen, decoding, glitch and
    effects off, as `make_app` leaves one."""
    app = view.App(FakeWin(40, 120), path, render.UNICODE, theme.DEFAULT, rng=random.Random(1))
    app.boot_until = app.decode_from = float("-inf")
    app.glitch_at = float("inf")
    app.fx_level = "off"
    return app


def test_the_viewer_draws_the_file_the_collector_wrote(tmp_path: Path) -> None:
    path = tmp_path / "run" / "state.json"
    built, _ = collector(out=path)
    built.write(built.tick())
    app = app_on(path)
    app.load()
    app.draw()
    assert app.load_error == ""
    assert [i["key"] for i in app.snapshot["instances"]] == [
        "i:apps/app",
        "i:apps/demo",
        "i:apps/idle",
    ]
    assert "NETWORK" in app.screen.win.grid().splitlines()[0]


def test_a_missing_state_file_names_the_file_it_waits_for() -> None:
    path = Path("/nonexistent/state.json")
    app = app_on(path)
    app.load()
    app.draw()
    assert f"waiting for {path}" in app.screen.win.grid().splitlines()[0]


def test_a_corrupt_state_file_is_reported_and_the_last_snapshot_stays(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"instances": []}')
    app = app_on(path)
    app.load()
    first = app.snapshot
    assert first == {"instances": []}
    path.write_text("{not json")
    later = path.stat().st_mtime + 10
    os.utime(path, (later, later))
    app.load()
    assert app.load_error.startswith("cannot read")
    assert app.snapshot is first


def test_an_unchanged_file_is_not_read_again(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"instances": []}')
    app = app_on(path)
    app.load()
    first = app.snapshot
    assert first == {"instances": []}
    unchanged = path.stat().st_mtime
    path.write_text('{"instances": [], "errors": ["x"]}')
    os.utime(path, (unchanged, unchanged))
    app.load()
    assert app.snapshot is first


def test_instances_seen_for_the_first_time_start_unfolded(tmp_path: Path) -> None:
    path = tmp_path / "run" / "state.json"
    built, _ = collector(out=path)
    built.write(built.tick())
    app = app_on(path)
    app.load()
    assert {"i:apps/app", "i:apps/demo"} <= machines_page(app).expanded


def test_a_look_boots_with_its_lines_typed_out_then_shows_the_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = view.App(
        FakeWin(40, 120), Path("/x"), render.UNICODE, theme.THEMES["matrix"], rng=random.Random(1)
    )
    app.glitch_at = float("inf")
    monkeypatch.setattr(time, "monotonic", lambda: 1001.5)  # 1.5 s into the 2.4 s boot
    app.draw()
    booting = app.screen.win.grid()
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0 + theme.BOOT_SECONDS + 1)
    app.draw()
    assert app.theme.boot[0] in booting
    assert "NETWORK" not in booting
    assert "NETWORK" in app.screen.win.grid()


def test_l_on_a_vm_unfolds_its_container_and_the_detail_pane_names_the_image_limits() -> None:
    app = make_app(theme.DEFAULT, "machines", 40, 120)
    app.draw()
    machines_page(app).selected = "i:apps/app"
    app.handle(ord("l"))
    app.draw()
    app.handle(ord("j"))
    app.draw()
    grid = app.screen.win.grid()
    assert "cpu limit  2 cores" in grid
    assert "mem limit  4.0G" in grid
    assert "pids       145" in grid


def test_d_toggles_the_detail_page_on_a_narrow_window() -> None:
    app = make_app(theme.DEFAULT, "machines", 30, 100)
    app.draw()
    machines_page(app).selected = "i:apps/app"
    app.handle(ord("d"))
    app.draw()
    shown = app.screen.win.grid()
    app.handle(ord("d"))
    app.draw()
    assert "NAME  (sort: name)" not in shown
    assert "NAME  (sort: name)" in app.screen.win.grid()


def test_page_down_moves_by_a_page() -> None:
    app = make_app(theme.DEFAULT, "machines", 10, 120)  # a page: 10 - 8 rows
    app.draw()
    rows = machines_page(app).rows
    app.handle(curses.KEY_NPAGE)
    assert machines_page(app).selected == rows[2].key


def test_page_down_stops_at_the_last_row() -> None:
    app = make_app(theme.DEFAULT, "machines", 10, 120)  # a page: 10 - 8 rows
    app.draw()
    rows = machines_page(app).rows
    for _ in range(3):
        app.handle(curses.KEY_NPAGE)
    assert machines_page(app).selected == rows[-1].key


def test_page_up_stops_at_the_first_row() -> None:
    app = make_app(theme.DEFAULT, "machines", 10, 120)  # a page: 10 - 8 rows
    app.draw()
    rows = machines_page(app).rows
    machines_page(app).selected = rows[-1].key
    for _ in range(3):
        app.handle(curses.KEY_PPAGE)
    assert machines_page(app).selected == rows[0].key


def test_h_on_a_container_selects_its_vm() -> None:
    app = make_app(theme.DEFAULT, "machines", 40, 120)
    machines_page(app).expanded.add("i:apps/app")
    app.draw()
    machines_page(app).selected = "i:apps/app/c:4a8290f0069f"
    app.handle(ord("h"))
    assert machines_page(app).selected == "i:apps/app"


def test_h_on_a_vm_folds_it() -> None:
    app = make_app(theme.DEFAULT, "machines", 40, 120)
    machines_page(app).expanded.add("i:apps/app")
    app.draw()
    machines_page(app).selected = "i:apps/app"
    app.handle(ord("h"))
    assert "i:apps/app" not in machines_page(app).expanded


def saved_app(tmp_path: Path, th: theme.Theme, **values: Any) -> view.App:
    """An App started with these saved settings."""
    prefs = Prefs(tmp_path / "s.json", st.Settings(), st.Settings(**values))
    return view.App(FakeWin(40, 120), Path("/nonexistent"), render.UNICODE, th, prefs=prefs)


def test_saved_settings_pick_the_first_page_and_the_effects(tmp_path: Path) -> None:
    app = saved_app(tmp_path, theme.DEFAULT, start_page="network", effects="off")

    assert (app.page, app.fx_level) == ("network", "off")


def test_boot_lines_play_unless_turned_off(tmp_path: Path) -> None:
    booting = next(t for t in LOOKS if t.boot)

    assert saved_app(tmp_path, booting).boot_until > 1000.0
    assert saved_app(tmp_path, booting, boot=False).boot_until == float("-inf")


def test_the_settings_note_shortens_the_home_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    app = saved_app(tmp_path, theme.DEFAULT)

    assert app.settings_note() == "saved in ~/s.json"
