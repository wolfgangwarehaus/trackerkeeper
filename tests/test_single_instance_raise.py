"""``force_foreground`` — the one seam every "come forward" path goes through.

The regression this guards: it used to return immediately on anything but
Windows, doing the show/raise/activate nowhere. Every caller that had NOT
pre-shown the window (the single-instance ping, ``AppBus.open_main_window``)
therefore did nothing at all — double-clicking the desktop icon while the app
sat in the tray span a launcher spinner and never brought the window up. The
test bridge's "raise" command masked it by calling show() itself first.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from trackerkeeper.single_instance import force_foreground


@pytest.fixture()
def win(qapp):
    w = QWidget()
    w.resize(320, 240)
    yield w
    w.close()
    w.deleteLater()


def test_shows_a_hidden_window(win):
    """The tray case: closed to tray means hide(), and raise_()/
    activateWindow() do nothing to an unmapped window."""
    win.show()
    win.hide()
    assert not win.isVisible()

    force_foreground(win)

    assert win.isVisible()


def test_unminimizes(win):
    win.show()
    win.setWindowState(Qt.WindowState.WindowMinimized)
    assert win.isMinimized()

    force_foreground(win)

    assert not win.isMinimized()
    assert win.isVisible()


def test_keeps_a_maximized_window_maximized(win):
    """Un-minimize by clearing the Minimized bit, not showNormal() — a window
    maximized before it went to the tray comes back maximized."""
    win.showMaximized()
    win.setWindowState(Qt.WindowState.WindowMaximized | Qt.WindowState.WindowMinimized)

    force_foreground(win)

    assert not win.isMinimized()
    assert win.isMaximized()


def test_never_raises_on_a_dead_window(qapp):
    """Best-effort contract: it's wired to signals that can outlive the
    window, and a throw there would tear down the emitting path."""
    class Exploding:
        def isMinimized(self):
            raise RuntimeError("C++ object already deleted")

    force_foreground(Exploding())  # must not raise
