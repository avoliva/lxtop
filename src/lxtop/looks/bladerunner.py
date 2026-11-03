"""Bladerunner: neon noir. Slanted rain at night, neon signs that buzz and drop out, lights of
flying cars crossing the upper sky, and a rare flash of lightning (see theme.py for the rules
every look keeps)."""

from __future__ import annotations

import random
from dataclasses import dataclass

from lxtop.looks.theme import (
    BACKGROUND,
    BLACK,
    BLUE_8,
    CYAN_8,
    FX_DIM,
    FX_GLASS,
    FX_GLASS_HEAD,
    FX_HEAD,
    FX_MID,
    GREEN_8,
    MAGENTA_8,
    RED_8,
    WHITE_8,
    YELLOW_8,
    Cell,
    Theme,
    Title,
)

SLANT = 0.4  # columns a streak drifts left per row it falls
STREAK = "\u2571"  # light diagonal; in the console font
SPLASH = "·"
AREA_PER_STREAK = 110  # cells of screen for each streak
SPLASH_LIFE = 0.25  # seconds
SPLASH_RATE = 1 / 1500  # new splashes per cell per second
FLASH_EVERY = (25.0, 70.0)  # seconds between lightning flashes
FLASH_LENGTH = 0.25
SIGN = "\u2501"  # heavy horizontal bar; in the console font
CAR_HEAD = "\u25cf"  # a lamp; in the console font
CAR_TAIL = "\u2500"
AREA_PER_SIGN = 1500  # cells of screen for each neon sign
SIGN_ZONE = 0.6  # signs hang in the upper part of the screen
SIGN_LEN = (4, 12)
SIGN_ON = (3.0, 11.0)  # seconds a sign burns steadily
SIGN_OFF = (0.3, 1.8)
SIGN_BUZZ = (0.25, 0.7)  # seconds of stutter before it dies or steadies
CAR_EVERY = (5.0, 14.0)  # seconds between flying cars
CAR_SPEED = (4.0, 9.0)  # columns per second: slow
CAR_ZONE = 0.35
CAR_MAX = 3


@dataclass
class _Streak:
    y: float  # row of the leading drop
    x: float  # column of the leading drop
    speed: float  # rows per second
    length: int


@dataclass
class _Splash:
    y: int
    x: int
    until: float


@dataclass
class _Sign:
    y: int
    x: int
    length: int
    mode: str  # "on", "buzz" or "off"
    until: float


@dataclass
class _Car:
    y: int
    x: float
    speed: float  # columns per second, negative: heading left


class Rain:
    """Short slanted streaks falling fast, a few splashes, and now and then a flash."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.h = 0
        self.w = 0
        self.streaks: list[_Streak] = []
        self.splashes: list[_Splash] = []
        self.last: float | None = None
        self.next_flash: float | None = None
        self.flash_until = -1.0
        self.signs: list[_Sign] = []
        self.cars: list[_Car] = []
        self.next_car: float | None = None

    def _streak(self, top: bool) -> _Streak:
        r = self.rng
        y = r.uniform(-self.h, -1) if top else r.uniform(-4, self.h)
        # Spawn across a band wider than the screen: the slant carries them left.
        x = r.uniform(0, self.w + self.h * SLANT)
        return _Streak(y, x, r.uniform(14.0, 26.0), r.randint(2, 4))

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        self.streaks = [self._streak(False) for _ in range(max(1, h * w // AREA_PER_STREAK))]
        self.splashes = []
        self.cars = []
        n = max(1, h * w // AREA_PER_SIGN) if h >= 4 and w >= 8 else 0
        self.signs = [self._sign() for _ in range(n)]

    def _sign(self) -> _Sign:
        r = self.rng
        length = min(r.randint(*SIGN_LEN), max(1, self.w))
        y = r.randrange(max(1, int(self.h * SIGN_ZONE)))
        x = r.randrange(max(1, self.w - length + 1))
        return _Sign(y, x, length, r.choice(("on", "off")), r.uniform(0, 4))

    def _step_signs(self, now: float, out: list[Cell]) -> None:
        r = self.rng
        for i, s in enumerate(self.signs):
            if now >= s.until:
                if s.mode == "on":
                    s.mode = "buzz" if r.random() < 0.6 else "off"
                    s.until = now + (
                        r.uniform(*SIGN_BUZZ) if s.mode == "buzz" else r.uniform(*SIGN_OFF)
                    )
                elif s.mode == "buzz":
                    s.mode = "on" if r.random() < 0.5 else "off"
                    s.until = now + (
                        r.uniform(*SIGN_ON) if s.mode == "on" else r.uniform(*SIGN_OFF)
                    )
                else:
                    s.mode, s.until = "on", now + r.uniform(*SIGN_ON)
                    if r.random() < 0.3:  # it comes back somewhere else
                        s = self.signs[i] = self._sign()
                        s.mode, s.until = "on", now + r.uniform(*SIGN_ON)
            if s.mode == "off" or (s.mode == "buzz" and r.random() < 0.5):
                continue
            tone = FX_HEAD if s.mode == "on" else FX_DIM
            out.extend((s.y, s.x + k, SIGN, tone) for k in range(s.length) if s.x + k < self.w)

    def _step_cars(self, now: float, dt: float, out: list[Cell]) -> None:
        r = self.rng
        h, w = self.h, self.w
        if self.next_car is None:
            self.next_car = now + r.uniform(0, CAR_EVERY[0])
        if now >= self.next_car:
            self.next_car = now + r.uniform(*CAR_EVERY)
            if len(self.cars) < CAR_MAX and h > 0 and w > 0:
                speed = r.uniform(*CAR_SPEED) * r.choice((-1, 1))
                self.cars.append(
                    _Car(
                        r.randrange(max(1, int(h * CAR_ZONE))),
                        -3.0 if speed > 0 else w + 3.0,
                        speed,
                    )
                )
        kept = []
        for c in self.cars:
            c.x += c.speed * dt
            if -4 <= c.x <= w + 4:
                kept.append(c)
                d = 1 if c.speed > 0 else -1
                for k, ch, tone in (
                    (0, CAR_HEAD, FX_HEAD),
                    (1, CAR_TAIL, FX_DIM),
                    (2, CAR_TAIL, FX_DIM),
                ):
                    x = int(c.x) - d * k
                    if 0 <= x < w and 0 <= c.y < h:
                        out.append((c.y, x, ch, tone))
        self.cars = kept

    def _step_flash(self, now: float) -> bool:
        if self.next_flash is None:
            self.next_flash = now + self.rng.uniform(*FLASH_EVERY)
        if now >= self.next_flash:
            self.flash_until = now + FLASH_LENGTH
            self.next_flash = now + self.rng.uniform(*FLASH_EVERY)
        return now < self.flash_until

    def frame(self, now: float) -> list[Cell]:
        dt = 0.0 if self.last is None else max(0.0, min(1.0, now - self.last))
        self.last = now
        flash = self._step_flash(now)
        out: list[Cell] = []
        h, w = self.h, self.w
        for i, s in enumerate(self.streaks):
            s.y += s.speed * dt
            s.x -= s.speed * dt * SLANT
            if s.y - s.length > h or s.x < -s.length:
                s = self.streaks[i] = self._streak(True)
            top = int(s.y)
            for k in range(s.length):
                y = top - k
                x = int(s.x + k * SLANT + 0.5)
                if 0 <= y < h and 0 <= x < w:
                    tone = FX_HEAD if k == 0 else FX_MID if flash else FX_DIM
                    out.append((y, x, STREAK, tone))
        self.splashes = [p for p in self.splashes if p.until > now]
        if h > 0 and self.rng.random() < min(1.0, h * w * SPLASH_RATE * dt):
            self.splashes.append(
                _Splash(self.rng.randrange(h), self.rng.randrange(w), now + SPLASH_LIFE)
            )
        out.extend((p.y, p.x, SPLASH, FX_DIM) for p in self.splashes)
        self._step_signs(now, out)
        self._step_cars(now, dt, out)
        return out


def make(console: bool, rng: random.Random) -> Rain:
    return Rain(rng)


THEME = Theme(
    name="bladerunner",
    colours={
        1: (87, CYAN_8),  # GREEN: neon cyan data
        2: (226, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (215, GREEN_8),  # CYAN: labels, amber (console slot 2 is redefined as amber)
        5: (207, MAGENTA_8),  # MAGENTA: hot magenta, upload
        6: (97, WHITE_8),  # BLUE: frames and quiet text, dusty violet
        7: (189, WHITE_8),  # WHITE: pale lavender
        # Rain stays far darker than any text.
        FX_DIM: (60, CYAN_8),
        FX_MID: (61, CYAN_8),
        FX_HEAD: (91, MAGENTA_8),
        BACKGROUND: (97, WHITE_8),
        FX_GLASS: (60, CYAN_8),
        FX_GLASS_HEAD: (91, MAGENTA_8),
    },
    background=BLACK,
    frame="╭╮╰╯─│",
    tick_ms=90,
    panels=True,
    glass=233,
    console_palette=(
        (BLUE_8, "0b0a1a"),  # glass: near black blue-violet
        (8, "2b3a5c"),  # dim text on the console: the rain, a dark steel blue
        (GREEN_8, "d98a3a"),  # amber
        (8 + GREEN_8, "ffb866"),
        (CYAN_8, "22d3e6"),  # neon cyan
        (8 + CYAN_8, "7af2ff"),
        (MAGENTA_8, "e0288f"),  # hot magenta
        (8 + MAGENTA_8, "ff63c0"),
        (WHITE_8, "9b8cc4"),  # dusty violet
        (8 + WHITE_8, "d8d0f5"),
    ),
    backdrop=make,
    glitch=True,
    noise=("░▒:·\u2571\u2572", "░▒:·\u2571\u2572"),
    meter_empty=("─", "─"),
    boot=(
        "night shift.",
        "rain on the glass.",
        "signs buzz over the street.",
        "servers on the street.",
    ),
    title=Title(left="░▒", right="▒░", prompt="", cursor="▌"),
    accent=4,
    label="neon noir: rain, buzzing signs, flying cars, amber haze",
)
