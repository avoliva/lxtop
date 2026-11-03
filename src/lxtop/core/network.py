"""What the network page says: ping numbers, hiccups grouped into events, and where they are.

Pure: snapshot in, plain words out. The collector's history holds, per tick, the three pings in
milliseconds (LOST for no answer), the share of TCP packets the host sent again, interface
faults, DNS timeouts, and per VM its visitors and failed requests. Comparing the pings places a
hiccup: the router alone is the house, the internet with a healthy router is the provider, and
the service alone (an HTTPS endpoint you depend on) is that service or the route to it.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from lxtop.core import snapshot as sn
from lxtop.core.render import duration
from lxtop.core.snapshot import Json, as_dict, as_list, num, text

LOST = -1.0
SKIPPED = -2.0  # no check of this target at that tick (the service is checked every 10 s)
# (series, what to call it, where a hiccup there is, how far above usual counts as slow in ms)
TARGETS = (
    ("router", "your router", "home", 20.0),
    ("internet", "the internet", "provider", 50.0),
    ("service", "the service", "service", 100.0),
    ("dns_local", "DNS lookups", "dns", 50.0),
)
SLOW_ALWAYS = 1000.0  # ms: a check this slow waited for a resent packet, whatever is usual
RETRANS_BAD = 0.05  # this share of TCP packets sent again is a lossy moment
LOSS_BAD = 0.02


@dataclass(frozen=True)
class PingStats:
    now: float | None  # the newest value, LOST, or None with no data
    median: float  # of answered pings
    worst: float
    lost: int
    count: int

    @property
    def loss(self) -> float:
        return self.lost / self.count if self.count else 0.0


@dataclass(frozen=True)
class Hiccup:
    when: float  # epoch seconds of its first sample
    seconds: float
    samples: int
    what: str
    where: str  # home | provider | service | dns | link | site
    severity: int  # 1 slow, 2 lost or failed


@dataclass(frozen=True)
class Site:
    key: str
    name: str
    per_minute: float
    bad_per_minute: float
    connections: int
    total: int
    history: list[float] = field(default_factory=list)  # requests per second


@dataclass(frozen=True)
class Machine:
    key: str
    name: str
    rx: float
    tx: float
    retrans: float
    rx_history: list[float] = field(default_factory=list)
    tx_history: list[float] = field(default_factory=list)


def net_series(snap: Json, name: str, key: str = "net") -> list[float]:
    return [num(v) for v in as_list(as_dict(sn.history(snap).get(key)).get(name))]


def ping_stats(values: list[float]) -> PingStats:
    checked = [v for v in values if v != SKIPPED]
    answered = [v for v in checked if v >= 0]
    return PingStats(
        now=checked[-1] if checked else None,
        median=statistics.median(answered) if answered else 0.0,
        worst=max(answered, default=0.0),
        lost=len(checked) - len(answered),
        count=len(checked),
    )


def marks(values: list[float], target: str) -> list[str]:
    """Per sample: "lost", "slow" (well above the usual for this target) or ""."""
    floor = next((t[3] for t in TARGETS if t[0] == target), 50.0)
    usual = ping_stats(values).median
    out = []
    for v in values:
        if v == SKIPPED:
            out.append("")
        elif v < 0:
            out.append("lost")
        elif v >= SLOW_ALWAYS or (v > usual + floor and v > usual * 3):
            out.append("slow")
        else:
            out.append("")
    return out


def worst(values: list[float], width: int) -> list[float]:
    """At most `width` points, each its bucket's worst: a lost ping, else the slowest."""
    if width <= 0 or len(values) <= width:
        return list(values)
    size = len(values) / width
    out = []
    for i in range(width):
        bucket = values[int(i * size) : max(int(i * size) + 1, int((i + 1) * size))]
        checked = [v for v in bucket if v != SKIPPED]
        if not checked:
            out.append(SKIPPED)
        else:
            out.append(LOST if any(v < 0 for v in checked) else max(checked))
    return out


def _runs(flags: list[bool]) -> list[tuple[int, int]]:
    """(start, length) of each run of True."""
    found, start = [], None
    for i, flag in enumerate([*flags, False]):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            found.append((start, i - start))
            start = None
    return found


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def hiccups(snap: Json, now: float) -> list[Hiccup]:
    """Every hiccup in the history, newest first."""
    interval = sn.interval(snap) or 2.0
    found: list[Hiccup] = []

    def add(length: int, start: int, size: int, what: str, where: str, severity: int) -> None:
        when = now - (length - start) * interval
        found.append(Hiccup(when, size * interval, size, what, where, severity))

    for name, label, where, _ in TARGETS:
        values = net_series(snap, f"ping_{name}")
        flagged = marks(values, name)
        usual = ping_stats(values).median
        for start, size in _runs([m == "lost" for m in flagged]):
            what = (
                f"{size} pings in a row to {label} lost" if size > 1 else f"1 ping to {label} lost"
            )
            add(len(values), start, size, what, where, 2)
        for start, size in _runs([m == "slow" for m in flagged]):
            peak = max(values[start : start + size])
            what = f"{label} slow: {peak:.0f} ms (usually {usual:.0f} ms)"
            add(len(values), start, size, what[0].upper() + what[1:], where, 1)

    retrans = net_series(snap, "retrans")
    for start, size in _runs([v >= RETRANS_BAD for v in retrans]):
        peak = max(retrans[start : start + size])
        add(len(retrans), start, size, f"{peak * 100:.0f}% of TCP packets sent again", "link", 1)
    faults = net_series(snap, "faults")
    for start, size in _runs([v > 0 for v in faults]):
        count = round(sum(faults[start : start + size]))
        add(
            len(faults),
            start,
            size,
            _plural(count, "network card error", "network card errors"),
            "link",
            1,
        )

    places = [("net", "on the host", "")]
    for inst in sn.instances(snap):
        inst = as_dict(inst)
        places.append(
            (
                text(inst.get("key")),
                f"in the {text(inst.get('name'), '?')} VM",
                text(inst.get("name"), "?"),
            )
        )
    for key, where_text, site in places:
        dns = net_series(snap, "dns_timeouts", key)
        for start, size in _runs([v > 0 for v in dns]):
            count = max(1, round(sum(dns[start : start + size])))
            what = _plural(count, "name lookup", "name lookups") + f" timed out {where_text}"
            add(len(dns), start, size, what, "dns", 1)
        if site:
            bad = net_series(snap, "bad", key)
            for start, size in _runs([v > 0 for v in bad]):
                count = max(1, round(sum(bad[start : start + size]) * interval))
                what = _plural(count, "visitor request", "visitor requests") + f" to {site} failed"
                add(len(bad), start, size, what, "site", 2)
    found.sort(key=lambda h: h.when, reverse=True)
    return found


def _ms(stats: PingStats) -> str:
    if stats.now is None:
        return "?"
    return "lost" if stats.now < 0 else f"{stats.median:.0f} ms"


def diagnosis(snap: Json) -> tuple[str, int]:
    """One sentence on where the trouble is, and how bad: 0 fine, 1 some, 2 real hiccups."""
    interval = sn.interval(snap) or 2.0
    router = ping_stats(net_series(snap, "ping_router"))
    internet = ping_stats(net_series(snap, "ping_internet"))
    api = ping_stats(net_series(snap, "ping_service"))
    if not router.count and not internet.count:
        return "No ping results yet: is the collector running as root?", 1
    span = duration(max(router.count, internet.count) * interval)
    if router.loss >= LOSS_BAD:
        return (
            f"Hiccups inside the house: your router missed {router.loss:.0%} of pings in the last"
            f" {span}. Check the host's cable to it, or restart the router.",
            2,
        )
    if internet.loss >= LOSS_BAD:
        return (
            f"The internet connection is losing packets: {internet.loss:.0%} of pings to 1.1.1.1"
            f" got no answer in the last {span}, while your router answered "
            + ("every one." if not router.lost else "almost every one.")
            + " The problem is past your router, at the internet provider.",
            2,
        )
    slow = marks(net_series(snap, "ping_internet"), "internet").count("slow")
    if slow >= 3:
        return f"The internet was slow {slow} times in the last {span}; the router was fine.", 1
    api_bad = api.lost + marks(net_series(snap, "ping_service"), "service").count("slow")
    if api_bad:
        return (
            f"the service was slow or unreachable {_plural(api_bad, 'time', 'times')} while"
            " the internet was fine: the trouble is on Service's side or the route to it.",
            1,
        )
    dns = [h for h in hiccups(snap, 0.0) if h.where == "dns"]
    if dns:
        return f"The link is fine, but {dns[0].what[0].lower()}{dns[0].what[1:]}.", 1
    parts = [f"router {_ms(router)}", f"internet {_ms(internet)}"]
    if api.count:
        parts.append(f"the service {_ms(api)}")
    return (
        f"The connection looks healthy: {', '.join(parts)}, no lost pings in the last {span}.",
        0,
    )


def site_rows(snap: Json) -> list[Site]:
    """Each VM whose Cloudflare tunnel reports visitors, busiest first."""
    found = []
    for inst in sn.instances(snap):
        inst = as_dict(inst)
        tunnel = as_dict(as_dict(inst.get("probe")).get("tunnel"))
        if not tunnel:
            continue
        key = text(inst.get("key"))
        found.append(
            Site(
                key=key,
                name=text(inst.get("name"), "?"),
                per_minute=num(tunnel.get("req")) * 60,
                bad_per_minute=num(tunnel.get("bad")) * 60,
                connections=int(num(tunnel.get("connections"))),
                total=int(num(tunnel.get("total"))),
                history=net_series(snap, "req", key),
            )
        )
    found.sort(key=lambda s: (-s.per_minute, s.name))
    return found


def machine_rows(snap: Json) -> list[Machine]:
    """Each running VM or container with its traffic, busiest first."""
    found = []
    for inst in sn.instances(snap):
        inst = as_dict(inst)
        if inst.get("running", True) is False:
            continue
        key = text(inst.get("key"))
        tcp = as_dict(as_dict(inst.get("probe")).get("tcp"))
        out = num(tcp.get("out"))
        found.append(
            Machine(
                key=key,
                name=text(inst.get("name"), "?"),
                rx=num(inst.get("rx")),
                tx=num(inst.get("tx")),
                retrans=num(tcp.get("retrans")) / out if out else 0.0,
                rx_history=net_series(snap, "rx", key),
                tx_history=net_series(snap, "tx", key),
            )
        )
    found.sort(key=lambda m: (-(m.rx + m.tx), m.name))
    return found


RANK = {"": 0, "slow": 1, "lost": 2}


def trouble(snap: Json, length: int, width: int) -> list[str]:
    """Per chart column: "lost" if a ping to the internet or the service got no answer then,
    "slow" if one was slow, else "". `length` is the chart's history length; the ping series
    are lined up with its newest end, then squeezed to `width` columns (worst of each)."""
    if width <= 0:
        return []
    combined = [""] * length
    for name in ("internet", "service"):
        flags = marks(net_series(snap, f"ping_{name}"), name)[-length:] if length else []
        offset = length - len(flags)
        for i, flag in enumerate(flags):
            if RANK[flag] > RANK[combined[offset + i]]:
                combined[offset + i] = flag
    if len(combined) <= width:
        return [""] * (width - len(combined)) + combined
    size = len(combined) / width
    out = []
    for i in range(width):
        bucket = combined[int(i * size) : max(int(i * size) + 1, int((i + 1) * size))]
        out.append(max(bucket, key=lambda f: RANK[f]))
    return out
