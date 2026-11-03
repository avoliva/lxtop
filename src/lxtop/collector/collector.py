"""The collector: samples the host, LXD and every running instance, and writes one snapshot file.

It runs as root (LXD's and Docker's sockets are root-only on the host) and reads no
input. The probes inside instances are in `instances.py`, the series it records in `series.py`.
"""

from __future__ import annotations

import contextlib
import json
import os
import pwd
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lxtop.collector import (
    checks,
    kernel,
    memory,
    ping,
    probe,
    units,
)
from lxtop.collector.instances import InstanceProbe, Probes, exec_argv
from lxtop.collector.series import API_CHECKS, guest_numbers, network_series, recent_loss
from lxtop.core import alerts as alerts_core
from lxtop.core import memory as memory_core
from lxtop.core import model
from lxtop.core import snapshot as sn
from lxtop.core.snapshot import VERSION, Json, Snap, Snapshot

LXD_SOCKET = "/var/snap/lxd/common/lxd/unix.socket"
INSTANCES_URL = "/1.0/instances?recursion=2&all-projects=true"
UPLINKS = ("eno1", "wlan0", "eth0", "enp0s3")


@dataclass
class Settings:
    out: Path
    interval: float = 2.0
    history_seconds: float = 600.0
    lxd_socket: str = LXD_SOCKET
    lxc: str = "lxc"
    sudo: bool = False
    probe_instances: bool = True
    ping: bool = True
    # The slower checks: model APIs over HTTPS, DNS, speed tests, traces (checks.py).
    checks: bool = True
    # The user whose slice, jobs and timers the memory and services pages show.
    user: str = "admin"


class Collector:
    def __init__(
        self,
        settings: Settings,
        sampler: probe.Sampler | None = None,
        lxd: Callable[[], list[Any]] | None = None,
        probes: Probes | None = None,
        clock: Callable[[], float] = time.monotonic,
        pinger: Any = None,
    ) -> None:
        self.settings = settings
        self.sampler = sampler or probe.Sampler()
        self.lxd = lxd or self._lxd
        self.clock = clock
        self.rates = model.Rates()
        self.history = model.History(max(10, int(settings.history_seconds / settings.interval)))
        self.probes = probes or Probes(self._make_probe, clock)
        if pinger is None and settings.ping:
            pinger = ping.Pinger(
                settings.interval, api_host=None if settings.checks else ping.API_HOST
            )
            self._start_pinger = True
        else:
            self._start_pinger = False
        self.pinger = pinger
        self._ping_rounds: dict[str, Any] = {}
        self.jobs: list[checks.Every] = make_jobs(settings) if settings.checks else []
        self.trace = checks.Trigger("trace", TRACE_PAUSE, checks.trace)
        # The host's own readers: cheap and local, so they run without the checks.
        uid = user_id(settings.user)
        self.memory = checks.Every("memory", MEMORY_INTERVAL, memory.Reader(uid).read)
        self.oom = checks.Every("oom", 60.0, kernel.read)
        self.units = checks.Every("units", 30.0, units.Reader(settings.user, uid).read)
        self.local_jobs = [self.memory, self.oom, self.units]
        self.speeds: list[Json] = []
        self._speed_round = 0

    def _lxd(self) -> list[Any]:
        found = probe.unix_get(self.settings.lxd_socket, INSTANCES_URL, timeout=10)
        return sn.as_list(sn.as_dict(found).get("metadata"))

    def _make_probe(self, project: str, name: str) -> InstanceProbe:
        s = self.settings
        argv = exec_argv(s.lxc, project, name, s.interval, s.sudo)
        return InstanceProbe(argv, self.clock, source=Path(probe.__file__).read_text())

    def tick(self) -> Snapshot:
        now = self.clock()
        host = self.sampler.sample()
        cores = int(sn.num(sn.as_dict(host.get("cpu")).get("count"), 1)) or 1
        errors: list[str] = []
        try:
            instances = model.instance_rows(self.lxd(), self.rates, now, cores)
        except (OSError, ValueError) as exc:
            instances = []
            errors.append(f"LXD: {exc}")
        if self.settings.probe_instances:
            self.probes.sync(
                [(i["key"], i["project"], i["name"]) for i in instances if i["running"]]
            )
        for inst in instances:
            found = self.probes.probes.get(inst["key"]) if self.settings.probe_instances else None
            inst["probe"] = found.latest if found else None
            inst["probe_status"] = found.status(self.settings.interval) if found else "off"
            guest_numbers(inst)
        checks = {job.name: job.latest() for job in self.jobs}
        self._keep_speed(checks.get("speed", {}))
        snapshot: Snapshot = {
            "version": VERSION,
            "time": time.time(),
            "interval": self.settings.interval,
            "uplinks": list(UPLINKS),
            "host": host,
            "instances": instances,
            "errors": errors,
            "pings": self.pinger.latest() if self.pinger is not None else {},
            "checks": checks,
            "memory": {**self.memory.latest(), "oom": self.oom.latest()},
            "units": self.units.latest(),
            "alerts": [],  # from the rest of this snapshot, below
            "room": {},
            "speeds": list(self.speeds),
            "trace": self.trace.latest(),
            "history": {},  # recorded from the rest of this snapshot, below
        }
        self._record(snapshot)
        snapshot["alerts"] = [
            {"text": sentence, "level": level}
            for sentence, level in alerts_core.alerts(snapshot, snapshot["time"])
        ]
        load = sn.as_list(host.get("load"))
        space = memory_core.room(snapshot["memory"], cores, sn.num(load[0]) if load else 0.0)
        if space is not None:
            snapshot["room"] = {"bytes": round(space[0]), "cores": round(space[1], 1)}
        if self.jobs and recent_loss(self.history.export(), TRACE_WINDOW) >= TRACE_LOSS:
            self.trace.fire()
        snapshot["history"] = self.history.export()
        return snapshot

    def _keep_speed(self, result: Json) -> None:
        """The speed tests' results, newest last (one every 30 minutes, the last 48)."""
        if result.get("bits") and result.get("round") != self._speed_round:
            self._speed_round = result["round"]
            self.speeds = [*self.speeds, {"at": result.get("at"), "bits": result["bits"]}][-48:]

    def _record(self, snapshot: Snap) -> None:
        for row in model.tree(snapshot, expanded=_every_key(snapshot)):
            self.history.push(row.key, row.cpu, row.mem_used, row.rx, row.tx)
        for key, name, value in network_series(snapshot, self._ping_rounds):
            self.history.put(key, name, value)
        self.history.end_tick()

    def write(self, snapshot: Snap) -> None:
        out = self.settings.out
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(f".{out.name}.tmp")
        tmp.write_text(json.dumps(snapshot, separators=(",", ":")))
        tmp.chmod(0o644)
        tmp.replace(out)

    def run(self, once: bool = False) -> None:
        next_at = self.clock()
        if self._start_pinger:
            self.pinger.start()
        for job in [*self.jobs, *self.local_jobs]:
            job.start()
        try:
            while True:
                self.write(self.tick())
                if once:
                    return
                next_at += self.settings.interval
                time.sleep(max(0.0, next_at - self.clock()))
                if self.clock() - next_at > self.settings.interval:
                    next_at = self.clock()
        finally:
            self.probes.stop_all()
            checks.stop_all([*self.jobs, *self.local_jobs])


MEMORY_INTERVAL = 5.0  # seconds between memory readings
TRACE_PAUSE = 600.0  # at most one trace every 10 minutes
TRACE_WINDOW = 30  # samples (a minute at 2 s)
TRACE_LOSS = 0.05
# (job name, series, seconds, check): every series is in milliseconds, LOST for no answer.
DNS_CHECKS = (
    ("dns_local", "127.0.0.53"),  # what every program on the host asks
    ("dns_google", "8.8.8.8"),
    ("dns_cloudflare", "1.1.1.1"),
)


def _api(host: str) -> Callable[[], Json]:
    return lambda: checks.https_steps(host, "/")


def _dns(server: str) -> Callable[[], Json]:
    return lambda: checks.dns_ms(server)


def make_jobs(settings: Settings) -> list[checks.Every]:
    jobs = [checks.Every(name, seconds, _api(host)) for name, _, seconds, host in API_CHECKS]
    jobs += [checks.Every(name, 10.0, _dns(server)) for name, server in DNS_CHECKS]
    jobs.append(checks.Every("speed", 1800.0, checks.download_bits))
    return jobs


def _every_key(snapshot: Snap) -> set[str]:
    keys = {"host"}
    keys.update(sn.text(i.get("key")) for i in sn.instances(snapshot))
    return keys


def default_lxc(sudo: bool = False) -> str:
    """The snap's client as root; with sudo, the path the host's sudoers names."""
    if not sudo and Path("/snap/bin/lxc").exists():
        return "/snap/bin/lxc"
    return shutil.which("lxc") or "/snap/bin/lxc"


def is_root() -> bool:
    with contextlib.suppress(AttributeError):
        return os.geteuid() == 0
    return False


def user_id(name: str) -> int:
    """The uid of `name` on this machine, or -1 (no slice to read) when there is none."""
    try:
        return pwd.getpwnam(name).pw_uid
    except KeyError:
        return -1
