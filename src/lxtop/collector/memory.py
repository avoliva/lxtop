"""The host's memory as the jobs on it feel it: pressure, what is available, what each
VM really costs the host, the user slice and its biggest jobs with their caps, LXD containers,
and who holds the GPU.

Everything comes from files the root collector can read (`/proc`, `/sys/fs/cgroup`) and one
`nvidia-smi`; no input. A VM's memory in LXD is what its guest reports; the host pays the
qemu process's resident memory, often much more.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import subprocess
from pathlib import Path

from lxtop.core.snapshot import Json

PROC = Path("/proc")
CGROUP = Path("/sys/fs/cgroup")
MIN_JOB = 64 << 20  # jobs smaller than this are left out
MAX_JOBS = 12
MAX_TEXT = 160
_PRESSURE = re.compile(r"^(some|full) avg10=([\d.]+) avg60=([\d.]+) avg300=([\d.]+)")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def clean(value: str) -> str:
    return _CONTROL.sub(" ", value)[:MAX_TEXT]


def _read(path: Path) -> str | None:
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        return None


def _number(path: Path) -> int | None:
    """A cgroup number file: bytes, or None for "max" or a missing file."""
    text = (_read(path) or "").strip()
    return int(text) if text.isdigit() else None


def parse_pressure(text: str) -> Json:
    """/proc/pressure/<kind>: {"some10": %, "some60": %, "full10": %, "full60": %}."""
    out: Json = {}
    for line in text.splitlines():
        m = _PRESSURE.match(line)
        if m:
            out[m.group(1) + "10"] = float(m.group(2))
            out[m.group(1) + "60"] = float(m.group(3))
    return out


def pressure(proc: Path = PROC) -> Json:
    out: Json = {}
    for kind in ("memory", "cpu", "io"):
        text = _read(proc / "pressure" / kind)
        if text is not None:
            out[kind] = parse_pressure(text)
    return out


def meminfo(proc: Path = PROC) -> Json:
    fields = {}
    for line in (_read(proc / "meminfo") or "").splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            fields[key] = int(parts[0]) * 1024
    keys = {"total": "MemTotal", "available": "MemAvailable", "swap_total": "SwapTotal",
            "swap_free": "SwapFree"}  # fmt: skip
    return {name: fields[key] for name, key in keys.items() if key in fields}


def vm_name(argv: list[str]) -> str:
    """The instance name from qemu's `-name`: "app" or "guest=app,debug-threads=on"."""
    for i, arg in enumerate(argv[:-1]):
        if arg == "-name":
            value = argv[i + 1]
            for part in value.split(","):
                if part.startswith("guest="):
                    return part[6:]
            return value.split(",")[0]
    return ""


def _status_rss(text: str) -> int:
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            return int(parts[1]) * 1024 if len(parts) > 1 and parts[1].isdigit() else 0
    return 0


def vms(proc: Path = PROC) -> list[Json]:
    """Each VM's qemu process and its resident memory on the host, largest first."""
    found = []
    with contextlib.suppress(OSError):
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            raw = None
            with contextlib.suppress(OSError):
                raw = (entry / "cmdline").read_bytes()
            argv = [a.decode(errors="replace") for a in (raw or b"").split(b"\0") if a]
            if not argv or "qemu-system" not in argv[0].rsplit("/", 1)[-1]:
                continue
            name = vm_name(argv)
            status = _read(entry / "status")
            if name and status is not None:
                found.append({"name": clean(name), "rss": _status_rss(status)})
    return sorted(found, key=lambda v: -v["rss"])


def _first_command(group: Path, proc: Path) -> str:
    """The command line of the oldest process in a cgroup or below it."""
    for path in [group, *sorted(group.rglob("*"))][:50]:
        procs = (_read(path / "cgroup.procs") or "").split()
        if procs:
            raw = None
            with contextlib.suppress(OSError):
                raw = (proc / procs[0] / "cmdline").read_bytes()
            if raw:
                return clean(" ".join(a.decode(errors="replace") for a in raw.split(b"\0") if a))
    return ""


def _oom_kills(group: Path) -> int:
    for line in (_read(group / "memory.events") or "").splitlines():
        key, _, value = line.partition(" ")
        if key == "oom_kill" and value.strip().isdigit():
            return int(value)
    return 0


def _group(path: Path, root: Path, proc: Path | None = None) -> Json:
    out: Json = {
        "name": path.name,
        "path": str(path.relative_to(root)),
        "current": _number(path / "memory.current") or 0,
        "peak": _number(path / "memory.peak"),
        "high": _number(path / "memory.high"),
        "max": _number(path / "memory.max"),
        "oom_kills": _oom_kills(path),
    }
    if proc is not None:
        out["command"] = _first_command(path, proc)
    return out


def user_slice(uid: int, root: Path = CGROUP, proc: Path = PROC) -> Json | None:
    """The user's slice and its biggest jobs: each session scope (an SSH login and what it
    started) and each service or scope of the user's own systemd."""
    top = root / "user.slice" / f"user-{uid}.slice"
    if not (top / "memory.current").exists():
        return None
    manager = top / f"user@{uid}.service"
    inside = sorted(p for p in manager.rglob("*") if p.is_dir()) if manager.is_dir() else []
    jobs = []
    for path in sorted(top.glob("session-*.scope")) + inside:
        if not path.name.endswith((".service", ".scope")) or path.name == "init.scope":
            continue
        current = _number(path / "memory.current") or 0
        if current >= MIN_JOB:
            jobs.append(_group(path, root, proc))
    jobs.sort(key=lambda j: -j["current"])
    stall = parse_pressure(_read(top / "memory.pressure") or "").get("some10")
    return {**_group(top, root), "pressure": stall, "jobs": jobs[:MAX_JOBS]}


def containers(root: Path = CGROUP) -> list[Json]:
    """LXD containers (`lxc.payload.<name>`): their memory and limit."""
    found = [_group(p, root) for p in sorted(root.glob("lxc.payload.*"))]
    for item in found:
        item["name"] = item["name"].removeprefix("lxc.payload.")
    return found


def owner(pid: str, proc: Path = PROC) -> str:
    """Who a process belongs to: an LXD container, a user unit, a system unit, or ""."""
    text = _read(proc / pid / "cgroup") or ""
    path = text.strip().rsplit("::", 1)[-1]
    m = re.search(r"lxc\.payload\.([^/]+)", path)
    if m:
        return clean(m.group(1))
    units = [part for part in path.split("/") if part.endswith((".service", ".scope"))]
    return clean(units[-1]) if units else ""


def parse_gpu_apps(text: str) -> list[tuple[str, int, str]]:
    """`nvidia-smi --query-compute-apps=pid,used_memory,process_name` CSV (MiB, no units)."""
    rows = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.split(",")]
        if len(cells) >= 3 and cells[0].isdigit() and cells[1].isdigit():
            rows.append((cells[0], int(cells[1]) << 20, clean(",".join(cells[2:]))))
    return rows


def gpu_apps(nvidia: str | None, proc: Path = PROC) -> list[Json] | None:
    """The processes holding GPU memory, with their owner; None without nvidia-smi."""
    if not nvidia:
        return None
    try:
        done = subprocess.run(
            [nvidia, "--query-compute-apps=pid,used_memory,process_name",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL, check=False,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return [
        {
            "pid": int(pid),
            "memory": used,
            "name": name.rsplit("/", 1)[-1],
            "owner": owner(pid, proc),
        }
        for pid, used, name in parse_gpu_apps(done.stdout)
    ]


class Reader:
    """`read()` for the collector, every few seconds."""

    def __init__(self, uid: int, proc: Path = PROC, root: Path = CGROUP) -> None:
        self.uid, self.proc, self.root = uid, proc, root
        self.nvidia = shutil.which("nvidia-smi")

    def read(self) -> Json:
        out: Json = {
            "pressure": pressure(self.proc),
            "meminfo": meminfo(self.proc),
            "vms": vms(self.proc),
            "containers": containers(self.root),
        }
        found = user_slice(self.uid, self.root, self.proc)
        if found is not None:
            out["user"] = found
        gpu = gpu_apps(self.nvidia, self.proc)
        if gpu is not None:
            out["gpu_apps"] = gpu
        return out
