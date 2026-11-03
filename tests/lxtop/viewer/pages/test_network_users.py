"""The network page's lower half: traffic per machine, visitors per site, and per agent."""

from __future__ import annotations

import pytest

from lxtop.looks import theme
from lxtop.viewer.pages import network_users
from tests.support.curses_win import frame_of, make_app

pytestmark = pytest.mark.usefixtures("headless")


def drawn(draw: str, chart: bool, **snapshot: object) -> str:
    app = make_app(theme.DEFAULT, "network", 40, 120)
    if snapshot:
        app.snapshot = dict(snapshot)
    frame = frame_of(app)
    frame.screen.begin()
    where = (0, 0, 100, 14)
    getattr(network_users, f"draw_{draw}")(frame.screen, frame.snapshot, where, chart=chart)
    grid: str = frame.screen.win.grid()
    return grid


@pytest.mark.parametrize("chart", [True, False])
def test_by_machine_lists_each_instance_with_its_traffic(chart: bool) -> None:
    grid = drawn("machines", chart)

    assert "BY MACHINE" in grid and "app" in grid and "↓" in grid


def test_visitors_say_so_when_no_tunnel_reports_any() -> None:
    assert "No tunnel reports visitors." in drawn("sites", False, host={}, instances=[])


SITES = {
    "interval": 2,
    "instances": [
        {"key": "i:apps/app", "name": "app", "probe": {"tunnel": {"req": 2.0, "connections": 4}}},
        {
            "key": "i:apps/shop",
            "name": "shop",
            "probe": {"tunnel": {"req": 1.0, "bad": 0.5, "connections": 1}},
        },
        {
            "key": "i:apps/own",
            "name": "own",
            "probe": {"docker": {"containers": [{"name": "app-cloudflared-1"}]}},
        },
    ],
    "history": {"i:apps/app": {"req": [1.0, 2.0, 2.0]}, "i:apps/shop": {"req": [0.5, 1.0]}},
}


@pytest.mark.parametrize("chart", [True, False])
def test_visitors_per_site_busiest_first_with_failures_and_silent_tunnels(chart: bool) -> None:
    grid = drawn("sites", chart, **SITES)
    lines = grid.splitlines()
    app = next(i for i, line in enumerate(lines) if "app" in line and "/min" in line)
    shop = next(i for i, line in enumerate(lines) if "shop" in line and "/min" in line)

    assert app < shop
    assert "120/min" in lines[app] and "tunnel 4/4" in lines[app]
    assert "30 failed/min" in lines[shop] and "tunnel 1/4" in lines[shop]
    assert "its own tunnel: no numbers" in grid


def test_a_machine_resending_packets_says_how_much() -> None:
    snap = {
        "instances": [
            {
                "key": "i:apps/a",
                "name": "lossy",
                "rx": 10.0,
                "probe": {"tcp": {"out": 100, "retrans": 8}},
            },
            {
                "key": "i:apps/b",
                "name": "fine",
                "rx": 5.0,
                "probe": {"tcp": {"out": 100, "retrans": 0}},
            },
        ]
    }

    lines = drawn("machines", False, **snap).splitlines()

    assert "8% resent" in next(line for line in lines if "lossy" in line)
    assert "resent" not in next(line for line in lines if "fine" in line)
