"""The Tron look: two teams of light cycles, glowing walls, derez bursts, a rare sweep."""

from __future__ import annotations

import itertools
import random

import pytest

from lxtop.looks import tron as look_tron
from lxtop.looks.theme import FX_DIM, FX_HEAD, FX_MID, Cell
from lxtop.looks.tron import HEAVY, LIGHT, PLAIN, SHARDS, Cycles

CONNECTORS = {
    "━": {(0, -1), (0, 1)},
    "┃": {(-1, 0), (1, 0)},
    "┏": {(0, 1), (1, 0)},
    "┓": {(0, -1), (1, 0)},
    "┗": {(0, 1), (-1, 0)},
    "┛": {(0, -1), (-1, 0)},
}
TO_HEAVY = dict(zip(LIGHT.values(), HEAVY.values(), strict=True))
SIZES = [(1, 1), (1, 40), (40, 1), (3, 5), (24, 80), (60, 213)]


def single(seed: int, console: bool = False) -> Cycles:
    grid = Cycles(console, random.Random(seed), count=1)
    grid.resize(60, 213)
    return grid


def walls(grid: Cycles) -> list[Cell]:
    return [c for cyc in grid.cycles for c in cyc.cells(grid.glyphs, grid.light)]


Frame = tuple[list[tuple[int, int]], dict[tuple[int, int], str]]
DIRECTIONS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def play(seed: int) -> list[Frame]:
    """Per frame of one lone cycle: its trail, and the lit cells (heavy glyph by position)."""
    grid = single(seed)
    frames: list[Frame] = []
    for step in range(400):
        grid.frame(step * 0.05)
        lit = {(y, x): TO_HEAVY.get(c, c) for y, x, c, _ in walls(grid)}
        frames.append((list(grid.cycles[0].trail), lit))
    return frames


def lit_neighbours(lit: dict[tuple[int, int], str], cell: tuple[int, int]) -> set[tuple[int, int]]:
    y, x = cell
    return {d for d in DIRECTIONS if (y + d[0], x + d[1]) in lit}


@pytest.mark.parametrize("seed", range(6))
def test_a_trail_moves_one_cell_at_a_time(seed: int) -> None:
    frames = play(seed)
    pairs = [(a, b) for trail, _ in frames for a, b in itertools.pairwise(trail)]
    assert len({tuple(trail) for trail, _ in frames}) > 100, "the cycle keeps moving"
    assert pairs
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in pairs)


@pytest.mark.parametrize("seed", range(6))
def test_every_trail_cell_touches_another(seed: int) -> None:
    multi = [lit for _, lit in play(seed) if len(lit) > 1]
    assert len({cell for lit in multi for cell in lit}) > 100, "the cycle covers ground"
    assert all(lit_neighbours(lit, cell) for lit in multi for cell in lit)


@pytest.mark.parametrize("seed", range(6))
def test_straight_pieces_lie_along_their_axis(seed: int) -> None:
    multi = [lit for _, lit in play(seed) if len(lit) > 1]
    straight = [
        (cell, char, lit_neighbours(lit, cell))
        for lit in multi
        for cell, char in lit.items()
        if char in "━┃"
    ]
    assert len({cell for cell, _, _ in straight}) > 100, "straight runs along a long path"
    assert all(near & CONNECTORS[char] for _, char, near in straight)


@pytest.mark.parametrize("seed", range(6))
def test_corner_pieces_join_a_horizontal_and_a_vertical_neighbour(seed: int) -> None:
    multi = [lit for _, lit in play(seed) if len(lit) > 1]
    corners = [
        (cell, char, lit_neighbours(lit, cell))
        for lit in multi
        for cell, char in lit.items()
        if char not in "━┃"
    ]
    assert len({cell for cell, _, _ in corners}) > 10, "the cycle turns"
    assert all(CONNECTORS[char] <= near for _, char, near in corners)


def test_the_head_glows_and_the_cycle_moves() -> None:
    grid = single(2)
    heads = []
    for step in range(40):
        grid.frame(step * 0.1)
        cyc = grid.cycles[0]
        if cyc.dead:
            continue
        bright = [c for c in walls(grid) if c[3] == FX_HEAD]
        assert 1 <= len(bright) <= look_tron.BRIGHT
        heads.append(cyc.trail[-1])
    assert len(set(heads)) > 8, "the cycle covers new cells over time"


def test_old_walls_thin_to_light_lines() -> None:
    grid = single(5)
    for step in range(60):
        grid.frame(step * 0.1)
    chars = {c for _, _, c, _ in walls(grid)}
    assert chars & set(LIGHT.values()) and chars & set(HEAVY.values())


def test_teams_differ_by_tone() -> None:
    grid = Cycles(False, random.Random(1), count=2)
    grid.resize(60, 213)
    assert {cyc.tone for cyc in grid.cycles} == {FX_DIM, FX_MID}


def test_old_trail_disappears_and_length_is_bounded() -> None:
    grid = single(4)
    first = {(y, x) for y, x, _, _ in walls(grid)}
    grid.frame(0.0)
    longest = 0
    for step in range(1, 300):
        grid.frame(step * 0.1)
        longest = max(longest, len(walls(grid)))
    assert longest <= 60
    assert not first & {(y, x) for y, x, _, _ in walls(grid)}, "the first trail has faded away"


def test_a_cycle_dies_and_a_new_one_starts() -> None:
    grid = single(1)
    for step in range(600):
        grid.frame(step * 0.1)
    assert grid.cycles[0].trail, "respawned cycles keep the grid alive"


def crowded(seed: int) -> Cycles:
    grid = Cycles(False, random.Random(seed), count=8)
    grid.resize(12, 30)
    return grid


def test_a_crash_bursts_into_bounded_fading_fragments_and_the_cycle_respawns() -> None:
    grid = crowded(3)
    seen_burst = respawned = False
    most = 0
    deaths: dict[int, bool] = {}
    for step in range(1200):
        now = step * 0.1
        grid.frame(now)
        most = max(most, len(grid.fragments))
        seen_burst |= bool(grid.fragments)
        for i, cyc in enumerate(grid.cycles):
            if deaths.get(i) and not cyc.dead:
                respawned = True
            deaths[i] = cyc.dead
        assert all(now - f.t0 < look_tron.FRAGMENT_SECONDS for f in grid.fragments)
    assert seen_burst, "cycles hit walls and derez"
    assert respawned
    assert most <= look_tron.MAX_FRAGMENTS
    grid.cycles = []
    grid.frame(1200 * 0.1 + 5.0)
    assert not grid.fragments, "fragments fade away"


def test_fragments_use_shard_glyphs_and_never_leave_the_screen() -> None:
    for console in (False, True):
        grid = Cycles(console, random.Random(7), count=8)
        grid.resize(12, 30)
        shards = set(SHARDS[1 if console else 0])
        found = set()
        for step in range(800):
            for y, x, c, _ in grid.frame(step * 0.1):
                assert 0 <= y < 12 and 0 <= x < 30
                found.add(c)
        assert found & shards


def test_the_rare_sweep_happens_and_is_short() -> None:
    grid = Cycles(False, random.Random(5), count=1)
    grid.resize(24, 80)
    swept = most = 0
    for step in range(3000):  # five minutes
        grid.frame(step * 0.1)
        if grid.pulse is not None:
            swept += 1
            most = max(most, len(grid.pulse.cells(step * 0.1, LIGHT) or []))
    assert 0 < swept < 3000 * 0.2, "it happens, and is rare"
    assert most <= look_tron.PULSE_LENGTH


def test_it_is_sparse_at_monitor_size() -> None:
    grid = Cycles(False, random.Random(9))
    grid.resize(60, 213)
    worst = 0
    for step in range(600):
        worst = max(worst, len(grid.frame(step * 0.1)))
    assert 0 < worst < 60 * 213 * 0.10


@pytest.mark.parametrize("size", SIZES)
def test_any_size_stays_on_screen_and_has_no_duplicates(size: tuple[int, int]) -> None:
    h, w = size
    grid = Cycles(False, random.Random(2))
    grid.resize(h, w)
    for step in range(300):
        cells = grid.frame(step * 0.1)
        assert all(0 <= y < h and 0 <= x < w for y, x, _, _ in cells)
        assert len({(y, x) for y, x, _, _ in cells}) == len(cells)


def test_resize_midway_and_to_nothing_are_safe() -> None:
    grid = Cycles(False, random.Random(2))
    for i, (h, w) in enumerate([(30, 100), (1, 1), (0, 0), (5, 200), (60, 213), (2, 3)]):
        grid.resize(h, w)
        for step in range(40):
            cells = grid.frame(i * 10 + step * 0.1)
            assert all(0 <= y < h and 0 <= x < w for y, x, _, _ in cells)


def test_the_same_seed_gives_the_same_frames() -> None:
    def run(seed: int) -> list[list[Cell]]:
        grid = Cycles(False, random.Random(seed))
        grid.resize(24, 80)
        return [sorted(grid.frame(s * 0.1)) for s in range(300)]

    assert run(4) == run(4)
    assert run(4) != run(5)


def test_console_effects_use_only_plain_characters() -> None:
    grid = Cycles(True, random.Random(3), count=6)
    grid.resize(20, 60)
    chars = {c for step in range(600) for _, _, c, _ in grid.frame(step * 0.1)}
    assert chars <= set(PLAIN.values()) | set(SHARDS[1]) | {"."}
    assert chars - {"+"}, "straight pieces appear"


def test_the_theme_exports_a_factory() -> None:
    assert look_tron.THEME.name == "tron"
    assert look_tron.THEME.backdrop is look_tron.make
    assert set(HEAVY.values()) == set("━┃┏┓┗┛")
