from __future__ import annotations

import ast
import http.client
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from lxtop.collector import probe

STAT = """cpu  100 0 50 800 50 0 0 0 0 0
cpu0 50 0 25 400 25 0 0 0 0 0
cpu1 50 0 25 400 25 0 0 0 0 0
intr 1 2 3
"""
STAT_LATER = """cpu  200 0 100 900 50 0 0 0 0 0
cpu0 150 0 75 400 25 0 0 0 0 0
cpu1 50 0 25 500 25 0 0 0 0 0
"""


def test_cpu_busy_counts_iowait_as_idle() -> None:
    first = probe.parse_proc_stat(STAT)
    later = probe.parse_proc_stat(STAT_LATER)
    assert first["cpu"] == (1000, 850)
    assert probe.cpu_busy(first["cpu"], later["cpu"]) == 150 / 250
    assert probe.cpu_busy(first["cpu0"], later["cpu0"]) == 1.0
    assert probe.cpu_busy(first["cpu1"], later["cpu1"]) == 0.0
    assert probe.cpu_busy(None, later["cpu"]) == 0.0


def test_memory_uses_available_not_free() -> None:
    info = probe.parse_meminfo(
        "MemTotal: 1000 kB\nMemFree: 100 kB\nMemAvailable: 600 kB\nCached: 300 kB\n"
        "Buffers: 50 kB\nSwapTotal: 200 kB\nSwapFree: 150 kB\nHugePages_Total: 0\n"
    )
    mem = probe.memory(info)
    assert mem["total"] == 1000 * 1024
    assert mem["used"] == 400 * 1024
    assert mem["swap_used"] == 50 * 1024
    assert info["HugePages_Total"] == 0


def test_net_dev_and_rates() -> None:
    text = (
        "Inter-|   Receive  |  Transmit\n face |bytes packets|bytes\n"
        "  eno1: 1000 5 0 0 0 0 0 0 2000 7 0 0 0 0 0 0\n"
        "    lo: 10 1 0 0 0 0 0 0 10 1 0 0 0 0 0 0\n"
    )
    first = probe.parse_net_dev(text)
    assert first == {"eno1": (1000, 2000), "lo": (10, 10)}
    later = {"eno1": (3000, 2500), "lo": (10, 10)}
    assert probe.rates(first, later, 2.0)["eno1"] == (1000.0, 250.0)
    # A counter that went backwards (interface re-created) is zero, never negative.
    assert probe.rates(later, first, 2.0)["eno1"] == (0.0, 0.0)
    assert probe.rates(None, later, 2.0)["eno1"] == (0.0, 0.0)


def test_diskstats_keeps_whole_disks_only() -> None:
    text = (
        " 259 0 nvme0n1 10 0 200 0 20 0 400 0 0 0 0\n"
        " 259 1 nvme0n1p1 1 0 2 0 2 0 4 0 0 0 0\n"
        "   7 0 loop0 1 0 2 0 2 0 4 0 0 0 0\n"
        " 252 0 vda 1 0 8 0 1 0 16 0 0 0 0\n"
    )
    assert probe.parse_diskstats(text) == {"nvme0n1": (200 * 512, 400 * 512), "vda": (4096, 8192)}


def test_pid_stat_with_spaces_and_parens_in_the_name() -> None:
    fields = " ".join(["S"] + ["0"] * 10 + ["30", "12"] + ["0"] * 8 + ["99"])
    parsed = probe.parse_pid_stat(f"42 (tmux: server (x)) {fields}")
    assert parsed == ("tmux: server (x)", 42, 99)
    assert probe.parse_pid_stat("garbage") is None


def test_docker_cpu_cores_from_two_readings() -> None:
    def stats(usage: int, system: int) -> probe.Sample:
        return {
            "cpu_stats": {
                "cpu_usage": {"total_usage": usage},
                "system_cpu_usage": system,
                "online_cpus": 4,
            }
        }

    cores, reading = probe.docker_cpu_cores(None, stats(100, 1000))
    assert cores == 0.0
    cores, _ = probe.docker_cpu_cores(reading, stats(200, 1400))
    # 100 of 400 ns of all CPUs, on 4 CPUs: one core busy.
    assert cores == 1.0


def test_docker_memory_and_io() -> None:
    stats = {
        "memory_stats": {"usage": 1000, "limit": 4000, "stats": {"inactive_file": 300}},
        "networks": {"eth0": {"rx_bytes": 5, "tx_bytes": 6}, "eth1": {"rx_bytes": 1}},
        "blkio_stats": {
            "io_service_bytes_recursive": [
                {"op": "read", "value": 10},
                {"op": "write", "value": 20},
                {"op": "Read", "value": 1},
            ]
        },
    }
    assert probe.docker_memory(stats) == (700, 4000)
    assert probe.docker_io(stats) == (6, 6, 11, 20)
    assert probe.docker_memory({}) == (0, 0)
    assert probe.docker_io({"blkio_stats": {"io_service_bytes_recursive": None}}) == (0, 0, 0, 0)


def test_nvidia_csv() -> None:
    line = "0, NVIDIA GeForce RTX 4070 Ti, 12, 1024, 12282, 41, 31.5, 285.00, [N/A]\n"
    (gpu,) = probe.parse_nvidia(line)
    assert gpu["name"] == "NVIDIA GeForce RTX 4070 Ti"
    assert gpu["util"] == 12.0
    assert gpu["fan_pct"] is None
    assert probe.parse_nvidia("only, three, cells") == []


def test_probe_source_has_no_package_imports() -> None:
    """The collector ships this file alone into each instance."""
    tree = ast.parse(Path(probe.__file__).read_text())
    modules = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    modules |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not {m for m in modules if m.split(".")[0] == "lxtop"}
    assert all(m == "__future__" or m.split(".")[0] in sys.stdlib_module_names for m in modules)


RUNSC_PS = """UID       PID       PPID      PGID      C         TTY       STIME     TIME      CMD
20002     1         0         1         0         pts/0     09:35     30ms      docker-init
20002     5         2         2         4         pts/0     09:35     5.05s     worker
20002     2198      2193      2192      41        ?         09:55     1m4.16s   pytest
garbage line
"""


def test_runsc_ps_table() -> None:
    procs = probe.parse_runsc_ps(RUNSC_PS)
    assert [p["name"] for p in procs] == ["docker-init", "worker", "pytest"]
    assert procs[2] == {"pid": 2198, "ppid": 2193, "c": 41.0, "time": 64.16, "name": "pytest"}
    assert probe.parse_runsc_ps("") == []


def test_go_durations() -> None:
    assert probe.go_duration("30ms") == 0.03
    assert probe.go_duration("1h2m3s") == 3723.0
    assert probe.go_duration("?") == 0.0


NET_DEV = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop
    lo:  100 1 0 0 0 0 0 0 100 1 0 0 0 0 0 0
  eno1: 5000 40 2 3 0 0 0 0 7000 50 1 4 0 0 0 0
"""


def test_net_faults_add_errors_and_drops_both_ways() -> None:
    assert probe.parse_net_faults(NET_DEV) == {"lo": 0, "eno1": 10}


SNMP = (
    "Ip: Forwarding DefaultTTL\nIp: 1 64\n"
    "Tcp: RtoAlgorithm RtoMin RtoMax MaxConn ActiveOpens PassiveOpens AttemptFails EstabResets"
    " CurrEstab InSegs OutSegs RetransSegs InErrs OutRsts InCsumErrors\n"
    "Tcp: 1 200 120000 -1 764857 4551 9 731296 5 16084268 18335250 22598 334 885303 0\n"
    "Udp: InDatagrams\nUdp: 7\n"
)


def test_snmp_tcp_counters() -> None:
    tcp = probe.parse_snmp_tcp(SNMP)
    assert tcp["OutSegs"] == 18335250
    assert tcp["RetransSegs"] == 22598
    assert tcp["CurrEstab"] == 5
    assert probe.parse_snmp_tcp("garbage") == {}


WIRELESS = """Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE
 face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22
wlan0: 0000   50.  -60.  -256        0      0      0    781      4        0
"""


def test_wireless_signal() -> None:
    assert probe.parse_wireless(WIRELESS) == [{"name": "wlan0", "quality": 50 / 70, "dbm": -60}]
    assert probe.parse_wireless("") == []


TUNNEL = """# HELP cloudflared_tunnel_response_by_code Count of responses by HTTP status code
# TYPE cloudflared_tunnel_response_by_code counter
cloudflared_tunnel_response_by_code{status_code="200"} 2890
cloudflared_tunnel_response_by_code{status_code="304"} 364
cloudflared_tunnel_response_by_code{status_code="404"} 257
cloudflared_tunnel_response_by_code{status_code="502"} 3
cloudflared_tunnel_request_errors 37
cloudflared_tunnel_ha_connections 4
cloudflared_tunnel_concurrent_requests_per_tunnel 1
something_else{x="y"} 9
"""


def test_tunnel_metrics() -> None:
    found = probe.parse_tunnel_metrics(TUNNEL)
    assert found == {
        "responses": 2890 + 364 + 257 + 3,
        "client_errors": 257,
        "server_errors": 3,
        "request_errors": 37,
        "connections": 4,
    }
    assert probe.parse_tunnel_metrics("no metrics here") is None


def test_tunnel_rates_from_two_readings() -> None:
    before = {"responses": 100, "client_errors": 2, "server_errors": 0, "request_errors": 1}
    after = {"responses": 130, "client_errors": 4, "server_errors": 1, "request_errors": 1}
    rates = probe.tunnel_rates(before, {**after, "connections": 4}, 2.0)
    assert rates == {"req": 15.0, "bad": 0.5, "connections": 4, "total": 130}
    # A restarted cloudflared starts its counters again: no negative rates.
    assert probe.tunnel_rates(after, {**before, "connections": 4}, 2.0)["req"] == 0.0
    assert probe.tunnel_rates(None, {**after, "connections": 4}, 2.0)["req"] == 0.0


RUNSC_EVENTS = (
    '{"type":"stats","id":"abc","data":{"cpu":{"usage":{"total":1}},'
    '"network_interfaces":[{"Name":"lo","RxBytes":213584,"TxBytes":217238}]}}\n'
)


def test_runsc_events_network_bytes() -> None:
    assert probe.parse_runsc_net(RUNSC_EVENTS) == 213584
    assert probe.parse_runsc_net('{"data":{}}') is None
    assert probe.parse_runsc_net("not json") is None


RESOLVED = (
    '{"transactions":{"currentTransactions":0,"totalTransactions":1985,"totalTimeouts":89,'
    '"totalFailedResponses":2},"cache":{"size":11}}'
)


def test_resolved_statistics() -> None:
    assert probe.parse_resolved(RESOLVED) == (1985, 89, 2)
    assert probe.parse_resolved("Failed to connect") is None


# ---- Sampler: the sections read from /proc, driven by fixture text ------------------------------


def feed(monkeypatch: pytest.MonkeyPatch, files: dict[str, str]) -> None:
    """Make probe._read serve `files` (path -> text); any other path reads as empty text.
    The dict is read at call time, so a test can change a file between two samples."""
    monkeypatch.setattr(probe, "_read", lambda path: files.get(path, ""))


def make_sampler(tmp_path: Path) -> probe.Sampler:
    """A Sampler with no GPU tool, no resolvectl, no runsc and a Docker socket that is absent."""
    sampler = probe.Sampler(docker_socket=str(tmp_path / "docker.sock"), gpu=False)
    sampler.resolvectl = None
    sampler.runsc = None
    return sampler


def test_read_returns_empty_text_for_a_missing_file(tmp_path: Path) -> None:
    assert probe._read(str(tmp_path / "none")) == ""


def test_read_returns_the_text_of_a_file(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("a b\n", encoding="utf-8")

    assert probe._read(str(tmp_path / "f")) == "a b\n"


def test_cpu_sample_reports_per_core_and_total_busy_between_two_samples(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = {"/proc/stat": STAT}
    feed(monkeypatch, files)
    sampler = make_sampler(tmp_path)

    first = sampler._cpu_sample()
    files["/proc/stat"] = STAT_LATER
    second = sampler._cpu_sample()

    assert first == {"busy": 0.0, "count": 2, "cores": [0.0, 0.0], "mhz": None}
    # cpu: 150 busy of 250 jiffies; cpu0: 150 of 150; cpu1: 0 of 100.
    assert second == {"busy": 0.6, "count": 2, "cores": [1.0, 0.0], "mhz": None}


@pytest.mark.parametrize(
    ("cpuinfo", "expected"),
    (("cpu MHz\t\t: 3000.0\ncpu MHz\t\t: 1000.0\n", 2000), ("model name\t: x\n", None)),
    ids=("two cores", "no mhz lines"),
)
def test_cpu_sample_averages_the_cpu_mhz_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cpuinfo: str, expected: int | None
) -> None:
    feed(monkeypatch, {"/proc/stat": STAT, "/proc/cpuinfo": cpuinfo})

    assert make_sampler(tmp_path)._cpu_sample()["mhz"] == expected


def test_net_sample_skips_loopback_and_counts_new_faults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    later = NET_DEV.replace("5000 40 2 3 0 0 0 0 7000 50 1 4", "9000 40 2 4 0 0 0 0 8000 50 1 4")
    files = {"/proc/net/dev": NET_DEV}
    feed(monkeypatch, files)
    sampler = make_sampler(tmp_path)

    sampler._net_sample(0.0)
    files["/proc/net/dev"] = later
    rows = sampler._net_sample(2.0)

    # eno1 took 4000 bytes in and 1000 out in 2 s, and one more drop than before.
    assert rows == [{"name": "eno1", "rx": 2000, "tx": 500, "rx_total": 9000, "faults": 1}]


def test_disk_sample_reports_read_and_write_rates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def disk(read_sectors: int, written_sectors: int) -> str:
        return f" 259 0 nvme0n1 10 0 {read_sectors} 0 20 0 {written_sectors} 0 0 0 0\n"

    files = {"/proc/diskstats": disk(200, 400)}
    feed(monkeypatch, files)
    sampler = make_sampler(tmp_path)

    sampler._disk_sample(0.0)
    files["/proc/diskstats"] = disk(600, 1000)
    rows = sampler._disk_sample(2.0)

    # 400 sectors read and 600 written, 512 bytes each, over 2 s.
    assert rows == [{"name": "nvme0n1", "read": 102400, "write": 153600}]


def test_tcp_sample_reports_resends_per_second(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    later = SNMP.replace("18335250 22598", "18335270 22608")
    files = {"/proc/net/snmp": SNMP}
    feed(monkeypatch, files)
    sampler = make_sampler(tmp_path)

    first = sampler._tcp_sample(0.0)
    files["/proc/net/snmp"] = later
    second = sampler._tcp_sample(2.0)

    assert first == {"out": 0.0, "retrans": 0.0, "estab": 5}
    assert second == {"out": 10.0, "retrans": 5.0, "estab": 5}


def test_sample_assembles_every_section(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class QuietSampler(probe.Sampler):
        def _procs(self, seconds: float) -> list[probe.Sample]:
            return []

        def _tunnel_sample(self, seconds: float) -> probe.Sample | None:
            return None

    feed(
        monkeypatch,
        {"/proc/uptime": "123.4 5.6\n", "/proc/loadavg": "0.50 0.40 0.30 1/100 42\n"},
    )
    monkeypatch.setattr(probe, "temperatures", lambda: [])
    sampler = QuietSampler(docker_socket=str(tmp_path / "docker.sock"), gpu=False)
    sampler.resolvectl = None

    sample = sampler.sample()

    assert set(sample) == {
        "hostname", "time", "uptime", "load", "cpu", "mem", "net", "disks", "fs", "temps",
        "gpus", "procs", "docker", "tcp", "wifi", "tunnel", "dns",
    }  # fmt: skip
    assert sample["uptime"] == 123.4
    assert sample["load"] == [0.5, 0.4, 0.3]
    assert sample["docker"] is None  # the socket file does not exist


def run_returning(returncode: int, stdout: str) -> Callable[..., SimpleNamespace]:
    return lambda argv, **kwargs: SimpleNamespace(returncode=returncode, stdout=stdout)


def test_gpus_parse_the_nvidia_smi_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    line = "0, NVIDIA GeForce RTX 4070 Ti, 12, 1024, 12282, 41, 31.5, 285.00, [N/A]\n"
    asked: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        asked.append(argv)
        return SimpleNamespace(returncode=0, stdout=line)

    monkeypatch.setattr(subprocess, "run", fake_run)
    sampler = make_sampler(tmp_path)
    sampler.nvidia = "/usr/bin/nvidia-smi"

    (gpu,) = sampler._gpus()

    assert gpu["name"] == "NVIDIA GeForce RTX 4070 Ti"
    assert asked[0][0] == "/usr/bin/nvidia-smi"


def exits_with_one(argv: list[str], **kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(returncode=1, stdout="")


def cannot_start(argv: list[str], **kwargs: object) -> SimpleNamespace:
    raise OSError("no such file")


@pytest.mark.parametrize("fake_run", (exits_with_one, cannot_start), ids=("exit 1", "os error"))
def test_gpus_are_empty_when_nvidia_smi_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_run: Callable[..., SimpleNamespace],
) -> None:
    monkeypatch.setattr(subprocess, "run", fake_run)
    sampler = make_sampler(tmp_path)
    sampler.nvidia = "/usr/bin/nvidia-smi"

    assert sampler._gpus() == []


def test_gpus_are_empty_without_nvidia_smi(tmp_path: Path) -> None:
    sampler = make_sampler(tmp_path)
    sampler.nvidia = None

    assert sampler._gpus() == []


def dns_sampler(tmp_path: Path) -> probe.Sampler:
    sampler = make_sampler(tmp_path)
    sampler.resolvectl = "/usr/bin/resolvectl"
    return sampler


def resolved_texts(monkeypatch: pytest.MonkeyPatch, texts: list[str]) -> list[list[str]]:
    """`resolvectl statistics` answers `texts` in order; returns the argv lists it was run with."""
    remaining = list(texts)
    asked: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        asked.append(argv)
        return SimpleNamespace(returncode=0, stdout=remaining.pop(0))

    monkeypatch.setattr(subprocess, "run", fake_run)
    return asked


def test_dns_check_reports_lookups_between_two_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    later = RESOLVED.replace("1985", "1990").replace('"totalTimeouts":89', '"totalTimeouts":90')
    resolved_texts(monkeypatch, [RESOLVED, later])
    sampler = dns_sampler(tmp_path)

    sampler._dns_check(100.0)
    second = sampler._dns_check(100.0 + probe.DNS_EVERY)

    assert second == {"lookups": 5, "timeouts": 1, "failed": 0, "seconds": 10.0}


def test_dns_check_reuses_its_last_sample_inside_the_interval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked = resolved_texts(monkeypatch, [RESOLVED])
    sampler = dns_sampler(tmp_path)

    first = sampler._dns_check(100.0)
    again = sampler._dns_check(100.0 + probe.DNS_EVERY - 1)

    assert again == first == {"lookups": 0, "timeouts": 0, "failed": 0, "seconds": 0.0}
    assert len(asked) == 1


def test_dns_check_restarts_its_baseline_when_counters_reset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    smaller = RESOLVED.replace("1985", "10").replace('"totalTimeouts":89', '"totalTimeouts":0')
    resolved_texts(monkeypatch, [RESOLVED, smaller])
    sampler = dns_sampler(tmp_path)

    sampler._dns_check(100.0)
    second = sampler._dns_check(100.0 + probe.DNS_EVERY)

    assert second == {"lookups": 0, "timeouts": 0, "failed": 0, "seconds": 0.0}


def test_dns_check_is_none_when_resolvectl_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(subprocess, "run", cannot_start)

    assert dns_sampler(tmp_path)._dns_check(100.0) is None


class RefusingConnection:
    def __init__(self, host: str, port: int, timeout: float) -> None:
        pass

    def request(self, method: str, path: str) -> None:
        raise ConnectionRefusedError("nothing listens")

    def close(self) -> None:
        pass


def test_tunnel_sample_is_none_when_nothing_listens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(http.client, "HTTPConnection", RefusingConnection)

    assert make_sampler(tmp_path)._tunnel_sample(2.0) is None


def test_tunnel_rates_come_from_two_metric_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bodies = [TUNNEL, TUNNEL.replace('"200"} 2890', '"200"} 2920')]

    class MetricsConnection:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            self.status = 200

        def request(self, method: str, path: str) -> None:
            pass

        def getresponse(self) -> MetricsConnection:
            return self

        def read(self, size: int) -> bytes:
            return bodies.pop(0).encode()

        def close(self) -> None:
            pass

    monkeypatch.setattr(http.client, "HTTPConnection", MetricsConnection)
    sampler = make_sampler(tmp_path)

    sampler._tunnel_sample(0.0)
    second = sampler._tunnel_sample(2.0)

    # 30 more responses in 2 s; the error counters did not move.
    assert second == {"req": 15.0, "bad": 0.0, "connections": 4, "total": 2920 + 364 + 257 + 3}


# ---- Sampler: Docker, gVisor sandboxes, filesystems ---------------------------------------------

CID = "a" * 64


def docker_socket(tmp_path: Path) -> Path:
    """The Sampler checks only that the socket path exists; unix_get is replaced in each test."""
    path = tmp_path / "docker.sock"
    path.touch()
    return path


def serve_docker(monkeypatch: pytest.MonkeyPatch, answers: dict[str, object]) -> list[str]:
    """Replace probe.unix_get. `answers` maps a url to its reply: an exception is raised, a tuple
    is served one item per call, anything else is returned as it is. Returns the urls asked."""
    queued = {url: list(reply) for url, reply in answers.items() if isinstance(reply, tuple)}
    asked: list[str] = []

    def fake_get(path: str, url: str, timeout: float = 3.0) -> object:
        asked.append(url)
        if url in queued:
            return queued[url].pop(0)
        reply = answers[url]
        if isinstance(reply, BaseException):
            raise reply
        return reply

    monkeypatch.setattr(probe, "unix_get", fake_get)
    return asked


def containers_of(result: probe.Sample | None) -> list[probe.Sample]:
    assert result is not None
    containers: list[probe.Sample] = result["containers"]
    return containers


def container(**fields: object) -> dict[str, object]:
    return {"Id": CID, "Names": ["/app"], "Image": "nginx", "State": "running", **fields}


def docker_stats(usage: int, system: int, rx: int, tx: int, read: int, write: int) -> probe.Sample:
    return {
        "cpu_stats": {
            "cpu_usage": {"total_usage": usage},
            "system_cpu_usage": system,
            "online_cpus": 4,
        },
        "memory_stats": {"usage": 1000, "limit": 4000, "stats": {"inactive_file": 300}},
        "networks": {"eth0": {"rx_bytes": rx, "tx_bytes": tx}},
        "blkio_stats": {
            "io_service_bytes_recursive": [
                {"op": "read", "value": read},
                {"op": "write", "value": write},
            ]
        },
        "pids_stats": {"current": 7},
    }


LIST_URL = "/containers/json?all=1"
STATS_URL = f"/containers/{CID}/stats?stream=false&one-shot=true"
INSPECT_URL = f"/containers/{CID}/json"
INSPECT: dict[str, Any] = {
    "HostConfig": {"NanoCpus": 2_000_000_000, "NetworkMode": "bridge", "Runtime": "runc"},
    "State": {"StartedAt": "2026-10-28T00:00:00Z"},
    "RestartCount": 3,
    "Config": {"WorkingDir": "/app"},
    "Mounts": [{"Source": "/srv/data"}, "not a mount"],
}


def test_docker_lists_containers_with_ports_and_labels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stopped = container(
        State="exited",
        Status="Exited (0) 1 hour ago",
        Created=1700000000,
        Labels={"role": "app"},
        Ports=[
            {"IP": "0.0.0.0", "PublicPort": 8080, "PrivatePort": 80, "Type": "tcp"},
            {"PrivatePort": 53, "Type": "udp"},
        ],
    )
    serve_docker(monkeypatch, {LIST_URL: [stopped]})
    sampler = probe.Sampler(docker_socket=str(docker_socket(tmp_path)), gpu=False)

    result = sampler._docker(2.0)

    assert result == {
        "error": None,
        "containers": [
            {
                "id": CID,
                "name": "app",
                "image": "nginx",
                "state": "exited",
                "status": "Exited (0) 1 hour ago",
                "created": 1700000000,
                "labels": {"role": "app"},
                "ports": ["0.0.0.0:8080->80/tcp", "53/udp"],
            }
        ],
    }


def test_docker_reports_the_error_when_the_socket_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    serve_docker(monkeypatch, {LIST_URL: OSError("HTTP 500 for /containers/json?all=1")})
    sampler = probe.Sampler(docker_socket=str(docker_socket(tmp_path)), gpu=False)

    assert sampler._docker(2.0) == {
        "error": "HTTP 500 for /containers/json?all=1",
        "containers": [],
    }


def test_docker_is_none_without_a_socket(tmp_path: Path) -> None:
    sampler = probe.Sampler(docker_socket=str(tmp_path / "missing.sock"), gpu=False)

    assert sampler._docker(2.0) is None


def test_docker_forgets_containers_that_are_gone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    serve_docker(monkeypatch, {LIST_URL: []})
    sampler = probe.Sampler(docker_socket=str(docker_socket(tmp_path)), gpu=False)
    sampler._docker_cpu["gone"] = (1, 2)
    sampler._docker_io["gone"] = (1, 2, 3, 4)
    sampler._inspect["gone"] = {}
    sampler._sandbox_time["gone"] = {1: 0.5}
    sampler._sandbox_net["gone"] = 9

    sampler._docker(2.0)

    kept = [
        "gone" in d
        for d in (
            sampler._docker_cpu,
            sampler._docker_io,
            sampler._inspect,
            sampler._sandbox_time,
            sampler._sandbox_net,
        )
    ]
    assert kept == [False] * 5


def running_container_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stats: tuple[probe.Sample, ...]
) -> list[probe.Sample]:
    """Sample a running container once per entry of `stats`; returns the row of each sample."""
    answers: dict[str, object] = {LIST_URL: [container()], STATS_URL: stats, INSPECT_URL: INSPECT}
    serve_docker(monkeypatch, answers)
    sampler = probe.Sampler(docker_socket=str(docker_socket(tmp_path)), gpu=False)
    return [containers_of(sampler._docker(2.0))[0] for _ in stats]


def test_container_stats_report_cpu_memory_io_and_limits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = docker_stats(100, 1000, 500, 600, 10, 20)
    second = docker_stats(200, 1400, 1500, 1100, 110, 220)

    _, row = running_container_rows(monkeypatch, tmp_path, (first, second))

    assert {k: row[k] for k in ("cpu_cores", "cpu_cap", "cpu_limit", "mem_used", "mem_limit")} == {
        "cpu_cores": 1.0,  # 100 of 400 ns on 4 CPUs
        "cpu_cap": 2.0,
        "cpu_limit": 2.0,  # HostConfig.NanoCpus / 1e9
        "mem_used": 700,  # usage 1000 minus inactive_file 300
        "mem_limit": 4000,
    }
    assert {k: row[k] for k in ("pids", "rx", "tx", "blk_read", "blk_write")} == {
        "pids": 7,
        "rx": 500,  # (1500 - 500) bytes over 2 s
        "tx": 250,
        "blk_read": 110,
        "blk_write": 220,
    }
    assert {k: row[k] for k in ("restarts", "network_mode", "runtime", "workdir", "mounts")} == {
        "restarts": 3,
        "network_mode": "bridge",
        "runtime": "runc",
        "workdir": "/app",
        "mounts": ["/srv/data"],  # a non-dict mount entry is skipped
    }


def test_container_stats_error_is_kept_on_the_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    serve_docker(monkeypatch, {LIST_URL: [container()], STATS_URL: OSError("boom")})
    sampler = probe.Sampler(docker_socket=str(docker_socket(tmp_path)), gpu=False)

    (row,) = containers_of(sampler._docker(2.0))

    assert row["error"] == "boom"
    assert "cpu_cores" not in row


RUNSC_INSPECT: dict[str, Any] = {
    **INSPECT,
    "HostConfig": {**INSPECT["HostConfig"], "Runtime": "runsc"},
}


def fake_runsc(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, events: list[str], ps: list[str]
) -> None:
    """`runsc events --stats` and `runsc ps` answer from the two lists, in order. The runsc
    state folder is a real folder (tmp_path), so the sampler does not skip it."""
    monkeypatch.setattr(probe, "RUNSC_ROOTS", (str(tmp_path),))
    events, ps = list(events), list(ps)

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        text = events.pop(0) if "events" in argv else ps.pop(0)
        return SimpleNamespace(returncode=0, stdout=text)

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_sandbox_traffic_reads_runsc_events_and_rates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    later = RUNSC_EVENTS.replace('"RxBytes":213584', '"RxBytes":217584')
    fake_runsc(monkeypatch, tmp_path, [RUNSC_EVENTS, later], [RUNSC_PS, RUNSC_PS])
    answers: dict[str, object] = {
        LIST_URL: [container()],
        STATS_URL: docker_stats(100, 1000, 0, 0, 0, 0),
        INSPECT_URL: RUNSC_INSPECT,
    }
    serve_docker(monkeypatch, answers)
    sampler = probe.Sampler(docker_socket=str(docker_socket(tmp_path)), gpu=False)
    sampler.runsc = "/usr/bin/runsc"

    sampler._docker(2.0)
    (row,) = containers_of(sampler._docker(2.0))

    # 4000 more bytes through the sandbox's network stack in 2 s.
    assert (row["sandbox_net"], row["sandbox_net_total"]) == (2000, 217584)


def test_sandbox_procs_start_from_the_lifetime_average(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_runsc(monkeypatch, tmp_path, [], [RUNSC_PS])
    sampler = make_sampler(tmp_path)
    sampler.runsc = "/usr/bin/runsc"

    procs = sampler._sandbox_procs(CID, 0.0)

    assert procs is not None
    assert [(p["name"], p["cpu"]) for p in procs] == [
        ("docker-init", 0.0),
        ("worker", 0.04),
        ("pytest", 0.41),
    ]  # round(C / 100, 3)


def test_sandbox_procs_use_cpu_time_between_samples(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    later = RUNSC_PS.replace("1m4.16s", "1m6.16s")
    fake_runsc(monkeypatch, tmp_path, [], [RUNSC_PS, later])
    sampler = make_sampler(tmp_path)
    sampler.runsc = "/usr/bin/runsc"

    sampler._sandbox_procs(CID, 2.0)
    procs = sampler._sandbox_procs(CID, 2.0)

    assert procs is not None
    # Only pytest used CPU: 2 s of CPU time in 2 s.
    assert [(p["name"], p["cpu"]) for p in procs] == [
        ("docker-init", 0.0),
        ("worker", 0.0),
        ("pytest", 1.0),
    ]


def test_sandbox_calls_are_skipped_without_runsc(tmp_path: Path) -> None:
    sampler = make_sampler(tmp_path)
    row: probe.Sample = {}

    sampler._sandbox_traffic(CID, row, 2.0)

    assert sampler._sandbox_procs(CID, 2.0) is None
    assert row == {}


def test_filesystems_list_each_real_device_once(tmp_path: Path) -> None:
    mounts = (
        f"/dev/sda1 {tmp_path} ext4 rw 0 0\n"
        f"/dev/sda1 {tmp_path} ext4 rw 0 0\n"
        "tmpfs /run tmpfs rw 0 0\n"
        f"/dev/sdb1 {tmp_path}/missing ext4 rw 0 0\n"
    )

    (row,) = probe.filesystems(mounts)

    assert (row["mount"], row["device"]) == (str(tmp_path), "/dev/sda1")
    assert 0 < row["used"] <= row["total"]


class FakeUnixConnection:
    """What unix_get talks to: replies with `status` and a JSON body."""

    status = 200
    last: FakeUnixConnection

    def __init__(self, path: str, timeout: float) -> None:
        self.closed = False
        FakeUnixConnection.last = self

    def request(self, method: str, url: str) -> None:
        pass

    def getresponse(self) -> FakeUnixConnection:
        return self

    def read(self) -> bytes:
        return b'{"ok": true}'

    def close(self) -> None:
        self.closed = True


def test_unix_get_decodes_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probe, "_UnixConnection", FakeUnixConnection)

    assert probe.unix_get("/s", "/x") == {"ok": True}
    assert FakeUnixConnection.last.closed is True


def test_unix_get_rejects_other_statuses_and_still_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Refusing(FakeUnixConnection):
        status = 500

    monkeypatch.setattr(probe, "_UnixConnection", Refusing)

    with pytest.raises(OSError, match="HTTP 500 for /x"):
        probe.unix_get("/s", "/x")

    assert Refusing.last.closed is True


def test_num_and_float_fall_back_to_zero() -> None:
    assert probe._num("x") == 0.0
    assert probe._num("2.5") == 2.5
    assert probe._float([]) == 0.0


class StopLoop(Exception):
    pass


class ClosedPipe:
    def write(self, text: str) -> int:
        raise BrokenPipeError("reader went away")

    def flush(self) -> None:
        pass


class OneLineSampler:
    def sample(self) -> probe.Sample:
        return {"a": 1}


def test_main_prints_one_json_line_and_stops_on_a_closed_pipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(probe, "Sampler", OneLineSampler)
    monkeypatch.setattr(sys, "stdout", ClosedPipe())

    assert probe.main(["--interval", "0.5"]) == 0


def test_main_writes_a_line_then_waits_for_the_next_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Recording:
        def __init__(self) -> None:
            self.text = ""

        def write(self, text: str) -> int:
            self.text += text
            return len(text)

        def flush(self) -> None:
            pass

    out = Recording()
    slept: list[float] = []

    def stop_after_first_sleep(seconds: float) -> None:
        slept.append(seconds)
        raise StopLoop

    monkeypatch.setattr(probe, "Sampler", OneLineSampler)
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(time, "sleep", stop_after_first_sleep)

    with pytest.raises(StopLoop):
        probe.main(["--interval", "2"])

    assert out.text == '{"a":1}\n'
    assert 0.0 <= slept[0] <= 2.0


def test_pid_stat_with_too_few_fields_is_none() -> None:
    assert probe.parse_pid_stat("1 (x) S 1 2") is None


def test_docker_cpu_cores_without_progress_is_zero() -> None:
    stats = {"cpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 1000}}

    cores, reading = probe.docker_cpu_cores((100, 1000), stats)

    assert (cores, reading) == (0.0, (100, 1000))


@pytest.mark.parametrize("text", ("not json", '{"transactions": 3}', "[]"))
def test_resolved_statistics_reject_text_that_is_not_the_expected_json(text: str) -> None:
    assert probe.parse_resolved(text) is None


def test_cpu_busy_is_zero_when_no_time_passed() -> None:
    assert probe.cpu_busy((1000, 850), (1000, 850)) == 0.0


def test_snmp_tcp_counters_that_are_not_numbers_are_ignored() -> None:
    text = "Tcp: A B\nTcp: 1 x\n"

    assert probe.parse_snmp_tcp(text) == {}
