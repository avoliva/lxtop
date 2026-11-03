"""The page contract: every registered page keeps it, and a frame is what a page draws from."""

from __future__ import annotations

import inspect

import pytest

from lxtop.viewer.pages import PAGES
from lxtop.viewer.pages.base import Page

pytestmark = pytest.mark.usefixtures("headless")

ATTRIBUTES = ("name", "label", "title", "host_line", "help")
METHODS = [n for n, _ in inspect.getmembers(Page, inspect.isfunction) if not n.startswith("_")]


def test_the_contract_has_the_methods_the_app_calls() -> None:
    assert sorted(METHODS) == ["draw", "footer", "handle", "loaded", "subtitle"]


@pytest.mark.parametrize("make", PAGES, ids=lambda make: make.__name__)
def test_every_page_keeps_the_contract(make: type) -> None:
    page = make()

    for name in ATTRIBUTES:
        assert hasattr(page, name), f"{make.__name__} has no {name}"
    for name in METHODS:
        theirs = inspect.signature(getattr(page, name)).parameters
        ours = inspect.signature(getattr(Page, name)).parameters
        assert list(theirs) == [p for p in ours if p != "self"], f"{make.__name__}.{name}"
    assert page.title.startswith(" ") and page.title.endswith(" ")
    assert all(len(row) == 2 for row in page.help)
