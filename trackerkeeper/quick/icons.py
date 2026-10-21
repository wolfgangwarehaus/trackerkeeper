"""SVG glyphs for QML: ``image://icon/<name>/<rrggbb>``.

The shared set (``trackerkeeper.icons._SVG``) plus the few the phone needs
that the desktop never drew. They live here, not in ``icons.py``, because
that module syncs from dough and would drop them on the next ``--apply``.
Same 24×24 viewBox, stroke 2, round caps, ``currentColor``.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer

from trackerkeeper import icons as _icons


def _stroke(d: str) -> str:
    return ('<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
            f'<path d="{d}" stroke="currentColor" stroke-width="2" fill="none" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>')


EXTRA = {
    "plus": _stroke("M12 5 L12 19 M5 12 L19 12"),
    "refresh": _stroke("M20 11 A8 8 0 1 0 17.7 17.7 M20 4 L20 11 L13 11"),
    "external": _stroke("M14 4 L20 4 L20 10 M20 4 L11 13 M18 14 L18 20 L4 20 L4 6 L10 6"),
    "edit": _stroke("M4 20 L8 19 L19 8 L16 5 L5 16 Z M14 7 L17 10"),
    "trash": _stroke("M4 7 L20 7 M9 7 L9 4 L15 4 L15 7 M6 7 L7 20 L17 20 L18 7"),
    "close": _stroke("M6 6 L18 18 M18 6 L6 18"),
    "more": ('<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
             '<circle cx="12" cy="5" r="1.8" fill="currentColor"/>'
             '<circle cx="12" cy="12" r="1.8" fill="currentColor"/>'
             '<circle cx="12" cy="19" r="1.8" fill="currentColor"/></svg>'),
}


def svg(name: str) -> str:
    return EXTRA.get(name) or _icons._SVG.get(name, "")


def render(name: str, color: str, px: int) -> QPixmap:
    pix = QPixmap(px, px)
    pix.fill(Qt.GlobalColor.transparent)
    src = svg(name)
    if src:
        renderer = QSvgRenderer(QByteArray(src.replace("currentColor", color).encode()))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(p)
        p.end()
    return pix


class IconProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Pixmap)

    def requestPixmap(self, id_: str, size: QSize, requested: QSize) -> QPixmap:  # noqa: N802
        name, _, color = id_.partition("/")
        px = max(requested.width(), requested.height())
        px = px if px > 0 else 48
        if size is not None:
            size.setWidth(px)
            size.setHeight(px)
        return render(name, "#" + (color.lstrip("#") or "ffffff"), px)
