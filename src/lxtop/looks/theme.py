"""Looks for the viewer: the core every look shares, and the plain default.

A look (a `Theme`) decides the colours behind the seven named pairs every page uses, the frame
characters, the title bar, and which effects run. Each look other than the default lives in its
own module in this package, `looks/<name>.py`, exporting `THEME`; `load_themes` finds them, so
adding a look means adding one file. This
module is pure; `viewer/colours.py` puts a look's colours on the terminal.

Rules every look keeps (tests/lxtop/looks/test_looks.py checks them for each one):
- red and yellow stay the warning colours, different from every other text colour;
- effects never draw over text: a backdrop's cells land only where nothing was drawn and not
  beside text, use only the three effect tones, never a text colour, and carry no digits;
- on the Linux console every character exists in its font, and the console palette never
  redefines black or the warning slots.
"""

from __future__ import annotations

import importlib
import pkgutil
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

# The pairs screen.py names (GREEN .. WHITE are 1 .. 7), then the effects' three tones, the
# window background, and the effects seen through a panel (trail and head). GLASS + n is pair n
# on a panel's tinted background.
FX_DIM, FX_MID, FX_HEAD, BACKGROUND, FX_GLASS, FX_GLASS_HEAD = 8, 9, 10, 11, 12, 13
TONES = (FX_DIM, FX_MID, FX_HEAD)
GLASS = 20
WARNING_SLOTS = (0, 1, 3, 9, 11)  # black, red, yellow and bold red, bold yellow on the console

# How many effects: (name, keep every nth column in the open, every nth behind glass). Effects
# start on ("light"); r steps through them. FX_SHOWN: what the footer and the title call each.
FX_LEVELS = (("light", 2, 4), ("full", 1, 2), ("off", 0, 0))
FX_SHOWN = {"light": "on", "full": "max", "off": "off"}
DECODE_SECONDS = 0.8
BOOT_SECONDS = 2.4

# Row, column, character, tone (one of TONES).
Cell = tuple[int, int, str, int]


class Backdrop(Protocol):
    """An animated background: cells to show at a moment. The viewer places each one only in a
    cell nothing was drawn in and not beside text, darker behind a panel's glass."""

    def resize(self, h: int, w: int) -> None: ...

    def frame(self, now: float) -> list[Cell]: ...


@dataclass(frozen=True)
class Title:
    """A look's own title bar, drawn on black: `left` NAME `right`, then `prompt` subtitle and
    a blinking `cursor`. Glitching looks flip a few letters and slip a column now and then."""

    left: str = ""
    right: str = ""
    prompt: str = ""
    cursor: str = ""


@dataclass(frozen=True)
class Theme:
    """`colours`: pair -> (colour on a 256-colour terminal, colour on an 8-colour one).
    `frame`: top-left, top-right, bottom-left, bottom-right, horizontal, vertical."""

    name: str
    colours: dict[int, tuple[int, int]]
    background: int  # the 8-colour background (0-7); -1 keeps the terminal's own
    # The same background on a 256-colour terminal: 16 is the colour cube's black, which no
    # terminal theme recolours; a light look sets a light one (e.g. 230, cream).
    background_rich: int = 16
    frame: str = "╭╮╰╯─│"
    tick_ms: int = 500
    # Sections drawn as framed panels whose insides are glass: effects show through them,
    # darker, and on a 256-colour terminal their background is tinted `glass` (-1: no tint).
    panels: bool = False
    glass: int = -1
    # On the Linux console (8 colours, no grey), palette slots this look redefines while it
    # shows: (slot 0-15, rrggbb). Slot 4, blue, is the glass when the look has panels.
    console_palette: tuple[tuple[int, str], ...] = ()
    # The animated background, made per viewer: backdrop(console, rng). None: no effects.
    backdrop: Callable[[bool, random.Random], Backdrop] | None = None
    # Effects levels thin the backdrop by columns (good for rain). Off for effects drawn as
    # lines, which columns would cut into dots: then any level but off shows all of it.
    thin: bool = False
    # Inside panels, effects show darker, behind the glass (Matrix's rain). Off: they are drawn
    # in front, in the look's own effect colours on the panel's background.
    see_through: bool = False
    glitch: bool = False  # pages decode from noise when they appear; the title glitches
    noise: tuple[str, str] = ("01", "01")  # scramble characters: (terminal, console)
    # The empty part of meters and bars, (terminal, console); "" keeps the glyph set's own.
    meter_empty: tuple[str, str] = ("", "")
    boot: tuple[str, ...] = ()  # lines typed out at start (any key skips); () for none
    title: Title | None = None  # None: the default reversed bar
    accent: int = 1  # the pair for the title, the footer bar and the boot lines
    label: str = ""  # a few words for the help screen


BLACK, RED_8, GREEN_8, YELLOW_8, BLUE_8, MAGENTA_8, CYAN_8, WHITE_8 = range(8)

DEFAULT = Theme(
    name="default",
    colours={
        1: (GREEN_8, GREEN_8),
        2: (YELLOW_8, YELLOW_8),
        3: (RED_8, RED_8),
        4: (CYAN_8, CYAN_8),
        5: (MAGENTA_8, MAGENTA_8),
        6: (BLUE_8, BLUE_8),
        7: (WHITE_8, WHITE_8),
    },
    background=-1,
    accent=6,
    label="the terminal's own colours",
)


def load_themes() -> dict[str, Theme]:
    """The default look, then the THEME of every other module in this package, in name order.
    A look that fails to import is left out rather than stopping the viewer."""
    from lxtop import looks

    found = {DEFAULT.name: DEFAULT}
    for module in sorted(m.name for m in pkgutil.iter_modules(looks.__path__)):
        if module == "theme":
            continue
        try:
            theme = importlib.import_module(f"lxtop.looks.{module}").THEME
        except Exception:  # one broken look must not take the dashboard down
            continue
        if isinstance(theme, Theme) and theme.name not in found:
            found[theme.name] = theme
    return found


def next_theme(theme: Theme, step: int = 1) -> Theme:
    """The look after `theme` in the list (step -1: the one before), wrapping round."""
    found = themes()
    names = list(found)
    index = names.index(theme.name) if theme.name in names else -step
    return found[names[(index + step) % len(names)]]


def pairs(theme: Theme, colours: int, console: bool = False) -> dict[int, tuple[int, int]]:
    """pair -> (foreground, background) for a terminal with `colours` colours."""
    rich = colours >= 256
    bg = theme.background
    if bg >= 0 and rich:
        bg = theme.background_rich
    out = {
        pair: (rich_fg if rich else plain_fg, bg)
        for pair, (rich_fg, plain_fg) in theme.colours.items()
    }
    if bg >= 0:
        # Text drawn with no colour of its own takes the window background's pair: make that
        # the look's plain text colour, so it reads on dark and light looks alike.
        out[BACKGROUND] = (out[7][0], bg)
    if tinted(theme, colours, console):
        glass = theme.glass if rich else BLUE_8  # the console's slot 4, redefined as glass
        for pair in (FX_GLASS, FX_GLASS_HEAD):
            if pair in out:  # a look with panels but no backdrop has no effect colours
                out[pair] = (out[pair][0], glass)
        out[GLASS] = (out[7][0], glass)  # uncoloured text on glass: plain text colour too
        for pair in range(1, BACKGROUND + 1):
            if pair in out:
                out[GLASS + pair] = (out[pair][0], glass)
    return out


def tinted(theme: Theme, colours: int, console: bool = False) -> bool:
    """Whether panels get a background tint: with 256 colours, or on the Linux console when
    the theme redefines its palette (8 colours have no grey of their own)."""
    if not theme.panels:
        return False
    return (colours >= 256 and theme.glass >= 0) or (console and bool(theme.console_palette))


def fx_falls(level: str, x: int, glass: bool) -> bool:
    """Whether effects at `level` show in column `x`, in the open or behind a panel's glass."""
    for name, open_every, glass_every in FX_LEVELS:
        if name == level:
            every = glass_every if glass else open_every
            return every > 0 and x % every == 0
    return False


def next_fx(level: str) -> str:
    names = [name for name, _, _ in FX_LEVELS]
    return names[(names.index(level) + 1) % len(names)] if level in names else names[0]


def scramble(text: str, share: float, rng: random.Random, chars: str) -> str:
    """`text` with about `share` of its non-space characters swapped for random `chars`."""
    if share <= 0:
        return text
    return "".join(
        rng.choice(chars) if c != " " and (share >= 1 or rng.random() < share) else c for c in text
    )


_themes: dict[str, Theme] | None = None


def themes() -> dict[str, Theme]:
    """Every look, found on first use rather than at import: a look module imports this one,
    so finding the looks while this module loads would meet that look half imported."""
    global _themes
    if _themes is None:
        _themes = load_themes()
    return _themes


def __getattr__(name: str) -> dict[str, Theme]:
    """`theme.THEMES` is `themes()`."""
    if name == "THEMES":
        return themes()
    raise AttributeError(name)
