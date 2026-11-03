"""The network page: is the internet OK, where are the hiccups, and who is using the link.

Top: one sentence that says where any trouble is, then the numbers that matter big. Middle: the
internet link as one chart (download up, upload down, lost pings marked on its axis) beside the
three pings and the latest hiccups. Bottom: traffic per VM, visitors through the Cloudflare
tunnels, and the speed tests with the latest trace. Speeds are in bits per second, like an
internet plan.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from lxtop.core import network as net
from lxtop.core import snapshot as sn
from lxtop.core.render import big, clean, duration, fit, speed, speed_parts
from lxtop.core.snapshot import Json, as_dict, as_list, num, text
from lxtop.viewer.pages import network_link, network_users
from lxtop.viewer.pages.base import Frame, Page
from lxtop.viewer.pages.network_link import (
    SEVERITY,
    host_series,
)
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


def wrap(sentence: str, width: int, rows: int) -> list[str]:
    """At most `rows` lines of whole words; the last one is cut with an ellipsis if need be."""
    lines: list[str] = []
    words = sentence.split()
    while words and len(lines) < rows:
        line = words.pop(0)
        while words and len(line) + 1 + len(words[0]) <= width:
            line += " " + words.pop(0)
        lines.append(line)
    if words and lines:
        lines[-1] = fit(lines[-1] + " " + " ".join(words), width)
    return lines


class NetworkPage:
    name = "network"
    label = "network"
    title = " NETWORK "
    host_line = True
    help: tuple[tuple[str, str], ...] = ()

    def loaded(self, snapshot: Json) -> None:
        pass

    def subtitle(self, frame: Frame, height: int, width: int) -> str:
        return "the internet link, its hiccups, and who uses it"

    def footer(self, frame: Frame, after: Page, pages: Sequence[Page]) -> str:
        numbers = "  ".join(f"{i} {page.name}" for i, page in enumerate(pages, start=1))
        return f"Tab {after.label}   {numbers}   ? help"

    def handle(self, key: int, frame: Frame) -> bool:
        return False  # nothing to pick: the page only shows

    def draw(self, frame: Frame, height: int, width: int) -> None:
        s, snap = frame.screen, frame.snapshot
        if s.theme.panels:
            height -= 1  # panels need the row above the footer for their bottom frames
        sentence, severity = net.diagnosis(snap)
        s.put(1, 1, "● ", color(SEVERITY[severity], True))
        for row, line in enumerate(wrap(clean(sentence), width - 4, 2)):
            s.put(1 + row, 3, line, color(WHITE, True), width - 4)
        wide = width >= 150 and height >= 40
        y = 3
        if width >= 100 and height >= 30:
            self.draw_tiles(s, snap, y, width)
            y += 7
        room = height - y
        if wide:
            mid = max(12, min(24, room // 2))
            left = int(width * 0.6)
            each = (width - 2) // 3
            low = y + mid + 1
            places = [
                (y, 1, left - 1, mid),
                (y, left + 2, width - left - 3, mid),
                (low, 1, each - 1, height - low),
                (low, 2 + each, each - 1, height - low),
                (low, 3 + 2 * each, each - 2, height - low),
            ]
            for top, x, w, h in places:  # frames first, so the sections draw over them
                s.panel(top, x, h, w, color(BLUE))
            network_link.draw_link(s, snap, places[0])
            network_link.draw_pings(s, snap, places[1])
            network_users.draw_machines(s, snap, places[2])
            network_users.draw_sites(s, snap, places[3])
            network_link.draw_tests(s, snap, places[4])
            return
        # Narrow: one column, each part as tall as the space left allows.
        link_h = max(6, min(12, room // 3))
        network_link.draw_link(s, snap, (y, 1, width - 2, link_h))
        y += link_h + 1
        ping_h = min(8, max(4, room // 4))
        network_link.draw_pings(s, snap, (y, 1, width - 2, ping_h), compact=True)
        y += ping_h + 1
        for part in ("machines", "sites", "tests"):
            if height - y < 3:
                return
            share = {"machines": 3, "sites": 2, "tests": 1}[part]
            h = max(3, (height - y) // share)
            where = (y, 1, width - 2, h)
            if part == "machines":
                network_users.draw_machines(s, snap, where, chart=False)
            elif part == "sites":
                network_users.draw_sites(s, snap, where, chart=False)
            else:
                network_link.draw_tests(s, snap, where)
            y += h

    # ---- top ---------------------------------------------------------------------------------

    def draw_tiles(self, s: Screen, snap: Json, y: int, width: int) -> None:
        host = sn.host(snap)
        uplinks = [
            as_dict(n)
            for n in as_list(host.get("net"))
            if text(as_dict(n).get("name")) in sn.uplinks(snap)
        ]
        rx = sum(num(n.get("rx")) for n in uplinks)
        tx = sum(num(n.get("tx")) for n in uplinks)
        interval = sn.interval(snap)
        span = duration(len(host_series(snap, "rx")) * interval) or "0s"
        internet = net.ping_stats(net.net_series(snap, "ping_internet"))
        router = net.ping_stats(net.net_series(snap, "ping_router"))
        api = net.ping_stats(net.net_series(snap, "ping_service"))
        sites = net.site_rows(snap)
        visitors = sum(site.per_minute for site in sites)
        failed = sum(sum(net.net_series(snap, "bad", site.key)) * interval for site in sites)
        down_value, down_unit = speed_parts(rx)
        up_value, up_unit = speed_parts(tx)
        recent = net.ping_stats(net.net_series(snap, "ping_internet")[-30:])  # the last minute
        if not recent.count:
            ping_value, ping_unit, ping_pair = "", "no data", BLUE
        elif recent.lost == recent.count:
            ping_value, ping_unit, ping_pair = "", "NO ANSWER", RED
        else:
            ping_value, ping_unit = f"{recent.median:.0f}", "ms"
            ping_pair = YELLOW if recent.median > internet.median + 50 else GREEN
        loss_pair = RED if internet.loss >= net.LOSS_BAD else YELLOW if internet.lost else GREEN
        api_text = f"service {api.median:.0f} ms" if api.count else "service: no data"
        tiles = [
            (
                "DOWNLOAD",
                down_value,
                down_unit,
                f"peak {speed(max(host_series(snap, 'rx'), default=0))} in {span}",
                GREEN,
            ),
            (
                "UPLOAD",
                up_value,
                up_unit,
                f"peak {speed(max(host_series(snap, 'tx'), default=0))} in {span}",
                MAGENTA,
            ),
            (
                "INTERNET PING",
                ping_value,
                ping_unit,
                f"router {router.median:.1f} ms · {api_text}",
                ping_pair,
            ),
            (
                "LOST PINGS",
                f"{internet.loss * 100:.0f}",
                "%",
                f"{internet.lost} of {internet.count} to 1.1.1.1 in {span}",
                loss_pair,
            ),
            self.speed_tile(snap),
            (
                "VISITORS",
                f"{visitors:.0f}",
                "a minute",
                f"{failed:.0f} failed in {span}" if sites else "no tunnel numbers",
                RED if failed else CYAN,
            ),
        ]
        tile_w = min(44, (width - 2) // len(tiles) - 1)
        for i, (title, value, unit, note, pair) in enumerate(tiles):
            x = 1 + i * (tile_w + 1)
            attr = color(pair, True)
            s.box(y, x, 6, tile_w, color(BLUE))
            s.put(y, x + 2, f" {title} ", color(WHITE, True))
            digits = big(value) if s.glyphs.eighths and value else ("", value, "")
            for row, line in enumerate(digits):
                s.put(y + 1 + row, x + 3, line, attr)
            gap = 1 if digits[1] else 0
            s.put(y + 3 if s.glyphs.eighths else y + 2, x + 3 + len(digits[1]) + gap, unit, attr)
            s.put(y + 4, x + 3, clean(note), color(BLUE), tile_w - 5)

    def speed_tile(self, snap: Json) -> tuple[str, str, str, str, int]:
        speeds = [as_dict(v) for v in sn.speeds(snap)]
        if not speeds:
            return ("SPEED TEST", "", "not yet", "a 10 MB download every 30 min", BLUE)
        last = speeds[-1]
        value, unit = speed_parts(num(last.get("bits")) / 8)
        best = max(num(v.get("bits")) for v in speeds)
        when = time.strftime("%H:%M", time.localtime(num(last.get("at"))))
        note = f"at {when} · best {speed(best / 8)} of {len(speeds)}"
        return ("SPEED TEST", value, unit, note, CYAN)

    # ---- the link ----------------------------------------------------------------------------

    # ---- the cable line ----------------------------------------------------------------------

    # ---- the bottom three --------------------------------------------------------------------
