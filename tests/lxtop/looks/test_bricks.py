"""The bricks look: a wall of bricks, a bouncing ball, a following paddle and the multiball."""

from __future__ import annotations

import random

import pytest

from lxtop.looks import bricks as look_bricks
from lxtop.looks.bricks import Breakout
from lxtop.looks.theme import FX_DIM, FX_HEAD, FX_MID, Cell


def test_the_ball_knocks_bricks_out_and_stays_in_play() -> None:
    s = scene(1)
    start = len(s.bricks)
    for f in frames(s, 60):
        balls = [(y, x) for y, x, c, _ in f if c == "●"]
        paddle = s.h - look_bricks.GROUND
        assert balls and all(y < paddle for y, _ in balls), "never lost past the paddle"
    assert start and len(s.bricks) < start


def test_the_paddle_follows_the_ball() -> None:
    s = scene(1)
    f = frames(s, 20)[-1]
    paddle = [x for y, x, c, _ in f if c == "▀" and y == s.h - look_bricks.GROUND]
    assert len(paddle) == look_bricks.PADDLE
    assert abs(sum(paddle) / len(paddle) - s.balls[0].x) < 12


def test_a_cleared_wall_is_built_again() -> None:
    s = scene(1)
    s.bricks = {next(iter(s.bricks))}
    s.bricks.clear()
    s.frame(0.0)
    assert s.bricks


def test_multiball_comes_and_goes() -> None:
    s = scene(2)
    counts = []
    for i in range(3000):
        s.frame(i * 0.1)
        counts.append(len(s.balls))
    assert 3 in counts and counts[-1] in (1, 3)
    assert counts.count(3) < len(counts) * 0.5


SIZES = [(1, 1), (1, 40), (40, 1), (3, 5), (24, 80), (60, 213)]


def scene(seed: int, h: int = 24, w: int = 80) -> Breakout:
    s = look_bricks.make(False, random.Random(seed))
    s.resize(h, w)
    return s


def frames(s: Breakout, seconds: float, tick: float = 0.1, start: float = 0.0) -> list[list[Cell]]:
    return [s.frame(start + i * tick) for i in range(int(seconds / tick))]


def test_it_is_sparse_at_monitor_size() -> None:
    worst = max(len(f) for f in frames(scene(9, 60, 213), 120))
    assert 0 < worst < 60 * 213 * 0.10


@pytest.mark.parametrize("size", SIZES)
def test_any_size_stays_on_screen_and_uses_effect_tones(size: tuple[int, int]) -> None:
    h, w = size
    for cells in frames(scene(2, h, w), 90):
        assert all(0 <= y < h and 0 <= x < w for y, x, _, _ in cells)
        assert all(len(c) == 1 and tone in (FX_DIM, FX_MID, FX_HEAD) for _, _, c, tone in cells)
        assert len({(y, x) for y, x, _, _ in cells}) == len(cells)


def test_resize_midway_and_to_nothing_are_safe() -> None:
    s = look_bricks.make(False, random.Random(2))
    for i, (h, w) in enumerate([(30, 100), (1, 1), (0, 0), (5, 200), (60, 213), (2, 3)]):
        s.resize(h, w)
        for cells in frames(s, 4, start=i * 10):
            assert all(0 <= y < h and 0 <= x < w for y, x, _, _ in cells)


def test_a_late_start_is_safe() -> None:
    """lxtop passes the monotonic clock, which can be days in."""
    cells = frames(scene(3), 5, start=500_000.0)
    assert all(cells)


def test_the_same_seed_gives_the_same_frames() -> None:
    def run(seed: int) -> list[list[Cell]]:
        return [sorted(f) for f in frames(scene(seed), 90)]

    assert run(4) == run(4)
    assert run(4) != run(5)


def test_the_theme_exports_a_factory() -> None:
    assert look_bricks.THEME.name == "bricks"
    assert look_bricks.THEME.backdrop is look_bricks.make
