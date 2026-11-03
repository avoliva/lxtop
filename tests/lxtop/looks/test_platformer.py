"""The platformer look: clouds, pipes on a brick floor, coins, a jumping hero, a question
block."""

from __future__ import annotations

import random

import pytest

from lxtop.looks import platformer as look_platformer
from lxtop.looks.platformer import Level
from lxtop.looks.theme import FX_DIM, FX_HEAD, FX_MID, Cell


def test_the_hero_runs_right_and_jumps_each_pipe() -> None:
    s = scene(1)
    floor = s.h - 2 - look_platformer.LIFT
    seen: dict[int, int] = {}
    for i in range(int(s.w / look_platformer.RUN * 10)):
        y, x = s.hero(i * 0.1)
        seen[x] = min(seen.get(x, floor), y)
    assert len(seen) > s.w * 0.8, "the hero crosses the screen"
    for pipe in s.pipes():
        assert seen.get(pipe, floor) < floor - 1, "over the pipe, not through it"
    assert any(y == floor for y in seen.values()), "and back on the floor between pipes"


def test_the_floor_and_pipes_stand_at_the_bottom() -> None:
    s = scene(1)
    cells = {(y, x): c for y, x, c, _ in s.frame(0.0)}
    floor = s.h - 1 - look_platformer.LIFT
    assert cells[(floor, 0)] == "▄"
    for pipe in s.pipes():
        assert cells[(floor - 1, pipe)] == "║" and cells[(floor - 2, pipe)] == "╔"


def test_the_question_block_appears_and_pops_coins_when_the_hero_passes() -> None:
    s = scene(3)
    blocks = pops = 0
    for cells in frames(s, 300):
        chars = [c for _, _, c, _ in cells]
        blocks += "?" in chars
        pops += chars.count("¤") >= 2
    assert blocks and pops


SIZES = [(1, 1), (1, 40), (40, 1), (3, 5), (24, 80), (60, 213)]


def scene(seed: int, h: int = 24, w: int = 80) -> Level:
    s = look_platformer.make(False, random.Random(seed))
    s.resize(h, w)
    return s


def frames(s: Level, seconds: float, tick: float = 0.1, start: float = 0.0) -> list[list[Cell]]:
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
    s = look_platformer.make(False, random.Random(2))
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
    assert look_platformer.THEME.name == "platformer"
    assert look_platformer.THEME.backdrop is look_platformer.make
