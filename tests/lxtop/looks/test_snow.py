"""The Snow look: flakes fall with a wobble and a gust now and then pushes them sideways."""

from __future__ import annotations

from lxtop.looks import snow as look_snow
from lxtop.looks import theme
from lxtop.looks.theme import TONES
from tests.support.backdrops import backdrop_of
from tests.support.colours import contrast

H, W = 60, 213


def make(seed: int = 1, h: int = H, w: int = W) -> look_snow.Snowfall:
    return backdrop_of(look_snow.THEME, look_snow.Snowfall, seed, h, w)


def test_flakes_fall_at_their_own_speed() -> None:
    snow = make()
    snow.frame(0.0)
    flake = snow.flakes[0]
    flake.y, flake.speed = 10.0, 2.0
    snow.frame(1.0)
    assert flake.y == 12.0
    rows = [int(f.y) for f in snow.flakes]
    snow.frame(2.0)
    fallen = sum(1 for f, row in zip(snow.flakes, rows, strict=True) if f.y > row)
    assert fallen >= len(rows) * 0.9


def test_a_flake_that_lands_starts_again_above_the_top() -> None:
    snow = make()
    snow.frame(0.0)
    snow.flakes[0].y = H - 0.5
    snow.flakes[0].speed = 2.0
    snow.frame(1.0)
    assert snow.flakes[0].y < 0


def test_a_gust_blows_for_a_few_seconds_and_dies_down() -> None:
    snow = make(3)
    winds = []
    for step in range(900):  # 90 seconds
        snow.frame(step * 0.1)
        winds.append(snow.wind)
    strong = [i for i, wind in enumerate(winds) if abs(wind) > 4]
    assert strong, "at least one gust within 90 seconds"
    assert len(strong) < len(winds) / 2, "gusts are the exception"
    assert abs(winds[-1]) < 16 and min(abs(w) for w in winds[strong[0] :]) < 1


def test_the_wind_pushes_flakes_sideways() -> None:
    snow = make()
    snow.frame(0.0)
    snow.wind = snow.target = 10.0
    snow.next_gust = 1e9
    xs = [f.x for f in snow.flakes]
    snow.frame(1.0)
    moved = sum(1 for f, x in zip(snow.flakes, xs, strict=True) if f.x != x)
    assert moved >= len(xs) * 0.9


def test_the_snow_is_sparse() -> None:
    snow = make()
    for t in range(40):
        assert len(snow.frame(t * 0.5)) < 0.1 * H * W


def test_works_at_any_size_and_after_a_resize() -> None:
    snow = make(1, 1, 1)
    for t in range(20):
        assert all(y == 0 and x == 0 for y, x, _, _ in snow.frame(t * 0.3))
    for h, w in ((1, 50), (50, 1), (3, 9), (60, 213)):
        snow.resize(h, w)
        for t in range(20):
            frame = snow.frame(10 + t * 0.3)
            assert all(0 <= y < h and 0 <= x < w and tone in TONES for y, x, _, tone in frame)


def test_frames_are_deterministic_for_a_seed() -> None:
    a, b = make(7), make(7)
    assert [a.frame(t * 0.3) for t in range(30)] == [b.frame(t * 0.3) for t in range(30)]


def run(snow: look_snow.Snowfall, seconds: float, step: float = 0.25) -> list[int]:
    return [len(snow.flakes) for _ in [snow.frame(i * step) for i in range(int(seconds / step))]]


def test_snow_settles_along_the_bottom_and_melts_away() -> None:
    snow = make(2)
    snow.flurry_left, snow.next_flurry = 0.0, 1e9
    run(snow, 60)
    assert max(snow.pile) > 0.3
    cells = snow.frame(61.0)
    assert any(y >= H - 2 for y, *_ in cells)
    snow.flakes = []
    snow.next_flurry = 1e9
    before = sum(snow.pile)
    for i in range(1, 400):  # 100 seconds with nothing falling
        snow.flakes = []
        snow.frame(61.0 + i * 0.25)
    assert sum(snow.pile) < before * 0.2
    assert max(snow.pile) <= look_snow.PILE_MAX


def test_a_rare_heavier_flurry_comes_and_stays_bounded() -> None:
    snow = make(4)
    base = len(snow.flakes)
    counts, shown = [], []
    for i in range(2400):  # 10 minutes
        shown.append(len(snow.frame(i * 0.25)))
        counts.append(len(snow.flakes))
    assert max(counts) > base * 1.5, "a flurry within ten minutes"
    assert max(counts) <= base * (1 + look_snow.FLURRY_EXTRA) + 1
    quiet = [c for c in counts if c <= base]
    assert len(quiet) > len(counts) * 0.5, "flurries are the exception"
    assert max(shown) < 0.1 * H * W


def test_effect_colours_are_quieter_than_all_text() -> None:
    fg = {p: c for p, (c, _) in theme.pairs(look_snow.THEME, 256).items()}
    for ground in (16, look_snow.THEME.glass):
        quietest = min(contrast(fg[p], ground) for p in range(1, 8))
        for p in (*TONES, theme.FX_GLASS, theme.FX_GLASS_HEAD):
            assert contrast(fg[p], ground) < quietest
