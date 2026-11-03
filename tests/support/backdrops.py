"""Build a look's backdrop at a size, the way every look test starts."""

from __future__ import annotations

import random

from lxtop.looks.theme import Theme


def backdrop_of[T](
    theme: Theme, kind: type[T], seed: int = 1, h: int = 60, w: int = 213, console: bool = False
) -> T:
    factory = theme.backdrop
    assert factory is not None
    backdrop = factory(console, random.Random(seed))
    assert isinstance(backdrop, kind)
    backdrop.resize(h, w)
    return backdrop
