"""Where the viewer keeps its settings: `$LXTOP_SETTINGS`, else
`$XDG_CONFIG_HOME/lxtop/settings.json`, else `~/.config/lxtop/settings.json`.
Each person who runs `lxtop` has their own. The file is JSON holding only what differs
from the defaults (`core/settings.py`); it is written whole to a temporary file and renamed, so
a crash never leaves half a file."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Collection, Mapping
from pathlib import Path

from lxtop.core import settings as st


def default_path(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if env.get("LXTOP_SETTINGS"):
        return Path(env["LXTOP_SETTINGS"])
    base = Path(env["XDG_CONFIG_HOME"]) if env.get("XDG_CONFIG_HOME") else None
    if base is None:
        base = Path(env.get("HOME") or Path.home()) / ".config"
    return base / "lxtop" / "settings.json"


class Prefs:
    """The defaults this run started from, the saved settings on top of them, and the file."""

    def __init__(self, path: Path, defaults: st.Settings, saved: st.Settings | None = None):
        self.path = path
        self.defaults = defaults
        self.settings = saved if saved is not None else defaults

    @classmethod
    def load(
        cls, path: Path, defaults: st.Settings, looks: Collection[str], pages: Collection[str]
    ) -> Prefs:
        """The saved settings, or the defaults when the file is missing or unreadable."""
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError, UnicodeDecodeError):
            data = {}
        saved = st.merge(defaults, data, looks, pages) if isinstance(data, dict) else defaults
        return cls(path, defaults, saved)

    def put(self, settings: st.Settings) -> str:
        """Keep `settings` and save them; "" when saved, else why not (the app shows it)."""
        self.settings = settings
        return self.save()

    def reset(self) -> str:
        self.settings = self.defaults
        return self.save()

    def save(self) -> str:
        text = json.dumps(st.diff(self.defaults, self.settings), indent=2) + "\n"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".settings.")
            try:
                with os.fdopen(fd, "w") as out:
                    out.write(text)
                Path(tmp).replace(self.path)
            except BaseException:
                Path(tmp).unlink()
                raise
        except OSError as exc:
            return exc.strerror or str(exc)
        return ""
