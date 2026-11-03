"""The collector's slower network checks, each in its own thread so none holds up a sample.

- `https_steps`: an HTTPS request to a model API, timed step by step (name lookup, TCP connect,
  TLS handshake, first byte). It sends no key, so the API answers 401 at once; that is the path
  and the work a request starts with.
- `dns_ms`: a lookup of a fresh name (so no cache answers it) at one resolver.
- `download_bits`: a short download from Cloudflare's speed test, in bits per second.
- `trace`: `mtr` to 1.1.1.1, run when pings start getting lost, to say which hop loses them.
Results are plain dicts; a failure is {"error": "..."} and a lost answer is ms LOST.
"""

from __future__ import annotations

import contextlib
import json
import random
import select
import shutil
import socket
import ssl
import struct
import subprocess
import threading
import time
from collections.abc import Callable
from typing import Any

LOST = -1.0
Result = dict[str, Any]


def _ms(start: float) -> float:
    return round((time.monotonic() - start) * 1000, 2)


# ---- DNS --------------------------------------------------------------------------------------


def dns_query(name: str, ident: int) -> bytes:
    header = struct.pack("!HHHHHH", ident, 0x0100, 1, 0, 0, 0)
    labels = b"".join(bytes([len(p)]) + p.encode() for p in name.split("."))
    return header + labels + b"\x00" + struct.pack("!HH", 1, 1)


def is_dns_answer(data: bytes, ident: int) -> bool:
    if len(data) < 12:
        return False
    got, flags = struct.unpack("!HH", data[:4])
    return bool(got == ident and flags & 0x8000)


def fresh_name() -> str:
    """A name no resolver has cached: the resolver must ask the internet (an NXDOMAIN answer)."""
    return f"tt{random.randrange(10**9)}.example.com"


def dns_ms(server: str, timeout: float = 2.0) -> Result:
    ident = random.randrange(1 << 16)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        start = time.monotonic()
        sock.sendto(dns_query(fresh_name(), ident), (server, 53))
        deadline = start + timeout
        while (left := deadline - time.monotonic()) > 0:
            ready, _, _ = select.select([sock], [], [], left)
            if not ready:
                break
            data, _addr = sock.recvfrom(2048)
            if is_dns_answer(data, ident):
                return {"target": server, "ms": _ms(start)}
    return {"target": server, "ms": LOST}


# ---- HTTPS, step by step ----------------------------------------------------------------------


def https_steps(host: str, path: str = "/", timeout: float = 5.0) -> Result:
    """Milliseconds from the start to: the name looked up, TCP connected, TLS done, first byte."""
    start = time.monotonic()
    out: Result = {"target": host}
    try:
        infos = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
        out["dns"] = _ms(start)
        address = str(infos[0][4][0])
        sock = socket.create_connection((address, 443), timeout=timeout)
        out["connect"] = _ms(start)
        context = ssl.create_default_context()
        with context.wrap_socket(sock, server_hostname=host) as tls:
            out["tls"] = _ms(start)
            tls.sendall(
                f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: lxtop\r\n"
                "Connection: close\r\n\r\n".encode()
            )
            first = tls.recv(64)
            out["first"] = _ms(start)
            parts = first.split(b" ", 2)
            out["status"] = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    except (OSError, ssl.SSLError) as exc:
        out["error"] = str(exc)[:120] or type(exc).__name__
        out["ms"] = LOST
        return out
    out["ms"] = out["first"]
    return out


# ---- speed ------------------------------------------------------------------------------------

SPEED_HOST = "speed.cloudflare.com"
SPEED_BYTES = 10_000_000  # every 30 minutes: about 0.5 GB a day


def download_bits(nbytes: int = SPEED_BYTES, timeout: float = 30.0) -> Result:
    import http.client

    conn = http.client.HTTPSConnection(SPEED_HOST, timeout=timeout)
    try:
        conn.request("GET", f"/__down?bytes={nbytes}", headers={"User-Agent": "lxtop"})
        reply = conn.getresponse()
        start = time.monotonic()
        got = 0
        while chunk := reply.read(1 << 16):
            got += len(chunk)
        seconds = time.monotonic() - start
    finally:
        conn.close()
    return {"bits": round(got * 8 / seconds) if seconds > 0 else 0, "bytes": got}


# ---- trace ------------------------------------------------------------------------------------

TRACE_TARGET = "1.1.1.1"


def parse_mtr(text: str) -> list[Result]:
    try:
        hubs = json.loads(text)["report"]["hubs"]
    except (ValueError, KeyError, TypeError):
        return []
    return [
        {"hop": int(h.get("count", 0)), "host": str(h.get("host", "?"))[:60],
         "loss": float(h.get("Loss%", 0.0)), "ms": float(h.get("Avg", 0.0))}
        for h in hubs
        if isinstance(h, dict)
    ][:40]  # fmt: skip


def first_lossy(hops: list[Result], threshold: float = 5.0) -> Result | None:
    """The first hop from which loss carries on to the destination (a hop that only drops
    answers to mtr itself, while later hops lose nothing, is not it)."""
    for i, hop in enumerate(hops):
        if hop["loss"] >= threshold and all(h["loss"] >= threshold for h in hops[i:]):
            return hop
    return None


def trace(target: str = TRACE_TARGET) -> Result:
    mtr = shutil.which("mtr")
    if not mtr:
        return {"error": "mtr is not installed"}
    done = subprocess.run(
        [mtr, "--report", "--json", "--no-dns", "--report-cycles", "20", target],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    hops = parse_mtr(done.stdout)
    if not hops:
        return {"error": (done.stderr.strip() or "no report")[:120]}
    return {"target": target, "hops": hops, "first_lossy": first_lossy(hops)}


# ---- scheduling -------------------------------------------------------------------------------


class Every:
    """Runs `fn` every `seconds` in its own thread and keeps its last result, with the round it
    came from (so the collector records each result once) and when it finished."""

    def __init__(
        self,
        name: str,
        seconds: float,
        fn: Callable[[], Result],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.name, self.seconds, self.fn, self.clock = name, seconds, fn, clock
        self._latest: Result = {}
        self._rounds = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def run_once(self) -> None:
        try:
            result = dict(self.fn())
        except Exception as exc:  # a check must never kill the collector
            result = {"error": f"{type(exc).__name__}: {exc}"[:120]}
        with self._lock:
            self._rounds += 1
            result.update(round=self._rounds, at=self.clock())
            self._latest = result

    def latest(self) -> Result:
        with self._lock:
            return dict(self._latest)

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name=self.name).start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            self.run_once()
            self._stop.wait(max(1.0, self.seconds - (time.monotonic() - started)))


class Trigger(Every):
    """Like Every, but runs only when fired, at most once per `seconds`."""

    def __init__(
        self,
        name: str,
        seconds: float,
        fn: Callable[[], Result],
        clock: Callable[[], float] = time.time,
    ) -> None:
        super().__init__(name, seconds, fn, clock)
        self._last_fire = float("-inf")
        self._busy = threading.Lock()

    def fire(self, background: bool = True) -> bool:
        now = self.clock()
        if now - self._last_fire < self.seconds or self._busy.locked():
            return False
        self._last_fire = now

        def go() -> None:
            with self._busy:
                self.run_once()

        if background:
            threading.Thread(target=go, daemon=True, name=self.name).start()
        else:
            go()
        return True

    def start(self) -> None:  # fired, never on a timer
        return None


def stop_all(jobs: list[Every]) -> None:
    for job in jobs:
        with contextlib.suppress(Exception):
            job.stop()
