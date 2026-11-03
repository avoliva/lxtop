"""The Matrix theme: colours, the rain, the scramble, and what the screen lets them draw."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from lxtop.looks import matrix as look_matrix
from lxtop.looks import theme
from lxtop.looks.matrix import THEME as MATRIX
from lxtop.viewer.screen import RED, YELLOW

FIXTURE = Path(__file__).parents[1] / "fixtures" / "terminus-chars.txt"
LOOKS = [t for t in theme.THEMES.values() if t.name != "default"]


@pytest.mark.parametrize("colours", (256, 8))
def test_the_default_look_leaves_the_background_alone(colours: int) -> None:
    assert {bg for _, bg in theme.pairs(theme.DEFAULT, colours).values()} == {-1}


@pytest.mark.parametrize(("colours", "background"), ((256, 16), (8, 0)))
def test_matrix_paints_every_base_pair_on_its_background(colours: int, background: int) -> None:
    base = {p: v for p, v in theme.pairs(MATRIX, colours).items() if p <= theme.BACKGROUND}
    assert {bg for _, bg in base.values()} == {background}


@pytest.mark.parametrize("colours", (256, 8))
@pytest.mark.parametrize("warning", (RED, YELLOW))
def test_matrix_warnings_differ_from_its_green(colours: int, warning: int) -> None:
    matrix = theme.pairs(MATRIX, colours)
    assert matrix[warning][0] != matrix[1][0]  # not the green everything else is


def test_matrix_eight_colour_warnings_are_red_and_yellow() -> None:
    eight = theme.pairs(MATRIX, 8)
    assert eight[RED][0] == theme.RED_8
    assert eight[YELLOW][0] == theme.YELLOW_8


def test_next_theme_visits_every_look_and_comes_back() -> None:
    seen, t = [], theme.DEFAULT
    for _ in range(len(theme.THEMES)):
        seen.append(t.name)
        t = theme.next_theme(t)
    assert t is theme.DEFAULT and sorted(seen) == sorted(theme.THEMES)


def test_default_is_the_first_look() -> None:
    assert next(iter(theme.THEMES)) == "default"


def test_matrix_is_a_registered_look() -> None:
    assert "matrix" in theme.THEMES


def test_scramble_keeps_length_and_spaces_and_fades_to_nothing() -> None:
    rng = random.Random(1)
    text = "CPU 42%  hosts 3"
    assert theme.scramble(text, 0, rng, "x") == text
    full = theme.scramble(text, 1, rng, "x")
    assert len(full) == len(text)
    assert all((a == " ") == (b == " ") for a, b in zip(text, full, strict=True))
    assert all(b == "x" for b in full if b != " ")


def test_rain_stays_on_screen_and_uses_only_its_characters() -> None:
    rain = look_matrix.Rain("01", random.Random(7))
    rain.resize(20, 30)
    seen = []
    for step in range(60):
        seen += rain.frame(step * 0.1)
    assert seen, "some rain falls within 6 seconds"
    assert all(0 <= y < 20 and 0 <= x < 30 for y, x, _, _ in seen)
    assert {c for _, _, c, _ in seen} <= set("01")
    assert {tone for *_, tone in seen} <= set(theme.TONES)
    rain.resize(5, 4)
    assert all(0 <= y < 5 and 0 <= x < 4 for y, x, _, _ in rain.frame(7.0))


def test_the_console_gets_rain_and_frames_its_font_has() -> None:
    font = set(FIXTURE.read_text().strip())
    shown = set(look_matrix.rain_chars(console=True) + MATRIX.frame + "█▒░")
    assert {c for c in shown if ord(c) > 0x7E} <= font
    assert set(look_matrix.KATAKANA) & set(look_matrix.rain_chars(console=False))
    for console in (True, False):
        assert not set(look_matrix.rain_chars(console)) & set("0123456789")  # never reads as data


def test_glass_pairs_tint_every_colour_only_with_256_colours() -> None:
    rich = theme.pairs(MATRIX, 256)
    for pair in range(1, theme.BACKGROUND + 1):
        assert rich[theme.GLASS + pair] == (rich[pair][0], MATRIX.glass)
    assert rich[theme.FX_GLASS][1] == MATRIX.glass
    assert theme.GLASS + 1 not in theme.pairs(MATRIX, 8)  # the console gets no tint
    assert theme.GLASS + 1 not in theme.pairs(theme.DEFAULT, 256)
    assert theme.tinted(MATRIX, 256) and not theme.tinted(MATRIX, 8)


def test_the_console_gets_glass_through_its_own_palette() -> None:
    console = theme.pairs(MATRIX, 8, console=True)
    assert console[theme.GLASS + 1] == (theme.GREEN_8, theme.BLUE_8)  # green on the glass slot
    assert console[theme.FX_GLASS][1] == theme.BLUE_8
    assert theme.tinted(MATRIX, 8, console=True)
    assert not theme.tinted(MATRIX, 8)  # an 8-colour terminal that is not the console
    assert not theme.tinted(theme.DEFAULT, 8, console=True)
    slots = dict(MATRIX.console_palette)
    assert theme.BLUE_8 in slots and 8 in slots  # the glass, and dim text (the rain behind it)
    assert theme.RED_8 not in slots and theme.YELLOW_8 not in slots  # warnings stay as they are


def test_rain_levels_thin_the_rain_and_thin_it_more_behind_glass() -> None:
    def columns(level: str, glass: bool) -> int:
        return sum(theme.fx_falls(level, x, glass) for x in range(100))

    assert columns("full", False) == 100 and columns("full", True) == 50
    assert columns("light", False) == 50 and columns("light", True) == 25
    assert columns("off", False) == columns("off", True) == 0
    assert theme.next_fx("light") == "full" and theme.next_fx("off") == "light"


def test_the_rain_is_darker_than_any_text_in_matrix() -> None:
    rich = theme.pairs(MATRIX, 256)
    rain = {rich[p][0] for p in (*theme.TONES, theme.FX_GLASS, theme.FX_GLASS_HEAD)}
    assert rain <= {22, 28}  # the two darkest greens in the 256-colour cube
    assert rich[6][0] not in rain  # quiet text (BLUE) is brighter than the brightest rain


@pytest.mark.parametrize("colours", (256, 8))
@pytest.mark.parametrize("look", LOOKS, ids=lambda t: t.name)
def test_the_background_pair_takes_the_plain_text_colour(look: theme.Theme, colours: int) -> None:
    got = theme.pairs(look, colours, console=colours == 8)
    assert got[theme.BACKGROUND][0] == got[7][0]


@pytest.mark.parametrize("colours", (256, 8))
@pytest.mark.parametrize("look", LOOKS, ids=lambda t: t.name)
def test_the_glass_pair_takes_the_plain_text_colour(look: theme.Theme, colours: int) -> None:
    got = theme.pairs(look, colours, console=colours == 8)
    assert got[theme.GLASS][0] == got[7][0]
