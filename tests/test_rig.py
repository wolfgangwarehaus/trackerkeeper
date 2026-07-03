"""The rig (dough/rig.py) — the probes must run where they can and decline
cleanly where they can't (exit 2, never a crash or a false PASS)."""

from __future__ import annotations

import pytest

from dough import rig


def test_pkg_resolves_to_the_package() -> None:
    """_PKG must be the owning package (a fork's rename keeps this correct) —
    and never '__main__' (the `python -m dough.rig` pitfall)."""
    assert rig._PKG == "dough"


def test_probe_declines_off_kde(monkeypatch, capsys) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    assert rig.cmd_probe() == 2
    assert "declining" in capsys.readouterr().out


def test_shot_declines_off_kde(monkeypatch, capsys) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "")
    assert rig.cmd_shot(None) == 2
    assert "declining" in capsys.readouterr().out


def test_cli_requires_a_subcommand() -> None:
    with pytest.raises(SystemExit):
        rig.main([])


def test_boot_smoke_runs_offscreen() -> None:
    """The rig's boot verb IS the CI smoke — prove it end-to-end (subprocess,
    offscreen; ~2s, the single most valuable integration test here)."""
    assert rig.cmd_boot() == 0
