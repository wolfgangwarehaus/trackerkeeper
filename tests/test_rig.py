"""The rig (trackerkeeper/rig.py) — the probes must run where they can and decline
cleanly where they can't (exit 2, never a crash or a false PASS)."""

from __future__ import annotations

import pytest

from trackerkeeper import rig


def test_pkg_resolves_to_the_package() -> None:
    """_PKG must be the owning package (a fork's rename keeps this correct) —
    and never '__main__' (the `python -m trackerkeeper.rig` pitfall)."""
    assert rig._PKG == "trackerkeeper"


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


def test_baseline_goldens_anchor_to_the_repo_not_the_cwd(tmp_path, monkeypatch):
    """The visual-bump gate's goldens belong to the checkout — running the
    ritual from anywhere else must still find tests/baselines/ (a wrong-CWD
    --update used to bake goldens into $CWD, silently splitting truth)."""
    from trackerkeeper import rig

    monkeypatch.chdir(tmp_path)
    root = rig._repo_root()
    assert (root / "pyproject.toml").is_file()
    assert (root / "tests" / "baselines").is_dir()


def test_grab_env_scrubs_stray_qt_vars(tmp_path, monkeypatch):
    """A shell's QT_SCALE_FACTOR=2 used to double the grab size → 100% false
    drift (or poisoned goldens via --update). Grabs run with QT_* scrubbed."""
    from trackerkeeper import rig

    seen: dict = {}

    def fake_run(cmd, env=None, **kw):
        seen["env"] = env

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(rig.subprocess, "run", fake_run)
    monkeypatch.setenv("QT_SCALE_FACTOR", "2")
    monkeypatch.setenv("QT_FONT_DPI", "144")
    rig._grab_shots(tmp_path)
    assert "QT_SCALE_FACTOR" not in seen["env"]
    assert "QT_FONT_DPI" not in seen["env"]
    assert seen["env"]["QT_QPA_PLATFORM"] == "offscreen"
