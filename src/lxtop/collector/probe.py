"""Samples one machine: CPU, memory, disks, network, temperatures, GPUs, top processes, Docker.

This file must stay self-contained (standard library only, no imports from lxtop): the
collector sends its source into each LXD instance as `python3 -I -c <source>`, where it prints one
JSON sample per tick. Guests may run an older Python, so keep to 3.8-era syntax at runtime.
"""

from __future__ import annotations

import http.client
import json
import os
import pwd
import re
import shutil
import socket
import subprocess
import sys
import time
from typing import Any

CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
WHOLE_DISK = re.compile(r"(nvme\d+n\d+|[shv]d[a-z]+|xvd[a-z]+|mmcblk\d+)")
REAL_FS = {"ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "f2fs", "bcachefs"}
TOP_PROCS = 15
MAX_CONTAINERS = 200
# Processes inside one gVisor container (`runsc ps`): Docker's own `top` lists the VM's.
MAX_SANDBOX_PROCS = 40
MAX_MOUNTS = 40
RUNSC_ROOTS = ("/var/run/docker/runtime-runc/moby", "/run/docker/runtime-runsc/moby")
DNS_EVERY = 10.0  # seconds between resolver checks
GO_UNITS = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 1e-3, "us": 1e-6, "µs": 1e-6, "ns": 1e-9}

Sample = dict[str, Any]


# ---- pure parsers (tested with fixture text) -------------------------------------------


def parse_proc_stat(text: str) -> dict[str, tuple[int, int]]:
    """`cpu`, `cpu0`... -> (total jiffies, idle jiffies). Guest time is already in user."""
    found: dict[str, tuple[int, int]] = {}
    for line in text.splitlines():
        if not line.startswith("cpu"):
            continue
        name, *fields = line.split()
        values = [int(v) for v in fields[:8]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        found[name] = (sum(values), idle)
    return found


def cpu_busy(prev: tuple[int, int] | None, cur: tuple[int, int]) -> float:
    """Busy fraction (0..1) between two `parse_proc_stat` readings of one CPU."""
    if prev is None:
        return 0.0
    total = cur[0] - prev[0]
    idle = cur[1] - prev[1]
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, (total - idle) / total))


def parse_meminfo(text: str) -> dict[str, int]:
    """Field -> bytes."""
    found: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts:
            found[key] = int(parts[0]) * (1024 if len(parts) > 1 else 1)
    return found


def memory(info: dict[str, int]) -> Sample:
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    swap_total = info.get("SwapTotal", 0)
    return {
        "total": total,
        "used": max(0, total - avail),
        "available": avail,
        "cached": info.get("Cached", 0) + info.get("Buffers", 0),
        "swap_total": swap_total,
        "swap_used": max(0, swap_total - info.get("SwapFree", 0)),
    }


def parse_net_dev(text: str) -> dict[str, tuple[int, int]]:
    """Interface -> (rx bytes, tx bytes)."""
    found: dict[str, tuple[int, int]] = {}
    for line in text.splitlines()[2:]:
        name, _, rest = line.partition(":")
        fields = rest.split()
        if len(fields) >= 9:
            found[name.strip()] = (int(fields[0]), int(fields[8]))
    return found


def parse_net_faults(text: str) -> dict[str, int]:
    """Interface -> errors plus drops, received and sent (cumulative)."""
    found: dict[str, int] = {}
    for line in text.splitlines()[2:]:
        name, _, rest = line.partition(":")
        fields = rest.split()
        if len(fields) >= 12:
            found[name.strip()] = sum(int(fields[i]) for i in (2, 3, 10, 11))
    return found


def parse_snmp_tcp(text: str) -> dict[str, int]:
    """The Tcp: counters of /proc/net/snmp (a header line, then a value line)."""
    rows = [line.split()[1:] for line in text.splitlines() if line.startswith("Tcp:")]
    if len(rows) < 2 or len(rows[0]) != len(rows[1]):
        return {}
    try:
        return {rows[0][i]: int(rows[1][i]) for i in range(len(rows[0]))}
    except ValueError:
        return {}


def parse_wireless(text: str) -> list[Sample]:
    """Wi-Fi link quality (0-1 of the driver's 70) and signal in dBm, per interface."""
    found: list[Sample] = []
    for line in text.splitlines()[2:]:
        name, _, rest = line.partition(":")
        fields = rest.split()
        if len(fields) >= 3:
            quality, dbm = _num(fields[1].rstrip(".")), _num(fields[2].rstrip("."))
            found.append({"name": name.strip(), "quality": quality / 70, "dbm": int(dbm)})
    return found


TUNNEL_METRICS = ("127.0.0.1", 20241)  # cloudflared run with --metrics on this port
_CODE = re.compile(r'^cloudflared_tunnel_response_by_code\{status_code="(\d{3})"\} (\S+)$')


def parse_tunnel_metrics(text: str) -> Sample | None:
    """Cumulative visitor counts from cloudflared's Prometheus page, or None if none are in it."""
    out = {"responses": 0, "client_errors": 0, "server_errors": 0, "request_errors": 0}
    seen = False
    connections = 0
    for line in text.splitlines():
        found = _CODE.match(line)
        if found:
            count = int(_num(found.group(2)))
            out["responses"] += count
            if found.group(1).startswith("4"):
                out["client_errors"] += count
            elif found.group(1).startswith("5"):
                out["server_errors"] += count
            seen = True
        elif line.startswith("cloudflared_tunnel_request_errors "):
            out["request_errors"] = int(_num(line.split()[1]))
            seen = True
        elif line.startswith("cloudflared_tunnel_ha_connections "):
            connections = int(_num(line.split()[1]))
            seen = True
    if not seen:
        return None
    out["connections"] = connections
    return out


def tunnel_rates(prev: Sample | None, cur: Sample, seconds: float) -> Sample:
    """Visitor requests per second, and failed ones (5xx or never answered) per second."""

    def per_second(*keys: str) -> float:
        if not prev or seconds <= 0:
            return 0.0
        now = sum(int(cur.get(k) or 0) for k in keys)
        before = sum(int(prev.get(k) or 0) for k in keys)
        return max(0, now - before) / seconds

    return {
        "req": per_second("responses"),
        "bad": per_second("server_errors", "request_errors"),
        "connections": cur.get("connections", 0),
        "total": cur.get("responses", 0),
    }


def parse_runsc_net(text: str) -> int | None:
    """Bytes through a gVisor sandbox's network stack (`runsc events --stats`). A sandbox
    with no network of its own (loopback only) shows its traffic here and nowhere else."""
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        nics = ((event if isinstance(event, dict) else {}).get("data") or {}).get(
            "network_interfaces"
        )
        if isinstance(nics, list):
            return sum(int(n.get("RxBytes") or 0) for n in nics if isinstance(n, dict))
    return None


def parse_resolved(text: str) -> tuple[int, int, int] | None:
    """(lookups, timeouts, failed answers) from `resolvectl statistics --json=short`."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    tx = data.get("transactions") if isinstance(data, dict) else None
    if not isinstance(tx, dict):
        return None
    return (
        int(tx.get("totalTransactions") or 0),
        int(tx.get("totalTimeouts") or 0),
        int(tx.get("totalFailedResponses") or 0),
    )


def parse_diskstats(text: str) -> dict[str, tuple[int, int]]:
    """Whole disks only -> (bytes read, bytes written)."""
    found: dict[str, tuple[int, int]] = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 10 and WHOLE_DISK.fullmatch(fields[2]):
            found[fields[2]] = (int(fields[5]) * 512, int(fields[9]) * 512)
    return found


def parse_pid_stat(text: str) -> tuple[str, int, int] | None:
    """(command name, utime+stime ticks, rss pages) from /proc/<pid>/stat."""
    open_at = text.find("(")
    close_at = text.rfind(")")
    if open_at < 0 or close_at < open_at:
        return None
    fields = text[close_at + 2 :].split()
    if len(fields) < 22:
        return None
    return text[open_at + 1 : close_at], int(fields[11]) + int(fields[12]), int(fields[21])


def rates(
    prev: dict[str, tuple[int, int]] | None, cur: dict[str, tuple[int, int]], seconds: float
) -> dict[str, tuple[float, float]]:
    """Per-second rates of two counter pairs; counters that went backwards count as zero."""
    if not prev or seconds <= 0:
        return {name: (0.0, 0.0) for name in cur}
    found: dict[str, tuple[float, float]] = {}
    for name, (a, b) in cur.items():
        pa, pb = prev.get(name, (a, b))
        found[name] = (max(0, a - pa) / seconds, max(0, b - pb) / seconds)
    return found


def docker_cpu_cores(prev: tuple[int, int] | None, stats: Sample) -> tuple[float, tuple[int, int]]:
    """CPU cores in use by a container from two Docker stats readings.

    Docker reports cumulative container usage and host system usage (ns); `online_cpus` scales
    the share to cores. Returns (cores, reading to keep for next time)."""
    cpu = stats.get("cpu_stats") or {}
    usage = int((cpu.get("cpu_usage") or {}).get("total_usage") or 0)
    system = int(cpu.get("system_cpu_usage") or 0)
    online = int(cpu.get("online_cpus") or 0) or 1
    reading = (usage, system)
    if prev is None:
        return 0.0, reading
    d_usage = usage - prev[0]
    d_system = system - prev[1]
    if d_usage <= 0 or d_system <= 0:
        return 0.0, reading
    return d_usage / d_system * online, reading


def docker_memory(stats: Sample) -> tuple[int, int]:
    """(used, limit) the way `docker stats` shows it: usage minus inactive file cache."""
    mem = stats.get("memory_stats") or {}
    usage = int(mem.get("usage") or 0)
    detail = mem.get("stats") or {}
    cache = int(detail.get("inactive_file") or detail.get("total_inactive_file") or 0)
    return max(0, usage - cache), int(mem.get("limit") or 0)


def docker_io(stats: Sample) -> tuple[int, int, int, int]:
    """(net rx, net tx, block read, block written) cumulative bytes."""
    rx = tx = 0
    for net in (stats.get("networks") or {}).values():
        rx += int(net.get("rx_bytes") or 0)
        tx += int(net.get("tx_bytes") or 0)
    read = written = 0
    blkio = stats.get("blkio_stats") or {}
    for entry in blkio.get("io_service_bytes_recursive") or []:
        op = str(entry.get("op", "")).lower()
        if op == "read":
            read += int(entry.get("value") or 0)
        elif op == "write":
            written += int(entry.get("value") or 0)
    return rx, tx, read, written


def go_duration(text: str) -> float:
    """Seconds from a Go duration as `runsc ps` prints TIME: "30ms", "5.05s", "1m2.5s"."""
    total = 0.0
    for value, unit in re.findall(r"([0-9]+(?:\.[0-9]+)?)(ms|us|µs|ns|h|m|s)", text):
        total += float(value) * GO_UNITS[unit]
    return total


def parse_runsc_ps(text: str) -> list[Sample]:
    """`runsc ps` table: UID PID PPID PGID C TTY STIME TIME CMD (CMD is the program name)."""
    rows: list[Sample] = []
    for line in text.splitlines()[1:]:
        fields = line.split(None, 8)
        if len(fields) < 9 or not (fields[1].isdigit() and fields[2].isdigit()):
            continue
        rows.append(
            {
                "pid": int(fields[1]),
                "ppid": int(fields[2]),
                "c": _num(fields[4]),
                "time": go_duration(fields[7]),
                "name": fields[8].strip()[:64],
            }
        )
    return rows[:MAX_SANDBOX_PROCS]


def parse_nvidia(text: str) -> list[Sample]:
    """Rows of the `nvidia-smi --query-gpu` CSV in GPU_FIELDS order."""
    gpus: list[Sample] = []
    for line in text.strip().splitlines():
        cells = [cell.strip() for cell in line.split(",")]
        if len(cells) != len(GPU_FIELDS):
            continue
        row: Sample = {"name": cells[1]}
        for key, cell in zip(GPU_FIELDS[2:], cells[2:]):  # noqa: B905 (3.8 has no strict=)
            try:
                row[key] = float(cell)
            except ValueError:
                row[key] = None
        gpus.append(row)
    return gpus


GPU_FIELDS = (
    "index",
    "name",
    "util",
    "mem_used_mib",
    "mem_total_mib",
    "temp_c",
    "power_w",
    "power_limit_w",
    "fan_pct",
)
GPU_QUERY = (
    "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,"
    "power.draw,power.limit,fan.speed"
)


# ---- Docker over its unix socket ----------------------------------------------------------


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._path)
        self.sock = sock


def unix_get(path: str, url: str, timeout: float = 3.0) -> Any:
    """GET `url` from an HTTP server on a unix socket and decode its JSON body."""
    conn = _UnixConnection(path, timeout)
    try:
        conn.request("GET", url)
        response = conn.getresponse()
        body = response.read()
        if response.status != 200:
            raise OSError(f"HTTP {response.status} for {url}")
        return json.loads(body)
    finally:
        conn.close()


# ---- the sampler ------------------------------------------------------------------------------


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


class Sampler:
    """Keeps the previous readings so each sample carries rates over the last interval."""

    def __init__(self, docker_socket: str = "/var/run/docker.sock", gpu: bool = True) -> None:
        self.docker_socket = docker_socket
        self.nvidia = shutil.which("nvidia-smi") if gpu else None
        self._time: float | None = None
        self._cpu: dict[str, tuple[int, int]] = {}
        self._net: dict[str, tuple[int, int]] | None = None
        self._disk: dict[str, tuple[int, int]] | None = None
        self._pids: dict[int, int] = {}
        self._users: dict[int, str] = {}
        self._docker_cpu: dict[str, tuple[int, int]] = {}
        self._docker_io: dict[str, tuple[int, int, int, int]] = {}
        self._inspect: dict[str, Sample] = {}
        self.runsc = shutil.which("runsc") or (
            "/usr/bin/runsc" if os.path.exists("/usr/bin/runsc") else None
        )
        self._sandbox_time: dict[str, dict[int, float]] = {}
        self._sandbox_net: dict[str, int] = {}
        self._faults: dict[str, int] = {}
        self._tcp: dict[str, int] = {}
        self._tunnel: Sample | None = None
        self._dns: tuple[int, int, int] | None = None
        self._dns_sample: Sample | None = None
        self._dns_at = float("-inf")
        self.resolvectl = shutil.which("resolvectl")

    def sample(self) -> Sample:
        now = time.monotonic()
        seconds = now - self._time if self._time is not None else 0.0
        self._time = now
        out: Sample = {
            "hostname": socket.gethostname(),
            "time": time.time(),
            "uptime": _float(_read("/proc/uptime").split()[:1]),
            "load": [_num(v) for v in _read("/proc/loadavg").split()[:3]],
            "cpu": self._cpu_sample(),
            "mem": memory(parse_meminfo(_read("/proc/meminfo"))),
            "net": self._net_sample(seconds),
            "disks": self._disk_sample(seconds),
            "fs": filesystems(_read("/proc/mounts")),
            "temps": temperatures(),
            "gpus": self._gpus(),
            "procs": self._procs(seconds),
            "docker": self._docker(seconds),
            "tcp": self._tcp_sample(seconds),
            "wifi": parse_wireless(_read("/proc/net/wireless")),
            "tunnel": self._tunnel_sample(seconds),
            "dns": self._dns_check(now),
        }
        return out

    def _tcp_sample(self, seconds: float) -> Sample:
        """Segments sent and resent per second: resends are the network losing packets."""
        cur = parse_snmp_tcp(_read("/proc/net/snmp"))
        prev, self._tcp = self._tcp, cur

        def per_second(name: str) -> float:
            if not prev or seconds <= 0 or name not in cur:
                return 0.0
            return round(max(0, cur[name] - prev.get(name, cur[name])) / seconds, 1)

        return {
            "out": per_second("OutSegs"),
            "retrans": per_second("RetransSegs"),
            "estab": cur.get("CurrEstab", 0),
        }

    def _tunnel_sample(self, seconds: float) -> Sample | None:
        """Visitors through a Cloudflare tunnel in this machine, if one runs here."""
        conn = http.client.HTTPConnection(*TUNNEL_METRICS, timeout=0.5)
        try:
            conn.request("GET", "/metrics")
            reply = conn.getresponse()
            body = reply.read(1 << 20).decode("utf-8", "replace") if reply.status == 200 else ""
        except (OSError, http.client.HTTPException):
            body = ""
        finally:
            conn.close()
        cur = parse_tunnel_metrics(body)
        if cur is None:
            self._tunnel = None
            return None
        out = tunnel_rates(self._tunnel, cur, seconds)
        self._tunnel = cur
        return out

    def _dns_check(self, now: float) -> Sample | None:
        """DNS lookups and timeouts between two checks DNS_EVERY seconds apart (needs root)."""
        if not self.resolvectl or now - self._dns_at < DNS_EVERY:
            return self._dns_sample
        try:
            done = subprocess.run(
                [self.resolvectl, "statistics", "--json=short"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            cur = parse_resolved(done.stdout)
        except (OSError, subprocess.SubprocessError):
            cur = None
        prev, prev_at = self._dns, self._dns_at
        self._dns, self._dns_at = cur, now
        if cur is None:
            self._dns_sample = None
        elif prev is None or any(cur[i] < prev[i] for i in range(3)):
            self._dns_sample = {"lookups": 0, "timeouts": 0, "failed": 0, "seconds": 0.0}
        else:
            self._dns_sample = {
                "lookups": cur[0] - prev[0],
                "timeouts": cur[1] - prev[1],
                "failed": cur[2] - prev[2],
                "seconds": round(now - prev_at, 1),
            }
        return self._dns_sample

    def _cpu_sample(self) -> Sample:
        cur = parse_proc_stat(_read("/proc/stat"))
        cores = [
            round(cpu_busy(self._cpu.get(name), cur[name]), 4)
            for name in sorted((n for n in cur if n != "cpu"), key=lambda n: int(n[3:]))
        ]
        total = cpu_busy(self._cpu.get("cpu"), cur["cpu"]) if "cpu" in cur else 0.0
        self._cpu = cur
        mhz = [float(m) for m in re.findall(r"cpu MHz\s*:\s*([\d.]+)", _read("/proc/cpuinfo"))]
        return {
            "busy": round(total, 4),
            "count": len(cores) or (os.cpu_count() or 1),
            "cores": cores,
            "mhz": round(sum(mhz) / len(mhz)) if mhz else None,
        }

    def _net_sample(self, seconds: float) -> list[Sample]:
        text = _read("/proc/net/dev")
        cur = parse_net_dev(text)
        per = rates(self._net, cur, seconds)
        faults = parse_net_faults(text)
        before = self._faults if self._net is not None else faults
        self._net, self._faults = cur, faults
        return [
            {
                "name": name,
                "rx": round(rx),
                "tx": round(tx),
                "rx_total": cur[name][0],
                "faults": max(0, faults.get(name, 0) - before.get(name, faults.get(name, 0))),
            }
            for name, (rx, tx) in sorted(per.items())
            if name != "lo"
        ]

    def _disk_sample(self, seconds: float) -> list[Sample]:
        cur = parse_diskstats(_read("/proc/diskstats"))
        per = rates(self._disk, cur, seconds)
        self._disk = cur
        return [
            {"name": n, "read": round(r), "write": round(w)} for n, (r, w) in sorted(per.items())
        ]

    def _gpus(self) -> list[Sample]:
        if not self.nvidia:
            return []
        try:
            done = subprocess.run(
                [self.nvidia, f"--query-gpu={GPU_QUERY}", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        return parse_nvidia(done.stdout) if done.returncode == 0 else []

    def _procs(self, seconds: float) -> list[Sample]:
        seen: dict[int, int] = {}
        rows: list[Sample] = []
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            parsed = parse_pid_stat(_read(f"/proc/{pid}/stat"))
            if parsed is None:
                continue
            name, ticks, rss = parsed
            seen[pid] = ticks
            prev = self._pids.get(pid)
            busy = (ticks - prev) / CLK_TCK / seconds if prev is not None and seconds > 0 else 0.0
            rows.append({"pid": pid, "name": name, "cpu": busy, "rss": rss * PAGE})
        self._pids = seen
        rows.sort(key=lambda r: (r["cpu"], r["rss"]), reverse=True)
        top = rows[:TOP_PROCS]
        for row in top:
            row["cpu"] = round(row["cpu"], 3)
            row["user"] = self._user(row["pid"])
            cmdline = _read(f"/proc/{row['pid']}/cmdline").replace("\0", " ").strip()
            row["cmd"] = cmdline[:200] or f"[{row['name']}]"
        return top

    def _user(self, pid: int) -> str:
        try:
            uid = os.stat(f"/proc/{pid}").st_uid
        except OSError:
            return "?"
        if uid not in self._users:
            try:
                self._users[uid] = pwd.getpwuid(uid).pw_name
            except KeyError:
                self._users[uid] = str(uid)
        return self._users[uid]

    def _docker(self, seconds: float) -> Sample | None:
        if not os.path.exists(self.docker_socket):
            return None
        try:
            listed = unix_get(self.docker_socket, "/containers/json?all=1")
        except (OSError, ValueError, http.client.HTTPException) as exc:
            return {"error": str(exc)[:200], "containers": []}
        containers: list[Sample] = []
        live: set[str] = set()
        for item in listed[:MAX_CONTAINERS]:
            cid = str(item.get("Id", ""))
            live.add(cid)
            names = item.get("Names") or [cid[:12]]
            row: Sample = {
                "id": cid,
                "name": str(names[0]).lstrip("/"),
                "image": item.get("Image"),
                "state": item.get("State"),
                "status": item.get("Status"),
                "created": item.get("Created"),
                "labels": item.get("Labels") or {},
                "ports": [
                    f"{p.get('IP', '')}:{p.get('PublicPort')}"
                    f"->{p.get('PrivatePort')}/{p.get('Type')}"
                    if p.get("PublicPort")
                    else f"{p.get('PrivatePort')}/{p.get('Type')}"
                    for p in item.get("Ports") or []
                ],
            }
            if item.get("State") == "running":
                self._container_stats(cid, row, seconds)
            containers.append(row)
        for gone in set(self._docker_cpu) - live:
            self._docker_cpu.pop(gone, None)
            self._docker_io.pop(gone, None)
            self._inspect.pop(gone, None)
            self._sandbox_time.pop(gone, None)
            self._sandbox_net.pop(gone, None)
        return {"error": None, "containers": containers}

    def _container_stats(self, cid: str, row: Sample, seconds: float) -> None:
        try:
            stats = unix_get(
                self.docker_socket, f"/containers/{cid}/stats?stream=false&one-shot=true"
            )
            if cid not in self._inspect:
                info = unix_get(self.docker_socket, f"/containers/{cid}/json")
                host = info.get("HostConfig") or {}
                state = info.get("State") or {}
                nano = int(host.get("NanoCpus") or 0)
                quota, period = int(host.get("CpuQuota") or 0), int(host.get("CpuPeriod") or 0)
                self._inspect[cid] = {
                    "cpu_limit": nano / 1e9
                    if nano
                    else (quota / period if quota and period else None),
                    "started": state.get("StartedAt"),
                    "restarts": info.get("RestartCount"),
                    "network_mode": host.get("NetworkMode"),
                    "runtime": host.get("Runtime"),
                    "workdir": (info.get("Config") or {}).get("WorkingDir"),
                    # Where each mount comes from (never the environment, which holds secrets).
                    "mounts": [
                        str(m.get("Source"))[:300]
                        for m in (info.get("Mounts") or [])[:MAX_MOUNTS]
                        if isinstance(m, dict)
                    ],
                }
        except (OSError, ValueError, http.client.HTTPException) as exc:
            row["error"] = str(exc)[:200]
            return
        cores, self._docker_cpu[cid] = docker_cpu_cores(self._docker_cpu.get(cid), stats)
        used, limit = docker_memory(stats)
        io = docker_io(stats)
        prev = self._docker_io.get(cid)
        self._docker_io[cid] = io
        if prev is not None and seconds > 0:
            rx, tx = (max(0, io[0] - prev[0]) / seconds, max(0, io[1] - prev[1]) / seconds)
        else:
            rx = tx = 0.0
        online = int((stats.get("cpu_stats") or {}).get("online_cpus") or 0) or None
        row.update(self._inspect[cid])
        row.update(
            {
                "cpu_cores": round(cores, 4),
                "cpu_cap": row.get("cpu_limit") or online,
                "mem_used": used,
                "mem_limit": limit,
                "pids": (stats.get("pids_stats") or {}).get("current"),
                "rx": round(rx),
                "tx": round(tx),
                "blk_read": io[2],
                "blk_write": io[3],
            }
        )
        if row.get("runtime") == "runsc":
            row["procs"] = self._sandbox_procs(cid, seconds)
            self._sandbox_traffic(cid, row, seconds)

    def _sandbox_traffic(self, cid: str, row: Sample, seconds: float) -> None:
        """A gVisor container's traffic from runsc: Docker sees none when it has no network."""
        if not self.runsc:
            return
        for root in RUNSC_ROOTS:
            if not os.path.isdir(root):
                continue
            try:
                done = subprocess.run(
                    [self.runsc, "--root", root, "events", "--stats", cid],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                return
            total = parse_runsc_net(done.stdout) if done.returncode == 0 else None
            if total is None:
                continue
            before = self._sandbox_net.get(cid)
            self._sandbox_net[cid] = total
            moved = total - before if before is not None and total >= before else 0
            row["sandbox_net"] = round(moved / seconds) if seconds > 0 else 0
            row["sandbox_net_total"] = total
            return

    def _sandbox_procs(self, cid: str, seconds: float) -> list[Sample] | None:
        """What runs inside a gVisor container, with each program's share of a CPU since the
        last sample (from its CPU time; `runsc ps` C is a lifetime average)."""
        if not self.runsc:
            return None
        for root in RUNSC_ROOTS:
            if not os.path.isdir(root):
                continue
            try:
                done = subprocess.run(
                    [self.runsc, "--root", root, "ps", cid],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                return None
            if done.returncode != 0:
                continue
            procs = parse_runsc_ps(done.stdout)
            prev = self._sandbox_time.get(cid, {})
            for proc in procs:
                before = prev.get(proc["pid"])
                if before is not None and seconds > 0:
                    proc["cpu"] = round(max(0.0, proc["time"] - before) / seconds, 3)
                else:
                    proc["cpu"] = round(proc["c"] / 100, 3)
            self._sandbox_time[cid] = {p["pid"]: p["time"] for p in procs}
            return procs
        return None


def filesystems(mounts: str) -> list[Sample]:
    """Real filesystems (one row per device), with size and use."""
    found: list[Sample] = []
    seen: set[str] = set()
    for line in mounts.splitlines():
        fields = line.split()
        if len(fields) < 3 or fields[2] not in REAL_FS or fields[0] in seen:
            continue
        mount = fields[1].replace("\\040", " ")
        try:
            st = os.statvfs(mount)
        except OSError:
            continue
        seen.add(fields[0])
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        found.append({"mount": mount, "device": fields[0], "total": total, "used": total - free})
    return found


def temperatures() -> list[Sample]:
    """Labelled hwmon sensors, e.g. k10temp Tctl, nvme Composite, amdgpu edge."""
    found: list[Sample] = []
    base = "/sys/class/hwmon"
    try:
        entries = sorted(os.listdir(base))
    except OSError:
        return found
    for entry in entries:
        folder = f"{base}/{entry}"
        chip = _read(f"{folder}/name").strip()
        try:
            files = sorted(os.listdir(folder))
        except OSError:
            continue
        for file in files:
            if not (file.startswith("temp") and file.endswith("_input")):
                continue
            raw = _read(f"{folder}/{file}").strip()
            if not raw.lstrip("-").isdigit():
                continue
            label = _read(f"{folder}/{file[:-6]}_label").strip() or file[:-6]
            found.append({"chip": chip, "label": label, "c": int(raw) / 1000})
    return found[:16]


def _num(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return 0.0


def _float(parts: list[str]) -> float:
    return _num(parts[0]) if parts else 0.0


def main(argv: list[str]) -> int:
    interval = 2.0
    if len(argv) >= 2 and argv[0] == "--interval":
        interval = max(0.5, float(argv[1]))
    sampler = Sampler()
    next_at = time.monotonic()
    while True:
        line = json.dumps(sampler.sample(), separators=(",", ":"))
        try:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except (BrokenPipeError, OSError):
            return 0
        next_at += interval
        time.sleep(max(0.0, next_at - time.monotonic()))
        if time.monotonic() - next_at > interval:
            next_at = time.monotonic()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
