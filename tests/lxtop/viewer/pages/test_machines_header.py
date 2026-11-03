"""view_machines: the big-number tiles at the top of the machines page."""

from __future__ import annotations

from pathlib import Path

from lxtop.core import render
from lxtop.viewer import app as view
from lxtop.viewer.pages import machines_header
from tests.support.curses_win import FakeWin, frame_of


def test_machine_tiles_show_the_trainer_in_big_numbers() -> None:
    app = view.App(FakeWin(60, 213), Path("/nonexistent"), render.UNICODE)
    app.snapshot = {
        "uplinks": ["eno1"],
        "host": {
            "cpu": {"busy": 0.25, "count": 16, "cores": [0.1] * 16},
            "mem": {"used": 22 * 2**30, "total": 62 * 2**30, "swap_used": 0, "swap_total": 0},
            "gpus": [{"util": 40, "mem_used_mib": 2048, "mem_total_mib": 16384, "temp_c": 55}],
            "temps": [{"chip": "k10temp", "label": "Tctl", "c": 61.0}],
            "fs": [{"mount": "/", "used": 100 * 2**30, "total": 400 * 2**30}],
            "disks": [{"name": "nvme0n1", "read": 1000, "write": 2000}],
            "net": [{"name": "eno1", "rx": 125_000, "tx": 25_000}, {"name": "lxdbr0", "rx": 9e9}],
        },
    }
    tiles = {t[0]: t for t in machines_header.machine_tiles(frame_of(app))}
    assert list(tiles) == ["CPU", "MEMORY", "GPU", "HOTTEST", "ROOT DISK", "INTERNET"]
    assert tiles["CPU"][1:3] == ("4.0", "cores") and tiles["CPU"][5] == 0.25
    assert tiles["MEMORY"][1] == "22.0" and "of 62 GB" in tiles["MEMORY"][3]
    assert tiles["GPU"][1] == "40" and "vram 2.0/16G" in tiles["GPU"][3]
    assert tiles["HOTTEST"][1:3] == ("61", "°C cpu")
    assert tiles["ROOT DISK"][1] == "100" and tiles["ROOT DISK"][5] == 0.25
    assert tiles["INTERNET"][1:3] == render.speed_parts(125_000)  # only the uplink counts


def test_machine_tiles_skip_what_the_host_does_not_have() -> None:
    app = view.App(FakeWin(60, 213), Path("/nonexistent"), render.UNICODE)
    app.snapshot = {"host": {"cpu": {"busy": 0.0, "count": 4}, "mem": {"total": 1}}}
    assert [t[0] for t in machines_header.machine_tiles(frame_of(app))] == [
        "CPU",
        "MEMORY",
        "INTERNET",
    ]
