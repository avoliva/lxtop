from __future__ import annotations

import curses
import time
from pathlib import Path

import pytest

from tests.support.snapshot import NOW


@pytest.fixture(autouse=True)
def own_settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test's viewer saves its settings under its own tmp_path, never in the
    real ~/.config."""
    path = tmp_path / "lxtop-settings.json"
    monkeypatch.setenv("LXTOP_SETTINGS", str(path))
    return path


@pytest.fixture
def headless(monkeypatch: pytest.MonkeyPatch) -> None:
    """No terminal and a fixed clock, so a draw is the same on every machine."""
    real_strftime, real_gmtime = time.strftime, time.gmtime
    monkeypatch.setattr(curses, "has_colors", lambda: False)
    monkeypatch.setattr(time, "time", lambda: NOW)
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(time, "localtime", lambda s=None: real_gmtime(NOW if s is None else s))
    monkeypatch.setattr(
        time, "strftime", lambda fmt, t=None: real_strftime(fmt, t or real_gmtime(NOW))
    )
