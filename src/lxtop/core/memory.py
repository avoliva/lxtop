"""What the memory & jobs page says, from the `memory` record of `collector/memory.py`
and `collector/kernel.py`: room for a job, pressure, what each VM costs the host, the user's
jobs against their cap, who holds the GPU, and the out-of-memory kills of the last week."""

from __future__ import annotations

from lxtop.core.snapshot import Json, as_dict, as_list, num, text

GIB = float(1 << 30)
RESERVE = 4 * GIB  # kept free for the system when saying how much room a job has
PRESSURE_ATTENTION = 10.0  # memory "some" avg10, %: tasks wait for memory a tenth of the time
PRESSURE_PROBLEM = 5.0  # memory "full" avg10, %: everything stalls on memory
RECENT = 24 * 3600.0  # a kill is news for a day
SLOWED = 20.0  # % of the time the user slice stalls on memory (avg10) that is worth saying
SWAP_FULL = 0.85  # swap use, as a share, past which a job past its line could stall
GOOD, ATTENTION, PROBLEM, QUIET = 0, 1, 2, 3


def gib(value: float) -> str:
    return f"{value / GIB:.1f} GB"


def room(record: Json, cores: int, load1: float) -> tuple[float, float] | None:
    """(bytes, cores) a new job can use now at full speed, or None unread. Memory: what the
    kernel calls available, less a reserve, and no more than is left under the user's line
    (MemoryHigh, past which it is slowed and swapped but never killed; or a hard cap
    if one is set); cores: the cores less the 1-minute load."""
    info = as_dict(record.get("meminfo"))
    if "available" not in info:
        return None
    free = num(info.get("available")) - RESERVE
    user = as_dict(record.get("user"))
    for key in ("max", "high"):
        line = user.get(key)
        if isinstance(line, int | float) and line > 0:
            free = min(free, num(line) - num(user.get("current")))
    return max(0.0, free), max(0.0, cores - load1)


def slowed_line(record: Json) -> tuple[str, int] | None:
    """When the user's jobs are past their line and being slowed (they keep running)."""
    user = as_dict(record.get("user"))
    stall = num(user.get("pressure"))
    if stall < SLOWED:
        return None
    return (
        f"the user's jobs are slowed for memory {stall:.0f}% of the time (past the "
        f"{gib(num(user.get('high')))} line, swapping); they keep running.",
        ATTENTION,
    )


def swap_line(record: Json) -> tuple[str, int] | None:
    """When swap is nearly full: the one state where a job past its line could stall."""
    info = as_dict(record.get("meminfo"))
    total = num(info.get("swap_total"))
    if total <= 0:
        return None
    used = total - num(info.get("swap_free"))
    if used / total < SWAP_FULL:
        return None
    return (
        f"Swap is {used / total:.0%} full ({gib(used)} of {gib(total)}): a big job could stall.",
        PROBLEM,
    )


def room_line(record: Json, cores: int, load1: float) -> tuple[str, int]:
    found = room(record, cores, load1)
    if found is None:
        return "Memory: not read yet.", QUIET
    space, spare = found
    level = GOOD if space >= 8 * GIB else ATTENTION if space >= 2 * GIB else PROBLEM
    user = as_dict(record.get("user"))
    cap, high = num(user.get("max")), num(user.get("high"))
    if cap:
        under = f", under the user's {gib(cap)} cap"
    elif high:
        under = f" before the user's jobs are slowed at {gib(high)} (never killed)"
    else:
        under = ", no line on the user's jobs"
    return f"Room for a job now: {gib(space)} and {spare:.0f} cores{under}.", level


def pressure_line(record: Json) -> tuple[str, int]:
    found = as_dict(as_dict(record.get("pressure")).get("memory"))
    if not found:
        return "Memory pressure: not read (no /proc/pressure).", QUIET
    some, full = num(found.get("some10")), num(found.get("full10"))
    if full >= PRESSURE_PROBLEM:
        return f"Memory pressure: everything stalls {full:.0f}% of the time (10 s).", PROBLEM
    if some >= PRESSURE_ATTENTION:
        return f"Memory pressure: tasks wait for memory {some:.0f}% of the time (10 s).", ATTENTION
    return f"Memory pressure: none to speak of ({some:.1f}% waiting, 10 s).", GOOD


def kills(record: Json) -> list[Json]:
    return [as_dict(k) for k in as_list(as_dict(record.get("oom")).get("kills"))]


def kill_line(record: Json, now: float) -> tuple[str, int] | None:
    """The newest out-of-memory kill if it is from the last day."""
    found = kills(record)
    if not found:
        return None
    newest = found[0]
    ago = now - num(newest.get("at"))
    if ago > RECENT:
        return None
    hours = f"{ago / 3600:.0f} h" if ago >= 3600 else f"{ago / 60:.0f} min"
    what = f"{text(newest.get('name'))} ({gib(num(newest.get('rss')))})"
    if newest.get("host_wide") is True:
        return (f"The host ran out of memory {hours} ago and killed {what}.", PROBLEM)
    return (f"A capped job was killed for memory {hours} ago: {what}.", ATTENTION)


def vm_rows(record: Json, instances: list[Json]) -> list[tuple[str, float, float, float]]:
    """(name, host bytes, guest used, guest total) per VM, largest host cost first."""
    guest = {text(i.get("name")): i for i in instances}
    rows = []
    for vm in as_list(record.get("vms")):
        vm = as_dict(vm)
        name = text(vm.get("name"))
        inst = as_dict(guest.get(name))
        rows.append(
            (name, num(vm.get("rss")), num(inst.get("mem_used")), num(inst.get("mem_total")))
        )
    return sorted(rows, key=lambda r: -r[1])


def host_rss(record: Json, name: str) -> float | None:
    """What one VM's qemu process holds on the host, or None."""
    for vm in as_list(record.get("vms")):
        vm = as_dict(vm)
        if text(vm.get("name")) == name:
            return num(vm.get("rss"))
    return None


def jobs(record: Json) -> list[Json]:
    return [as_dict(j) for j in as_list(as_dict(record.get("user")).get("jobs"))]


def job_name(job: Json) -> str:
    """A session scope is named by its command; a unit by itself."""
    name = text(job.get("name"))
    command = text(job.get("command"))
    if name.startswith("session-") and command:
        return command
    return name.removeprefix("app-").removesuffix(".service")


def gpu_rows(record: Json) -> list[Json] | None:
    found = record.get("gpu_apps")
    return [as_dict(a) for a in found] if isinstance(found, list) else None
