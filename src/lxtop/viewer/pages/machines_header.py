"""The machines page header: summary lines and big-number tiles."""

from __future__ import annotations

import curses
import time
from typing import Any

from lxtop.core import model
from lxtop.core import snapshot as sn
from lxtop.core.render import bar, clean, duration, human_bytes, human_rate, speed, speed_parts
from lxtop.core.snapshot import Json, as_dict, as_list, num, text
from lxtop.viewer.pages.base import Frame
from lxtop.viewer.pages.common import used_of
from lxtop.viewer.screen import (
    BLUE,
    CYAN,
    GREEN,
    MAGENTA,
    RED,
    WHITE,
    Tile,
    color,
    level,
    tile,
)


def machines_subtitle(frame: Frame) -> str:
    host = sn.host(frame.snapshot)
    load = " ".join(f"{num(v):.2f}" for v in as_list(host.get("load")))
    name = clean(text(host.get("hostname"), "?"))
    return f"{name}: up {duration(num(host.get('uptime')))}, load {load}"


def draw_machines_line(frame: Frame, w: int) -> None:
    """Row 1: how many instances and containers run, in a sentence."""
    snap = frame.snapshot
    instances = [as_dict(i) for i in sn.instances(snap)]
    running = [i for i in instances if text(i.get("status")).lower() == "running"]
    containers = sum(len(model.docker_containers(as_dict(i.get("probe")))) for i in instances)
    containers += len(model.docker_containers(sn.host(snap)))
    stopped = len(instances) - len(running)
    line = (
        f"{len(running)} LXD instances running"
        + (f" ({stopped} stopped)" if stopped else "")
        + f", {containers} Docker containers inside them and on the host."
    )
    frame.screen.put(1, 1, line, color(WHITE, True), w - 2)
    for message in sn.errors(snap)[:1]:
        frame.screen.right(1, w - 1, " " + clean(message, 80), color(RED, True))


def machine_tiles(frame: Frame) -> list[Tile]:
    host = sn.host(frame.snapshot)
    cpu = as_dict(host.get("cpu"))
    busy = num(cpu.get("busy"))
    cores = num(cpu.get("count"))
    mem = as_dict(host.get("mem"))
    used, total = num(mem.get("used")), num(mem.get("total"), 1)
    swap = used_of(mem.get("swap_used"), mem.get("swap_total"), percent=False)
    tiles: list[Tile] = [
        ("CPU", f"{busy * cores:.1f}", "cores", "", None, busy),
        (
            "MEMORY",
            f"{used / 2**30:.1f}",
            "GB",
            f"of {total / 2**30:.0f} GB, swap {swap}",
            None,
            used / total,
        ),
    ]
    for gpu in as_list(host.get("gpus"))[:1]:
        gpu = as_dict(gpu)
        util = num(gpu.get("util")) / 100
        vram = f"{num(gpu.get('mem_used_mib')) / 1024:.1f}/"
        vram += f"{num(gpu.get('mem_total_mib')) / 1024:.0f}G"
        note = f"vram {vram} · {num(gpu.get('temp_c')):.0f}°C {num(gpu.get('power_w')):.0f}W"
        tiles.append(("GPU", f"{util * 100:.0f}", "%", note, None, util))
    readings = temps(frame, host)
    if readings:
        label, hottest = max(readings, key=lambda t: t[1])
        note = "  ".join(f"{name} {value:.0f}" for name, value in readings)
        tiles.append(("HOTTEST", f"{hottest:.0f}", f"°C {label}", note, None, hottest / 95))
    root = next((as_dict(f) for f in as_list(host.get("fs")) if as_dict(f).get("mount") == "/"), {})
    disks = [as_dict(d) for d in as_list(host.get("disks"))]
    io = f"r {human_rate(sum(num(d.get('read')) for d in disks))}"
    io += f"  w {human_rate(sum(num(d.get('write')) for d in disks))}"
    if root:
        size = num(root.get("total")) or 1
        frac = num(root.get("used")) / size
        used_gb = f"{num(root.get('used')) / 2**30:.0f}"
        tiles.append(("ROOT DISK", used_gb, "GB", f"of {human_bytes(size, 0)} · {io}", None, frac))
    uplinks = sn.uplinks(frame.snapshot)
    rx = tx = 0.0
    for link in as_list(host.get("net")):
        link = as_dict(link)
        if text(link.get("name")) in uplinks:
            rx += num(link.get("rx"))
            tx += num(link.get("tx"))
    value, unit = speed_parts(rx)
    tiles.append(("INTERNET", value, unit, f"{frame.glyphs.up} {speed(tx)} out", GREEN, 0.0))
    return tiles


def draw_machine_tiles(frame: Frame, y: int, w: int) -> None:
    """Rows y .. y+5: the host itself in big numbers; the CPU tile's note is its cores."""
    tiles = machine_tiles(frame)
    tile_w = min(52, (w - 2) // len(tiles) - 1)
    for i, spec in enumerate(tiles):
        tile(frame.screen, y, 1 + i * (tile_w + 1), tile_w, spec)
    cores = as_list(as_dict(sn.host(frame.snapshot).get("cpu")).get("cores"))
    draw_cores(frame, y + 4, 4, cores, tile_w - 5, label="")


def draw_header(frame: Frame, w: int) -> None:
    s, g = frame.screen, frame.glyphs
    snap = frame.snapshot
    host = sn.host(snap)
    age = time.time() - sn.taken_at(snap, time.time())
    interval = sn.interval(snap)
    x = s.put(0, 0, " lxtop ", color(WHITE, True) | curses.A_REVERSE)
    x = s.put(0, x + 1, clean(text(host.get("hostname"), "?")), color(CYAN, True))
    load = " ".join(f"{num(v):.2f}" for v in as_list(host.get("load")))
    x = s.put(0, x + 2, f"up {duration(num(host.get('uptime')))}   load {load}")
    x = s.put(0, x + 3, time.strftime("%a %d %b %H:%M:%S"), color(WHITE, True))
    if frame.load_error:
        s.put(0, x + 3, clean(frame.load_error), color(RED, True))
    elif age > 3 * interval:
        s.put(0, x + 3, f"NO NEW DATA FOR {duration(age)}: collector down?", color(RED, True))
    for message in sn.errors(snap)[:1]:
        s.put(0, x + 3, clean(message, 80), color(RED, True))

    half = max(40, (w - 2) // 2)
    meter = max(10, min(40, half - 34))
    cpu = as_dict(host.get("cpu"))
    busy = num(cpu.get("busy"))
    x = s.put(1, 1, "CPU  ", color(CYAN, True))
    x = s.put(1, x, bar(busy, meter, g), level(busy))
    mhz = num(cpu.get("mhz"))
    s.put(1, x + 1, f"{busy * 100:5.1f}%  {int(num(cpu.get('count')))} cores  {mhz:.0f} MHz")
    draw_cores(frame, 2, 1, as_list(cpu.get("cores")), half - 2)
    mem = as_dict(host.get("mem"))
    used, total = num(mem.get("used")), num(mem.get("total"), 1)
    x = s.put(3, 1, "MEM  ", color(CYAN, True))
    x = s.put(3, x, bar(used / total, meter, g), level(used / total))
    swap = "swap " + used_of(mem.get("swap_used"), mem.get("swap_total"), percent=False)
    s.put(3, x + 1, f"{human_bytes(used)}/{human_bytes(total)}  {swap}")

    right = half + 1
    for gpu in as_list(host.get("gpus"))[:1]:
        gpu = as_dict(gpu)
        util = num(gpu.get("util")) / 100
        vram = num(gpu.get("mem_used_mib")) / (num(gpu.get("mem_total_mib")) or 1)
        x = s.put(1, right, "GPU  ", color(CYAN, True))
        x = s.put(1, x, bar(util, meter // 2, g), level(util))
        x = s.put(1, x + 1, f"{util * 100:3.0f}%  vram ")
        x = s.put(1, x, bar(vram, meter // 2, g), level(vram))
        vram_used, vram_total = num(gpu.get("mem_used_mib")), num(gpu.get("mem_total_mib"))
        vram_text = f"{vram_used / 1024:.1f}/{vram_total / 1024:.0f}G"
        x = s.put(1, x + 1, vram_text)
        power = f"{num(gpu.get('power_w')):.0f}W"
        s.put(
            1,
            x + 2,
            f"{num(gpu.get('temp_c')):.0f}°C {power}",
            level(num(gpu.get("temp_c")) / 95),
        )
    readings = temps(frame, host)
    x = s.put(2, right, "TEMP ", color(CYAN, True))
    for label, value in readings:
        x = s.put(2, x, f"{label} ", color(WHITE))
        x = s.put(2, x, f"{value:.0f}°C  ", level(value / 95))
    for disk in as_list(host.get("disks"))[:2]:
        disk = as_dict(disk)
        x = s.put(2, x, clean(text(disk.get("name"))) + " ", color(WHITE))
        x = s.put(
            2,
            x,
            f"r {human_rate(num(disk.get('read')))} w {human_rate(num(disk.get('write')))}  ",
        )
    root = next((as_dict(f) for f in as_list(host.get("fs")) if as_dict(f).get("mount") == "/"), {})
    if root:
        frac = num(root.get("used")) / (num(root.get("total")) or 1)
        s.put(
            2,
            x,
            f"/ {frac * 100:.0f}% of {human_bytes(num(root.get('total')), 0)}",
            level(frac),
        )
    x = s.put(3, right, "NET  ", color(CYAN, True))
    uplinks = sn.uplinks(snap)
    for net in as_list(host.get("net")):
        net = as_dict(net)
        if text(net.get("name")) in uplinks and num(net.get("rx_total")) > 0:
            x = s.put(3, x, clean(text(net.get("name"))) + " ", color(WHITE))
            x = s.put(3, x, f"{g.down}{human_rate(num(net.get('rx')))} ", color(GREEN))
            x = s.put(3, x, f"{g.up}{human_rate(num(net.get('tx')))}  ", color(MAGENTA))
    s.put(4, 0, g.hline * w, color(BLUE))


def temps(frame: Frame, host: Json) -> list[tuple[str, float]]:
    wanted = {
        ("k10temp", "Tctl"): "cpu",
        ("nvme", "Composite"): "nvme",
        ("amdgpu", "edge"): "igpu",
    }
    found = []
    for item in as_list(host.get("temps")):
        item = as_dict(item)
        label = wanted.get((text(item.get("chip")), text(item.get("label"))))
        if label:
            found.append((label, num(item.get("c"))))
    return found


def draw_cores(
    frame: Frame, y: int, x: int, cores: list[Any], width: int, label: str = "     "
) -> None:
    s, g = frame.screen, frame.glyphs
    x = s.put(y, x, label, color(CYAN))
    for core in cores[: max(0, width - len(label) - 1)]:
        busy = num(core)
        x = s.put(y, x, g.empty, color(BLUE)) if busy < 0.05 else s.put(y, x, g.full, level(busy))
