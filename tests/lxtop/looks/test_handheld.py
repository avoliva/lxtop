"""The handheld look: pale LCD colours and a tiny falling-block puzzle."""

from __future__ import annotations

import random

import pytest

from lxtop.looks import theme
from lxtop.looks.handheld import FLASH_STEPS, STEP, THEME, Blocks


def blocks(h: int = 60, w: int = 213, seed: int = 1) -> Blocks:
    backdrop = Blocks(False, random.Random(seed))
    backdrop.resize(h, w)
    return backdrop


def test_a_piece_falls_into_the_well() -> None:
    backdrop = blocks(h=40, w=60)
    well = backdrop.wells[0]
    for _ in range(3):
        well.step()
    assert well.piece is not None
    first = well.r
    well.step()
    assert well.r > first


def test_pieces_land_and_leave_a_pile_on_the_floor() -> None:
    backdrop = blocks(h=30, w=60)
    well = backdrop.wells[0]
    for _ in range(30):
        well.step()
    assert any(any(row) for row in well.grid)


def test_a_pile_never_rises_above_its_cap() -> None:
    backdrop = blocks(h=30, w=60)
    well = backdrop.wells[0]
    tallest = 0
    for _ in range(4000):
        well.step()
        tallest = max(tallest, well.h - well._top())
    assert tallest <= well.cap + 4, "a piece lands on top of a pile no taller than the cap"


def test_a_full_row_blinks_then_clears() -> None:
    backdrop = blocks(h=30, w=60)
    well = backdrop.wells[0]
    for c in range(well.bw - 1):
        well.grid[well.h - 1][c] = True
    well.piece = ((0, 0),)
    well.r, well.c, well.target = well.h - 2, well.bw - 1, well.bw - 1
    well.step()
    well.step()
    assert well.flash == [well.h - 1] and well.flash_left == FLASH_STEPS
    assert backdrop.frame(0.0)
    for _ in range(FLASH_STEPS):
        well.step()
    assert not well.flash and not any(well.grid[well.h - 1])
    assert well.clears == 1


def test_the_rare_event_happens_and_stays_bounded() -> None:
    backdrop = blocks(h=40, w=80, seed=3)
    well = backdrop.wells[0]
    peak = 0
    for step in range(1, 3001):
        cells = backdrop.frame(step * STEP)
        peak = max(peak, len(cells))
    assert well.clears > 0, "a full row clears now and then"
    assert peak < 0.1 * 40 * 80


def test_an_overgrown_pile_is_wiped() -> None:
    backdrop = blocks(h=12, w=60)
    well = backdrop.wells[0]
    for r in range(well.h - well.cap - 1, well.h):
        for c in range(well.bw - 1):
            well.grid[r][c] = True
    well.piece = ((0, 0), (1, 0))
    well.r, well.c, well.target = well.h - well.cap - 3, well.bw - 1, well.bw - 1
    for _ in range(30):
        well.step()
    assert well.h - well._top() <= well.cap


def test_console_uses_only_console_font_characters() -> None:
    backdrop = Blocks(True, random.Random(2))
    backdrop.resize(30, 80)
    chars = {c for t in range(200) for _, _, c, _ in backdrop.frame(t * 0.2)}
    assert chars
    assert chars <= set("█▒░·")


def test_the_well_is_sparse_at_a_big_screen() -> None:
    backdrop = blocks()
    for step in range(200):
        assert len(backdrop.frame(step * 0.3)) < 0.1 * 60 * 213


@pytest.mark.parametrize("size", [(1, 1), (1, 30), (30, 1), (3, 5), (2, 12), (60, 213)])
def test_tiny_screens_and_resizes_stay_inside(size: tuple[int, int]) -> None:
    backdrop = blocks(*size)
    for h, w in (size, (30, 80), (1, 1), (60, 213), (8, 20), (0, 0)):
        backdrop.resize(h, w)
        for step in range(60):
            assert all(0 <= y < h and 0 <= x < w for y, x, _, _ in backdrop.frame(step * 0.5))


def test_the_same_seed_gives_the_same_frames() -> None:
    a, b = blocks(seed=4), blocks(seed=4)
    assert all(a.frame(t * 0.1) == b.frame(t * 0.1) for t in range(400))
    c = blocks(seed=5)
    assert any(a.frame(t * 0.1) != c.frame(t * 0.1) for t in range(400, 800))


def test_the_refresh_sweep_brightens_the_dot_grid_for_a_while() -> None:
    backdrop = blocks(h=30, w=60)
    tones = [{t for _, _, ch, t in backdrop.frame(s * 0.25) if ch == "·"} for s in range(1, 400)]
    assert any(theme.FX_MID in t for t in tones) and any(t == {theme.FX_DIM} for t in tones)


def test_every_pair_sits_on_the_light_background_at_256_colours() -> None:
    pairs = theme.pairs(THEME, 256)
    light = {pair: bg for pair, (_, bg) in pairs.items() if pair < theme.FX_GLASS}
    assert set(light.values()) == {THEME.background_rich}
    glass = {bg for pair, (_, bg) in pairs.items() if pair >= theme.FX_GLASS}
    assert glass == {THEME.glass} and THEME.glass != THEME.background_rich


def test_text_is_darker_than_the_effects_and_the_screen_is_pale() -> None:
    assert THEME.background == theme.WHITE_8 and THEME.background_rich == 194
    assert dict(THEME.console_palette)[theme.WHITE_8] == dict(THEME.console_palette)[15]
