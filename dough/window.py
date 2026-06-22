"""AppWindow — dough's frosted, frameless, cross-platform main-window base.

Subclass it (or use it directly), drop your UI in with ``set_content(widget)``,
and you inherit, solved once:

  * **Borderless frameless chrome** — on KDE Wayland a KWin ``noborder`` rule
    strips the decoration; on Windows ``FramelessWindowHint`` + the
    ``win_frameless`` native sizing frame (smooth top/left-edge resize, taskbar-
    correct maximize). Opt back into the native title bar with
    ``settings.native_window_border``.
  * **Compositor blur** shaped to the rounded body (KWin / DWM Acrylic), with an
    honest near-opaque fallback when blur isn't available — a frosted surface
    never goes broken-see-through.
  * **A self-painted rounded body** that squares flush when maximized.
  * **Edge/corner resize + cursors** on Wayland; the OS native frame on Windows.
  * **A top bar that doubles as the titlebar** (drag-to-move, window controls).

Every chrome method here is lifted from jellytoast's shipped main window, with
the music removed and ``PlayerBus`` → ``AppBus``.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSlider,
    QApplication,
    QMainWindow,
    QStyle,
    QStyleOption,
    QVBoxLayout,
    QWidget,
)

from dough.bus import AppBus
from dough.design_tokens import RADIUS_WINDOW
from dough.platform_compat import IS_WINDOWS, is_kde_wayland
from dough.settings import get_settings

logger = logging.getLogger(__name__)


class _ResizeEdgeFilter(QObject):
    """Edge + corner resize for the borderless window on KDE Wayland.

    The borderless window is still server-side-decorated (KWin owns the real
    window rect — a ``noborder`` rule just strips the visible chrome), so
    ``startSystemResize`` works directly. KWin no longer draws resize borders,
    so this filter re-supplies the hit detection + cursor feedback. Installed on
    the QApplication so it sees mouse events whatever child they land on.
    """

    MARGIN = 6  # single-edge band thickness, logical px
    CORNER = 16  # corner zones are fatter — forgiving diagonal grab

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._cursor_on = False

    def eventFilter(self, obj, event):
        et = event.type()
        if et not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress):
            return False
        win = self._window
        if (
            win.isMaximized()
            or win.isFullScreen()
            or not win.isVisible()
            or not win.isActiveWindow()
        ):
            self._clear_cursor()
            return False
        local = win.mapFromGlobal(event.globalPosition().toPoint())
        if not win.rect().contains(local):
            self._clear_cursor()
            return False
        edges = self._edges_at(local, win.width(), win.height())
        if edges == Qt.Edge(0):
            self._clear_cursor()
            return False
        # A press/hover on an interactive control near the edge is a click/drag, not a
        # resize — let it through. Buttons (titlebar window controls) AND sliders (an
        # auto-fade scrollbar pill lives ON the right edge) both yield, so the resize
        # band doesn't steal the scrollbar's grab.
        if isinstance(win.childAt(local), (QAbstractButton, QAbstractSlider)):
            self._clear_cursor()
            return False
        if et == QEvent.Type.MouseMove:
            win.setCursor(self._cursor_for(edges))
            self._cursor_on = True
            return False
        if event.button() == Qt.MouseButton.LeftButton:
            handle = win.windowHandle()
            if handle is not None:
                handle.startSystemResize(edges)
                return True  # consume — the child under it must not also react
        return False

    def _clear_cursor(self):
        if self._cursor_on:
            self._window.unsetCursor()
            self._cursor_on = False

    def _edges_at(self, pos, w, h):
        m, c = self.MARGIN, self.CORNER
        x, y = pos.x(), pos.y()
        near_l, near_r = x <= c, x >= w - c
        near_t, near_b = y <= c, y >= h - c
        if near_l and near_t:
            return Qt.Edge.LeftEdge | Qt.Edge.TopEdge
        if near_r and near_t:
            return Qt.Edge.RightEdge | Qt.Edge.TopEdge
        if near_l and near_b:
            return Qt.Edge.LeftEdge | Qt.Edge.BottomEdge
        if near_r and near_b:
            return Qt.Edge.RightEdge | Qt.Edge.BottomEdge
        if x <= m:
            return Qt.Edge.LeftEdge
        if x >= w - m:
            return Qt.Edge.RightEdge
        if y <= m:
            return Qt.Edge.TopEdge
        if y >= h - m:
            return Qt.Edge.BottomEdge
        return Qt.Edge(0)

    @staticmethod
    def _cursor_for(edges):
        left, right = Qt.Edge.LeftEdge, Qt.Edge.RightEdge
        top, bottom = Qt.Edge.TopEdge, Qt.Edge.BottomEdge
        if edges in (left | top, right | bottom):
            return Qt.CursorShape.SizeFDiagCursor
        if edges in (right | top, left | bottom):
            return Qt.CursorShape.SizeBDiagCursor
        if edges in (left, right):
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor


class AppWindow(QMainWindow):
    """The frosted cross-platform main window. Use ``set_content()`` to fill the
    area below the top bar."""

    def __init__(self, *, title: str = "dough"):
        super().__init__()
        self.setObjectName("doughWindow")
        self.setWindowTitle(title)
        self.bus = AppBus.get()
        s = get_settings()

        # ── Windows real-blur (Acrylic) chrome ────────────────────────────
        # DWM/accent backdrops never composite behind a per-pixel-alpha LAYERED
        # window (WA_TranslucentBackground), so on Windows we DON'T set it —
        # instead the background is a styled (QSS) transparent that repaints
        # each frame, and the Acrylic is applied to the HWND in blur/_dwm.
        self._win_blur = IS_WINDOWS and not s.native_window_border
        if self._win_blur:
            from dough.theme import get_active_theme

            self._win_blur_active = get_active_theme().blur
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self.setStyleSheet(
                self.styleSheet() + "\n#doughWindow{background:transparent}"
            )
        else:
            self._win_blur_active = False
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Body fill: alpha tracks verified blur status (glass ~67% with blur,
        # near-opaque ~92% without) so a frosted theme never renders see-through.
        self._body_qcolor = self._resolve_body_qcolor()

        # Windows: Qt-frameless (also grants the per-pixel alpha the Acrylic
        # backdrop shows through). KDE Wayland: a KWin noborder rule does it.
        self._win_frameless = IS_WINDOWS and not s.native_window_border
        if self._win_frameless:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self._borderless = (
            is_kde_wayland() and not s.native_window_border
        ) or self._win_frameless

        if self._borderless:
            # Wayland: re-supply edge resize (KWin draws no border). Windows: the
            # native sizing frame owns resize, so skip the Qt filter there.
            if not self._win_frameless:
                self._resize_filter = _ResizeEdgeFilter(self)
                QApplication.instance().installEventFilter(self._resize_filter)
            # Re-shape the rounded blur region after a resize settles (debounced).
            self._blur_settle = QTimer(self)
            self._blur_settle.setSingleShot(True)
            self._blur_settle.setInterval(120)
            self._blur_settle.timeout.connect(self._apply_blur)

        # ── Structure: top bar (titlebar) + content host ──────────────────
        central = QWidget(self)
        central.setStyleSheet("background: transparent;")
        self._root = QVBoxLayout(central)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        self.top_bar = self._make_top_bar(title)
        self._root.addWidget(self.top_bar)

        self._content_host = QWidget()
        self._content_host.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._root.addWidget(self._content_host, 1)
        self._footer: "QWidget | None" = None
        self.setCentralWidget(central)

        # Live theme/accent: re-stamp body + blur (+ rebuild GLOBAL_STYLE).
        self.bus.theme_changed.connect(self._on_theme_changed)
        self._did_first_show = False
        self.resize(1100, 720)

    # ── Public API ────────────────────────────────────────────────────────
    def set_content(self, widget: QWidget) -> None:
        """Replace the content area below the top bar with ``widget``."""
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            old = item.widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        self._content_layout.addWidget(widget, 1)

    def set_footer(self, widget) -> None:
        """Pin ``widget`` as a bottom row below the content area (e.g. a media
        transport bar). Replaces any previous footer; pass ``None`` to clear. The
        footer takes its natural height — only the content area stretches."""
        if self._footer is not None:
            self._footer.setParent(None)
            self._footer.deleteLater()
            self._footer = None
        if widget is not None:
            self._root.addWidget(widget)  # after _content_host → pinned bottom
            self._footer = widget

    def _make_top_bar(self, title: str):
        """Build the top bar (which doubles as the titlebar). Override to supply a
        custom bar — it only needs to expose ``restyle()`` (called on every theme
        change). Default: the generic :class:`~dough.top_bar.TopBar`."""
        from dough.top_bar import TopBar

        return TopBar(self, titlebar_mode=self._borderless, title=title)

    def closeEvent(self, event) -> None:
        """Persist window geometry on close so the next launch restores it
        (``run_app`` calls ``restore_geometry`` on boot). A fork that quits by a
        path other than closing the window can save geometry on its own quit hook."""
        get_settings().save_geometry(self)
        super().closeEvent(event)

    # ── Theme / appearance ─────────────────────────────────────────────────
    def _on_theme_changed(self):
        from dough import ui_helpers

        ui_helpers.refresh_theme()  # rebuild GLOBAL_STYLE + module constants
        if self._win_blur:
            self.setStyleSheet(
                ui_helpers.GLOBAL_STYLE + "\n#doughWindow{background:transparent}"
            )
        self._refresh_body_color()
        self._apply_blur()
        if hasattr(self.top_bar, "restyle"):
            self.top_bar.restyle()

    def showEvent(self, e):
        super().showEvent(e)
        if not self._did_first_show:
            self._did_first_show = True
            if self._win_frameless:
                QTimer.singleShot(0, self._apply_win_native_frame)
            QTimer.singleShot(0, self._first_blur_pass)

    # ── Chrome internals (lifted from jellytoast) ──────────────────────────
    def _is_edge_flush(self) -> bool:
        """True when the window sits flush to a screen edge so its rounded
        corners shouldn't paint — Qt-maximized OR a height-flush vertical-max."""
        if self.isMaximized() or self.isFullScreen():
            return True
        screen = self.screen()
        if screen is None:
            return False
        avail = screen.availableGeometry()
        geo = self.geometry()
        return abs(geo.height() - avail.height()) <= 1 and abs(geo.y() - avail.y()) <= 1

    def _resolve_body_qcolor(self) -> QColor:
        from dough import ui_helpers

        return QColor(*ui_helpers.body_color_tuple("main"))

    def _refresh_body_color(self):
        if self._win_blur:
            from dough.theme import get_active_theme

            was = self._win_blur_active
            self._win_blur_active = get_active_theme().blur
            if was != self._win_blur_active:
                self.update()
        new = self._resolve_body_qcolor()
        if new != self._body_qcolor:
            self._body_qcolor = new
            self.update()

    def _apply_win_native_frame(self):
        if not self._win_frameless:
            return
        try:
            from dough import win_frameless

            win_frameless.enable(int(self.winId()))
        except Exception as exc:  # pragma: no cover — Windows-only
            logger.debug("native frame setup failed: %s", exc)

    def _first_blur_pass(self):
        """Post-show: issue blur now the surface is mapped, then re-probe the
        verified status and re-pick the body alpha."""
        from dough import blur
        from dough.theme import get_active_theme

        self._apply_blur()
        if not get_active_theme().blur:
            return
        status = blur.status(force=True)
        self._refresh_body_color()
        if status is not blur.BlurStatus.ACTIVE:
            logger.info("Frosted theme: %s (%s).", blur.reason(), status.value)
        else:
            logger.debug("Compositor blur: %s", blur.reason())

    def _apply_blur(self):
        """Shape the compositor blur to the rounded body (squared when flush)."""
        from dough import blur
        from dough.theme import get_active_theme

        radius = 0 if self._is_edge_flush() else RADIUS_WINDOW
        blur.apply(self, get_active_theme().blur, radius)

    def _apply_blur_whole(self):
        """Whole-window (square, empty-region) blur during an active resize —
        auto-tracks the lagging Wayland surface so it can't desync."""
        from dough import blur
        from dough.theme import get_active_theme

        blur.apply(self, get_active_theme().blur, 0)

    def paintEvent(self, e):
        if self._win_blur_active:
            # Frosted theme + Windows Acrylic: paint the styled transparent
            # background (clears each frame, no ghosting) so the blur shows.
            opt = QStyleOption()
            opt.initFrom(self)
            sp = QPainter(self)
            self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, sp, self)
            sp.end()
            return
        p = QPainter(self)
        try:
            if self._borderless:
                radius = 0 if self._is_edge_flush() else RADIUS_WINDOW
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(self._body_qcolor)
                p.drawRoundedRect(self.rect(), radius, radius)
                self._paint_body_backdrop(p, self.rect(), radius)
            else:
                p.fillRect(self.rect(), self._body_qcolor)
                self._paint_body_backdrop(p, self.rect(), 0)
        finally:
            p.end()

    def _paint_body_backdrop(self, painter, rect, radius) -> None:
        """No-op hook, called right after the body fill in :meth:`paintEvent`.
        Override to paint a backdrop (e.g. an album-art frost behind the content)
        without re-implementing the rounded-rect / edge-flush body logic."""
        return

    def changeEvent(self, e):
        if e.type() == QEvent.Type.DevicePixelRatioChange:
            try:
                AppBus.get().dpr_changed.emit()
            except Exception as exc:
                logger.warning("dpr_changed emit failed: %s", exc)
            if self._win_frameless:
                try:
                    from dough import win_frameless

                    hwnd = int(self.winId())
                    if not win_frameless.is_enabled(hwnd):
                        win_frameless.enable(hwnd)
                except Exception as exc:
                    logger.debug("native frame re-assert failed: %s", exc)
        elif getattr(self, "_borderless", False) and (
            e.type() == QEvent.Type.WindowStateChange
        ):
            self.update()
            self._apply_blur_whole()
            self._blur_settle.start()
        super().changeEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, "_borderless", False) and hasattr(self, "_blur_settle"):
            # Windows: skip the per-tick DWM reshape (Acrylic auto-covers the
            # HWND); Wayland needs the immediate whole-window call.
            if not IS_WINDOWS:
                self._apply_blur_whole()
            self._blur_settle.start()

    def nativeEvent(self, event_type, message):
        if self._win_frameless and event_type == b"windows_generic_MSG":
            try:
                from dough import win_frameless

                handled, result = win_frameless.handle(self, int(message))
                if handled:
                    return True, result
            except Exception as exc:  # pragma: no cover — Windows-only
                logger.debug("native resize event: %s", exc)
        return super().nativeEvent(event_type, message)
