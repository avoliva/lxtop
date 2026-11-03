"""What the timers & services page says, from the `units` record: the user's timers and
running services, and the failed units of the host."""

from __future__ import annotations

from lxtop.core.snapshot import Json, as_dict, as_list, text

GOOD, ATTENTION, PROBLEM, QUIET = 0, 1, 2, 3


def timers(record: Json) -> list[Json]:
    return [as_dict(t) for t in as_list(record.get("timers"))]


def timer_state(timer: Json) -> tuple[str, int]:
    """How the timer's service last ended: ("ok", GOOD), ("running", ATTENTION), ("failed:
    exit 2", PROBLEM) or ("never ran", QUIET)."""
    state = as_dict(timer.get("service_state"))
    active = text(state.get("active"))
    if active in ("activating", "active") and text(state.get("sub")) in ("start", "running"):
        return "running", ATTENTION
    result = text(state.get("result"))
    if not result:
        return ("never ran", QUIET) if timer.get("last") is None else ("?", QUIET)
    if result == "success":
        return "ok", GOOD
    status = state.get("status")
    exit_ = f", exit {status}" if isinstance(status, int) and status else ""
    return f"{result}{exit_}", PROBLEM


def failed(units: Json) -> list[tuple[str, str, list[str]]]:
    """(where, unit, last log lines) of every failed unit: the host's and the user's own."""
    out = []
    for item in as_list(units.get("failed")):
        item = as_dict(item)
        scope = text(item.get("scope"))
        where = "host" if scope == "system" else f"host ({scope})"
        log = [text(line) for line in as_list(item.get("log"))]
        out.append((where, text(item.get("unit")), log))
    return out


def running(units: Json) -> list[str]:
    return [text(as_dict(u).get("unit")) for u in as_list(units.get("running"))]
