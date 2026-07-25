"""Shared fixtures for the trackerkeeper test suite.

trackerkeeper is PySide6 code, so almost every test needs a live ``QApplication``. We
deliberately don't depend on ``pytest-qt`` (it's not in the dev extras) — a
hand-rolled, session-scoped ``qapp`` fixture mirrors the offscreen application
``ci.yml``'s boot-smoke builds, so the suite runs headless and deterministically.
"""

from __future__ import annotations

import os

# Force the offscreen platform BEFORE any PySide6 import so the suite never needs
# a display server (parity with the boot-smoke CI step). setdefault so a caller
# can still override (e.g. QT_QPA_PLATFORM=xcb to eyeball a widget).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QSettings,
    QStandardPaths,
    QThread,
)
from PySide6.QtWidgets import QApplication

# Keep the suite OUT of the maker's real settings — it had been writing straight
# into them. Tests mutate settings through the shipped `get_settings()` handle
# (save_collapsed, the tray toggles, the refresh interval), and that handle keys
# off QSettings(identity.org(), identity.app()) — the SHIPPED path — so a plain
# `pytest` was editing ~/.config/wolfgangwarehaus/trackerkeeper.conf. It really
# did: `collapsed_groups` and `start_minimized` turned up there, written by the
# suite, which means a run could quietly discard the groups you had folded.
#
# Two calls are needed, not one. Test mode redirects PATHS, but QSettings'
# NativeFormat is a different store per platform and only Linux's is a path it
# can reach — macOS uses a CFPreferences .plist and Windows the registry, and
# neither is redirected. IniFormat routes all three through QStandardPaths so
# the redirect is universal. Both must precede any QSettings construction: the
# (org, app) ctor resolves its backend at construction time.
# tests/test_settings_isolation.py is the guard that keeps this honest.
QStandardPaths.setTestModeEnabled(True)
QSettings.setDefaultFormat(QSettings.Format.IniFormat)

# …and pin WHERE the INI lives, because test mode doesn't reach it off Linux.
# QSettings resolves its own base dir and only consults QStandardPaths on Linux
# (via XDG_CONFIG_HOME, which test mode sets); macOS uses a hardcoded ~/.config
# and Windows the raw %APPDATA%, so IniFormat alone still lands on the real
# store in an INI coat. setPath() is Qt's explicit override and the only thing
# that binds all three. Anchored to the test-mode config location so everything
# stays under one qttest tree.
QSettings.setPath(
    QSettings.Format.IniFormat,
    QSettings.Scope.UserScope,
    QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericConfigLocation),
)


@pytest.fixture(scope="session")
def qapp():
    """The process-wide QApplication, identity-stamped exactly like ``main()``:
    application + organization name ``"trackerkeeper"`` so the ``QSettings("trackerkeeper",
    "trackerkeeper")`` handle resolves identically under test."""
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("trackerkeeper")
    app.setOrganizationName("trackerkeeper")
    yield app


@pytest.fixture(autouse=True)
def _isolate_identity():
    """Snapshot and restore the process-global identity (trackerkeeper.identity is module
    state mutated by configure()). Defense-in-depth for the whole identity /
    metadata suite: a test that reidentifies the app and fails — or a future one
    that forgets to restore — would otherwise leak into every later assertion.
    Restores the raw ``_owner`` sentinel too, which configure() cannot reset to
    None. Snapshot via the private globals so the reset is exact."""
    from trackerkeeper import identity

    saved = (identity._org, identity._app, identity._display_name, identity._owner)
    yield
    identity._org, identity._app, identity._display_name, identity._owner = saved


@pytest.fixture(autouse=True)
def _isolate_qt_windows(qapp):
    """Tear down any top-level windows a test creates, right after it runs, so Qt
    state never accumulates across tests. Without this, lingering windows — each
    carrying native blur / event-filter state — pile up and get destroyed in an
    arbitrary order at process exit, which makes PySide6 segfault; the leak is
    order-dependent, so it only bites under shuffled runs (pytest-randomly).
    Deleting per test, while the QApplication is healthy, keeps each test's Qt
    world isolated and the process exit clean."""
    yield
    # A widget can own a RUNNING QThread — Dashboard parents its _RefreshWorker
    # to itself — and destroying one mid-flight aborts the process ("QThread:
    # Destroyed while thread is still running"). Let them finish before the
    # delete below can take their parent out from under them. Caught in dough,
    # where the breadboard's channel probe hit exactly this once the reap landed.
    for w in qapp.topLevelWidgets():
        for t in w.findChildren(QThread):
            if t.isRunning():
                t.quit()          # ends an event loop; a blocking run() ignores it
                t.wait(10_000)    # …so this is what actually makes it safe
    for w in qapp.topLevelWidgets():
        w.close()
        w.deleteLater()
    qapp.processEvents()
    # …and actually REAP them. processEvents() does not deliver DeferredDelete:
    # Qt only reaps those when an event loop unwinds to the nesting level that
    # posted them, and this fixture never runs one. Without this line every
    # deleteLater'd widget in the suite stays alive until the first test that
    # spins a real nested QEventLoop — test_single_instance_forwarding's _spin()
    # — which then destroys hundreds of them at once, in arbitrary order, each
    # carrying native blur / event-filter state. That is exactly the pile-up
    # this fixture exists to prevent, and it aborted the run (SIGABRT on
    # ubuntu/macos, a hard exit on windows) on most pushes. Reaping per test
    # keeps destruction ordered and the process exit clean.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
