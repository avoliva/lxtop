"""lxtop's command line (`python -m lxtop collect|view|probe`): how options reach the
collector, the probe and the viewer. Everything the commands start is replaced, so no sampler,
curses screen or font tool runs."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from lxtop import __main__ as entry
from lxtop.collector import collector as collect
from lxtop.collector import probe
from lxtop.core import render
from lxtop.looks import theme
from lxtop.viewer import app as view
from lxtop.viewer import font
from lxtop.viewer import prefs as pr
from tests.support.snapshot import full_snapshot


class CollectorCalls:
    def __init__(self) -> None:
        self.made: list[collect.Settings] = []
        self.ran: list[bool] = []


class ViewerCalls:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, render.Glyphs, theme.Theme, float]] = []
        self.extra: list[dict[str, object]] = []


@pytest.fixture
def collector(monkeypatch: pytest.MonkeyPatch) -> CollectorCalls:
    calls = CollectorCalls()

    class RecordingCollector:
        def __init__(self, settings: collect.Settings) -> None:
            calls.made.append(settings)

        def run(self, once: bool = False) -> None:
            calls.ran.append(once)

    monkeypatch.setattr(collect, "Collector", RecordingCollector)
    monkeypatch.setattr(collect, "default_lxc", lambda sudo=False: f"lxc(sudo={sudo})")
    return calls


@pytest.fixture
def viewer(monkeypatch: pytest.MonkeyPatch) -> ViewerCalls:
    calls = ViewerCalls()

    def fake_main(
        state: Path,
        glyphs: render.Glyphs,
        look: theme.Theme = theme.DEFAULT,
        cycle: float = 0.0,
        **extra: object,
    ) -> int:
        calls.calls.append((state, glyphs, look, cycle))
        calls.extra.append(extra)
        return 0

    monkeypatch.setattr(view, "main", fake_main)
    monkeypatch.setenv("TERM", "xterm")
    return calls


def test_collect_builds_settings_from_its_options_and_runs_once(
    collector: CollectorCalls, tmp_path: Path
) -> None:
    argv = ["collect", "--out", str(tmp_path / "s.json"), "--history", "90"]
    argv += ["--lxd-socket", "/run/lxd.sock", "--sudo", "--once"]

    assert entry.main(argv) == 0

    (settings,) = collector.made
    assert settings.out == tmp_path / "s.json"
    assert settings.history_seconds == 90.0
    assert settings.lxd_socket == "/run/lxd.sock"
    assert settings.sudo is True
    assert settings.lxc == "lxc(sudo=True)"
    assert collector.ran == [True]


def test_collect_raises_a_sub_half_second_interval_to_half_a_second(
    collector: CollectorCalls,
) -> None:
    entry.main(["collect", "--interval", "0.1"])

    assert collector.made[0].interval == 0.5


def test_collect_no_instances_and_no_checks_turn_those_off(collector: CollectorCalls) -> None:
    entry.main(["collect", "--no-instances", "--no-checks"])

    assert collector.made[0].probe_instances is False
    assert collector.made[0].checks is False


def test_probe_passes_its_interval_to_the_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_main(argv: list[str]) -> int:
        seen.append(argv)
        return 7

    monkeypatch.setattr(probe, "main", fake_main)

    assert entry.main(["probe", "--interval", "5"]) == 7
    assert seen == [["--interval", "5"]]


def test_view_is_the_default_command_and_passes_state_look_and_cycle(viewer: ViewerCalls) -> None:
    assert entry.main([]) == 0

    assert viewer.calls == [(Path(entry.STATE), render.UNICODE, theme.THEMES["default"], 300.0)]


def test_view_options_reach_the_viewer(viewer: ViewerCalls, tmp_path: Path) -> None:
    argv = ["view", "--state", str(tmp_path / "x.json"), "--glyphs", "console"]
    argv += ["--theme", "matrix", "--cycle", "0"]

    assert entry.main(argv) == 0

    assert viewer.calls == [(tmp_path / "x.json", render.CONSOLE, theme.THEMES["matrix"], 0.0)]


def test_list_themes_prints_every_look_and_returns_zero(
    viewer: ViewerCalls, capsys: pytest.CaptureFixture[str]
) -> None:
    assert entry.main(["view", "--list-themes"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == len(theme.THEMES)
    assert lines[0] == f"{'default':<12} {theme.THEMES['default'].label}"
    assert viewer.calls == []


def test_an_unknown_look_exits_with_the_look_names(
    viewer: ViewerCalls, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stop:
        entry.main(["view", "--theme", "nope"])

    assert stop.value.code == 2
    err = capsys.readouterr().err
    assert "no look called 'nope'" in err
    assert "matrix" in err
    assert viewer.calls == []


def test_a_negative_cycle_exits_with_an_error(
    viewer: ViewerCalls, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stop:
        entry.main(["view", "--cycle", "-1"])

    assert stop.value.code == 2
    assert "--cycle: expected 0 (off) or more seconds" in capsys.readouterr().err
    assert viewer.calls == []


def test_font_option_opens_the_font_around_the_viewer(
    viewer: ViewerCalls, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TERM", "linux")
    opened: list[Path] = []

    console = object()

    @contextlib.contextmanager
    def fake_open(base: Path) -> Iterator[object]:
        opened.append(base)
        yield console

    monkeypatch.setattr(font, "console_font", fake_open)

    assert entry.main(["view", "--font", "/f.psf"]) == 0

    assert opened == [Path("/f.psf")]
    assert viewer.calls[0][1] == render.CONSOLE_BLOCKS
    assert viewer.extra[0]["font"] is console


def saved_prefs(path: Path, data: dict[str, object]) -> Path:
    path.write_text(json.dumps(data))
    return path


def test_the_saved_look_and_cycle_start_the_viewer(viewer: ViewerCalls, tmp_path: Path) -> None:
    file = saved_prefs(tmp_path / "s.json", {"look": "matrix", "cycle_seconds": 0})

    assert entry.main(["view", "--settings", str(file)]) == 0

    assert viewer.calls[0][2:] == (theme.THEMES["matrix"], 0.0)
    prefs = viewer.extra[0]["prefs"]
    assert isinstance(prefs, pr.Prefs)
    assert prefs.path == file
    assert prefs.settings.effects == "light"


def test_theme_and_cycle_options_beat_the_saved_settings_for_one_run(
    viewer: ViewerCalls, tmp_path: Path
) -> None:
    file = saved_prefs(tmp_path / "s.json", {"look": "matrix", "cycle_seconds": 0})

    entry.main(["view", "--settings", str(file), "--theme", "tron", "--cycle", "60"])

    assert viewer.calls[0][2:] == (theme.THEMES["tron"], 60.0)
    prefs = viewer.extra[0]["prefs"]
    assert isinstance(prefs, pr.Prefs)
    assert prefs.settings.look == "matrix"  # what is saved is unchanged


def test_default_cycle_is_used_until_a_cycle_is_saved(viewer: ViewerCalls, tmp_path: Path) -> None:
    entry.main(["view", "--settings", str(tmp_path / "none.json"), "--default-cycle", "90"])

    assert viewer.calls[0][3] == 90.0
    prefs = viewer.extra[0]["prefs"]
    assert isinstance(prefs, pr.Prefs)
    assert prefs.defaults.cycle_seconds == 90.0


def test_the_settings_file_defaults_to_the_environments_choice(
    viewer: ViewerCalls, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LXTOP_SETTINGS", str(tmp_path / "env.json"))

    entry.main(["view"])

    prefs = viewer.extra[0]["prefs"]
    assert isinstance(prefs, pr.Prefs)
    assert prefs.path == tmp_path / "env.json"


PTY_WAIT = 20.0  # seconds a step may take before the test fails; a green run needs well under one


def _pty_drain(master: int, seen: bytearray, seconds: float) -> None:
    """Copy what the child wrote into `seen`, waiting at most `seconds` for more."""
    ready, _, _ = select.select([master], [], [], seconds)
    if ready:
        with contextlib.suppress(OSError):  # Linux: EIO once the child has closed its end
            seen.extend(os.read(master, 65536))


def test_view_draws_a_frame_and_q_ends_it_with_status_zero(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    state.write_text(json.dumps(full_snapshot()))
    master, slave = pty.openpty()
    child: subprocess.Popen[bytes] | None = None
    seen = bytearray()
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
        env = {**os.environ, "TERM": "xterm-256color"}
        child = subprocess.Popen(
            [sys.executable, "-m", "lxtop", "view", "--state", str(state), "--cycle", "0"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=env,
            start_new_session=True,
        )
        os.close(slave)
        slave = -1
        deadline = time.monotonic() + PTY_WAIT
        # The page title is drawn only by a real frame (a traceback would not contain it).
        while b" NETWORK " not in seen and time.monotonic() < deadline:
            _pty_drain(master, seen, 0.1)
        assert b" NETWORK " in seen, bytes(seen[-300:])

        os.write(master, b"q")
        while child.poll() is None and time.monotonic() < deadline:
            _pty_drain(master, seen, 0.1)
        assert child.returncode == 0
    finally:
        if child is not None:
            child.kill()
            child.wait()
        if slave >= 0:
            os.close(slave)
        os.close(master)


def test_settings_changed_in_the_running_viewer_are_saved(tmp_path: Path) -> None:
    """o opens the menu, l steps the look, q closes the menu, q quits: the file holds it."""
    state = tmp_path / "state.json"
    state.write_text(json.dumps(full_snapshot()))
    file = tmp_path / "settings.json"
    master, slave = pty.openpty()
    child: subprocess.Popen[bytes] | None = None
    seen = bytearray()
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
        env = {**os.environ, "TERM": "xterm-256color"}
        argv = [sys.executable, "-m", "lxtop", "view", "--state", str(state)]
        child = subprocess.Popen(
            [*argv, "--settings", str(file), "--cycle", "0"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=env,
            start_new_session=True,
        )
        os.close(slave)
        slave = -1
        deadline = time.monotonic() + PTY_WAIT
        for key, wait_for in ((b"", b" NETWORK "), (b"o", b"Reset to defaults")):
            if key:
                os.write(master, key)
            while wait_for not in seen and time.monotonic() < deadline:
                _pty_drain(master, seen, 0.1)
            assert wait_for in seen, bytes(seen[-300:])
        os.write(master, b"l")
        while not file.exists() and time.monotonic() < deadline:
            _pty_drain(master, seen, 0.1)
        os.write(master, b"qq")
        while child.poll() is None and time.monotonic() < deadline:
            _pty_drain(master, seen, 0.1)
        assert child.returncode == 0
        assert json.loads(file.read_text())["look"] == theme.next_theme(theme.DEFAULT).name
    finally:
        if child is not None:
            child.kill()
            child.wait()
        if slave >= 0:
            os.close(slave)
        os.close(master)


def test_collect_shows_the_user_who_ran_sudo_unless_told_otherwise(
    collector: CollectorCalls, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUDO_USER", "ops")
    assert entry.main(["collect", "--once"]) == 0
    assert entry.main(["collect", "--once", "--user", "deploy"]) == 0
    assert [s.user for s in collector.made] == ["ops", "deploy"]
