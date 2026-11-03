from __future__ import annotations

import re
import struct
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from lxtop.collector import checks
from tests.support.clock import Clock
from tests.support.threads import RecordedThread


def test_dns_query_asks_for_an_a_record() -> None:
    packet = checks.dns_query("tt123.example.com", 0xBEEF)
    ident, flags, questions = struct.unpack("!HHH", packet[:6])
    assert (ident, flags, questions) == (0xBEEF, 0x0100, 1)  # recursion desired
    assert packet[12:] == b"\x05tt123\x07example\x03com\x00" + b"\x00\x01\x00\x01"


def test_dns_answer_matches_by_id_and_answer_flag() -> None:
    reply = struct.pack("!HHHHHH", 0xBEEF, 0x8183, 1, 0, 0, 0)  # NXDOMAIN is still an answer
    assert checks.is_dns_answer(reply, 0xBEEF)
    assert not checks.is_dns_answer(reply, 0xBEEE)
    assert not checks.is_dns_answer(struct.pack("!HH", 0xBEEF, 0x0100), 0xBEEF)  # a question


MTR = """{"report": {"mtr": {"dst": "1.1.1.1"}, "hubs": [
  {"count": 1, "host": "10.0.0.1", "Loss%": 0.0, "Avg": 3.1},
  {"count": 2, "host": "198.51.100.1", "Loss%": 20.0, "Avg": 12.4},
  {"count": 3, "host": "203.0.113.1", "Loss%": 25.0, "Avg": 14.0},
  {"count": 4, "host": "1.1.1.1", "Loss%": 22.0, "Avg": 18.2}
]}}"""


def test_mtr_report_and_where_loss_starts() -> None:
    hops = checks.parse_mtr(MTR)
    assert [h["host"] for h in hops] == ["10.0.0.1", "198.51.100.1", "203.0.113.1", "1.1.1.1"]
    first = checks.first_lossy(hops)
    assert first is not None and first["hop"] == 2 and first["loss"] == 20.0
    assert checks.first_lossy(hops[:1]) is None
    assert checks.parse_mtr("not json") == []


def test_mtr_ignores_a_router_that_only_drops_its_own_replies() -> None:
    # A middle hop that rate-limits answers to mtr but forwards everything is not where loss
    # starts: the hops after it lose nothing.
    hops = checks.parse_mtr(
        '{"report": {"hubs": [{"count": 1, "host": "a", "Loss%": 0},'
        '{"count": 2, "host": "b", "Loss%": 60}, {"count": 3, "host": "c", "Loss%": 0}]}}'
    )
    assert checks.first_lossy(hops) is None


def test_every_counts_rounds_and_keeps_the_last_result() -> None:
    calls = []

    def run() -> dict[str, float]:
        calls.append(1)
        return {"ms": float(len(calls))}

    job = checks.Every("dns", 10.0, run, clock=Clock(1000.0))
    job.run_once()
    job.run_once()
    latest = job.latest()
    assert latest["ms"] == 2.0 and latest["round"] == 2 and latest["at"] == 1000.0


def test_every_turns_an_exception_into_an_error_result() -> None:
    def broken() -> dict[str, float]:
        raise OSError("network is unreachable")

    job = checks.Every("api", 10.0, broken, clock=Clock(1000.0))
    job.run_once()
    assert job.latest()["error"] == "OSError: network is unreachable"


def test_trigger_waits_out_its_pause() -> None:
    clock = Clock(1000.0)
    runs = []

    def run() -> dict[str, list[int]]:
        runs.append(1)
        return {"hops": []}

    trigger = checks.Trigger("trace", 600.0, run, clock=clock)
    assert trigger.fire(background=False)
    assert not trigger.fire(background=False)  # within the pause
    clock.now += 601
    assert trigger.fire(background=False)
    assert len(runs) == 2


# ---- fakes for the code that talks to the network, a thread or a subprocess ---------------------


def record_threads(monkeypatch: pytest.MonkeyPatch) -> list[RecordedThread]:
    """Replace `threading.Thread` inside checks.py. Patch after the Every / Trigger is built:
    their constructors still need the real `threading.Lock` and `threading.Event`."""
    made: list[RecordedThread] = []

    def thread(target: Callable[[], None], daemon: bool, name: str) -> RecordedThread:
        made.append(RecordedThread(target, daemon, name))
        return made[-1]

    monkeypatch.setattr(checks, "threading", SimpleNamespace(Thread=thread))
    return made


def ticking(*values: float) -> Callable[[], float]:
    """A `time.monotonic` that returns `values` in order."""
    remaining = list(values)
    return lambda: remaining.pop(0)


class FakeUdp:
    """The DNS socket: remembers what was sent and answers it, flagged as a reply."""

    def __init__(self) -> None:
        self.sent = b""

    def __enter__(self) -> FakeUdp:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def sendto(self, data: bytes, address: tuple[str, int]) -> None:
        self.sent = data

    def recvfrom(self, size: int) -> tuple[bytes, tuple[str, int]]:
        return self.sent[:2] + struct.pack("!H", 0x8183) + bytes(8), ("192.0.2.53", 53)


class FakeDownload:
    """http.client.HTTPSConnection that serves two 1000-byte chunks, then ends."""

    last: FakeDownload

    def __init__(self, host: str, timeout: float) -> None:
        self.closed = False
        FakeDownload.last = self

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        return None

    def getresponse(self) -> FakeDownload:
        self.chunks = [b"x" * 1000, b"x" * 1000, b""]
        return self

    def read(self, size: int) -> bytes:
        return self.chunks.pop(0)

    def close(self) -> None:
        self.closed = True


# ---- Every / Trigger: the loop, stop and start --------------------------------------------------


def test_every_loop_runs_until_its_job_stops_it() -> None:
    rounds: list[int] = []

    def run() -> checks.Result:
        rounds.append(1)
        job.stop()
        return {}

    job = checks.Every("dns", 10.0, run, clock=Clock(1000.0))

    job._run()

    assert rounds == [1]
    assert job.latest()["round"] == 1


def test_every_stop_sets_the_flag() -> None:
    rounds: list[int] = []

    def run() -> checks.Result:
        rounds.append(1)
        return {}

    job = checks.Every("dns", 10.0, run, clock=Clock(1000.0))

    job.stop()
    job._run()

    assert rounds == []
    assert job.latest() == {}


def test_every_start_runs_the_loop_in_a_named_daemon_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = checks.Every("dns", 10.0, dict, clock=Clock(1000.0))
    made = record_threads(monkeypatch)

    job.start()

    (thread,) = made
    assert (thread.daemon, thread.name, thread.started) == (True, "dns", True)
    assert thread.target == job._run


def test_trigger_start_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    trigger = checks.Trigger("trace", 600.0, dict, clock=Clock(1000.0))
    made = record_threads(monkeypatch)

    trigger.start()

    assert made == []


def test_stop_all_ignores_a_job_that_fails_to_stop() -> None:
    class BadStop(checks.Every):
        def stop(self) -> None:
            raise RuntimeError("cannot stop")

    class Recorded(checks.Every):
        stopped = False

        def stop(self) -> None:
            self.stopped = True

    bad = BadStop("bad", 10.0, dict)
    good = Recorded("good", 10.0, dict)

    checks.stop_all([bad, good])

    assert good.stopped is True


# ---- trace --------------------------------------------------------------------------------------


def fake_mtr(monkeypatch: pytest.MonkeyPatch, stdout: str, stderr: str = "") -> None:
    monkeypatch.setattr(checks, "shutil", SimpleNamespace(which=lambda name: "/usr/bin/mtr"))
    monkeypatch.setattr(
        checks,
        "subprocess",
        SimpleNamespace(run=lambda *a, **k: SimpleNamespace(stdout=stdout, stderr=stderr)),
    )


def test_trace_reports_the_hops_and_the_first_lossy_hop(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_mtr(monkeypatch, MTR)

    result = checks.trace("1.1.1.1")

    assert result["target"] == "1.1.1.1"
    assert len(result["hops"]) == 4
    assert result["first_lossy"]["hop"] == 2


def test_trace_says_when_mtr_is_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checks, "shutil", SimpleNamespace(which=lambda name: None))

    assert checks.trace() == {"error": "mtr is not installed"}


def test_trace_without_a_report_returns_the_error_text(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_mtr(monkeypatch, "not json", " mtr: boom \n")

    assert checks.trace() == {"error": "mtr: boom"}


def test_trace_with_no_text_at_all_says_no_report(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_mtr(monkeypatch, "", "")

    assert checks.trace() == {"error": "no report"}


# ---- dns, download, https -----------------------------------------------------------------------


def test_dns_ms_returns_the_round_trip_for_a_matching_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sock = FakeUdp()
    monkeypatch.setattr(
        checks, "socket", SimpleNamespace(socket=lambda *a: sock, AF_INET=2, SOCK_DGRAM=2)
    )
    monkeypatch.setattr(
        checks, "select", SimpleNamespace(select=lambda r, w, x, t: ([sock], [], []))
    )
    monkeypatch.setattr(checks, "time", SimpleNamespace(monotonic=ticking(1.0, 1.0, 1.25)))

    assert checks.dns_ms("192.0.2.53") == {"target": "192.0.2.53", "ms": 250.0}


def test_dns_ms_is_lost_when_nothing_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    sock = FakeUdp()
    monkeypatch.setattr(
        checks, "socket", SimpleNamespace(socket=lambda *a: sock, AF_INET=2, SOCK_DGRAM=2)
    )
    monkeypatch.setattr(checks, "select", SimpleNamespace(select=lambda r, w, x, t: ([], [], [])))
    monkeypatch.setattr(checks, "time", SimpleNamespace(monotonic=ticking(1.0, 1.0)))

    assert checks.dns_ms("192.0.2.53") == {"target": "192.0.2.53", "ms": checks.LOST}


def test_download_bits_counts_bytes_and_bits_per_second(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("http.client.HTTPSConnection", FakeDownload)
    monkeypatch.setattr(checks, "time", SimpleNamespace(monotonic=ticking(10.0, 12.0)))

    assert checks.download_bits(2000) == {"bits": 8000, "bytes": 2000}
    assert FakeDownload.last.closed is True


def test_https_steps_reports_a_failed_lookup_as_lost(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object) -> None:
        raise OSError("name or service not known")

    monkeypatch.setattr(
        checks, "socket", SimpleNamespace(getaddrinfo=refuse, AF_INET=2, SOCK_STREAM=1)
    )

    assert checks.https_steps("api.example.test") == {
        "target": "api.example.test",
        "error": "name or service not known",
        "ms": checks.LOST,
    }


def test_fresh_name_is_a_new_example_com_name() -> None:
    assert re.fullmatch(r"tt\d+\.example\.com", checks.fresh_name()) is not None
