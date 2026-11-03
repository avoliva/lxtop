"""The history series the collector records each tick beyond CPU, memory and traffic: pings,
the slow checks step by step, TCP resends, interface faults and DNS timeouts,
and each guest's own numbers."""

from __future__ import annotations

from typing import Any

from lxtop.collector import ping
from lxtop.core import model
from lxtop.core import snapshot as sn
from lxtop.core.snapshot import Json, Snap

# The slow HTTPS checks: job name, ping target, seconds between, host.
API_CHECKS = (("api_service", "service", 10.0, "api.github.com"),)
NET = "net"  # the history key of host-wide network series


STEPS = ("dns", "connect", "tls", "first")


def recent_loss(history: Json, window: int) -> float:
    """Share of the last `window` pings to the internet that got no answer."""
    series = sn.as_list(sn.as_dict(history.get(NET)).get("ping_internet"))[-window:]
    values = [v for v in series if v != ping.SKIPPED]
    return sum(1 for v in values if v == ping.LOST) / len(values) if values else 0.0


VIRTUAL = ("lo", "docker", "br-", "veth", "tap", "virbr", "lxdbr")  # bridges, not the way out


MIN_SEGMENTS = 20.0  # per second; under this one resent packet is noise, not a share


def retrans_share(tcp: Json) -> float:
    """TCP segments sent again, as a share of all sent: the network losing packets."""
    out = sn.num(tcp.get("out"))
    return sn.num(tcp.get("retrans")) / out if out >= MIN_SEGMENTS else 0.0


def dns_per_tick(dns: Json, interval: float) -> float:
    """DNS timeouts per sample. The probe checks every 10 s and repeats that check's count in
    between, so it is spread evenly: summing a series then gives the real number."""
    seconds = sn.num(dns.get("seconds"))
    return sn.num(dns.get("timeouts")) * interval / seconds if seconds > 0 else 0.0


def network_series(
    snapshot: Snap, rounds: dict[str, Any] | None = None
) -> list[tuple[str, str, float]]:
    """(history key, series name, value) for this tick's network readings. `rounds` keeps the
    pinger round each target was last recorded at: a result already recorded is SKIPPED, so a
    check made every few rounds counts once, not once per tick."""
    found: list[tuple[str, str, float]] = []
    rounds = {} if rounds is None else rounds
    for name, result in sn.pings(snapshot).items():
        result = sn.as_dict(result)
        if "ms" not in result:
            continue
        value = sn.num(result.get("ms"), ping.LOST)
        if "round" in result:
            if rounds.get(name) == result["round"]:
                value = ping.SKIPPED
            rounds[name] = result["round"]
        found.append((NET, f"ping_{name}", value))
    for name, result in sn.checks(snapshot).items():
        found += check_series(name, sn.as_dict(result), rounds)
    host = sn.host(snapshot)
    uplinks = sn.uplinks(snapshot)
    faults = sum(
        sn.num(sn.as_dict(n).get("faults"))
        for n in sn.as_list(host.get("net"))
        if sn.text(sn.as_dict(n).get("name")) in uplinks
    )
    found += [
        (NET, "retrans", retrans_share(sn.as_dict(host.get("tcp")))),
        (NET, "faults", faults),
    ]
    interval = sn.interval(snapshot)
    dns = sn.as_dict(host.get("dns"))
    if dns:
        found.append((NET, "dns_timeouts", dns_per_tick(dns, interval)))
    for inst in sn.instances(snapshot):
        inst = sn.as_dict(inst)
        key = sn.text(inst.get("key"))
        sample = sn.as_dict(inst.get("probe"))
        if not key or not sample:
            continue
        found.append((key, "retrans", retrans_share(sn.as_dict(sample.get("tcp")))))
        tunnel = sn.as_dict(sample.get("tunnel"))
        if tunnel:
            found.append((key, "req", sn.num(tunnel.get("req"))))
            found.append((key, "bad", sn.num(tunnel.get("bad"))))
        dns = sn.as_dict(sample.get("dns"))
        if dns:
            found.append((key, "dns_timeouts", dns_per_tick(dns, interval)))
        for item in model.docker_containers(sample):
            if "sandbox_net" in item:
                ckey = model.container_key(key, sn.text(item.get("id")))
                found.append((ckey, "net", sn.num(item.get("sandbox_net"))))
    return found


def check_series(name: str, result: Json, rounds: dict[str, Any]) -> list[tuple[str, str, float]]:
    """A slow check's numbers, once per result: SKIPPED on ticks that bring nothing new."""
    if "round" not in result:
        return []
    fresh = rounds.get(f"check:{name}") != result["round"]
    rounds[f"check:{name}"] = result["round"]

    def value(v: object) -> float:
        return sn.num(v, ping.LOST) if fresh else ping.SKIPPED

    api = next((series for job, series, _, _ in API_CHECKS if job == name), None)
    if api:
        out = [(NET, f"ping_{api}", value(result.get("ms", ping.LOST)))]
        if api == "service":
            out += [(NET, f"step_{api}_{s}", value(result.get(s, ping.LOST))) for s in STEPS]
        return out
    if name.startswith("dns_"):
        return [(NET, f"ping_{name}", value(result.get("ms", ping.LOST)))]
    return []


def guest_numbers(inst: Json) -> None:
    """Fill CPU and memory from the guest's own probe where LXD has none (a VM whose lxd-agent
    is not running reports no memory)."""
    sample = sn.as_dict(inst.get("probe"))
    if not sample:
        return
    if not inst.get("mem_used"):
        mem = sn.as_dict(sample.get("mem"))
        inst["mem_used"] = sn.num(mem.get("used"))
        inst["mem_total"] = inst.get("mem_total") or sn.num(mem.get("total"))
    if not inst.get("cpu_cores"):
        cpu = sn.as_dict(sample.get("cpu"))
        inst["cpu_cores"] = sn.num(cpu.get("busy")) * sn.num(cpu.get("count"))
    if not inst.get("rx") and not inst.get("tx"):
        # LXD reports no traffic for some VMs' NICs: count the guest's own real interfaces.
        nets = [sn.as_dict(n) for n in sn.as_list(sample.get("net"))]
        real = [n for n in nets if not sn.text(n.get("name")).startswith(VIRTUAL)]
        inst["rx"] = sum(sn.num(n.get("rx")) for n in real)
        inst["tx"] = sum(sn.num(n.get("tx")) for n in real)
