"""RTL smoke — the whole chrome builds mirrored without error.

Qt reverses every box/grid layout automatically when layoutDirection is
RightToLeft (an Arabic/Hebrew locale flips it at boot). trackerkeeper's kit avoids
hardcoded left/right positioning, so mirroring should be free — this suite
forces RTL app-wide, boots the real window + kit pieces, and keeps it that
way: a future widget that positions with absolute left/right maths tends to
throw or lay out degenerately here.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


@pytest.fixture()
def rtl(qapp):
    """Force app-wide RightToLeft for the test; restore after (the qapp is
    session-scoped — leaking RTL would mirror every later test)."""
    saved = qapp.layoutDirection()
    qapp.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    yield qapp
    qapp.setLayoutDirection(saved)


def test_main_window_builds_rtl(rtl):
    from trackerkeeper.top_bar import TopBar
    from trackerkeeper.window import AppWindow

    win = AppWindow(title="trackerkeeper")
    win.set_content(QLabel("مرحبا"))
    win.resize(640, 480)
    win.show()
    rtl.processEvents()

    # Sanity: the chrome exists and inherited the mirrored direction.
    assert isinstance(win.top_bar, TopBar)
    assert win.top_bar.layoutDirection() == Qt.LayoutDirection.RightToLeft
    # The top bar laid out (no zero-size collapse from geometry maths).
    assert win.top_bar.width() > 0
    # Window controls landed inside the bar — a hardcoded-x placement would
    # typically push them out of the mirrored geometry.
    for name in ("settings_btn", "min_btn", "max_btn", "close_btn"):
        btn = getattr(win.top_bar, name, None)
        if btn is not None:
            assert win.top_bar.rect().contains(btn.geometry().center())


def test_selector_builds_rtl(rtl):
    from trackerkeeper.selector import Selector, selector_qss

    sel = Selector()
    for label in ("uno", "dos", "tres"):
        sel.addItem(label, label)
    sel.resize(200, 32)
    sel.show()
    rtl.processEvents()
    # The QSS block flips its chevron reserve + text-align under RTL.
    qss = selector_qss()
    assert "padding: 6px 12px 6px 32px" in qss
    assert "text-align: right" in qss
    # Paint path runs with the mirrored chevron position without error.
    sel.grab()


def test_frosted_dialog_builds_rtl(rtl):
    from trackerkeeper.frosted_dialog import FrostedMessageDialog

    dlg = FrostedMessageDialog(None, title="عنوان", text="نص الرسالة")
    dlg.show()
    rtl.processEvents()
    assert dlg.layoutDirection() == Qt.LayoutDirection.RightToLeft
    dlg.close()
