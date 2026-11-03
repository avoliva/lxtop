"""The Aquarium look: fish swim along their rows, bubbles rise, weed sways, a crab and a big
fish visit now and then."""

from __future__ import annotations

from lxtop.looks import aquarium as look_aquarium
from lxtop.looks.theme import TONES
from tests.support.backdrops import backdrop_of

H, W = 60, 213


def make(seed: int = 1, h: int = H, w: int = W) -> look_aquarium.Tank:
    return backdrop_of(look_aquarium.THEME, look_aquarium.Tank, seed, h, w)


def test_fish_swim_along_their_row_and_keep_their_shape() -> None:
    tank = make()
    tank.frame(0.0)
    fish = tank.fish[0]
    fish.x, fish.heading, fish.big, fish.turn_in = 50.0, 1, False, 1e9
    row, x0 = fish.row, fish.x
    tank.frame(1.0)
    assert fish.row == row and fish.x > x0
    shape = fish.shape()
    cells = {(y, x): c for y, x, c, _ in tank.frame(1.0 + 1e-9)}
    left = int(fish.x)
    assert "".join(cells.get((row, left + i), "?") for i in range(len(shape))) == shape


def test_fish_face_the_way_they_swim_and_turn_round_now_and_then() -> None:
    tank = make()
    tank.frame(0.0)
    fish = tank.fish[0]
    fish.x, fish.heading, fish.big, fish.turn_in = 50.0, 1, True, 0.5
    assert fish.shape() == look_aquarium.BIG_RIGHT
    tank.frame(1.0)
    assert fish.heading == -1 and fish.shape() == look_aquarium.BIG_LEFT
    assert fish.turn_in > 5


def test_a_fish_that_leaves_the_tank_comes_back_in_from_the_other_side() -> None:
    tank = make(2)
    tank.frame(0.0)
    tank.fish = tank.fish[:1]
    fish = tank.fish[0]
    fish.x, fish.heading, fish.turn_in = float(W) - 0.5, 1, 1e9
    tank.frame(1.0)
    assert tank.fish[0].x < 0


def test_bubbles_rise_and_come_back_at_the_bottom() -> None:
    tank = make()
    tank.frame(0.0)
    bubble = tank.bubbles[0]
    bubble.y, bubble.speed = 30.0, 2.0
    tank.frame(1.0)
    assert bubble.y == 28.0
    bubble.y = -0.9
    tank.frame(2.0)
    assert tank.bubbles[0].y >= H - 1


def test_the_tank_is_sparse() -> None:
    tank = make()
    for t in range(40):
        assert len(tank.frame(t * 0.5)) < 0.05 * H * W


def test_works_at_any_size_and_after_a_resize() -> None:
    tank = make(1, 1, 1)
    for t in range(20):
        assert all(y == 0 and x == 0 for y, x, _, _ in tank.frame(t * 0.3))
    for h, w in ((1, 50), (50, 1), (3, 9), (60, 213)):
        tank.resize(h, w)
        for t in range(20):
            frame = tank.frame(10 + t * 0.3)
            assert all(0 <= y < h and 0 <= x < w and tone in TONES for y, x, _, tone in frame)


def test_frames_are_deterministic_for_a_seed() -> None:
    a, b = make(7), make(7)
    assert [a.frame(t * 0.3) for t in range(30)] == [b.frame(t * 0.3) for t in range(30)]


def cells_of(tank: look_aquarium.Tank, now: float) -> dict[tuple[int, int], str]:
    return {(y, x): c for y, x, c, _ in tank.frame(now)}


def test_seaweed_rises_from_the_bottom_row_and_sways() -> None:
    tank = make(3)
    tank.fish, tank.bubbles = [], []
    tank.next_crab = tank.next_whale = 1e9
    weed = tank.weeds[0]
    seen = set()
    for t in range(40):
        cells = cells_of(tank, t * 0.4)
        assert (H - 1, weed.col) in cells
        seen.add(cells[(H - 2, weed.col)] if weed.height > 1 else "")
    assert len(tank.weeds) > 10
    assert len(seen - {""}) >= 2, "the strand changes its lean"


def test_the_crab_scuttles_along_the_floor_and_leaves() -> None:
    tank = make(4)
    tank.fish, tank.bubbles, tank.weeds = [], [], []
    tank.next_whale = 1e9
    tank.next_crab = 0.5
    tank.frame(0.0)
    xs: list[float] = []
    legs: set[str | None] = set()
    for t in range(1, 1200):
        frame = tank.frame(t * 0.1)
        if xs and tank.crab is None:
            break
        floor = {x: c for y, x, c, _ in frame if y == H - 1}
        if tank.crab:
            xs.append(tank.crab.x)
            legs.add(floor.get(int(tank.crab.x) + 1))
    assert xs and max(xs) - min(xs) > 20 and "o" in legs
    assert len(legs - {None}) >= 1
    assert tank.crab is None, "gone once it has walked off"


def test_the_big_fish_is_rare_slow_and_one_at_a_time() -> None:
    tank = make(5)
    tank.fish, tank.bubbles, tank.weeds = [], [], []
    tank.next_crab = 1e9
    tank.next_whale = 1.0
    tank.rng.seed(5)
    tank.frame(0.0)
    appeared = 0
    for t in range(1, 1500):
        tank.frame(t * 0.5)
        if tank.whale:
            appeared += 1
            assert len(tank.whale.shape()) == len(look_aquarium.WHALE_RIGHT)
    assert 0 < appeared < 1500 * 0.5, "visits, but most of the time the tank is calm"


def test_still_sparse_with_the_visitors_and_weed() -> None:
    tank = make(6)
    tank.crab = look_aquarium.Crab(100.0, 1)
    tank.whale = look_aquarium.Whale(20, 100.0, 1)
    for t in range(40):
        assert len(tank.frame(t * 0.5)) < 0.1 * H * W


def test_the_tank_survives_a_resize_with_visitors_present() -> None:
    tank = make(7)
    tank.crab = look_aquarium.Crab(100.0, 1)
    tank.whale = look_aquarium.Whale(40, 100.0, -1)
    tank.resize(5, 12)
    assert tank.crab is None and tank.whale is None
    for t in range(30):
        assert all(0 <= y < 5 and 0 <= x < 12 for y, x, _, _ in tank.frame(t * 0.5))
