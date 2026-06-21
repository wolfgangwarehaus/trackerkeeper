"""Shared fixtures for the dough test suite.

dough is PySide6 code, so almost every test needs a live ``QApplication``. We
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
    application + organization name ``"dough"`` so the ``QSettings("dough",
    "dough")`` handle resolves identically under test."""
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("dough")
    app.setOrganizationName("dough")
    yield app


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
