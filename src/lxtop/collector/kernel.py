"""Out-of-memory kills from the kernel's log: when, which process, how big it was, and
whether the whole host ran out ("Out of memory: Killed process") or only a capped cgroup
("Memory cgroup out of memory: Killed process"). A host-wide kill can pick any process,
a VM's qemu as well as the job that caused it.

The collector runs `journalctl -k` as root every minute for the last week; nothing else.
"""

from __future__ import annotations

import json
import re
import subprocess

from lxtop.core.snapshot import Json

SINCE = "-7d"
MAX_KILLS = 20
_KILLED = re.compile(
    r"(?P<scope>Memory cgroup out of memory|Out of memory)[^:]*: Killed process (?P<pid>\d+) "
    r"\((?P<name>[^)]{0,64})\)(?:.*?anon-rss:(?P<anon>\d+)kB)?(?:.*?UID:(?P<uid>\d+))?"
)


def parse(lines: list[str]) -> list[Json]:
    """`journalctl -o json` lines -> kills, newest first. Lines that are not kills, or not
    JSON, are skipped."""
    kills: list[Json] = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        message = entry.get("MESSAGE")
        stamp = entry.get("__REALTIME_TIMESTAMP")
        if not isinstance(message, str) or not isinstance(stamp, str) or not stamp.isdigit():
            continue
        m = _KILLED.search(message)
        if not m:
            continue
        kills.append(
            {
                "at": int(stamp) / 1e6,
                "pid": int(m.group("pid")),
                "name": m.group("name"),
                "rss": int(m.group("anon")) * 1024 if m.group("anon") else 0,
                "uid": int(m.group("uid")) if m.group("uid") else None,
                "host_wide": m.group("scope") == "Out of memory",
            }
        )
    kills.sort(key=lambda k: -float(k["at"]))
    return kills[:MAX_KILLS]


def read() -> Json:
    try:
        done = subprocess.run(
            ["journalctl", "-k", "--since", SINCE, "-o", "json", "--no-pager",
             "-g", "Killed process"],
            capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL, check=False,
            start_new_session=True,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError) as exc:
        return {"error": str(exc)[:120]}
    # exit 1 with no output: nothing matched
    if done.returncode not in (0, 1):
        return {"error": (done.stderr.strip() or f"journalctl exit {done.returncode}")[:120]}
    return {"kills": parse(done.stdout.splitlines()), "since": SINCE}
