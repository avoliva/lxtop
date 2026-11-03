"""The network page's lower half: who uses the link. Traffic per VM, visitors through the
Cloudflare tunnels per site, each as a stacked chart."""

from __future__ import annotations

from collections.abc import Callable

from lxtop.core import network as net
from lxtop.core import snapshot as sn
from lxtop.core.charts import nice_top, stack
from lxtop.core.render import clean, fit, speed
from lxtop.core.snapshot import Json, as_dict, as_list, text
from lxtop.viewer.pages.common import aligned
from lxtop.viewer.pages.network_link import AXIS, speed_top
from lxtop.viewer.screen import (
    BLUE,
    CYAN,
    GREEN,
    MAGENTA,
    RED,
    WHITE,
    YELLOW,
    Screen,
    color,
    series_colour,
)


def draw_stack(
    s: Screen,
    snap: Json,
    layers: list[list[float]],
    pairs: list[int],
    where: tuple[int, int, int, int],
    as_text: Callable[[float], str],
    top_of: Callable[[list[float]], float],
) -> None:
    y, x, width, height = where
    axis = AXIS
    cols = max(1, width - axis)
    length = max([len(v) for v in layers] or [0])
    sampled = [aligned(v, length, cols) for v in layers]
    totals = [sum(c) for c in zip(*sampled, strict=True)] if sampled else []
    top = top_of(totals)
    grid = stack(sampled, cols, height, top, s.glyphs)
    for row, cells in enumerate(grid):
        label = as_text(top) if row == 0 else ("0" if row == height - 1 else "")
        s.put(y + row, x, fit(label, axis - 2, right=True), color(BLUE))
        s.put(y + row, x + axis - 1, "┤" if label else "│", color(BLUE))
        s.mark(y + row, x + axis, len(cells))
        for col, (char, owner) in enumerate(cells):
            if char != " ":
                pair = pairs[owner] if 0 <= owner < len(pairs) else BLUE
                s.put(y + row, x + axis + col, char, color(pair, True))


def draw_machines(
    s: Screen, snap: Json, where: tuple[int, int, int, int], chart: bool = True
) -> None:
    y, x, width, height = where
    machines = net.machine_rows(snap)
    s.put(y, x, "BY MACHINE  in and out together", color(WHITE, True))
    y += 1
    pairs = [series_colour(i) for i in range(len(machines))]
    chart_h = min(8, height - len(machines) - 3) if chart else 0
    if chart_h >= 3:
        layers = [
            [a + b for a, b in zip(m.rx_history, m.tx_history, strict=False)] for m in machines
        ]
        draw_stack(
            s, snap, layers, pairs, (y, x, width, chart_h), speed, lambda t: speed_top(t, 1e6)
        )
        y += chart_h + 1
    g = s.glyphs
    for i, m in enumerate(machines[: max(0, height - (y - where[0]))]):
        s.put(y + i, x, g.full * 2, color(pairs[i], True))
        cx = s.put(y + i, x + 3, fit(clean(m.name), 18), color(WHITE, True))
        cx = s.put(y + i, cx, fit(f"{g.down} {speed(m.rx)}", 15), color(GREEN))
        cx = s.put(y + i, cx, fit(f"{g.up} {speed(m.tx)}", 15), color(MAGENTA))
        if m.retrans >= 0.01:
            pair = RED if m.retrans >= net.RETRANS_BAD else YELLOW
            s.put(y + i, cx, f"{m.retrans * 100:.0f}% resent", color(pair, True), x + width - cx)


def draw_sites(s: Screen, snap: Json, where: tuple[int, int, int, int], chart: bool = True) -> None:
    y, x, width, height = where
    sites = net.site_rows(snap)
    s.put(y, x, "VISITORS  through Cloudflare tunnels", color(WHITE, True))
    y += 1
    silent = [
        text(as_dict(i).get("name"))
        for i in sn.instances(snap)
        if not as_dict(as_dict(i).get("probe")).get("tunnel")
        and any(
            "cloudflared" in text(as_dict(c).get("name"))
            for c in as_list(
                as_dict(as_dict(as_dict(i).get("probe")).get("docker")).get("containers")
            )
        )
    ]
    pairs = [series_colour(i) for i in range(len(sites))]
    chart_h = min(8, height - len(sites) - len(silent) - 3) if chart else 0
    if chart_h >= 3 and sites:
        layers = [[v * 60 for v in site.history] for site in sites]
        draw_stack(
            s,
            snap,
            layers,
            pairs,
            (y, x, width, chart_h),
            lambda v: f"{v:.0f}/min",
            lambda t: nice_top(t, 10),
        )
        y += chart_h + 1
    if not sites and not silent:
        s.put(y, x, "No tunnel reports visitors.", color(BLUE), width)
        return
    g = s.glyphs
    row = 0
    for i, site in enumerate(sites):
        if row >= height - (y - where[0]):
            return
        s.put(y + row, x, g.full * 2, color(pairs[i], True))
        cx = s.put(y + row, x + 3, fit(clean(site.name), 18), color(WHITE, True))
        cx = s.put(y + row, cx, fit(f"{site.per_minute:.0f}/min", 10), color(CYAN, True))
        link_pair = GREEN if site.connections >= 4 else YELLOW if site.connections else RED
        cx = s.put(y + row, cx, fit(f"tunnel {site.connections}/4", 11), color(link_pair, True))
        if site.bad_per_minute > 0:
            s.put(
                y + row,
                cx,
                f"{site.bad_per_minute:.0f} failed/min",
                color(RED, True),
                x + width - cx,
            )
        row += 1
    for name in silent:
        if row >= height - (y - where[0]):
            return
        s.put(y + row, x + 3, fit(clean(name), 18), color(BLUE, True))
        s.put(y + row, x + 21, "its own tunnel: no numbers", color(BLUE), max(0, width - 21))
        row += 1
