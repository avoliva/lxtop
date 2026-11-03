"""Helpers more than one page uses: number and text formatting, the host's line in the footer,
and drawing lines of text and a moment's time."""

from __future__ import annotations

import time

from lxtop.core import snapshot as sn
from lxtop.core.charts import resample
from lxtop.core.render import clean, human_bytes, speed_short
from lxtop.core.snapshot import Json, as_dict, as_list, num, text
from lxtop.viewer.screen import Screen


def graph_heights(room: int, wanted_below: int) -> tuple[int, int, int]:
    """Heights of the CPU, memory and each network graph: what is left after the list below
    them (at most 16 rows of it), split 4:3:2:2, never under 2 rows each."""
    spare = room - min(max(wanted_below, 4), 16) - 4  # 4 title rows
    unit = max(0, spare) / 11
    return max(2, int(unit * 4)), max(2, int(unit * 3)), max(2, int(unit * 2))


def docker_summary(sample: Json) -> str:
    docker = sample.get("docker")
    if not isinstance(docker, dict):
        return "not installed"
    if docker.get("error"):
        return f"error: {text(docker.get('error'))}"
    states = [text(as_dict(c).get("state")) for c in as_list(docker.get("containers"))]
    return f"{states.count('running')} running, {len(states)} in all"


def bytes_of(data: Json, key: str) -> str:
    return human_bytes(num(data.get(key)))


def used_of(used: object, total: object, percent: bool = True) -> str:
    """ "1.2G/4.0G (30%)" from untrusted numbers."""
    u, t = num(used), num(total)
    out = f"{human_bytes(u)}/{human_bytes(t)}"
    return out + f" ({u / t * 100:.0f}%)" if percent and t else out


def aligned(values: list[float], length: int, width: int) -> list[float]:
    """`values` as the newest end of a `length`-point window, resampled to `width`: series of
    different lengths then share one time axis."""
    padded = [0.0] * max(0, length - len(values)) + values[-length:] if length else []
    return resample(padded, width)


LOST_MARK = "\u00d7"  # in the console font, unlike a bold x


SLOW_MARK = "•"


def bits_text(bits_per_second: float) -> str:
    """An axis label for a chart drawn in bits per second: "100k", "2M"."""
    return speed_short(bits_per_second / 8)


def cores_text(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


def bytes_text(value: float) -> str:
    return human_bytes(value, 0)


def host_line(snap: Json) -> str:
    """The host itself, in one quiet line for the footer."""
    host = sn.host(snap)
    cpu = num(as_dict(host.get("cpu")).get("busy"))
    mem = as_dict(host.get("mem"))
    out = (
        f"host: CPU {cpu * 100:.0f}% · memory {human_bytes(num(mem.get('used')), 0)}"
        f" of {human_bytes(num(mem.get('total')), 0)}"
    )
    for gpu in as_list(host.get("gpus"))[:1]:
        out += f" · GPU {num(as_dict(gpu).get('util')):.0f}%"
    return out


def put_lines(
    s: Screen, lines: list[tuple[str, int]], y: int, x: int, width: int, height: int
) -> int:
    """Draw (text, attribute) lines from row y while they fit above `height`; returns the row
    after the last one drawn."""
    for line, attr in lines:
        if y >= height:
            break
        s.put(y, x, clean(line), attr, width)
        y += 1
    return y


def when(at: float) -> str:
    """A past moment as the pages show it: "Mon 02 Nov 00:09"."""
    return time.strftime("%a %d %b %H:%M", time.localtime(at))
