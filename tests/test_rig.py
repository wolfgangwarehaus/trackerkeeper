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


# ── the visual-bump gate (baseline) ──────────────────────────────────────────


def _img(tmp_path, name, w=64, h=64, tweak=None):
    from PySide6.QtGui import QColor, QImage, QPainter

    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(QColor(40, 44, 52))
    p = QPainter(img)
    p.fillRect(8, 8, 20, 20, QColor(200, 120, 60))
    if tweak:
        tweak(p)
    p.end()
    path = tmp_path / f"{name}.png"
    img.save(str(path))
    return path


@pytest.mark.usefixtures("qapp")
def test_drift_zero_for_identical_images(tmp_path) -> None:
    a = _img(tmp_path, "a")
    b = _img(tmp_path, "b")
    assert rig._image_drift(a, b) == 0.0


@pytest.mark.usefixtures("qapp")
def test_drift_total_for_size_mismatch(tmp_path) -> None:
    a = _img(tmp_path, "a")
    b = _img(tmp_path, "b", w=32, h=32)
    assert rig._image_drift(a, b) == 1.0


@pytest.mark.usefixtures("qapp")
def test_drift_catches_a_visual_bump(tmp_path) -> None:
    from PySide6.QtGui import QColor

    a = _img(tmp_path, "a")
    b = _img(tmp_path, "b", tweak=lambda p: p.fillRect(30, 30, 24, 24, QColor("red")))
    assert rig._image_drift(a, b) > rig._DRIFT_BUDGET


@pytest.mark.usefixtures("qapp")
def test_drift_tolerates_subtle_noise(tmp_path) -> None:
    """A ±3-per-channel wobble (antialiasing-grade) must NOT read as a bump."""
    from PySide6.QtGui import QColor

    a = _img(tmp_path, "a")
    b = _img(tmp_path, "b", tweak=lambda p: p.fillRect(8, 8, 20, 20, QColor(203, 122, 62)))
    assert rig._image_drift(a, b) <= rig._DRIFT_BUDGET
