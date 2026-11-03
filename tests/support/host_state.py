"""A fake /proc and cgroup tree for the memory reader, and `memory` and `units`
records as the collector leaves them in the snapshot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

GIB = 1 << 30
NOW = 1_793_600_000.0  # 2026-11-02 06:13 UTC
UID = 1000


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def fake_proc(tmp: Path, procs: dict[int, tuple[list[str], int, str]]) -> Path:
    """/proc with meminfo, pressure files and, per pid, (argv, resident KiB, cgroup path)."""
    proc = tmp / "proc"
    write(
        proc / "meminfo",
        "MemTotal: 65000000 kB\nMemAvailable: 40000000 kB\n"
        "SwapTotal: 8388604 kB\nSwapFree: 6000000 kB\n",
    )
    write(
        proc / "pressure" / "memory",
        "some avg10=12.50 avg60=3.00 avg300=1.00 total=1\nfull avg10=0.50 avg60=0.10 "
        "avg300=0.00 total=1\n",
    )
    write(proc / "pressure" / "cpu", "some avg10=2.06 avg60=2.40 avg300=2.00 total=1\n")
    for pid, (argv, rss_kib, cgroup) in procs.items():
        d = proc / str(pid)
        d.mkdir(parents=True)
        (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
        write(d / "status", f"Name:\tx\nVmRSS:\t{rss_kib} kB\n")
        write(d / "cgroup", f"0::{cgroup}\n")
    return proc


def group(
    root: Path,
    rel: str,
    current: int,
    *,
    peak: int | None = None,
    maximum: str = "max",
    high: str = "max",
    kills: int = 0,
    procs: str = "",
) -> Path:
    path = root / rel
    write(path / "memory.current", f"{current}\n")
    write(path / "memory.max", f"{maximum}\n")
    write(path / "memory.high", f"{high}\n")
    write(path / "memory.events", f"low 0\nhigh 0\nmax 0\noom 0\noom_kill {kills}\n")
    if peak is not None:
        write(path / "memory.peak", f"{peak}\n")
    write(path / "cgroup.procs", procs)
    return path


def memory_record(**extra: Any) -> dict[str, Any]:
    """A `memory` record: 40 GB available, admin using 14 under a 40 GiB slow-down line and
    no hard cap, two VMs."""
    out: dict[str, Any] = {
        "pressure": {"memory": {"some10": 0.0, "some60": 0.0, "full10": 0.0, "full60": 0.0}},
        "meminfo": {
            "total": 62 * GIB,
            "available": 40 * GIB,
            "swap_total": 8 * GIB,
            "swap_free": 6 * GIB,
        },
        "vms": [{"name": "ci", "rss": 8 * GIB}, {"name": "app", "rss": 7 * GIB}],
        "containers": [],
        "user": {
            "name": "user-1000.slice",
            "path": "user.slice/user-1000.slice",
            "current": 14 * GIB,
            "peak": 50 * GIB,
            "high": 40 * GIB,
            "max": None,
            "pressure": 0.0,
            "oom_kills": 0,
            "jobs": [
                {
                    "name": "stats-kaggle-build4.service",
                    "current": 9 * GIB,
                    "peak": 12 * GIB,
                    "high": None,
                    "max": None,
                    "oom_kills": 0,
                    "command": "/home/admin/.venv/bin/stats build gold",
                },
                {
                    "name": "session-92140.scope",
                    "current": 2 * GIB,
                    "peak": 3 * GIB,
                    "high": None,
                    "max": None,
                    "oom_kills": 1,
                    "command": "python3 search.py --trials 400",
                },
            ],
        },
        "gpu_apps": [{"pid": 7, "memory": 11 * GIB, "name": "ollama", "owner": "llm"}],
        "oom": {"kills": [], "since": "-7d"},
    }
    out.update(extra)
    return out


def kill(
    at: float, host_wide: bool = True, name: str = "stats", rss: int = 49 * GIB
) -> dict[str, Any]:
    return {"at": at, "pid": 42, "name": name, "rss": rss, "uid": UID, "host_wide": host_wide}


def timer(
    unit: str,
    result: str = "success",
    status: int = 0,
    active: str = "inactive",
    sub: str = "dead",
    last: float | None = NOW - 600,
) -> dict[str, Any]:
    service = unit.replace(".timer", ".service")
    return {
        "unit": unit,
        "service": service,
        "next": NOW + 300,
        "last": last,
        "service_state": {
            "unit": service,
            "description": "",
            "result": result,
            "active": active,
            "sub": sub,
            "status": status,
            "started": last,
            "exited": last,
        },
    }


def units_record(**extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "user": "admin",
        "timers": [timer("stats-propline.timer"), timer("stats-paper.timer")],
        "running": [
            {
                "unit": "stats-books.service",
                "description": "",
                "active": "active",
                "sub": "running",
            }
        ],
        "failed": [],
    }
    out.update(extra)
    return out
