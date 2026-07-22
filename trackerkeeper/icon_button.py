"""IconButton — a flat icon QPushButton that paints its icon SNAPPED to whole
device pixels, so single-color SVG icons stay crisp at FRACTIONAL display
scales (Windows 125% = devicePixelRatio 1.25, 150%, KDE Wayland fractional).

The standard QPushButton/QStyle path blits the icon pixmap at the button's
layout position, which at a fractional devicePixelRatio can land on a
half-device-pixel and get bilinear-smoothed — that's the soft-icon look. Text
dodges this because the font engine hints glyphs onto the pixel grid; pixmaps
don't (and supersampling the pixmap doesn't help — the smear is the POSITION,
not the resolution).

IconButton intercepts setIcon (capturing the QIcon instead of letting Qt draw
it) and, in paintEvent, blits the dpr-correct pixmap at a top-left position
ROUNDED to whole device pixels — the same pixel-grid alignment a font engine
does. Every existing ``btn.setIcon(icon(name))`` call site works unchanged;
only the button class is swapped, so accent / active / toggle states (which
just call setIcon again) keep working with zero call-site churn.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QIcon, QPainter
from PySide6.QtWidgets import QPushButton

logger = logging.getLogger(__name__)


class IconButton(QPushButton):
    """An icon-only button has no visible text, so a screen reader has
    nothing to announce unless we name it. Pass ``accessible_name`` (a short
    translated action label — "Settings", "Close") at construction; when
    omitted, the tooltip doubles as the accessible name (every existing
    ``setToolTip`` call site keeps working). A button that ends up shown
    with neither logs a debug warning — and fails ``tests/test_a11y.py``
    when reachable from the demo window — unless it opts out with
    ``setProperty("a11y_exempt", True)`` (decorative controls only)."""

    def __init__(self, *args, accessible_name: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._own_qicon: QIcon | None = None
        # Whether the accessible name was set explicitly (ctor or
        # setAccessibleName) vs mirrored from the tooltip — an explicit name
        # is never clobbered by a later tooltip change.
        self._explicit_a11y_name = bool(accessible_name)
        if accessible_name:
            super().setAccessibleName(accessible_name)
        # Icon buttons are mouse-driven chrome: they keep the default arrow
        # cursor (no pointing-hand — that affordance is reserved for text CTAs
        # and clickable cards) and take NO keyboard focus, so a focus snap
        # (e.g. after a mode toggle) never paints Qt's focus ring on a
        # transport button. Centralised here so every site — including the
        # subclasses (CoverOverlayButton here; an app's own
        # transport buttons) and the top/footer bars — is uniform; a styled focus ring belongs with a real
        # keyboard-nav pass, not on these.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def setAccessibleName(self, name: str) -> None:  # noqa: N802 — Qt override
        # An explicit name wins over the tooltip mirror from here on.
        self._explicit_a11y_name = bool(name)
        super().setAccessibleName(name)

    def setToolTip(self, text: str) -> None:  # noqa: N802 — Qt override
        super().setToolTip(text)
        if not self._explicit_a11y_name:
            # Tooltip doubles as the accessible name — the fallback that
            # keeps every pre-a11y call site announced.
            super().setAccessibleName(text)
        elif text and text != self.accessibleName():
            # With an explicit name, a DIFFERENT tooltip adds detail — expose
            # it as the description (identical text would just be announced
            # twice, so skip that case).
            self.setAccessibleDescription(text)

    def showEvent(self, e):  # noqa: N802 — Qt override
        super().showEvent(e)
        if (
            not self.accessibleName()
            and not self.text()
            and not self.property("a11y_exempt")
        ):
            logger.debug(
                "IconButton shown without an accessible name — pass "
                "accessible_name= or setToolTip() so screen readers can "
                "announce it (objectName=%r)",
                self.objectName(),
            )

    def setIcon(self, icon: QIcon) -> None:  # noqa: N802 — Qt override
        # Capture the icon and paint it ourselves (snapped). Deliberately NOT
        # forwarded to QPushButton, whose style would draw it un-snapped.
        self._own_qicon = icon
        self.update()

    def icon(self) -> QIcon:  # noqa: N802 — keep the getter consistent
        return self._own_qicon if self._own_qicon is not None else QIcon()

    def sizeHint(self):  # noqa: N802 — Qt override
        # We don't forward the glyph to QPushButton, so its sizeHint ignores
        # it. A button that doesn't setFixedSize would collapse to a bare
        # frame — fall back to the icon size so it stays the right size.
        s = self.iconSize()
        return s if not s.isEmpty() else super().sizeHint()

    def paintEvent(self, e):  # noqa: N802 — Qt override
        # QPushButton paints the flat background + hover/pressed wash (it has
        # no icon on the super, so it draws none).
        super().paintEvent(e)
        ic = self._own_qicon
        s = self.iconSize()
        if ic is not None and not ic.isNull() and not s.isEmpty():
            dpr = self.devicePixelRatioF()
            # Centre the icon, then SNAP the top-left to whole device pixels —
            # the crispness fix. round(x*dpr)/dpr puts the icon's left/top
            # exactly on a device-pixel boundary so the dpr-correct pixmap
            # blits 1:1.
            x = round((self.width() - s.width()) / 2.0 * dpr) / dpr
            y = round((self.height() - s.height()) / 2.0 * dpr) / dpr
            if not self.isEnabled():
                mode = QIcon.Mode.Disabled
            elif self.underMouse():
                mode = QIcon.Mode.Active
            else:
                mode = QIcon.Mode.Normal
            pm = ic.pixmap(s, dpr, mode, QIcon.State.Off)
            # Painter built only when there's an icon to draw — the no-icon
            # path (text-only / pre-setIcon) stays painter-free (pre-#99).
            p = QPainter(self)
            p.drawPixmap(QPointF(x, y), pm)
            p.end()
        # Keyboard-focus affordance is the platform style's NATIVE focus
        # indicator (drawn by super().paintEvent for the focused button) —
        # the same one the plain-QPushButton dropdowns (View / library) get,
        # so every keyboard-focusable chrome button matches. A custom accent
        # ring on top of it double-highlighted; don't add one.
