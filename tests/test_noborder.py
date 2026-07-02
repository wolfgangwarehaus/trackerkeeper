"""Tests for dough.noborder — the KWin ``noborder`` main-window rule.

The package picks its backend at import time via a runtime call to
``dough.platform_compat.is_kde_wayland()``. On KDE Wayland the ``_kwin`` backend
shells out to kwriteconfig/kreadconfig/qdbus to manage a window rule in
kwinrulesrc. Everywhere else the unsupported backend is a silent no-op.

All shell-outs and the QSettings UUID store are mocked so the suite runs on any
host without touching the real config.
"""

from __future__ import annotations

import importlib
import subprocess
import sys

import pytest

from dough import identity


def _reload_noborder():
    """Drop and re-import the package so its import-time ``is_kde_wayland()``
    gate re-evaluates against current mocks."""
    for mod_name in (
        "dough.noborder",
        "dough.noborder._kwin",
        "dough.noborder._unsupported",
    ):
        sys.modules.pop(mod_name, None)
    return importlib.import_module("dough.noborder")


def _force_kde_wayland(monkeypatch, value: bool):
    import dough.platform_compat as pc

    monkeypatch.setattr(pc, "is_kde_wayland", lambda: value)


class _FakeQSettings:
    """In-memory QSettings stand-in so the rule-UUID store never touches the
    real user config. Shared dict keyed like QSettings' flat namespace."""

    _store: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    def value(self, key, default="", type=str):
        return self._store.get(key, default)

    def setValue(self, key, val):
        self._store[key] = val

    def remove(self, key):
        self._store.pop(key, None)


@pytest.fixture(autouse=True)
def _fresh_fake_settings():
    _FakeQSettings._store = {}
    yield
    _FakeQSettings._store = {}


@pytest.fixture(autouse=True)
def _restore_noborder_module():
    """Leave a fresh import after each test so the next gets a clean module +
    backend reference."""
    yield
    for mod_name in (
        "dough.noborder",
        "dough.noborder._kwin",
        "dough.noborder._unsupported",
    ):
        sys.modules.pop(mod_name, None)


# ── backend selection ─────────────────────────────────────────────────


def test_imports_cleanly_on_kde_wayland(monkeypatch):
    _force_kde_wayland(monkeypatch, True)
    noborder = _reload_noborder()
    assert hasattr(noborder, "install_main_window_noborder")
    assert hasattr(noborder, "remove_main_window_noborder")
    assert hasattr(noborder, "is_supported")
    assert hasattr(noborder, "diagnose")


def test_imports_cleanly_off_kde_wayland(monkeypatch):
    _force_kde_wayland(monkeypatch, False)
    noborder = _reload_noborder()
    assert hasattr(noborder, "install_main_window_noborder")
    assert hasattr(noborder, "remove_main_window_noborder")


def test_kwin_backend_selected_on_kde_wayland(monkeypatch):
    _force_kde_wayland(monkeypatch, True)
    noborder = _reload_noborder()
    assert noborder._backend.__name__ == "dough.noborder._kwin"


def test_unsupported_backend_selected_off_kde_wayland(monkeypatch):
    _force_kde_wayland(monkeypatch, False)
    noborder = _reload_noborder()
    assert noborder._backend.__name__ == "dough.noborder._unsupported"


# ── _unsupported backend ──────────────────────────────────────────────


def test_unsupported_methods_are_silent_noops(monkeypatch):
    _force_kde_wayland(monkeypatch, False)
    noborder = _reload_noborder()
    assert noborder.is_supported() is False
    assert noborder.install_main_window_noborder() is False
    assert noborder.remove_main_window_noborder() is False
    d = noborder.diagnose()
    assert d["backend"] == "unsupported"
    assert d["is_supported"] is False


# ── is_supported ──────────────────────────────────────────────────────


def test_is_supported_false_when_kde_tools_missing(monkeypatch):
    _force_kde_wayland(monkeypatch, True)
    noborder = _reload_noborder()
    from dough.noborder import _kwin

    monkeypatch.setattr(_kwin.shutil, "which", lambda _: None)
    assert noborder.is_supported() is False


def test_is_supported_true_when_kde_tools_present(monkeypatch):
    _force_kde_wayland(monkeypatch, True)
    noborder = _reload_noborder()
    from dough.noborder import _kwin

    monkeypatch.setattr(_kwin.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    assert noborder.is_supported() is True


# ── install / remove ──────────────────────────────────────────────────


def _wire_kwin(monkeypatch):
    from dough.noborder import _kwin

    monkeypatch.setattr(_kwin.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(_kwin, "QSettings", _FakeQSettings)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(_kwin.subprocess, "run", fake_run)
    return _kwin, calls


def test_install_returns_false_when_tools_missing(monkeypatch):
    _force_kde_wayland(monkeypatch, True)
    noborder = _reload_noborder()
    from dough.noborder import _kwin

    monkeypatch.setattr(_kwin.shutil, "which", lambda _: None)
    assert noborder.install_main_window_noborder() is False


def test_install_shells_out_and_reconfigures(monkeypatch):
    _force_kde_wayland(monkeypatch, True)
    noborder = _reload_noborder()
    _kwin, calls = _wire_kwin(monkeypatch)

    assert noborder.install_main_window_noborder() is True
    assert any("kwriteconfig6" in c[0] or "kwriteconfig5" in c[0] for c in calls)
    assert any("qdbus" in c[0] and "reconfigure" in c for c in calls)


def test_install_matches_on_wmclass_not_title(monkeypatch):
    """dough scopes the rule to the wmclass (identity.app()) with NO title match
    — so the window title is free to change (e.g. a document name). Assert a
    wmclass write with the app slug, and that no `title`/`titlematch` key is
    ever written."""
    _force_kde_wayland(monkeypatch, True)
    noborder = _reload_noborder()
    _kwin, calls = _wire_kwin(monkeypatch)
    noborder.install_main_window_noborder()

    wmclass_writes = [c for c in calls if len(c) >= 2 and c[-2] == "wmclass"]
    assert wmclass_writes and all(c[-1] == identity.app() for c in wmclass_writes)
    # No title-based matching at all.
    assert not any(len(c) >= 2 and c[-2] in ("title", "titlematch") for c in calls)


def test_install_writes_force_noborder(monkeypatch):
    """noborder=true + noborderrule=2 (Force) — KWin draws no decoration."""
    _force_kde_wayland(monkeypatch, True)
    noborder = _reload_noborder()
    _kwin, calls = _wire_kwin(monkeypatch)
    noborder.install_main_window_noborder()

    noborder_writes = [c for c in calls if len(c) >= 2 and c[-2] == "noborder"]
    assert noborder_writes and all(c[-1] == "true" for c in noborder_writes)
    rule_writes = [c for c in calls if len(c) >= 2 and c[-2] == "noborderrule"]
    assert rule_writes and all(c[-1] == "2" for c in rule_writes)


def test_install_is_idempotent_reuses_uuid(monkeypatch):
    """A second install must reuse the stored UUID, not mint a new rule."""
    _force_kde_wayland(monkeypatch, True)
    noborder = _reload_noborder()
    _kwin, _calls = _wire_kwin(monkeypatch)

    noborder.install_main_window_noborder()
    first = _FakeQSettings._store.get(_kwin._MAIN_NOBORDER_KEY)
    noborder.install_main_window_noborder()
    second = _FakeQSettings._store.get(_kwin._MAIN_NOBORDER_KEY)
    assert first and first == second


def test_remove_false_when_nothing_installed(monkeypatch):
    _force_kde_wayland(monkeypatch, True)
    noborder = _reload_noborder()
    _kwin, _calls = _wire_kwin(monkeypatch)
    # Nothing stored → clean short-circuit.
    assert noborder.remove_main_window_noborder() is False


def test_remove_deletes_stored_rule(monkeypatch):
    _force_kde_wayland(monkeypatch, True)
    noborder = _reload_noborder()
    _kwin, calls = _wire_kwin(monkeypatch)

    noborder.install_main_window_noborder()
    assert _kwin._MAIN_NOBORDER_KEY in _FakeQSettings._store
    calls.clear()
    assert noborder.remove_main_window_noborder() is True
    assert _kwin._MAIN_NOBORDER_KEY not in _FakeQSettings._store
    # A delete pass (--delete) + a reconfigure were issued.
    assert any("--delete" in c for c in calls)
    assert any("qdbus" in c[0] and "reconfigure" in c for c in calls)


def test_install_survives_subprocess_failure(monkeypatch):
    """A FileNotFoundError from subprocess.run inside a helper must be
    swallowed; install still reports True because is_supported gated past."""
    _force_kde_wayland(monkeypatch, True)
    noborder = _reload_noborder()
    from dough.noborder import _kwin

    monkeypatch.setattr(_kwin.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(_kwin, "QSettings", _FakeQSettings)

    def raising_run(cmd, **kwargs):
        raise FileNotFoundError("tool vanished mid-call")

    monkeypatch.setattr(_kwin.subprocess, "run", raising_run)
    # Must not raise.
    noborder.install_main_window_noborder()


# ── diagnose ──────────────────────────────────────────────────────────


def test_diagnose_on_kwin_backend_reports_wmclass(monkeypatch):
    _force_kde_wayland(monkeypatch, True)
    noborder = _reload_noborder()
    from dough.noborder import _kwin

    monkeypatch.setattr(_kwin.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    d = noborder.diagnose()
    assert d["backend"] == "kwin"
    assert d["is_supported"] is True
    assert d["rule_wmclass"] == identity.app()
