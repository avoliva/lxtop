"""The critters look: swaying grass patches, birds, and a creature that peeks out of the grass."""

from __future__ import annotations

import random

import pytest

from lxtop.looks import critters as look_critters
from lxtop.looks.critters import Meadow
from lxtop.looks.theme import FX_DIM, FX_HEAD, FX_MID, Cell


def test_the_grass_sways() -> None:
    s = scene(1)
    a = {(y, x): c for y, x, c, _ in s.frame(0.0)}
    b = {(y, x): c for y, x, c, _ in s.frame(0.6)}
    grass = [k for k in a if a[k] in look_critters.GRASS]
    assert grass and any(a[k] != b.get(k) for k in grass)


def test_an_alert_comes_before_a_creature_peeks_out() -> None:
    order = []
    for f in frames(scene(2), 120):
        chars = "".join(c for _, _, c, _ in f)
        if "!" in chars:
            order.append("!")
        elif "(" in chars:
            order.append("(")
    assert "!" in order and "(" in order
    assert order.index("!") < order.index("("), "the alert comes first"


def test_encounters_are_occasional() -> None:
    busy = [any(c in "!(" for _, _, c, _ in f) for f in frames(scene(5), 300)]
    assert 0 < sum(busy) < len(busy) * 0.5


SIZES = [(1, 1), (1, 40), (40, 1), (3, 5), (24, 80), (60, 213)]


def scene(seed: int, h: int = 24, w: int = 80) -> Meadow:
    s = look_critters.make(False, random.Random(seed))
    s.resize(h, w)
    return s


def frames(s: Meadow, seconds: float, tick: float = 0.1, start: float = 0.0) -> list[list[Cell]]:
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
    s = look_critters.make(False, random.Random(2))
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
    assert look_critters.THEME.name == "critters"
    assert look_critters.THEME.backdrop is look_critters.make
