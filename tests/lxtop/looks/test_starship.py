"""The Starship look's indicator lights: sparse blocks that blink in slow patterns."""

from __future__ import annotations

import itertools
import random

from lxtop.looks.starship import RIPPLE_SLOT, SCAN_SPEED, Lights


def panel(seed: int = 1, h: int = 60, w: int = 213) -> Lights:
    p = Lights(random.Random(seed))
    p.resize(h, w)
    return p


def test_lights_sit_in_a_few_rows() -> None:
    p = panel()
    rows = {y for y, *_ in p.frame(0.0)}
    assert 2 <= len(rows) <= 7


def test_lights_blink_on_and_off_over_time() -> None:
    p = panel()
    states = [tuple(p.is_on(light, t * 0.1) for light in p.lights) for t in range(200)]
    assert len(set(states)) > 10
    for i in range(len(p.lights)):
        column = {s[i] for s in states}
        assert column == {True, False}, "every light blinks"


def test_the_blinking_is_slow() -> None:
    p = panel()
    changed = []
    for t in range(100):
        a = [p.is_on(light, t * 0.1) for light in p.lights]
        b = [p.is_on(light, (t + 1) * 0.1) for light in p.lights]
        changed.append(sum(x != y for x, y in zip(a, b, strict=False)) / len(a))
    assert sum(changed) / len(changed) < 0.25


def test_sparse_at_monitor_size() -> None:
    p = panel()
    for step in range(60):
        assert len(p.frame(step * 0.5)) < 0.1 * 60 * 213


def test_tiny_and_resized_screens() -> None:
    p = Lights(random.Random(2))
    for h, w in ((1, 1), (1, 40), (5, 1), (30, 80), (2, 2)):
        p.resize(h, w)
        for step in range(30):
            assert all(0 <= y < h and 0 <= x < w for y, x, _, _ in p.frame(step * 0.2 + 5))


def test_the_same_seed_gives_the_same_frames() -> None:
    a, b = panel(9), panel(9)
    assert [a.frame(t * 0.3) for t in range(20)] == [b.frame(t * 0.3) for t in range(20)]


def scan_heads(p: Lights, times: list[float]) -> list[int]:
    return [next(x for y, x, c, _ in p.frame(t) if y == p.scan_row and c == "■") for t in times]


def test_the_scanner_sweeps_slowly_to_and_fro() -> None:
    p = panel()
    heads = scan_heads(p, [t * 0.5 for t in range(120)])
    assert max(heads) > 150 and min(heads) < 20, "it crosses the screen"
    steps = [abs(b - a) for a, b in itertools.pairwise(heads)]
    assert max(steps) <= SCAN_SPEED * 0.5 + 1
    assert any(b < a for a, b in itertools.pairwise(heads)), "and comes back"


def ripple_times(p: Lights) -> list[float]:
    return [t * 0.25 for t in range(int(RIPPLE_SLOT * 12 / 0.25))]


def test_an_alert_ripple_happens_rarely_and_runs_along_one_row() -> None:
    p = panel()
    times = ripple_times(p)
    active = [t for t in times if p.ripple(t)]
    assert active, "it happens within a few minutes"
    assert len(active) < 0.3 * len(times), "but rarely"
    for t in active:
        cells = p.ripple(t)
        assert len({y for y, *_ in cells}) == 1
        assert len(cells) <= 213 // 2 + 1


def test_the_ripple_front_moves_along_the_row() -> None:
    p = panel()
    t0 = next(t for t in ripple_times(p) if p.ripple(t))
    a = {x for _, x, _, _ in p.ripple(t0 + 0.5)}
    b = {x for _, x, _, _ in p.ripple(t0 + 1.0)}
    assert a and b and a != b
    assert max(a) != max(b) or min(a) != min(b)


def test_ripple_stays_sparse_and_bounded_in_time() -> None:
    p = panel()
    for t in ripple_times(p):
        assert len(p.frame(t)) < 0.1 * 60 * 213


def test_one_by_one_has_no_scanner_and_does_not_fail() -> None:
    p = panel(4, 1, 1)
    assert p.scan_row == -1
    for t in range(0, 600, 7):
        assert all(y == 0 and x == 0 for y, x, _, _ in p.frame(float(t)))
