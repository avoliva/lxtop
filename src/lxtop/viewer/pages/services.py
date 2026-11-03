"""The timers & services page: what runs on a schedule and what failed.

    rows 1..  the loudest of: failed units, timers whose last run failed
    left      the user's timers: last run, how it ended, next run; then their running services
    right     failed units on the host and in the user's systemd, each with its last log lines

On narrow screens the sections stack. View only: start, stop and re-run from a shell, since the
collector takes no input.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from lxtop.core import services as svc
from lxtop.core import snapshot as sn
from lxtop.core.render import clean, fit
from lxtop.core.snapshot import Json, text
from lxtop.viewer.pages.base import Frame, Page
from lxtop.viewer.pages.common import put_lines
from lxtop.viewer.screen import BLUE, CYAN, GREEN, RED, WHITE, YELLOW, color

WIDE = 130
LEVELS = (GREEN, YELLOW, RED, BLUE)
Line = tuple[str, int]


def _at(value: object, now: float) -> str:
    """ "14:05" today, "Mon 09:00" within a week, else the date; "-" for none."""
    if not isinstance(value, int | float) or value <= 0:
        return "-"
    if abs(value - now) < 20 * 3600:
        return time.strftime("%H:%M", time.localtime(value))
    if abs(value - now) < 6 * 86400:
        return time.strftime("%a %H:%M", time.localtime(value))
    return time.strftime("%d %b", time.localtime(value))


def timer_lines(units: Json, now: float) -> list[Line]:
    out: list[Line] = [
        (f"{'TIMER':<25}{'last':>10}  {'ended':<19}{'next':>10}", color(WHITE, True))
    ]
    for timer in svc.timers(units):
        state, level = svc.timer_state(timer)
        name = fit(text(timer.get("unit")).removesuffix(".timer"), 24)
        last, nxt = _at(timer.get("last"), now), _at(timer.get("next"), now)
        out.append((f"{name} {last:>10}  {fit(state, 18)} {nxt:>10}", color(LEVELS[level])))
    if len(out) == 1:
        out.append(("no timers read" if not units else "no timers", color(BLUE)))
    running = svc.running(units)
    if running:
        out.append(("", 0))
        out.append(("RUNNING SERVICES", color(WHITE, True)))
        out += [(f"● {name.removesuffix('.service')}", color(CYAN)) for name in running]
    return out


def failed_lines(units: Json) -> list[Line]:
    out: list[Line] = [("FAILED UNITS", color(WHITE, True))]
    for where, unit, log in svc.failed(units):
        out.append((f"● {unit}  ({where})", color(RED, True)))
        out += [(f"    {line}", color(WHITE)) for line in log]
    if len(out) == 1:
        out.append(("none on the host or in your own services", color(GREEN)))
    return out


class ServicesPage:
    name = "services"
    label = "timers & services"
    title = " TIMERS & SERVICES "
    host_line = True
    help: tuple[tuple[str, str], ...] = ()

    def loaded(self, snapshot: Json) -> None:
        pass

    def subtitle(self, frame: Frame, height: int, width: int) -> str:
        return "what runs on a schedule and what failed"

    def footer(self, frame: Frame, after: Page, pages: Sequence[Page]) -> str:
        return f"Tab {after.label}   ? help"

    def handle(self, key: int, frame: Frame) -> bool:
        return False  # nothing to pick: the page only shows

    def draw(self, frame: Frame, height: int, width: int) -> None:
        s, snap = frame.screen, frame.snapshot
        now = time.time()
        units = sn.units(snap)
        y = 1
        news = [line for line in (_failed_sentence(units),) if line is not None] or [
            ("Nothing failed; every timer's last run ended well.", svc.GOOD)
        ]
        for sentence, level in news:
            s.put(y, 1, "● ", color(LEVELS[level], True))
            s.put(y, 3, clean(sentence), color(WHITE, True), width - 4)
            y += 1
        y += 1
        left, right = timer_lines(units, now), failed_lines(units)
        if width >= WIDE:
            half = width // 2
            put_lines(s, left, y, 1, half - 2, height)
            put_lines(s, right, y, half + 1, width - half - 2, height)
        else:
            y = put_lines(s, left, y, 1, width - 2, height) + 1
            put_lines(s, right, y, 1, width - 2, height)


def _failed_sentence(units: Json) -> tuple[str, int] | None:
    broken = svc.failed(units)
    bad = [t for t in svc.timers(units) if svc.timer_state(t)[1] == svc.PROBLEM]
    if not broken and not bad:
        return None
    parts = []
    if broken:
        parts.append(f"{len(broken)} failed unit{'s' if len(broken) != 1 else ''}")
    if bad:
        parts.append(f"{len(bad)} timer{'s' if len(bad) != 1 else ''} whose last run failed")
    return " and ".join(parts).capitalize() + ".", svc.PROBLEM
