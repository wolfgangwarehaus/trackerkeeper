"""The system-tray presence — tracker keeper's resting state.

A watchtower is only useful if it's *watching*, which means living in the tray
rather than in a window you have to keep open. :class:`AppTray` puts the app
there: an icon whose tooltip carries the current update count, a menu (Show /
Check for updates / Settings / Quit), left-click to toggle the window, and an
optional close-to-tray so the X button hides instead of quitting.

Everything is best-effort and self-disabling: if the desktop has no tray
(``isSystemTrayAvailable()`` False — headless, some wlroots sessions), nothing
is created, ``available`` stays False, and the app behaves exactly as before —
the close button never traps the window in an invisible process.

Preferences live under the documented extension path (``get_settings()._s``), so
no base settings file is touched:
``app/show_tray_icon`` and ``app/close_to_tray``.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from trackerkeeper.bus import AppBus
from trackerkeeper.settings import get_settings

logger = logging.getLogger(__name__)

_KEY_SHOW = "app/show_tray_icon"
_KEY_CLOSE = "app/close_to_tray"


def _as_bool(val, default: bool) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def show_tray_icon() -> bool:
    return _as_bool(get_settings()._s.value(_KEY_SHOW), True)


def set_show_tray_icon(v: bool) -> None:
    get_settings()._s.setValue(_KEY_SHOW, bool(v))


def close_to_tray() -> bool:
    """Close hides to the tray instead of quitting. On by default for a
    watchtower — but only ever honoured while a tray icon is actually live."""
    return _as_bool(get_settings()._s.value(_KEY_CLOSE), True)


def set_close_to_tray(v: bool) -> None:
    get_settings()._s.setValue(_KEY_CLOSE, bool(v))


def tooltip_text(app_name: str, n_updates: int) -> str:
    """The hover text: the fleet's headline, no window needed."""
    if n_updates <= 0:
        return f"{app_name} — all current"
    return f"{app_name} — {n_updates} update{'s' if n_updates != 1 else ''} available"


class AppTray(QObject):
    """The tray icon + its menu. Construct with the main window; call
    :meth:`set_update_count` whenever the fleet's update total changes."""

    def __init__(self, window, *, app_name: str = "tracker keeper",
                 on_refresh=None, parent=None):
        super().__init__(parent or window)
        self._window = window
        self._app_name = app_name
        self._on_refresh = on_refresh
        self._quitting = False
        self._icon: QSystemTrayIcon | None = None

        if not (show_tray_icon() and QSystemTrayIcon.isSystemTrayAvailable()):
            return

        from trackerkeeper.ui_helpers import make_app_icon, opaque_menu

        self._icon = QSystemTrayIcon(QIcon(make_app_icon(64)), self)
        self._icon.setToolTip(tooltip_text(app_name, 0))

        menu = opaque_menu(window, blur_corner_radius=8)
        self._show_action = menu.addAction("Show tracker keeper")
        self._show_action.triggered.connect(lambda _=False: self._toggle_window())
        if on_refresh is not None:
            menu.addAction("Check for updates").triggered.connect(
                lambda _=False: on_refresh())
        menu.addSeparator()
        menu.addAction("Settings…").triggered.connect(
            lambda _=False: AppBus.get().show_settings.emit())
        menu.addAction("Quit").triggered.connect(lambda _=False: self.quit())
        self._menu = menu
        self._icon.setContextMenu(menu)
        self._icon.activated.connect(self._on_activated)
        self._icon.show()

        # Hiding the last window must NOT end the process once we live in the
        # tray — the app's whole point is to keep watching.
        app = QApplication.instance()
        if app is not None:
            app.setQuitOnLastWindowClosed(False)
        window.installEventFilter(self)

    # ── state ──────────────────────────────────────────────────────────────
    @property
    def available(self) -> bool:
        """True when a tray icon is actually live (desktop supports it and the
        user hasn't turned it off). Everything else no-ops when False."""
        return self._icon is not None

    def set_update_count(self, n: int) -> None:
        """Reflect the fleet's update total in the tooltip."""
        if self._icon is not None:
            self._icon.setToolTip(tooltip_text(self._app_name, n))

    def notify(self, title: str, body: str) -> None:
        """A tray balloon — the fallback when the OS notification backend
        isn't available."""
        if self._icon is not None:
            self._icon.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information)

    # ── actions ────────────────────────────────────────────────────────────
    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self._toggle_window()

    def _toggle_window(self) -> None:
        w = self._window
        if w.isVisible() and not w.isMinimized():
            self._hide_window()
        else:
            from trackerkeeper.single_instance import force_foreground

            w.showNormal()
            force_foreground(w)

    def _hide_window(self) -> None:
        # Geometry is normally persisted by the window's closeEvent — hiding
        # skips that, so save it here or a tray-only session forgets its size.
        try:
            get_settings().save_geometry(self._window)
        except Exception:
            logger.debug("save_geometry on hide-to-tray failed", exc_info=True)
        self._window.hide()

    def quit(self) -> None:
        """Really exit (the tray's Quit) — bypasses close-to-tray."""
        self._quitting = True
        try:
            get_settings().save_geometry(self._window)
        except Exception:
            logger.debug("save_geometry on quit failed", exc_info=True)
        if self._icon is not None:
            self._icon.hide()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    # ── close-to-tray ──────────────────────────────────────────────────────
    def eventFilter(self, obj, event):  # noqa: N802 (Qt override)
        # Guard order matters: bail out on the no-tray / quitting cases BEFORE
        # touching the event, so the filter is inert (and safe) when there's no
        # tray to hide into.
        if (
            self.available
            and not self._quitting
            and obj is self._window
            and close_to_tray()
            and event is not None
            and event.type() == QEvent.Type.Close
        ):
            event.ignore()
            self._hide_window()
            return True
        return False
