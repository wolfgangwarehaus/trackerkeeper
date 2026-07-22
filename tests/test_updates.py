"""trackerkeeper.updates + trackerkeeper.update_chip — the daily release check and its chip.

Network never leaves the process: _on_finished is driven with a fake reply,
and maybe_check's gates are tested via monkeypatched channel/settings.
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import QSettings

from trackerkeeper import updates
from trackerkeeper.bus import AppBus


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    """A Settings instance backed by a throwaway INI, patched in as the
    process singleton for both trackerkeeper.settings and the updates module."""
    import trackerkeeper.settings as smod

    s = smod.Settings.__new__(smod.Settings)
    s._s = QSettings(str(tmp_path / "store.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(smod, "_inst", s)
    return s


# ── version parsing ───────────────────────────────────────────────────


def test_version_tuple_parses_v_prefix_and_junk():
    assert updates._version_tuple("v0.1.5") == (0, 1, 5)
    assert updates._version_tuple("0.2.0-rc1") == (0, 2, 0)
    assert updates._version_tuple("garbage") == (0,)


def test_is_newer():
    assert updates.is_newer("0.2.0", "0.1.9")
    assert not updates.is_newer("0.1.9", "0.1.9")
    assert not updates.is_newer("0.1.8", "0.1.9")


# ── channel gating ────────────────────────────────────────────────────


def test_channel_env_stamp(monkeypatch):
    monkeypatch.setattr(updates, "is_msix_packaged", lambda: False)
    monkeypatch.setattr(updates, "is_macos_sandboxed", lambda: False)
    monkeypatch.delenv("TRACKERKEEPER_CHANNEL", raising=False)
    assert updates.get_channel() == "source"
    monkeypatch.setenv("TRACKERKEEPER_CHANNEL", "AUR")
    assert updates.get_channel() == "aur"
    assert updates.is_auto_update_channel()


def test_runtime_probe_wins_over_env(monkeypatch):
    monkeypatch.setattr(updates, "is_msix_packaged", lambda: True)
    monkeypatch.setenv("TRACKERKEEPER_CHANNEL", "deb")
    assert updates.get_channel() == "msix"
    assert updates.is_auto_update_channel()


def test_auto_channel_suppresses_even_forced(isolated_settings, monkeypatch):
    monkeypatch.setenv("TRACKERKEEPER_CHANNEL", "aur")
    monkeypatch.setattr(updates, "is_msix_packaged", lambda: False)
    monkeypatch.setattr(updates, "is_macos_sandboxed", lambda: False)
    called = []
    monkeypatch.setattr(updates, "get_qnam", lambda: called.append(1))
    updates.maybe_check(force=True)
    assert called == []  # never even built the request


def test_setting_off_suppresses_automatic_check(isolated_settings, monkeypatch):
    monkeypatch.delenv("TRACKERKEEPER_CHANNEL", raising=False)
    monkeypatch.setattr(updates, "is_msix_packaged", lambda: False)
    monkeypatch.setattr(updates, "is_macos_sandboxed", lambda: False)
    isolated_settings.check_for_updates = False
    called = []
    monkeypatch.setattr(updates, "get_qnam", lambda: called.append(1))
    updates.maybe_check()
    assert called == []
    assert not updates.should_check()


def test_daily_throttle(isolated_settings, monkeypatch):
    import time as _time

    monkeypatch.delenv("TRACKERKEEPER_CHANNEL", raising=False)
    monkeypatch.setattr(updates, "is_msix_packaged", lambda: False)
    monkeypatch.setattr(updates, "is_macos_sandboxed", lambda: False)
    isolated_settings.update_last_check_time = int(_time.time()) - 60
    called = []
    monkeypatch.setattr(updates, "get_qnam", lambda: called.append(1))
    updates.maybe_check()
    assert called == []  # checked a minute ago — throttled


# ── repo resolution ───────────────────────────────────────────────────


def test_releases_api_uses_sidecar_repo():
    # From this checkout the metadata sidecar names wolfgangwarehaus/trackerkeeper.
    assert updates._releases_api() == (
        "https://api.github.com/repos/wolfgangwarehaus/trackerkeeper/releases/latest"
    )


def test_repo_falls_back_to_identity(monkeypatch):
    import trackerkeeper.metadata as md

    def boom():
        raise md.MetadataError("no sidecar in a frozen build")

    monkeypatch.setattr(md, "load", boom)
    from trackerkeeper import identity

    assert updates._repo() == (identity.owner(), identity.app())


# ── download deep-link ────────────────────────────────────────────────


def test_pick_download_url_matches_channel_asset():
    assets = [
        {"name": "app-1.0.deb", "browser_download_url": "https://x/app.deb"},
        {"name": "app-1.0.AppImage", "browser_download_url": "https://x/app.AppImage"},
    ]
    assert updates._pick_download_url(assets, "deb", "https://page") == "https://x/app.deb"
    assert (
        updates._pick_download_url(assets, "appimage", "https://page")
        == "https://x/app.AppImage"
    )
    assert updates._pick_download_url(assets, "source", "https://page") == "https://page"


# ── response handling → the bus ───────────────────────────────────────


class _FakeReply:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode()

    def error(self):
        from PySide6.QtNetwork import QNetworkReply

        return QNetworkReply.NetworkError.NoError

    def readAll(self):
        return self._data

    def deleteLater(self):
        pass


def _release(tag: str) -> dict:
    return {"tag_name": tag, "html_url": "https://x/notes", "assets": []}


def test_newer_release_emits_update_available(qapp, isolated_settings):
    got = []
    AppBus.get().update_available.connect(lambda v, d, n: got.append((v, d, n)))
    try:
        updates._on_finished(_FakeReply(_release("v99.0.0")), force=False)
        assert got == [("99.0.0", "https://x/notes", "https://x/notes")]
    finally:
        AppBus._instance = None  # drop the connected singleton


def test_dismissed_version_stays_silent(qapp, isolated_settings):
    isolated_settings.update_dismissed_version = "99.0.0"
    got = []
    AppBus.get().update_available.connect(lambda v, d, n: got.append(v))
    try:
        updates._on_finished(_FakeReply(_release("v99.0.0")), force=False)
        assert got == []
        # …but a manual "Check now" surfaces it again.
        updates._on_finished(_FakeReply(_release("v99.0.0")), force=True)
        assert got == ["99.0.0"]
    finally:
        AppBus._instance = None


def test_older_release_stays_silent(qapp, isolated_settings):
    got = []
    AppBus.get().update_available.connect(lambda v, d, n: got.append(v))
    try:
        updates._on_finished(_FakeReply(_release("v0.0.0")), force=False)
        assert got == []
    finally:
        AppBus._instance = None


# ── the chip ──────────────────────────────────────────────────────────


def test_chip_shows_on_bus_signal_and_dismiss_remembers(qapp, isolated_settings):
    from trackerkeeper.update_chip import UpdateChip

    chip = UpdateChip()
    try:
        assert not chip.isVisibleTo(None) or not chip.isVisible()
        AppBus.get().update_available.emit("1.2.3", "https://x/dl", "https://x/notes")
        qapp.processEvents()
        assert "1.2.3" in chip.text()
        assert chip._download_url == "https://x/dl"
        chip._dismiss()
        assert isolated_settings.update_dismissed_version == "1.2.3"
        assert not chip.isVisible()
    finally:
        AppBus._instance = None


def test_top_bar_carries_the_chip(qapp):
    from trackerkeeper.top_bar import TopBar
    from trackerkeeper.update_chip import UpdateChip
    from trackerkeeper.window import AppWindow

    win = AppWindow(title="trackerkeeper")
    bar = TopBar(win, titlebar_mode=False)
    try:
        assert isinstance(bar.update_chip, UpdateChip)
        assert not bar.update_chip.isVisible()  # silent until a release lands
    finally:
        AppBus._instance = None
