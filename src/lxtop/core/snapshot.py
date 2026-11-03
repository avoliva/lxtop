"""The snapshot the collector writes every interval and the viewer reads.

`Snapshot` names every top-level key. The collector builds one whole, so mypy checks that it
writes each key and no other. The viewer reads the file back as plain JSON, which may be partial
or from an older collector, and reads each part through the functions below, which never fail on
a missing or wrongly typed value. Below the top level the values come partly from the probes
inside guests and are untrusted, so they are read with `num`, `text`, `as_dict` and `as_list`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, TypedDict

# A JSON object as `json.loads` returns it. The only definition: every module imports it here.
Json = dict[str, Any]
# A snapshot as it is read: a Snapshot the collector built, or the JSON the viewer loaded.
Snap = Mapping[str, Any]
VERSION = 1
INTERVAL = 2.0  # seconds between snapshots when a snapshot does not say


class Snapshot(TypedDict):
    version: int
    time: float  # when it was taken, in seconds since the epoch
    interval: float  # seconds between snapshots
    uplinks: list[str]  # the host's interfaces that reach the internet
    host: Json  # the host itself, from probe.Sampler
    instances: list[Json]  # one row per LXD instance (model.instance_rows), each with its probe
    errors: list[str]
    pings: Json  # the pinger's latest result per target
    checks: Json  # the slow checks' latest result per job
    memory: Json  # pressure, VMs' host memory, the user slice and its jobs, GPU, `oom`
    units: Json  # the user's timers and running services, failed units
    alerts: list[Json]  # the problems, loudest first: {"text", "level"} (core/alerts.py)
    room: Json  # room for a job now: {"bytes", "cores"} (core/memory.room), {} unread
    speeds: list[Json]  # speed tests, newest last
    trace: Json  # the latest trace after loss
    history: dict[str, dict[str, list[float]]]  # item key -> series name -> values, oldest first


KEYS = frozenset(Snapshot.__required_keys__)


# ---- reading untrusted JSON ---------------------------------------------------------------------


def num(value: object, default: float = 0.0) -> float:
    """A finite number from untrusted JSON, or `default` (bools, strings, NaN and inf too)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    number = float(value)
    return number if math.isfinite(number) else default


def text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def as_dict(value: object) -> Json:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


# ---- the snapshot's parts -----------------------------------------------------------------------


def taken_at(snap: Snap, default: float) -> float:
    return num(snap.get("time"), default)


def interval(snap: Snap) -> float:
    return num(snap.get("interval"), INTERVAL)


def uplinks(snap: Snap) -> list[str]:
    return [name for name in as_list(snap.get("uplinks")) if isinstance(name, str)]


def host(snap: Snap) -> Json:
    return as_dict(snap.get("host"))


def instances(snap: Snap) -> list[Json]:
    return [as_dict(item) for item in as_list(snap.get("instances"))]


def errors(snap: Snap) -> list[str]:
    return [text(message) for message in as_list(snap.get("errors"))]


def pings(snap: Snap) -> Json:
    return as_dict(snap.get("pings"))


def checks(snap: Snap) -> Json:
    return as_dict(snap.get("checks"))


def check(snap: Snap, name: str) -> Json:
    """The latest result of one slow check (`api_service`, `dns_local`, `speed`, ...)."""
    return as_dict(checks(snap).get(name))


def memory(snap: Snap) -> Json:
    return as_dict(snap.get("memory"))


def units(snap: Snap) -> Json:
    return as_dict(snap.get("units"))


def alerts(snap: Snap) -> list[tuple[str, int]]:
    """The collector's alerts as (sentence, level), loudest first."""
    out = []
    for item in as_list(snap.get("alerts")):
        item = as_dict(item)
        sentence = text(item.get("text"))
        if sentence:
            out.append((sentence, int(num(item.get("level")))))
    return out


def speeds(snap: Snap) -> list[Json]:
    return [as_dict(item) for item in as_list(snap.get("speeds"))]


def trace(snap: Snap) -> Json:
    return as_dict(snap.get("trace"))


def history(snap: Snap) -> Json:
    return as_dict(snap.get("history"))


def series(snap: Snap, key: str, name: str) -> list[float]:
    """One series of an item's history (`host`, `net`, `i:apps/app`, ...), oldest first."""
    return [num(v) for v in as_list(as_dict(history(snap).get(key)).get(name))]
