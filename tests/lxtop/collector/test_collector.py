from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from lxtop.collector import checks, instances, kernel, memory, probe, units
from lxtop.collector import collector as collect
from tests.support.clock import Clock
from tests.support.probes import FakeProbe


class FakeSampler(probe.Sampler):
    def sample(self) -> probe.Sample:
        return {
            "hostname": "host",
            "cpu": {"busy": 0.5, "count": 4},
            "mem": {"used": 1, "total": 2},
            "docker": {"containers": [{"id": "c1", "name": "x", "state": "running"}]},
        }


@pytest.fixture(autouse=True)
def no_host_readers(monkeypatch: pytest.MonkeyPatch) -> None:
    """The host's own readers read nothing real: run() starts their threads, and on a
    machine with systemd they would call systemctl and journalctl for real."""
    monkeypatch.setattr(memory.Reader, "read", lambda self: {})
    monkeypatch.setattr(kernel, "read", lambda: {})
    monkeypatch.setattr(units.Reader, "read", lambda self: {})


def lxd() -> list[Any]:
    return [
        {"name": "app", "project": "apps", "status": "Running", "state": {"cpu": {"usage": 0}}},
        {"name": "demo", "project": "apps", "status": "Stopped"},
    ]


def test_collector_survives_lxd_errors(tmp_path: Path) -> None:
    def broken() -> list[Any]:
        raise PermissionError("permission denied")

    clock = Clock(100.0)
    probes = instances.Probes(lambda p, n: FakeProbe(p, n, clock, []), clock)
    settings = collect.Settings(out=tmp_path / "state.json")
    snap = collect.Collector(settings, FakeSampler(), broken, probes, clock).tick()
    assert snap["instances"] == []
    assert snap["errors"] == ["LXD: permission denied"]


class FakePinger:
    def latest(self) -> dict[str, dict[str, Any]]:
        return {
            "router": {"target": "10.0.0.1", "ms": 0.5},
            "internet": {"target": "1.1.1.1", "ms": -1.0},
            "service": {"target": "api.github.com", "error": "no permission to ping"},
        }


class NetSampler(FakeSampler):
    def sample(self) -> probe.Sample:
        out = super().sample()
        out["tcp"] = {"out": 200.0, "retrans": 10.0}
        out["net"] = [{"name": "eno1", "rx": 5, "tx": 6, "faults": 2}, {"name": "x0", "faults": 9}]
        out["dns"] = {"lookups": 10, "timeouts": 3, "seconds": 6.0}
        return out


class GuestProbe(FakeProbe):
    def start(self) -> None:
        super().start()
        self.latest = {
            "tcp": {"out": 0.0, "retrans": 0.0},
            "tunnel": {"req": 4.0, "bad": 0.5, "connections": 4},
            "docker": {
                "containers": [
                    {"id": "agent1", "state": "running", "sandbox_net": 1500, "labels": {}}
                ]
            },
        }


def test_speed_results_are_kept_once_each() -> None:
    settings = collect.Settings(out=Path("/nonexistent/x.json"), ping=False, checks=False)
    collector = collect.Collector(settings, FakeSampler(), lxd, probes=None, clock=Clock(100.0))
    collector._keep_speed({"bits": 250e6, "round": 1, "at": 1.0})
    collector._keep_speed({"bits": 250e6, "round": 1, "at": 1.0})
    collector._keep_speed({"error": "timed out", "round": 2})
    collector._keep_speed({"bits": 300e6, "round": 3, "at": 2.0})
    assert [s["bits"] for s in collector.speeds] == [250e6, 300e6]


class StopRun(Exception):
    """Raised by the fake sleep to end `Collector.run`, which loops until it is interrupted."""


class RecordingEvery(checks.Every):
    """A check that logs start and stop and spawns no thread."""

    def __init__(self, name: str, log: list[str]) -> None:
        super().__init__(name, 5.0, lambda: {})
        self.log = log

    def start(self) -> None:
        self.log.append(f"start {self.name}")

    def stop(self) -> None:
        self.log.append(f"stop {self.name}")


def make_collector(tmp_path: Path, clock: Clock, log: list[str]) -> collect.Collector:
    """A Collector for `run`: fake probes, no pinger, no real checks, and recording jobs."""
    probes = instances.Probes(lambda p, n: FakeProbe(p, n, clock, log), clock)
    settings = collect.Settings(
        out=tmp_path / "run" / "state.json", interval=2, ping=False, checks=False
    )
    built = collect.Collector(settings, FakeSampler(), lxd, probes, clock)
    built.jobs = [RecordingEvery("a", log)]
    return built


def test_run_writes_a_snapshot_each_interval_and_sleeps_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    collector = make_collector(tmp_path, clock, [])
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.now += seconds
        if len(sleeps) == 3:
            raise StopRun

    monkeypatch.setattr(time, "sleep", sleep)
    with pytest.raises(StopRun):
        collector.run()
    written = json.loads((tmp_path / "run" / "state.json").read_text())
    assert sleeps == [2.0, 2.0, 2.0]
    assert written["instances"][0]["key"] == "i:apps/app"


def test_run_once_writes_one_snapshot_and_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector = make_collector(tmp_path, Clock(), [])

    def sleep(seconds: float) -> None:
        raise AssertionError("run(once=True) must not sleep")

    monkeypatch.setattr(time, "sleep", sleep)
    collector.run(once=True)
    assert (tmp_path / "run" / "state.json").exists()


def test_run_skips_the_ticks_it_missed_after_a_stall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    collector = make_collector(tmp_path, clock, [])
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 1:
            clock.now += 10.0  # the machine stalled for five intervals
        if len(sleeps) == 2:
            raise StopRun

    monkeypatch.setattr(time, "sleep", sleep)
    with pytest.raises(StopRun):
        collector.run()
    assert sleeps == [2.0, 2.0]


def test_a_missing_user_has_no_slice_to_read() -> None:
    assert collect.user_id("no-such-user-here") == -1
