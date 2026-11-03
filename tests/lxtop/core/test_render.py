from __future__ import annotations

from lxtop.core import charts, render
from lxtop.core.render import CONSOLE, UNICODE, speed, speed_short

# Characters the host's plain console font (Uni2-TerminusBold32x16) has, checked against its PSF
# unicode table. It lacks the eighth blocks ▁▂▃▄▅▆▇ and ▏▎▍▌▋▊▉.
CONSOLE_FONT = set("█░▒─│┌┐└┘├┤┬┴┼═║▲▼●•·↑↓…+ ") | {chr(c) for c in range(0x20, 0x7F)} | {"°"}


def test_clean_drops_escape_sequences() -> None:
    evil = "app\x1b]0;pwned\x07\x1b[2J\x9b31m\r\nname‮"
    out = render.clean(evil)
    assert "\x1b" not in out and "\x07" not in out and "\x9b" not in out
    assert "\r" not in out and "\n" not in out and "‮" not in out
    assert out.startswith("app ")
    assert render.clean("x" * 1000, limit=10) == "x" * 10
    assert render.clean(42) == "42"


def test_bar_widths_and_fill() -> None:
    assert render.bar(0.5, 10, CONSOLE) == "█" * 5 + "░" * 5
    assert render.bar(1.5, 4, CONSOLE) == "████"
    assert render.bar(-1, 4, CONSOLE) == "░░░░"
    assert len(render.bar(0.33, 7, UNICODE)) == 7
    assert render.bar(0.25, 2, UNICODE) == "▌░"
    assert render.bar(0.0625, 2, UNICODE) == "▏░"


def test_console_glyphs_are_all_in_the_console_font() -> None:
    drawn = [getattr(CONSOLE, f) for f in CONSOLE.__dataclass_fields__]
    used = set().union(*(set(v) for v in drawn if isinstance(v, str)))
    assert used <= CONSOLE_FONT
    bars = "".join(render.bar(i / 20, 10, CONSOLE) for i in range(21))
    graphs = "".join("".join(charts.graph([i / 9], 1, 3, 1.0, CONSOLE)) for i in range(10))
    assert set(bars + graphs) <= CONSOLE_FONT


def test_glyph_choice() -> None:
    assert render.glyphs_for("linux") is CONSOLE
    assert render.glyphs_for("xterm-256color") is UNICODE
    assert render.glyphs_for("linux", "unicode") is UNICODE
    # The console with lxtop's font has the eighth blocks but no braille: box-line graphs.
    blocks = render.glyphs_for("linux", console_blocks=True)
    assert blocks.vertical == UNICODE.vertical and blocks.eighths == UNICODE.eighths
    assert not blocks.braille
    assert render.glyphs_for("linux", "console", console_blocks=True) is CONSOLE


def test_sizes_and_durations() -> None:
    assert render.human_bytes(512) == "512B"
    assert render.human_bytes(1536) == "1.5K"
    assert render.human_bytes(12 * 2**30) == "12.0G"
    assert render.human_rate(2048) == "2.0K/s"
    assert render.duration(59) == "59s"
    assert render.duration(3 * 86400 + 4 * 3600) == "3d 4h"
    assert render.fit("abcdef", 4) == "abc…"
    assert render.fit("ab", 4, right=True) == "  ab"


def test_big_digits() -> None:
    rows = render.big("1.5")
    assert len(set(map(len, rows))) == 1
    assert rows[0].startswith("▀█")
    assert render.big("x") == ("", "", "")


def test_speeds_are_in_bits_like_an_internet_plan() -> None:
    assert speed(0) == "0 bit/s"
    assert speed(125) == "1.0 kbit/s"
    assert speed(312_500) == "2.5 Mbit/s"
    assert speed(125_000_000) == "1.0 Gbit/s"
    assert speed(25_000_000) == "200 Mbit/s"


def test_short_speeds_fit_an_axis() -> None:
    assert speed_short(12_500) == "100k"
    assert speed_short(312_500) == "2.5M"
    assert speed_short(10) == "80"
