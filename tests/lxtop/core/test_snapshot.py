"""The snapshot's contract: the collector writes exactly the keys `Snapshot` names, and
the viewer's readers never fail on a partial, old or hostile snapshot."""

from __future__ import annotations

import json
from typing import Any

import pytest

from lxtop.core import snapshot as sn
from tests.support.snapshot import collector, full_snapshot


def test_num_rejects_untrusted_shapes() -> None:
    assert sn.num(3) == 3.0
    assert sn.num(True) == 0.0
    assert sn.num("5") == 0.0
    assert sn.num(float("nan")) == 0.0
    assert sn.num(float("inf"), 1.0) == 1.0


def test_text_and_containers_fall_back_to_empty() -> None:
    assert sn.text("a") == "a" and sn.text(3) == "" and sn.text(None, "?") == "?"
    assert sn.as_dict({"a": 1}) == {"a": 1} and sn.as_dict([1]) == {}
    assert sn.as_list([1]) == [1] and sn.as_list({"a": 1}) == []


def test_the_collector_writes_exactly_the_snapshots_keys() -> None:
    built, clock = collector()
    clock.step()

    written = json.loads(json.dumps(built.tick()))

    assert set(written) == sn.KEYS
    assert written["version"] == sn.VERSION


def test_the_readers_find_each_part_of_a_real_snapshot() -> None:
    snap = full_snapshot()

    assert sn.host(snap)["hostname"]
    assert sn.instances(snap) and all(isinstance(i, dict) for i in sn.instances(snap))
    assert sn.uplinks(snap) and sn.interval(snap) > 0
    assert sn.series(snap, "host", "cpu")
    assert isinstance(sn.pings(snap), dict) and isinstance(sn.checks(snap), dict)


HOSTILE: list[Any] = [
    {},
    {"host": [], "instances": {}, "uplinks": [1, "eno1"], "errors": [None, "x"]},
    {"history": {"host": {"cpu": ["a", None, 0.5]}}, "interval": "fast", "time": True},
    {"checks": {"speed": 5}, "speeds": [3, {"bits": 1}], "trace": "x"},
]


@pytest.mark.parametrize("snap", HOSTILE)
def test_the_readers_never_fail_and_keep_their_types(snap: dict[str, Any]) -> None:
    assert isinstance(sn.host(snap), dict)
    assert all(isinstance(i, dict) for i in sn.instances(snap))
    assert all(isinstance(u, str) for u in sn.uplinks(snap))
    assert all(isinstance(e, str) for e in sn.errors(snap))
    assert all(isinstance(s, dict) for s in sn.speeds(snap))
    assert isinstance(sn.check(snap, "speed"), dict)
    assert isinstance(sn.trace(snap), dict)
    assert all(isinstance(v, float) for v in sn.series(snap, "host", "cpu"))
    assert sn.interval(snap) > 0
    assert sn.taken_at(snap, 7.0) == 7.0 or isinstance(snap.get("time"), int | float)
