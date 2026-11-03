"""The Tracker look: pings that quicken as blips drift in, a rare swarm, sparse and safe."""

from __future__ import annotations

import math
import random

from lxtop.looks.theme import FX_HEAD
from lxtop.looks.tracker import EPOCH, FAST, SLOW, Tracker

RING = set("-|/\\")


def grid(seed: int = 1, h: int = 60, w: int = 213) -> Tracker:
    t = Tracker(random.Random(seed))
    t.resize(h, w)
    return t


def swarm_scan(t: Tracker) -> int:
    return next(i for i in range(500) if t.scan(i).swarm)


def test_the_ping_rate_climbs_as_blips_close_in_then_resets() -> None:
    t = grid()
    peak = t.scan(0).peak
    rates = [t.clock(peak * f)[3] for f in (0.0, 0.25, 0.5, 0.75, 0.99)]
    assert rates == sorted(rates) and rates[0] == SLOW and rates[-1] > 0.9 * FAST
    assert t.clock(peak + 0.5)[3] == SLOW
    assert t.clock(EPOCH + 0.01)[2] < 0.05  # a new scan starts a fresh ring


def test_the_ring_grows_from_the_fixed_point() -> None:
    t = grid()
    assert (t.cy, t.cx) == (int(60 * 0.8), 213 // 2)
    cells = [(y, x) for y, x, c, _ in t.frame(1.5) if c in RING]
    assert cells
    left = [x for _, x in cells if x < t.cx]
    right = [x for _, x in cells if x >= t.cx]
    assert abs(len(left) - len(right)) <= 12


def test_blips_drift_toward_the_centre_and_end_in_a_burst() -> None:
    t = grid(4)
    b = t.scan(0).blips[0]
    mid = (b.born + b.arrives) / 2
    far = math.hypot(*(t.where(b, b.born + 0.1) or (9, 9))[:2])
    near = math.hypot(*(t.where(b, mid) or (9, 9))[:2])
    late = math.hypot(*(t.where(b, b.arrives - 0.1) or (9, 9))[:2])
    assert far > near > late
    assert t.where(b, b.arrives) is None
    sparks = [c for y, x, c, _ in t.frame(b.arrives + 0.1) if c == "*"]
    assert sparks


def test_a_swarm_is_rare_and_shows_several_blips_at_once_and_is_bounded() -> None:
    t = grid(3)
    scans = [t.scan(i) for i in range(400)]
    swarms = [s for s in scans if s.swarm]
    assert 0.05 < len(swarms) / len(scans) < 0.35
    for s in scans:
        assert 2 <= len(s.blips) <= 12 and s.peak <= 0.93 * EPOCH
        assert (
            5 <= sum(b.swarm for b in s.blips) <= 8
            if s.swarm
            else not any(b.swarm for b in s.blips)
        )
    i = swarm_scan(t)
    born = next(b.born for b in t.scan(i).blips if b.swarm)
    now = i * EPOCH + born + 0.2
    lit = [cell for cell in t.frame(now) if cell[2] == "@" and cell[3] == FX_HEAD]
    assert len(lit) >= 4


def test_sparse_and_cheap_at_monitor_size() -> None:
    t = grid()
    worst = 0
    for step in range(0, 1400):
        worst = max(worst, len(t.frame(step * 0.1)))
    assert worst < 0.1 * 60 * 213
    t = grid(3)
    i = swarm_scan(t)
    for step in range(60):
        assert len(t.frame(i * EPOCH + 9 + step * 0.1)) < 0.1 * 60 * 213


def test_tiny_and_resized_screens() -> None:
    t = Tracker(random.Random(2))
    for h, w in ((1, 1), (1, 40), (5, 1), (30, 80), (2, 2), (60, 213)):
        t.resize(h, w)
        for step in range(0, 400):
            assert all(0 <= y < h and 0 <= x < w for y, x, _, _ in t.frame(step * 0.9))


def test_no_digits_and_ascii_only() -> None:
    t = grid()
    chars = {c for s in range(0, 900) for _, _, c, _ in t.frame(s * 0.4)}
    assert chars and all(" " <= c <= "~" and not c.isdigit() for c in chars)


def test_the_same_seed_gives_the_same_frames() -> None:
    a, b = grid(9), grid(9)
    assert [a.frame(s * 0.7) for s in range(60)] == [b.frame(s * 0.7) for s in range(60)]
    assert [a.frame(s * 0.7) for s in range(60)] != [grid(10).frame(s * 0.7) for s in range(60)]
