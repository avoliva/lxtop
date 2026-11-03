"""The sonar look: a rotating sweep with a fading wake, and rising bubbles."""

from __future__ import annotations

import math
import random

import pytest

from lxtop.looks.sonar import (
    EVENT_PERIOD,
    EVENT_SECONDS,
    THEME,
    TURN_SECONDS,
    Sweep,
    afterglow,
)
from lxtop.looks.theme import FX_DIM, FX_HEAD, FX_MID


def sweep(h: int = 60, w: int = 213, seed: int = 1) -> Sweep:
    backdrop = Sweep(False, random.Random(seed))
    backdrop.resize(h, w)
    return backdrop


def head(backdrop: Sweep, now: float) -> list[tuple[int, int]]:
    return [(y, x) for y, x, c, tone in backdrop.frame(now) if tone == FX_HEAD and c in "|-/\\\\"]


def test_the_sweep_line_runs_from_the_centre_and_turns_clockwise() -> None:
    backdrop = sweep()
    cy, cx = 30, 106
    east = head(backdrop, 0.0)
    assert east and all(y == cy and x > cx for y, x in east)
    south = head(backdrop, TURN_SECONDS / 4)
    assert (
        south and all(x == cx and y >= cy for y, x in south) and max(y for y, _ in south) > cy + 10
    )
    west = head(backdrop, TURN_SECONDS / 2)
    assert west and all(y == cy and x < cx for y, x in west)
    assert math.isclose(backdrop.angle(TURN_SECONDS), backdrop.angle(0.0), abs_tol=1e-9)


def test_the_wake_fades_behind_the_sweep() -> None:
    backdrop = sweep()
    cells = backdrop.frame(TURN_SECONDS / 4)  # pointing down; the wake is to the east
    tones = {tone for y, x, _, tone in cells if x > 106 and y > 30}
    assert {FX_MID, FX_DIM} <= tones


def test_bubbles_rise() -> None:
    backdrop = sweep(h=40, w=100)
    backdrop.bubbles = backdrop.bubbles[:1]

    def bubbles(now: float) -> list[int]:
        return sorted(y for y, _ in backdrop.bubble_cells(now))

    before, after = bubbles(0.2), bubbles(1.2)
    assert before and len(before) == len(after)
    assert sum(after) < sum(before), "rows get smaller: they go up"


def test_the_sweep_is_sparse() -> None:
    backdrop = sweep()
    for step in range(60):
        assert len(backdrop.frame(step * 0.07)) < 0.1 * 60 * 213


@pytest.mark.parametrize("size", [(1, 1), (1, 30), (30, 1), (3, 5)])
def test_tiny_screens_and_resizes_stay_inside(size: tuple[int, int]) -> None:
    backdrop = sweep(*size)
    for h, w in (size, (30, 80), (1, 1), (60, 213)):
        backdrop.resize(h, w)
        for step in range(40):
            assert all(0 <= y < h and 0 <= x < w for y, x, _, _ in backdrop.frame(step * 0.1))


def test_the_same_seed_gives_the_same_frames() -> None:
    a, b = sweep(seed=2), sweep(seed=2)
    assert all(a.frame(t * 0.1) == b.frame(t * 0.1) for t in range(40))


def test_the_look_has_a_sweep_backdrop() -> None:
    assert THEME.name == "sonar" and THEME.backdrop is not None


def test_afterglow_fades_with_the_time_since_the_sweep() -> None:
    tones = [afterglow(a) for a in (0.0, 0.2, 0.5, 0.9)]
    assert [t[1] if t else None for t in tones] == [FX_HEAD, FX_MID, FX_DIM, None]


def test_a_contact_lights_when_swept_then_fades_until_the_next_pass() -> None:
    backdrop = sweep(h=40, w=100)
    cy, cx = 20, 50
    backdrop.contacts = [(cx + 20.0, float(cy), 0.0, 0.0)]  # due east, not moving
    backdrop.rings = []
    backdrop.bubbles = []

    def glow(now: float) -> int | None:
        for y, x, c, tone in backdrop.frame(now):
            if (y, x) == (cy, cx + 20) and c in "*+:":
                return tone
        return None

    # The sweep points east at t=0; just after, the contact is bright, later dimmer, then gone.
    assert glow(TURN_SECONDS * 0.01) == FX_HEAD
    assert glow(TURN_SECONDS * 0.2) == FX_MID
    assert glow(TURN_SECONDS * 0.5) == FX_DIM
    assert glow(TURN_SECONDS * 0.9) is None
    assert glow(TURN_SECONDS * 1.01) == FX_HEAD


def test_range_rings_are_faint_and_flare_with_the_sweep() -> None:
    backdrop = sweep()
    assert backdrop.rings
    cells = {(y, x): tone for y, x, c, tone in backdrop.frame(0.0) if c == "·"}
    assert set(cells.values()) <= {FX_DIM, FX_MID} and FX_DIM in cells.values()


def test_the_large_contact_crosses_rarely_and_stays_on_screen() -> None:
    backdrop = sweep(h=40, w=100)
    backdrop.offset = 0.0
    seen: list[float] = []
    for step in range(int(EVENT_PERIOD * 2 * 4)):
        now = step * 0.25
        cells = backdrop.large(now, backdrop.angle(now))
        assert all(0 <= y < 40 and 0 <= x < 100 for y, x in cells)
        if cells:
            seen.append(now)
    assert seen, "it comes"
    assert max(seen) - min(seen) < EVENT_PERIOD + EVENT_SECONDS
    # Not there most of the time: rare.
    assert len(seen) * 0.25 < 0.5 * EVENT_PERIOD * 2
    assert len(backdrop.large(EVENT_SECONDS / 2, 0.0)) < 60  # a small shape, bounded


def test_the_large_contact_moves_and_reverses_between_crossings() -> None:
    backdrop = sweep(h=40, w=100)
    backdrop.offset = 0.0

    def xs(now: float) -> float:
        cells = backdrop.large(now, 0.0)
        return sum(x for _, x in cells) / len(cells)

    assert xs(EVENT_SECONDS * 0.6) > xs(EVENT_SECONDS * 0.4)  # first crossing: rightwards
    later = EVENT_PERIOD
    assert xs(later + EVENT_SECONDS * 0.6) < xs(later + EVENT_SECONDS * 0.4)  # then leftwards


def test_sparse_with_every_effect_running() -> None:
    backdrop = sweep()
    backdrop.offset = 0.0
    most = max(len(backdrop.frame(t * 0.2 + 10)) for t in range(60))
    assert most < 0.1 * 60 * 213
