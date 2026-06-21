"""Shared fixtures for the dough test suite.

dough is PySide6 code, so almost every test needs a live ``QApplication``.
We deliberately don't depend on ``pytest-qt`` (it's not in the dev extras) — a
hand-rolled, session-scoped ``qapp`` fixture mirrors the offscreen application
``ci.yml``'s boot-smoke already builds, so the suite runs headless and
deterministically both locally and in CI.
"""

from __future__ import annotations

import os

# Force the offscreen platform BEFORE any PySide6 import so the suite never
# needs a display server (parity with the boot-smoke CI step). setdefault so a
# caller can still override (e.g. QT_QPA_PLATFORM=xcb to eyeball a widget).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """The process-wide QApplication, identity-stamped exactly like ``main()``:
    application + organization name ``"dough"`` so the ``QSettings("dough",
    "dough")`` handle (``settings.py`` and ``design_tokens._load_font_scale``)
    resolves identically under test."""
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("dough")
    app.setOrganizationName("dough")
    yield app
    # No teardown: a session QApplication lives for the whole run. Destroying it
    # mid-process can crash later Qt cleanup, and pytest exits the process anyway.
