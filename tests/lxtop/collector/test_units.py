"""systemd on the host: the user's timers with how each service last ended, running
services, failed units with their last log lines, from a fake `systemctl`/`journalctl`."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from lxtop.collector import units

TIMERS = json.dumps(
    [
        {
            "next": 1793603700000000,
            "left": 1,
            "last": 1793603401600022,
            "passed": 1,
            "unit": "stats-oddsapi.timer",
            "activates": "stats-oddsapi.service",
        },
        {
            "next": 1793605681600082,
            "left": 1,
            "last": None,
            "passed": None,
            "unit": "stats-paper.timer",
            "activates": "stats-paper.service",
        },
        {"unit": "bad name;rm -rf", "activates": "x.service"},
    ]
)
SHOW = (
    "Id=stats-oddsapi.service\nDescription=odds\nResult=exit-code\nActiveState=failed\n"
    "SubState=failed\nExecMainStatus=2\nExecMainStartTimestamp=@1793603401\n"
    "ExecMainExitTimestamp=@1793603405\n\n"
    "Id=stats-paper.service\nDescription=paper\nResult=success\nActiveState=inactive\n"
    "SubState=dead\nExecMainStatus=0\nExecMainStartTimestamp=\nExecMainExitTimestamp=n/a\n"
)
FAILED_USER = json.dumps(
    [
        {
            "unit": "stats-oddsapi.service",
            "load": "loaded",
            "active": "failed",
            "sub": "failed",
            "description": "odds",
        }
    ]
)


def fake(calls: list[list[str]]) -> units.Run:
    def run(argv: list[str]) -> str | None:
        calls.append(argv)
        line = " ".join(argv)
        if "list-timers" in line:
            return TIMERS
        if " show " in line:
            return SHOW
        if "--failed" in line:
            return FAILED_USER if "--user" in line else "[]"
        if "--state=running" in line:
            return json.dumps(
                [
                    {
                        "unit": "stats-books.service",
                        "active": "active",
                        "sub": "running",
                        "description": "books",
                    }
                ]
            )
        if argv[0] == "journalctl":
            return "one\ntwo\nthree\nfour\nfive\n"
        return None

    return run


def test_timers_carry_their_services_last_result() -> None:
    calls: list[list[str]] = []
    got = units.timers("admin", fake(calls))
    assert [t["unit"] for t in got] == ["stats-oddsapi.timer", "stats-paper.timer"]
    odds = got[0]
    assert odds["last"] == 1793603401.600022 and odds["next"] == 1793603700.0
    assert odds["service_state"]["result"] == "exit-code"
    assert odds["service_state"]["status"] == 2 and odds["service_state"]["exited"] == 1793603405
    assert got[1]["last"] is None and got[1]["service_state"]["started"] is None
    show = next(c for c in calls if "show" in c)
    assert show[:5] == ["systemctl", "--user", "-M", "admin@", "show"]
    assert "x.service" not in show  # the bad timer's service is not asked about


def test_failed_units_have_their_last_log_lines_from_the_users_journal() -> None:
    calls: list[list[str]] = []
    (got,) = units.failed("admin", 1000, fake(calls))
    assert (got["unit"], got["scope"]) == ("stats-oddsapi.service", "admin")
    assert got["log"] == ["two", "three", "four", "five"]
    journal = next(c for c in calls if c[0] == "journalctl")
    assert journal[1:3] == ["_SYSTEMD_USER_UNIT=stats-oddsapi.service", "_UID=1000"]


def test_the_reader_reports_timers_running_and_failed() -> None:
    got = units.Reader("admin", 1000, fake([])).read()
    assert got["user"] == "admin" and [r["unit"] for r in got["running"]] == ["stats-books.service"]
    assert len(got["timers"]) == 2 and len(got["failed"]) == 1


def test_systemctl_that_cannot_answer_is_empty_lists() -> None:
    got = units.Reader("admin", 1000, lambda argv: None).read()
    assert (got["timers"], got["running"], got["failed"]) == ([], [], [])


def test_show_blocks_are_split_and_timestamps_read() -> None:
    (one,) = units.parse_show("Id=a.service\nResult=success\nExecMainStartTimestamp=@5\n")
    assert (one["unit"], one["result"], one["started"], one["status"]) == (
        "a.service",
        "success",
        5.0,
        None,
    )


def test_run_never_lets_systemctl_ask_for_a_password_and_kills_what_a_slow_command_started(
    tmp_path: Path,
) -> None:
    script = tmp_path / "systemctl"
    script.write_text('#!/bin/sh\necho "$@"\n')
    script.chmod(0o755)
    assert units.run([str(script), "list-units"]) == "list-units\n"  # a path is not "systemctl"
    slow = tmp_path / "slow"
    marker = tmp_path / "child-alive"
    slow.write_text(f"#!/bin/sh\n(sleep 5; touch {marker}) &\nsleep 30\n")
    slow.chmod(0o755)
    started = time.monotonic()
    assert units.run([str(slow)], timeout=0.5) is None
    assert time.monotonic() - started < 3  # did not wait for the background child's pipe
    time.sleep(5.5)  # bounded wait: the killed child would have touched the marker by now
    assert not marker.exists()


def test_systemctl_gets_no_ask_password(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    class Child:
        pid, returncode = 1, 0

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            return "[]", ""

    def popen(argv: list[str], **kw: object) -> Child:
        seen.append(argv)
        return Child()

    monkeypatch.setattr("lxtop.collector.units.subprocess.Popen", popen)
    units.run(["systemctl", "--user", "list-timers"])
    assert seen[0][:2] == ["systemctl", "--no-ask-password"]
