"""TopBar — the app's top bar, which doubles as the titlebar in borderless mode.

A compact strip modelled on the dough shell: a hamburger menu + settings on the
LEFT, then the app title and a status badge; on the right an app-fillable action
slot, the update chip, and (when trackerkeeper owns the chrome) the minimize /
maximize / close window controls. Dragging the bar moves the window
(``startSystemMove``); double-click toggles maximize.

Apps fold their OWN header controls onto this one line instead of a second row:
``insert_title_widget()`` drops a badge beside the title, ``add_action()`` adds a
right-side control (a button, a status label), and ``add_menu_action()`` extends
the hamburger menu. See :class:`~trackerkeeper.dashboard.Dashboard`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel

from trackerkeeper import ui_helpers
from trackerkeeper.bus import AppBus
from trackerkeeper.design_tokens import TYPE_SUBHEAD, type_qss
from trackerkeeper.icon_button import IconButton
from trackerkeeper.icons import icon


class TopBar(ui_helpers.CenteredBar):
    HEIGHT = 44

    def __init__(self, window, *, titlebar_mode: bool, title: str = "trackerkeeper"):
        super().__init__(window)
        self._window = window
        self._titlebar_mode = titlebar_mode
        self._menu_actions: list = []
        self.setFixedHeight(self.HEIGHT)
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(5)

        # ── left: hamburger menu + settings ──
        self.menu_btn = self._chrome_button("menu", "Menu")
        self.menu_btn.clicked.connect(self._open_menu)
        lay.addWidget(self.menu_btn)
        self.settings_btn = self._chrome_button("settings", "Settings")
        self.settings_btn.clicked.connect(lambda: AppBus.get().show_settings.emit())
        lay.addWidget(self.settings_btn)

        # ── title, then a slot right after it for an app badge (update count) ──
        self.title = QLabel(title)
        lay.addWidget(self.title)
        self._title_slot = QHBoxLayout()
        self._title_slot.setContentsMargins(4, 0, 0, 0)
        self._title_slot.setSpacing(6)
        lay.addLayout(self._title_slot)

        lay.addStretch(1)

        # ── right: an app action slot (buttons / a status label) ──
        self._action_slot = QHBoxLayout()
        self._action_slot.setContentsMargins(0, 0, 0, 0)
        self._action_slot.setSpacing(6)
        lay.addLayout(self._action_slot)

        # Update-available chip — invisible until trackerkeeper.updates finds a newer
        # release (AppBus.update_available); Download / What's-new / Dismiss.
        from trackerkeeper.update_chip import UpdateChip

        self.update_chip = UpdateChip(self)
        lay.addWidget(self.update_chip)

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

    # ── the app-fills-the-bar API ──────────────────────────────────────────
    def insert_title_widget(self, widget) -> None:
        """Add a widget immediately after the title (e.g. an update-count badge)."""
        self._title_slot.addWidget(widget)

    def add_action(self, widget) -> None:
        """Append an app control to the right-side slot — left of the update chip
        and the window buttons."""
        self._action_slot.addWidget(widget)

    def add_menu_action(self, label: str, callback) -> None:
        """Add an entry to the hamburger menu (above the always-present Settings)."""
        self._menu_actions.append((label, callback))

    def _open_menu(self) -> None:
        menu = ui_helpers.opaque_menu(self, blur_corner_radius=8)
        for label, cb in self._menu_actions:
            menu.addAction(label).triggered.connect(lambda _=False, c=cb: c())
        if self._menu_actions:
            menu.addSeparator()
        menu.addAction("Settings…").triggered.connect(
            lambda _=False: AppBus.get().show_settings.emit())
        menu.exec(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))

    # ── chrome ─────────────────────────────────────────────────────────────
    def _chrome_button(self, icon_name: str, tip: str) -> IconButton:
        # accessible_name passed explicitly (the preferred pattern) even though
        # the tooltip would fall back to the same string.
        b = IconButton(accessible_name=tip)
        b.setIcon(icon(icon_name))
        b.setToolTip(tip)
        b.setFixedSize(30, 26)  # compact, dough-matched (was 36×32)
        return b

    def restyle(self) -> None:
        """Re-read theme colors (call on AppBus.theme_changed) + refresh icons."""
        self.title.setStyleSheet(f"color: {ui_helpers.TEXT}; {type_qss(TYPE_SUBHEAD)}")
        for name, attr in (
            ("menu", "menu_btn"),
            ("settings", "settings_btn"),
            ("win_minimize", "min_btn"),
            ("win_maximize", "max_btn"),
            ("win_close", "close_btn"),
        ):
            btn = getattr(self, attr, None)
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
