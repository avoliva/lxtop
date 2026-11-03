"""Snapshot builders shared by the view and model tests."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from lxtop.collector import checks
from lxtop.collector import collector as collect

PROCS = [
    {"pid": 1, "ppid": 0, "name": "docker-init", "cpu": 0.0},
    {"pid": 2, "ppid": 1, "name": "python3", "cpu": 0.0},
    {"pid": 3, "ppid": 2, "name": "socat", "cpu": 0.0},
    {"pid": 5, "ppid": 2, "name": "worker", "cpu": 0.01},
    {"pid": 40, "ppid": 5, "name": "node", "cpu": 0.0},  # an MCP server, idle
    {"pid": 41, "ppid": 5, "name": "bash", "cpu": 0.0},
    {"pid": 42, "ppid": 41, "name": "uv", "cpu": 0.0},
    {"pid": 43, "ppid": 42, "name": "pytest", "cpu": 0.9},
]
OLD_MOUNTS = [
    "/srv/app/data",
    "/srv/app/cache",
]


def container(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "4a8290f0069f" + "0" * 52,
        "name": "app-worker-4a8290f0069f",
        "state": "running",
        "labels": {"com.example.role": "worker"},
        "started": "2026-10-27T09:35:59Z",
        "cpu_limit": 2.0,
        "cpu_cores": 0.5,
        "mem_used": 1 << 30,
        "mem_limit": 4 << 30,
        "pids": 145,
        "mounts": list(OLD_MOUNTS),
        "procs": [dict(p) for p in PROCS],
    }
    item.update(overrides)
    return item


def snapshot(*items: dict[str, Any]) -> dict[str, Any]:
    return {
        "instances": [
            {"key": "i:apps/demo", "name": "demo", "probe": {"docker": {"containers": []}}},
            {
                "key": "i:apps/app",
                "name": "app",
                "probe": {
                    "docker": {"containers": list(items)},
                    "procs": [{"name": "app", "rss": 300 << 20}, {"name": "x", "rss": 1}],
                },
            },
        ]
    }


def lxd_instance(name: str, cpu_ns: float, rx: float, status: str = "Running") -> dict[str, Any]:
    return {
        "name": name,
        "project": "apps",
        "type": "virtual-machine",
        "status": status,
        "expanded_config": {"limits.cpu": "6", "limits.memory": "12GiB"},
        "state": {
            "cpu": {"usage": cpu_ns},
            "memory": {"usage": 2 * 2**30, "total": 12 * 2**30},
            "disk": {"root": {"usage": 5 * 2**30, "total": 64 * 2**30}},
            "network": {
                "lo": {"counters": {"bytes_received": 999, "bytes_sent": 999}},
                "enp5s0": {
                    "counters": {"bytes_received": rx, "bytes_sent": 0},
                    "addresses": [
                        {"family": "inet", "address": "10.200.3.10", "scope": "global"},
                        {"family": "inet6", "address": "fe80::1", "scope": "link"},
                    ],
                },
            },
            "processes": 140,
        },
    }


NOW = 1_800_000_000.0


class _Pinger:
    def __init__(self, service: bool = True) -> None:
        self.round = 0
        self.service = service

    def latest(self) -> dict[str, Any]:
        self.round += 1
        found: dict[str, Any] = {
            "router": {"ms": 1.2, "round": self.round},
            "internet": {"ms": 14.0 + self.round % 3, "round": self.round},
        }
        if self.service:
            found["service"] = {"ms": 21.0, "round": self.round}
        return found


class _Sampler:
    def sample(self) -> dict[str, Any]:
        return {
            "hostname": "host",
            "uptime": 3 * 86400 + 4000,
            "load": [0.5, 0.4, 0.3],
            "cpu": {"busy": 0.25, "count": 16, "cores": [0.1 * (i % 8) for i in range(16)]},
            "mem": {"used": 22 * 2**30, "total": 62 * 2**30, "swap_used": 0, "swap_total": 0},
            "gpus": [{"util": 40, "mem_used_mib": 2048, "mem_total_mib": 16384, "temp_c": 55}],
            "temps": [{"chip": "k10temp", "label": "Tctl", "c": 61.0}],
            "fs": [{"mount": "/", "used": 100 * 2**30, "total": 400 * 2**30}],
            "disks": [{"name": "nvme0n1", "read": 1000, "write": 2000}],
            "net": [{"name": "eno1", "rx": 125_000, "tx": 25_000}, {"name": "lxdbr0", "rx": 9e9}],
            "docker": {"containers": []},
        }


class _Tick:
    """The collector's clock: starts at 100.0 and moves only when a test says so."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def step(self, seconds: float = 2.0) -> None:
        self.now += seconds


def collector(
    out: Path | None = None,
    *,
    jobs: Sequence[checks.Every] = (),
    pinger: Any = None,
) -> tuple[collect.Collector, _Tick]:
    """The real Collector over a fake sampler and fake LXD. `jobs` are slow checks whose
    `run_once()` runs before the caller's first tick."""
    clock = _Tick()

    def lxd() -> list[Any]:
        step = clock.now - 100.0
        return [
            lxd_instance("app", (1 + step * 0.3) * 1e9, step * 4000),
            lxd_instance("demo", (1 + step * 0.05) * 1e9, step * 100),
            lxd_instance("idle", 0, 0, status="Stopped"),
        ]

    settings = collect.Settings(
        out=out or Path("/nonexistent/state.json"),
        probe_instances=False,
        ping=False,
        checks=False,
    )
    built = collect.Collector(
        settings,
        _Sampler(),  # type: ignore[arg-type]
        lxd,
        clock=clock,
        pinger=pinger or _Pinger(service=not jobs),
    )
    built.jobs = list(jobs)
    for job in jobs:
        job.run_once()
    return built, clock


def full_snapshot(
    out: Path | None = None,
    *,
    jobs: Sequence[checks.Every] = (),
    pinger: Any = None,
) -> dict[str, Any]:
    """What the collector writes after a dozen ticks: a host, three LXD instances (one with
    a Docker container), pings, and history for the graphs. Built by the real Collector."""
    built, clock = collector(out, jobs=jobs, pinger=pinger)
    snap: dict[str, Any] = {}
    for _ in range(12):
        clock.step()
        snap = dict(built.tick())  # a plain dict, as the viewer reads the file
    snap["time"] = NOW
    agent_probe = {
        "docker": {"containers": [container()]},
        "procs": [{"name": "app", "rss": 300 << 20}],
    }
    snap["instances"][0]["probe"] = agent_probe
    snap["instances"][0]["probe_status"] = "ok"
    return snap
