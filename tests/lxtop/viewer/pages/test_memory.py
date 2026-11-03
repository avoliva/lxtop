"""The memory & jobs page: what it draws from the `memory` record, and that a missing
record never breaks it."""

from __future__ import annotations

from typing import Any

import pytest

from lxtop.looks import theme
from lxtop.viewer import app as view
from tests.support.curses_win import make_app
from tests.support.host_state import NOW, kill, memory_record

pytestmark = pytest.mark.usefixtures("headless")


def shown(record: dict[str, Any] | None, h: int = 40, w: int = 140) -> str:
    app: view.App = make_app(theme.DEFAULT, "memory", h, w)
    if record is None:
        app.snapshot.pop("memory", None)
    else:
        app.snapshot["memory"] = record
    app.draw()
    grid: str = app.screen.win.grid()
    return grid


def test_it_shows_room_vms_jobs_gpu_and_kills(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lxtop.viewer.pages.memory.time.time", lambda: NOW)
    grid = shown(memory_record(oom={"kills": [kill(NOW - 3600)]}))
    assert "MEMORY & JOBS" in grid and "Room for a job now:" in grid
    assert "before the user's jobs are slowed at 40.0 GB (never killed)" in grid
    assert "The host ran out of memory 1 h ago and killed stats (49.0 GB)." in grid
    assert "admin  14.0 GB in use, never killed, slowed past 40.0 GB" in grid
    assert "ci" in grid and "host pays" in grid
    assert "stats-kaggle-build4" in grid and "python3 search.py" in grid
    assert "ollama" in grid and "llm" in grid
    assert "over the whole host" in grid


def test_no_kills_and_no_gpu_users_are_said() -> None:
    grid = shown(memory_record(gpu_apps=[]))
    assert "nothing holds GPU memory" in grid and "OUT-OF-MEMORY KILLS" in grid


@pytest.mark.parametrize("bad", [None, {}, {"meminfo": "x", "vms": [1], "user": {"jobs": "y"}}])
def test_a_missing_or_broken_record_is_said_not_crashed(bad: Any) -> None:
    grid = shown(bad)
    assert "Memory: not read yet." in grid


@pytest.mark.parametrize(("h", "w"), [(24, 80), (60, 213)])
def test_it_draws_at_every_size(h: int, w: int) -> None:
    assert "Room for a job now" in shown(memory_record(), h, w)
