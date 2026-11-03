"""Tracker: green phosphor on black. A ping ring grows from a fixed point near the lower middle
and lights the blips it passes. The blips drift in toward that point over a 32 s scan, the
pings come faster as they close, each blip ends in a contact burst, then the screen goes quiet
and a new scan starts. Now and then a swarm of blips appears all at once. Faint range rings
and a slow sweep arm sit behind it (see theme.py for the rules every look keeps)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from lxtop.looks.theme import (
    BACKGROUND,
    BLACK,
    BLUE_8,
    FX_DIM,
    FX_GLASS,
    FX_GLASS_HEAD,
    FX_HEAD,
    FX_MID,
    GREEN_8,
    RED_8,
    WHITE_8,
    YELLOW_8,
    Cell,
    Theme,
    Title,
)

EPOCH = 32.0  # seconds per scan, then everything resets
SLOW = 1 / 3.0  # pings per second at the start of a scan
FAST = 1 / 0.75  # pings per second when the blips are about to arrive
BLIP_LIFE = 1.6  # seconds a blip stays lit after a ring passes it
ROW_SCALE = 0.5  # a cell is about twice as tall as wide: rings are ellipses in cells
SWARM_CHANCE = 0.17  # share of scans that bring a swarm
BURST = 0.9  # seconds a contact burst lasts
SWEEP_PERIOD = 14.0


def _line(vx: float, vy: float) -> str:
    """The character that lies along the screen direction (vx, vy), y pointing down."""
    ax, ay = abs(vx), abs(vy)
    if ay < 0.38 * ax:
        return "-"
    if ax < 0.38 * ay:
        return "|"
    return "\\" if vx * vy > 0 else "/"


@dataclass(frozen=True)
class Blip:
    theta: float  # bearing, 0 to pi: the upper half of the screen
    start: float  # share of the full range when it appears
    born: float  # seconds into the scan when it appears
    arrives: float  # seconds into the scan when it reaches the centre
    swarm: bool = False


@dataclass(frozen=True)
class Scan:
    blips: tuple[Blip, ...]
    swarm: bool
    peak: float  # when the last blip arrives: the pings are fastest then


class Tracker:
    """A ring of dots expanding from (cy, cx) and blips drifting in toward it."""

    def __init__(self, rng: random.Random) -> None:
        self.seed = rng.getrandbits(32)
        self.h = 0
        self.w = 0
        self.cy = 0
        self.cx = 0
        self.rmax = 4.0
        self._scans: dict[int, Scan] = {}

    def resize(self, h: int, w: int) -> None:
        self.h, self.w = h, w
        self.cy = int(h * 0.8)
        self.cx = w // 2
        self.rmax = max(4.0, w * 0.5)

    def scan(self, index: int) -> Scan:
        """Scan number `index`: two to four blips, and now and then a swarm that appears at once."""
        found = self._scans.get(index)
        if found is not None:
            return found
        r = random.Random((self.seed << 20) ^ (index & 0xFFFFF))
        blips = [
            Blip(
                r.uniform(0.05, 0.95) * math.pi,
                r.uniform(0.55, 0.95),
                0.0,
                r.uniform(0.55, 0.88) * EPOCH,
            )
            for _ in range(r.randint(2, 4))
        ]
        swarm = r.random() < SWARM_CHANCE
        if swarm:
            born = r.uniform(0.25, 0.45) * EPOCH
            base = r.uniform(0.2, 0.8) * math.pi
            for _ in range(r.randint(5, 8)):
                blips.append(
                    Blip(
                        min(max(base + r.uniform(-0.45, 0.45), 0.05), math.pi - 0.05),
                        r.uniform(0.8, 0.98),
                        born,
                        min(born + r.uniform(5.0, 8.0), 0.92 * EPOCH),
                        True,
                    )
                )
        scan = Scan(tuple(blips), swarm, max(b.arrives for b in blips))
        if len(self._scans) > 8:
            self._scans.clear()
        self._scans[index] = scan
        return scan

    def clock(self, now: float) -> tuple[int, float, float, float]:
        """(scan index, seconds into it, ping phase 0..1, pings per second)."""
        index = int(now // EPOCH)
        t = now - index * EPOCH
        peak = self.scan(index).peak
        gain = FAST - SLOW
        if t < peak:
            u = t / peak
            count = SLOW * t + gain * t * u * u / 3
            rate = SLOW + gain * u * u
        else:
            count = SLOW * peak + gain * peak / 3 + SLOW * (t - peak)
            rate = SLOW
        return index, t, count % 1.0, rate

    def where(self, blip: Blip, t: float) -> tuple[float, float, float] | None:
        """(row offset up, column offset, share of range left) of a blip at `t`, or None."""
        if not blip.born <= t < blip.arrives:
            return None
        left = 1.0 - (t - blip.born) / (blip.arrives - blip.born)
        th = blip.theta + 0.25 * (1 - left)
        ymax = max(1.0, 0.92 * self.cy)
        reach = min(self.rmax, ymax / (ROW_SCALE * max(math.sin(th), 0.15)))
        r = blip.start * left * reach
        return r * ROW_SCALE * math.sin(th), r * math.cos(th), left * blip.start

    def _put(
        self, out: dict[tuple[int, int], tuple[str, int]], y: int, x: int, c: str, t: int
    ) -> None:
        if 0 <= y < self.h and 0 <= x < self.w:
            out[(y, x)] = (c, t)

    def _rings(self, out: dict[tuple[int, int], tuple[str, int]]) -> None:
        """Faint range rings, a dot every few cells."""
        for share in (0.34, 0.67):
            a = share * self.rmax
            n = max(8, int(2 * math.pi * a / 9))
            for i in range(n):
                th = 2 * math.pi * i / n
                self._put(
                    out,
                    self.cy - round(a * ROW_SCALE * math.sin(th)),
                    self.cx + round(a * math.cos(th)),
                    ":",
                    FX_DIM,
                )
        self._put(out, self.cy, self.cx, "+", FX_MID)

    def _sweep(self, out: dict[tuple[int, int], tuple[str, int]], now: float) -> None:
        """A slow arm swinging across the upper half, a dotted line with a short bright head."""
        phi = math.pi * (0.5 + 0.5 * math.sin(2 * math.pi * now / SWEEP_PERIOD))
        step = max(2.0, self.rmax / 24)
        for k in range(1, int(self.rmax * 0.9 / step) + 1):
            r = k * step
            self._put(
                out,
                self.cy - round(r * ROW_SCALE * math.sin(phi)),
                self.cx + round(r * math.cos(phi)),
                ".",
                FX_DIM,
            )
        r = self.rmax * 0.9
        self._put(
            out,
            self.cy - round(r * ROW_SCALE * math.sin(phi)),
            self.cx + round(r * math.cos(phi)),
            _line(math.cos(phi), -ROW_SCALE * math.sin(phi)),
            FX_MID,
        )

    def _ping(self, out: dict[tuple[int, int], tuple[str, int]], p: float) -> None:
        a = p * self.rmax
        if a < 1.0 or p >= 0.95:
            return
        b = a * ROW_SCALE
        n = max(8, int(2 * math.pi * math.sqrt((a * a + b * b) / 2) / 2.2))
        tone = FX_HEAD if p < 0.25 else FX_MID if p < 0.6 else FX_DIM
        for i in range(n):
            th = 2 * math.pi * i / n
            char = _line(-math.sin(th), -math.cos(th))
            y = self.cy - round(b * math.sin(th))
            self._put(out, y, self.cx + round(a * math.cos(th)), char, tone)

    def _blips(
        self,
        out: dict[tuple[int, int], tuple[str, int]],
        scan: Scan,
        t: float,
        p: float,
        rate: float,
    ) -> None:
        for blip in scan.blips:
            spot = self.where(blip, t)
            if spot is None:
                continue
            up, across, left = spot
            y, x = self.cy - round(up), self.cx + round(across)
            q = math.hypot(across, up / ROW_SCALE) / self.rmax  # share of the ring's reach
            age = ((p - q) % 1.0) / rate  # seconds since a ring last passed it
            appearing = blip.swarm and t - blip.born < 0.6  # a swarm shows itself at once
            if appearing:
                age = min(age, 0.0)
            if age >= BLIP_LIFE:
                continue
            char, tone = (
                ("@", FX_HEAD) if age < 0.4 else ("o", FX_MID) if age < 0.9 else (".", FX_DIM)
            )
            if left < 0.2:  # lock-on: the last stretch is bracketed and never goes dark
                self._put(out, y, x - 2, "[", FX_MID)
                self._put(out, y, x + 2, "]", FX_MID)
                if age >= 0.4:
                    char, tone = "o", FX_MID
            self._put(out, y, x, char, tone)

    def _burst(self, out: dict[tuple[int, int], tuple[str, int]], scan: Scan, t: float) -> None:
        """Where a blip reaches the centre, a small ring of sparks."""
        for blip in scan.blips:
            dt = t - blip.arrives
            if not 0 <= dt < BURST:
                continue
            k = 1 + int(dt * 5)
            char, tone = ("*", FX_HEAD) if dt < 0.45 else ("+", FX_MID)
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
                self._put(out, self.cy + dy * (k // 2 + 1), self.cx + dx * (k + 1), char, tone)

    def frame(self, now: float) -> list[Cell]:
        if self.h < 1 or self.w < 1:
            return []
        out: dict[tuple[int, int], tuple[str, int]] = {}
        index, t, p, rate = self.clock(now)
        scan = self.scan(index)
        self._rings(out)
        self._sweep(out, now)
        self._ping(out, p)
        self._blips(out, scan, t, p, rate)
        self._burst(out, scan, t)
        return [(y, x, c, tone) for (y, x), (c, tone) in out.items()]


def make(console: bool, rng: random.Random) -> Tracker:
    return Tracker(rng)


THEME = Theme(
    name="tracker",
    colours={
        1: (82, GREEN_8),  # GREEN: phosphor, a yellowish green
        2: (226, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (156, GREEN_8),  # CYAN: labels, pale phosphor
        5: (114, WHITE_8),  # MAGENTA: upload, a softer green
        6: (65, GREEN_8),  # BLUE: frames and quiet text, a dusty green
        7: (193, WHITE_8),  # WHITE: pale green-white
        FX_DIM: (22, GREEN_8),
        FX_MID: (28, GREEN_8),
        FX_HEAD: (29, GREEN_8),
        BACKGROUND: (65, GREEN_8),
        FX_GLASS: (22, GREEN_8),
        FX_GLASS_HEAD: (23, GREEN_8),
    },
    background=BLACK,
    frame="┌┐└┘┄┆",
    tick_ms=100,
    panels=True,
    glass=233,
    console_palette=(
        (BLUE_8, "07120a"),  # glass: green-black under the panels
        (8, "0b4a1a"),  # effects: dark phosphor
        (GREEN_8, "7ae030"),
        (8 + GREEN_8, "a6ff5a"),
        (WHITE_8, "c8f0c0"),
        (8 + WHITE_8, "e8ffe0"),
    ),
    backdrop=make,
    glitch=True,
    noise=("·:;.,'`", ".:;,'`-"),
    boot=("sweep armed.", "range thirty metres.", "no contacts yet.", "gain rises as they close."),
    title=Title(left="((●", right="●))", prompt="> ", cursor="_"),
    accent=1,
    meter_empty=("·", "·"),
    label="green phosphor, pings quicken as blips close in",
)
