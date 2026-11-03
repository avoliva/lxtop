"""The Coffee look: steam curls up from the bottom, aroma motes drift, and now and then a slow
ripple spreads across a cup surface and fades."""

from __future__ import annotations

import itertools

from lxtop.looks import coffee as look_coffee
from lxtop.looks.theme import FX_DIM, FX_HEAD, FX_MID, TONES
from tests.support.backdrops import backdrop_of

H, W = 60, 213
RIPPLE_CHARS = set("-~()")


def make(seed: int = 1, h: int = H, w: int = W) -> look_coffee.Steam:
    return backdrop_of(look_coffee.THEME, look_coffee.Steam, seed, h, w)


def ripple_times(steam: look_coffee.Steam, seconds: float = 200.0) -> list[float]:
    return [t / 4 for t in range(int(seconds * 4)) if steam.ripple_at(t / 4) is not None]


def test_wisps_rise_a_row_every_half_second() -> None:
    for offset in range(len(look_coffee.PATTERN)):
        for d in range(20):
            assert look_coffee.wisp_kind(d + 1, 3.5 + 0.5, offset) == look_coffee.wisp_kind(
                d, 3.5, offset
            )


def test_steam_hugs_the_bottom_and_fades_with_height() -> None:
    steam = make()
    steam.motes, steam._ripple = [], None
    steam.ripple_at = lambda now: None  # type: ignore[method-assign]
    frame = [c for t in range(40) for c in steam.frame(t * 0.4)]
    assert min(y for y, *_ in frame) >= H - look_coffee.PLUME_HEIGHT
    low = {tone for y, _, _, tone in frame if y >= H - 4}
    high = {tone for y, _, _, tone in frame if y < H - 12}
    assert FX_MID in low and high == {FX_DIM}
    assert {c for _, _, c, _ in frame} <= set("(~)/\\'.")


def test_a_plume_leans_and_curls_smoothly() -> None:
    spot = look_coffee.Spot(100, 0.5, 0)
    for t in range(0, 60, 3):
        path = [look_coffee.sway(spot, d, t) for d in range(16)]
        assert max(abs(b - a) for a, b in itertools.pairwise(path)) < 2.0
        assert max(path) - min(path) < 9
    columns = {round(look_coffee.sway(spot, 12, t * 0.25)) for t in range(80)}
    assert len(columns) >= 4


def test_the_ripple_is_rare_bounded_and_spreads() -> None:
    steam = make(3)
    times = ripple_times(steam)
    assert times, "one shows within 200 s"
    assert len(times) / 4 < 0.4 * 200, "rare"
    for t in times:
        y, x, rel = steam.ripple_at(t)  # type: ignore[misc]
        assert 0 <= rel < look_coffee.RIPPLE_LEN and 0 <= y < H and 0 <= x < W
    # At most one ripple per window, and it never outlives its length.
    windows: dict[int, list[float]] = {}
    for t in times:
        windows.setdefault(int(t // look_coffee.RIPPLE_EVERY), []).append(t)
    assert all(max(v) - min(v) < look_coffee.RIPPLE_LEN for v in windows.values())


def test_the_ripple_grows_then_dies_out() -> None:
    steam = make(3)
    steam.motes, steam.spots = [], []
    start = ripple_times(steam)[0]
    # The ripple's first moment may fall a quarter second after it begins.
    spans = []
    for dt in (3.0, 5.0, 7.0):
        cells = steam.frame(start + dt)
        assert cells and all(c in RIPPLE_CHARS for _, _, c, _ in cells)
        xs = [x for _, x, *_ in cells]
        spans.append(max(xs) - min(xs))
    assert spans[0] < spans[1] < spans[2]
    assert steam.frame(start + look_coffee.RIPPLE_LEN + 1.0) == []
    assert max(len(steam.frame(start + t * 0.25)) for t in range(40)) < 0.02 * H * W
    tones = {tone for t in range(40) for *_, tone in steam.frame(start + t * 0.25)}
    assert tones <= set(TONES) and FX_HEAD in tones


def test_motes_drift_up_slowly() -> None:
    steam = make()
    steam.ripple_at = lambda now: None  # type: ignore[method-assign]
    steam.spots = []
    a = steam.frame(10.0)
    b = steam.frame(10.2)
    assert a and {c for _, _, c, _ in a} <= set(".'") and {t for *_, t in a} == {FX_DIM}
    assert len(a) <= len(steam.motes)
    assert a != b


def test_the_steam_is_sparse() -> None:
    steam = make()
    for t in range(0, 400):
        assert len(steam.frame(t * 0.5)) < 0.05 * H * W


def test_works_at_any_size_and_after_a_resize() -> None:
    steam = make(1, 1, 1)
    for t in range(60):
        assert all(y == 0 and x == 0 for y, x, _, _ in steam.frame(t * 3.1))
    for h, w in ((1, 50), (50, 1), (3, 9), (60, 213), (1, 1)):
        steam.resize(h, w)
        for t in range(80):
            frame = steam.frame(10 + t * 2.7)
            assert all(0 <= y < h and 0 <= x < w and tone in TONES for y, x, _, tone in frame)


def test_frames_are_deterministic_for_a_seed() -> None:
    a, b = make(7), make(7)
    times = [t * 1.3 for t in range(120)]
    assert [a.frame(t) for t in times] == [b.frame(t) for t in times]
    assert ripple_times(make(7)) != ripple_times(make(8))
