"""The console's palette escapes and reading it back."""

from __future__ import annotations

import curses
import fcntl
import os
from pathlib import Path

import pytest

from lxtop.looks import theme as th
from lxtop.viewer import colours


def test_palette_codes_are_console_escapes_for_each_slot() -> None:
    assert colours.palette_codes([(4, "143018"), (15, "eaffee")]) == "\033]P4143018\033]PFeaffee"
    assert colours.palette_codes([(16, "000000")]) == ""


def test_read_palette_is_none_off_the_console(tmp_path: Path) -> None:
    with (tmp_path / "f").open("wb") as f:
        assert colours.read_palette(f.fileno()) is None


def test_read_palette_reads_the_consoles_sixteen_colours(monkeypatch: pytest.MonkeyPatch) -> None:
    def ioctl(fd: int, request: int, buf: bytearray, mutate: bool) -> None:
        assert request == colours.GIO_CMAP and mutate
        buf[:] = bytes(range(48))

    monkeypatch.setattr(fcntl, "ioctl", ioctl)

    got = colours.read_palette(0)

    assert got is not None and len(got) == 16
    assert got[0] == "000102" and got[15] == "2d2e2f"


class Win:
    def __init__(self) -> None:
        self.background: tuple[object, ...] = ()

    def bkgd(self, *args: object) -> None:
        self.background = args


@pytest.mark.parametrize("look", ["default", "matrix"])
def test_init_colours_sets_every_pair_and_the_background(
    monkeypatch: pytest.MonkeyPatch, look: str
) -> None:
    pairs: dict[int, tuple[int, int]] = {}
    monkeypatch.setattr(curses, "has_colors", lambda: True)
    monkeypatch.setattr(curses, "COLORS", 256, raising=False)
    monkeypatch.setattr(curses, "init_pair", lambda n, fg, bg: pairs.update({n: (fg, bg)}))
    monkeypatch.setattr(curses, "color_pair", lambda n: n << 8)
    theme = th.THEMES[look]
    win = Win()

    colours.init_colours(win, theme)

    assert pairs == th.pairs(theme, 256)
    expected = (" ", th.BACKGROUND << 8) if theme.background >= 0 else (" ", 0)
    assert win.background == expected


def test_write_palette_puts_back_the_consoles_own_or_the_kernels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: list[bytes] = []

    def write(fd: int, data: bytes) -> int:
        written.append(data)
        return len(data)

    monkeypatch.setattr(os, "write", write)

    colours.write_palette(((4, "143018"),), None)
    colours.write_palette((), ["000000"] * 16)
    colours.write_palette((), None)

    assert written[0] == b"\x1b]P4143018"
    assert written[1].startswith(b"\x1b]P0000000") and written[2] == b"\x1b]R"
