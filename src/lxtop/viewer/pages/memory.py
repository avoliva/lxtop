"""The memory & jobs page: whether there is room for a job, and who holds the memory.

    rows 1..  room for a job now, memory pressure, the newest out-of-memory kill
    then      the host's memory and swap, the user's slice against its cap
    left      VMs: what each costs the host beside what its guest says it uses
    right     the user's biggest jobs (units and SSH sessions) with peak and cap; who holds the GPU
    bottom    out-of-memory kills of the last week

On narrow screens the sections stack. View only.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from lxtop.core import memory as mem
from lxtop.core import snapshot as sn
from lxtop.core.render import clean, fit
from lxtop.core.snapshot import Json, as_dict, as_list, num, text
from lxtop.viewer.pages.base import Frame, Page
from lxtop.viewer.pages.common import put_lines, when
from lxtop.viewer.screen import BLUE, CYAN, GREEN, RED, WHITE, YELLOW, color

WIDE = 130
LEVELS = (GREEN, YELLOW, RED, BLUE)
Line = tuple[str, int]


def summary_lines(snap: Json, now: float) -> list[tuple[str, int]]:
    record = sn.memory(snap)
    cpu = as_dict(sn.host(snap).get("cpu"))
    load = as_list(sn.host(snap).get("load"))
    cores = int(num(cpu.get("count"), 1)) or 1
    out = [mem.room_line(record, cores, num(load[0]) if load else 0.0), mem.pressure_line(record)]
    for extra in (mem.slowed_line(record), mem.swap_line(record), mem.kill_line(record, now)):
        if extra is not None:
            out.append(extra)
    return out


def host_lines(record: Json) -> list[Line]:
    info = as_dict(record.get("meminfo"))
    out: list[Line] = []
    if info:
        total, available = num(info.get("total")), num(info.get("available"))
        swap = num(info.get("swap_total")) - num(info.get("swap_free"))
        out.append(
            (f"host   {mem.gib(total - available)} used of {mem.gib(total)}, "
             f"{mem.gib(available)} available, swap {mem.gib(swap)} used", color(WHITE))
        )  # fmt: skip
    user = as_dict(record.get("user"))
    if user:
        cap = user.get("max")
        cap_text = f"cap {mem.gib(num(cap))}" if isinstance(cap, int | float) else "never killed"
        high = user.get("high")
        slow = f", slowed past {mem.gib(num(high))}" if isinstance(high, int | float) else ""
        kills = int(num(user.get("oom_kills")))
        killed = f", {kills} killed for memory since boot" if kills else ""
        ink = RED if kills else WHITE
        out.append(
            (f"admin  {mem.gib(num(user.get('current')))} in use, {cap_text}{slow}{killed}",
             color(ink))
        )  # fmt: skip
    return out


def vm_lines(snap: Json) -> list[Line]:
    record = sn.memory(snap)
    rows = mem.vm_rows(record, sn.instances(snap))
    out: list[Line] = [
        (f"{'VM':<16}{'host pays':>11}{'guest uses':>12}{'of':>9}", color(WHITE, True))
    ]
    for name, rss, used, total in rows:
        ink = YELLOW if used and rss > 2 * used and rss > 2 * mem.GIB else WHITE
        guest = mem.gib(used) if used else "-"
        limit = mem.gib(total) if total else "-"
        out.append((f"{name:<16}{mem.gib(rss):>11}{guest:>12}{limit:>9}", color(ink)))
    for item in as_list(record.get("containers")):
        item = as_dict(item)
        out.append(
            (f"{text(item.get('name')):<16}{mem.gib(num(item.get('current'))):>11}"
             f"{'(container)':>12}", color(WHITE))
        )  # fmt: skip
    if len(out) == 1:
        out.append(("no VM processes read", color(BLUE)))
    return out


def job_lines(record: Json) -> list[Line]:
    out: list[Line] = [(f"{'JOB':<30}{'now':>9}{'peak':>9}{'cap':>9}", color(WHITE, True))]
    for job in mem.jobs(record):
        cap = job.get("max")
        cap_text = mem.gib(num(cap)) if isinstance(cap, int | float) else "-"
        peak = job.get("peak")
        peak_text = mem.gib(num(peak)) if isinstance(peak, int | float) else "-"
        ink = RED if num(job.get("oom_kills")) else WHITE
        name = fit(mem.job_name(job), 29)
        out.append(
            (f"{name} {mem.gib(num(job.get('current'))):>8}{peak_text:>9}{cap_text:>9}", color(ink))
        )
    if len(out) == 1:
        out.append(("no job of the user's above 64 MB", color(BLUE)))
    gpu = mem.gpu_rows(record)
    out.append(("", 0))
    out.append(("GPU", color(WHITE, True)))
    if gpu is None:
        out.append(("no nvidia-smi", color(BLUE)))
    elif not gpu:
        out.append(("nothing holds GPU memory", color(BLUE)))
    for app in gpu or []:
        owner = text(app.get("owner")) or "host"
        out.append(
            (f"{text(app.get('name'))[:20]:<21}{mem.gib(num(app.get('memory'))):>8}  {owner}",
             color(CYAN))
        )  # fmt: skip
    return out


def kill_lines(record: Json, now: float) -> list[Line]:
    out: list[Line] = [("OUT-OF-MEMORY KILLS, LAST 7 DAYS", color(WHITE, True))]
    oom = as_dict(record.get("oom"))
    if oom.get("error"):
        out.append((f"journal not read: {text(oom.get('error'))}", color(YELLOW)))
    for kill in mem.kills(record):
        at = num(kill.get("at"))
        scope = "the whole host" if kill.get("host_wide") is True else "its cap"
        stamp = when(at)
        out.append(
            (f"{stamp}  {text(kill.get('name')):<12} {mem.gib(num(kill.get('rss'))):>8}  "
             f"over {scope}", color(RED if kill.get("host_wide") is True else YELLOW))
        )  # fmt: skip
    if len(out) == 1 and not oom.get("error"):
        out.append(("none" if oom else "not read yet", color(GREEN if oom else BLUE)))
    return out


class MemoryPage:
    name = "memory"
    label = "memory & jobs"
    title = " MEMORY & JOBS "
    host_line = True
    help: tuple[tuple[str, str], ...] = ()

    def loaded(self, snapshot: Json) -> None:
        pass

    def subtitle(self, frame: Frame, height: int, width: int) -> str:
        return "room for a job, who holds the memory, and what was killed for it"

    def footer(self, frame: Frame, after: Page, pages: Sequence[Page]) -> str:
        return f"Tab {after.label}   ? help"

    def handle(self, key: int, frame: Frame) -> bool:
        return False  # nothing to pick: the page only shows

    def draw(self, frame: Frame, height: int, width: int) -> None:
        s, snap = frame.screen, frame.snapshot
        now = time.time()
        record = sn.memory(snap)
        y = 1
        for sentence, level in summary_lines(snap, now):
            s.put(y, 1, "● ", color(LEVELS[level], True))
            s.put(y, 3, clean(sentence), color(WHITE, level != mem.QUIET), width - 4)
            y += 1
        y += 1
        for line, attr in host_lines(record):
            s.put(y, 1, clean(line), attr, width - 2)
            y += 1
        y += 1
        left, right = vm_lines(snap), job_lines(record)
        if width >= WIDE:
            half = width // 2
            rows = max(len(left), len(right))
            put_lines(s, left, y, 1, half - 2, height)
            put_lines(s, right, y, half + 1, width - half - 2, height)
            y += rows + 1
        else:
            y = put_lines(s, left, y, 1, width - 2, height) + 1
            y = put_lines(s, right, y, 1, width - 2, height) + 1
        put_lines(s, kill_lines(record, now), y, 1, width - 2, height)
