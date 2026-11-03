from __future__ import annotations

from typing import Any

from lxtop.core import model
from tests.support.snapshot import lxd_instance


def test_instance_rows_turn_counters_into_rates() -> None:
    rates = model.Rates()
    model.instance_rows([lxd_instance("app", 0, 0)], rates, now=10.0, host_cores=32)
    (row,) = model.instance_rows([lxd_instance("app", 3e9, 2000)], rates, now=12.0, host_cores=32)
    assert row["key"] == "i:apps/app"
    assert row["type"] == "vm"
    assert row["cpu_cores"] == 1.5
    assert row["cpu_cap"] == 6
    assert row["rx"] == 1000.0
    assert row["mem_total"] == 12 * 2**30
    assert row["addresses"] == ["10.200.3.10 (enp5s0)"]
    assert row["running"] is True


def test_stopped_instance_and_garbage_fields() -> None:
    bad: dict[str, Any] = {"name": "x", "status": "Stopped", "state": None, "config": "nope"}
    (row,) = model.instance_rows([bad, "not a dict"][:1], model.Rates(), 1.0, 8)
    assert row["running"] is False
    assert row["cpu_cap"] == 8
    assert row["mem_used"] == 0
    (junk,) = model.instance_rows(["not a dict"], model.Rates(), 1.0, 8)
    assert junk["name"] == "?"


def test_cpu_limit_forms() -> None:
    assert model.cpu_limit("6", 32) == 6
    assert model.cpu_limit("0-3", 32) == 4
    assert model.cpu_limit("1,3,8-9", 32) == 4
    assert model.cpu_limit("", 32) == 32
    assert model.cpu_limit("weird", 32) == 32


def test_rates_ignore_counter_resets() -> None:
    rates = model.Rates()
    assert rates.rate("a", 100, 1.0) == 0.0
    assert rates.rate("a", 300, 3.0) == 100.0
    assert rates.rate("a", 50, 5.0) == 0.0  # instance restarted
    assert rates.rate("a", 150, 6.0) == 100.0


def test_history_is_bounded_and_forgets_gone_items() -> None:
    history = model.History(length=3)
    for i in range(5):
        history.push("a", i, 0, 0, 0)
        if i == 0:
            history.push("gone", 1, 1, 1, 1)
        history.end_tick()
    data = history.export()
    assert data["a"]["cpu"] == [2, 3, 4]
    assert "gone" not in data


def snapshot() -> dict[str, Any]:
    container = {
        "id": "abcdef1234567890",
        "name": "app-worker-1",
        "state": "running",
        "cpu_cores": 1.0,
        "cpu_cap": 2,
        "mem_used": 100,
        "mem_limit": 400,
    }
    stopped = {"id": "ffff", "name": "old", "state": "exited"}
    return {
        "uplinks": ["eno1"],
        "host": {
            "hostname": "host",
            "cpu": {"busy": 0.25, "count": 32},
            "mem": {"used": 10, "total": 100},
            "net": [{"name": "eno1", "rx": 5, "tx": 6}, {"name": "app", "rx": 99, "tx": 99}],
            "docker": {"containers": [stopped]},
        },
        "instances": [
            {
                "key": "i:apps/app",
                "name": "app",
                "type": "vm",
                "status": "Running",
                "cpu_cores": 3,
                "cpu_cap": 6,
                "probe": {"docker": {"containers": [container]}},
            },
            {"key": "i:apps/demo", "name": "demo", "type": "vm", "status": "Stopped"},
        ],
    }


def test_tree_nests_containers_under_their_instance() -> None:
    rows = model.tree(snapshot(), expanded={"host", "i:apps/app"})
    assert [(r.key, r.depth) for r in rows] == [
        ("host", 0),
        ("host/c:ffff", 1),
        ("i:apps/app", 0),
        ("i:apps/app/c:abcdef123456", 1),
        ("i:apps/demo", 0),
    ]
    host, _, app, worker, _ = rows
    assert host.rx == 5  # uplinks only, not the bridges
    assert app.cpu == 0.5
    assert app.children == 1
    assert worker.cpu == 0.5


def test_tree_folds_and_sorts() -> None:
    rows = model.tree(snapshot(), expanded=set(), sort="cpu")
    assert [r.key for r in rows] == ["host", "i:apps/app", "i:apps/demo"]


def test_history_put_takes_any_series_name() -> None:
    history = model.History(length=2)
    for value in (1.0, 2.0, 3.0):
        history.put("net", "ping_router", value)
        history.end_tick()
    history.push("net", 0, 0, 0, 0)
    data = history.export()
    assert data["net"]["ping_router"] == [2.0, 3.0]
    assert data["net"]["cpu"] == [0.0]
