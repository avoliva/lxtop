"""Pure text rendering: glyph sets, bars, sizes and speeds, big digits, and cleaning untrusted
strings for the screen. Charts are in charts.py."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Glyphs:
    """Characters the terminal can show. The Linux console font (Terminus, 512 glyphs) has full
    blocks, shades and box lines but none of the eighth blocks, so it gets whole-cell graphs."""

    full: str
    empty: str
    eighths: str  # partial fills from 1/8 to 7/8; empty means whole cells only
    vertical: str  # graph cells from 1/8 to 8/8 height; one char means whole cells only
    open: str
    closed: str
    hline: str
    vline: str
    up: str
    down: str
    ellipsis: str
    # Braille dots (2 x 4 per cell) for line graphs; the console font has none, so it draws
    # lines with box-drawing characters instead.
    braille: bool = False


UNICODE = Glyphs(
    full="█",
    empty="░",
    eighths="▏▎▍▌▋▊▉",
    vertical="▁▂▃▄▅▆▇█",
    open="▾",
    closed="▸",
    hline="─",
    vline="│",
    up="↑",
    down="↓",
    ellipsis="…",
    braille=True,
)
CONSOLE = Glyphs(
    full="█",
    empty="░",
    eighths="",
    vertical="█",
    open="▼",
    closed="+",
    hline="─",
    vline="│",
    up="↑",
    down="↓",
    ellipsis="…",
)


# The console with lxtop's own font (font.py): its eighth blocks, but still no braille.
CONSOLE_BLOCKS = replace(UNICODE, braille=False)


def glyphs_for(term: str, choice: str = "auto", console_blocks: bool = False) -> Glyphs:
    """The console gets whole cells, or eighth blocks once lxtop's font is loaded on it;
    line graphs there use box lines either way, since no console font here has braille."""
    if choice == "console" or (choice == "auto" and term == "linux" and not console_blocks):
        return CONSOLE
    if choice == "auto" and term == "linux":
        return CONSOLE_BLOCKS
    return UNICODE


def clean(value: object, limit: int = 300) -> str:
    """Printable text only. Names and labels come from tenant VMs, so an escape sequence in a
    container name must never reach the terminal."""
    raw = value if isinstance(value, str) else str(value)
    out = "".join(ch if ch.isprintable() else " " for ch in raw[: limit * 2])
    return out[:limit]


def fit(value: str, width: int, ellipsis: str = "…", right: bool = False) -> str:
    """Exactly `width` columns, cut with an ellipsis or padded."""
    if width <= 0:
        return ""
    if len(value) > width:
        return value[: width - 1] + ellipsis if width > 1 else value[:width]
    return value.rjust(width) if right else value.ljust(width)


def bar(fraction: float, width: int, g: Glyphs) -> str:
    """A horizontal meter `width` cells wide."""
    if width <= 0:
        return ""
    fraction = max(0.0, min(1.0, fraction))
    cells = fraction * width
    whole = int(cells)
    out = g.full * whole
    if whole < width:
        rest = cells - whole
        index = int(rest * 8)
        if g.eighths and index > 0:
            out += g.eighths[index - 1]
        elif not g.eighths and rest >= 0.5:
            out += g.full
        else:
            out += g.empty
    return (out + g.empty * width)[:width]


def human_bytes(n: float, digits: int = 1) -> str:
    n = float(n)
    for unit in ("B", "K", "M", "G", "T"):
        if abs(n) < 1024 or unit == "T":
            if unit == "B":
                return f"{n:.0f}B"
            return f"{n:.{digits}f}{unit}"
        n /= 1024
    return f"{n:.1f}T"


def human_rate(n: float) -> str:
    return human_bytes(n) + "/s"


def speed_parts(per_second: float) -> tuple[str, str]:
    """Bytes per second as an internet speed: ("2.4", "Mbit/s")."""
    bits = max(0.0, per_second) * 8
    for unit, scale in (("Gbit/s", 1e9), ("Mbit/s", 1e6), ("kbit/s", 1e3)):
        if bits >= scale:
            value = bits / scale
            return (f"{value:.1f}" if value < 100 else f"{value:.0f}"), unit
    return f"{bits:.0f}", "bit/s"


def speed(per_second: float) -> str:
    value, unit = speed_parts(per_second)
    return f"{value} {unit}"


def speed_short(per_second: float) -> str:
    """A speed for a narrow axis label, in bits: "100k", "2.5M"."""
    value, unit = speed_parts(per_second)
    return value + ("" if unit == "bit/s" else unit[0])


def duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def since(epoch: float, now: float | None = None) -> str:
    return duration((now if now is not None else time.time()) - epoch)


def percent(fraction: float) -> str:
    return f"{fraction * 100:5.1f}%"


# Three-row digits from ▀ ▄ █ (font.py adds ▀ to the console font).
BIG = {
    "0": ("█▀█", "█ █", "▀▀▀"),
    "1": ("▀█ ", " █ ", "▀▀▀"),
    "2": ("▀▀█", "█▀▀", "▀▀▀"),
    "3": ("▀▀█", " ▀█", "▀▀▀"),
    "4": ("█ █", "▀▀█", "  ▀"),
    "5": ("█▀▀", "▀▀█", "▀▀▀"),
    "6": ("█▀▀", "█▀█", "▀▀▀"),
    "7": ("▀▀█", "  █", "  ▀"),
    "8": ("█▀█", "█▀█", "▀▀▀"),
    "9": ("█▀█", "▀▀█", "▀▀▀"),
    ".": ("   ", "   ", " ▀ "),
    " ": ("  ", "  ", "  "),
}


def big(value: str) -> tuple[str, str, str]:
    """`value` (digits, '.', ' ') in three rows; other characters are dropped."""
    parts = [BIG[c] for c in value if c in BIG]
    return (
        " ".join(p[0] for p in parts),
        " ".join(p[1] for p in parts),
        " ".join(p[2] for p in parts),
    )
