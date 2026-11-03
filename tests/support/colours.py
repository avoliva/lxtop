"""WCAG contrast of the 256-colour palette, for the look tests."""

from __future__ import annotations

from lxtop.looks import theme

_BASE = [
    (0, 0, 0),
    (128, 0, 0),
    (0, 128, 0),
    (128, 128, 0),
    (0, 0, 128),
    (128, 0, 128),
    (0, 128, 128),
    (192, 192, 192),
    (128, 128, 128),
    (255, 0, 0),
    (0, 255, 0),
    (255, 255, 0),
    (0, 0, 255),
    (255, 0, 255),
    (0, 255, 255),
    (255, 255, 255),
]


def _rgb(n: int) -> tuple[int, int, int]:
    if n < 16:
        return _BASE[n]
    if n < 232:
        n -= 16
        steps = (0, 95, 135, 175, 215, 255)
        return steps[n // 36], steps[n // 6 % 6], steps[n % 6]
    grey = 8 + (n - 232) * 10
    return grey, grey, grey


def _luminance(n: int) -> float:
    def channel(v: int) -> float:
        x = v / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in _rgb(n))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: int, b: int) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def grounds(look: theme.Theme) -> list[int]:
    """What text sits on at 256 colours: the background, and the glass inside panels."""
    out = [look.background_rich if look.background >= 0 else 16]
    if look.panels and look.glass >= 0:
        out.append(look.glass)
    return out
