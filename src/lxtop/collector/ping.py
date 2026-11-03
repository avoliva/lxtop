"""How long the host waits for its router, the internet and the service (collector only).

Three checks a round, one round per interval, in a thread so a slow answer never holds up a
sample: an ICMP echo to the default gateway (the home router) and to 1.1.1.1, and every few rounds
a TCP connect to api.github.com:443 (name lookup included, no data sent). Comparing them says
where a hiccup is: inside the house, at the internet provider, or on the way to Service.
The collector runs as root; `net.ipv4.ping_group_range` is closed on the host, so it uses a raw
socket. A result is milliseconds, or LOST when nothing came back within the timeout.
"""

from __future__ import annotations

import contextlib
import os
import select
import socket
import struct
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

LOST = -1.0
SKIPPED = -2.0  # a series value for a tick with no new check of that target
INTERNET = "1.1.1.1"
API_HOST = "api.github.com"
TCP_EVERY = 5  # rounds between TCP checks: about 10 s at the default interval
TIMEOUT = 1.0
ROUTE = "/proc/net/route"

Measure = Callable[[str, str, float], float]


def default_gateway(route_text: str) -> str | None:
    """The default route's gateway with the lowest metric, from /proc/net/route."""
    best: tuple[int, str] | None = None
    for line in route_text.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 7 or fields[1] != "00000000":
            continue
        try:
            flags, metric = int(fields[3], 16), int(fields[6])
            gateway = socket.inet_ntoa(struct.pack("<I", int(fields[2], 16)))
        except ValueError:
            continue
        if flags & 0x2 and (best is None or metric < best[0]):
            best = (metric, gateway)
    return best[1] if best else None


def checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\0"
    total: int = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


def echo_request(ident: int, seq: int) -> bytes:
    payload = b"lxtop"
    header = struct.pack("!BBHHH", 8, 0, 0, ident, seq)
    return struct.pack("!BBHHH", 8, 0, checksum(header + payload), ident, seq) + payload


def is_reply(data: bytes, ident: int, seq: int) -> bool:
    """An echo reply to our request. A raw socket hands over the IPv4 header too."""
    if data[:1] and data[0] >> 4 == 4:
        data = data[(data[0] & 0x0F) * 4 :]
    if len(data) < 8:
        return False
    kind, _code, _sum, got_ident, got_seq = struct.unpack("!BBHHH", data[:8])
    return bool(kind == 0 and got_ident == ident and got_seq == seq)


def icmp_ms(target: str, timeout: float, ident: int, seq: int) -> float:
    """One echo round trip in milliseconds, or LOST. PermissionError without root."""
    with socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP) as sock:
        start = time.monotonic()
        sock.sendto(echo_request(ident, seq), (target, 0))
        deadline = start + timeout
        while (left := deadline - time.monotonic()) > 0:
            ready, _, _ = select.select([sock], [], [], left)
            if not ready:
                break
            data, addr = sock.recvfrom(2048)
            if addr[0] == target and is_reply(data, ident, seq):
                return round((time.monotonic() - start) * 1000, 2)
    return LOST


def tcp_ms(host: str, timeout: float) -> float:
    """Name lookup plus a TCP handshake to port 443, in milliseconds, or LOST."""
    start = time.monotonic()
    try:
        with socket.create_connection((host, 443), timeout=timeout):
            return round((time.monotonic() - start) * 1000, 2)
    except OSError:
        return LOST


class Pinger:
    def __init__(
        self,
        interval: float = 2.0,
        measure: Measure | None = None,
        gateway: Callable[[], str | None] | None = None,
        api_host: str | None = API_HOST,
    ) -> None:
        self.interval = interval
        # None: the collector times the API over HTTPS instead (checks.https_steps).
        self.api_host = api_host
        self.measure = measure or self._measure
        self.gateway = gateway or self._gateway
        self._latest: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._rounds = 0
        self._seq = 0
        self._ident = os.getpid() & 0xFFFF
        self._stop = threading.Event()

    def _gateway(self) -> str | None:
        try:
            return default_gateway(Path(ROUTE).read_text())
        except OSError:
            return None

    def _measure(self, kind: str, target: str, timeout: float) -> float:
        if kind == "tcp":
            return tcp_ms(target, timeout)
        self._seq = (self._seq + 1) & 0xFFFF
        return icmp_ms(target, timeout, self._ident, self._seq)

    def _check(self, name: str, kind: str, target: str) -> None:
        try:
            result: dict[str, Any] = {
                "target": target,
                "ms": self.measure(kind, target, TIMEOUT),
                "round": self._rounds,
            }
        except PermissionError:
            result = {"target": target, "error": "no permission to ping"}
        except OSError as exc:
            result = {"target": target, "error": str(exc)[:100]}
        with self._lock:
            self._latest[name] = result

    def round(self) -> None:
        router = self.gateway()
        if router:
            self._check("router", "icmp", router)
        else:
            with self._lock:
                self._latest.pop("router", None)
        self._check("internet", "icmp", INTERNET)
        if self.api_host and self._rounds % TCP_EVERY == 0:
            self._check("service", "tcp", self.api_host)
        self._rounds += 1

    def latest(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {name: dict(result) for name, result in self._latest.items()}

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="pinger").start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        next_at = time.monotonic()
        while not self._stop.is_set():
            with contextlib.suppress(Exception):  # a broken round must not end the thread
                self.round()
            next_at += self.interval
            self._stop.wait(max(0.0, next_at - time.monotonic()))
            if time.monotonic() - next_at > self.interval:
                next_at = time.monotonic()
