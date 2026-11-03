"""keys.handle: the viewer's own keys (pages, looks, help, quit), and that every other key
goes to the page showing."""

from __future__ import annotations

import pytest

from lxtop.looks import theme
from lxtop.viewer import app as view
from lxtop.viewer import keys
from lxtop.viewer.pages.base import Frame
from tests.support.curses_win import machines_page, make_app

pytestmark = pytest.mark.usefixtures("headless")


def shown(page: str = "machines", h: int = 40, w: int = 120) -> view.App:
    """`page` drawn once."""
    app: view.App = make_app(theme.DEFAULT, page, h, w)
    app.draw()
    return app


def test_no_key_is_a_no_op() -> None:
    app = shown()
    before = machines_page(app).selected

    assert keys.handle(app, -1) is True

    assert machines_page(app).selected == before


def test_q_quits_and_question_mark_opens_the_help_that_any_key_closes() -> None:
    app = shown()
    keys.handle(app, ord("?"))
    opened = app.help
    keys.handle(app, ord("x"))

    assert (opened, app.help) == (True, False)
    assert keys.handle(app, ord("q")) is False


class Clock:
    """A fourth page, to show a page is added by listing it."""

    name = "clock"
    label = "clock"
    title = " CLOCK "
    host_line = False
    help: tuple[tuple[str, str], ...] = (
        ("Clock page", ""),
        ("x", "say hello"),
    )

    def __init__(self) -> None:
        self.pressed: list[int] = []

    def loaded(self, snapshot: object) -> None:
        pass

    def subtitle(self, frame: Frame, height: int, width: int) -> str:
        return "the time"

    def footer(self, frame: Frame, after: object, pages: object) -> str:
        return f"x hello   Tab {getattr(after, 'label', '')}"

    def handle(self, key: int, frame: Frame) -> bool:
        self.pressed.append(key)
        return key == ord("x")

    def draw(self, frame: Frame, height: int, width: int) -> None:
        frame.screen.put(2, 1, "TICK TOCK", 0)
