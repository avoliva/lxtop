from __future__ import annotations

from typing import Any

from lxtop.core import network as net

LOST = -1.0


def test_ping_stats() -> None:
    stats = net.ping_stats([10.0, 12.0, LOST, 11.0, 40.0])
    assert stats.now == 40.0
    assert stats.median == 11.5
    assert stats.worst == 40.0
    assert stats.lost == 1
    assert stats.count == 5
    assert round(stats.loss, 2) == 0.2
    empty = net.ping_stats([])
    assert empty.count == 0 and empty.loss == 0.0 and empty.now is None


def test_bad_samples_flags_loss_and_spikes_against_the_usual() -> None:
    values = [10.0] * 10 + [LOST, 95.0, 30.0, 10.0]
    marks = net.marks(values, "internet")
    assert marks[:10] == [""] * 10
    assert marks[10:] == ["lost", "slow", "", ""]  # 30 ms is under 10 + 50
    # The router is near zero: a few milliseconds is not a hiccup, 25 is.
    router = net.marks([0.5] * 10 + [4.0, 25.0], "router")
    assert router[-2:] == ["", "slow"]


def series(**values: list[float]) -> dict[str, Any]:
    return {"history": {"net": values}, "interval": 2, "instances": []}


def test_hiccups_group_runs_and_say_where() -> None:
    snap = series(
        ping_router=[1.0] * 20,
        ping_internet=[15.0] * 5 + [LOST, LOST, LOST] + [15.0] * 6 + [LOST] + [15.0] * 5,
    )
    found = net.hiccups(snap, now=1000.0)
    assert [(h.where, h.samples) for h in found] == [("provider", 1), ("provider", 3)]
    newest, older = found
    assert newest.what == "1 ping to the internet lost"
    assert older.what == "3 pings in a row to the internet lost"
    assert older.when == 1000.0 - 15 * 2  # 20 samples, the run starts at index 5
    assert older.seconds == 6.0


def test_hiccups_from_dns_retransmits_and_visitors() -> None:
    snap = series(dns_timeouts=[0.0, 1.0, 1.0, 0.0], retrans=[0.0, 0.2, 0.0, 0.0])
    snap["instances"] = [{"key": "i:apps/app", "name": "app"}]
    snap["history"]["i:apps/app"] = {"dns_timeouts": [0, 0, 0.4, 0.2], "bad": [0, 0, 0, 2.0]}
    found = {(h.where, h.what) for h in net.hiccups(snap, now=100.0)}
    assert ("dns", "2 name lookups timed out on the host") in found
    assert ("dns", "1 name lookup timed out in the app VM") in found
    assert ("link", "20% of TCP packets sent again") in found
    assert ("site", "4 visitor requests to app failed") in found


def test_diagnosis_names_the_layer() -> None:
    healthy = series(ping_router=[1.0] * 30, ping_internet=[15.0] * 30)
    sentence, severity = net.diagnosis(healthy)
    assert severity == 0
    assert sentence.startswith("The connection looks healthy")
    provider = series(ping_router=[1.0] * 30, ping_internet=[15.0] * 20 + [LOST] * 10)
    sentence, severity = net.diagnosis(provider)
    assert severity == 2
    assert "past your router" in sentence and "33%" in sentence
    home = series(ping_router=[1.0] * 25 + [LOST] * 5, ping_internet=[15.0] * 25 + [LOST] * 5)
    assert "inside the house" in net.diagnosis(home)[0]
    api = series(
        ping_router=[1.0] * 30, ping_internet=[15.0] * 30, ping_service=[20.0] * 20 + [LOST] * 3
    )
    assert "Service" in net.diagnosis(api)[0]
    assert net.diagnosis(series())[0] == "No ping results yet: is the collector running as root?"


def test_worst_keeps_a_lost_ping_visible_when_squeezed() -> None:
    values = [10.0, LOST, 12.0, 11.0, 50.0, 9.0]
    assert net.worst(values, 3) == [LOST, 12.0, 50.0]
    assert net.worst(values, 10) == values


def test_site_and_machine_rows() -> None:
    snap: dict[str, Any] = {
        "interval": 2,
        "instances": [
            {
                "key": "i:apps/website",
                "name": "website",
                "rx": 100.0,
                "tx": 900.0,
                "probe": {"tunnel": {"req": 0.5, "bad": 0.0, "connections": 4, "total": 77}},
            },
            {"key": "i:apps/app", "name": "app", "rx": 5000.0, "tx": 10.0, "probe": {}},
            {"key": "i:apps/off", "name": "off", "running": False},
        ],
        "history": {"i:apps/website": {"req": [0.0, 0.5], "rx": [1.0], "tx": [2.0]}},
    }
    sites = net.site_rows(snap)
    assert [(s.name, s.per_minute, s.connections, s.total) for s in sites] == [
        ("website", 30.0, 4, 77)
    ]
    machines = net.machine_rows(snap)
    assert [m.name for m in machines] == ["app", "website"]  # busiest first
    assert machines[1].rx_history == [1.0] and machines[1].tx_history == [2.0]


def test_skipped_ticks_count_for_nothing() -> None:
    skip = net.SKIPPED
    values = [20.0, skip, skip, LOST, skip, 21.0, skip]
    stats = net.ping_stats(values)
    assert (stats.count, stats.lost, stats.now) == (3, 1, 21.0)
    assert net.marks(values, "service") == ["", "", "", "lost", "", "", ""]
    assert net.worst([skip, skip, 5.0, skip], 2) == [skip, 5.0]


def test_trouble_marks_line_up_with_a_chart() -> None:
    skip = net.SKIPPED
    snap = series(
        ping_internet=[15.0, LOST, 15.0, 15.0],
        ping_service=[20.0, skip, skip, 9000.0],  # the last check was very slow
    )
    # Six samples of history (the chart's length); the pings cover the newest four.
    assert net.trouble(snap, 6, 6) == ["", "", "", "lost", "", "slow"]
    # Squeezed into three columns, each takes its worst moment.
    assert net.trouble(snap, 6, 3) == ["", "lost", "slow"]
    assert net.trouble(series(), 6, 3) == ["", "", ""]


GATEWAY = {
    "down": [
        {"id": "20", "freq": 975.0, "power": -1.9, "snr": 45.0, "lost_per_min": 18288.0,
         "lost_share": 0.43},
        {"id": "194", "freq": 1086.0, "power": -34.9, "snr": 40.3, "lost_per_min": 18288.0,
         "lost_share": 0.43},
        {"id": "17", "freq": 957.0, "power": -1.6, "snr": 44.8, "lost_per_min": 0.0,
         "lost_share": 0.0},
    ],
    "round": 3,
}  # fmt: skip
