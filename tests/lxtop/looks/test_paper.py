"""The Paper look: dark ink on cream, calm, readable warnings and a few slow ink blots."""

from __future__ import annotations

import random

import pytest

from lxtop.looks import theme
from lxtop.looks.paper import BLOT_SECONDS, THEME
from tests.support.colours import contrast, grounds


def test_every_pair_sits_on_cream_paper() -> None:
    pairs = theme.pairs(THEME, 256)
    plain = {
        pair: bg
        for pair, (_, bg) in pairs.items()
        if pair < theme.GLASS and pair not in (theme.FX_GLASS, theme.FX_GLASS_HEAD)
    }
    assert set(plain) >= set(range(1, 8)) and set(plain.values()) == {230}
    assert {bg for _, bg in theme.pairs(THEME, 8).values()} == {theme.WHITE_8}
    glass = {bg for pair, (_, bg) in pairs.items() if pair >= theme.GLASS}
    assert glass == {THEME.glass} and THEME.glass != 230


def test_it_is_calm() -> None:
    assert THEME.glitch is False
    assert THEME.backdrop is not None
    assert THEME.boot


def test_ink_is_dark_and_warnings_are_readable_and_stand_out() -> None:
    fg = {pair: c for pair, (c, _) in theme.pairs(THEME, 256).items()}
    assert fg[7] in range(232, 239) and fg[4] == 240
    assert {fg[1], fg[5]} == {22, 18}
    assert fg[2] == 130 and fg[3] == 160
    assert THEME.accent in (1, 4, 5, 6, 7)
    for ground in grounds(THEME):
        assert contrast(fg[2], ground) >= 3.5 and contrast(fg[3], ground) >= 4.0
        assert min(contrast(fg[p], ground) for p in (1, 4, 5, 7)) >= 4.5


def test_the_frame_is_a_ruled_double_line() -> None:
    assert THEME.frame == "╔╗╚╝═║"


def test_blots_move_fade_and_stay_sparse() -> None:
    blots = THEME.backdrop(True, random.Random(1))  # type: ignore[misc]
    blots.resize(60, 213)
    frames = [blots.frame(t * 2.0) for t in range(int(BLOT_SECONDS))]
    assert any(frames) and len({tuple(f) for f in frames}) > 5
    assert max(len(f) for f in frames) < 0.03 * 60 * 213
    tones = {tone for f in frames for *_, tone in f}
    assert len(tones) == 3, "young blots are darker than old ones"
    cells = [(y, x) for f in frames for y, x, _, _ in f]
    assert len({c for c in frames[3]}) == len(frames[3]) and cells


def test_blots_are_seeded_and_survive_any_size() -> None:
    a, b = (THEME.backdrop(False, random.Random(9)) for _ in range(2))  # type: ignore[misc]
    for backdrop in (a, b):
        backdrop.resize(40, 100)
    assert a.frame(12.5) == b.frame(12.5)
    assert a.frame(12.5) != THEME.backdrop(False, random.Random(10)).frame(12.5)  # type: ignore[misc]


@pytest.mark.parametrize("size", [(1, 1), (1, 80), (50, 1), (2, 3), (60, 213)])
def test_blots_stay_on_screen_after_a_resize(size: tuple[int, int]) -> None:
    backdrop = THEME.backdrop(True, random.Random(4))  # type: ignore[misc]
    backdrop.resize(30, 80)
    backdrop.frame(1.0)
    h, w = size
    backdrop.resize(h, w)
    for step in range(60):
        for y, x, char, _ in backdrop.frame(step * 0.9):
            assert 0 <= y < h and 0 <= x < w and len(char) == 1 and not char.isdigit()
