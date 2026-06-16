"""SettingsDialog — a FrostedDialog demonstrating dough's live theme system.

Three controls — theme mode, accent color, font size — each writing to
``Settings`` and re-stamping the whole app live via ``AppBus.theme_changed``
(font size needs a relaunch; everything else applies instantly). It's both a
working settings panel and the worked example of the dialog + Selector +
live-theme pattern an app builds on.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from dough import ui_helpers
from dough.bus import AppBus
from dough.design_tokens import TYPE_CAPTION, type_qss
from dough.frosted_dialog import FrostedDialog
from dough.selector import Selector, selector_qss
from dough.settings import get_settings
from dough.theme import ACCENT_PRESETS

_THEME_MODES = [
    ("Auto (follow OS)", "auto"),
    ("Frosted Dark", "frosted_dark"),
    ("Frosted Light", "frosted_light"),
    ("Dark", "dark"),
    ("Light", "light"),
]
_FONT_SIZES = [
    ("Default", "default"),
    ("Small", "small"),
    ("Large", "large"),
    ("Largest", "largest"),
]


class SettingsDialog(FrostedDialog):
    def __init__(self, parent=None):
        super().__init__(parent, title="Settings", icon_name="settings", min_width=420)
        self.s = get_settings()
        # Merge the Selector QSS into the dialog's sheet so the dropdowns style.
        self.setStyleSheet(self.styleSheet() + selector_qss())

        self.content_layout.addWidget(self._label("THEME"))
        self.theme_sel = Selector()
        for lbl, val in _THEME_MODES:
            self.theme_sel.addItem(lbl, val)
        self._select(self.theme_sel, self.s.theme_mode)
        self.theme_sel.setFixedWidth(256)
        self.theme_sel.currentIndexChanged.connect(self._on_theme_mode)
        self.content_layout.addWidget(self.theme_sel)

        self.content_layout.addWidget(self._label("ACCENT COLOR"))
        self.content_layout.addLayout(self._accent_row())

        self.content_layout.addWidget(self._label("FONT SIZE"))
        self.font_sel = Selector()
        for lbl, val in _FONT_SIZES:
            self.font_sel.addItem(lbl, val)
        self._select(self.font_sel, self.s.font_scale)
        self.font_sel.setFixedWidth(256)
        self.font_sel.currentIndexChanged.connect(self._on_font_size)
        self.content_layout.addWidget(self.font_sel)
        self._restart_note = QLabel("")
        self._restart_note.setStyleSheet(
            f"color: {ui_helpers.WARN_FG}; {type_qss(TYPE_CAPTION)}"
        )
        self.content_layout.addWidget(self._restart_note)

    # ── Builders ───────────────────────────────────────────────────────────
    def _label(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setStyleSheet(f"color: {ui_helpers.TEXT_DIM}; {type_qss(TYPE_CAPTION)}")
        return lab

    def _accent_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        self._swatches = []
        for name, hex_ in ACCENT_PRESETS:
            sw = QPushButton()
            sw.setToolTip(name)
            sw.setFixedSize(28, 28)
            sw.setCursor(self.cursor())
            sw.setStyleSheet(self._swatch_qss(hex_, selected=False))
            sw.clicked.connect(lambda _=False, h=hex_: self._on_accent(h))
            self._swatches.append((sw, hex_))
            row.addWidget(sw)
        row.addStretch(1)
        self._mark_selected_swatch(self.s.accent_color)
        return row

    @staticmethod
    def _swatch_qss(hex_: str, selected: bool) -> str:
        border = "2px solid #ffffff" if selected else "2px solid transparent"
        return (
            f"QPushButton{{background:{hex_};border-radius:14px;{border};}}"
            f"QPushButton:hover{{border:2px solid rgba(255,255,255,0.6);}}"
        )

    def _mark_selected_swatch(self, current_hex: str) -> None:
        cur = (current_hex or "").strip().lower()
        for sw, hex_ in self._swatches:
            sw.setStyleSheet(self._swatch_qss(hex_, selected=hex_.lower() == cur))

    @staticmethod
    def _select(sel: Selector, value: str) -> None:
        idx = sel.findData(value)
        sel.setCurrentIndex(idx if idx >= 0 else 0)

    # ── Handlers ───────────────────────────────────────────────────────────
    def _apply_live(self) -> None:
        ui_helpers.refresh_theme()
        AppBus.get().theme_changed.emit()

    def _on_theme_mode(self, _idx: int) -> None:
        self.s.theme_mode = self.theme_sel.currentData()
        self._apply_live()

    def _on_accent(self, hex_: str) -> None:
        self.s.accent_color = hex_
        self._mark_selected_swatch(hex_)
        self._apply_live()
        AppBus.get().accent_changed.emit(hex_)

    def _on_font_size(self, _idx: int) -> None:
        self.s.font_scale = self.font_sel.currentData()
        # FONT_SCALE is baked at import (design_tokens) — needs a relaunch.
        self._restart_note.setText("Font size applies after a restart.")
