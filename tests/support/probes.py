"""A stand-in for one instance's probe process, for the collector's tests."""

from __future__ import annotations

from lxtop.collector import instances
from tests.support.clock import Clock


class FakeProbe(instances.InstanceProbe):
    def __init__(self, project: str, name: str, clock: Clock, log: list[str]) -> None:
        super().__init__(argv=[], clock=clock)
        self.label = f"{project}/{name}"
        self.log = log
        self.alive = False

    def start(self) -> None:
        self.started_at = self.clock()
        self.alive = True
        self.log.append(f"start {self.label}")

    def running(self) -> bool:
        return self.alive

    def stop(self) -> None:
        self.alive = False
        self.log.append(f"stop {self.label}")
