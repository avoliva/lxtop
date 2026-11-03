"""The host's problems in one list, loudest first: a recent out-of-memory kill, memory
pressure, failed units and timers whose last run failed."""

from __future__ import annotations

from lxtop.core import memory as mem
from lxtop.core import services
from lxtop.core import snapshot as sn
from lxtop.core.snapshot import Snap

PROBLEM, ATTENTION = 2, 1


def alerts(snap: Snap, now: float) -> list[tuple[str, int]]:
    """(sentence, level) with level 2 a problem and 1 worth a look; quiet things are left out."""
    out: list[tuple[str, int]] = []
    record = sn.memory(snap)
    kill = mem.kill_line(record, now)
    if kill is not None:
        out.append(kill)
    for extra in (mem.swap_line(record), mem.slowed_line(record)):
        if extra is not None:
            out.append(extra)
    pressure, level = mem.pressure_line(record)
    if level in (PROBLEM, ATTENTION):
        out.append((pressure, level))
    units = sn.units(snap)
    broken = services.failed(units)
    if broken:
        names = ", ".join(f"{unit} ({where})" for where, unit, _ in broken[:3])
        more = f" and {len(broken) - 3} more" if len(broken) > 3 else ""
        out.append((f"Failed: {names}{more}.", PROBLEM))
    bad = [t for t in services.timers(units) if services.timer_state(t)[1] == PROBLEM]
    if bad:
        names = ", ".join(sn.text(t.get("unit")).removesuffix(".timer") for t in bad[:3])
        out.append((f"Last run failed: {names}.", PROBLEM))
    out.sort(key=lambda a: -a[1])
    return out
