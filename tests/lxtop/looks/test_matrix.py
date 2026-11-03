"""The Matrix look's rain: two layers, a rare glitch column, a trail that freezes and dissolves."""

from __future__ import annotations

import itertools
import random

import pytest

from lxtop.looks import matrix as look_matrix
from lxtop.looks.matrix import CONSOLE_FAR, DISSOLVE_SECONDS, FLASH_SECONDS, Rain
from lxtop.looks.theme import FX_DIM, FX_HEAD, FX_MID, Cell


def run(
    seed: int, h: int = 60, w: int = 213, seconds: float = 60.0, step: float = 0.1
) -> tuple[Rain, list[tuple[float, list[Cell]]]]:
    rain = look_matrix.rain(True, random.Random(seed))
    rain.resize(h, w)
    frames = [(i * step, rain.frame(i * step)) for i in range(int(seconds / step))]
    return rain, frames


def test_the_rain_is_sparse_at_a_big_screen() -> None:
    _, frames = run(1, seconds=30)
    share = max(len(cells) for _, cells in frames) / (60 * 213)
    assert share < 0.10


def test_a_dimmer_slower_layer_sits_behind_the_main_one() -> None:
    rain = Rain("AB", random.Random(2), far_chars="xy")
    rain.resize(40, 80)
    seen = set()
    for i in range(80):
        seen |= {c for _, _, c, _ in rain.frame(i * 0.1)}
    assert {"x", "y"} <= seen and {"A", "B"} <= seen
    near = [d.speed for d in rain.drops]
    far = [d.speed for d in rain.far if d]
    assert far and max(far) < min(near)
    cells = rain.frame(9.0)
    assert all(t == FX_DIM for _, _, c, t in cells if c in "xy")


def test_no_cell_is_drawn_twice() -> None:
    _, frames = run(3, h=30, w=100, seconds=30)
    assert any(cells for _, cells in frames), "some frame has cells"
    for _, cells in frames:
        spots = [(y, x) for y, x, _, _ in cells]
        assert len(spots) == len(set(spots))


def test_a_glitch_column_flashes_rarely_and_stays_bounded() -> None:
    rain, _ = run(4, seconds=1)
    flashes = []
    step = 0.05
    for i in range(int(90 / step)):
        now = 1.0 + i * step
        cells = rain.frame(now)
        if rain.flash:
            x = rain.flash[0]
            col = [c for c in cells if c[1] == x]
            assert all(t in (FX_HEAD, FX_MID) for *_, t in col)
            assert len(col) <= 60 // 3 + 2, "a band, not the whole column"
            flashes.append((x, rain.flash[1]))
    starts = sorted(set(flashes), key=lambda f: f[1])
    assert 3 <= len(starts) <= 15, "a few in 90 seconds"
    assert all(b[1] - a[1] >= FLASH_SECONDS for a, b in itertools.pairwise(starts))


def test_a_trail_freezes_then_dissolves_then_the_column_restarts() -> None:
    rain, _ = run(5, seconds=1)
    track: dict[int, list[tuple[float, int, int]]] = {}
    step = 0.05
    for i in range(int(120 / step)):
        now = 1.0 + i * step
        cells = rain.frame(now)
        x = rain.frozen
        if x is not None:
            n = sum(1 for c in cells if c[1] == x)
            track.setdefault(x, []).append((now, int(rain.drops[x].head), n))
    assert track, "a trail freezes within two minutes"
    for rows in track.values():
        heads = {head for _, head, _ in rows}
        assert len(heads) == 1, "the head stays put while frozen"
        counts = [n for *_, n in rows]
        assert counts[0] > counts[-1], "cells dissolve away"
        assert rows[-1][0] - rows[0][0] <= 1.3 + DISSOLVE_SECONDS + 0.2


@pytest.mark.parametrize("size", [(1, 1), (1, 40), (40, 1), (2, 3), (200, 5)])
def test_any_size_works_and_resizing_midway_is_safe(size: tuple[int, int]) -> None:
    h, w = size
    rain = look_matrix.rain(False, random.Random(6))
    rain.resize(h, w)
    for i in range(400):
        now = i * 0.1
        if i == 200:
            rain.resize(3, 7)
            h, w = 3, 7
        cells = rain.frame(now)
        assert all(0 <= y < h and 0 <= x < w and len(c) == 1 for y, x, c, _ in cells)


def test_same_seed_same_rain_and_console_rain_is_ascii_without_digits() -> None:
    a = [cells for _, cells in run(7, h=20, w=40, seconds=20)[1]]
    b = [cells for _, cells in run(7, h=20, w=40, seconds=20)[1]]
    assert a == b
    chars = {c for cells in a for _, _, c, _ in cells}
    assert chars <= set(look_matrix.CONSOLE_RAIN + CONSOLE_FAR)
    assert not chars & set("0123456789")
