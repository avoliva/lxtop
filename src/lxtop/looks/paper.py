"""Paper: a light look. Dark ink on cream newsprint, navy and forest green for accents, a
ruled double-line frame and a typewriter title. Calm: no glitch, and the only effect is a few
ink blots that spread slowly as faint speckled rings and fade (see matrix.py for the model
look and theme.py for the rules every look keeps).

Readability (256 colours, against the cream and the glass): text 4.5:1 or better, the warning
(dark orange, 130) 4.6 / 3.7 and the alarm (strong red, 160) 5.3 / 4.3, both well over 3:1."""

from __future__ import annotations

import math
import random

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
    RED_8,
    WHITE_8,
    YELLOW_8,
    Backdrop,
    Cell,
    Theme,
    Title,
)

CREAM_256 = 230

BLOT_SECONDS = 28.0  # one blot's life: it spreads, then fades out
BLOTS = 3  # at most this many are on the page at once
SPECKS = 44  # cells in one blot's ring
CHARS = ".'`,:"  # ASCII only: these exist on the console too


class InkBlots:
    """A few ink blots, one starting every BLOT_SECONDS / BLOTS: each is a ring of faint
    specks that spreads from a spot and fades, young specks a little darker than old ones.
    A pure function of the time and the seed, placed by fractions of the screen so a resize
    just moves them; about 1% of the cells at most."""

    def __init__(self, console: bool, rng: random.Random) -> None:
        self.seed = rng.getrandbits(32)
        self.offsets = [rng.random() * BLOT_SECONDS for _ in range(BLOTS)]
        self.h = self.w = 1

    def resize(self, h: int, w: int) -> None:
        self.h, self.w = max(1, h), max(1, w)

    def blot(self, n: int, now: float) -> list[Cell]:
        t = now + self.offsets[n]
        life, phase = divmod(t / BLOT_SECONDS, 1.0)
        if phase > 0.92:
            return []  # gone for a moment before the next one lands
        rnd = random.Random(self.seed * 7919 + n * 104729 + int(life))
        cy, cx = rnd.random() * self.h, rnd.random() * self.w
        reach = max(3.0, min(self.w / 2.5, self.h * 1.6))
        radius = reach * math.sqrt(phase / 0.92)
        tone = FX_HEAD if phase < 0.25 else FX_MID if phase < 0.6 else FX_DIM
        cells: list[Cell] = []
        for i in range(SPECKS):
            angle = (i + rnd.random()) * math.tau / SPECKS
            r = radius * (0.8 + 0.2 * rnd.random())
            y = int(cy + r * math.sin(angle) * 0.5)  # cells are about twice as tall as wide
            x = int(cx + r * math.cos(angle))
            char = CHARS[rnd.randrange(len(CHARS))]
            if 0 <= y < self.h and 0 <= x < self.w:
                cells.append((y, x, char, tone))
        return cells

    def frame(self, now: float) -> list[Cell]:
        seen: dict[tuple[int, int], Cell] = {}
        for n in range(BLOTS):
            for cell in self.blot(n, now):
                seen.setdefault((cell[0], cell[1]), cell)
        return list(seen.values())


def blots(console: bool, rng: random.Random) -> Backdrop:
    return InkBlots(console, rng)


THEME = Theme(
    name="paper",
    colours={
        1: (22, 2),  # GREEN: data, forest green (console slot 2, redefined)
        2: (130, YELLOW_8),  # YELLOW: warning, dark orange, 4.6 / 3.7 on the paper / glass
        3: (160, RED_8),  # RED: alarm, strong red, 5.3 / 4.3
        4: (240, 6),  # CYAN: labels, dark grey (console slot 6, redefined)
        5: (18, 5),  # MAGENTA: upload, navy (console slot 5, redefined)
        6: (242, 6),  # BLUE: frames and quiet text, mid grey
        7: (234, BLACK),  # WHITE: plain text, near black ink
        BACKGROUND: (234, BLACK),
        # Blots: pencil greys, all well below the quietest text (1.5 to 2.4 against the sheet)
        FX_DIM: (252, CYAN_8),
        FX_MID: (250, CYAN_8),
        FX_HEAD: (248, CYAN_8),
        FX_GLASS: (248, CYAN_8),  # a little darker where the panel's glass is
        FX_GLASS_HEAD: (246, CYAN_8),
    },
    background=WHITE_8,
    background_rich=CREAM_256,
    frame="╔╗╚╝═║",  # a ruled double line
    tick_ms=250,
    panels=True,
    glass=254,  # a slightly darker sheet under the panels
    console_palette=(
        (BLUE_8, "ebe3c8"),  # glass: darker paper
        (8, "5a5a5a"),  # dim text: grey ink
        (2, "1f5a2e"),  # forest green
        (5, "1a2a6c"),  # navy
        (6, "4d4d4d"),  # dark grey
        (WHITE_8, "f7f0d8"),  # cream paper
        (8 + WHITE_8, "f7f0d8"),
        (10, "1f5a2e"),  # bold green stays dark
        (13, "1a2a6c"),  # bold magenta stays navy
        (14, "4d4d4d"),  # bold cyan stays grey
    ),
    backdrop=blots,
    glitch=False,
    noise=("#%&=+", "#%&=+"),
    meter_empty=("·", "·"),  # leader dots
    boot=("feeding paper to the platen.", "inking the ribbon.", "setting the headlines."),
    title=Title(left="══╡ ", right=" ╞══", prompt="the daily load", cursor="_"),
    accent=5,
    label="typewriter ink on cream newsprint, with slow ink blots",
)
