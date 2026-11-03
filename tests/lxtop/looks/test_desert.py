"""The Desert look's blowing sand and its rare ripple."""

from __future__ import annotations

import random

from lxtop.looks.desert import GUST_SECONDS, RIPPLE_CROSSING, RIPPLE_EVERY, Sand


def dunes(seed: int = 1, h: int = 60, w: int = 213) -> Sand:
    s = Sand(random.Random(seed))
    s.resize(h, w)
    return s


def test_grains_move_left_to_right() -> None:
    s = dunes()
    s.frame(0.0)
    before = [g[1] for g in s.grains]
    s.frame(0.5)
    moved = [(b - a) % s.w for a, b in zip(before, (g[1] for g in s.grains), strict=False)]
    assert all(0 <= m < s.w / 2 for m in moved)
    assert sum(moved) > 0


def test_density_rises_and_falls_over_about_ten_seconds() -> None:
    s = dunes()
    values = [s.density(t * GUST_SECONDS / 20) for t in range(21)]
    assert max(values) > 0.9 and min(values) < 0.2
    assert abs(values[0] - values[20]) < 1e-9, "one swell per gust period"
    lit = [len(s.frame(t * 0.25)) for t in range(80)]
    assert max(lit) - min(lit) > 100, "gusts thicken the grains over steady dunes"


def test_the_ripple_is_a_long_bounded_bulge_crossing_left_to_right() -> None:
    s = dunes()
    start = -s.ripple_offset % RIPPLE_EVERY
    assert s.ripple(start + 1.0), "it is on screen early in the crossing"
    assert not s.ripple(start + RIPPLE_CROSSING + 1.0)
    assert not s.ripple(start + RIPPLE_EVERY - 1.0)
    assert s.ripple(start + RIPPLE_EVERY + 1.0)
    early = max(x for _, x, _, _ in s.ripple(start + 5.0))
    later = max(x for _, x, _, _ in s.ripple(start + 12.0))
    assert later > early
    mid = s.ripple(start + 10.0)
    assert len(mid) <= 2 * 90
    assert len({x for _, x, _, _ in mid}) >= 40, "long"
    assert len({y for y, _, _, _ in mid}) >= 3, "it bulges"
    assert {c for _, _, c, _ in mid} <= {"\u2248", "~", "-"}


def test_dunes_hug_the_bottom_and_creep_with_the_wind() -> None:
    s = dunes()
    cells = s.dunes()
    assert cells and all(y >= s.h - 3 for y, _, _, _ in cells)
    before = [s.dune_height(x) for x in range(s.w)]
    for step in range(100):
        s.frame(step * 0.5)
    assert [s.dune_height(x) for x in range(s.w)] != before
    assert s.drift > 0
    assert any(s.dune_height(x) != s.dune_height(x + 1) for x in range(s.w - 1)), "not flat"


def test_sparse_at_monitor_size() -> None:
    s = dunes()
    for step in range(100):
        assert len(s.frame(step * 0.2)) < 0.1 * 60 * 213


def test_tiny_and_resized_screens() -> None:
    s = Sand(random.Random(2))
    for h, w in ((1, 1), (1, 40), (5, 1), (30, 80), (2, 2)):
        s.resize(h, w)
        for step in range(40):
            assert all(0 <= y < h and 0 <= x < w for y, x, _, _ in s.frame(step * 0.5))


def test_the_same_seed_gives_the_same_frames() -> None:
    a, b = dunes(9), dunes(9)
    assert [a.frame(t * 0.3) for t in range(20)] == [b.frame(t * 0.3) for t in range(20)]
