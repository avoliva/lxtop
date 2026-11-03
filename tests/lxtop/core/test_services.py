"""What the timers & services page says: how each timer's run ended, failed units from
everywhere, and which applies need a second look."""

from __future__ import annotations

import pytest

from lxtop.core import services as svc
from tests.support.host_state import timer


@pytest.mark.parametrize(
    ("made", "state", "level"),
    [
        (timer("a.timer"), "ok", svc.GOOD),
        (timer("a.timer", result="exit-code", status=2), "exit-code, exit 2", svc.PROBLEM),
        (timer("a.timer", result="timeout", status=0), "timeout", svc.PROBLEM),
        (timer("a.timer", active="activating", sub="start"), "running", svc.ATTENTION),
        (timer("a.timer", result="", last=None), "never ran", svc.QUIET),
    ],
)
def test_a_timer_says_how_its_last_run_ended(
    made: dict[str, object], state: str, level: int
) -> None:
    assert svc.timer_state(made) == (state, level)
