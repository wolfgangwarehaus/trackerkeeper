"""TopBar — the app's top bar, which doubles as the titlebar in borderless mode.

A generic strip: an app title on the left, a settings button on the right, and
(when dough owns the chrome) the minimize / maximize / close window controls.
Dragging the bar moves the window (``startSystemMove``); double-click toggles
maximize. An app subclasses or replaces this freely — it's deliberately thin.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel

from dough import ui_helpers
from dough.bus import AppBus
from dough.design_tokens import TYPE_SUBHEAD, type_qss
from dough.icon_button import IconButton
from dough.icons import icon


class TopBar(ui_helpers.CenteredBar):
    HEIGHT = 48

    def __init__(self, window, *, titlebar_mode: bool, title: str = "dough"):
        super().__init__(window)
        self._window = window
        self._titlebar_mode = titlebar_mode
        self.setFixedHeight(self.HEIGHT)
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 6, 10, 6)
        lay.setSpacing(6)

        self.title = QLabel(title)
        lay.addWidget(self.title)
        lay.addStretch(1)

        self.settings_btn = self._chrome_button("settings", "Settings")
        self.settings_btn.clicked.connect(lambda: AppBus.get().show_settings.emit())
        lay.addWidget(self.settings_btn)

        # Window controls only when we own the titlebar (borderless / frameless).
        if titlebar_mode:
            self.min_btn = self._chrome_button("win_minimize", "Minimize")
            self.min_btn.clicked.connect(window.showMinimized)
            self.max_btn = self._chrome_button("win_maximize", "Maximize")
            self.max_btn.clicked.connect(self._toggle_max)
            self.close_btn = self._chrome_button("win_close", "Close")
            self.close_btn.clicked.connect(window.close)
            for b in (self.min_btn, self.max_btn, self.close_btn):
                lay.addWidget(b)

        self.restyle()

    def _chrome_button(self, icon_name: str, tip: str) -> IconButton:
        b = IconButton()
        b.setIcon(icon(icon_name))
        b.setToolTip(tip)
        b.setFixedSize(36, 32)
        return b

    def restyle(self) -> None:
        """Re-read theme colors (call on AppBus.theme_changed) + refresh icons."""
        self.title.setStyleSheet(f"color: {ui_helpers.TEXT}; {type_qss(TYPE_SUBHEAD)}")
        for name, btn in (
            ("settings", getattr(self, "settings_btn", None)),
            ("win_minimize", getattr(self, "min_btn", None)),
            ("win_maximize", getattr(self, "max_btn", None)),
            ("win_close", getattr(self, "close_btn", None)),
        ):
            if btn is not None:
                btn.setIcon(icon(name))

    def _toggle_max(self) -> None:
        w = self._window
        w.showNormal() if w.isMaximized() else w.showMaximized()

    # ── Drag-to-move / double-click maximize (titlebar) ────────────────────
    def mousePressEvent(self, e):
        if self._titlebar_mode and e.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
                return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self._titlebar_mode and e.button() == Qt.MouseButton.LeftButton:
            self._toggle_max()
            return
        super().mouseDoubleClickEvent(e)
