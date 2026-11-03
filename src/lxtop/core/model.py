"""Pure data logic shared by the collector and the viewer: LXD rows, rates, history, the tree."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from lxtop.core import snapshot as sn
from lxtop.core.snapshot import Json, Snap, as_dict, as_list, num, text

SERIES = ("cpu", "mem", "rx", "tx")
SORTS = ("name", "cpu", "mem")


def cpu_limit(value: object, host_cores: int) -> float:
    """LXD `limits.cpu`: a count ("6"), a range ("0-3"), a list ("1,3,5"), or unset."""
    raw = text(value).strip()
    if not raw:
        return float(host_cores)
    if raw.isdigit():
        return float(raw)
    count = 0
    for part in raw.split(","):
        start, _, end = part.partition("-")
        if start.strip().isdigit() and (not end or end.strip().isdigit()):
            count += int(end) - int(start) + 1 if end else 1
    return float(count or host_cores)


class Rates:
    """Per-second rates of cumulative counters, keyed by any string."""

    def __init__(self) -> None:
        self._last: dict[str, tuple[float, float]] = {}

    def rate(self, key: str, value: float, now: float) -> float:
        prev = self._last.get(key)
        self._last[key] = (value, now)
        if prev is None or now <= prev[1] or value < prev[0]:
            return 0.0
        return (value - prev[0]) / (now - prev[1])

    def forget_except(self, keys: Iterable[str]) -> None:
        keep = set(keys)
        self._last = {k: v for k, v in self._last.items() if k in keep}


def instance_rows(instances: list[Any], rates: Rates, now: float, host_cores: int) -> list[Json]:
    """LXD `/1.0/instances?recursion=2` metadata -> one flat row per instance."""
    rows: list[Json] = []
    for item in instances:
        inst = as_dict(item)
        name = text(inst.get("name"), "?")
        project = text(inst.get("project"), "default")
        key = f"i:{project}/{name}"
        config = as_dict(inst.get("config"))
        expanded = as_dict(inst.get("expanded_config")) or config
        state = as_dict(inst.get("state"))
        memory = as_dict(state.get("memory"))
        cpu_ns = num(as_dict(state.get("cpu")).get("usage"))
        cap = cpu_limit(expanded.get("limits.cpu"), host_cores)
        cores = rates.rate(f"{key}:cpu", cpu_ns, now) / 1e9
        rx = tx = 0.0
        addresses: list[str] = []
        for iface, net in as_dict(state.get("network")).items():
            if iface == "lo":
                continue
            counters = as_dict(as_dict(net).get("counters"))
            rx += num(counters.get("bytes_received"))
            tx += num(counters.get("bytes_sent"))
            for addr in as_list(as_dict(net).get("addresses")):
                addr = as_dict(addr)
                if text(addr.get("scope")) == "global" and text(addr.get("family")) == "inet":
                    addresses.append(f"{text(addr.get('address'))} ({iface})")
        root = as_dict(as_dict(state.get("disk")).get("root"))
        rows.append(
            {
                "key": key,
                "name": name,
                "project": project,
                "type": "vm" if text(inst.get("type")) == "virtual-machine" else "container",
                "status": text(inst.get("status"), "Unknown"),
                "running": text(inst.get("status")) == "Running",
                "cpu_cores": max(0.0, cores),
                "cpu_cap": cap,
                "mem_used": num(memory.get("usage")),
                "mem_total": num(memory.get("total")) or _memory_limit(expanded),
                "rx": rates.rate(f"{key}:rx", rx, now),
                "tx": rates.rate(f"{key}:tx", tx, now),
                "disk_used": num(root.get("usage")),
                "disk_total": num(root.get("total")),
                "processes": num(state.get("processes"), -1),
                "addresses": addresses,
                "created": text(inst.get("created_at")),
                "last_used": text(inst.get("last_used_at")),
                "limits_cpu": text(expanded.get("limits.cpu")),
                "limits_memory": text(expanded.get("limits.memory")),
                "description": text(inst.get("description")),
            }
        )
    rows.sort(key=lambda r: (r["project"], r["name"]))
    return rows


def _memory_limit(config: Mapping[str, Any]) -> float:
    raw = text(config.get("limits.memory")).strip()
    units = {
        "KiB": 2**10,
        "MiB": 2**20,
        "GiB": 2**30,
        "TiB": 2**40,
        "KB": 1e3,
        "MB": 1e6,
        "GB": 1e9,
    }
    for suffix, scale in units.items():
        if raw.endswith(suffix) and raw[: -len(suffix)].strip().replace(".", "", 1).isdigit():
            return float(raw[: -len(suffix)]) * scale
    return float(raw) if raw.isdigit() else 0.0


class History:
    """A fixed-length series per item key and series name: cpu (fraction of its capacity), mem,
    rx and tx for every item, and any other name the collector puts (pings, visitors...)."""

    def __init__(self, length: int) -> None:
        self.length = length
        self._data: dict[str, dict[str, deque[float]]] = {}
        self._seen: dict[str, int] = {}
        self._tick = 0

    def push(self, key: str, cpu: float, mem: float, rx: float, tx: float) -> None:
        for name, value in zip(SERIES, (cpu, mem, rx, tx), strict=True):
            self.put(key, name, value)

    def put(self, key: str, name: str, value: float) -> None:
        series = self._data.setdefault(key, {})
        if name not in series:
            series[name] = deque(maxlen=self.length)
        series[name].append(round(value, 4))
        self._seen[key] = self._tick

    def end_tick(self) -> None:
        """Drop items not pushed for a whole history length (a removed container, say)."""
        self._tick += 1
        stale = [k for k, seen in self._seen.items() if self._tick - seen > self.length]
        for key in stale:
            self._data.pop(key, None)
            self._seen.pop(key, None)

    def export(self) -> dict[str, dict[str, list[float]]]:
        return {k: {n: list(s) for n, s in series.items()} for k, series in self._data.items()}


def container_key(parent: str, container_id: str) -> str:
    """History and tree key of a Docker container under `host` or an instance key."""
    return f"{parent}/c:{container_id[:12]}"


def busy(cores: float, cap: float) -> float:
    return cores / cap if cap > 0 else 0.0


# ---- the viewer's tree ------------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    key: str
    depth: int
    kind: str  # host | vm | container | docker
    name: str
    state: str
    cpu: float  # fraction of the item's own capacity
    mem_used: float
    mem_total: float
    rx: float
    tx: float
    children: int
    data: Json


def host_row(snapshot: Snap) -> Row:
    host = sn.host(snapshot)
    cpu = as_dict(host.get("cpu"))
    mem = as_dict(host.get("mem"))
    nets = [as_dict(n) for n in as_list(host.get("net"))]
    uplinks = [n for n in nets if text(n.get("name")) in sn.uplinks(snapshot)]
    containers = docker_containers(host)
    return Row(
        key="host",
        depth=0,
        kind="host",
        name=text(host.get("hostname"), "host"),
        state="up",
        cpu=num(cpu.get("busy")),
        mem_used=num(mem.get("used")),
        mem_total=num(mem.get("total")),
        rx=sum(num(n.get("rx")) for n in uplinks),
        tx=sum(num(n.get("tx")) for n in uplinks),
        children=len(containers),
        data=host,
    )


def docker_containers(sample: Json) -> list[Json]:
    return [as_dict(c) for c in as_list(as_dict(sample.get("docker")).get("containers"))]


def container_row(parent: str, depth: int, item: Json, fallback_cap: float) -> Row:
    cap = num(item.get("cpu_cap")) or fallback_cap
    return Row(
        key=container_key(parent, text(item.get("id"))),
        depth=depth,
        kind="docker",
        name=text(item.get("name"), "?"),
        state=text(item.get("state"), "?"),
        cpu=busy(num(item.get("cpu_cores")), cap),
        mem_used=num(item.get("mem_used")),
        mem_total=num(item.get("mem_limit")),
        rx=num(item.get("rx")),
        tx=num(item.get("tx")),
        children=0,
        data=item,
    )


def _order(rows: list[Row], sort: str) -> list[Row]:
    if sort == "cpu":
        return sorted(rows, key=lambda r: (-r.cpu, r.name))
    if sort == "mem":
        return sorted(rows, key=lambda r: (-r.mem_used, r.name))
    return sorted(rows, key=lambda r: (r.state != "running" and r.state != "Running", r.name))


def tree(snapshot: Snap, expanded: set[str], sort: str = "name") -> list[Row]:
    """Host first with its own containers, then each instance with the containers inside it."""
    host = host_row(snapshot)
    out = [host]
    host_cores = num(as_dict(host.data.get("cpu")).get("count"), 1)
    if host.key in expanded:
        kids = [container_row("host", 1, c, host_cores) for c in docker_containers(host.data)]
        out.extend(_order(kids, sort))
    instances: list[Row] = []
    for inst in sn.instances(snapshot):
        inst = as_dict(inst)
        probe = as_dict(inst.get("probe"))
        instances.append(
            Row(
                key=text(inst.get("key")),
                depth=0,
                kind=text(inst.get("type"), "vm"),
                name=text(inst.get("name"), "?"),
                state=text(inst.get("status"), "?"),
                cpu=busy(num(inst.get("cpu_cores")), num(inst.get("cpu_cap"), 1)),
                mem_used=num(inst.get("mem_used")),
                mem_total=num(inst.get("mem_total")),
                rx=num(inst.get("rx")),
                tx=num(inst.get("tx")),
                children=len(docker_containers(probe)),
                data=inst,
            )
        )
    for row in _order(instances, sort):
        out.append(row)
        if row.key in expanded:
            probe = as_dict(row.data.get("probe"))
            cap = num(row.data.get("cpu_cap"), 1)
            kids = [container_row(row.key, 1, c, cap) for c in docker_containers(probe)]
            out.extend(_order(kids, sort))
    return out
