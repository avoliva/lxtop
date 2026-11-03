"""Every character the viewer draws exists on the host's console."""

from __future__ import annotations

import ast
from pathlib import Path

import lxtop
from lxtop.viewer import font

# The non-ASCII characters of Uni2-TerminusBold24x12 (and the 28x14 and 32x16 sizes, which
# share its table), read from Ubuntu's /usr/share/consolefonts.
FIXTURE = Path(__file__).parents[1] / "fixtures" / "terminus-chars.txt"
CONSOLE = set(FIXTURE.read_text().strip()) | set(font.NEW)
PACKAGE = Path(lxtop.__file__).parent
# Every module whose strings reach the screen: the viewer (but font.py, which names the spare
# glyphs) and the pure core.
DRAWN = tuple(
    sorted(
        str(path.relative_to(PACKAGE))
        for path in [
            *PACKAGE.glob("viewer/**/*.py"),
            *PACKAGE.glob("core/*.py"),
        ]
        if path.name not in ("__init__.py", "font.py")
    )
)


def drawn_strings(path: Path) -> set[str]:
    """String constants in a module, without docstrings (never drawn)."""
    tree = ast.parse(path.read_text())
    docs = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs
    }


def test_viewer_strings_fit_the_console_font() -> None:
    folder = PACKAGE
    missing = {}
    for name in DRAWN:
        chars = {c for text in drawn_strings(folder / name) for c in text if ord(c) > 0x7E}
        if chars - CONSOLE:
            missing[name] = "".join(sorted(chars - CONSOLE))
    assert missing == {}


def test_spares_are_never_drawn() -> None:
    assert not font.SPARE & set(font.NEW)
    folder = PACKAGE
    used = {c for name in DRAWN for text in drawn_strings(folder / name) for c in text}
    assert not used & font.SPARE
