"""SettingsDialog — a FrostedDialog demonstrating trackerkeeper's live theme system.

The look controls — theme mode, accent color, font size, font family, and a
square-corners toggle — each write to ``Settings`` and re-stamp the whole
app live via ``AppBus.theme_changed``. Theme mode, accent, and font family
apply instantly; font size and square corners re-stamp for an immediate preview
but only fully land on a relaunch (both bake into ``design_tokens`` at import).
Plus a launch-on-login toggle (shown only where ``trackerkeeper.autostart`` has a
working backend; the OS entry is the source of truth, not QSettings). It's
both a working settings panel and the worked example of the dialog +
Selector + live-theme pattern an app builds on.
"""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel

from trackerkeeper import ui_helpers
from trackerkeeper.bus import AppBus
from trackerkeeper.design_tokens import TYPE_CAPTION, set_square_corners, type_qss
from trackerkeeper.frosted_dialog import FrostedDialog
from trackerkeeper.selector import Selector, selector_qss
from trackerkeeper.settings import get_settings
from trackerkeeper.theme import ACCENT_PRESETS

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
        # The Selector QSS is folded in by _extra_qss() (below), re-stamped with
        # the live accent on every theme_changed — so changing the accent while
        # THIS dialog is open updates its own dropdowns too. (The base already
        # applied it once via register_for_theme in super().__init__.)

        self.content_layout.addWidget(self._label("THEME"))
        self.theme_sel = Selector(accessible_name=self.tr("Theme"))
        for lbl, val in _THEME_MODES:
            self.theme_sel.addItem(lbl, val)
        self._select(self.theme_sel, self.s.theme_mode)
        self.theme_sel.setFixedWidth(256)
        self.theme_sel.currentIndexChanged.connect(self._on_theme_mode)
        self.content_layout.addWidget(self.theme_sel)

        self.content_layout.addWidget(self._label("ACCENT COLOR"))
        self.content_layout.addLayout(self._accent_row())

        # Follow the OS accent — applies now + tracks live changes (see
        # trackerkeeper.system_accent). Picking a swatch above turns it back off.
        self.follow_accent_check = QCheckBox("Follow system accent color")
        self.follow_accent_check.setChecked(self.s.follow_system_accent)
        self.follow_accent_check.toggled.connect(self._on_follow_accent)
        self.content_layout.addWidget(self.follow_accent_check)

        self.content_layout.addWidget(self._label("FONT SIZE"))
        self.font_sel = Selector(accessible_name=self.tr("Font size"))
        for lbl, val in _FONT_SIZES:
            self.font_sel.addItem(lbl, val)
        self._select(self.font_sel, self.s.font_scale)
        self.font_sel.setFixedWidth(256)
        self.font_sel.currentIndexChanged.connect(self._on_font_size)
        self.content_layout.addWidget(self.font_sel)

        # Font family — the app-wide UI text font. Lists installed families that
        # can render Latin text (private + symbol/icon fonts are dropped so a
        # pick can't turn every string into tofu); "System default" = '' = the
        # built-in Inter stack. Applies LIVE (no restart) via the global QSS
        # font stack + app.setFont; SVG icons are never touched.
        self.content_layout.addWidget(self._label("FONT FAMILY"))
        self.family_sel = Selector(accessible_name=self.tr("Font family"))
        self.family_sel.addItem("System default", "")
        from PySide6.QtGui import QFont, QFontDatabase

        latin = QFontDatabase.WritingSystem.Latin
        for fam in QFontDatabase.families():
            if QFontDatabase.isPrivateFamily(fam):
                continue
            if latin not in QFontDatabase.writingSystems(fam):
                continue
            # Preview each family in its own typeface in the dropdown.
            self.family_sel.addItem(fam, fam, font=QFont(fam))
        self._select(self.family_sel, self.s.font_family)
        self.family_sel.setFixedWidth(256)
        self.family_sel.currentIndexChanged.connect(self._on_font_family)
        self.content_layout.addWidget(self.family_sel)

        # Square corners — zero every rounded corner in the UI (windows, tiles,
        # dialogs, buttons, popups); genuinely circular controls (round icon
        # buttons, slider handles) stay round. design_tokens bakes the radii at
        # import, so the re-stamp below is a partial preview and the notice asks
        # for a relaunch to land it everywhere.
        self.content_layout.addWidget(self._label("CORNERS"))
        self.corners_check = QCheckBox("Square corners")
        self.corners_check.setChecked(self.s.square_corners)
        self.corners_check.toggled.connect(self._on_square_corners)
        self.content_layout.addWidget(self.corners_check)

        # Language — the UI language override. "System default" ('') follows
        # the OS locale; explicit picks are bare codes ("es"). Translators
        # install in run_app() before any widget exists, so this is restart-
        # required like Square corners. Options come from i18n.SHIPPED_LANGUAGES
        # so adding a catalog auto-extends the menu; the row is hidden entirely
        # while no catalog ships (bare trackerkeeper) — a picker with only English in
        # it is noise.
        from trackerkeeper.i18n import SHIPPED_LANGUAGES

        if SHIPPED_LANGUAGES:
            self.content_layout.addWidget(self._label("LANGUAGE"))
            self.language_sel = Selector(accessible_name=self.tr("Language"))
            self.language_sel.addItem(self.tr("System default"), "")
            self.language_sel.addItem("English", "en")
            for _code, _en_name, _native in SHIPPED_LANGUAGES:
                self.language_sel.addItem(_native, _code)
            self._select(self.language_sel, self.s.language)
            self.language_sel.setFixedWidth(256)
            self.language_sel.currentIndexChanged.connect(self._on_language)
            self.content_layout.addWidget(self.language_sel)

        # Launch on login — only offered when a platform backend can actually
        # fulfil it (XDG autostart / Run key / StartupTask / LaunchAgent). The
        # OS entry is the source of truth — no QSettings mirror to drift: the
        # box reads is_enabled() and writes enable()/disable() directly.
        from trackerkeeper import autostart

        self.content_layout.addWidget(self._label(self.tr("SYSTEM")))
        if autostart.is_supported():
            self.autostart_check = QCheckBox(self.tr("Launch on login"))
            self.autostart_check.setChecked(autostart.is_enabled())
            self.autostart_check.toggled.connect(self._on_autostart)
            self.content_layout.addWidget(self.autostart_check)

        # Daily update check (trackerkeeper.updates) — the top-bar chip. The toggle is
        # honoured by maybe_check(); auto-updating channels (Store / MAS / AUR)
        # stay silent regardless, so leaving this visible there is harmless.
        self.updates_check = QCheckBox(self.tr("Check for updates"))
        self.updates_check.setChecked(self.s.check_for_updates)
        self.updates_check.toggled.connect(self._on_check_updates)
        self.content_layout.addWidget(self.updates_check)

        # Copy diagnostics — the one-click support report (trackerkeeper.diagnostics):
        # versions, platform/session, theme + verified blur status, a
        # secrets-excluded settings dump, the log tail. Lands on the clipboard.
        from PySide6.QtWidgets import QHBoxLayout as _QHBoxLayout
        from PySide6.QtWidgets import QPushButton

        from trackerkeeper.design_tokens import BTN_SECONDARY, button_qss

        self.diagnostics_btn = QPushButton(self.tr("Copy diagnostics"))
        self.diagnostics_btn.setStyleSheet(button_qss(BTN_SECONDARY))
        self.diagnostics_btn.setToolTip(
            self.tr("Copy a support report (no credentials) to the clipboard")
        )
        self.diagnostics_btn.clicked.connect(self._on_copy_diagnostics)
        _diag_row = _QHBoxLayout()
        _diag_row.addWidget(self.diagnostics_btn)
        _diag_row.addStretch(1)
        self.content_layout.addLayout(_diag_row)

        self._restart_note = QLabel("")
        self._restart_note.setStyleSheet(
            f"color: {ui_helpers.WARN_FG}; {type_qss(TYPE_CAPTION)}"
        )
        self.content_layout.addWidget(self._restart_note)

    # ── Live accent ─────────────────────────────────────────────────────────
    def _extra_qss(self) -> str:
        # a FRESH selector_qss() (reads the current accent) folded in after
        # GLOBAL_STYLE on every restyle — so the dropdown accent borders track
        # a change made in THIS dialog.
        return selector_qss()

    def _restyle(self) -> None:
        super()._restyle()  # GLOBAL_STYLE + selector_qss(), live accent
        # the "Copy diagnostics" button carries a hover-accent of its own.
        if hasattr(self, "diagnostics_btn"):
            from trackerkeeper.design_tokens import BTN_SECONDARY, button_qss

            self.diagnostics_btn.setStyleSheet(button_qss(BTN_SECONDARY))

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
            sw = ui_helpers.CircleSwatch(hex_, diameter=28, hover_ring="#99ffffff")
            sw.setToolTip(name)
            sw.setAccessibleName(name)  # a swatch has no text — announce the color
            sw.clicked.connect(lambda _=False, h=hex_: self._on_accent(h))
            self._swatches.append((sw, hex_))
            row.addWidget(sw)
        row.addStretch(1)
        self._mark_selected_swatch(self.s.accent_color)
        return row

    def _mark_selected_swatch(self, current_hex: str) -> None:
        # CircleSwatch paints the circle + ring with QPainter — QSS circles
        # (border-radius = half size) stroke four arcs whose quadrant seams
        # leave dot artifacts along the path (found live 2026-07-08).
        cur = (current_hex or "").strip().lower()
        for sw, hex_ in self._swatches:
            sw.set_ring("#ffffff" if hex_.lower() == cur else None)

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
        # An explicit pick overrides the OS-follow — reflect that in the toggle
        # (blockSignals so the un-check doesn't fire _on_follow_accent).
        if self.s.follow_system_accent:
            self.s.follow_system_accent = False
            self.follow_accent_check.blockSignals(True)
            self.follow_accent_check.setChecked(False)
            self.follow_accent_check.blockSignals(False)
        self._mark_selected_swatch(hex_)
        self._apply_live()
        AppBus.get().accent_changed.emit(hex_)

    def _on_follow_accent(self, on: bool) -> None:
        self.s.follow_system_accent = bool(on)
        if on:
            # The live watcher only fires on OS-side changes — sync now so the
            # toggle takes effect immediately (async off the GUI thread where
            # the read blocks; the swatch ring updates via theme_changed).
            from trackerkeeper.system_accent import resync_system_accent

            resync_system_accent()

    def _on_font_size(self, _idx: int) -> None:
        self.s.font_scale = self.font_sel.currentData()
        # FONT_SCALE is baked at import (design_tokens) — needs a relaunch.
        self._restart_note.setText("Font size applies after a restart.")

    def _on_font_family(self, _idx: int) -> None:
        self.s.font_family = self.family_sel.currentData() or ""
        # Live preview: recompute the font tokens, re-install the app font, and
        # broadcast theme_changed — reads settings.font_family live, no restart.
        ui_helpers.apply_font_settings_live()

    def _on_square_corners(self, on: bool) -> None:
        self.s.square_corners = bool(on)
        # Keep design_tokens' in-memory flag in lockstep, then re-stamp for an
        # immediate partial preview; the radii baked at import fully re-square on
        # the next launch, so surface the restart notice too.
        set_square_corners(bool(on))
        self._apply_live()
        self._restart_note.setText("Square corners fully applies after a restart.")

    def _on_language(self, _idx: int) -> None:
        # Persist the pick; translators only install at boot (run_app calls
        # i18n.install before any widget exists), so show the restart notice.
        self.s.language = self.language_sel.currentData() or ""
        self._restart_note.setText("Language applies after a restart.")

    def _on_check_updates(self, on: bool) -> None:
        self.s.check_for_updates = bool(on)

    def _on_copy_diagnostics(self) -> None:
        from trackerkeeper import diagnostics

        if diagnostics.copy_to_clipboard():
            # Acknowledge in the dialog's own notice line — no extra dialog.
            self._restart_note.setText(self.tr("Diagnostics copied to clipboard."))
        else:
            self._restart_note.setText(self.tr("Could not copy diagnostics."))

    def _on_autostart(self, on: bool) -> None:
        from trackerkeeper import autostart

        ok = autostart.enable() if on else autostart.disable()
        if on and not ok:
            # The backend refused (no launchable path, sandbox denial) — snap
            # the box back to what the OS actually says rather than lying.
            self.autostart_check.blockSignals(True)
            self.autostart_check.setChecked(autostart.is_enabled())
            self.autostart_check.blockSignals(False)
