"""The all-machines page: the host, every LXD instance and the containers inside them.

    rows 0-3  host summary: CPU, memory, GPU, temperatures, network, disks
    left      tree: host and its containers, then each LXD instance and its containers
    right     the selected item: facts, CPU/memory/network graphs, top processes or labels

On narrow terminals the tree takes the whole width and d switches to the detail page. On the
host's monitor (at least 120x40) the header is the title bar and big-number tiles instead.
"""

from __future__ import annotations

import curses
from collections.abc import Sequence

from lxtop.core import model
from lxtop.core import snapshot as sn
from lxtop.core.model import Row
from lxtop.core.snapshot import Json, as_dict, text
from lxtop.viewer.pages import machines_header, machines_tree
from lxtop.viewer.pages.base import Frame, Page
from lxtop.viewer.screen import BLUE, WHITE, color

WIDE = 120  # the tree and the detail side by side
TILED_HEIGHT = 40  # with WIDE: the title bar and tiles, like the other pages


def tiled(frame: Frame) -> bool:
    h, w = frame.screen.size
    return w >= WIDE and h >= TILED_HEIGHT


class MachinesPage:
    name = "machines"
    label = "all machines"
    title = " ALL MACHINES "
    host_line = False  # the page is the host's numbers
    help: tuple[tuple[str, str], ...] = (
        ("All machines page", ""),
        ("↑ ↓  j k", "select"),
        ("PgUp PgDn  g G", "page, first, last"),
        ("→ ←  l h  Enter", "open or fold an instance, jump to parent"),
        ("e  c", "open all, fold all"),
        ("s", "sort by name, CPU, memory"),
        ("d", "detail page (narrow screens)"),
    )

    def __init__(self) -> None:
        self.expanded: set[str] = {"host"}
        self.seen: set[str] = set()  # instances already shown once: new ones start open
        self.selected = "host"
        self.top = 0  # first tree row shown
        self.sort = "name"
        self.detail_page = False  # narrow screens: the detail instead of the tree
        self.rows: list[Row] = []  # the tree as last drawn, for the keys

    def subtitle(self, frame: Frame, height: int, width: int) -> str | None:
        return machines_header.machines_subtitle(frame) if tiled(frame) else None

    def footer(self, frame: Frame, after: Page, pages: Sequence[Page]) -> str:
        return f"↑↓ select  →← open/fold  s sort  e/c all  d detail  Tab {after.label}  ? help"

    # ---- input -----------------------------------------------------------------------------

    def handle(self, key: int, frame: Frame) -> bool:
        rows = self.rows
        keys = [r.key for r in rows]
        index = keys.index(self.selected) if self.selected in keys else 0
        current = rows[index] if rows else None
        page = max(1, frame.screen.size[0] - 8)
        if key in (curses.KEY_DOWN, ord("j")):
            index += 1
        elif key in (curses.KEY_UP, ord("k")):
            index -= 1
        elif key == curses.KEY_NPAGE:
            index += page
        elif key == curses.KEY_PPAGE:
            index -= page
        elif key in (curses.KEY_HOME, ord("g")):
            index = 0
        elif key in (curses.KEY_END, ord("G")):
            index = len(rows) - 1
        elif key == ord("s"):
            self.sort = model.SORTS[(model.SORTS.index(self.sort) + 1) % len(model.SORTS)]
        elif key == ord("e"):
            self.expanded |= {r.key for r in rows if r.depth == 0}
        elif key == ord("c"):
            self.expanded.clear()
        elif key == ord("d"):
            self.detail_page = not self.detail_page
        elif current is not None and key in (curses.KEY_RIGHT, ord("l")):
            self.expanded.add(current.key)
        elif current is not None and key in (curses.KEY_LEFT, ord("h")):
            if current.depth > 0:
                self.selected = current.key.rsplit("/c:", 1)[0]
                return True
            self.expanded.discard(current.key)
        elif current is not None and key in (curses.KEY_ENTER, 10, 13, ord(" ")):
            if current.depth == 0:
                self.expanded ^= {current.key}
            else:
                self.detail_page = True
        else:
            return False
        if rows:
            index = max(0, min(len(rows) - 1, index))
            self.selected = rows[index].key
        return True

    # ---- the page --------------------------------------------------------------------------

    def loaded(self, snapshot: Json) -> None:
        """An instance seen for the first time starts unfolded; one folded by hand stays so."""
        for inst in sn.instances(snapshot):
            key = text(as_dict(inst).get("key"))
            if key and key not in self.seen:
                self.seen.add(key)
                self.expanded.add(key)

    def draw(self, frame: Frame, height: int, width: int) -> None:
        s, g = frame.screen, frame.glyphs
        snap = frame.snapshot
        rows = model.tree(snap, self.expanded, self.sort) if snap else []
        self.rows = rows
        if self.selected not in {r.key for r in rows} and rows:
            self.selected = rows[0].key
        wide = width >= WIDE
        tiles = tiled(frame)
        if tiles:
            machines_header.draw_machines_line(frame, width)
            machines_header.draw_machine_tiles(frame, 3, width)
            body_top = 11
        else:
            machines_header.draw_header(frame, width)
            body_top = 5
        body_height = height - body_top
        list_width = min(100, max(64, int(width * 0.5))) if wide else width
        selected = next((r for r in rows if r.key == self.selected), None)
        if tiles and s.theme.panels:
            # Each half in a panel whose frame runs along the row above it, titled there.
            body_height -= 1
            top = body_top - 1
            s.panel(top, 1, body_height + 1, list_width - 2, color(BLUE))
            s.put(top, 3, " MACHINES ", color(WHITE, True))
            machines_tree.draw_tree(self, frame, rows, body_top, body_height, list_width - 2, 1)
            if selected is not None:
                x = list_width + 2
                s.panel(top, x, body_height + 1, width - x - 1, color(BLUE))
                s.put(top, x + 2, " DETAIL ", color(WHITE, True))
                machines_tree.draw_detail(
                    frame, selected, body_top, body_height, x + 1, width - x - 1
                )
            return
        if wide or not self.detail_page:
            machines_tree.draw_tree(self, frame, rows, body_top, body_height, list_width)
        if selected is not None and (wide or self.detail_page):
            x = list_width + 1 if wide else 0
            if wide:
                for y in range(body_top, body_top + body_height):
                    s.put(y, list_width, g.vline, color(BLUE))
            machines_tree.draw_detail(frame, selected, body_top, body_height, x, width - x)
