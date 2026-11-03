"""One probe per running LXD instance: `probe.py` inside it through a long-lived `lxc exec`, its
samples read line by line. Everything from inside an instance is untrusted: lines are
size-capped, must be JSON objects, and lists are cut short before they reach the snapshot."""

from __future__ import annotations

import contextlib
import json
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import IO

from lxtop.collector import probe
from lxtop.core import snapshot as sn
from lxtop.core.snapshot import Json

MAX_LINE = 1 << 20


RESTART_AFTER = 15.0


def read_line(stream: IO[bytes], limit: int = MAX_LINE) -> bytes | None:
    """One line of at most `limit` bytes. A longer line is read to its end and dropped (b"")."""
    line = stream.readline(limit)
    if not line:
        return None
    if line.endswith(b"\n"):
        return line
    while True:
        more = stream.readline(limit)
        if not more or more.endswith(b"\n"):
            return b""


def decode(line: bytes) -> Json | None:
    try:
        value = json.loads(line)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def trim(sample: Json) -> Json:
    """Cut lists from a guest to the sizes the viewer can show."""
    out = dict(sample)
    for key, size in (("procs", probe.TOP_PROCS), ("net", 64), ("fs", 32), ("temps", 16)):
        out[key] = sn.as_list(out.get(key))[:size]
    docker = sn.as_dict(out.get("docker"))
    if docker:
        containers = []
        for item in sn.as_list(docker.get("containers"))[: probe.MAX_CONTAINERS]:
            item = dict(sn.as_dict(item))
            for key, size in (("procs", probe.MAX_SANDBOX_PROCS), ("mounts", probe.MAX_MOUNTS)):
                if key in item:
                    item[key] = sn.as_list(item.get(key))[:size]
            containers.append(item)
        out["docker"] = {"error": docker.get("error"), "containers": containers}
    return out


@dataclass
class InstanceProbe:
    """`probe.py` running inside one instance through a long-lived `lxc exec`."""

    argv: list[str]
    clock: Callable[[], float] = time.monotonic
    # Program text sent on stdin (then closed), so it stays out of argv, `ps` and sudo's log.
    source: str | None = None
    latest: Json | None = None
    latest_at: float = 0.0
    error: str = ""
    started_at: float = 0.0
    process: subprocess.Popen[bytes] | None = field(default=None, repr=False)
    # Checks and cuts each line before it is kept (`trim` for probe.py's samples).
    shape: Callable[[Json], Json] = field(default=trim, repr=False)

    def start(self) -> None:
        self.started_at = self.clock()
        try:
            self.process = subprocess.Popen(
                self.argv,
                stdin=subprocess.DEVNULL if self.source is None else subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if self.source is not None and self.process.stdin is not None:
                with contextlib.suppress(BrokenPipeError):
                    self.process.stdin.write(self.source.encode())
                self.process.stdin.close()
        except OSError as exc:
            self.error = str(exc)
            self.process = None
            return
        threading.Thread(target=self._read_out, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def _read_out(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        stream = self.process.stdout
        with stream:  # closed at EOF, so a stopped probe leaves no open pipe
            while (line := read_line(stream)) is not None:
                sample = decode(line) if line else None
                if sample is not None:
                    self.latest = self.shape(sample)
                    self.latest_at = self.clock()
                    self.error = ""

    def _read_err(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        stream = self.process.stderr
        with stream:
            while (line := read_line(stream, 4096)) is not None:
                if line.strip():
                    self.error = line.decode("utf-8", "replace").strip()[:300]

    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def status(self, interval: float) -> str:
        now = self.clock()
        if self.latest is not None and now - self.latest_at <= 3 * interval:
            return "ok"
        if not self.running():
            return f"error: {self.error or 'probe exited'}"
        if self.latest is None:
            return "starting" if now - self.started_at < 10 * interval else "error: no data"
        return "stale"


# Runs the program text it reads on stdin; `__name__` stays "__main__", so probe.main() runs.
BOOT = "import sys; exec(compile(sys.stdin.read(), 'lxtop-probe', 'exec'))"


def exec_argv(lxc: str, project: str, name: str, interval: float, sudo: bool) -> list[str]:
    """The `lxc exec` that runs the probe (or deploys.py) in an instance (its source goes on
    stdin). As non-root (testing), `sudo -n`: it needs a sudo timestamp from `sudo -v` first,
    since nothing on the host runs lxc without a password."""
    argv = [lxc, "--project", project, "exec", name, "--", "python3", "-I", "-c", BOOT]
    argv += ["--interval", str(interval)]
    return ["sudo", "-n", *argv] if sudo else argv


class Probes:
    """Keeps one probe per running instance: starts new ones, restarts dead ones after a pause,
    and stops those whose instance went away."""

    def __init__(self, make: Callable[[str, str], InstanceProbe], clock: Callable[[], float]):
        self.make = make
        self.clock = clock
        self.probes: dict[str, InstanceProbe] = {}

    def sync(self, running: list[tuple[str, str, str]]) -> None:
        """`running`: (key, project, name) of each running instance."""
        wanted = {key for key, _, _ in running}
        for key in list(self.probes):
            if key not in wanted:
                self.probes.pop(key).stop()
        for key, project, name in running:
            current = self.probes.get(key)
            if current is None:
                current = self.make(project, name)
                self.probes[key] = current
                current.start()
            elif not current.running() and self.clock() - current.started_at >= RESTART_AFTER:
                current.start()

    def stop_all(self) -> None:
        for item in self.probes.values():
            item.stop()
