"""The contract every page keeps, so a page is added by writing one module and listing
it in `pages.PAGES`.

The app owns the loop, the look, the title bar and the footer bar; a page owns what is between
them and its own state (what is selected, what is open, how far it scrolled). Every snapshot read
goes to each page's `loaded`; each frame the app builds a `Frame` and calls the showing page's
`draw`; each key the app does not use itself (q, t, r, ?, Tab, the page numbers) goes to its
`handle`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from lxtop.core.render import Glyphs
from lxtop.core.snapshot import Json
from lxtop.viewer.screen import Screen


@dataclass
class Frame:
    """What a page draws from: the screen and the latest snapshot, read once per frame."""

    screen: Screen
    snapshot: Json
    load_error: str = ""  # why the snapshot could not be read, or ""

    @property
    def glyphs(self) -> Glyphs:
        return self.screen.glyphs


class Page(Protocol):
    name: str  # short, in the footer's page list: "network"
    label: str  # in Tab hints and the help: "network"
    title: str  # the title bar's name: " NETWORK "
    host_line: bool  # whether the footer ends with the host's own CPU and memory
    help: tuple[tuple[str, str], ...]  # the page's section of the help, () for none

    def loaded(self, snapshot: Json) -> None:
        """Every page hears of each snapshot read, even while another page shows."""
        ...

    def subtitle(self, frame: Frame, height: int, width: int) -> str | None:
        """The title bar's subtitle, or None when the page draws its own header in row 0."""
        ...

    def footer(self, frame: Frame, after: Page, pages: Sequence[Page]) -> str:
        """The keys for the footer bar; `after` is the page Tab goes to."""
        ...

    def handle(self, key: int, frame: Frame) -> bool:
        """Apply a key; False when the key is not one of this page's."""
        ...

    def draw(self, frame: Frame, height: int, width: int) -> None:
        """Draw rows 1 .. height-1: row 0 is the title bar (the page draws its own there when
        `subtitle` is None), and the row at `height` is the footer."""
        ...
