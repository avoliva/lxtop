"""The machines page tree and the detail pane."""

from __future__ import annotations

import curses
import time
from typing import TYPE_CHECKING, Any

from lxtop.core import memory
from lxtop.core import snapshot as sn
from lxtop.core.charts import downsample, graph, nice_top
from lxtop.core.model import Row
from lxtop.core.render import clean, duration, fit, human_bytes, human_rate
from lxtop.core.snapshot import Json, as_dict, as_list, num, text
from lxtop.viewer.pages.base import Frame
from lxtop.viewer.pages.common import bytes_of, docker_summary, graph_heights, used_of
from lxtop.viewer.screen import (
    BLUE,
    CYAN,
    GREEN,
    RED,
    WHITE,
    color,
    level,
)

if TYPE_CHECKING:
    from lxtop.viewer.pages.machines import MachinesPage


KINDS = {"host": "host", "vm": "vm", "container": "lxc", "docker": "docker"}


def columns(frame: Frame, width: int) -> tuple[int, ...]:
    """Widths: name, kind, state, cpu, mem, net."""
    fixed = 7 + 9 + 7 + 14 + 20 + 5
    return (max(12, width - fixed), 7, 9, 7, 14, 20)


def draw_tree(
    page: MachinesPage,
    frame: Frame,
    rows: list[Row],
    top: int,
    height: int,
    width: int,
    left: int = 0,
) -> None:
    s, g = frame.screen, frame.glyphs
    name_w, kind_w, state_w, cpu_w, mem_w, net_w = columns(frame, width)
    header = (
        fit(f" NAME  (sort: {page.sort})", name_w)
        + " "
        + fit("KIND", kind_w)
        + fit("STATE", state_w)
        + fit("CPU", cpu_w, right=True)
        + " "
        + fit("MEMORY", mem_w, right=True)
        + "  "
        + fit("NET in/out", net_w)
    )
    s.put(top, left, header, color(CYAN, True) | curses.A_UNDERLINE, width)
    visible = height - 1
    keys = [r.key for r in rows]
    index = keys.index(page.selected) if page.selected in keys else 0
    if index < page.top:
        page.top = index
    elif index >= page.top + visible:
        page.top = index - visible + 1
    page.top = max(0, min(page.top, max(0, len(rows) - visible)))
    for offset, row in enumerate(rows[page.top : page.top + visible]):
        y = top + 1 + offset
        picked = row.key == page.selected
        base = curses.A_REVERSE if picked else 0
        if row.depth == 0:
            arrow = (g.open if row.key in page.expanded else g.closed) if row.children else " "
            label = f" {arrow} {clean(row.name)}"
            if row.children:
                label += f" ({row.children})"
            name_attr = color(WHITE, True) | base
        else:
            label = f"     {clean(row.name)}"
            name_attr = base
        running = row.state.lower() in ("running", "up")
        x = s.put(y, left, label, name_attr, name_w)
        x = s.put(y, x, " ", base)
        x = s.put(y, x, fit(KINDS.get(row.kind, row.kind), kind_w), color(BLUE, True) | base)
        x = s.put(
            y,
            x,
            fit(clean(row.state), state_w),
            (color(GREEN) if running else color(RED)) | base,
        )
        if running:
            x = s.put(y, x, fit(f"{row.cpu * 100:.1f}%", cpu_w, right=True), level(row.cpu) | base)
            mem = human_bytes(row.mem_used)
            if row.mem_total:
                mem += "/" + human_bytes(row.mem_total, 0)
            frac = row.mem_used / row.mem_total if row.mem_total else 0.0
            x = s.put(y, x, " " + fit(mem, mem_w, right=True), level(frac) | base)
            net = f"{g.down}{human_bytes(row.rx)} {g.up}{human_bytes(row.tx)}"
            s.put(y, x, "  " + fit(net, net_w), base, left + width - x)
        else:
            s.put(y, x, "", base, left + width - x)
    if len(rows) > visible:
        s.put(top + height - 1, left + width - 12, f" {index + 1}/{len(rows)} ", color(BLUE))


def draw_detail(frame: Frame, row: Row, top: int, height: int, x: int, width: int) -> None:
    s = frame.screen
    width = max(20, width - 1)
    kind = {"host": "host", "vm": "LXD VM", "container": "LXD container", "docker": "Docker"}
    title = f" {clean(row.name)} "
    s.put(top, x, title, color(WHITE, True) | curses.A_REVERSE)
    s.put(
        top,
        x + len(title) + 1,
        f"{kind.get(row.kind, row.kind)}  ·  {clean(row.state)}",
        color(CYAN),
    )
    found = facts(frame, row)
    y = top + 1
    half = width // 2
    for i in range(0, len(found), 2):
        for col, (label, value) in enumerate(found[i : i + 2]):
            cx = x + col * half
            s.put(y, cx, fit(label, 10), color(BLUE, True))
            s.put(y, cx + 11, clean(value), 0, half - 12)
        y += 1
    y += 1
    series = as_dict(sn.history(frame.snapshot).get(row.key))
    cpu_h, mem_h, net_h = graph_heights(top + height - y, bottom_rows(frame, row))
    interval = sn.interval(frame.snapshot)
    span = duration(len(as_list(series.get("cpu"))) * interval)
    cap = cpu_cap(frame, row)
    cpu_note = f"{row.cpu * 100:.1f}% of {cap:g} cores" if cap else f"{row.cpu * 100:.1f}%"
    y = draw_graph(frame, y, x, width, f"CPU  {cpu_note}", series.get("cpu"), 1.0, cpu_h, "%", span)
    mem_note = human_bytes(row.mem_used) + (
        f" of {human_bytes(row.mem_total)}" if row.mem_total else ""
    )
    mem_top = row.mem_total or nice_top([num(v) for v in as_list(series.get("mem"))], 1)
    y = draw_graph(
        frame, y, x, width, f"MEM  {mem_note}", series.get("mem"), mem_top, mem_h, "B", span
    )
    rx_vals = [num(v) for v in as_list(series.get("rx"))]
    tx_vals = [num(v) for v in as_list(series.get("tx"))]
    net_top = nice_top(rx_vals + tx_vals, 1024, base=1024)
    y = draw_graph(
        frame, y, x, width, f"IN   {human_rate(row.rx)}", rx_vals, net_top, net_h, "B", span
    )
    y = draw_graph(
        frame, y, x, width, f"OUT  {human_rate(row.tx)}", tx_vals, net_top, net_h, "B", span
    )
    end = top + height
    if row.kind == "docker":
        draw_labels(frame, y, x, width, end, row.data)
    else:
        source = row.data if row.kind == "host" else as_dict(row.data.get("probe"))
        draw_procs(frame, y, x, width, end, source, row)


def bottom_rows(frame: Frame, row: Row) -> int:
    """Rows the list under the graphs wants: labels for a container, processes otherwise."""
    if row.kind == "docker":
        return len(as_dict(row.data.get("labels"))) + 2
    source = row.data if row.kind == "host" else as_dict(row.data.get("probe"))
    return len(as_list(source.get("procs"))) + 1 or 2


def cpu_cap(frame: Frame, row: Row) -> float:
    if row.kind == "host":
        return num(as_dict(row.data.get("cpu")).get("count"))
    return num(row.data.get("cpu_cap"))


def draw_graph(
    frame: Frame,
    y: int,
    x: int,
    width: int,
    title: str,
    values: Any,
    top: float,
    height: int,
    unit: str,
    span: str,
) -> int:
    s, g = frame.screen, frame.glyphs
    data = [num(v) for v in as_list(values)]
    s.put(y, x, title, color(CYAN, True))
    peak = max(data, default=0.0)
    peak_text = f"{peak * 100:.0f}%" if unit == "%" else human_bytes(peak)
    s.put(y, x + width - 26, fit(f"peak {peak_text}  last {span}", 26, right=True), color(BLUE))
    axis = 7
    cols = max(1, width - axis)
    lines = graph(downsample(data, cols), cols, height, top, g)
    top_text = "100%" if unit == "%" else human_bytes(top, 0)
    for i, line in enumerate(lines):
        label = top_text if i == 0 else ("0" if i == height - 1 else "")
        s.put(y + 1 + i, x, fit(label, axis - 1, right=True), color(BLUE))
        s.put(
            y + 1 + i,
            x + axis,
            line,
            level(peak / top if top else 0) if unit == "%" else color(GREEN),
        )
    return y + height + 1


def facts(frame: Frame, row: Row) -> list[tuple[str, str]]:
    d = row.data
    if row.kind == "host":
        fs = [as_dict(f) for f in as_list(d.get("fs"))]
        out = [
            ("uptime", duration(num(d.get("uptime")))),
            ("cores", f"{int(num(as_dict(d.get('cpu')).get('count')))}"),
            ("docker", docker_summary(d)),
        ]
        for f in fs[:4]:
            out.append(
                (
                    text(f.get("mount"))[:10],
                    used_of(f.get("used"), f.get("total")),
                )
            )
        for gpu in as_list(d.get("gpus")):
            gpu = as_dict(gpu)
            out.append(("gpu", f"{text(gpu.get('name'))}  fan {num(gpu.get('fan_pct')):.0f}%"))
            out.append(
                (
                    "power",
                    f"{num(gpu.get('power_w')):.0f}W of {num(gpu.get('power_limit_w')):.0f}W",
                )
            )
        return out
    if row.kind == "docker":
        labels = as_dict(d.get("labels"))
        limit = num(d.get("cpu_limit"))
        return [
            ("image", text(d.get("image"))),
            ("status", text(d.get("status"))),
            ("id", text(d.get("id"))[:12]),
            ("created", time.strftime("%Y-%m-%d %H:%M", time.localtime(num(d.get("created"))))),
            ("cpu limit", f"{limit:g} cores" if limit else "none"),
            ("mem limit", human_bytes(num(d.get("mem_limit")))),
            ("pids", f"{int(num(d.get('pids')))}"),
            ("restarts", f"{int(num(d.get('restarts')))}"),
            (
                "block io",
                f"r {bytes_of(d, 'blk_read')}  w {bytes_of(d, 'blk_write')}",
            ),
            ("network", text(d.get("network_mode")) or "?"),
            ("ports", ", ".join(text(p) for p in as_list(d.get("ports"))) or "none"),
            ("labels", str(len(labels))),
        ]
    probe = as_dict(d.get("probe"))
    out = [
        ("project", text(d.get("project"))),
        (
            "limits",
            f"cpu {text(d.get('limits_cpu')) or 'host'}  "
            f"mem {text(d.get('limits_memory')) or 'host'}",
        ),
        (
            "disk",
            f"{human_bytes(num(d.get('disk_used')))}"
            + (f" of {human_bytes(num(d.get('disk_total')))}" if num(d.get("disk_total")) else ""),
        ),
        ("processes", f"{int(num(d.get('processes')))}"),
        ("address", ", ".join(text(a) for a in as_list(d.get("addresses"))) or "none"),
        ("probe", text(d.get("probe_status"))),
    ]
    rss = memory.host_rss(sn.memory(frame.snapshot), text(d.get("name")))
    if rss is not None:  # what the VM's qemu holds on the host
        out.insert(2, ("host pays", f"{human_bytes(rss)} of the host's memory"))
    if probe:
        load = " ".join(f"{num(v):.2f}" for v in as_list(probe.get("load")))
        mem = as_dict(probe.get("mem"))
        guest_cpu = as_dict(probe.get("cpu"))
        out += [
            ("docker", docker_summary(probe)),
            ("guest up", duration(num(probe.get("uptime")))),
            ("guest load", load),
            (
                "guest mem",
                f"{bytes_of(mem, 'used')} used, {bytes_of(mem, 'cached')} cache",
            ),
            (
                "guest cpu",
                f"{num(guest_cpu.get('busy')) * 100:.1f}% of "
                f"{int(num(guest_cpu.get('count')))} cores",
            ),
        ]
        for f in [as_dict(f) for f in as_list(probe.get("fs"))][:2]:
            out.append(
                (
                    text(f.get("mount"))[:10],
                    used_of(f.get("used"), f.get("total")),
                )
            )
    return out


def draw_procs(frame: Frame, y: int, x: int, width: int, end: int, source: Json, row: Row) -> None:
    s = frame.screen
    procs = [as_dict(p) for p in as_list(source.get("procs"))]
    if y >= end:
        return
    if not procs:
        note = (
            "no process list"
            if row.kind == "host"
            else f"no data from inside ({text(row.data.get('probe_status'), 'off')})"
        )
        s.put(y, x, clean(note), color(BLUE))
        return
    cores = num(as_dict(source.get("cpu")).get("count"), 1)
    s.put(
        y,
        x,
        fit("    PID USER         CPU    MEM  COMMAND", width),
        color(CYAN, True) | curses.A_UNDERLINE,
    )
    for proc in procs[: max(0, end - y - 1)]:
        y += 1
        cpu = num(proc.get("cpu"))
        line = f"{int(num(proc.get('pid'))):7d} {fit(clean(text(proc.get('user'))), 10)} "
        s.put(y, x, line)
        s.put(y, x + len(line), f"{cpu * 100:5.0f}%", level(cpu / cores * 4))
        s.put(y, x + len(line) + 7, f"{human_bytes(num(proc.get('rss'))):>6}  ")
        s.put(y, x + len(line) + 15, clean(text(proc.get("cmd"))), 0, width - len(line) - 15)


def draw_labels(frame: Frame, y: int, x: int, width: int, end: int, data: Json) -> None:
    s = frame.screen
    labels = as_dict(data.get("labels"))
    if y >= end:
        return
    s.put(y, x, fit("LABELS", width), color(CYAN, True) | curses.A_UNDERLINE)
    for key in sorted(labels)[: max(0, end - y - 1)]:
        y += 1
        s.put(y, x, clean(key), color(BLUE, True), min(40, width // 2))
        s.put(
            y,
            x + min(40, width // 2) + 1,
            clean(text(labels[key])),
            0,
            width - min(40, width // 2) - 1,
        )
    if data.get("error"):
        s.put(min(end - 1, y + 1), x, clean(text(data.get("error"))), color(RED), width)
