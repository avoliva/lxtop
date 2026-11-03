"""What the memory & jobs page says: room for a job, pressure, the newest kill, VM rows,
job names."""

from __future__ import annotations

import pytest

from lxtop.core import memory as mem
from tests.support.host_state import GIB, NOW, kill, memory_record


def test_room_is_available_less_a_reserve_and_no_more_than_the_line_leaves() -> None:
    record = memory_record()  # 40 available, 14 used under a 40 GiB slow-down line
    assert mem.room(record, 32, 4.0) == (26 * GIB, 28.0)  # the line leaves 26, less than 36
    capped = memory_record(user={"current": 14 * GIB, "max": 20 * GIB, "high": 40 * GIB})
    assert mem.room(capped, 32, 0.0) == (6 * GIB, 32.0)  # a hard cap, if one were set
    open_ended = memory_record(user={"current": 14 * GIB, "max": None})
    assert mem.room(open_ended, 32, 40.0) == (36 * GIB, 0.0)
    assert mem.room({}, 32, 0.0) is None


@pytest.mark.parametrize(
    ("available", "level"), [(40 * GIB, mem.GOOD), (8 * GIB, mem.ATTENTION), (5 * GIB, mem.PROBLEM)]
)
def test_the_room_line_gets_louder_as_room_runs_out(available: int, level: int) -> None:
    record = memory_record(meminfo={"available": available}, user={})
    sentence, got = mem.room_line(record, 32, 0.0)
    assert got == level and sentence.startswith("Room for a job now:")
    assert "no line on the user's jobs" in sentence


def test_pressure_levels() -> None:
    calm = mem.pressure_line(memory_record())
    waiting = mem.pressure_line(memory_record(pressure={"memory": {"some10": 20.0, "full10": 1.0}}))
    stalled = mem.pressure_line(memory_record(pressure={"memory": {"some10": 60.0, "full10": 9.0}}))
    assert calm[1] == mem.GOOD and waiting[1] == mem.ATTENTION and stalled[1] == mem.PROBLEM
    assert "20%" in waiting[0] and "9%" in stalled[0]
    assert mem.pressure_line({})[1] == mem.QUIET


def test_a_kill_is_news_for_a_day_and_host_wide_is_a_problem() -> None:
    host_wide = memory_record(oom={"kills": [kill(NOW - 7200)]})
    capped = memory_record(oom={"kills": [kill(NOW - 600, host_wide=False, rss=33 * GIB)]})
    old = memory_record(oom={"kills": [kill(NOW - 2 * 86400)]})
    assert mem.kill_line(host_wide, NOW) == (
        "The host ran out of memory 2 h ago and killed stats (49.0 GB).",
        mem.PROBLEM,
    )
    assert mem.kill_line(capped, NOW) == (
        "A capped job was killed for memory 10 min ago: stats (33.0 GB).",
        mem.ATTENTION,
    )
    assert mem.kill_line(old, NOW) is None and mem.kill_line(memory_record(), NOW) is None


def test_vm_rows_pair_host_cost_with_the_guests_view() -> None:
    instances = [{"name": "app", "mem_used": 3 * GIB, "mem_total": 24 * GIB}]
    rows = mem.vm_rows(memory_record(), instances)
    assert rows == [("ci", 8 * GIB, 0.0, 0.0), ("app", 7 * GIB, 3 * GIB, 24 * GIB)]
    assert mem.host_rss(memory_record(), "app") == 7 * GIB
    assert mem.host_rss(memory_record(), "nope") is None


def test_a_session_job_is_named_by_its_command() -> None:
    build, session = mem.jobs(memory_record())
    assert mem.job_name(build) == "stats-kaggle-build4"
    assert mem.job_name(session) == "python3 search.py --trials 400"


def test_gpu_rows_none_means_unread() -> None:
    assert mem.gpu_rows(memory_record())[0]["owner"] == "llm"  # type: ignore[index]
    assert mem.gpu_rows({}) is None


def test_the_room_line_says_jobs_are_slowed_never_killed() -> None:
    sentence, _ = mem.room_line(memory_record(), 32, 0.0)
    assert sentence.endswith("before the user's jobs are slowed at 40.0 GB (never killed).")


def test_slowed_jobs_are_said_to_keep_running() -> None:
    calm = memory_record()
    slowed = memory_record(user={"current": 45 * GIB, "high": 40 * GIB, "pressure": 35.0})
    assert mem.slowed_line(calm) is None
    assert mem.slowed_line(slowed) == (
        "the user's jobs are slowed for memory 35% of the time (past the 40.0 GB line, swapping);"
        " they keep running.",
        mem.ATTENTION,
    )


def test_nearly_full_swap_is_a_problem() -> None:
    half = memory_record(meminfo={"swap_total": 72 * GIB, "swap_free": 36 * GIB})
    full = memory_record(meminfo={"swap_total": 72 * GIB, "swap_free": 4 * GIB})
    assert mem.swap_line(half) is None and mem.swap_line(memory_record(meminfo={})) is None
    assert mem.swap_line(full) == (
        "Swap is 94% full (68.0 GB of 72.0 GB): a big job could stall.",
        mem.PROBLEM,
    )
