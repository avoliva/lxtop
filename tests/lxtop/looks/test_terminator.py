"""Terminator look: reticle corners, two scan lines, target locks that close in, a rare
analysing flash, the alarm red alone, and sparse effects."""

from __future__ import annotations

import random

from lxtop.looks import theme
from lxtop.looks.terminator import THEME
from lxtop.viewer.screen import BLUE, CYAN, GREEN, MAGENTA, RED, WHITE, YELLOW

TEXT = (GREEN, CYAN, MAGENTA, BLUE, WHITE)
H, W = 60, 213


def backdrop(console: bool = False, seed: int = 1, h: int = H, w: int = W) -> theme.Backdrop:
    assert THEME.backdrop is not None
    b = THEME.backdrop(console, random.Random(seed))
    b.resize(h, w)
    return b


def test_the_horizontal_sweep_starts_at_the_top_and_moves_down() -> None:
    b = backdrop()
    seen = []
    for step in range(60):
        cells = b.frame(step * 0.05)
        full = {
            y for y in range(H) if sum(1 for cy, _, c, t in cells if cy == y and c == "─") > W // 2
        }
        seen.append(min(full) if full else -1)
    swept = [r for r in seen if r >= 0]
    assert swept[0] == 0 and swept == sorted(swept)


def test_the_sweep_reaches_the_bottom_of_the_screen() -> None:
    b = backdrop()
    hit = any(
        y == H - 1 and c == "─" and t == theme.FX_HEAD
        for step in range(300)
        for y, _, c, t in b.frame(step * 0.02)
        if y > 0
    )
    assert hit


def test_a_vertical_scan_line_moves_across() -> None:
    b = backdrop()
    cols = []
    for step in range(100):
        cells = b.frame(step * 0.05)
        by_col: dict[int, int] = {}
        for _, x, c, _ in cells:
            if c == "│":
                by_col[x] = by_col.get(x, 0) + 1
        full = [x for x, n in by_col.items() if n > H // 2]
        if full:
            cols.append(full[0])
    assert len(cols) > 10 and cols == sorted(cols) and cols[-1] > cols[0] + W // 4


def test_reticle_brackets_sit_in_all_four_corners() -> None:
    cells = {(y, x): c for y, x, c, _ in backdrop().frame(6.5)}
    assert cells[(0, 0)] == "┏" and cells[(0, W - 1)] == "┓"
    assert cells[(H - 1, 0)] == "┗" and cells[(H - 1, W - 1)] == "┛"


def test_lock_brackets_close_in_and_then_hold() -> None:
    b = backdrop(seed=4)
    widths = []
    for step in range(25):
        cells = b.frame(step * 0.05)
        # the first target's row: brackets '[' and ']' on one row
        rows: dict[int, list[tuple[int, str]]] = {}
        for y, x, c, _ in cells:
            if c in "[]":
                rows.setdefault(y, []).append((x, c))
        pair = next((sorted(v) for v in rows.values() if len(v) == 2), None)
        if pair:
            widths.append(pair[1][0] - pair[0][0])
    assert max(widths) > min(widths) >= 6
    assert widths[-1] == min(widths)


def _flash_frames(seed: int, console: bool = False) -> list[float]:
    b = backdrop(console, seed)
    hits = []
    for step in range(int(120 / 0.05)):
        now = step * 0.05
        if any(c in "═║" or (console and c == "=") for _, _, c, _ in b.frame(now)):
            hits.append(now)
    return hits


def test_the_analysing_flash_is_rare_and_bounded() -> None:
    for seed in (1, 2, 3):
        hits = _flash_frames(seed)
        assert hits, "it happens within two minutes"
        assert len(hits) * 0.05 < 120 * 0.1, "and fills a small share of the time"
        # each flash lasts under a second and a half
        runs, last = 0, -9.0
        for t in hits:
            runs += t - last > 0.5
            last = t
        assert runs <= 8


def test_the_flash_box_stays_small() -> None:
    b = backdrop()
    for step in range(int(120 / 0.05)):
        cells = [c for c in b.frame(step * 0.05) if c[2] in "═║"]
        assert len(cells) <= 60


def test_effects_stay_sparse_and_drawn_once_per_cell() -> None:
    for console in (False, True):
        b = backdrop(console)
        for step in range(400):
            cells = b.frame(step * 0.05)
            assert len({(y, x) for y, x, _, _ in cells}) == len(cells)
            assert len(cells) < 0.10 * H * W


def test_same_seed_same_frames() -> None:
    a, b = backdrop(seed=9), backdrop(seed=9)
    for step in range(200):
        assert sorted(a.frame(step * 0.1)) == sorted(b.frame(step * 0.1))


def test_tiny_and_resized_screens_are_safe() -> None:
    for h, w in ((1, 1), (1, 40), (40, 1), (2, 3), (5, 7)):
        b = backdrop(True, h=h, w=w)
        for step in range(300):
            for y, x, ch, _ in b.frame(step * 0.1):
                assert 0 <= y < h and 0 <= x < w and len(ch) == 1
    b = backdrop()
    b.frame(1.0)
    b.resize(10, 30)
    assert all(y < 10 and x < 30 for y, x, _, _ in b.frame(1.1))


def test_a_clock_that_restarts_is_safe() -> None:
    b = backdrop()
    b.frame(500.0)
    assert b.frame(0.0)


def test_the_alarm_red_is_the_only_red_at_256_colours() -> None:
    fg = {pair: c for pair, (c, _) in theme.pairs(THEME, 256).items()}
    assert fg[RED] == 196
    assert not {196, 160, 124, 9} & {fg[p] for p in (*TEXT, YELLOW)}


def test_every_text_colour_on_the_console_has_a_redefined_slot() -> None:
    slots = {slot for slot, _ in THEME.console_palette}
    for pair in TEXT:
        plain = THEME.colours[pair][1]
        assert plain in slots and 8 + plain in slots, pair
