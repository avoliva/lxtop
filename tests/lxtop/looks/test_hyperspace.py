"""The Hyperspace look's star streaks: they move outward from the centre and lengthen."""

from __future__ import annotations

import itertools
import random

from lxtop.looks import hyperspace as lh
from lxtop.looks.hyperspace import Hyperspace


def sky(seed: int = 1, h: int = 60, w: int = 213) -> Hyperspace:
    s = Hyperspace(random.Random(seed))
    s.resize(h, w)
    return s


def test_stars_move_outward_from_the_centre() -> None:
    s = sky()
    for i in range(len(s.stars)):
        us = [s.depth(i, t * 0.01) for t in range(20)]
        steps = list(itertools.pairwise(us))
        assert sum(b < a for a, b in steps) <= 1, "progress only wraps back to the centre"
        assert all(b > a for a, b in steps if b > a - 0.5), "otherwise it moves outward"


def test_dots_lie_nearer_the_centre_than_streaks() -> None:
    s = sky()

    def dist(y: int, x: int) -> float:
        return float(((x - s.cx) ** 2 + (2 * (y - s.cy)) ** 2) ** 0.5)

    dots: list[float] = []
    streaks: list[float] = []
    for step in range(30):
        for y, x, c, _ in s.frame(step * 0.1):
            (dots if c == "." else streaks).append(dist(y, x))
    assert dots and streaks
    assert sum(dots) / len(dots) < sum(streaks) / len(streaks)


def rays(s: Hyperspace) -> list[tuple[int, int, str]]:
    """(dx, dy, char) of every streak cell, not the dots, over ten frames."""
    return [
        (x - s.cx, y - s.cy, c)
        for step in range(10)
        for y, x, c, _ in s.frame(step * 0.2)
        if c != "."
    ]


def test_horizontal_streaks_are_dashes() -> None:
    chars = [c for dx, dy, c in rays(sky()) if abs(dx) > 8 and abs(dy) * 5 <= abs(dx)]
    assert chars, "streaks lie along the horizontal ray"  # 339 cells today
    assert set(chars) == {"-"}


def test_vertical_streaks_are_bars() -> None:
    chars = [c for dx, dy, c in rays(sky()) if abs(dy) > 8 and abs(dx) * 5 <= abs(dy)]
    assert chars, "streaks lie along the vertical ray"  # 30 cells today
    assert set(chars) == {"|"}


def test_sparse_at_monitor_size() -> None:
    s = sky()
    for step in range(60):
        assert len(s.frame(step * 0.1)) < 0.1 * 60 * 213


def test_tiny_and_resized_screens() -> None:
    s = Hyperspace(random.Random(2))
    for h, w in ((1, 1), (1, 40), (5, 1), (30, 80), (2, 2)):
        s.resize(h, w)
        for step in range(30):
            assert all(0 <= y < h and 0 <= x < w for y, x, _, _ in s.frame(step * 0.2))


def test_the_same_seed_gives_the_same_frames() -> None:
    a, b = sky(9), sky(9)
    assert [a.frame(t * 0.3) for t in range(20)] == [b.frame(t * 0.3) for t in range(20)]


def test_a_jump_is_rare_short_and_bounded() -> None:
    s = sky()
    levels = [lh.jump_level(t * 0.05, s.offset) for t in range(int(lh.JUMP_EVERY * 3 / 0.05))]
    assert max(levels) == 1.0 and min(levels) == 0.0
    assert sum(v > 0 for v in levels) / len(levels) < 0.06, "a jump is rare"
    assert all(0.0 <= v <= 1.0 for v in levels)
    t0 = next(t * 0.05 for t, v in enumerate(levels) if v == 1.0)
    cruise = t0 + lh.JUMP_LENGTH + 0.5
    assert lh.jump_level(cruise, s.offset) == 0.0, "snaps back"
    during = len(s.frame(t0))
    assert during > len(s.frame(cruise)), "streaks are longer in the jump"
    assert during < 0.1 * 60 * 213, "and still sparse"


def test_near_stars_are_faster_and_longer() -> None:
    s = sky()
    rates: dict[int, list[float]] = {0: [], 1: [], 2: []}
    for i, (_, rate, _) in enumerate(s.stars):
        rates[s.layer[i]].append(rate)
    assert all(rates.values())
    mean = {k: sum(v) / len(v) for k, v in rates.items()}
    assert mean[0] < mean[1] < mean[2]
