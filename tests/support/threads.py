"""A thread double that records how it was made and never runs."""

from __future__ import annotations

from collections.abc import Callable


class RecordedThread:
    def __init__(self, target: Callable[[], None], daemon: bool, name: str) -> None:
        self.target, self.daemon, self.name = target, daemon, name
        self.started = False

    def start(self) -> None:
        self.started = True
