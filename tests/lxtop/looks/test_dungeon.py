"""The dungeon look: flickering torches, floor stones, bats, a wandering adventurer and a chest."""

from __future__ import annotations

import itertools
import random

import pytest

from lxtop.looks import dungeon as look_dungeon
from lxtop.looks.dungeon import Dungeon
from lxtop.looks.theme import FX_DIM, FX_HEAD, FX_MID, Cell


def test_torches_flicker_where_they_hang() -> None:
    s = scene(1)
    flames = [{(y, x): c for y, x, c, _ in s.frame(i * 0.1)} for i in range(20)]
    for spot in s.torches():
        assert len({f[spot] for f in flames}) > 1


def test_the_adventurer_wanders_one_step_at_a_time() -> None:
    s = scene(1)
    spots = []
    for i in range(300):
        s.frame(i * 0.1)
        spots.append(s.hero)
    steps = [(a, b) for a, b in itertools.pairwise(spots) if a != b]
    assert len(set(spots)) > 5
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in steps)


def test_bats_flap() -> None:
    chars = {c for f in frames(scene(1), 3) for _, _, c, _ in f}
    assert {"^", "-", "v"} <= chars


def test_a_chest_appears_now_and_then_and_goes() -> None:
    shown = [any(c == "■" for _, _, c, _ in f) for f in frames(scene(4), 300)]
    assert any(shown) and not all(shown)
    assert sum(shown) < len(shown) * 0.4


SIZES = [(1, 1), (1, 40), (40, 1), (3, 5), (24, 80), (60, 213)]


def scene(seed: int, h: int = 24, w: int = 80) -> Dungeon:
    s = look_dungeon.make(False, random.Random(seed))
    s.resize(h, w)
    return s


def frames(s: Dungeon, seconds: float, tick: float = 0.1, start: float = 0.0) -> list[list[Cell]]:
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
    s = look_dungeon.make(False, random.Random(2))
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
    assert look_dungeon.THEME.name == "dungeon"
    assert look_dungeon.THEME.backdrop is look_dungeon.make
