"""run_app's subsystem wiring — autostart reconcile + the notify bus route.

These cover the two P1-leftover wirings without running the event loop: the
helpers are module-level so they're testable in isolation, and every OS-facing
call is monkeypatched (a test must never write a real autostart entry or pop a
real notification).
"""

from __future__ import annotations

import pytest

from dough import app as app_mod
from dough import autostart, notifications
from dough.bus import AppBus


@pytest.fixture
def fresh_bus():
    """A private AppBus instance per test — the process singleton would
    accumulate ``_wire_notifications`` connections across tests (each emit
    would then fan out to every prior test's slot)."""
    saved = AppBus._instance
    AppBus._instance = None
    try:
        yield AppBus.get()
    finally:
        AppBus._instance = saved


def test_reconcile_autostart_reasserts_when_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr(autostart, "is_supported", lambda: True)
    monkeypatch.setattr(autostart, "is_enabled", lambda: True)
    monkeypatch.setattr(autostart, "enable", lambda: calls.append("enable") or True)
    app_mod._reconcile_autostart()
    assert calls == ["enable"]


@pytest.mark.parametrize(
    ("supported", "enabled"),
    [(False, True), (True, False), (False, False)],
)
def test_reconcile_autostart_is_opt_in(monkeypatch, supported, enabled):
    """dough never turns autostart ON — off or unsupported means no enable()."""
    calls = []
    monkeypatch.setattr(autostart, "is_supported", lambda: supported)
    monkeypatch.setattr(autostart, "is_enabled", lambda: enabled)
    monkeypatch.setattr(autostart, "enable", lambda: calls.append("enable") or True)
    app_mod._reconcile_autostart()
    assert calls == []


def test_reconcile_autostart_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("backend exploded")

    monkeypatch.setattr(autostart, "is_supported", boom)
    app_mod._reconcile_autostart()  # must not raise


@pytest.mark.usefixtures("qapp")
def test_notify_signal_reaches_backend(monkeypatch, fresh_bus):
    got = []
    monkeypatch.setattr(
        notifications, "notify", lambda title, body="", **kw: got.append((title, body))
    )
    app_mod._wire_notifications(fresh_bus)
    fresh_bus.notify.emit("Saved", "form.pdf written")
    assert got == [("Saved", "form.pdf written")]


@pytest.mark.usefixtures("qapp")
def test_notify_backend_failure_is_swallowed(monkeypatch, fresh_bus):
    def boom(*a, **kw):
        raise RuntimeError("no notification daemon")

    monkeypatch.setattr(notifications, "notify", boom)
    app_mod._wire_notifications(fresh_bus)
    fresh_bus.notify.emit("still fine", "")  # must not raise through the signal


@pytest.mark.usefixtures("qapp")
def test_settings_dialog_autostart_toggle(monkeypatch):
    """The toggle appears when supported, reads the OS truth, and writes
    enable()/disable() — no QSettings mirror."""
    state = {"enabled": False}
    monkeypatch.setattr(autostart, "is_supported", lambda: True)
    monkeypatch.setattr(autostart, "is_enabled", lambda: state["enabled"])
    monkeypatch.setattr(
        autostart, "enable", lambda: state.__setitem__("enabled", True) or True
    )
    monkeypatch.setattr(
        autostart, "disable", lambda: state.__setitem__("enabled", False) or True
    )

    from dough.settings_dialog import SettingsDialog

    dlg = SettingsDialog()
    try:
        assert hasattr(dlg, "autostart_check")
        assert not dlg.autostart_check.isChecked()
        dlg.autostart_check.setChecked(True)
        assert state["enabled"] is True
        dlg.autostart_check.setChecked(False)
        assert state["enabled"] is False
    finally:
        dlg.deleteLater()


@pytest.mark.usefixtures("qapp")
def test_settings_dialog_hides_autostart_when_unsupported(monkeypatch):
    monkeypatch.setattr(autostart, "is_supported", lambda: False)

    from dough.settings_dialog import SettingsDialog

    dlg = SettingsDialog()
    try:
        assert not hasattr(dlg, "autostart_check")
    finally:
        dlg.deleteLater()
