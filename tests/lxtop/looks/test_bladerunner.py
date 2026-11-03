"""The Bladerunner look: slanted rain, flickering neon signs, flying cars, rare lightning."""

from __future__ import annotations

import itertools
import random

from lxtop.looks import bladerunner as lb
from lxtop.looks.theme import FX_DIM, FX_HEAD, FX_MID, TONES
from tests.support.backdrops import backdrop_of

H, W = 60, 213


def make(seed: int = 1, h: int = H, w: int = W) -> lb.Rain:
    return backdrop_of(lb.THEME, lb.Rain, seed, h, w)


def test_streaks_fall_and_drift_left() -> None:
    rain = make()
    rain.frame(0.0)
    before = [(s.y, s.x) for s in rain.streaks]
    rain.frame(0.1)
    moved = 0
    for (y, x), s in zip(before, rain.streaks, strict=True):
        if s.y > y:  # not respawned
            moved += 1
            assert s.x < x
            assert abs((x - s.x) / (s.y - y) - lb.SLANT) < 1e-6
    assert moved > len(before) * 0.9


def test_a_streak_is_a_few_cells_with_a_bright_head_above_its_tail() -> None:
    rain = make(h=40, w=100)
    rain.streaks = [lb._Streak(y=10.0, x=50.0, speed=20.0, length=3)]
    rain.signs, rain.cars, rain.next_car = [], [], 1e9
    cells = rain.frame(0.0)
    assert [c[3] for c in cells] == [FX_HEAD, FX_DIM, FX_DIM]
    rows = [c[0] for c in cells]
    cols = [c[1] for c in cells]
    assert rows == [10, 9, 8] and cols == sorted(cols)


def test_splashes_are_short_lived() -> None:
    rain = make()
    rain.streaks, rain.signs, rain.next_car = [], [], 1e9
    seen: dict[tuple[int, int], list[float]] = {}
    for step in range(600):
        t = step * 0.1
        for y, x, ch, _ in rain.frame(t):
            assert ch == lb.SPLASH
            seen.setdefault((y, x), []).append(t)
    assert seen, "splashes appear"
    for times in seen.values():
        start = times[0]
        for prev, t in itertools.pairwise(times):
            if t - prev > 0.15:  # a later splash at the same spot
                start = t
            assert t - start <= lb.SPLASH_LIFE


def lightning_frames(seed: int, seconds: int) -> int:
    rain = make(seed)
    count = 0
    for step in range(seconds * 10):
        if any(tone == FX_MID for *_, tone in rain.frame(step * 0.1)):
            count += 1
    return count


def test_lightning_is_rare_and_brief() -> None:
    for seed in range(8):
        frames = lightning_frames(seed, 60)
        assert frames <= 4 * 3, (seed, frames)  # at most a few flashes of a few frames
    assert any(lightning_frames(seed, 120) for seed in range(8)), "it does flash"


def test_lightning_never_fills_the_screen() -> None:
    rain = make()
    biggest = 0
    for step in range(1800):
        biggest = max(biggest, len(rain.frame(step * 0.1)))
    assert biggest < 0.1 * H * W


def test_sparse_outside_lightning() -> None:
    rain = make()
    frames = [rain.frame(step * 0.1) for step in range(300)]
    assert all({tone for *_, tone in cells} <= set(TONES) for cells in frames)
    quiet = [cells for cells in frames if not any(tone == FX_MID for *_, tone in cells)]
    assert quiet, "most frames have no lightning"  # 297 of 300 today
    assert max(len(cells) for cells in quiet) > 100, "rain falls between flashes"  # 332 today
    assert all(len(cells) < 0.1 * H * W for cells in quiet)


def test_console_uses_only_font_characters() -> None:
    backdrop = lb.THEME.backdrop
    assert backdrop is not None
    rain = backdrop(True, random.Random(2))
    rain.resize(30, 80)
    chars = {c for t in range(50) for _, _, c, _ in rain.frame(t * 0.1)}
    assert chars
    assert chars <= {lb.STREAK, lb.SPLASH, lb.SIGN, lb.CAR_HEAD, lb.CAR_TAIL}


def sign_cells(rain: lb.Rain, now: float) -> int:
    return sum(1 for _, _, ch, _ in rain.frame(now) if ch == lb.SIGN)


def test_signs_buzz_on_and_off_irregularly() -> None:
    rain = make(seed=4)
    counts = [sign_cells(rain, step * 0.09) for step in range(400)]
    assert min(counts) < max(counts), "signs go out and come back"
    assert max(counts) > 0
    changes = sum(1 for a, b in itertools.pairwise(counts) if a != b)
    assert changes > 20, "they flicker, not just toggle once"


def test_signs_hang_in_the_upper_part_as_short_horizontal_bars() -> None:
    rain = make()
    seen = 0
    for step in range(200):
        cells = [c for c in rain.frame(step * 0.09) if c[2] == lb.SIGN]
        seen += len(cells)
        assert all(y < H * lb.SIGN_ZONE for y, *_ in cells)
        rows: dict[int, int] = {}
        for y, *_ in cells:
            rows[y] = rows.get(y, 0) + 1
        assert all(n <= lb.SIGN_LEN[1] * len(rain.signs) for n in rows.values())
    assert seen > 0, "some sign is lit within 200 steps"


def test_cars_cross_slowly_in_the_upper_part_and_are_bounded() -> None:
    rain = make(seed=2)
    rain.streaks, rain.signs = [], []
    seen_cars = most = 0
    xs: list[float] = []
    for step in range(1500):
        cells = rain.frame(step * 0.1)
        heads = [c for c in cells if c[2] == lb.CAR_HEAD]
        most = max(most, len(rain.cars))
        assert all(y < H * lb.CAR_ZONE + 1 for y, *_ in heads)
        if heads:
            seen_cars += 1
        if len(rain.cars) == 1:
            xs.append(rain.cars[0].x)
    assert seen_cars > 50, "cars do cross"
    assert most <= lb.CAR_MAX
    steps = [abs(b - a) for a, b in itertools.pairwise(xs) if abs(b - a) < 5]
    assert steps and max(steps) <= lb.CAR_SPEED[1] * 0.1 + 1e-6


def test_tiny_and_resized_screens_are_safe() -> None:
    for h, w in ((1, 1), (1, 40), (40, 1), (2, 2)):
        rain = make(h=h, w=w)
        for step in range(300):
            for y, x, *_ in rain.frame(step * 0.1):
                assert 0 <= y < h and 0 <= x < w
    rain = make()
    for step, (h, w) in enumerate(((60, 213), (10, 30), (1, 1), (45, 100))):
        rain.resize(h, w)
        for k in range(50):
            for y, x, *_ in rain.frame((step * 50 + k) * 0.1):
                assert 0 <= y < h and 0 <= x < w


def test_seeded_runs_are_identical() -> None:
    a, b = make(seed=9), make(seed=9)
    for step in range(200):
        assert a.frame(step * 0.1) == b.frame(step * 0.1)
