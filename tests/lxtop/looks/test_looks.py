"""The rules every look keeps, checked for each `look_*.py` module found.

A new look passes these before it ships: warnings stay recognisable, effects never compete
with text, and everything the console draws exists in its font.
"""

from __future__ import annotations

import pkgutil
import random
import re
import time
from pathlib import Path

import pytest

import lxtop.looks
from lxtop.looks import theme
from lxtop.viewer import font
from lxtop.viewer.screen import BLUE, CYAN, GREEN, MAGENTA, RED, WHITE, YELLOW
from tests.support.colours import contrast, grounds

FIXTURE = Path(__file__).parents[1] / "fixtures" / "terminus-chars.txt"
CONSOLE_FONT = set(FIXTURE.read_text().strip()) | set(font.NEW)
TEXT = (GREEN, CYAN, MAGENTA, BLUE, WHITE)
LOOKS = [t for t in theme.THEMES.values() if t.name != "default"]
MODULES = sorted(m.name for m in pkgutil.iter_modules(lxtop.looks.__path__) if m.name != "theme")


def on_console(chars: str) -> set[str]:
    """The characters the console font lacks."""
    return {c for c in chars if not (" " <= c <= "~") and c not in CONSOLE_FONT}


def test_every_look_module_loads_under_its_own_name() -> None:
    assert MODULES, "at least the Matrix look"
    assert sorted(t.name for t in LOOKS) == MODULES


@pytest.mark.parametrize("look", theme.THEMES.values(), ids=lambda t: t.name)
def test_colours_cover_every_pair_the_viewer_uses(look: theme.Theme) -> None:
    assert set(range(1, 8)) <= set(look.colours)
    for rich, plain in look.colours.values():
        assert 0 <= rich < 256 and 0 <= plain < 8


@pytest.mark.parametrize("look", LOOKS, ids=lambda t: t.name)
def test_a_look_with_effects_defines_their_pairs(look: theme.Theme) -> None:
    assert look.backdrop is not None
    assert {*theme.TONES, theme.FX_GLASS, theme.FX_GLASS_HEAD} <= set(look.colours)


@pytest.mark.parametrize("look", LOOKS, ids=lambda t: t.name)
def test_a_look_with_a_background_defines_the_background_pair(look: theme.Theme) -> None:
    assert look.background >= 0
    assert theme.BACKGROUND in look.colours


@pytest.mark.parametrize("look", theme.THEMES.values(), ids=lambda t: t.name)
def test_warnings_stay_unlike_any_other_text(look: theme.Theme) -> None:
    for colours, console in ((256, False), (8, True), (8, False)):
        fg = {pair: c for pair, (c, _) in theme.pairs(look, colours, console).items()}
        assert fg[RED] != fg[YELLOW]
        assert {fg[RED], fg[YELLOW]}.isdisjoint(fg[p] for p in TEXT), (colours, console)
    assert look.accent in TEXT


@pytest.mark.parametrize("look", LOOKS, ids=lambda t: t.name)
def test_effects_never_share_a_colour_with_text(look: theme.Theme) -> None:
    assert look.backdrop is not None
    fg = {pair: c for pair, (c, _) in theme.pairs(look, 256).items()}
    effects = {fg[p] for p in (*theme.TONES, theme.FX_GLASS, theme.FX_GLASS_HEAD)}
    assert effects.isdisjoint(fg[p] for p in (*TEXT, RED, YELLOW))


@pytest.mark.parametrize("look", LOOKS, ids=lambda t: t.name)
def test_the_console_palette_leaves_black_and_the_warnings_alone(look: theme.Theme) -> None:
    assert look.console_palette, "every look recolours the console"
    for slot, rgb in look.console_palette:
        assert 0 <= slot < 16 and slot not in theme.WARNING_SLOTS
        assert re.fullmatch(r"[0-9a-f]{6}", rgb)
    assert theme.BLUE_8 in dict(look.console_palette), "slot 4 is the console's glass"


@pytest.mark.parametrize("look", LOOKS, ids=lambda t: t.name)
def test_shape(look: theme.Theme) -> None:
    assert len(look.frame) == 6 and 50 <= look.tick_ms <= 1000
    assert look.label and len(look.label) <= 60
    assert all(look.noise) and len(look.boot) <= 5
    assert all(0 < len(line) <= 60 for line in look.boot)


@pytest.mark.parametrize("look", LOOKS, ids=lambda t: t.name)
def test_everything_the_console_draws_is_in_its_font(look: theme.Theme) -> None:
    title = look.title or theme.Title()
    drawn = look.frame + title.left + title.right + title.prompt + title.cursor
    drawn += look.noise[1] + "".join(look.boot)
    assert not on_console(drawn)


@pytest.mark.parametrize("look", LOOKS, ids=lambda t: t.name)
@pytest.mark.parametrize("console", (True, False), ids=("console", "terminal"))
def test_the_backdrop_stays_on_screen_in_effect_tones_without_digits(
    look: theme.Theme, console: bool
) -> None:
    assert look.backdrop is not None
    backdrop = look.backdrop(console, random.Random(3))
    cells = []
    for h, w in ((30, 80), (60, 213), (8, 20)):
        backdrop.resize(h, w)
        for step in range(40):
            frame = backdrop.frame(step * 0.1)
            assert all(0 <= y < h and 0 <= x < w for y, x, _, _ in frame), (h, w)
            cells += frame
    assert cells, "something shows within 4 seconds"
    assert {tone for *_, tone in cells} <= set(theme.TONES)
    chars = "".join(c for _, _, c, _ in cells)
    assert all(len(c) == 1 for _, _, c, _ in cells)
    assert not set(chars) & set("0123456789"), "effects beside a table must not read as data"


def console_cells(look: theme.Theme) -> list[theme.Cell]:
    """Every cell a look's console backdrop draws over three sizes and 4 seconds each."""
    assert look.backdrop is not None
    backdrop = look.backdrop(True, random.Random(3))
    cells: list[theme.Cell] = []
    for h, w in ((30, 80), (60, 213), (8, 20)):
        backdrop.resize(h, w)
        for step in range(40):
            cells += backdrop.frame(step * 0.1)
    return cells


@pytest.mark.parametrize("look", LOOKS, ids=lambda t: t.name)
def test_a_console_backdrop_draws_only_characters_the_console_font_has(look: theme.Theme) -> None:
    cells = console_cells(look)
    assert cells, "something shows within 4 seconds"
    assert not on_console("".join(c for _, _, c, _ in cells))


@pytest.mark.parametrize("look", LOOKS, ids=lambda t: t.name)
def test_the_backdrop_is_cheap_on_the_monitor(look: theme.Theme) -> None:
    assert look.backdrop is not None
    backdrop = look.backdrop(True, random.Random(5))
    backdrop.resize(60, 213)
    passes = []
    for attempt in range(3):
        start = time.perf_counter()
        for step in range(30):
            backdrop.frame((attempt * 30 + step) * 0.1)  # time never runs backwards
        passes.append(time.perf_counter() - start)
    assert min(passes) / 30 < 0.02, "under 20 ms a frame at 213x60"


# ---- readability: WCAG contrast of each colour against the background and the glass ----


@pytest.mark.parametrize("look", LOOKS, ids=lambda t: t.name)
def test_text_is_readable_on_the_background_and_the_glass(look: theme.Theme) -> None:
    fg = {pair: c for pair, (c, _) in theme.pairs(look, 256).items()}
    for ground in grounds(look):
        for pair in (GREEN, CYAN, MAGENTA, WHITE):  # data, labels, secondary, plain text
            assert contrast(fg[pair], ground) >= 4.5, (pair, ground)
        for pair in (BLUE, RED, YELLOW):  # quiet text and frames, the warnings
            assert contrast(fg[pair], ground) >= 3.0, (pair, ground)


@pytest.mark.parametrize("look", LOOKS, ids=lambda t: t.name)
def test_effects_are_quieter_than_the_quietest_text(look: theme.Theme) -> None:
    assert look.backdrop is not None
    fg = {pair: c for pair, (c, _) in theme.pairs(look, 256).items()}
    for ground in grounds(look):
        quietest = min(contrast(fg[p], ground) for p in (*TEXT, RED, YELLOW))
        for pair in (*theme.TONES, theme.FX_GLASS, theme.FX_GLASS_HEAD):
            assert contrast(fg[pair], ground) < quietest, (pair, ground)


@pytest.mark.parametrize("look", LOOKS, ids=lambda t: t.name)
def test_a_meter_character_is_one_cell_and_on_the_console_in_its_font(look: theme.Theme) -> None:
    terminal, console = look.meter_empty
    assert len(terminal) <= 1 and len(console) <= 1
    assert not on_console(console)
