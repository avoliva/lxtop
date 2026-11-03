"""The series the collector records each tick beyond CPU, memory and traffic."""

from __future__ import annotations

from typing import Any

from lxtop.collector import series


def test_guest_numbers_fill_what_lxd_lacks() -> None:
    inst: dict[str, Any] = {
        "mem_used": 0.0,
        "mem_total": 0.0,
        "cpu_cores": 0.0,
        "probe": {"mem": {"used": 5, "total": 10}, "cpu": {"busy": 0.5, "count": 4}},
    }
    series.guest_numbers(inst)
    assert (inst["mem_used"], inst["mem_total"], inst["cpu_cores"]) == (5, 10, 2.0)
    kept: dict[str, Any] = {"mem_used": 7, "cpu_cores": 1.0, "probe": inst["probe"]}
    series.guest_numbers(kept)
    assert (kept["mem_used"], kept["cpu_cores"]) == (7, 1.0)


def test_a_ping_result_counts_once_however_many_ticks_show_it() -> None:
    rounds: dict[str, Any] = {}
    snap = {"pings": {"service": {"target": "a", "ms": -1.0, "round": 0}}}
    first = series.network_series(snap, rounds)
    again = series.network_series(snap, rounds)
    snap["pings"]["service"] = {"target": "a", "ms": 20.0, "round": 5}
    fresh = series.network_series(snap, rounds)
    pick = [v for k, n, v in first + again + fresh if n == "ping_service"]
    assert pick == [-1.0, -2.0, 20.0]


def test_guest_traffic_fills_in_when_lxd_reports_none() -> None:
    nets = [
        {"name": "enp5s0", "rx": 257.0, "tx": 158.0},
        {"name": "docker0", "rx": 900.0, "tx": 900.0},
        {"name": "veth01baf7b", "rx": 5.0, "tx": 5.0},
        {"name": "br-1bc2b8935b7f", "rx": 5.0, "tx": 5.0},
    ]
    inst: dict[str, Any] = {"rx": 0.0, "tx": 0.0, "probe": {"net": nets}}
    series.guest_numbers(inst)
    assert (inst["rx"], inst["tx"]) == (257.0, 158.0)
    lxd_has: dict[str, Any] = {"rx": 10.0, "tx": 0.0, "probe": {"net": nets}}
    series.guest_numbers(lxd_has)
    assert (lxd_has["rx"], lxd_has["tx"]) == (10.0, 0.0)


def test_recent_loss_ignores_skipped_ticks() -> None:
    history = {"net": {"ping_internet": [15.0, -2.0, -1.0, 15.0, -2.0]}}
    assert series.recent_loss(history, 5) == 1 / 3
    assert series.recent_loss({}, 30) == 0.0
