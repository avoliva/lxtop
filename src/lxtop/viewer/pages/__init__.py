"""The viewer's pages, in Tab order; the first is the home page. A new page is a module
here keeping the contract in `base.py`, and one entry in PAGES."""

from __future__ import annotations

from collections.abc import Callable

from lxtop.viewer.pages.base import Page
from lxtop.viewer.pages.machines import MachinesPage
from lxtop.viewer.pages.memory import MemoryPage
from lxtop.viewer.pages.network import NetworkPage
from lxtop.viewer.pages.services import ServicesPage

PAGES: tuple[Callable[[], Page], ...] = (
    NetworkPage,
    MachinesPage,
    MemoryPage,
    ServicesPage,
)
