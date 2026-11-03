"""The host's alerts, loudest first."""

from __future__ import annotations

from lxtop.core import alerts
from tests.support.host_state import NOW, memory_record


def test_memory_pressure_is_an_alert_only_when_it_is_felt() -> None:
    felt = {"memory": memory_record(pressure={"memory": {"some10": 30.0, "full10": 0.0}})}
    assert alerts.alerts(felt, NOW)[0][1] == 1


def test_slowed_jobs_and_full_swap_are_alerts() -> None:
    record = memory_record(
        user={"current": 45 << 30, "high": 40 << 30, "pressure": 30.0},
        meminfo={"available": 1 << 30, "swap_total": 72 << 30, "swap_free": 2 << 30},
    )
    got = alerts.alerts({"memory": record}, NOW)
    assert [level for _, level in got] == [2, 1]
    assert got[0][0].startswith("Swap is 97% full") and "they keep running" in got[1][0]
