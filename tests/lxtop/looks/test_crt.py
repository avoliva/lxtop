"""The CRT look: a bright band rolling down the screen and flickering static."""

from __future__ import annotations

import random

import pytest

from lxtop.looks.crt import FLICKER_SECONDS, GHOST_SECONDS, ROLL_SECONDS, THEME, Roll
from lxtop.looks.theme import FX_DIM, FX_MID


def roll(h: int = 60, w: int = 213, seed: int = 1) -> Roll:
    backdrop = Roll(False, random.Random(seed))
    backdrop.resize(h, w)
    return backdrop


def mid_rows(backdrop: Roll, now: float) -> list[int]:
    cells = backdrop.frame(now)
    return sorted({y for y, _, c, tone in cells if c == "░" and tone == FX_MID})


def test_the_band_rolls_down_and_wraps_every_six_seconds() -> None:
    backdrop = roll()
    rows = [mid_rows(backdrop, t) for t in (1.0, 2.0, 3.0, 4.0, 5.0)]
    assert all(len(r) == 1 for r in rows)
    flat = [r[0] for r in rows]
    assert flat == sorted(flat) and len(set(flat)) == 5
    assert backdrop.band_row(0.0) == backdrop.band_row(ROLL_SECONDS)


def test_dim_light_shade_rows_sit_above_and_below_the_band() -> None:
    backdrop = roll()
    cells = backdrop.frame(3.0)
    (row,) = mid_rows(backdrop, 3.0)
    dim = {y for y, _, c, tone in cells if c == "░" and tone == FX_DIM}
    assert dim == {row - 1, row + 1}
    assert sum(1 for y, _, c, _ in cells if y == row and c == "░") == 213


def test_static_specks_flicker() -> None:
    backdrop = roll()
    frames = [
        frozenset((y, x) for y, x, c, _ in backdrop.frame(0.0) if c in ".,") for _ in range(5)
    ]
    assert all(frames) and len(set(frames)) == 5


def test_the_roll_is_sparse() -> None:
    backdrop = roll()
    for step in range(120):
        assert len(backdrop.frame(step * 0.1)) < 0.1 * 60 * 213


@pytest.mark.parametrize("size", [(1, 1), (1, 30), (30, 1), (3, 5)])
def test_tiny_screens_and_resizes_stay_inside(size: tuple[int, int]) -> None:
    backdrop = roll(*size)
    for h, w in (size, (30, 80), (1, 1), (60, 213)):
        backdrop.resize(h, w)
        for step in range(70):
            assert all(0 <= y < h and 0 <= x < w for y, x, _, _ in backdrop.frame(step * 0.1))


def test_the_same_seed_gives_the_same_frames() -> None:
    a, b = roll(seed=6), roll(seed=6)
    assert all(a.frame(t * 0.3) == b.frame(t * 0.3) for t in range(30))


def test_the_amber_text_stays_clear_of_the_yellow_warning() -> None:
    assert THEME.colours[2][0] in (220, 226) and 200 <= THEME.colours[1][0] <= 214


def ghost_letters(backdrop: Roll, now: float) -> list[tuple[int, int, str]]:
    return [(y, x, c) for y, x, c, _ in backdrop.frame(now) if c.isalpha()]


def test_the_burn_in_ghost_is_dim_letters_that_fade_away() -> None:
    backdrop = roll(seed=2)
    early = ghost_letters(backdrop, 1.0)
    late = ghost_letters(backdrop, GHOST_SECONDS - 1.0)
    assert early and len(late) < len(early)
    tones = {t for _, _, c, t in backdrop.frame(1.0) if c.isalpha()}
    assert tones == {FX_DIM}
    chars = "".join(c for _, _, c in early)
    assert chars.isalpha() and chars.islower()


def test_a_new_ghost_appears_each_cycle() -> None:
    backdrop = roll(seed=4)
    first = ghost_letters(backdrop, 1.0)
    second = ghost_letters(backdrop, GHOST_SECONDS + 1.0)
    assert second and first != second


def test_a_rare_burst_of_static_crosses_a_few_rows_then_ends() -> None:
    backdrop = roll(seed=3)
    backdrop.frame(0.0)
    start = backdrop.flicker_at
    assert start is not None and start >= 14.0
    burst = [c for c in backdrop.frame(start + 0.1) if c[2] in "▒:;"]
    rows = {y for y, *_ in burst}
    assert burst and 2 <= len(rows) <= 4
    assert len(burst) < 0.3 * 213 * 4 + 1
    after = backdrop.frame(start + FLICKER_SECONDS + 0.1)
    assert not [c for c in after if c[2] in "▒:;"]
    assert backdrop.flicker_at is not None and backdrop.flicker_at > start


def test_bursts_are_rare() -> None:
    backdrop = roll(seed=8)
    lit = sum(1 for step in range(1200) if any(c[2] in "▒:;" for c in backdrop.frame(step * 0.12)))
    assert 0 < lit < 1200 * 0.1
