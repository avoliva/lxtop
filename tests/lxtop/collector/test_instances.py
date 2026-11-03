"""One probe per running instance: reading its lines, starting and restarting it."""

from __future__ import annotations

import io
import sys
import threading
from pathlib import Path

import pytest

from lxtop.collector import instances, probe
from tests.support.clock import Clock
from tests.support.probes import FakeProbe


def test_read_line_drops_overlong_lines() -> None:
    stream = io.BytesIO(b"x" * 50 + b"\n" + b'{"ok":1}\n')
    assert instances.read_line(stream, limit=10) == b""
    assert instances.read_line(stream, limit=10) == b'{"ok":1}\n'
    assert instances.read_line(stream, limit=10) is None


def test_decode_accepts_objects_only() -> None:
    assert instances.decode(b'{"a":1}') == {"a": 1}
    assert instances.decode(b"[1,2]") is None
    assert instances.decode(b"not json") is None


def test_trim_caps_guest_lists() -> None:
    sample = {"procs": list(range(100)), "docker": {"containers": list(range(500))}, "net": "x"}
    out = instances.trim(sample)
    assert len(out["procs"]) == probe.TOP_PROCS
    assert len(out["docker"]["containers"]) == probe.MAX_CONTAINERS
    assert out["net"] == []


def test_exec_argv_matches_the_sudoers_word_order() -> None:
    argv = instances.exec_argv("/usr/sbin/lxc", "apps", "app", 2.0, sudo=True)
    assert argv[:8] == ["sudo", "-n", "/usr/sbin/lxc", "--project", "apps", "exec", "app", "--"]
    assert argv[8:12] == ["python3", "-I", "-c", instances.BOOT]
    assert len(" ".join(argv)) < 300  # the probe's source goes on stdin, not here
    assert argv[-2:] == ["--interval", "2.0"]
    assert instances.exec_argv("lxc", "default", "llm", 2.0, sudo=False)[0] == "lxc"


def test_probes_follow_running_instances_and_restart_after_a_pause() -> None:
    clock = Clock(100.0)
    log: list[str] = []
    probes = instances.Probes(lambda p, n: FakeProbe(p, n, clock, log), clock)
    probes.sync([("i:apps/app", "apps", "app"), ("i:apps/demo", "apps", "demo")])
    assert log == ["start apps/app", "start apps/demo"]
    dead = probes.probes["i:apps/app"]
    assert isinstance(dead, FakeProbe)
    dead.alive = False
    clock.now += 5
    probes.sync([("i:apps/app", "apps", "app")])
    assert log[-1] == "stop apps/demo"  # demo stopped; app not restarted yet
    clock.now += instances.RESTART_AFTER
    probes.sync([("i:apps/app", "apps", "app")])
    assert log[-1] == "start apps/app"


def test_probe_status() -> None:
    clock = Clock(100.0)
    item = FakeProbe("apps", "app", clock, [])
    item.start()
    assert item.status(2) == "starting"
    item.latest, item.latest_at = {"x": 1}, clock.now
    assert item.status(2) == "ok"
    clock.now += 7
    assert item.status(2) == "stale"
    item.alive = False
    item.error = "Error: Instance is not running"
    assert item.status(2) == "error: Error: Instance is not running"


class SampleSeen:
    """A probe clock that stands at 0.0 and sets `seen` on its second read: `start` reads it once
    and the reader thread reads it once per sample. Standing still keeps `status` deterministic
    whether or not the reader thread has stored the sample's time yet."""

    def __init__(self) -> None:
        self.reads = 0
        self.seen = threading.Event()

    def __call__(self) -> float:
        self.reads += 1
        if self.reads >= 2:
            self.seen.set()
        return 0.0


@pytest.mark.skipif(not Path("/proc/stat").exists(), reason="needs Linux /proc")
def test_a_real_probe_process_reports_samples() -> None:
    """Runs probe.py as the collector would, here with the local Python instead of lxc exec."""
    source = Path(probe.__file__).read_text()
    argv = [sys.executable, "-I", "-c", instances.BOOT, "--interval", "0.5"]
    clock = SampleSeen()
    item = instances.InstanceProbe(argv, clock=clock, source=source)
    item.start()
    try:
        assert clock.seen.wait(15), item.error
        assert item.latest is not None, item.error
        assert "cpu" in item.latest and "mem" in item.latest
        assert item.status(0.5) == "ok"
    finally:
        item.stop()


def test_a_probe_child_printing_json_lines_sets_latest_and_reports_ok() -> None:
    """A real child process and a real pipe, with no /proc: the child prints one sample."""
    script = (
        "import json, time; "
        "print(json.dumps({'cpu': {'busy': 0.5, 'count': 4}, 'mem': {'used': 1, 'total': 2}}), "
        "flush=True); time.sleep(30)"
    )
    clock = SampleSeen()
    item = instances.InstanceProbe([sys.executable, "-I", "-c", script], clock=clock)
    item.start()
    try:
        assert clock.seen.wait(15), item.error
        assert item.latest is not None, item.error
        assert item.latest["cpu"] == {"busy": 0.5, "count": 4}
        assert item.latest["mem"] == {"used": 1, "total": 2}
        assert item.status(2) == "ok"
        item.stop()
        assert not item.running()
    finally:
        item.stop()
