"""Out-of-memory kills from the kernel's journal: host-wide or capped, size, newest
first, and lines that are not kills."""

from __future__ import annotations

import json
import subprocess

import pytest

from lxtop.collector import kernel


def entry(message: str, at: float) -> str:
    return json.dumps({"MESSAGE": message, "__REALTIME_TIMESTAMP": str(int(at * 1e6))})


HOST = (
    "Out of memory: Killed process 2568855 (stats) total-vm:80630504kB, "
    "anon-rss:52386400kB, file-rss:2388kB, shmem-rss:0kB, UID:1000 pgtables:115"
)
CAPPED = (
    "Memory cgroup out of memory: Killed process 1845144 (stats) total-vm:47296048kB, "
    "anon-rss:33469844kB, file-rss:31760kB, shmem-rss:0kB, UID:1000 pgtables:961"
)


def test_kills_are_parsed_newest_first_with_their_scope_and_size() -> None:
    got = kernel.parse(
        [
            entry(HOST, 100.0),
            entry(CAPPED, 200.0),
            "not json",
            "[1]",
            entry("oom-kill:constraint=CONSTRAINT_NONE", 150.0),
        ]
    )
    assert [(k["at"], k["host_wide"], k["name"], k["pid"]) for k in got] == [
        (200.0, False, "stats", 1845144),
        (100.0, True, "stats", 2568855),
    ]
    assert got[1]["rss"] == 52386400 * 1024 and got[1]["uid"] == 1000


def test_an_older_kernel_line_without_sizes_is_still_a_kill() -> None:
    (got,) = kernel.parse([entry("Out of memory: Killed process 7 (python)", 1.0)])
    assert (got["rss"], got["uid"], got["host_wide"]) == (0, None, True)


def test_only_the_newest_kills_are_kept() -> None:
    lines = [entry(HOST, float(i)) for i in range(kernel.MAX_KILLS + 5)]
    got = kernel.parse(lines)
    assert len(got) == kernel.MAX_KILLS and got[0]["at"] == kernel.MAX_KILLS + 4


@pytest.mark.parametrize(("code", "out", "want"), [(1, "", []), (0, entry(HOST, 5.0), [5.0])])
def test_read_runs_journalctl_and_no_match_is_no_kills(
    monkeypatch: pytest.MonkeyPatch, code: int, out: str, want: list[float]
) -> None:
    seen: list[list[str]] = []

    def fake(argv: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(argv, code, out, "")

    monkeypatch.setattr("lxtop.collector.kernel.subprocess.run", fake)
    got = kernel.read()
    assert [k["at"] for k in got["kills"]] == want
    assert seen[0][:3] == ["journalctl", "-k", "--since"]


def test_a_journal_that_cannot_be_read_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(argv: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 2, "", "No journal files were found.")

    monkeypatch.setattr("lxtop.collector.kernel.subprocess.run", fake)
    assert kernel.read() == {"error": "No journal files were found."}
