"""The swarm look: a marching formation, a sliding cannon, shots and bursts, a passing saucer."""

from __future__ import annotations

import random

import pytest

from lxtop.looks import swarm as look_swarm
from lxtop.looks.swarm import Invasion
from lxtop.looks.theme import FX_DIM, FX_HEAD, FX_MID, Cell


def test_the_formation_marches_and_steps_down() -> None:
    s = scene(1)
    lefts = {s.formation(i * 0.5)[2] for i in range(200)}
    tops = {s.formation(i * 0.5)[1] for i in range(400)}
    assert len(lefts) > 10 and len(tops) > 1


def test_the_aliens_move_their_legs() -> None:
    chars = {c for f in frames(scene(1), 2) for _, _, c, _ in f}
    assert {"W", "M"} <= chars


def test_the_cannon_shoots_and_aliens_fall() -> None:
    s = scene(3)
    shots = bursts = 0
    for f in frames(s, 120):
        chars = [c for _, _, c, _ in f]
        shots += "|" in chars
        bursts += "*" in chars
        assert chars.count("▲") == 1
    assert shots and bursts
    assert s.dead or s.wave > 0


def test_a_saucer_crosses_now_and_then() -> None:
    shown = [any(c == "■" for _, _, c, _ in f) for f in frames(scene(4), 300)]
    assert any(shown) and sum(shown) < len(shown) * 0.4


SIZES = [(1, 1), (1, 40), (40, 1), (3, 5), (24, 80), (60, 213)]


def scene(seed: int, h: int = 24, w: int = 80) -> Invasion:
    s = look_swarm.make(False, random.Random(seed))
    s.resize(h, w)
    return s


def frames(s: Invasion, seconds: float, tick: float = 0.1, start: float = 0.0) -> list[list[Cell]]:
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
    s = look_swarm.make(False, random.Random(2))
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
    assert look_swarm.THEME.name == "swarm"
    assert look_swarm.THEME.backdrop is look_swarm.make
