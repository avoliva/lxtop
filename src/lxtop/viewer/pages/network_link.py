"""The network page's internet half: the link as one mirrored chart with lost pings on its
axis, the three pings and the recent hiccups."""

from __future__ import annotations

import curses
import time

from lxtop.core import network as net
from lxtop.core import snapshot as sn
from lxtop.core.charts import lines, nice_top
from lxtop.core.render import clean, duration, fit, speed
from lxtop.core.snapshot import Json, as_dict, as_list, num, text
from lxtop.viewer.pages.common import LOST_MARK, SLOW_MARK
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
)

SEVERITY = (GREEN, YELLOW, RED)
AXIS = 13  # room for "100 Mbit/s ┤"
WHERE = {
    "home": "house",
    "provider": "provider",
    "service": "Service",
    "dns": "DNS",
    "link": "link",
    "site": "website",
}
UPLINK_NAMES = {"eno1": "wired", "eth0": "wired", "enp0s3": "wired", "wlan0": "Wi-Fi"}


def signal_word(dbm: float) -> str:
    if dbm >= -55:
        return "strong"
    if dbm >= -67:
        return "good"
    if dbm >= -75:
        return "weak"
    return "very weak"


def speed_top(values: list[float], floor_bits: float) -> float:
    """A round chart top for byte rates, round in bits: 1, 2, 5, 10 Mbit/s..."""
    return nice_top([v * 8 for v in values], floor_bits) / 8


def host_series(snap: Json, name: str) -> list[float]:
    return net.net_series(snap, name, "host")


def filled(values: list[float]) -> list[float]:
    """A check's series for a line: ticks with no new check hold the last answer (checks run
    every 10 s, samples every 2 s); a lost answer stays a gap."""
    out: list[float] = []
    last = -1.0
    for v in values:
        if v == net.SKIPPED:
            out.append(last)
        else:
            last = v
            out.append(v)
    return out


def check_result(snap: Json, name: str) -> Json:
    """The latest result for a ping target, from the pinger or the slow checks."""
    found = as_dict(sn.pings(snap).get(name))
    checks = sn.checks(snap)
    return found or as_dict(checks.get(f"api_{name}")) or as_dict(checks.get(name))


def draw_link(s: Screen, snap: Json, where: tuple[int, int, int, int]) -> None:
    y, x, width, height = where
    g = s.glyphs
    host = sn.host(snap)
    uplinks = sn.uplinks(snap)
    nets = [as_dict(n) for n in as_list(host.get("net"))]
    live = [n for n in nets if text(n.get("name")) in uplinks and num(n.get("rx_total")) > 0]
    main = max(live, key=lambda n: num(n.get("rx")) + num(n.get("tx")), default={})
    name = text(main.get("name"), "?")
    title = f"INTERNET LINK  {clean(name)} ({UPLINK_NAMES.get(name, 'link')})"
    cx = s.put(y, x, title, color(WHITE, True))
    rx_now = sum(num(n.get("rx")) for n in live)
    tx_now = sum(num(n.get("tx")) for n in live)
    cx = s.put(y, cx + 3, f"{g.down} {speed(rx_now)}", color(GREEN, True))
    cx = s.put(y, cx + 2, f"{g.up} {speed(tx_now)}", color(MAGENTA, True))
    wifi = [as_dict(w) for w in as_list(host.get("wifi"))]
    if wifi:
        dbm = num(wifi[0].get("dbm"))
        note = f"Wi-Fi on standby, signal {dbm:.0f} dBm ({signal_word(dbm)})"
        if cx + 3 + len(note) <= x + width:
            s.right(y, x + width, note, color(BLUE))
    rx = host_series(snap, "rx")
    tx = host_series(snap, "tx")
    axis = AXIS
    cols = max(1, width - axis)
    rows = max(3, height - 3)
    top = speed_top(rx + tx, 1e6)
    grid = lines([rx, tx], cols, rows, top, g)
    pairs = (color(GREEN, True), color(MAGENTA, True))
    for row, cells in enumerate(grid):
        label = speed(top) if row == 0 else ("0" if row == rows - 1 else "")
        if row == rows // 2:
            label = speed(top / 2)
        s.put(y + 1 + row, x, fit(label, axis - 2, right=True), color(BLUE))
        s.put(y + 1 + row, x + axis - 1, "┤" if label else "│", color(BLUE))
        s.mark(y + 1 + row, x + axis, len(cells))  # the chart's blanks are the chart's
        for col, (char, owner) in enumerate(cells):
            if char != " ":
                s.put(y + 1 + row, x + axis + col, char, pairs[owner] if owner >= 0 else 0)
    # The axis, with lost and slow pings under the moment they happened.
    base = y + 1 + rows
    s.put(base, x + axis - 1, "└" + g.hline * cols, color(BLUE))
    for col, flag in enumerate(net.trouble(snap, len(rx), cols)):
        if flag:
            mark, pair = (LOST_MARK, RED) if flag == "lost" else (SLOW_MARK, YELLOW)
            s.put(base, x + axis + col, mark, color(pair, True))
    interval = sn.interval(snap)
    span = duration(len(rx) * interval) or "0s"
    bottom = base + 1
    s.put(bottom, x + axis, f"{span} ago", color(BLUE))
    legend = f"{g.down} download   {g.up} upload   {LOST_MARK} lost check   {SLOW_MARK} slow check"
    start = x + axis + len(span) + 8
    if start + len(legend) + 4 <= x + width:
        s.put(bottom, start, legend, color(BLUE))
    s.right(bottom, x + width, "now", color(BLUE))


def draw_pings(
    s: Screen, snap: Json, where: tuple[int, int, int, int], compact: bool = False
) -> None:
    y, x, width, height = where
    end = y + height
    s.put(
        y,
        x,
        "CHECKS  router and internet every 2 s, the rest every 10-20 s",
        color(WHITE, True),
    )
    y += 1
    rows = 1 if compact else 2
    gap = 0 if compact or height < len(net.TARGETS) * 4 + 6 else 1
    for name, label, _, _ in net.TARGETS:
        if y + rows >= end:
            break
        values = net.net_series(snap, f"ping_{name}")
        result = check_result(snap, name)
        stats = net.ping_stats(values)
        flagged = net.marks(values, name)
        now_pair = GREEN
        if stats.now is not None and stats.now < 0:
            now_text, now_pair = "lost", RED
        elif stats.now is not None:
            now_text = f"{stats.now:.1f} ms"
            now_pair = YELLOW if flagged[-1] == "slow" else GREEN
        else:
            now_text, now_pair = text(result.get("error"), "no data"), BLUE
        head = f"{label[0].upper()}{label[1:]}"
        cx = s.put(y, x, fit(head, 17), color(CYAN, True))
        cx = s.put(y, cx, fit(clean(text(result.get("target"))), 18), color(BLUE))
        cx = s.put(y, cx, fit(clean(now_text), 10), color(now_pair, True))
        if stats.count:
            lost_pair = RED if stats.loss >= net.LOSS_BAD else YELLOW if stats.lost else BLUE
            cx = s.put(
                y, cx, f"usually {stats.median:.0f} · worst {stats.worst:.0f}  ", color(BLUE)
            )
            s.put(y, cx, f"lost {stats.lost} of {stats.count}", color(lost_pair, True))
        y += 1
        cols = max(1, width)
        line_values = filled(values)
        top = nice_top([v for v in line_values if v >= 0] or [1.0], 1.0)
        grid = lines([line_values], cols, rows, top, s.glyphs)
        column = net.worst(values, cols)
        column_flags = net.marks(column, name) if column else []
        offset = cols - len(column)
        slow = {offset + i for i, f in enumerate(column_flags) if f == "slow"}
        for row, cells in enumerate(grid):
            s.mark(y + row, x, len(cells))
            for col, (char, _) in enumerate(cells):
                if char != " ":
                    pair = YELLOW if col in slow else GREEN
                    s.put(y + row, x + col, char, color(pair, True))
        for i, flag in enumerate(column_flags):
            if flag == "lost":
                s.put(y + rows - 1, x + offset + i, LOST_MARK, color(RED, True))
        y += rows
        if not compact and name == "service" and "first" in result and y < end:
            ms = {k: f"{num(result.get(k)):.0f}" for k in ("dns", "connect", "tls", "first")}
            steps = (
                f"  lookup {ms['dns']} · connect {ms['connect']} · TLS {ms['tls']}"
                f" · first byte {ms['first']} ms"
            )
            s.put(y, x, steps, color(BLUE), width)
            y += 1
        if not compact and name == "dns_local" and y < end:
            others = []
            for job, who in (("dns_google", "Google"), ("dns_cloudflare", "Cloudflare")):
                other = net.ping_stats(net.net_series(snap, f"ping_{job}"))
                if other.count:
                    others.append(f"{who} {other.median:.0f} ms, lost {other.lost}")
            if others:
                s.put(y, x, "  " + " · ".join(others), color(BLUE), width)
                y += 1
        y += gap
    if compact or y + 2 >= end:
        return
    s.put(y, x, "RECENT HICCUPS", color(WHITE, True) | curses.A_UNDERLINE)
    y += 1
    found = net.hiccups(snap, time.time())
    if not found:
        s.put(y, x, "None in this window. All quiet.", color(GREEN, True), width)
        return
    shown = found[: max(0, end - y)]
    for i, h in enumerate(shown):
        if len(found) > len(shown) and i == len(shown) - 1:
            s.put(y + i, x, f"… and {len(found) - i} more", color(BLUE))
            break
        when = time.strftime("%H:%M:%S", time.localtime(h.when))
        cx = s.put(y + i, x, when + "  ", color(BLUE))
        cx = s.put(y + i, cx, fit(WHERE.get(h.where, h.where), 10), color(CYAN))
        s.put(y + i, cx, clean(h.what), color(SEVERITY[h.severity], True), x + width - cx)


def draw_tests(s: Screen, snap: Json, where: tuple[int, int, int, int]) -> None:
    """The speed tests (10 MB every 30 min) and the latest trace after internet loss."""
    y, x, width, height = where
    end = y + height
    speeds = [num(as_dict(v).get("bits")) for v in sn.speeds(snap)]
    if y < end - 1:
        s.put(y, x, "SPEED TESTS  10 MB every 30 min", color(WHITE, True), width)
        if speeds:
            s.right(y, x + width, f"last {speed(speeds[-1] / 8)}", color(CYAN, True))
            if len(speeds) > 1 and y + 3 < end:
                top = nice_top(speeds, 1e6)
                for row, cells in enumerate(lines([speeds], width, 2, top, s.glyphs)):
                    s.mark(y + 1 + row, x, len(cells))
                    for col, (char, _) in enumerate(cells):
                        if char != " ":
                            s.put(y + 1 + row, x + col, char, color(CYAN, True))
                y += 2
        else:
            s.put(
                y + 1,
                x,
                "the first runs within 30 min of the collector starting",
                color(BLUE),
                width,
            )
            y += 1
        y += 2
    trace = sn.trace(snap)
    if y < end - 1:
        s.put(y, x, "TRACE  runs when internet loss passes 5%", color(WHITE, True), width)
        y += 1
        if not trace:
            s.put(y, x, "none yet", color(BLUE), width)
        elif trace.get("error"):
            s.put(y, x, clean(text(trace.get("error"))), color(YELLOW), width)
        else:
            when = time.strftime("%H:%M", time.localtime(num(trace.get("at"))))
            first = as_dict(trace.get("first_lossy"))
            if first:
                what = (
                    f"{when}: loss starts at hop {int(num(first.get('hop')))}"
                    f" ({clean(text(first.get('host')))}, {num(first.get('loss')):.0f}% lost)"
                )
                s.put(y, x, what, color(RED, True), width)
            else:
                s.put(y, x, f"{when}: no hop kept losing packets", color(GREEN), width)
