"""P1 — the AppWindow extension seams (the prerequisites for the jellytoast
inversion): a top-bar factory hook, a pinned footer slot, and a body-backdrop
paint hook. The final test mimics JellytoastWindow's exact shape — a custom top
bar + a 3-row body (top bar / content / transport footer) + a frost backdrop —
to prove a real app can subclass dough.AppWindow without re-running the chrome.
"""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QLabel, QWidget


@pytest.mark.usefixtures("qapp")
def test_default_top_bar_unchanged() -> None:
    from dough.top_bar import TopBar
    from dough.window import AppWindow

    win = AppWindow(title="dough")
    assert isinstance(win.top_bar, TopBar)  # default hook still builds TopBar


@pytest.mark.usefixtures("qapp")
def test_custom_top_bar_hook() -> None:
    from dough.window import AppWindow

    class _Bar(QWidget):
        def __init__(self, parent=None, titlebar_mode=False):
            super().__init__(parent)
            self.restyled = 0

        def restyle(self):
            self.restyled += 1

    class _Win(AppWindow):
        def _make_top_bar(self, title):
            return _Bar(self, titlebar_mode=self._borderless)

    win = _Win(title="x")
    assert isinstance(win.top_bar, _Bar)
    # the bar sits at row 0 of the root layout
    assert win._root.itemAt(0).widget() is win.top_bar


@pytest.mark.usefixtures("qapp")
def test_set_footer_pins_third_row() -> None:
    from dough.window import AppWindow

    win = AppWindow(title="x")
    win.set_content(QLabel("body"))
    footer = QLabel("transport")
    win.set_footer(footer)

    # root layout is now exactly: top_bar, content_host, footer
    assert win._root.count() == 3
    assert win._root.itemAt(2).widget() is footer
    # only the content host stretches; the footer keeps its natural height
    assert win._root.stretch(1) == 1
    assert win._root.stretch(2) == 0

    # replacing the footer swaps it out, not stacks it
    footer2 = QLabel("transport2")
    win.set_footer(footer2)
    assert win._root.count() == 3
    assert win._root.itemAt(2).widget() is footer2

    win.set_footer(None)
    assert win._root.count() == 2  # cleared


@pytest.mark.usefixtures("qapp")
def test_backdrop_hook_fires_on_paint() -> None:
    from dough.window import AppWindow

    class _Win(AppWindow):
        painted = 0

        def _paint_body_backdrop(self, painter, rect, radius):
            self.painted += 1

    win = _Win(title="x")
    win.set_content(QLabel("body"))
    win.grab()  # force a synchronous paintEvent
    # The backdrop hook only paints in the self-drawn chrome mode — Windows
    # keeps the native frame, so there the hook (correctly) never fires.
    if sys.platform != "win32":
        assert win.painted >= 1


@pytest.mark.usefixtures("qapp")
def test_jellytoast_shaped_window() -> None:
    """The whole inversion pattern at once: a custom music top bar, a stacked
    content area via set_content, a pinned transport bar via set_footer, and a
    frost backdrop — none of which re-implements chrome."""
    from PySide6.QtWidgets import QStackedWidget

    from dough.window import AppWindow

    class _MusicBar(QWidget):
        def __init__(self, parent=None, titlebar_mode=False):
            super().__init__(parent)
            self.restyled = 0

        def restyle(self):
            self.restyled += 1

    class _PlayerWindow(AppWindow):
        def __init__(self):
            super().__init__(title="Jellytoast")
            self.stack = QStackedWidget()
            self.stack.addWidget(QLabel("library"))
            self.stack.addWidget(QLabel("now playing"))
            self.set_content(self.stack)
            self.set_footer(QLabel("◀  ▶  ⏸   now playing…"))

        def _make_top_bar(self, title):
            return _MusicBar(self, titlebar_mode=self._borderless)

        def _paint_body_backdrop(self, painter, rect, radius):
            self.frosted = getattr(self, "frosted", 0) + 1

    win = _PlayerWindow()
    assert isinstance(win.top_bar, _MusicBar)
    assert win._root.count() == 3  # bar / content / footer
    assert isinstance(win._content_layout.itemAt(0).widget(), QStackedWidget)
    win.grab()
    if sys.platform != "win32":  # backdrop hook: self-drawn chrome mode only
        assert getattr(win, "frosted", 0) >= 1
    # theme re-stamp reaches the custom bar via the duck-typed restyle() contract
    win._on_theme_changed()
    assert win.top_bar.restyled >= 1
