"""The live theme as properties QML binds to.

Opaque, always: Plasma Mobile disables blur, and the frosted body the desktop
window paints over a wallpaper is what made the Widgets UI unreadable on a
phone (white-on-pale-frost). The phone gets the theme's solid panel colour.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal
from PySide6.QtGui import QColor

from trackerkeeper import ui_helpers as _u


def _qcolor(css: str) -> QColor:
    """Our tokens are CSS strings (``#rrggbb`` / ``rgba(r, g, b, a)``)."""
    r, g, b, a = _u._parse_qss_color(css)
    c = QColor(r, g, b)
    c.setAlphaF(a)
    return c


def _opaque(css: str) -> QColor:
    c = _qcolor(css)
    c.setAlphaF(1.0)
    return c


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    """``a`` moved ``t`` of the way to ``b`` — a solid tint, no alpha, so it
    reads the same over anything."""
    return QColor.fromRgbF(a.redF() + (b.redF() - a.redF()) * t,
                           a.greenF() + (b.greenF() - a.greenF()) * t,
                           a.blueF() + (b.blueF() - a.blueF()) * t)


class Theme(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtGui import QGuiApplication

        from trackerkeeper.bus import AppBus

        AppBus.get().theme_changed.connect(self.changed)
        app = QGuiApplication.instance()
        if app is not None:
            # "auto" follows the OS light/dark switch — on a phone that's the
            # quick-settings toggle, flipped mid-session. Re-stamp the module
            # tokens, then let every binding re-read them.
            app.styleHints().colorSchemeChanged.connect(self._on_scheme)

    def _on_scheme(self, *_):
        _u.refresh_theme()
        self.changed.emit()

    def _bg(self) -> QColor:
        return _opaque(_u.BG)

    def _on_accent(self) -> QColor:
        c = _qcolor(_u.ACCENT)
        lum = 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
        return QColor("#111111") if lum > 0.6 else QColor("#ffffff")

    background = Property(QColor, _bg, notify=changed)
    # A step up from the page: sheets and the pressed-row wash.
    surface = Property(QColor, lambda self: _mix(_opaque(_u.BG), QColor("#ffffff"), 0.07),
                       notify=changed)
    text = Property(QColor, lambda self: _opaque(_u.TEXT), notify=changed)
    textDim = Property(QColor, lambda self: _mix(_opaque(_u.BG), _opaque(_u.TEXT), 0.68),
                       notify=changed)
    textFaint = Property(QColor, lambda self: _mix(_opaque(_u.BG), _opaque(_u.TEXT), 0.40),
                         notify=changed)
    divider = Property(QColor, lambda self: _mix(_opaque(_u.BG), _opaque(_u.TEXT), 0.12),
                       notify=changed)
    accent = Property(QColor, lambda self: _opaque(_u.ACCENT), notify=changed)
    onAccent = Property(QColor, _on_accent, notify=changed)
    # The accent as a quiet fill (a fresh row's wash, the "N new" pill).
    accentWash = Property(QColor, lambda self: _mix(_opaque(_u.BG), _opaque(_u.ACCENT), 0.16),
                          notify=changed)
    warning = Property(QColor, lambda self: QColor("#c98a2b"), constant=True)
