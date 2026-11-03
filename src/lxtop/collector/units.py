"""systemd on the host: the user's timers (stats's collectors and nightly jobs) with
how each one's last run ended, the user's running services, failed units of the system and of
the user's own systemd, and the last journal lines of each failed one.

The collector runs `systemctl` and `journalctl` as root every 30 s; `--user -M <user>@`
reaches the user's own systemd without logging in as them.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
from collections.abc import Callable

from lxtop.core.snapshot import Json

MAX_TIMERS = 30
MAX_FAILED = 12
LOG_LINES = 4
SHOW = (
    "Id,Description,Result,ActiveState,SubState,ExecMainStatus,ExecMainStartTimestamp,"
    "ExecMainExitTimestamp"
)
_UNIT = re.compile(r"[A-Za-z0-9@_.:\\-]{1,128}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")

Run = Callable[[list[str]], str | None]


def clean(value: object, limit: int = 160) -> str:
    return _CONTROL.sub(" ", value)[:limit] if isinstance(value, str) else ""


def run(argv: list[str], timeout: float = 20.0) -> str | None:
    """stdout of a command, or None when it could not run, failed or took too long.
    systemctl never asks for a password (polkit would wait for an answer that never comes),
    and a command that times out is killed with everything it started, so no helper is left
    holding the pipe."""
    if argv and argv[0] == "systemctl":
        argv = [argv[0], "--no-ask-password", *argv[1:]]
    try:
        child = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, start_new_session=True,
        )  # fmt: skip
    except OSError:
        return None
    try:
        out, _ = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            os.killpg(child.pid, signal.SIGKILL)
        child.communicate()
        return None
    return out if child.returncode == 0 else None


def _json_list(text: str | None) -> list[Json]:
    try:
        value = json.loads(text or "")
    except ValueError:
        return []
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _unix(value: str) -> float | None:
    """ "@1793603401" (systemctl --timestamp=unix) -> seconds; "" or "n/a" -> None."""
    value = value.strip().lstrip("@")
    try:
        return float(value) if value else None
    except ValueError:
        return None


def parse_show(text: str) -> list[Json]:
    """`systemctl show` of several units: blocks of KEY=value separated by blank lines."""
    units: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in [*text.splitlines(), ""]:
        if not line.strip():
            if current:
                units.append(current)
            current = {}
            continue
        key, _, value = line.partition("=")
        current[key] = value
    out = []
    for unit in units:
        status = unit.get("ExecMainStatus", "")
        out.append(
            {
                "unit": clean(unit.get("Id")),
                "description": clean(unit.get("Description")),
                "result": clean(unit.get("Result")),
                "active": clean(unit.get("ActiveState")),
                "sub": clean(unit.get("SubState")),
                "status": int(status) if status.isdigit() else None,
                "started": _unix(unit.get("ExecMainStartTimestamp", "")),
                "exited": _unix(unit.get("ExecMainExitTimestamp", "")),
            }
        )
    return out


def timers(user: str, run_: Run = run) -> list[Json]:
    """The user's timers: next and last run (seconds since the epoch) and how the service it
    starts last ended."""
    found = _json_list(run_(["systemctl", "--user", "-M", f"{user}@", "list-timers", "--all",
                             "-o", "json", "--no-pager"]))  # fmt: skip
    rows: list[Json] = []
    for item in found[:MAX_TIMERS]:
        unit, service = clean(item.get("unit")), clean(item.get("activates"))
        if not _UNIT.fullmatch(unit):
            continue
        rows.append(
            {
                "unit": unit,
                "service": service if _UNIT.fullmatch(service) else "",
                "next": _micro(item.get("next")),
                "last": _micro(item.get("last")),
            }
        )
    services = [str(r["service"]) for r in rows if r["service"]]
    if services:
        shown = run_(["systemctl", "--user", "-M", f"{user}@", "show", "--timestamp=unix",
                      "-p", SHOW, *services])  # fmt: skip
        by_unit = {s["unit"]: s for s in parse_show(shown or "")}
        for row in rows:
            row["service_state"] = by_unit.get(row["service"], {})
    return rows


def _micro(value: object) -> float | None:
    return value / 1e6 if isinstance(value, int) and value > 0 else None


def _units(argv: list[str], run_: Run) -> list[Json]:
    return [
        {"unit": clean(u.get("unit")), "description": clean(u.get("description")),
         "active": clean(u.get("active")), "sub": clean(u.get("sub"))}
        for u in _json_list(run_(argv))
        if _UNIT.fullmatch(clean(u.get("unit")))
    ]  # fmt: skip


def failed(user: str, uid: int, run_: Run = run) -> list[Json]:
    """Failed units of the system and of the user, each with its last journal lines."""
    system = _units(["systemctl", "list-units", "--failed", "-o", "json", "--no-pager"], run_)
    mine = _units(["systemctl", "--user", "-M", f"{user}@", "list-units", "--failed", "-o",
                   "json", "--no-pager"], run_)  # fmt: skip
    out = [{**u, "scope": "system"} for u in system] + [{**u, "scope": user} for u in mine]
    for item in out[:MAX_FAILED]:
        match = (f"_SYSTEMD_UNIT={item['unit']}" if item["scope"] == "system"
                 else f"_SYSTEMD_USER_UNIT={item['unit']}")  # fmt: skip
        argv = ["journalctl", match, "-n", str(LOG_LINES), "-o", "cat", "--no-pager"]
        if item["scope"] != "system":
            argv.insert(2, f"_UID={uid}")
        lines = (run_(argv) or "").splitlines()[-LOG_LINES:]
        item["log"] = [clean(line, 200) for line in lines]
    return out[:MAX_FAILED]


def running(user: str, run_: Run = run) -> list[Json]:
    """The user's services that are running now (long jobs and recorders)."""
    return _units(["systemctl", "--user", "-M", f"{user}@", "list-units", "--type=service",
                   "--state=running", "-o", "json", "--no-pager"], run_)  # fmt: skip


class Reader:
    def __init__(self, user: str, uid: int, run_: Run = run) -> None:
        self.user, self.uid, self.run = user, uid, run_

    def read(self) -> Json:
        return {
            "user": self.user,
            "timers": timers(self.user, self.run),
            "running": running(self.user, self.run),
            "failed": failed(self.user, self.uid, self.run),
        }
