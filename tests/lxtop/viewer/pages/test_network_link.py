"""The network page's internet half: the helpers it reads numbers with, and its sections drawn
on their own."""

from __future__ import annotations

import pytest

from lxtop.core.network import LOST, SKIPPED
from lxtop.viewer.pages import network_link

pytestmark = pytest.mark.usefixtures("headless")


@pytest.mark.parametrize(
    ("dbm", "word"), [(-40, "strong"), (-60, "good"), (-70, "weak"), (-90, "very weak")]
)
def test_signal_word_names_each_band(dbm: float, word: str) -> None:
    assert network_link.signal_word(dbm) == word


def test_speed_top_of_nothing_is_the_floor() -> None:
    assert network_link.speed_top([], 1e6) > 0
    assert network_link.speed_top([0.0], 1e6) > 0


def test_filled_holds_the_last_answer_through_skipped_ticks_and_keeps_losses() -> None:
    values = [10.0, SKIPPED, SKIPPED, LOST, SKIPPED, 12.0]

    assert network_link.filled(values) == [10.0, 10.0, 10.0, LOST, LOST, 12.0]


def test_check_result_prefers_the_pinger_then_the_api_check_then_the_named_check() -> None:
    snap = {
        "pings": {"internet": {"ms": 9}},
        "checks": {"api_service": {"ms": 200}, "dns": {"ms": 30}},
    }

    assert network_link.check_result(snap, "internet") == {"ms": 9}
    assert network_link.check_result(snap, "service") == {"ms": 200}
    assert network_link.check_result(snap, "dns") == {"ms": 30}
    assert network_link.check_result({}, "dns") == {}
