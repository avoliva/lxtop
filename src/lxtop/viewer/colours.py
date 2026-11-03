"""The terminal's colours and the Linux console's palette: the I/O half of a look.
`looks/theme.py` decides the colours; this module puts them on the screen."""

from __future__ import annotations

import contextlib
import curses
import fcntl
import os
import sys

from lxtop.looks import theme as th
from lxtop.looks.theme import Theme

GIO_CMAP = 0x4B70  # linux/kd.h: read the console's 16-colour palette


def read_palette(fd: int) -> list[str] | None:
    """The console's palette as 16 rrggbb strings, or None when `fd` is not a Linux console."""
    buf = bytearray(48)
    try:
        fcntl.ioctl(fd, GIO_CMAP, buf, True)
    except OSError:
        return None
    return [buf[i * 3 : i * 3 + 3].hex() for i in range(16)]


def palette_codes(entries: list[tuple[int, str]] | tuple[tuple[int, str], ...]) -> str:
    """Linux console escapes (console_codes(4), ESC ] P n rrggbb) setting palette slots."""
    return "".join(f"\033]P{slot:X}{rgb}" for slot, rgb in entries if 0 <= slot < 16)


def init_colours(win: object, theme: Theme, console: bool = False) -> None:
    """Set the pairs and the window background for `theme` (callable again to switch)."""
    if not curses.has_colors():
        return
    for pair, (fg, bg) in th.pairs(theme, curses.COLORS, console).items():
        curses.init_pair(pair, fg, bg)
    if theme.background >= 0:
        win.bkgd(" ", curses.color_pair(th.BACKGROUND))  # type: ignore[attr-defined]
    else:
        win.bkgd(" ", 0)  # type: ignore[attr-defined]


def write_palette(entries: tuple[tuple[int, str], ...], own: list[str] | None) -> None:
    """Show `entries` on the console's palette, or with none, put back `own` (the palette the
    console had when the viewer started), or the kernel's default if that is unknown."""
    if entries:
        codes = palette_codes(entries)
    elif own:
        codes = palette_codes(list(enumerate(own)))
    else:
        codes = "\033]R"  # the kernel's default palette
    with contextlib.suppress(OSError):
        os.write(sys.stdout.fileno(), codes.encode())
