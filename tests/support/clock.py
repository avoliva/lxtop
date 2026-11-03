"""A settable clock for tests that take a `clock=` callable."""

from __future__ import annotations


class Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now
