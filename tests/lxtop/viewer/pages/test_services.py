"""The timers & services page: timers, failed units with their logs, applies."""

from __future__ import annotations

from typing import Any

import pytest

from lxtop.looks import theme
from lxtop.viewer import app as view
from tests.support.curses_win import make_app

pytestmark = pytest.mark.usefixtures("headless")


def shown(units: Any, applies: Any, ci: Any = None, h: int = 40, w: int = 140) -> str:
    app: view.App = make_app(theme.DEFAULT, "services", h, w)
    app.snapshot["units"] = units
    app.snapshot["applies"] = applies
    app.snapshot["ci"] = ci or {}
    app.draw()
    grid: str = app.screen.win.grid()
    return grid
