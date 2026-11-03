from __future__ import annotations

import gzip
import subprocess
from pathlib import Path

import pytest

from lxtop.viewer import font

SPARES = sorted(font.SPARE)


def tiny(spares: int = len(SPARES)) -> bytes:
    """A 10x4 PSF2 font: A, a shared box glyph, then `spares` DOS symbols."""
    entries = [b"A", "┌┍╭".encode(), b"B" + b"\xfe" + "B̈".encode()]
    entries += [c.encode() for c in SPARES[:spares]]
    glyphs = [bytes([i]) * 8 for i in range(len(entries))]  # 2 bytes a row, 4 rows
    f = font.Font(width=10, height=4, glyphs=glyphs, table=entries)
    return gzip.compress(font.dump(f))


def test_blocks_replace_spare_glyphs_only() -> None:
    base = font.parse(tiny())
    out = font.parse(font.dump(font.with_blocks(base)))
    have = set().union(*(font.codepoints(e) for e in out.table))
    assert set(font.NEW) <= have
    assert {"A", "┌", "B"} <= have
    assert out.glyphs[0] == base.glyphs[0]


def test_block_bitmaps() -> None:
    # 10 pixels wide, so two bytes a row with the low 6 bits unused.
    assert font.bitmap("▄", 10, 4) == bytes(4) + b"\xff\xc0" * 2
    assert font.bitmap("▌", 10, 4) == b"\xf8\x00" * 4
    assert font.bitmap("▁", 10, 4) == bytes(6) + b"\xff\xc0"
    assert font.bitmap("▀", 10, 4) == b"\xff\xc0" * 2 + bytes(4)
    assert font.bitmap("▐", 10, 4) == b"\x07\xc0" * 4


def test_too_few_spares_and_bad_files() -> None:
    with pytest.raises(ValueError, match="spare"):
        font.with_blocks(font.parse(tiny(spares=3)))
    with pytest.raises(ValueError):
        font.parse(b"\x36\x04 psf1")
    with pytest.raises(ValueError):
        font.parse(gzip.compress(b"\x72\xb5\x4a\x86" + bytes(28)))


def test_font_is_swapped_in_and_back_on_your_own_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        if argv[1] == "-O":
            Path(argv[2]).write_bytes(b"saved")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(font, "own_console", lambda: True)
    monkeypatch.setenv("TERM", "linux")
    base = tmp_path / "base.psf.gz"
    base.write_bytes(tiny())
    with font.console_font(base) as loaded:
        assert loaded is not None
        assert calls[0][:2] == ["setfont", "-O"] and calls[0][3].endswith("blocks.psf")
    assert calls[-1][0] == "setfont" and calls[-1][1].endswith("before.psf")
    assert len(calls) == 2


def test_no_font_change_off_the_console_or_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **_: calls.append(argv))
    base = tmp_path / "base.psf.gz"
    base.write_bytes(tiny())
    monkeypatch.setenv("TERM", "xterm-256color")
    with font.console_font(base) as loaded:
        assert loaded is None
    monkeypatch.setenv("TERM", "linux")
    monkeypatch.setattr(font, "own_console", lambda: False)  # ssh: a pty
    with font.console_font(base) as loaded:
        assert loaded is None
    monkeypatch.setattr(font, "own_console", lambda: True)
    bad = tmp_path / "bad.psf.gz"
    bad.write_bytes(tiny(spares=2))
    with font.console_font(bad) as loaded:
        assert loaded is None
    assert calls == []
