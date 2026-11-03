"""The memory reader: pressure, meminfo, VMs' host memory, the user slice and its jobs,
containers and GPU owners, from a fake /proc and cgroup tree."""

from __future__ import annotations

from pathlib import Path

import pytest

from lxtop.collector import memory
from tests.support.host_state import GIB, UID, fake_proc, group


@pytest.fixture
def tree(tmp_path: Path) -> tuple[Path, Path]:
    proc = fake_proc(
        tmp_path,
        {
            100: (
                ["/snap/lxd/current/bin/qemu-system-x86_64", "-S", "-name", "app", "-uuid", "x"],
                7 * 1024 * 1024,
                "/",
            ),
            101: (
                ["qemu-system-x86_64", "-name", "guest=ci,debug-threads=on"],
                8 * 1024 * 1024,
                "/",
            ),
            102: (["qemu-system-x86_64", "-nodefaults"], 1024, "/"),  # no -name: skipped
            200: (
                ["/home/admin/.venv/bin/stats", "build", "gold"],
                1024,
                "/user.slice/user-1000.slice/user@1000.service/app.slice/stats-build.service",
            ),
            300: (["python3", "search.py"], 1024, "/user.slice/user-1000.slice/session-9.scope"),
            400: (
                ["/usr/bin/ollama", "serve"],
                1024,
                "/lxc.payload.llm/system.slice/ollama.service",
            ),
        },
    )
    root = tmp_path / "cgroup"
    top = "user.slice/user-1000.slice"
    group(root, top, 14 * GIB, peak=50 * GIB, maximum=str(40 * GIB), high=str(36 * GIB), kills=6)
    (root / top / "memory.pressure").write_text(
        "some avg10=7.50 avg60=1.00 avg300=0.00 total=1\n"
        "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
    )
    group(root, f"{top}/user@1000.service", 10 * GIB)
    group(root, f"{top}/user@1000.service/init.scope", 200 << 20, procs="5\n")
    group(
        root,
        f"{top}/user@1000.service/app.slice/stats-build.service",
        9 * GIB,
        peak=12 * GIB,
        maximum=str(30 * GIB),
        kills=1,
        procs="200\n",
    )
    group(root, f"{top}/user@1000.service/app.slice/tiny.service", 1 << 20, procs="201\n")
    group(root, f"{top}/session-9.scope", 2 * GIB, procs="300\n")
    group(root, "lxc.payload.llm", 3 * GIB, maximum=str(16 * GIB))
    return proc, root


def test_pressure_and_meminfo_are_read(tree: tuple[Path, Path]) -> None:
    proc, _ = tree
    assert memory.pressure(proc)["memory"] == {
        "some10": 12.5,
        "some60": 3.0,
        "full10": 0.5,
        "full60": 0.1,
    }
    assert memory.pressure(proc)["cpu"]["some10"] == 2.06 and "io" not in memory.pressure(proc)
    info = memory.meminfo(proc)
    assert info["available"] == 40_000_000 * 1024 and info["swap_free"] == 6_000_000 * 1024


def test_each_vms_qemu_is_found_by_its_name_largest_first(tree: tuple[Path, Path]) -> None:
    proc, _ = tree
    assert memory.vms(proc) == [
        {"name": "ci", "rss": 8 * GIB},
        {"name": "app", "rss": 7 * GIB},
    ]


def test_the_user_slice_has_its_cap_kills_and_biggest_jobs(tree: tuple[Path, Path]) -> None:
    proc, root = tree
    found = memory.user_slice(UID, root, proc)
    assert found is not None
    assert (found["current"], found["max"], found["high"], found["oom_kills"]) == (
        14 * GIB,
        40 * GIB,
        36 * GIB,
        6,
    )
    assert [j["name"] for j in found["jobs"]] == ["stats-build.service", "session-9.scope"]
    build = found["jobs"][0]
    assert (build["peak"], build["max"], build["oom_kills"]) == (12 * GIB, 30 * GIB, 1)
    assert build["command"] == "/home/admin/.venv/bin/stats build gold"
    assert found["jobs"][1]["command"] == "python3 search.py"
    assert found["pressure"] == 7.5  # the slice's own memory.pressure, some avg10


def test_no_slice_is_none(tmp_path: Path) -> None:
    assert memory.user_slice(UID, tmp_path, tmp_path) is None


def test_containers_and_gpu_owners(tree: tuple[Path, Path]) -> None:
    proc, root = tree
    (llm,) = memory.containers(root)
    assert (llm["name"], llm["current"], llm["max"]) == ("llm", 3 * GIB, 16 * GIB)
    assert memory.owner("400", proc) == "llm"
    assert memory.owner("200", proc) == "stats-build.service"
    assert memory.owner("999", proc) == ""


def test_nvidia_csv_is_parsed_and_bad_rows_skipped() -> None:
    rows = memory.parse_gpu_apps("400, 11264, /usr/bin/ollama\nNo running processes found\n")
    assert rows == [("400", 11264 << 20, "/usr/bin/ollama")]


def test_no_nvidia_smi_is_none() -> None:
    assert memory.gpu_apps(None) is None


def test_the_reader_puts_it_all_together(tree: tuple[Path, Path]) -> None:
    proc, root = tree
    reader = memory.Reader(UID, proc, root)
    reader.nvidia = None
    got = reader.read()
    assert set(got) == {"pressure", "meminfo", "vms", "containers", "user"}
    assert "gpu_apps" not in got


def test_text_from_processes_is_cleaned() -> None:
    assert memory.clean("a\x1b[2Jb" + "x" * 300) == "a [2Jb" + "x" * 154
