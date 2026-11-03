"""lxtop: a live terminal dashboard for an LXD host. `lxtop collect` (as root) samples the
host and writes a snapshot; `lxtop view` draws it."""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lxtop.viewer.prefs import Prefs

STATE = "/run/lxtop/state.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lxtop", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    view = sub.add_parser("view", help="show the dashboard (default)")
    view.add_argument("--state", default=STATE, help="snapshot file to read")
    view.add_argument("--glyphs", choices=("auto", "unicode", "console"), default="auto")
    view.add_argument(
        "--theme", default=None, help="the look for this run (t switches); see --list-themes"
    )
    view.add_argument("--list-themes", action="store_true", help="print the looks and stop")
    view.add_argument(
        "--cycle",
        type=float,
        default=None,
        metavar="SECONDS",
        help="for this run, change the look every SECONDS (0 keeps it); o sets it for good",
    )
    view.add_argument(
        "--default-cycle",
        type=float,
        default=300.0,
        metavar="SECONDS",
        help="how often the look changes unless the settings say otherwise (default 300)",
    )
    view.add_argument(
        "--settings", default=None, help="the settings file (default ~/.config/lxtop/…)"
    )
    view.add_argument(
        "--font", default=None, help="on a console, the Terminus font to add graph blocks to"
    )
    # Accepted and ignored, for older launchers.
    view.add_argument("--kiosk", action="store_true", help=argparse.SUPPRESS)
    collect = sub.add_parser("collect", help="sample everything and write the snapshot")
    collect.add_argument("--out", default=STATE)
    collect.add_argument("--interval", type=float, default=2.0)
    collect.add_argument("--history", type=float, default=600.0, help="seconds of history")
    collect.add_argument("--lxd-socket", default=None)
    collect.add_argument("--no-instances", action="store_true", help="skip probes inside instances")
    collect.add_argument(
        "--sudo", action="store_true", help="run lxc exec through sudo -n (testing as non-root)"
    )
    collect.add_argument("--once", action="store_true")
    collect.add_argument("--no-checks", action="store_true", help="skip API, DNS and speed checks")
    collect.add_argument(
        "--user",
        default=os.environ.get("SUDO_USER") or "root",
        help="whose timers, services and jobs to show (default: the user who ran sudo)",
    )
    probe = sub.add_parser("probe", help="print one JSON sample per interval")
    probe.add_argument("--interval", default="2")
    args = parser.parse_args(argv)

    if args.command == "collect":
        from lxtop.collector import collector as c

        settings = c.Settings(
            out=Path(args.out),
            interval=max(0.5, args.interval),
            history_seconds=args.history,
            lxd_socket=args.lxd_socket or c.LXD_SOCKET,
            lxc=c.default_lxc(args.sudo),
            sudo=args.sudo,
            probe_instances=not args.no_instances,
            checks=not args.no_checks,
            user=args.user,
        )
        c.Collector(settings).run(once=args.once)
        return 0
    if args.command == "probe":
        from lxtop.collector import probe as p

        return p.main(["--interval", args.interval])

    from lxtop.core import render
    from lxtop.looks import theme as th
    from lxtop.viewer import app as v
    from lxtop.viewer import font as f

    if getattr(args, "list_themes", False):
        from lxtop.looks import theme as th

        for t in th.THEMES.values():
            print(f"{t.name:<12} {t.label}")
        return 0
    state = Path(getattr(args, "state", STATE))
    choice = getattr(args, "glyphs", "auto")
    font = getattr(args, "font", None)
    opened = f.console_font(Path(font)) if font else contextlib.nullcontext(None)
    with opened as console:
        term = os.environ.get("TERM", "")
        glyphs = render.glyphs_for(term, choice, console_blocks=console is not None)
        prefs = load_prefs(getattr(args, "settings", None), getattr(args, "default_cycle", 300.0))
        name = getattr(args, "theme", None) or prefs.settings.look
        if name not in th.THEMES:
            parser.error(f"no look called {name!r}: " + ", ".join(th.THEMES))
        cycle = getattr(args, "cycle", None)
        if cycle is None:
            cycle = prefs.settings.cycle_seconds
        if cycle < 0:
            parser.error("--cycle: expected 0 (off) or more seconds")
        return v.main(state, glyphs, th.THEMES[name], cycle, font=console, prefs=prefs)


def load_prefs(path: str | None, default_cycle: float) -> Prefs:
    """The saved settings over the defaults; `default_cycle` is the site's own
    (`[monitor] look_cycle_seconds`, passed by the installed `lxtop`)."""
    from lxtop.core import settings as st
    from lxtop.looks import theme as th
    from lxtop.viewer import prefs as pr
    from lxtop.viewer.pages import PAGES

    defaults = st.Settings(cycle_seconds=max(0.0, default_cycle))
    pages = [make().name for make in PAGES]
    file = Path(path) if path else pr.default_path()
    return pr.Prefs.load(file, defaults, th.THEMES, pages)


if __name__ == "__main__":
    sys.exit(main())
