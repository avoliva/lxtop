"""core.settings: reading a saved file over the defaults, what gets saved, and stepping the
menu's choices."""

from __future__ import annotations

import pytest

from lxtop.core import settings as st

LOOKS = ("default", "matrix", "tron")
PAGES = ("services", "network", "machines")


def test_valid_saved_values_replace_the_defaults() -> None:
    saved = {"look": "tron", "cycle_seconds": 60, "effects": "off", "start_page": "network"}
    saved["boot"] = False

    got = st.merge(st.Settings(), saved, LOOKS, PAGES)

    assert got == st.Settings("tron", 60.0, "off", "network", False)


@pytest.mark.parametrize(
    "saved",
    [
        {"look": "gone"},
        {"look": 3},
        {"cycle_seconds": -1},
        {"cycle_seconds": True},
        {"cycle_seconds": "60"},
        {"cycle_seconds": st.MAX_CYCLE + 1},
        {"effects": "loud"},
        {"start_page": "nowhere"},
        {"boot": "yes"},
        {"unknown": 1},
    ],
)
def test_a_bad_or_unknown_value_is_ignored(saved: dict[str, object]) -> None:
    assert st.merge(st.Settings(), saved, LOOKS, PAGES) == st.Settings()


def test_only_what_differs_from_the_defaults_is_saved() -> None:
    base = st.Settings(cycle_seconds=90.0)

    assert st.diff(base, base) == {"version": st.VERSION}
    assert st.diff(base, st.Settings(look="tron", cycle_seconds=90.0)) == {
        "version": st.VERSION,
        "look": "tron",
    }


def test_step_goes_round_and_starts_over_from_an_unknown_value() -> None:
    assert st.step(PAGES, "machines", 1) == "services"
    assert st.step(PAGES, "services", -1) == "machines"
    assert st.step(PAGES, "gone", 1) == "services"


def test_step_cycle_moves_through_the_choices_and_from_between_them() -> None:
    assert st.step_cycle(300.0, 1) == 600.0
    assert st.step_cycle(0.0, -1) == st.CYCLE_CHOICES[-1]
    assert st.step_cycle(st.CYCLE_CHOICES[-1], 1) == 0.0
    assert st.step_cycle(45.0, 1) == 60.0
    assert st.step_cycle(45.0, -1) == 0.0
    assert st.step_cycle(9999.0, 1) == 0.0


@pytest.mark.parametrize(
    ("seconds", "label"),
    [(0, "off"), (45, "45 s"), (90, "90 s"), (300, "5 min"), (5400, "90 min"), (3600, "1 h")],
)
def test_cycle_label(seconds: float, label: str) -> None:
    assert st.cycle_label(seconds) == label
