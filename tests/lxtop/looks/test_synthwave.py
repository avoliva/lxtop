"""The synthwave look's sun, grid floor, stars and rare events: sparse, safe at any size."""

from __future__ import annotations

import itertools
import random

import pytest

from lxtop.looks.synthwave import THEME, Outrun
from lxtop.looks.theme import FX_HEAD, FX_MID, TONES

SUN = "▓"


def grid(h: int = 60, w: int = 213, console: bool = False, seed: int = 1) -> Outrun:
    backdrop = Outrun(console, random.Random(seed))
    backdrop.resize(h, w)
    return backdrop


def line_rows(backdrop: Outrun, now: float, char: str) -> list[int]:
    cells = backdrop.frame(now)
    rows: dict[int, int] = {}
    for y, _, c, _ in cells:
        if c == char:
            rows[y] = rows.get(y, 0) + 1
    return sorted(y for y, n in rows.items() if n > backdrop.w // 4)


def test_horizontal_lines_move_toward_the_viewer_and_spread_apart() -> None:
    backdrop = grid()
    before, after = line_rows(backdrop, 0.0, "─"), line_rows(backdrop, 0.5, "─")
    assert len(before) == len(after) >= 3
    assert all(b >= a for a, b in zip(before, after, strict=True)) and sum(after) > sum(before)
    gaps = [b - a for a, b in itertools.pairwise(after)]
    assert gaps == sorted(gaps) and gaps[-1] > gaps[0], "further apart near the bottom"
    assert min(after) >= backdrop.horizon, "the floor is the bottom third"


def test_converging_lines_fan_out_from_the_horizon_centre() -> None:
    backdrop = grid()
    cells = backdrop.frame(0.0)
    centre = (backdrop.w - 1) / 2
    spans: dict[int, tuple[int, int]] = {}
    for y, x, c, _ in cells:
        if c in "/\\|":
            lo, hi = spans.get(y, (x, x))
            spans[y] = (min(lo, x), max(hi, x))
    rows = sorted(spans)
    first, last = spans[rows[0]], spans[rows[-1]]
    assert last[1] - last[0] > 3 * (first[1] - first[0] + 1)
    assert first[0] <= centre <= first[1] + 1 and last[0] < centre < last[1]


def test_stars_twinkle_in_the_top_third() -> None:
    backdrop = grid()
    seen: list[frozenset[tuple[int, int]]] = []
    for step in range(60):
        stars = [(y, x) for y, x, c, _ in backdrop.frame(step * 0.2) if c in ".+*"]
        assert all(y < 20 for y, _ in stars)
        seen.append(frozenset(stars))
    assert len(set(seen)) > 5 and all(seen)


@pytest.mark.parametrize("console", (True, False))
def test_the_backdrop_is_sparse_and_uses_only_effect_tones(console: bool) -> None:
    backdrop = grid(console=console)
    for step in range(600):
        cells = backdrop.frame(step * 0.1)
        assert len(cells) < 0.1 * 60 * 213
        assert {t for *_, t in cells} <= set(TONES)
    assert {t for *_, t in backdrop.frame(0.5)} & {FX_HEAD, FX_MID}


@pytest.mark.parametrize("size", [(1, 1), (1, 40), (40, 1), (2, 2), (3, 3), (5, 7)])
def test_tiny_screens_and_resizes_stay_inside(size: tuple[int, int]) -> None:
    backdrop = grid(*size)
    for h, w in (size, (30, 80), (1, 1), (60, 213)):
        backdrop.resize(h, w)
        for step in range(30):
            assert all(0 <= y < h and 0 <= x < w for y, x, _, _ in backdrop.frame(step * 0.3))


def test_the_same_seed_gives_the_same_frames() -> None:
    a, b = grid(seed=9), grid(seed=9)
    assert all(a.frame(t * 0.1) == b.frame(t * 0.1) for t in range(30))


def test_the_look_is_a_dark_one_with_the_grid_backdrop() -> None:
    assert THEME.name == "synthwave" and THEME.backdrop is not None and THEME.background == 0


def sun_cells(backdrop: Outrun, now: float) -> dict[int, list[int]]:
    char = "▒" if backdrop.console else SUN
    rows: dict[int, list[int]] = {}
    for y, x, c, _ in backdrop.frame(now):
        if c == char:
            rows.setdefault(y, []).append(x)
    return rows


def test_the_sun_is_a_striped_half_disc_at_the_horizon_centre() -> None:
    backdrop = grid()
    rows = sun_cells(backdrop, 0.0)
    assert rows and max(rows) < backdrop.horizon
    xs = [x for cols in rows.values() for x in cols]
    assert abs((min(xs) + max(xs)) / 2 - (backdrop.w - 1) / 2) <= 1
    span = range(backdrop.horizon - backdrop.sun, backdrop.horizon)
    gaps = [y for y in span if y not in rows]
    assert gaps, "bands have gaps between them"
    assert gaps == sorted(gaps) and max(gaps) - min(gaps) >= 3
    # gaps are thicker toward the bottom than the top
    lit = [y in rows for y in span]
    half = len(lit) // 2
    assert lit[:half].count(False) <= lit[half:].count(False)
    assert len(xs) < 0.05 * backdrop.h * backdrop.w


def test_the_sun_stripes_slide_down_over_time() -> None:
    backdrop = grid()
    shapes = {frozenset(sun_cells(backdrop, t * 0.5)) for t in range(30)}
    assert len(shapes) > 3


def test_a_rare_event_happens_and_stays_bounded() -> None:
    backdrop = grid(seed=4)
    kinds = set()
    busy = 0
    frames = 0
    for t in range(0, 1200):
        cells = backdrop.frame(t * 0.1)
        frames += 1
        ev = backdrop.event
        if ev is not None:
            kinds.add(ev[0])
            busy += 1
        extra = [c for _, _, c, _ in cells if c == "*"]
        assert len(extra) < 60
    assert kinds, "an event shows within two minutes"
    assert 0 < busy < frames * 0.2, "rare: well under a fifth of the time"


def test_the_events_cross_the_screen_and_end() -> None:
    backdrop = grid(seed=2)
    backdrop.frame(0.0)
    for kind in ("star", "streak"):
        backdrop.event = (kind, 100.0, 120, 1)
        seen: list[set[int] | set[tuple[int, int]]] = []
        for step in range(40):
            now = 100.0 + step * 0.1
            backdrop.next_at = 1e9
            cells = backdrop.frame(now)
            horizon_row = backdrop.horizon - 1
            if kind == "streak":
                seen.append({x for y, x, _, tone in cells if y == horizon_row and tone == FX_HEAD})
            else:
                seen.append({(y, x) for y, x, c, _ in cells if c == "*" and y < 20})
        assert len({frozenset(s) for s in seen}) > 5, kind
        backdrop.frame(100.0 + 10)
        assert backdrop.event is None


def test_events_do_not_leak_across_a_resize() -> None:
    backdrop = grid()
    backdrop.event = ("streak", 0.0, 3, 0)
    backdrop.resize(20, 50)
    assert backdrop.event is None


def test_console_mode_draws_only_ascii_or_console_font_characters() -> None:
    backdrop = grid(console=True, seed=6)
    chars = set()
    for t in range(1000):
        chars |= {c for _, _, c, _ in backdrop.frame(t * 0.1)}
    assert chars
    assert chars <= set(".+*-=/\\|▒")
