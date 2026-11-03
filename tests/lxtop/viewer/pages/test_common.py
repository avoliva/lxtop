"""common: the helpers more than one page uses."""

from __future__ import annotations

from lxtop.core.render import speed_short
from lxtop.viewer.pages import common


def test_docker_summary_says_not_installed_when_there_is_no_docker_block() -> None:
    assert common.docker_summary({}) == "not installed"


def test_docker_summary_shows_the_error_text() -> None:
    assert common.docker_summary({"docker": {"error": "boom"}}) == "error: boom"


def test_docker_summary_counts_running_containers() -> None:
    sample = {"docker": {"containers": [{"state": "running"}, {"state": "exited"}]}}

    assert common.docker_summary(sample) == "1 running, 2 in all"


def test_bytes_of_formats_a_missing_number_as_zero() -> None:
    assert common.bytes_of({}, "x") == "0B"


def test_bytes_of_formats_a_number_in_units() -> None:
    assert common.bytes_of({"x": 2048}, "x") == "2.0K"


def test_aligned_puts_a_short_series_at_the_newest_end() -> None:
    assert common.aligned([5.0, 7.0], 4, 4) == [0.0, 0.0, 5.0, 7.0]
    assert common.aligned([1.0], 0, 3) == []


def test_axis_labels_are_short() -> None:
    assert common.cores_text(2.50) == "2.5" and common.cores_text(0) == "0"
    assert common.bits_text(8e6) == speed_short(1e6)
    assert common.bytes_text(2**30) == "1G"


def test_the_host_line_names_cpu_memory_and_the_first_gpu() -> None:
    snap = {
        "host": {
            "cpu": {"busy": 0.25},
            "mem": {"used": 2**30, "total": 4 * 2**30},
            "gpus": [{"util": 40}, {"util": 99}],
        }
    }

    assert common.host_line(snap) == "host: CPU 25% · memory 1G of 4G · GPU 40%"
    assert common.host_line({}) == "host: CPU 0% · memory 0B of 0B"
