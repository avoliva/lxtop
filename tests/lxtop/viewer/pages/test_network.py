from __future__ import annotations

from typing import Any

import pytest

from lxtop.collector import checks
from lxtop.looks import theme
from lxtop.viewer import app as view
from lxtop.viewer.pages import network as network_view
from lxtop.viewer.pages.network import wrap
from tests.support.curses_win import make_app
from tests.support.snapshot import NOW, collector, full_snapshot

pytestmark = pytest.mark.usefixtures("headless")


@pytest.mark.parametrize("size", [(40, 120), (25, 80)])
def test_network_page_draws_at_two_sizes(size: tuple[int, int]) -> None:
    app = make_app(theme.DEFAULT, "network", *size)
    app.draw()
    assert "NETWORK" in app.screen.win.grid()


def test_wrap_of_nothing_is_empty_and_the_last_line_is_cut() -> None:
    assert network_view.wrap("", 20, 2) == []
    lines = network_view.wrap("one two three four five six seven", 10, 2)
    assert len(lines) == 2 and lines[1].endswith("…")


def network_app(size: tuple[int, int], **kwargs: Any) -> view.App:
    """The network page over a snapshot the real Collector built with the given slow checks."""
    app: view.App = make_app(theme.DEFAULT, "network", *size)
    app.snapshot = full_snapshot(**kwargs)
    return app


def speed_job() -> checks.Every:
    return checks.Every("speed", 1800.0, lambda: {"bits": 250e6}, clock=lambda: NOW)


def api_job() -> checks.Every:
    steps = {"ms": 220.0, "dns": 1.0, "connect": 20.0, "tls": 54.0, "first": 220.0}
    return checks.Every("api_service", 20.0, lambda: steps, clock=lambda: NOW)


def outside_the_window(app: view.App, size: tuple[int, int]) -> list[tuple[int, int]]:
    h, w = size
    return [pos for pos in app.screen.win.cells if not (0 <= pos[0] < h and 0 <= pos[1] < w)]


def test_the_speed_tile_shows_the_latest_download() -> None:
    app = network_app((60, 213), jobs=[speed_job()])
    app.draw()
    assert "at 08:00 · best" in app.screen.win.grid()


def test_the_api_step_line_shows_lookup_connect_tls_and_first_byte() -> None:
    app = network_app((60, 213), jobs=[api_job()])
    app.draw()
    assert "lookup 1 · connect 20 · TLS 54 · first byte 220 ms" in app.screen.win.grid()


def test_the_trace_section_names_the_hop_where_loss_starts() -> None:
    built, clock = collector(jobs=[speed_job()])
    built.trace = checks.Trigger(
        "trace",
        600.0,
        lambda: {"first_lossy": {"hop": 5, "host": "x.example", "loss": 12.0}},
        clock=lambda: NOW,
    )
    built.trace.fire(background=False)
    clock.step()
    app = make_app(theme.DEFAULT, "network", 60, 213)
    app.snapshot = built.tick()
    app.snapshot["time"] = NOW
    app.draw()
    assert "loss starts at hop 5" in app.screen.win.grid()


def test_wrap_keeps_whole_words_and_cuts_the_last_line() -> None:
    assert wrap("one two three four", 9, 2) == ["one two", "three fo…"]
    assert wrap("short", 20, 2) == ["short"]
