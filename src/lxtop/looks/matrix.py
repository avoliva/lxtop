"""Matrix: green on black, digital rain, pages that decode from noise (the model look
for the other looks; see theme.py for the rules every look keeps)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

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

# Half-width katakana are one cell wide; the console font has none of them, so the console
# rains letters and symbols it does have. No digits: rain beside a table must not read as data.
KATAKANA = "ｦｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ"
CONSOLE_RAIN = "ABCDEFHKMXZ:=*+<>|"


def rain_chars(console: bool) -> str:
    return CONSOLE_RAIN if console else KATAKANA


# The far layer is quieter in shape too: thin strokes and dots instead of full glyphs.
KATAKANA_FAR = "ｲｼｿﾄﾉﾚﾝﾑﾘ"
CONSOLE_FAR = ":.|+=-"

FLASH_EVERY = (6.0, 14.0)  # seconds between glitch-column flashes (one at a time)
FLASH_SECONDS = 0.35
FROZEN_EVERY = (9.0, 20.0)  # seconds between a trail that freezes, then dissolves
FROZEN_SECONDS = (0.6, 1.2)
DISSOLVE_SECONDS = 1.0


@dataclass
class _Drop:
    head: float  # row of the bright head; negative means not on screen yet
    speed: float  # rows per second
    length: int
    chars: list[str] = field(default_factory=list)
    freeze_at: float | None = None  # when the trail stopped falling
    freeze_for: float = 0.0  # how long it stays still before it dissolves
    fade: list[float] = field(default_factory=list)  # per row: how far into the dissolve it goes


class Rain:
    """Two layers of falling columns. The near layer is quick and bright, about a third of the
    columns at once; behind it a slower, dimmer one of thin strokes gives depth. Now and then a
    glitch column flashes bright top to bottom, and a near trail freezes for a moment, then
    dissolves cell by cell. At most one of each happens at a time."""

    def __init__(
        self, chars: str, rng: random.Random | None = None, far_chars: str | None = None
    ) -> None:
        self.chars = chars
        self.far_chars = far_chars or chars
        self.rng = rng or random.Random()
        self.h = 0
        self.w = 0
        self.drops: list[_Drop] = []
        self.far: list[_Drop | None] = []
        self.last: float | None = None
        self.flash: tuple[int, float] | None = None  # column, start time
        self.next_flash: float | None = None
        self.frozen: int | None = None  # column of the frozen trail
        self.next_frozen: float | None = None

    def _drop(self, h: int, start: bool) -> _Drop:
        r = self.rng
        length = r.randint(4, max(5, h // 3))
        head = r.uniform(-h * 5, h) if start else r.uniform(-h * 5, -1)
        return _Drop(
            head, r.uniform(8.0, 22.0), length, [r.choice(self.chars) for _ in range(h + length)]
        )

    def _far_drop(self, h: int, start: bool) -> _Drop:
        r = self.rng
        length = r.randint(3, max(4, h // 4))
        head = r.uniform(-h * 5, h) if start else r.uniform(-h * 6, -1)
        chars = [r.choice(self.far_chars) for _ in range(h + length)]
        return _Drop(head, r.uniform(2.5, 7.0), length, chars)

    def resize(self, h: int, w: int) -> None:
        if (h, w) == (self.h, self.w):
            return
        self.h, self.w = h, w
        self.drops = [self._drop(h, True) for _ in range(w)]
        self.far = [self._far_drop(h, True) if self.rng.random() < 0.4 else None for _ in range(w)]
        self.flash = self.frozen = None

    def _events(self, now: float) -> None:
        r = self.rng
        if self.next_flash is None:
            self.next_flash = now + r.uniform(*FLASH_EVERY) / 2
        if self.next_frozen is None:
            self.next_frozen = now + r.uniform(*FROZEN_EVERY) / 2
        if self.flash and now - self.flash[1] > FLASH_SECONDS:
            self.flash = None
        if self.flash is None and now >= self.next_flash and self.w:
            self.flash = (r.randrange(self.w), now)
            self.next_flash = now + r.uniform(*FLASH_EVERY)
        if self.frozen is None and now >= self.next_frozen and self.w:
            x = r.randrange(self.w)
            drop = self.drops[x]
            if 0 < drop.head < self.h:  # only a trail that is on screen can freeze
                drop.freeze_at = now
                drop.freeze_for = r.uniform(*FROZEN_SECONDS)
                drop.fade = [r.random() for _ in range(drop.length + 1)]
                self.frozen = x
                self.next_frozen = now + r.uniform(*FROZEN_EVERY)
            else:
                self.next_frozen = now + 0.5

    def _trail(self, out: list[Cell], x: int, drop: _Drop, tones: tuple[int, int, int]) -> None:
        head_tone, mid_tone, dim_tone = tones
        top = int(drop.head)
        for y in range(max(0, top - drop.length + 1), min(self.h, top + 1)):
            age = top - y
            tone = head_tone if age == 0 else mid_tone if age < drop.length // 3 else dim_tone
            out.append((y, x, drop.chars[y % len(drop.chars)], tone))

    def frame(self, now: float) -> list[Cell]:
        """(row, column, character, tone) for every rain cell on screen at `now`."""
        dt = 0.0 if self.last is None else max(0.0, min(1.0, now - self.last))
        self.last = now
        r = self.rng
        self._events(now)
        out: list[Cell] = []
        for x, drop in enumerate(self.drops):
            if drop.freeze_at is None:
                drop.head += drop.speed * dt
            elif now - drop.freeze_at > drop.freeze_for + DISSOLVE_SECONDS:
                drop.freeze_at = None  # gone: the column starts again from above
                self.frozen = None
                drop.head = -float(drop.length)
                drop.speed = r.uniform(8.0, 22.0)
            if drop.head - drop.length > self.h:
                self.drops[x] = drop = self._drop(self.h, False)
            if r.random() < 0.08:  # a character in the trail flickers to another
                drop.chars[r.randrange(len(drop.chars))] = r.choice(self.chars)
            if drop.freeze_at is None:
                self._trail(out, x, drop, (FX_HEAD, FX_MID, FX_DIM))
            else:
                self._dissolve(out, x, drop, now)
        near = {(y, x) for y, x, _, _ in out}
        for x, far in enumerate(self.far):  # behind: slow, dim, only the quietest tone
            if far is None:
                continue
            far.head += far.speed * dt
            if far.head - far.length > self.h:
                self.far[x] = far = self._far_drop(self.h, False)
            behind: list[Cell] = []
            self._trail(behind, x, far, (FX_DIM, FX_DIM, FX_DIM))
            out += [c for c in behind if (c[0], c[1]) not in near]
        if self.flash:
            self._glitch(out, now)
        return out

    def _dissolve(self, out: list[Cell], x: int, drop: _Drop, now: float) -> None:
        """A frozen trail: still for a moment, then cells drop out, the tail first."""
        assert drop.freeze_at is not None
        gone = (now - drop.freeze_at - drop.freeze_for) / DISSOLVE_SECONDS
        top = int(drop.head)
        for y in range(max(0, top - drop.length + 1), min(self.h, top + 1)):
            age = top - y
            # older cells go earlier: their threshold is lowered by how far down the tail they are
            if gone > 0 and drop.fade[age] * 0.5 + (1 - age / max(1, drop.length)) * 0.5 < gone:
                continue
            tone = FX_HEAD if age == 0 else FX_MID if age < drop.length // 3 else FX_DIM
            out.append((y, x, drop.chars[y % len(drop.chars)], tone))

    def _glitch(self, out: list[Cell], now: float) -> None:
        """One column lights bright in a band that sweeps down it, its characters scrambling."""
        assert self.flash is not None
        x, start = self.flash
        t = (now - start) / FLASH_SECONDS
        band = max(2, self.h // 3)
        front = int(t * (self.h + band))
        out[:] = [c for c in out if c[1] != x]
        for y in range(max(0, front - band), min(self.h, front + 1)):
            out.append((y, x, self.rng.choice(self.chars), FX_HEAD if y > front - 3 else FX_MID))


def rain(console: bool, rng: random.Random) -> Rain:
    return Rain(rain_chars(console), rng, CONSOLE_FAR if console else KATAKANA_FAR)


# Shades of green for everything that was a colour of its own (series, upload against
# download), from bright to dark, so lines on one chart still tell apart.
THEME = Theme(
    name="matrix",
    colours={
        1: (46, GREEN_8),  # GREEN: bright phosphor
        2: (226, YELLOW_8),  # YELLOW: still a warning
        3: (196, RED_8),  # RED: still an alarm
        4: (120, GREEN_8),  # CYAN: labels, pale green
        5: (194, WHITE_8),  # MAGENTA: upload, near white so it differs from download
        6: (35, GREEN_8),  # BLUE: frames and quiet text, a green brighter than the rain
        7: (194, WHITE_8),  # WHITE: mint
        # The rain stays darker than any text: it is the background, not the news.
        FX_DIM: (22, GREEN_8),
        FX_MID: (22, GREEN_8),
        FX_HEAD: (28, GREEN_8),
        BACKGROUND: (34, GREEN_8),
        FX_GLASS: (22, GREEN_8),
        FX_GLASS_HEAD: (22, GREEN_8),
    },
    background=BLACK,
    frame="╔╗╚╝═║",
    tick_ms=100,
    panels=True,
    glass=234,
    console_palette=(
        (BLUE_8, "143018"),  # glass: a dark green-grey under the panels
        (8, "0c5a1e"),  # the console draws dim text in slot 8: rain behind glass, dark green
        (GREEN_8, "17b83c"),
        (8 + GREEN_8, "52ff78"),  # bold green
        (WHITE_8, "c8ffd4"),  # mint
        (8 + WHITE_8, "f0fff2"),  # bold mint
    ),
    backdrop=rain,
    thin=True,
    see_through=True,
    glitch=True,
    noise=(KATAKANA, CONSOLE_RAIN),
    meter_empty=("·", "·"),  # the unfilled part of a meter is a quiet dot, like a far raindrop
    boot=("tracing the feed...", "decoding the rain.", "all hosts in sight."),
    title=Title(left="█▒░", right="░▒█", prompt="> ", cursor="█"),
    accent=1,
    label="green rain, pages decode from noise",
)
