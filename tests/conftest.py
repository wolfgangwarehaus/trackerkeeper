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
from PySide6.QtWidgets import QApplication


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
    for w in qapp.topLevelWidgets():
        w.close()
        w.deleteLater()
    qapp.processEvents()
