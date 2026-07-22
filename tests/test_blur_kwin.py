"""The KWin blur backend's plugin-path shim (trackerkeeper/blur/_kwin.py).

A pip-installed PySide6 bundles its own Qt, whose library paths don't include
the distro's /usr/lib/qt6/plugins — so KWindowSystem's platform-integration
plugin (the piece that actually speaks the Wayland blur protocols) is
invisible, and a blur-capable KWin reads as UNSUPPORTED (found live 2026-07-08:
the app painted grainy faux-frost on a real KDE Wayland session with the Blur
effect on). The shim exposes ONLY the kwindowsystem plugin family.
"""

from __future__ import annotations

from pathlib import Path

from trackerkeeper.blur import _kwin


def _reset_shim_state(monkeypatch):
    monkeypatch.setattr(_kwin, "_plugin_path_ensured", False)


def test_shim_exposes_only_the_kwindowsystem_plugins(tmp_path, monkeypatch, qapp):
    """When the plugin dir exists only under a system root, a shim library
    path is added whose tree contains JUST the kf6 kwindowsystem symlink."""
    from PySide6.QtCore import QCoreApplication

    _reset_shim_state(monkeypatch)
    fake_root = tmp_path / "plugins"
    src = fake_root / _kwin._KF_PLUGIN_SUBDIR
    src.mkdir(parents=True)
    (src / "KF6WindowSystemKWaylandPlugin.so").write_bytes(b"")
    monkeypatch.setattr(_kwin, "_SYSTEM_PLUGIN_ROOTS", (str(fake_root),))

    # Hermetic precondition: an earlier test in the session may have installed
    # the REAL shim already — hide any path that makes the plugin discoverable.
    hidden = [
        p for p in QCoreApplication.libraryPaths()
        if (Path(p) / _kwin._KF_PLUGIN_SUBDIR).is_dir()
    ]
    for p in hidden:
        QCoreApplication.removeLibraryPath(p)

    before = list(QCoreApplication.libraryPaths())
    _kwin._ensure_platform_plugin()
    added = [p for p in QCoreApplication.libraryPaths() if p not in before]
    try:
        assert len(added) == 1
        shim = Path(added[0])
        link = shim / _kwin._KF_PLUGIN_SUBDIR
        assert link.is_symlink() and link.resolve() == src.resolve()
        # nothing else is exposed through the shim
        assert [p.name for p in shim.iterdir()] == ["kf6"]
    finally:
        for p in added:
            QCoreApplication.removeLibraryPath(p)
        for p in hidden:
            QCoreApplication.addLibraryPath(p)


def test_shim_is_a_noop_when_already_discoverable(tmp_path, monkeypatch, qapp):
    """Distro PySide6 (shared Qt prefix) already sees the plugin — no shim."""
    from PySide6.QtCore import QCoreApplication

    _reset_shim_state(monkeypatch)
    visible = tmp_path / "visible"
    (visible / _kwin._KF_PLUGIN_SUBDIR).mkdir(parents=True)
    QCoreApplication.addLibraryPath(str(visible))
    try:
        before = list(QCoreApplication.libraryPaths())
        _kwin._ensure_platform_plugin()
        assert list(QCoreApplication.libraryPaths()) == before
    finally:
        QCoreApplication.removeLibraryPath(str(visible))


def test_shim_survives_no_system_roots(monkeypatch, qapp):
    """No distro plugin anywhere → silent no-op (blur stays best-effort)."""
    from PySide6.QtCore import QCoreApplication

    _reset_shim_state(monkeypatch)
    monkeypatch.setattr(_kwin, "_SYSTEM_PLUGIN_ROOTS", ())
    before = list(QCoreApplication.libraryPaths())
    _kwin._ensure_platform_plugin()
    assert list(QCoreApplication.libraryPaths()) == before
