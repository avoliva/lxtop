"""viewer.prefs: where the settings file is, loading it safely and saving only the changes."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from lxtop.core import settings as st
from lxtop.viewer import prefs as pr

LOOKS = ("default", "matrix")
PAGES = ("services", "network")


def test_the_path_comes_from_the_override_then_xdg_then_home() -> None:
    assert pr.default_path({"LXTOP_SETTINGS": "/x.json", "HOME": "/h"}) == Path("/x.json")
    assert pr.default_path({"XDG_CONFIG_HOME": "/c", "HOME": "/h"}) == Path(
        "/c/lxtop/settings.json"
    )
    assert pr.default_path({"HOME": "/h"}) == Path("/h/.config/lxtop/settings.json")


@pytest.mark.parametrize("text", [None, "not json", "[1, 2]", "\xff"])
def test_a_missing_or_broken_file_loads_the_defaults(tmp_path: Path, text: str | None) -> None:
    path = tmp_path / "s.json"
    if text is not None:
        path.write_text(text)
    defaults = st.Settings(cycle_seconds=90.0)

    assert pr.Prefs.load(path, defaults, LOOKS, PAGES).settings == defaults


def test_saving_writes_only_the_changes_and_loading_reads_them_back(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "s.json"
    defaults = st.Settings()
    prefs = pr.Prefs(path, defaults)

    assert prefs.put(st.Settings(look="matrix")) == ""

    assert json.loads(path.read_text()) == {"version": st.VERSION, "look": "matrix"}
    assert pr.Prefs.load(path, defaults, LOOKS, PAGES).settings.look == "matrix"
    assert [p.name for p in path.parent.iterdir()] == ["s.json"]  # no temporary file left


def test_reset_saves_an_empty_file_and_goes_back_to_the_defaults(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    prefs = pr.Prefs(path, st.Settings(), st.Settings(look="matrix"))

    assert prefs.reset() == ""

    assert prefs.settings == st.Settings()
    assert json.loads(path.read_text()) == {"version": st.VERSION}


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes anywhere")
def test_a_save_that_fails_returns_why_and_keeps_the_settings(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        prefs = pr.Prefs(locked / "s.json", st.Settings())

        why = prefs.put(st.Settings(look="matrix"))

        assert why
        assert prefs.settings.look == "matrix"
        assert not (locked / "s.json").exists()
    finally:
        locked.chmod(0o700)
