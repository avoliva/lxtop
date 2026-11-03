from __future__ import annotations

import contextlib
import os
import struct
from types import SimpleNamespace

import pytest

from lxtop.collector import ping

ROUTE = """Iface	Destination	Gateway 	Flags	RefCnt	Use	Metric	Mask		MTU	Window	IRTT
eno1	00000000	0100000A	0003	0	0	100	00000000	0	0	0
wlan0	00000000	0100000A	0003	0	0	600	00000000	0	0	0
eno1	0000000A	00000000	0001	0	0	100	00FFFFFF	0	0	0
"""


def test_echo_request_has_a_valid_checksum() -> None:
    packet = ping.echo_request(0x1234, 7)
    assert packet[0] == 8  # echo request
    assert ping.checksum(packet) == 0  # a correct checksum sums to zero
    assert struct.unpack("!HH", packet[4:8]) == (0x1234, 7)


def reply(ident: int, seq: int, kind: int = 0) -> bytes:
    body = struct.pack("!BBHHH", kind, 0, 0, ident, seq) + b"lxtop"
    return body


def test_echo_reply_with_and_without_an_ip_header() -> None:
    ip_header = bytes([0x45]) + bytes(19)  # IPv4, 20-byte header, as a raw socket gives it
    assert ping.is_reply(ip_header + reply(5, 9), 5, 9)
    assert ping.is_reply(reply(5, 9), 5, 9)
    assert not ping.is_reply(ip_header + reply(5, 8), 5, 9)  # an older reply
    assert not ping.is_reply(ip_header + reply(6, 9), 5, 9)  # another program's ping
    assert not ping.is_reply(ip_header + reply(5, 9, kind=8), 5, 9)  # our own request
    assert not ping.is_reply(b"\x45\x00", 5, 9)


# ---- the route file, the real measure, the loop --------------------------------------------------


def test_measure_sends_tcp_checks_to_tcp_ms_and_icmp_to_icmp_ms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    icmp_calls: list[tuple[str, float, int, int]] = []

    def fake_icmp(target: str, timeout: float, ident: int, seq: int) -> float:
        icmp_calls.append((target, timeout, ident, seq))
        return 2.5

    monkeypatch.setattr(ping, "tcp_ms", lambda host, timeout: 1.5)
    monkeypatch.setattr(ping, "icmp_ms", fake_icmp)
    pinger = ping.Pinger()

    assert pinger.measure("tcp", "h", 1.0) == 1.5
    assert pinger.measure("icmp", "10.0.0.1", 1.0) == 2.5
    assert icmp_calls == [("10.0.0.1", 1.0, os.getpid() & 0xFFFF, 1)]


def test_the_icmp_sequence_number_counts_up_and_wraps_at_16_bits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seqs: list[int] = []

    def fake_icmp(target: str, timeout: float, ident: int, seq: int) -> float:
        seqs.append(seq)
        return 0.0

    monkeypatch.setattr(ping, "icmp_ms", fake_icmp)
    pinger = ping.Pinger()
    pinger._seq = 0xFFFF

    pinger.measure("icmp", "10.0.0.1", 1.0)

    assert seqs == [0]


def test_tcp_ms_is_lost_when_the_connection_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(address: tuple[str, int], timeout: float) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(ping, "socket", SimpleNamespace(create_connection=refuse))

    assert ping.tcp_ms("h", 1.0) == ping.LOST


def test_tcp_ms_returns_the_handshake_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ping,
        "socket",
        SimpleNamespace(create_connection=lambda address, timeout: contextlib.nullcontext()),
    )

    assert ping.tcp_ms("h", 1.0) >= 0.0
