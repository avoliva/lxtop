"""A console font with the block elements graphs need.

The Linux console holds 512 glyphs, and the Terminus fonts use all of them without the eighth
blocks (▁▂▃▄▅▆▇ and ▏▎▍▌▋▊▉), so graphs there could only fill whole cells. This copies the
system font and redraws a few glyphs no dashboard draws (old DOS symbols such as ₧ ⌐ ☺ ‼) as
those blocks.
The viewer does this itself when it runs on a console (`console_font`) and puts the
console's own font back when it quits; on any failure it draws whole cells instead.
"""

from __future__ import annotations

import contextlib
import gzip
import os
import re
import struct
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

MAGIC = 0x864AB572
HAS_TABLE = 1
LOWER = "▁▂▃▄▅▆▇"  # 1/8 to 7/8 of the cell's height, from the bottom
LEFT = "▏▎▍▌▋▊▉"  # 1/8 to 7/8 of its width, from the left
HALVES = "▀▐"  # upper half, right half: the big digits use ▀ ▄ █
NEW = LOWER + LEFT + HALVES
# Glyphs given up for them: DOS-era symbols that each have a glyph of their own in Terminus and
# that no name or graph here uses. A tenant name holding one shows a block instead.
SPARE = set("₧⌐⌠⌡ⁿ☺☻☼‼¤∟‗ϳϴ₮⌂↨¦ƒ")


@dataclass
class Font:
    width: int
    height: int
    glyphs: list[bytes]
    table: list[bytes]  # per glyph: its UTF-8 code points, then 0xFE sequences, without 0xFF

    @property
    def row_bytes(self) -> int:
        return (self.width + 7) // 8


def parse(data: bytes) -> Font:
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    if len(data) < 32:
        raise ValueError("not a PSF2 font")
    magic, _version, header, flags, count, size, height, width = struct.unpack("<8I", data[:32])
    if magic != MAGIC or not flags & HAS_TABLE:
        raise ValueError("not a PSF2 font with a unicode table")
    glyphs = [data[header + i * size : header + (i + 1) * size] for i in range(count)]
    entries = data[header + count * size :].split(b"\xff")[:count]
    if len(entries) < count or any(len(g) != size for g in glyphs):
        raise ValueError("truncated font")
    return Font(width, height, glyphs, entries)


def dump(font: Font) -> bytes:
    size = font.row_bytes * font.height
    header = struct.pack(
        "<8I", MAGIC, 0, 32, HAS_TABLE, len(font.glyphs), size, font.height, font.width
    )
    return header + b"".join(font.glyphs) + b"".join(e + b"\xff" for e in font.table)


def codepoints(entry: bytes) -> set[str]:
    return set(entry.split(b"\xfe")[0].decode("utf-8", "replace"))


def bitmap(char: str, width: int, height: int) -> bytes:
    rb = (width + 7) // 8
    if char == "▀":
        return _top(width, height)
    if char == "▐":
        right = int("0" * (width // 2) + "1" * (width - width // 2) + "0" * (rb * 8 - width), 2)
        return right.to_bytes(rb, "big") * height
    if char in LOWER:
        rows = max(1, round(height * (LOWER.index(char) + 1) / 8))
        line = int("1" * width + "0" * (rb * 8 - width), 2).to_bytes(rb, "big")
        return bytes(rb) * (height - rows) + line * rows
    cols = max(1, round(width * (LEFT.index(char) + 1) / 8))
    line = int("1" * cols + "0" * (rb * 8 - cols), 2).to_bytes(rb, "big")
    return line * height


def _top(width: int, height: int) -> bytes:
    rb = (width + 7) // 8
    rows = height // 2
    line = int("1" * width + "0" * (rb * 8 - width), 2).to_bytes(rb, "big")
    return line * rows + bytes(rb) * (height - rows)


def with_blocks(font: Font) -> Font:
    """The same font with NEW drawn into spare glyphs. Raises if there are too few spares."""
    have = set().union(*(codepoints(e) for e in font.table))
    wanted = [c for c in NEW if c not in have]
    spare = [
        i
        for i, entry in enumerate(font.table)
        if b"\xfe" not in entry and codepoints(entry) and codepoints(entry) <= SPARE
    ]
    if len(spare) < len(wanted):
        raise ValueError(f"only {len(spare)} spare glyphs for {len(wanted)} blocks")
    glyphs, table = list(font.glyphs), list(font.table)
    for index, char in zip(spare, wanted, strict=False):
        glyphs[index] = bitmap(char, font.width, font.height)
        table[index] = char.encode()
    return Font(font.width, font.height, glyphs, table)


def own_console() -> bool:
    """True when this process draws on a Linux virtual console (/dev/ttyN), not a pty."""
    try:
        name = os.ttyname(1)
    except OSError:
        return False
    return re.fullmatch(r"/dev/tty[0-9]+", name) is not None


def run_setfont(*args: str) -> bool:
    try:
        done = subprocess.run(["setfont", *args], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


class ConsoleFont:
    """The font on your own console while lxtop runs: Terminus with the graph blocks."""

    def __init__(
        self, blocks: Font, folder: Path, setfont: Callable[..., bool] = run_setfont
    ) -> None:
        self.blocks = blocks
        self.folder = folder
        self.setfont = setfont


@contextlib.contextmanager
def console_font(base: Path) -> Iterator[ConsoleFont | None]:
    """On your own console: save its font, load `base` with block glyphs, and put the saved
    font back afterwards. Yields the ConsoleFont, or None when the blocks are not loaded.
    setfont needs no root for the console you are logged in on."""
    if os.environ.get("TERM") != "linux" or not own_console():
        yield None
        return
    with tempfile.TemporaryDirectory(prefix="lxtop-") as folder:
        saved = Path(folder) / "before.psf"
        built = Path(folder) / "blocks.psf"
        try:
            blocks = with_blocks(parse(base.read_bytes()))
            built.write_bytes(dump(blocks))
        except (OSError, ValueError):
            yield None
            return
        if not run_setfont("-O", str(saved), str(built)):
            yield None
            return
        try:
            yield ConsoleFont(blocks, Path(folder))
        finally:
            if saved.exists():
                run_setfont(str(saved))
