"""Update-available chip — a small rounded button in the top bar's right
column, shown only when ``trackerkeeper/updates.py`` finds a newer release on a
manual install channel.

Hidden until ``AppBus.update_available`` fires; then it reads "Update 0.1.6"
and a click opens a small menu — **Download** (deep-linked to the right asset),
**What's new** (release notes), **Dismiss** (hide + remember the version so it
doesn't re-nag). Subtle accent-pill styling with live-accent refresh, matching
the top bar it sits in.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import QPushButton

from trackerkeeper import ui_helpers
from trackerkeeper.bus import AppBus
from trackerkeeper.design_tokens import TYPE_CAPTION, rad, type_qss
from trackerkeeper.ui_helpers import opaque_menu


class UpdateChip(QPushButton):
    """Compact "a newer version is out" pill. Subtle by design — present but
    not shouting — so the top bar stays calm."""

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setObjectName("doughUpdateChip")
        # Announce even while hidden/empty (the a11y gate walks constructed
        # surfaces); once a release lands, the visible "Update x.y.z" text and
        # the versioned tooltip carry the detail.
        self.setAccessibleName(self.tr("Update available"))
        self.setFixedHeight(24)
        self.setFlat(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._version = ""
        self._download_url = ""
        self._notes_url = ""
        self._menu = None  # kept alive across a non-blocking popup()
        self._apply_style()
        self.clicked.connect(self._open_menu)
        self.setVisible(False)

        bus = AppBus.get()
        bus.update_available.connect(self._on_update_available)
        # Live-accent: rebuild the stylesheet when the accent changes.
        bus.theme_changed.connect(self._apply_style)

    # ── Style ───────────────────────────────────────────────────────────
    def _apply_style(self, *_: object) -> None:
        r, g, b = self._accent_rgb()
        self.setStyleSheet(
            f"QPushButton#doughUpdateChip {{ "
            f"background: rgba({r},{g},{b},0.16); color: {ui_helpers.TEXT_DIM}; "
            f"border: 1px solid rgba({r},{g},{b},0.40); "
            f"border-radius: {rad(6)}px; padding: 0 10px; "
            f"{type_qss(TYPE_CAPTION)} }}"
            f"QPushButton#doughUpdateChip:hover {{ "
            f"background: rgba({r},{g},{b},0.26); "
            f"border-color: rgba({r},{g},{b},0.60); }}"
        )

    @staticmethod
    def _accent_rgb() -> tuple[int, int, int]:
        try:
            # Module-attribute read (not a from-import) so the live-accent
            # restyle sees the CURRENT accent after refresh_theme() rebinds it.
            s = ui_helpers.ACCENT.lstrip("#")
            return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        except Exception:
            return 124, 102, 208

    # ── Bus handler ─────────────────────────────────────────────────────
    def _on_update_available(self, version: str, download_url: str, notes_url: str) -> None:
        from trackerkeeper import identity

        self._version = version
        self._download_url = download_url
        self._notes_url = notes_url
        self.setText(self.tr("Update {0}").format(version))
        self.setToolTip(
            self.tr("{0} {1} is available").format(identity.display_name(), version)
        )
        self.setVisible(True)

    # ── Interaction ─────────────────────────────────────────────────────
    def _open_menu(self) -> None:
        if not self._version:
            return
        menu = opaque_menu(self)
        download = QAction(self.tr("Download"), menu)
        download.triggered.connect(lambda: self._open(self._download_url))
        menu.addAction(download)
        notes = QAction(self.tr("What's new"), menu)
        notes.triggered.connect(lambda: self._open(self._notes_url))
        menu.addAction(notes)
        menu.addSeparator()
        dismiss = QAction(self.tr("Dismiss"), menu)
        dismiss.triggered.connect(self._dismiss)
        menu.addAction(dismiss)
        self._menu = menu  # prevent GC during the non-blocking popup
        menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    @staticmethod
    def _open(url: str) -> None:
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _dismiss(self) -> None:
        try:
            from trackerkeeper.settings import get_settings

            get_settings().update_dismissed_version = self._version
        except Exception:
            pass
        self.setVisible(False)
