"""view_tree: the facts listed for a machine, the process table and the label list of the
machines page's detail pane."""

from __future__ import annotations

import pytest

from lxtop.core.model import Row
from lxtop.core.snapshot import Json
from lxtop.looks import theme
from lxtop.viewer import app as view
from lxtop.viewer.pages import machines_tree
from tests.support.curses_win import frame_of, make_app

pytestmark = pytest.mark.usefixtures("headless")

GIB = 2**30


def app_for_drawing() -> view.App:
    """A fresh app per drawing test: the fake window keeps what an earlier draw put on it."""
    app: view.App = make_app(theme.DEFAULT, "machines", 40, 120)
    app.screen.begin()
    return app


def row(kind: str, data: Json) -> Row:
    return Row(
        key="k",
        depth=0,
        kind=kind,
        name="n",
        state="running",
        cpu=0.0,
        mem_used=0.0,
        mem_total=0.0,
        rx=0.0,
        tx=0.0,
        children=0,
        data=data,
    )


HOST = {
    "uptime": 262800,
    "cpu": {"count": 16},
    "docker": {"containers": [{"state": "running"}, {"state": "exited"}]},
    "fs": [
        {"mount": "/", "used": 100 * GIB, "total": 400 * GIB},
        {"mount": "/srv/data/long-name", "used": 2 * GIB, "total": 8 * GIB},
    ],
    "gpus": [{"name": "RTX 4070 Ti", "fan_pct": 30.4, "power_w": 31.5, "power_limit_w": 285.0}],
}


def test_host_facts_list_uptime_cores_docker_filesystems_and_gpu_power() -> None:
    facts = machines_tree.facts(frame_of(app_for_drawing()), row("host", HOST))

    assert facts == [
        ("uptime", "3d 1h"),
        ("cores", "16"),
        ("docker", "1 running, 2 in all"),
        ("/", "100.0G/400.0G (25%)"),
        ("/srv/data/", "2.0G/8.0G (25%)"),  # the mount name is cut to 10 characters
        ("gpu", "RTX 4070 Ti  fan 30%"),
        ("power", "32W of 285W"),
    ]


DOCKER = {
    "image": "nginx",
    "status": "Up 2 hours",
    "id": "a" * 64,
    "created": 1700000000,
    "cpu_limit": 2.0,
    "mem_limit": 4 * GIB,
    "pids": 7,
    "restarts": 3,
    "blk_read": 2048,
    "blk_write": 1024,
    "network_mode": "bridge",
    "ports": ["0.0.0.0:8080->80/tcp", "53/udp"],
    "labels": {"a": "1", "b": "2"},
}


def test_docker_facts_list_image_limits_ports_and_labels() -> None:
    facts = machines_tree.facts(frame_of(app_for_drawing()), row("docker", DOCKER))

    assert facts == [
        ("image", "nginx"),
        ("status", "Up 2 hours"),
        ("id", "aaaaaaaaaaaa"),
        ("created", "2023-11-14 22:13"),  # headless: localtime is UTC
        ("cpu limit", "2 cores"),
        ("mem limit", "4.0G"),
        ("pids", "7"),
        ("restarts", "3"),
        ("block io", "r 2.0K  w 1.0K"),
        ("network", "bridge"),
        ("ports", "0.0.0.0:8080->80/tcp, 53/udp"),
        ("labels", "2"),
    ]


def test_docker_facts_without_limits_or_ports_say_none() -> None:
    facts = dict(machines_tree.facts(frame_of(app_for_drawing()), row("docker", {})))

    assert (facts["cpu limit"], facts["ports"], facts["network"]) == ("none", "none", "?")


VM = {
    "project": "apps",
    "limits_cpu": "6",
    "limits_memory": "12GiB",
    "disk_used": 5 * GIB,
    "disk_total": 64 * GIB,
    "processes": 140,
    "addresses": ["10.200.3.10 (enp5s0)"],
    "probe_status": "off",
}


def test_instance_facts_without_a_probe_stop_at_the_probe_status() -> None:
    facts = machines_tree.facts(frame_of(app_for_drawing()), row("vm", VM))

    assert facts == [
        ("project", "apps"),
        ("limits", "cpu 6  mem 12GiB"),
        ("disk", "5.0G of 64.0G"),
        ("processes", "140"),
        ("address", "10.200.3.10 (enp5s0)"),
        ("probe", "off"),
    ]


def test_instance_facts_with_a_probe_add_guest_load_memory_cpu_and_filesystems() -> None:
    probe = {
        "docker": {"containers": [{"state": "running"}]},
        "uptime": 90061,
        "load": [0.5, 0.4, 0.3],
        "mem": {"used": 2 * GIB, "cached": GIB},
        "cpu": {"busy": 0.125, "count": 6},
        "fs": [
            {"mount": "/", "used": 10 * GIB, "total": 40 * GIB},
            {"mount": "/var/lib/docker", "used": GIB, "total": 8 * GIB},
            {"mount": "/boot", "used": 1, "total": 2},
        ],
    }

    facts = machines_tree.facts(frame_of(app_for_drawing()), row("vm", {**VM, "probe": probe}))

    assert facts[6:] == [
        ("docker", "1 running, 1 in all"),
        ("guest up", "1d 1h"),
        ("guest load", "0.50 0.40 0.30"),
        ("guest mem", "2.0G used, 1.0G cache"),
        ("guest cpu", "12.5% of 6 cores"),
        ("/", "10.0G/40.0G (25%)"),
        ("/var/lib/d", "1.0G/8.0G (12%)"),  # only the first two filesystems
    ]


PROCS = {
    "cpu": {"count": 4},
    "procs": [
        {"pid": 4242, "user": "root", "cpu": 0.5, "rss": 2 * 2**20, "cmd": "python3 -m lxtop"},
        {"pid": 7, "user": "agent", "cpu": 0.0, "rss": 512, "cmd": "sleep 1"},
    ],
}


def test_draw_procs_lists_the_busiest_processes_under_a_header() -> None:
    app = app_for_drawing()

    machines_tree.draw_procs(frame_of(app), 0, 0, 60, 6, PROCS, row("host", PROCS))

    assert app.screen.win.grid().splitlines() == [
        "    PID USER         CPU    MEM  COMMAND",
        "   4242 root          50%   2.0M  python3 -m lxtop",
        "      7 agent          0%   512B  sleep 1",
    ]


def test_draw_procs_without_a_process_list_says_so_for_a_host() -> None:
    app = app_for_drawing()

    machines_tree.draw_procs(frame_of(app), 0, 0, 60, 6, {}, row("host", {}))

    assert app.screen.win.grid() == "no process list\n"


def test_draw_procs_without_a_process_list_names_the_probe_status_for_an_instance() -> None:
    app = app_for_drawing()

    machines_tree.draw_procs(frame_of(app), 0, 0, 60, 6, {}, row("vm", {"probe_status": "off"}))

    assert app.screen.win.grid() == "no data from inside (off)\n"


def test_draw_procs_draws_nothing_when_there_is_no_room() -> None:
    app = app_for_drawing()

    machines_tree.draw_procs(frame_of(app), 6, 0, 60, 6, PROCS, row("host", PROCS))

    assert app.screen.win.grid() == "\n"


def test_draw_labels_lists_sorted_labels_and_the_error() -> None:
    app = app_for_drawing()
    data = {"labels": {"b": "2", "a": "1"}, "error": "boom"}

    machines_tree.draw_labels(frame_of(app), 0, 0, 60, 6, data)

    lines = app.screen.win.grid().splitlines()
    assert lines[0] == "LABELS"
    assert lines[1].startswith("a ") and lines[1].endswith(" 1")
    assert lines[2].startswith("b ") and lines[2].endswith(" 2")
    assert lines[3] == "boom"


def test_a_vms_facts_say_what_it_costs_the_host_when_the_memory_reader_saw_it() -> None:
    app = app_for_drawing()
    app.snapshot["memory"] = {"vms": [{"name": "app", "rss": 7 * GIB}]}
    facts = machines_tree.facts(frame_of(app), row("vm", {**VM, "name": "app"}))
    assert facts[2] == ("host pays", "7.0G of the host's memory")
    assert "host pays" not in dict(machines_tree.facts(frame_of(app), row("vm", VM)))
