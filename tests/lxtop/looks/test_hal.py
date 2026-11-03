"""The Hal look: a calm starfield with one pulsing eye."""

from __future__ import annotations

import itertools

from lxtop.looks import hal as look_hal
from lxtop.looks.theme import FX_HEAD, FX_MID, TONES
from tests.support.backdrops import backdrop_of

H, W = 60, 213


def make(seed: int = 1) -> look_hal.Stars:
    return backdrop_of(look_hal.THEME, look_hal.Stars, seed, H, W)


def eye_cell(stars: look_hal.Stars, now: float) -> tuple[int, int, str, int]:
    cells = [c for c in stars.frame(now) if c[2] == look_hal.EYE]
    assert len(cells) == 1
    return cells[0]


def test_the_eye_pulses_in_place() -> None:
    stars = make()
    seen = [eye_cell(stars, t * 0.25) for t in range(24)]  # six seconds
    assert len({(y, x) for y, x, _, _ in seen}) == 1
    tones = {tone for *_, tone in seen}
    assert len(tones) >= 2 and FX_HEAD in tones
    assert tones <= set(TONES)


def test_the_sky_is_sparse() -> None:
    stars = make()
    for t in range(20):
        assert len(stars.frame(t * 0.5)) < 0.05 * H * W


def test_the_stars_never_use_the_head_tone() -> None:
    stars = make()
    seen = 0
    for t in range(20):
        tones = [
            tone
            for _, _, c, tone in stars.frame(t * 0.5)
            if c not in (look_hal.EYE, look_hal.GLOW[0])
        ]
        seen += len(tones)
        assert all(tone != FX_HEAD for tone in tones)
    assert seen > 0, "stars are drawn besides the eye"


def test_the_look_is_calm() -> None:
    assert look_hal.THEME.glitch is False
    assert 150 <= look_hal.THEME.tick_ms <= 250


def test_frames_are_deterministic_for_a_seed() -> None:
    a, b = make(7), make(7)
    assert [a.frame(t * 0.3) for t in range(10)] == [b.frame(t * 0.3) for t in range(10)]


def glow_cells(stars: look_hal.Stars, now: float) -> list[tuple[int, int, str, int]]:
    return [c for c in stars.frame(now) if c[2] in look_hal.GLOW[:2] and near_eye(stars, c)]


def near_eye(stars: look_hal.Stars, cell: tuple[int, int, str, int]) -> bool:
    return abs(cell[0] - stars.eye[0]) <= 4 and abs(cell[1] - stars.eye[1]) <= 8


def test_the_eye_glow_swells_and_fades() -> None:
    stars = make()
    full = look_hal.EYE_SECONDS / 2
    assert len(glow_cells(stars, 0.0)) == 0
    assert len(glow_cells(stars, full)) > 10
    ring_chars = {c for _, _, c, _ in glow_cells(stars, full)}
    assert ring_chars == set(look_hal.GLOW[:2])
    sizes = [len(glow_cells(stars, t * 0.25)) for t in range(24)]
    assert len(set(sizes)) >= 3


def test_the_glow_gets_quieter_away_from_the_eye() -> None:
    stars = make()
    cells = glow_cells(stars, look_hal.EYE_SECONDS / 2)
    tone: dict[str, set[int]] = {}
    for _, _, c, t in cells:
        tone.setdefault(c, set()).add(t)
    assert tone[look_hal.GLOW[0]] == {FX_HEAD}
    assert tone[look_hal.GLOW[1]] == {FX_MID}


def shots(stars: look_hal.Stars, end: float = 400.0) -> list[tuple[float, int]]:
    out = []
    t = 0.0
    while t < end:
        n = len(stars.shooting_star(t))
        if n:
            out.append((t, n))
        t += 0.1
    return out


def test_a_shooting_star_is_rare_and_bounded() -> None:
    stars = make()
    seen = shots(stars)
    assert seen, "one crosses within 400 seconds"
    assert max(n for _, n in seen) <= 7
    assert len(seen) * 0.1 < 400 * 0.1, "on screen less than a tenth of the time"
    for t, _ in seen:
        assert len(stars.frame(t)) < 0.05 * H * W


def test_a_shooting_star_moves_right_and_down() -> None:
    stars = make()
    t0 = shots(stars)[0][0]
    heads = []
    for k in range(4):
        cells = [c for c in stars.shooting_star(t0 + k * 0.2) if c[2] == "*"]
        if cells:
            heads.append(cells[0])
    assert len(heads) >= 2
    assert all(b[1] > a[1] and b[0] >= a[0] for a, b in itertools.pairwise(heads))


def test_tiny_and_resized_screens_are_safe() -> None:
    stars = make()
    for h, w in ((1, 1), (2, 3), (60, 213), (1, 50), (5, 1)):
        stars.resize(h, w)
        for t in range(0, 400, 3):
            frame = stars.frame(t * 0.5)
            assert all(0 <= y < h and 0 <= x < w for y, x, _, _ in frame)
            assert len({(y, x) for y, x, _, _ in frame}) == len(frame)


def test_shooting_stars_follow_the_seed() -> None:
    assert shots(make(3)) == shots(make(3))
    assert shots(make(3)) != shots(make(4))
