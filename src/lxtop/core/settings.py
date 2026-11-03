"""The viewer's settings, changed from inside the app: which look it starts in, how
often the look changes by itself, the effects level, the page it opens on and whether a look's
boot lines play at start.

Pure: the viewer reads and writes the file (`viewer/prefs.py`). Only the settings that differ
from the defaults are saved, so a default changed later (`[monitor] look_cycle_seconds` in
site.toml) still reaches anyone who never changed that setting.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection, Mapping
from dataclasses import dataclass

VERSION = 1
EFFECTS = ("light", "full", "off")  # the levels r steps through (looks.theme.FX_LEVELS)
# The choices for "change look every", in seconds; 0 keeps one look.
CYCLE_CHOICES = (0.0, 60.0, 120.0, 300.0, 600.0, 900.0, 1800.0, 3600.0)
MAX_CYCLE = 24 * 3600.0


@dataclass(frozen=True)
class Settings:
    look: str = "default"
    cycle_seconds: float = 300.0
    effects: str = "light"
    start_page: str = "network"
    boot: bool = True  # a look's boot lines at start (any key skips them anyway)


FIELDS = tuple(f.name for f in dataclasses.fields(Settings))


def merge(
    base: Settings, saved: Mapping[str, object], looks: Collection[str], pages: Collection[str]
) -> Settings:
    """`base` with each valid value from `saved` (a parsed settings file). A value of the
    wrong type, a look or page that no longer exists, or an unknown key is ignored, so an old
    or hand-edited file never stops the dashboard from starting."""
    out = base
    look = saved.get("look")
    if isinstance(look, str) and look in looks:
        out = dataclasses.replace(out, look=look)
    cycle = saved.get("cycle_seconds")
    if isinstance(cycle, int | float) and not isinstance(cycle, bool) and 0 <= cycle <= MAX_CYCLE:
        out = dataclasses.replace(out, cycle_seconds=float(cycle))
    effects = saved.get("effects")
    if isinstance(effects, str) and effects in EFFECTS:
        out = dataclasses.replace(out, effects=effects)
    page = saved.get("start_page")
    if isinstance(page, str) and page in pages:
        out = dataclasses.replace(out, start_page=page)
    boot = saved.get("boot")
    if isinstance(boot, bool):
        out = dataclasses.replace(out, boot=boot)
    return out


def diff(base: Settings, current: Settings) -> dict[str, object]:
    """What to save: the version and every setting of `current` that differs from `base`."""
    out: dict[str, object] = {"version": VERSION}
    for name in FIELDS:
        value = getattr(current, name)
        if value != getattr(base, name):
            out[name] = value
    return out


def step(choices: tuple[str, ...], value: str, by: int) -> str:
    """The choice `by` places after `value`, going round; the first when `value` is not one."""
    if value not in choices:
        return choices[0]
    return choices[(choices.index(value) + by) % len(choices)]


def step_cycle(seconds: float, by: int) -> float:
    """The next (`by` 1) or previous (-1) of CYCLE_CHOICES from `seconds`, going round; a
    value between two choices (`--cycle 45`) moves to the nearest one that way."""
    if seconds in CYCLE_CHOICES:
        index = CYCLE_CHOICES.index(seconds) + by
        return CYCLE_CHOICES[index % len(CYCLE_CHOICES)]
    if by > 0:
        return next((c for c in CYCLE_CHOICES if c > seconds), CYCLE_CHOICES[0])
    return next((c for c in reversed(CYCLE_CHOICES) if c < seconds), CYCLE_CHOICES[-1])


def cycle_label(seconds: float) -> str:
    """`off`, `45 s`, `5 min`, `1 h`."""
    if seconds <= 0:
        return "off"
    if seconds < 60 or seconds % 60:
        return f"{seconds:g} s"
    if seconds < 3600 or seconds % 3600:
        return f"{seconds / 60:g} min"
    return f"{seconds / 3600:g} h"
