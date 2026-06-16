"""
Shared UI helpers: theme, async image loader, formatting, common widgets.
"""

import contextlib
import shutil
import subprocess
import threading
from typing import Optional

from PySide6.QtCore import (
    Property,
    QEvent,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPalette,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

from dough.icon_button import IconButton

# ── Theme ────────────────────────────────────────────────────────────────────
# Palette + body fills come from the active Theme (dough/theme.py).
# Constants are re-exported so existing `from dough.ui_helpers import
# TEXT, ACCENT, ...` callers don't have to change.
#
# These names are mutated in place by ``refresh_theme()`` when the user
# picks a new accent — the live-apply path: settings → refresh_theme()
# → bus.theme_changed → subscribers re-pull the current values. Since
# callers typically grab the constants once at __init__ and splat them
# into QSS strings, the subscriber has to re-run its styling code; the
# new module-level values are what it'll read.
from dough.theme import get_active_theme, ink_alpha  # noqa: F401  (re-exported)

_THEME = get_active_theme()

# Every UI color now lives on the active Theme as a semantic token
# (dough/theme.py). The constants below are flat re-exports of those
# tokens — named for the SEMANTIC they serve, not the value they hold —
# so the whole set swaps wholesale when the theme mode changes. They're
# mutated in place by ``refresh_theme()`` (see its docstring) and may be
# further overlaid by user color-token overrides via ``color_tokens``.

# ── Accent ─────────────────────────────────────────────────────────────
ACCENT = _THEME.accent
ACCENT_DEEP = _THEME.accent_deep
BORDER_ACCENT = _THEME.border_accent

# ── Surfaces ───────────────────────────────────────────────────────────
BG = _THEME.bg
BG_PANEL = _THEME.bg_panel
BG_CARD = _THEME.bg_card

# ── Text ───────────────────────────────────────────────────────────────
TEXT = _THEME.text
TEXT_DIM = _THEME.text_dim
TEXT_FAINT = _THEME.text_faint
IDLE_TEXT = _THEME.idle_text  # "Nothing playing" / idle-state foreground
ERROR_FG = _THEME.error_fg  # inline error text (login failed, etc.)
WARN_FG = _THEME.warn_fg  # warning marker — offline-mode indicator

# ── Borders ────────────────────────────────────────────────────────────
BORDER = _THEME.border

# ── Interactive washes ─────────────────────────────────────────────────
# Hover / press fills for buttons, list rows, tiles — interpolated into
# QSS. Sourcing them from one place keeps wash strength uniform across
# every surface instead of each stylesheet hardcoding its own near-but-
# not-identical value.
WASH_HOVER = _THEME.wash_hover  # icon-button hover, volume popup body
WASH_PRESSED = _THEME.wash_pressed  # icon-button pressed state
HOVER_SUBTLE = _THEME.hover_subtle  # ghost-button + library-tile hover
HOVER_LIST_ROW = _THEME.hover_list_row  # list-row hover (cast/settings)
SELECTED_ROW = _THEME.selected_row  # selected list row (non-accent)
PRESSED_WHITE = _THEME.pressed_white  # white-press button state

# ── Inputs ─────────────────────────────────────────────────────────────
SURFACE_INPUT = _THEME.surface_input  # QLineEdit / QComboBox / QSpinBox
SURFACE_INPUT_FOCUS = _THEME.surface_input_focus  # input :focus tint
DISABLED_FG = _THEME.disabled_fg  # disabled icon-button color

# ── Sliders ────────────────────────────────────────────────────────────
SLIDER_GROOVE = _THEME.slider_groove  # slider track (volume / seek / EQ)

# ── Overlays / popups ──────────────────────────────────────────────────
OVERLAY_DARK = _THEME.overlay_dark  # cover-art heart bg + downloads chip
OVERLAY_DARK_HOVER = _THEME.overlay_dark_hover  # overlay on hover
POPUP_OPAQUE_FILL = _THEME.popup_opaque_fill  # opaque popup body

# ── Painted body fills ─────────────────────────────────────────────────
# Used as `QColor(*BODY_COLOR)` inside paintEvent. Three slots because
# the main window, mini player, and dialogs each paint their own
# surface and read at slightly different depths.
BODY_COLOR = _THEME.body_color
MINI_BODY_COLOR = _THEME.mini_body_color
DIALOG_BODY_COLOR = _THEME.dialog_body_color


def body_color_tuple(surface: str = "main") -> tuple:
    """Status-aware RGBA body fill for a frosted painted surface.

    The single source of truth behind "Frosted never renders see-through":
    on a frosted theme the body alpha tracks whether real compositor blur is
    *verified* behind the window — glass (~67%) when it is, a near-opaque
    frosted panel (~92%) when it isn't. Non-frosted themes (Solid /
    Transparent) return their fixed body unchanged. The main window, mini
    player, and every frosted dialog all read this so they degrade together.

    Reads the live active theme + the cached blur status, so it picks up a
    theme switch and a post-show blur re-probe for free. ``surface`` selects
    main / mini / dialog. Does NOT apply the main window's JT_OPAQUE override
    (that's main-window-only; the caller handles it). Never raises."""
    from dough import blur
    from dough.theme import body_color_for, get_active_theme

    theme = get_active_theme()
    status = blur.status() if theme.blur else blur.BlurStatus.DISABLED
    return body_color_for(theme, status, surface)


# Materialize the check-mark SVG to a cache file so QSS can reference
# it via image:url(...).
#
# Rasterised to PNG, not SVG: Qt's QStyleSheetStyle silently fails to
# render `image: url(file.svg)` on KDE Fusion / some Wayland builds
# (the indicator shows as solid-fill with no visible glyph). PNG
# loads via QPixmap which is the well-tested path.
#
# The stroke color is parameterised — we render one PNG per
# distinct stroke color the app asks for and cache by (color, size).
# `_check_url_for(color)` returns the on-disk path for a given hex
# color; it generates the PNG lazily on first request.
def _render_check_png(color_hex: str, size: int = 24) -> str:
    """Rasterise the checkmark SVG to a transparent PNG in the given
    stroke color and return the cached path. Caches by (color, size)
    so an accent change uses a different file → Qt picks up the new
    image instead of returning a stale cached pixmap.

    Returns empty string when called before QApplication exists
    (early imports during module load) — QPixmap requires a running
    QGuiApplication and would SIGABRT otherwise. The first post-boot
    call rasterises and caches; subsequent calls hit the disk cache
    even before QApplication if the file already exists from a
    previous run."""
    try:
        import hashlib
        import os

        from PySide6.QtCore import QByteArray, Qt
        from PySide6.QtGui import QGuiApplication, QPainter, QPixmap
        from PySide6.QtSvg import QSvgRenderer

        svg_src = (
            f'<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">'
            f'<path d="M3 8 L7 12 L13 4" stroke="{color_hex}" '
            f'stroke-width="1.6" fill="none" stroke-linecap="round" '
            f'stroke-linejoin="round"/></svg>'
        )
        cache_dir = os.path.expanduser(
            "~/.cache/PySideApp/qss_icons"
        )
        os.makedirs(cache_dir, exist_ok=True)
        digest = hashlib.sha1(
            (svg_src + f"@{size}").encode("utf-8")
        ).hexdigest()
        out_path = os.path.join(cache_dir, f"check_{digest}.png")
        if not os.path.exists(out_path):
            # QPixmap requires QGuiApplication. If we're called
            # during module load (before main() has constructed it),
            # bail out — the file will be generated on the first
            # post-boot call.
            if QGuiApplication.instance() is None:
                return ""
            renderer = QSvgRenderer(QByteArray(svg_src.encode("utf-8")))
            pix = QPixmap(size, size)
            pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            renderer.render(painter)
            painter.end()
            pix.save(out_path, "PNG")
        return out_path.replace("\\", "/")
    except Exception:
        return ""


def check_url_for_accent() -> str:
    """Return the PNG path for a check mark in the current ACCENT
    color. Computed at call time so a fresh URL is generated when
    the accent changes — the differing path also defeats Qt's
    QSS image-pixmap cache that otherwise sticks to the previous
    render."""
    return _render_check_png(ACCENT)


# Back-compat for any caller still referencing _CHECK_URL — empty
# at module-load time (QPixmap requires QApplication which doesn't
# exist yet at import). All callers should use check_url_for_accent()
# which lazy-renders on first call.
_CHECK_URL = ""


def _accent_rgb_tuple() -> tuple[int, int, int]:
    """Parse the active ACCENT hex into (r, g, b) so QSS rules can
    build accent-derived rgba() colours without hard-coding the
    default purple. Falls back to purple if the hex is malformed."""
    from dough.theme import _hex_to_rgb

    try:
        return _hex_to_rgb(ACCENT)
    except Exception:
        return (150, 125, 225)


def _hex_to_rgb_safe(hex_value: str) -> tuple[int, int, int]:
    """Safe (r, g, b) for any hex string. Falls back to neutral grey
    if the input doesn't parse. Public helper so other modules can
    derive rgba() colours from arbitrary token values without each
    re-implementing the fallback."""
    from dough.theme import _hex_to_rgb

    try:
        return _hex_to_rgb(hex_value)
    except Exception:
        return (128, 128, 128)


def _tooltip_qcolor() -> "QColor":
    """``QColor`` form of ``_tooltip_fill_opaque()`` for the QPalette
    ToolTipBase role. Parses the same opaque rgb/rgba string we hand
    to QSS so palette + stylesheet agree on the tooltip backdrop."""
    s = _tooltip_fill_opaque()
    try:
        inner = s[s.index("(") + 1 : s.index(")")]
        parts = [p.strip() for p in inner.split(",")]
        return QColor(int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        return QColor(28, 30, 34)


def _tooltip_fill_opaque() -> str:
    """Tooltip backdrop colour. Returns ``POPUP_OPAQUE_FILL`` directly,
    which the active theme picks: frosted themes diverge to a
    translucent wash (backstopped by ``apply_elevated_blur`` on
    show), solid + transparent themes keep an opaque value."""
    return POPUP_OPAQUE_FILL


def _build_global_style() -> str:
    ar, ag, ab = _accent_rgb_tuple()
    # Regenerate the check-mark PNG for the current accent (lazy +
    # cached per color). Embedding the path into the QSS string here
    # means the next stamp picks up the new path automatically.
    check_url = check_url_for_accent()
    # NB hover tooltips are drawn by our custom popup (dough/custom_tooltip),
    # NOT Qt's QTipLabel — the QToolTip QSS rule below is a defensive fallback
    # for any stray native tooltip and stays `background: transparent`, so the
    # global style doesn't derive a tooltip fill here.
    return f"""
* {{
    color: {TEXT};
    font-family: 'Inter', 'Segoe UI', 'Noto Sans', sans-serif;
}}
QMainWindow, QDialog, QWidget {{
    background: {BG};
}}
QCheckBox {{
    color: {TEXT};
    spacing: 8px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background: {ink_alpha(0.04)};
}}
QCheckBox::indicator:hover {{
    border-color: {ink_alpha(0.30)};
}}
QCheckBox::indicator:checked {{
    background: rgba({ar},{ag},{ab},0.15);
    border: 1px solid rgba({ar},{ag},{ab},0.45);
    image: url({check_url});
}}
QCheckBox::indicator:checked:hover {{
    background: rgba({ar},{ag},{ab},0.28);
    border-color: rgba({ar},{ag},{ab},0.65);
}}
QCheckBox::indicator:disabled {{
    border-color: {ink_alpha(0.10)};
    background: {ink_alpha(0.02)};
}}
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{
    background: {ink_alpha(0.03)}; width: 8px; border-radius: 4px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: rgba({ar},{ag},{ab},0.4); border-radius: 4px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 8px; background: transparent; }}
QScrollBar::handle:horizontal {{
    background: rgba({ar},{ag},{ab},0.4); border-radius: 4px; min-width: 24px;
}}
QLineEdit {{
    background: {ink_alpha(0.05)};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 12px;
    color: {TEXT};
    selection-background-color: {ACCENT_DEEP};
}}
QLineEdit:focus {{ border-color: {ACCENT}; background: {ink_alpha(0.07)}; }}
QPushButton {{
    background: {ink_alpha(0.05)};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 14px;
}}
QPushButton:hover {{ background: rgba({ar},{ag},{ab},0.15); border-color: {BORDER_ACCENT}; }}
QPushButton:pressed {{ background: rgba({ar},{ag},{ab},0.3); }}
QPushButton#accent {{
    background: {ACCENT_DEEP}; border: 1px solid {ACCENT}; color: white;
}}
QPushButton#accent:hover {{ background: {ACCENT}; }}
QPushButton#ghost {{
    background: transparent; border: none;
}}
QPushButton#ghost:hover {{ background: {ink_alpha(0.06)}; }}
QComboBox {{
    background: {ink_alpha(0.05)};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 12px;
    min-height: 22px;
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {POPUP_OPAQUE_FILL};
    border: none;
    border-radius: 6px;
    selection-background-color: rgba({ar},{ag},{ab},0.25);
    padding: 4px;
}}
QListWidget {{
    background: transparent;
    border: 1px solid {BORDER};
    border-radius: 8px;
    outline-style: none;
}}
QListWidget::item {{
    padding: 8px 10px; border-radius: 6px; margin: 1px 2px;
}}
QListWidget::item:selected {{ background: rgba({ar},{ag},{ab},0.18); }}
QListWidget::item:hover {{ background: {ink_alpha(0.04)}; }}
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_DIM};
    padding: 8px 18px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 500;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{
    color: {ACCENT}; border-bottom: 2px solid {ACCENT};
}}
QSlider::groove:horizontal {{
    height: 3px; background: {ink_alpha(0.12)}; border-radius: 1px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 1px; }}
QSlider::handle:horizontal {{
    width: 12px; height: 12px; margin: -5px 0;
    background: {TEXT}; border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{ background: {ACCENT}; }}
QMenu {{
    background: {POPUP_OPAQUE_FILL};
    border: none;
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 8px 24px 8px 14px; border-radius: 4px;
}}
QMenu::item:selected {{ background: rgba({ar},{ag},{ab},0.2); }}
QMenu::separator {{
    height: 1px; background: {BORDER}; margin: 4px 8px;
}}
QToolTip {{
    /* Hover tooltips are drawn by dough/custom_tooltip (a top-level
       translucent widget that Source-paints popup_paint_qcolor and rides
       KWin blur). This rule only styles any stray native QTipLabel that
       slips past the filter — keep it transparent + minimal so such a
       fallback still reads as a plain pill. */
    background: transparent; color: {TEXT};
    border: none; padding: 4px 8px; border-radius: 6px;
}}
"""


# Initial value — rebuilt by refresh_theme() when the accent changes.
GLOBAL_STYLE = _build_global_style()


def refresh_theme() -> str:
    """Re-read the active theme (after a settings.accent_color or
    settings.theme_mode change) and update every module-level theme
    constant in place. Rebuilds and returns the new GLOBAL_STYLE so
    the caller can push it onto the QApplication. Pair with
    ``icons.refresh_theme()`` (to refresh ICON_ACCENT) and
    ``PlayerBus.theme_changed.emit()`` (to notify subscribers).

    Module-level constants stay the same object identities — we mutate
    the names in place via ``globals()`` so any caller that did
    ``from dough.ui_helpers import ACCENT`` keeps a STALE reference,
    but anyone re-importing or reading ``ui_helpers.ACCENT`` directly
    sees the new value. Subscribers to theme_changed should re-read
    the constant they need on the signal, not cache it in their own
    instance state from __init__.
    """
    global _THEME
    global ACCENT, ACCENT_DEEP, BORDER_ACCENT
    global BG, BG_PANEL, BG_CARD
    global TEXT, TEXT_DIM, TEXT_FAINT, IDLE_TEXT, ERROR_FG, WARN_FG
    global BORDER
    global WASH_HOVER, WASH_PRESSED, HOVER_SUBTLE, HOVER_LIST_ROW
    global SELECTED_ROW, PRESSED_WHITE
    global SURFACE_INPUT, SURFACE_INPUT_FOCUS, DISABLED_FG
    global SLIDER_GROOVE
    global OVERLAY_DARK, OVERLAY_DARK_HOVER, POPUP_OPAQUE_FILL
    global BODY_COLOR, MINI_BODY_COLOR, DIALOG_BODY_COLOR
    global GLOBAL_STYLE
    _THEME = get_active_theme()
    ACCENT = _THEME.accent
    ACCENT_DEEP = _THEME.accent_deep
    BORDER_ACCENT = _THEME.border_accent
    BG = _THEME.bg
    BG_PANEL = _THEME.bg_panel
    BG_CARD = _THEME.bg_card
    TEXT = _THEME.text
    TEXT_DIM = _THEME.text_dim
    TEXT_FAINT = _THEME.text_faint
    IDLE_TEXT = _THEME.idle_text
    ERROR_FG = _THEME.error_fg
    WARN_FG = _THEME.warn_fg
    BORDER = _THEME.border
    WASH_HOVER = _THEME.wash_hover
    WASH_PRESSED = _THEME.wash_pressed
    HOVER_SUBTLE = _THEME.hover_subtle
    HOVER_LIST_ROW = _THEME.hover_list_row
    SELECTED_ROW = _THEME.selected_row
    PRESSED_WHITE = _THEME.pressed_white
    SURFACE_INPUT = _THEME.surface_input
    SURFACE_INPUT_FOCUS = _THEME.surface_input_focus
    DISABLED_FG = _THEME.disabled_fg
    SLIDER_GROOVE = _THEME.slider_groove
    OVERLAY_DARK = _THEME.overlay_dark
    OVERLAY_DARK_HOVER = _THEME.overlay_dark_hover
    POPUP_OPAQUE_FILL = _THEME.popup_opaque_fill
    BODY_COLOR = _THEME.body_color
    MINI_BODY_COLOR = _THEME.mini_body_color
    DIALOG_BODY_COLOR = _THEME.dialog_body_color
    # Re-overlay any user color-token overrides on top of the freshly-
    # read theme defaults. Without this, switching theme mode (or
    # picking a new accent preset) would wipe overrides the user set
    # via Settings → Colors for unrelated tokens (e.g. they overrode
    # WASH_HOVER, then picked a green accent — without this re-overlay,
    # WASH_HOVER snaps back to the default). The accent picker
    # explicitly clears the ACCENT override before calling us so the
    # picker's pick wins for that one token.
    try:
        from dough import color_tokens as _ct

        _ct.load_persisted_overrides()
    except Exception:
        # color_tokens may not be importable in odd boot orders; the
        # original theme defaults remain in place.
        pass
    GLOBAL_STYLE = _build_global_style()
    _propagate_theme_constants()
    apply_app_palette()
    return GLOBAL_STYLE


# Token names mirrored into other modules' namespaces — every constant
# a surface might have imported `from dough.ui_helpers import …` and
# baked into a stylesheet at construction.
_PROPAGATED_TOKENS = (
    "ACCENT", "ACCENT_DEEP", "BORDER_ACCENT",
    "BG", "BG_PANEL", "BG_CARD",
    "TEXT", "TEXT_DIM", "TEXT_FAINT", "IDLE_TEXT", "ERROR_FG", "WARN_FG",
    "BORDER",
    "WASH_HOVER", "WASH_PRESSED", "HOVER_SUBTLE", "HOVER_LIST_ROW",
    "SELECTED_ROW", "PRESSED_WHITE",
    "SURFACE_INPUT", "SURFACE_INPUT_FOCUS", "DISABLED_FG",
    "SLIDER_GROOVE",
    "OVERLAY_DARK", "OVERLAY_DARK_HOVER", "POPUP_OPAQUE_FILL",
    "BODY_COLOR", "MINI_BODY_COLOR", "DIALOG_BODY_COLOR",
    "GLOBAL_STYLE",
)


def _propagate_theme_constants() -> None:
    """Rebind the theme-token constants in every ``dough.*`` module
    that imported them by value.

    The documented contract is "re-read ``ui_helpers.X`` on
    theme_changed", but in practice many surfaces did
    ``from dough.ui_helpers import TEXT`` and bake it into a
    stylesheet at construction. A light↔dark switch changes every
    token, so those stale module-level copies have to be refreshed
    too — otherwise a surface's theme_changed re-stamp rebuilds its
    QSS from the *previous* palette. Centralising it here means each
    surface's handler only has to re-run its own styling; it doesn't
    also have to re-import constants."""
    import sys

    src = sys.modules[__name__]
    values = {n: getattr(src, n) for n in _PROPAGATED_TOKENS}
    for mod_name, mod in list(sys.modules.items()):
        if mod is None or mod is src or not mod_name.startswith("dough."):
            continue
        for name, value in values.items():
            if hasattr(mod, name):
                setattr(mod, name, value)


@contextlib.contextmanager
def theme_swap_guard():
    """Wrap a live theme/accent swap so it doesn't read as a freeze.

    The swap fan-out (``refresh_theme`` + the ~33 ``theme_changed`` slots, each
    re-stamping QSS) is all-synchronous on the GUI thread — the event loop
    can't paint until it returns. This (a) shows a busy cursor (the honest
    signal, since a spinner can't animate while the loop is blocked) and (b)
    suspends repaints on the visible top-levels so the many intermediate
    ``setStyleSheet`` / re-polish calls collapse into ONE repaint at the end
    instead of flickering through half-restyled states. Best-effort: always
    restores the cursor + updates, even if the swap raises."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    suspended = []
    if app is not None:
        app.setOverrideCursor(Qt.CursorShape.BusyCursor)
        for w in app.topLevelWidgets():
            if w.isVisible() and w.updatesEnabled():
                w.setUpdatesEnabled(False)
                suspended.append(w)
    try:
        yield
    finally:
        for w in suspended:
            try:
                w.setUpdatesEnabled(True)
            except RuntimeError:
                pass  # a top-level was deleted mid-swap (e.g. dialog rebuild)
        if app is not None:
            app.restoreOverrideCursor()


def apply_app_palette() -> None:
    """Push a QPalette derived from the active theme onto the
    QApplication.

    GLOBAL_STYLE's QSS only reaches the widget tree it's set on (the
    main window). Separate top-levels — the Settings / cast dialogs,
    QMenu / QToolTip popups — don't inherit it, so any text Qt paints
    from the *palette* rather than from an explicit QSS ``color:`` rule
    falls back to the desktop palette. On a dark desktop that's white
    text, which is invisible on a light dough theme (the dark
    themes never exposed this — the desktop palette happened to match).

    Most backgrounds stay with QSS / per-widget paint so window
    translucency isn't disturbed. The tooltip text roles
    (``ToolTipText``) are pushed so any stray native tooltip still
    reads in the theme ink; hover tooltips themselves are drawn by our
    custom popup (dough/custom_tooltip), which carries its own colour.

    Safe to call before the QApplication exists (no-op)."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    ink = QColor(TEXT)
    pal = app.palette()
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.ToolTipText,
    ):
        pal.setColor(role, ink)
    # Tooltip backdrop — TRANSPARENT. Hover tooltips are our custom popup now,
    # not QTipLabel, so ToolTipBase only governs any stray native tooltip; keep
    # it transparent so QStyle never paints an opaque RECTANGLE behind the pill
    # (the dark-block-at-the-corners bug on dialog-owned / separate-top-level
    # tooltips that the QSS `QToolTip{background:transparent}` rule didn't reach).
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(0, 0, 0, 0))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    # Disabled foreground — the ink at low alpha.
    disabled = QColor(ink)
    disabled.setAlpha(110)
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        pal.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    app.setPalette(pal)


# ── KDE Plasma window-manager hints ─────────────────────────────────────────

_XPROP_OK: Optional[bool] = None


def skip_taskbar_x11(widget: QWidget):
    """
    Tell EWMH-aware window managers (KWin/Mutter/i3/etc.) to keep `widget` out
    of the taskbar and pager. Uses xprop to set _NET_WM_STATE atoms.
    Silently no-ops if xprop is missing or we're on native Wayland (the
    xprop subprocess can't address Wayland surfaces; mini_player.py uses
    the Qt.Tool window flag on Wayland instead).
    """
    global _XPROP_OK
    # Off-X11 (Wayland, Windows, macOS): xprop can't address the surface;
    # bail before subprocessing.
    from dough.platform_compat import is_x11

    if not is_x11():
        return
    if _XPROP_OK is False:
        return
    if _XPROP_OK is None:
        _XPROP_OK = shutil.which("xprop") is not None
        if not _XPROP_OK:
            return

    try:
        wid = int(widget.winId())
    except Exception:
        return
    if wid <= 0:
        return

    def _run():
        try:
            subprocess.run(
                [
                    "xprop",
                    "-id",
                    str(wid),
                    "-f",
                    "_NET_WM_STATE",
                    "32a",
                    "-set",
                    "_NET_WM_STATE",
                    "_NET_WM_STATE_SKIP_TASKBAR,_NET_WM_STATE_SKIP_PAGER,_NET_WM_STATE_ABOVE",
                ],
                check=False,
                timeout=2,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


# ── HiDPI helpers ───────────────────────────────────────────────────────────


def screen_dpr(widget: "Optional[QWidget]" = None) -> float:
    """Effective device-pixel ratio for ``widget``'s screen, or the
    primary screen if no widget is given.

    ``QWidget.devicePixelRatioF()`` is the right answer on multi-monitor
    setups (it tracks the screen the widget's window is currently on)
    once the widget has been mapped; it returns 0.0 before that, which
    we fall through to the primary-screen DPR. Use this everywhere
    cover artwork or any other pixmap is scaled — passing logical
    sizes to Qt at fractional / 2× / 3× scales without DPR-multiplying
    the request size produces soft pixmaps.
    """
    if widget is not None:
        try:
            dpr = widget.devicePixelRatioF()
        except Exception:
            dpr = 0.0
        if dpr >= 1.0:
            return dpr
    s = QGuiApplication.primaryScreen()
    return s.devicePixelRatio() if s is not None else 1.0


# Fixed bucket set for cache-key DPR quantization. Wayland fractional
# scaling reports values like 1.5999999 that drift across launches —
# using the raw DPR in a cache key fragments the disk cache so a
# "loaded" library re-hits the network on every reload. Use the closest
# bucket below for fetch-size + cache-key calculations; keep the raw
# screen_dpr() for the actual scale-pixmap-for-dpr tag (so rendering
# stays sharp).
_DPR_BUCKETS = (1.0, 1.5, 2.0, 3.0)


def dpr_bucket(dpr: float) -> float:
    """Snap ``dpr`` to the nearest entry in ``_DPR_BUCKETS``. Use for
    cache-key + fetch-size math; pass the raw ``screen_dpr()`` to the
    actual pixmap scaling so DPR drift across launches doesn't
    fragment the cover cache."""
    if dpr >= _DPR_BUCKETS[-1]:
        return _DPR_BUCKETS[-1]
    return min(_DPR_BUCKETS, key=lambda b: abs(b - dpr))


def scale_pixmap_for_dpr(
    pix: "QPixmap",
    logical_size: int,
    dpr: "Optional[float]" = None,
) -> "QPixmap":
    """Return a DPR-tagged square pixmap sized for ``logical_size``
    logical points. Scales ``pix`` to ``round(logical_size * dpr)``
    physical pixels via ``KeepAspectRatioByExpanding`` (so square
    targets fill cleanly without letterboxing), centre-crops if one
    axis overshoots, and calls ``setDevicePixelRatio(dpr)`` so Qt
    paints at ``logical_size × logical_size`` logical points using
    the full-resolution texture.

    On a 1.0× display this is a single scale + a no-op DPR tag; on
    1.25× / 1.5× / 2× / 3× displays it's the only thing keeping
    album art from looking soft after Qt's paint-time downscale
    from logical-sized bytes to the physical surface.
    """
    if pix is None or pix.isNull():
        return pix
    if dpr is None:
        dpr = screen_dpr()
    target = max(logical_size, int(round(logical_size * dpr)))
    from PySide6.QtCore import QSize

    scaled = pix.scaled(
        target,
        target,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    # KeepAspectRatioByExpanding always meets-or-exceeds the requested
    # size on both axes for non-square source aspect ratios; centre-crop
    # the overflow so the result is exactly target × target.
    if scaled.size() != QSize(target, target):
        x = max(0, (scaled.width() - target) // 2)
        y = max(0, (scaled.height() - target) // 2)
        scaled = scaled.copy(x, y, target, target)
    scaled.setDevicePixelRatio(dpr)
    return scaled


# ── Async image loader ──────────────────────────────────────────────────────

# LRU bound on the decoded-pixmap cache. QPixmaps are GPU-side textures
# (~30-60kB each at typical 200x200 cover sizes plus rounded-corner
# variants), so an unbounded dict balloons VRAM on big libraries.
# 256 is generous enough that a typical browse never repeats a fetch
# but caps growth to single-digit megabytes.
def fmt_time(ms: int) -> str:
    if ms < 0:
        ms = 0
    s = ms // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_duration_ticks(ticks: int) -> str:
    return fmt_time(ticks // 10_000)


_APP_ICON_CACHE: dict[int, QPixmap] = {}
_APP_ICON_RENDERER: "Optional[QSvgRenderer]" = None


def _load_app_icon_svg_bytes() -> bytes:
    """Read the brand-mark SVG from inside the package via
    ``importlib.resources`` so it resolves in a built/installed wheel
    (a ``Path(__file__).parent.parent / "packaging"`` reference points
    outside the package and is wheel-excluded → blank icon). Returns
    the raw SVG bytes, or ``b""`` if the resource is missing/unreadable
    (the caller then draws a placeholder)."""
    try:
        import importlib.resources as _ir

        res = _ir.files("dough.assets").joinpath("dough.svg")
        if not res.is_file():
            return b""
        return res.read_bytes()
    except Exception:
        return b""


def _draw_placeholder_icon(size: int) -> QPixmap:
    """Last-ditch brand mark when the SVG can't be loaded — a rounded
    accent square so an installed build never renders a blank/empty
    icon. Drawn (not QStyle-based) so it works without a live QStyle."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    try:
        from dough.theme import get_active_theme as _gt

        accent = _gt().accent
    except Exception:
        accent = "#e0a44c"
    path = QPainterPath()
    radius = size * 0.22
    inset = size * 0.12
    path.addRoundedRect(QRectF(inset, inset, size - 2 * inset, size - 2 * inset), radius, radius)
    p.fillPath(path, QColor(accent))
    p.end()
    return pix


def make_app_icon(size: int = 64) -> QPixmap:
    """dough logo, rasterized from the bundled
    ``dough/assets/dough.svg`` at the requested pixel size.
    Single source of truth for the brand mark — edits to the SVG flow
    to every surface (window decoration, tray, QApplication app icon)
    on next launch. Loaded via ``importlib.resources`` so it ships in
    the wheel; falls back to a drawn placeholder if the SVG is missing
    or the renderer is invalid, so an installed build never renders a
    blank icon. Cached per size since the icon is requested 3+ times
    during launch (QApplication, JellytoastWindow, TrayController) and
    the pixmap is immutable."""
    cached = _APP_ICON_CACHE.get(size)
    if cached is not None:
        return cached
    global _APP_ICON_RENDERER
    if _APP_ICON_RENDERER is None:
        from PySide6.QtCore import QByteArray

        svg_bytes = _load_app_icon_svg_bytes()
        _APP_ICON_RENDERER = QSvgRenderer(QByteArray(svg_bytes)) if svg_bytes else QSvgRenderer()
    if not _APP_ICON_RENDERER.isValid():
        # Don't cache the placeholder under the per-size key — if the
        # renderer later becomes valid (it won't here, but keep the
        # contract clean) we'd want a real render. Placeholder is cheap.
        return _draw_placeholder_icon(size)
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _APP_ICON_RENDERER.render(p, QRectF(0, 0, size, size))
    p.end()
    _APP_ICON_CACHE[size] = pix
    return pix


# ── Scrubbable slider ──────────────────────────────────────────────────────
# Used by every slider that should "feel like a music player slider":
# clicking anywhere in the groove jumps to that value, dragging continues
# to scrub. Stock QSlider only page-steps when you click off the handle,
# which is the wrong default for progress / volume / seek bars.
#
# Also kills the focus rectangle — Qt's default focus indicator paints
# blue notches at the slider edges that read as "brackets" against a
# hairline groove. NoFocus removes them and removes the slider from the
# tab order (transport sliders are mouse-only by design).


class ScrubbableSlider(QSlider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _value_at(self, pos: int) -> int:
        # Horizontal sliders read from x; vertical from y. Pick whichever
        # axis matches the current orientation so this class works for
        # both without a separate subclass.
        #
        # ``QStyle.sliderValueFromPosition`` is orientation-naïve — it
        # just maps a 1D pixel position to a value range. Qt's default
        # vertical QSlider visual is *top = max* (volume-control
        # convention), but with ``upsideDown=False`` the function maps
        # position 0 → min, which would flip drag direction relative to
        # the visual. So vertical sliders need ``upsideDown=True`` to
        # match the default visual; ``invertedAppearance`` then flips
        # back as expected. Horizontal sliders pass it straight through.
        if self.orientation() == Qt.Orientation.Horizontal:
            span = max(1, self.width())
            upside_down = self.invertedAppearance()
        else:
            span = max(1, self.height())
            upside_down = not self.invertedAppearance()
        return QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            pos,
            span,
            upside_down,
        )

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            pos = (
                int(e.position().x())
                if self.orientation() == Qt.Orientation.Horizontal
                else int(e.position().y())
            )
            v = self._value_at(pos)
            # setSliderDown so consumer-side position-update slots that
            # gate on isSliderDown() pause their writes during the scrub
            # — otherwise the playback timer fights the user's drag.
            self.setSliderDown(True)
            self.setValue(v)
            self.sliderMoved.emit(v)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton and self.isSliderDown():
            pos = (
                int(e.position().x())
                if self.orientation() == Qt.Orientation.Horizontal
                else int(e.position().y())
            )
            v = self._value_at(pos)
            self.setValue(v)
            self.sliderMoved.emit(v)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            self.setSliderDown(False)
            e.accept()
            return
        super().mouseReleaseEvent(e)


# ── Marquee label ────────────────────────────────────────────────────────


class MarqueeLabel(QLabel):
    """QLabel that scrolls its text horizontally when the text exceeds
    the label's width. Pauses briefly at the start of each cycle so the
    beginning of the text is readable before it moves.

    Pacing: 30fps repaint (smooth) at a sub-pixel speed (slow). The 0.5
    px/tick ≈ 15 px/sec — about a third of typical marquee speed, tuned
    for ambient/glanceable use rather than pulling the eye. Timer is
    only running while a scroll is actually needed; widening the label
    so the text fits cancels the timer."""

    SPEED_PX_PER_TICK = 0.5
    GAP_PX = 48
    PAUSE_TICKS = 90  # ~3s at 33ms tick — longer dwell on the start
    TICK_MS = 33

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._marquee_text = ""
        self._marquee_offset_f = 0.0
        self._marquee_offset = 0
        self._pause = self.PAUSE_TICKS
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(self.TICK_MS)
        if text:
            self.setText(text)

    def setText(self, text: str):
        if text == self._marquee_text:
            return
        self._marquee_text = text or ""
        self._marquee_offset_f = 0.0
        self._marquee_offset = 0
        self._pause = self.PAUSE_TICKS
        super().setText(self._marquee_text)
        self._update_marquee_state()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_marquee_state()

    def _text_width(self) -> int:
        return self.fontMetrics().horizontalAdvance(self._marquee_text)

    def _needs_scroll(self) -> bool:
        return bool(self._marquee_text) and self._text_width() > self.width()

    def _update_marquee_state(self):
        if self._needs_scroll():
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self._marquee_offset_f = 0.0
            self._marquee_offset = 0
            self.update()

    def _tick(self):
        if self._pause > 0:
            self._pause -= 1
            return
        cycle = self._text_width() + self.GAP_PX
        self._marquee_offset_f = (self._marquee_offset_f + self.SPEED_PX_PER_TICK) % cycle
        if self._marquee_offset_f < self.SPEED_PX_PER_TICK:
            self._pause = self.PAUSE_TICKS
        self._marquee_offset = int(self._marquee_offset_f)
        self.update()

    def paintEvent(self, e):
        if not self._needs_scroll():
            super().paintEvent(e)
            return
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()))
        p.setFont(self.font())
        fm = p.fontMetrics()
        baseline = (self.height() + fm.ascent() - fm.descent()) // 2
        text_w = fm.horizontalAdvance(self._marquee_text)
        x = -self._marquee_offset
        p.drawText(x, baseline, self._marquee_text)
        p.drawText(x + text_w + self.GAP_PX, baseline, self._marquee_text)


# ── Cover-overlay button ─────────────────────────────────────────────────


def overlay_disc_colors() -> tuple[str, str]:
    """``(normal, hover)`` fill for a circular button that floats over
    album art — the favourite heart, the mini-player close button, the
    album-tile play / download overlays.

    The disc is the OPPOSITE tone to the ink: a light disc on a light
    theme, a dark disc on a dark theme — exactly inverted, same alpha
    both ways. The glyph on top is theme-ink (black on light,
    near-white on dark), so an inverse-tone disc keeps it readable on
    any cover. Deliberately translucent — the cover reads through."""
    r, g, b = _hex_to_rgb_safe(TEXT)
    base = "255,255,255" if r + g + b < 384 else "0,0,0"
    return f"rgba({base},0.50)", f"rgba({base},0.66)"


def overlay_disc_qcolor(hover: bool = False) -> QColor:
    """QColor form of :func:`overlay_disc_colors` for ``paintEvent`` /
    delegate code (album-tile corner buttons, the download progress
    ring). Same inverse-of-ink logic + alpha as the QSS form."""
    r, g, b = _hex_to_rgb_safe(TEXT)
    v = 255 if r + g + b < 384 else 0
    return QColor(v, v, v, 168 if hover else 128)


class CoverOverlayButton(IconButton):
    """Small circular button pinned to the bottom-right of its parent
    widget — used by the now-playing surfaces to overlay a heart on
    the album art. Repositions on parent resize and only shows while
    the cursor is hovering the cover.

    The visibility tracking uses ``parent.underMouse()`` — which Qt
    treats as true when the cursor is anywhere within the parent's
    geometric bounds *including* descendant widgets. That means the
    overlay button itself doesn't trigger a hide when the cursor moves
    onto it: the parent's Leave fires (Qt routes mouse to the child),
    we schedule a hide with a small grace, then ``underMouse`` reports
    true and we cancel.
    """

    DEFAULT_SIZE = 28
    DEFAULT_MARGIN = 8
    HIDE_GRACE_MS = 80

    def __init__(
        self,
        parent: QWidget,
        size: int = DEFAULT_SIZE,
        margin: int = DEFAULT_MARGIN,
        bordered: bool = True,
    ):
        super().__init__(parent)
        self._anchor_margin = margin
        self._bordered = bordered
        self.setFixedSize(size, size)
        self._apply_circle_style()
        # Re-tone the disc on a live theme switch (light disc on a
        # light theme, dark on a dark one). Lazy import dodges the
        # ui_helpers ↔ player_state import cycle.
        try:
            from dough.player_state import PlayerBus

            PlayerBus.get().theme_changed.connect(self._apply_circle_style)
        except Exception:
            pass
        self.hide()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(self.HIDE_GRACE_MS)
        self._hide_timer.timeout.connect(self._maybe_hide)
        parent.installEventFilter(self)
        self._reposition()

    def _apply_circle_style(self):
        """(Re)build the disc QSS. Theme-aware via overlay_disc_colors()
        — ``bordered=False`` (the mini player) drops the faint rim."""
        radius = self.width() // 2
        normal, hover = overlay_disc_colors()
        if self._bordered:
            ir, ig, ib = _hex_to_rgb_safe(TEXT)
            border = f"1px solid rgba({ir},{ig},{ib},0.18)"
            hover_border = f"    border-color: rgba({ir},{ig},{ib},0.35);\n"
        else:
            border = "none"
            hover_border = ""
        self.setStyleSheet(f"""
            QPushButton {{
                background: {normal};
                border: {border};
                border-radius: {radius}px;
            }}
            QPushButton:hover {{
                background: {hover};
{hover_border}            }}
        """)

    def eventFilter(self, obj, event):
        et = event.type()
        if et == QEvent.Type.Resize:
            self._reposition()
        elif et == QEvent.Type.Enter:
            self._hide_timer.stop()
            self.show()
            self.raise_()
        elif et == QEvent.Type.Leave:
            self._hide_timer.start()
        return False

    def _maybe_hide(self):
        p = self.parentWidget()
        if p is None:
            return
        if not p.underMouse():
            self.hide()

    def _reposition(self):
        p = self.parentWidget()
        if p is None:
            return
        x = p.width() - self.width() - self._anchor_margin
        y = p.height() - self.height() - self._anchor_margin
        self.move(max(0, x), max(0, y))
        self.raise_()


# ── Empty-state widget ──────────────────────────────────────────────────


class EmptyState(QWidget):
    """Centered glyph + headline + optional sub-line + optional action
    button. Drop into any scroll area, grid, or list whose data set
    can be legitimately empty (no albums on the server, queue empty,
    no search results, etc.). Replaces "blank viewport" failure modes
    that read as "is this loading or broken?" with an intentional
    "this is empty, here's why" affordance.

    Use ``set_state(headline=..., sub=..., glyph=...)`` to repurpose
    the same instance for different empty conditions on one surface.
    The ``action_clicked`` signal fires when the optional button is
    pressed — callers wire it to whatever recovery action makes sense
    (Retry, Browse, etc.)."""

    GLYPH_PX = 64  # default glyph point size
    VPAD = 18  # spacing between rows

    action_clicked = Signal()

    def __init__(
        self,
        glyph: str = "♪",  # ♪ — default to "nothing playing" semantic
        headline: str = "",
        sub: str = "",
        action_label: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(self.VPAD)
        outer.addStretch(1)

        # Glyph — large muted character. Unicode rather than an SVG so
        # the widget has no external resource dependency and renders
        # at any size without re-rasterising.
        self._glyph_label = QLabel(glyph)
        gf = QFont()
        gf.setPixelSize(self.GLYPH_PX)
        self._glyph_label.setFont(gf)
        self._glyph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._glyph_label, 0, Qt.AlignmentFlag.AlignHCenter)

        self._headline_label = QLabel(headline)
        self._headline_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._headline_label.setWordWrap(True)
        outer.addWidget(self._headline_label)

        self._sub_label = QLabel(sub)
        self._sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub_label.setWordWrap(True)
        outer.addWidget(self._sub_label)
        if not sub:
            self._sub_label.hide()

        # Action row — button is created up front but hidden unless
        # action_label is provided so callers can flip it on later
        # via set_state without rebuilding the widget.
        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.addStretch(1)
        self._action_btn = QPushButton(action_label or "")
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._action_btn.clicked.connect(self.action_clicked.emit)
        action_row.addWidget(self._action_btn)
        action_row.addStretch(1)
        outer.addLayout(action_row)
        if not action_label:
            self._action_btn.hide()

        outer.addStretch(1)

        self._apply_styling()
        # Live-accent: re-stamp the baked QSS on every theme/accent swap so
        # a visible overlay isn't left in the old palette (e.g. a white
        # headline on a light body after a dark->light swap = invisible).
        # Per-surface re-stamp contract; see architecture_live_accent.md.
        # PySide6 auto-disconnects this bound-method slot when the widget is
        # destroyed, so call sites that recreate the overlay don't leak.
        from dough.player_state import PlayerBus

        PlayerBus.get().theme_changed.connect(self._apply_styling)

    def _apply_styling(self) -> None:
        """(Re-)stamp the per-widget QSS from the current theme tokens.
        Called at construction and on every ``PlayerBus.theme_changed``.
        Reads the ui_helpers module-level tokens by name so each call
        picks up the values ``refresh_theme()`` rebound in place."""
        from dough.design_tokens import TYPE_BODY, TYPE_CAPTION, type_qss

        # Theme ink at low alpha — faint glyph, legible on either theme.
        self._glyph_label.setStyleSheet(f"color: {ink_alpha(0.22)};")
        self._headline_label.setStyleSheet(
            f"color: {TEXT}; {type_qss(TYPE_BODY)} font-weight: 500;"
        )
        self._sub_label.setStyleSheet(f"color: {TEXT_DIM}; {type_qss(TYPE_CAPTION)}")
        self._action_btn.setStyleSheet(f"""
            QPushButton {{
                background: {WASH_HOVER};
                border: 1px solid {ink_alpha(0.10)};
                border-radius: 8px;
                padding: 6px 14px;
                color: {TEXT};
                font-weight: 500;
            }}
            QPushButton:hover {{ background: {WASH_PRESSED}; }}
        """)

    def set_state(
        self,
        *,
        glyph: Optional[str] = None,
        headline: Optional[str] = None,
        sub: Optional[str] = None,
        action_label: Optional[str] = None,
    ):
        """Update any subset of the visible content. Pass ``""`` for
        ``sub`` or ``action_label`` to hide those rows; pass ``None``
        (default) to leave them untouched."""
        if glyph is not None:
            self._glyph_label.setText(glyph)
        if headline is not None:
            self._headline_label.setText(headline)
        if sub is not None:
            self._sub_label.setText(sub)
            self._sub_label.setVisible(bool(sub))
        if action_label is not None:
            self._action_btn.setText(action_label)
            self._action_btn.setVisible(bool(action_label))


# ── Popup menu helpers ──────────────────────────────────────────────────


def apply_elevated_blur(widget, corner_radius: int = 0) -> bool:
    """Install compositor blur behind ``widget`` when the active theme
    asks for it (any theme with ``blur=True`` — the frosted modes).

    Top-level "elevated" surfaces (combo popups, QMenus, hover
    tooltips, the volume popup window) read this so the frosted-glass
    look extends past the main window body — without it the body is
    blurred but a popup floating free over the wallpaper would be a
    flat translucent rectangle. No-op for non-frosted themes (nothing
    to blur, the surface stays whatever its fill says).

    Idempotent; callers may invoke on every show. ``widget`` must
    have a platform window (``windowHandle()``) — call after the
    popup is shown, or via ``showEvent`` / ``aboutToShow``.
    """
    try:
        from dough import blur as _blur
        from dough.theme import get_active_theme

        if not get_active_theme().blur:
            return False
        # elevated=True: these surfaces carry their own QSS frost fill,
        # so a backend with a tinted blur material (Windows Acrylic)
        # drops its tint instead of double-veiling the popup.
        return _blur.apply(widget, True, corner_radius=corner_radius, elevated=True)
    except Exception:
        return False


def opaque_menu(parent=None, *, menu_cls=None, blur_corner_radius: int = 4) -> "QMenu":
    """``QMenu`` that's guaranteed opaque even when the parent window
    has ``WA_TranslucentBackground`` set. On Wayland a popup-class
    window inherits the ancestor's translucency attribute at QWindow
    creation, and Qt 6 doesn't reliably honour a later
    ``setAttribute(WA_TranslucentBackground, False)`` because the
    surface was already constructed as ARGB. The result: ghost text
    bleeds through the menu over content beneath.

    The fix is layered — every layer is defensive against a different
    failure mode, and together they produce opaque pixels even if any
    single mechanism misbehaves:

    - ``WA_TranslucentBackground=False`` + ``WA_NoSystemBackground=
      False`` ask the platform plugin for an opaque surface.
    - ``WA_OpaquePaintEvent=True`` skips Qt's pre-paint clear pass.
    - ``setAutoFillBackground(True)`` + opaque palette ``Window`` /
      ``Base`` colours fill the widget rect with solid pixels before
      QSS paints — even if the surface ends up ARGB, the autofill
      writes alpha=255 across the whole popup.
    - The stylesheet then paints over those filled pixels with the
      menu's visual treatment. Selection uses the accent colour at
      moderate alpha (we lift the accent live from the active theme
      so a runtime accent change takes effect on the next menu open).

    Use this everywhere you'd otherwise call ``QMenu(parent)`` so the
    fix lives in one spot. Pass ``menu_cls`` to harden a ``QMenu``
    subclass instead of a vanilla ``QMenu`` (e.g. a stay-open multi-select
    menu) while keeping the same opacity/blur treatment. ``blur_corner_radius``
    shapes the compositor blur region to the menu's rounded rect — pass the
    same radius the caller's QSS uses (the top-bar dropdowns override to 8 px)
    so the blur doesn't bleed past the visible corners into a square halo;
    defaults to 4 to match this function's own QSS ``border-radius``.
    """
    from dough.theme import _hex_to_rgb

    menu = (menu_cls or QMenu)(parent)
    # Keep the menu surface translucent so its QSS rgba background composites
    # over compositor blur (the lifted-frosted-glass look) ONLY when blur is
    # verified active behind it. On solid / transparent themes — or a frosted
    # theme on a box where blur didn't land — there's nothing to backstop
    # see-through, so harden to an opaque panel instead of a thin pill.
    if popup_blur_active():
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # corner_radius matches the QMenu QSS border-radius (4 px)
        # below, so KWin's blur region is shaped to the rounded pill
        # instead of the rectangular bounding box. Without this the
        # corners read as SQUARE — blurred wallpaper shows through
        # outside the QSS clip but inside the blur-rect.
        #
        # Deferred via QTimer.singleShot(0, ...) so the blur runs
        # AFTER Qt has finished laying out the menu in this event-
        # loop tick — at aboutToShow time the menu's width/height may
        # still be stale, making the rounded blur region too small
        # and leaving most of the menu surface unblurred.
        from PySide6.QtCore import QTimer

        def _do_blur(m=menu):
            # Round the BLUR region a touch tighter than the QSS corner so
            # its (1-bit, aliased) rounded edge tucks UNDER the menu's
            # smooth antialiased QSS corner instead of peeking past it as a
            # jagged sliver — that mismatch is what read as "weird corners".
            apply_elevated_blur(m, corner_radius=blur_corner_radius + 2)

        menu.aboutToShow.connect(
            lambda m=menu: QTimer.singleShot(0, lambda: _do_blur(m))
        )
    else:
        _harden_popup_opacity(menu)
    a_r, a_g, a_b = _hex_to_rgb(ACCENT)
    # Frosty fill when blur is verified behind the menu (lets the blur lift
    # through), opaque otherwise — mirrors the WA_TranslucentBackground gate
    # above so the menu's paint and its surface translucency agree.
    menu.setStyleSheet(f"""
        QMenu {{
            background-color: {popup_body_fill()};
            color: {TEXT};
            border: none;
            border-radius: 4px;
            padding: 4px;
        }}
        QMenu::item {{
            background-color: transparent;
            /* Symmetric horizontal padding — the old right-padding of
               22 reserved space for a shortcut/arrow column we don't
               use, which made every menu wider than its longest entry
               needed. Symmetric padding tightens the menu to its
               content + matches the visual balance left↔right. */
            padding: 7px 14px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background-color: rgba({a_r},{a_g},{a_b},0.28);
            color: {TEXT};
        }}
        QMenu::separator {{
            height: 1px;
            background: {BORDER};
            margin: 4px 8px;
        }}
    """)
    return menu


def popup_fill_qcolor() -> QColor:
    """Opaque QColor form of the active theme's ``POPUP_OPAQUE_FILL``
    token — for the palette autofill backstop in ``_harden_popup_opacity``
    where an opaque palette ``Window`` is required to paint solid
    pixels under the QSS. Alpha is STRIPPED here even if the token
    is rgba (frosted themes diverge ``popup_opaque_fill`` to a
    translucent composite for tooltip painting; the autofill backstop
    still wants the opaque rgb, since menus/combos that go through
    ``_harden_popup_opacity`` need solid fill). Use ``popup_paint_qcolor``
    instead when the caller WANTS the alpha (e.g. translucent tooltip
    paint over a blurred surface)."""
    try:
        s = POPUP_OPAQUE_FILL
        inner = s[s.index("(") + 1 : s.index(")")]
        parts = [p.strip() for p in inner.split(",")]
        return QColor(int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        return QColor(20, 22, 26)


def popup_blur_active() -> bool:
    """True when an elevated popup (tooltip / menu / combo / About) should
    render as translucent glass — i.e. the theme wants blur AND real compositor
    blur is *verified* behind it. False on non-frosted themes, or a frosted
    theme on a box where blur didn't land, so popups harden to a near-opaque
    panel instead of reading thin / see-through. The popup analogue of the
    blur-status check in :func:`body_color_tuple`. Never raises."""
    try:
        from dough import blur
        from dough.theme import get_active_theme

        return bool(get_active_theme().blur) and (
            blur.status() is blur.BlurStatus.ACTIVE
        )
    except Exception:
        return False


def popup_paint_qcolor() -> QColor:
    """Status-aware elevated-popup body colour for PAINTING a popup backdrop
    (the tooltip pill, the About dialog body, the _Selector dropdown). Returns
    the full rgba QColor from ``POPUP_OPAQUE_FILL`` — but, like
    :func:`body_color_tuple`, the alpha tracks whether real blur is verified
    behind the popup: the translucent glass tone when :func:`popup_blur_active`,
    a near-opaque panel otherwise, so popups never read thin / see-through on a
    box without working blur. Opaque (rgb) fills return unchanged."""
    try:
        s = POPUP_OPAQUE_FILL
        inner = s[s.index("(") + 1 : s.index(")")]
        parts = [p.strip() for p in inner.split(",")]
        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
        a = int(round(float(parts[3]) * 255)) if len(parts) >= 4 else 255
    except Exception:
        return QColor(20, 22, 26)
    if a < 255 and not popup_blur_active():
        # Frosted popup with no verified blur behind it — harden to a
        # near-opaque panel (matches the body fallback in body_color_for).
        from dough.theme import get_active_theme

        a = max(a, getattr(get_active_theme(), "fallback_body_alpha", None) or 240)
    elif a < 255:
        # Real blur verified — cap the alpha so the blur lifts through as
        # "a slight lift, still frosty" instead of a near-solid panel
        # (the light family's token is tuned opaque at 0.80). Mirrors
        # popup_body_fill() for the QSS-painted popups.
        a = min(a, int(round(_POPUP_FROST_ALPHA * 255)))
    return QColor(r, g, b, max(0, min(255, a)))


# Target alpha for a blur-backed popup body — low enough that the
# compositor blur reads through as "a slight lift, still frosty" rather
# than a solid panel. The light family's POPUP_OPAQUE_FILL was tuned to
# 0.80 (vs the dark family's 0.65), so its menus / combos read as stark
# white over the frosted body; capping the painted alpha here when real
# blur is verified brings both families to the same frosted depth.
_POPUP_FROST_ALPHA = 0.62


def popup_body_fill() -> str:
    """QSS background fill for a blur-AWARE popup (the ``opaque_menu`` menus,
    the _Selector dropdown, the About body). When real compositor blur is
    verified behind the popup, return the ``POPUP_OPAQUE_FILL`` hue at a
    capped frosted alpha (``_POPUP_FROST_ALPHA``) so the blur lifts through;
    otherwise return ``POPUP_OPAQUE_FILL`` unchanged so the popup stays
    opaque and legible on a box with no working blur. Never raises.

    Bare ``QMenu`` / ``QComboBox`` popups (GLOBAL_STYLE) still use the raw
    opaque token — they get no ``blur.apply()`` so they MUST stay opaque."""
    if not popup_blur_active():
        return POPUP_OPAQUE_FILL
    try:
        r, g, b, a = _parse_qss_color(POPUP_OPAQUE_FILL)
    except Exception:
        return POPUP_OPAQUE_FILL
    a = min(a, _POPUP_FROST_ALPHA)
    return f"rgba({r}, {g}, {b}, {a:.2f})"


def _parse_qss_color(s: str) -> tuple[int, int, int, float]:
    """Parse a QSS colour literal — ``#rrggbb``, ``rgb(r,g,b)``, or
    ``rgba(r,g,b,a)`` — into ``(r, g, b, a)`` with ``a`` in 0..1. Falls
    back to opaque mid-grey on anything unparseable. Never raises."""
    try:
        s = s.strip()
        if s.startswith("#"):
            from dough.theme import _hex_to_rgb

            r, g, b = _hex_to_rgb(s)
            return r, g, b, 1.0
        inner = s[s.index("(") + 1 : s.index(")")]
        parts = [p.strip() for p in inner.split(",")]
        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
        a = float(parts[3]) if len(parts) >= 4 else 1.0
        return r, g, b, a
    except Exception:
        return (128, 128, 128, 1.0)


def volume_popup_fill() -> str:
    """Opaque, NEUTRAL fill for the volume slider popup, baked to read as
    the SAME elevated tone as the volume BUTTON's hover highlight.

    The popup is a child surface (can't ride KWin blur), so it has to be a
    flat OPAQUE pill — but it must still match the hovered volume button it
    sits over, which is ``wash_hover`` riding the blurred body. So on the
    FROSTED themes we reproduce that highlight directly: composite the
    theme's ``wash_hover`` over a representative backdrop, then neutralise
    to gray (the button wash is hueless, so r==g==b — no blue cast) and
    force it opaque (the mini-player right-edge popup must hide the volume
    button + ✕ it overlaps — a translucent fill would let them ghost
    through).

    The backdrop is this theme's ``body_color`` over a neutral mid-gray
    stand-in for the (unknowable) blurred wallpaper. That mid-gray term is
    the crux: an earlier attempt composited the wash over the body's raw RGB
    alone and read TOO DARK; the real desktop behind the body lightens it,
    so the stand-in restores that. With it the popup lands at the hovered
    button's apparent tone in each family — ≈224 on light, ≈74 on dark.

    The prior implementation took the raw luminance of ``popup_opaque_fill``
    and DROPPED its alpha. That's fine on dark (the token's RGB is already a
    dark 67) but baked the light token's near-white *wash* (248,248,248 @
    0.80) to a stark 248 — far whiter than the 0.55-alpha button highlight
    it sits over, so the light popup read as a bright white slab. (A later
    ``min(lum, 238)`` cap only shaved the worst off and still read white.)

    Solid (non-frosted) themes carry an already-opaque ``rgb()``
    ``popup_opaque_fill`` (a == 1.0) tuned to the elevated tone; those are
    returned as-is (neutralised), unchanged. Reads the live theme so a
    dark↔light flip retints it."""
    from dough.theme import get_active_theme

    th = get_active_theme()
    pr, pg, pb, pa = _parse_qss_color(th.popup_opaque_fill)
    body = getattr(th, "body_color", None)
    if pa < 1.0 and body and len(body) == 4:
        # Frosted theme: rebuild the button-hover highlight as an opaque
        # tone. wash_hover over (body over neutral-gray) — see docstring.
        wr, wg, wb, wa = _parse_qss_color(th.wash_hover)
        body_a = body[3] / 255.0
        _NEUTRAL = 128.0
        back = [body_a * body[i] + (1.0 - body_a) * _NEUTRAL for i in range(3)]
        r = wa * wr + (1.0 - wa) * back[0]
        g = wa * wg + (1.0 - wa) * back[1]
        b = wa * wb + (1.0 - wa) * back[2]
    else:
        r, g, b = pr, pg, pb
    # Perceived (WCAG) luminance → neutral gray; drops any cool tint while
    # preserving the composited lightness.
    lum = max(0, min(255, round(0.2126 * r + 0.7152 * g + 0.0722 * b)))
    return f"rgb({lum}, {lum}, {lum})"


# Backdrop blur for the volume popup (in-app "acrylic"). Tunable by eye.
VOLUME_BACKDROP_RADIUS = 12  # logical px of blur + grab padding


def volume_popup_veil_qcolor() -> "QColor":
    """Semi-transparent veil painted OVER the software-blurred backdrop in the
    volume popup so the slider handle / accent fill / padlock stay legible
    while the frost still reads through. The neutral ``volume_popup_fill()``
    tone at a per-family reduced alpha (lower than the opaque pill so the blur
    shows). Tunable by eye."""
    from PySide6.QtGui import QColor

    from dough.theme import get_active_theme

    fill = volume_popup_fill()  # "rgb(l, l, l)"
    try:
        inner = fill[fill.index("(") + 1 : fill.index(")")]
        r, g, b = (int(x) for x in inner.split(",")[:3])
    except Exception:
        r = g = b = 128
    light = not getattr(get_active_theme(), "dark", False)
    # Dark dropped 0.55 → 0.42: at 0.55 the neutral veil over the (already
    # dark) captured backdrop reconstituted the flat opaque-pill tone, so the
    # frost was invisible. A thinner dark veil lets the blurred backdrop read
    # through. Light stays 0.62 (it already reads well). Tunable by eye.
    a = int(round((0.62 if light else 0.42) * 255))
    return QColor(r, g, b, a)


def capture_blurred_backdrop(
    host: "QWidget", geom: "QRect", *, radius_logical: int = VOLUME_BACKDROP_RADIUS
) -> "Optional[QPixmap]":
    """Grab the ``host`` pixels under ``geom`` and return a software-blurred
    QPixmap of that region — the in-app "frosted glass" backdrop for the volume
    popup (a child surface that can't ride compositor blur).

    KEY: ``QWidget.grab()`` re-renders the widget tree into an offscreen
    pixmap; it does NOT round-trip the Wayland compositor, so the "grab is
    blur-blind" caveat (about *compositor* blur) does not apply to a frost we
    paint ourselves. The grab is expanded by ``radius_logical`` on every side so
    the blur has padding to bleed into (no sharp clipped edge); the caller draws
    the result offset by ``-radius_logical`` and clips to the body's rounded
    rect. A fast, predictable downscale→upscale (SmoothTransformation) blur —
    cheap enough for a hover popup and free of QGraphicsScene coordinate
    pitfalls. Returns None on any failure → caller falls back to the opaque
    pill. Never raises."""
    try:
        from PySide6.QtCore import Qt as _Qt

        if host is None:
            return None
        r = int(radius_logical)
        grab_rect = geom.adjusted(-r, -r, r, r)
        src = host.grab(grab_rect)  # QPixmap, physical size, dpr-tagged
        if src is None or src.isNull() or src.width() < 2 or src.height() < 2:
            return None
        dpr = src.devicePixelRatio() or screen_dpr(host)
        # Downscale→upscale box blur. Stronger shrink = softer frost; scale the
        # shrink with the (device) radius so it reads consistent across DPRs.
        shrink = max(3, int(round(r * dpr / 2.0)))
        sw = max(1, src.width() // shrink)
        sh = max(1, src.height() // shrink)
        small = src.scaled(
            sw, sh, _Qt.AspectRatioMode.IgnoreAspectRatio, _Qt.TransformationMode.SmoothTransformation
        )
        blurred = small.scaled(
            src.width(),
            src.height(),
            _Qt.AspectRatioMode.IgnoreAspectRatio,
            _Qt.TransformationMode.SmoothTransformation,
        )
        blurred.setDevicePixelRatio(dpr)
        return blurred
    except Exception:
        return None


def _harden_popup_opacity(popup: "QWidget") -> None:
    """Force ``popup`` to render opaque even when its ancestor window
    has ``WA_TranslucentBackground`` set.

    Applies the same multi-layer fix used by ``opaque_menu``:
    translucent-background OFF, system-background ON, opaque paint
    event flag set, autoFillBackground True, palette ``Window`` /
    ``Base`` set to the theme's opaque popup fill. Idempotent — safe
    to call on the same widget multiple times.

    Use directly on custom popups (volume sliders, drag chips, etc.)
    where ``QMenu`` / ``QComboBox`` plumbing doesn't apply. Combobox
    callers should use ``_OpaqueComboBox`` from ``settings_dialog`` so
    the per-popup show-time fixup also runs.
    """
    popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    popup.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
    popup.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
    popup.setAutoFillBackground(True)
    pal = popup.palette()
    fill = popup_fill_qcolor()
    pal.setColor(pal.ColorRole.Window, fill)
    pal.setColor(pal.ColorRole.Base, fill)
    popup.setPalette(pal)


# ── Seeded-radio entry point (album / artist / genre) ────────────────────
#
# The track-radio flow seeds an INSTANT_MIX queue with the track itself
# and lets ``queue_manager.RadioFeeder`` fetch similar tracks once
# playback nears the tail (see ``SongsView._on_context_menu``). Album /
# artist / genre have no single seed *item* to drop into the queue, so
# ``start_seed_radio`` must fetch the initial batch itself (off the GUI
# thread via ``async_io.run_async``) before emitting ``queue_play_now``.
# The RadioFeeder then auto-extends from the stamped ``seed_kind``
# exactly as it does for the track flow.


def start_seed_radio(seed_kind: str, source_id: str, source_label: str) -> None:
    """Fetch the initial radio batch for ``seed_kind`` and install it as
    the live INSTANT_MIX queue.

    ``seed_kind`` is one of ``"album"`` / ``"artist"`` / ``"genre"``:

      * ``album``  → ``get_instant_mix(source_id)``
      * ``artist`` → ``get_similar_songs(source_id)``
      * ``genre``  → ``get_genre_radio(source_label)``

    The provider call is a network round-trip, so it runs on the shared
    pool. On an empty result (or any failure) nothing is emitted — the
    user just sees no change, matching the "show nothing fancy on
    failure" contract. Called from the view-internal right-click menus
    (``LibraryGrid.contextMenuEvent``, ``_GenresListView``) that each
    own their ``QMenu``.
    """
    if seed_kind == "genre":
        if not source_label:
            return
    elif not source_id:
        return

    from dough import async_io
    from dough.providers import get_provider

    def _fetch():
        api = get_provider()
        if seed_kind == "album":
            return api.get_instant_mix(source_id)
        if seed_kind == "artist":
            return api.get_similar_songs(source_id)
        if seed_kind == "genre":
            return api.get_genre_radio(source_label)
        return []

    def _on_result(tracks):
        if not tracks:
            return
        from dough.player_state import PlayerBus, QueueContext, QueueKind

        ctx = QueueContext(
            kind=QueueKind.INSTANT_MIX,
            source_id=source_id,
            source_label=source_label,
            seed_kind=seed_kind,
        )
        PlayerBus.get().queue_play_now.emit(list(tracks), 0, ctx)

    async_io.run_async(_fetch, on_result=_on_result)


# ── "Create smart playlist from this X" entry point ──────────────────────


def open_create_smart_playlist(
    parent: QWidget,
    kind: str,
    name: str,
    item: "Optional[dict]" = None,
) -> None:
    """Right-click *Create smart playlist from this <kind>* flow.

    ``kind`` is one of ``"artist"`` / ``"album"`` / ``"genre"`` /
    ``"track"``. Builds a schema-valid rules dict via the matching
    ``dough.smart_playlists.presets`` ``from_*`` factory, opens the
    smart-playlist editor pre-populated (rules + a suggested name),
    and on save appends the new entry to ``settings.smart_playlists``
    so it shows up on the Smart Playlists tab.

    ``item`` (optional) is the full item dict for the seeded entity —
    the album/track factories use it to extract Genres + ProductionYear
    for the era-vibe recipes. Passing only ``name`` still works (the
    factories degrade gracefully); pass ``item`` whenever the caller
    already has it for richer rule seeding.

    Naming follows the Spotify/Plexamp short-suffix idiom — "More like
    X", "Deep Cuts: X", "X Discoveries" — to read well in the
    Playlists list typography.

    Non-blocking — opens the editor with a save callback rather than
    waiting on the dialog.
    """
    if not name:
        return
    from dough.smart_playlist_editor import open_smart_playlist_editor
    from dough.smart_playlists import presets as _presets

    hint: "Optional[str]" = None
    if kind == "artist":
        rules = _presets.from_artist(name)
        suggested = f"Deep Cuts: {name}"
    elif kind == "album":
        rules = _presets.from_album(item if item is not None else name)
        suggested = f"More like {name}"
        # Surface the missing-metadata case so the user knows WHY the
        # recipe only has a year rule. The album / track recipes both
        # rely on Genres for the "more like" feel — a library without
        # genre tags makes the recipe degrade to era-only.
        if isinstance(item, dict) and not (item.get("Genres") or []):
            hint = f"{name} has no genre tags, add some to help suggestions."
    elif kind == "genre":
        rules = _presets.from_genre(name)
        suggested = f"{name} Discoveries"
    elif kind == "track":
        rules = _presets.from_track(item if item is not None else name)
        suggested = f"More like {name}"
        if isinstance(item, dict) and not (item.get("Genres") or []):
            hint = f"{name} has no genre tags, add some to help suggestions."
    else:
        return

    def _persist(entry):
        from dough.settings import get_settings

        entries = list(get_settings().smart_playlists)
        entries.append(entry)
        get_settings().smart_playlists = entries

    def _on_save_and_play(entry, dismiss):
        """Save & Play: persist, then resolve+play. The editor stays
        open in a Loading state until ``dismiss`` is called — pass
        it through to ``play_entry`` as the ``on_complete`` hook so
        the dialog closes the moment playback actually starts (or
        empty / error feedback lands)."""
        from dough.smart_playlists.play import play_entry

        _persist(entry)
        play_entry(entry, parent, on_complete=dismiss)

    open_smart_playlist_editor(
        parent,
        preset_rules=rules,
        suggested_name=suggested,
        hint=hint,
        on_save=_persist,
        on_save_and_play=_on_save_and_play,
    )


# ── Auto-fade scroll bar ─────────────────────────────────────────────────


class AutoFadeScrollBar(QScrollBar):
    """A scroll bar that renders ONLY the pill — no track, no lane, no
    background of any kind. Bypasses Qt's native style (which would
    otherwise paint a track lane even when QSS sets the bar's
    background transparent) by overriding paintEvent and drawing the
    handle directly.

    The pill fades to invisible after a short idle period. Any scroll
    movement (wheel, drag, programmatic value change, or mouse hover
    over the bar itself) wakes it back to full opacity. The fade is
    driven by a QPropertyAnimation on the custom handleAlpha property,
    not a QGraphicsOpacityEffect — the effect approach left a faint
    rendered backdrop visible against translucent body colors."""

    IDLE_MS = 900  # how long the pill stays visible after the last interaction
    FADE_MS = 220  # cross-fade duration
    PILL_ALPHA = 110  # peak alpha of the handle (0-255); ~0.43
    PILL_RADIUS = 3
    PILL_INSET = 2  # px shrink applied to the handle rect for breathing room

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._handle_alpha = 0
        self._hovered = False
        # Translucent + no system background → Qt won't paint anything
        # behind the widget; combined with our paintEvent skipping
        # everything except the handle, the lane is truly invisible.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        # Strip any application-level QSS that would otherwise reach
        # this widget. We paint everything manually.
        self.setStyleSheet("QScrollBar { background: transparent; border: none; }")

        self._anim = QPropertyAnimation(self, b"handleAlpha", self)
        self._anim.setDuration(self.FADE_MS)

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._fade_out)

        self.valueChanged.connect(self._wake)

    # ── Custom property used for the fade animation ────────────────────

    def get_handle_alpha(self) -> int:
        return self._handle_alpha

    def set_handle_alpha(self, alpha: int):
        alpha = max(0, min(255, int(alpha)))
        if alpha != self._handle_alpha:
            self._handle_alpha = alpha
            self.update()  # repaint with new alpha

    handleAlpha = Property(int, get_handle_alpha, set_handle_alpha)

    # ── Paint just the pill ────────────────────────────────────────────

    def paintEvent(self, _event):
        if self._handle_alpha <= 0:
            return  # nothing to draw
        # Look up the handle rect from the style — accounts for the
        # current scroll position + range automatically.
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_ScrollBar,
            opt,
            QStyle.SubControl.SC_ScrollBarSlider,
            self,
        )
        # Inset on the long axis so the pill has a tiny breath of
        # space at each end of its slot — reads as a floating element
        # rather than something flush to invisible bounds.
        if self.orientation() == Qt.Orientation.Vertical:
            handle.adjust(0, self.PILL_INSET, 0, -self.PILL_INSET)
        else:
            handle.adjust(self.PILL_INSET, 0, -self.PILL_INSET, 0)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        # Brighter on hover so the pill answers cursor presence.
        peak = 180 if self._hovered else self.PILL_ALPHA
        # Scale alpha down by the current handleAlpha fraction.
        alpha = int(peak * (self._handle_alpha / 255))
        # Theme ink so the handle reads on a light theme too.
        _hr, _hg, _hb = _hex_to_rgb_safe(TEXT)
        painter.setBrush(QColor(_hr, _hg, _hb, alpha))
        painter.drawRoundedRect(handle, self.PILL_RADIUS, self.PILL_RADIUS)

    def _wake(self, *_):
        self._anim.stop()
        self._anim.setStartValue(self._handle_alpha)
        self._anim.setEndValue(255)
        self._anim.start()
        self._idle_timer.start(self.IDLE_MS)

    def _fade_out(self):
        self._anim.stop()
        self._anim.setStartValue(self._handle_alpha)
        self._anim.setEndValue(0)
        self._anim.start()

    def enterEvent(self, event):
        self._hovered = True
        self._wake()
        self._idle_timer.stop()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._idle_timer.start(self.IDLE_MS)
        self.update()
        super().leaveEvent(event)


def install_autofade_scrollbars(scroll_area: QScrollArea):
    """Replace the QScrollArea's default scroll bars with auto-fading
    versions. The bar widgets paint nothing but their own pill — track,
    lane, and page backgrounds are skipped entirely so only the handle
    renders against the body."""
    v = AutoFadeScrollBar(Qt.Orientation.Vertical, scroll_area)
    h = AutoFadeScrollBar(Qt.Orientation.Horizontal, scroll_area)
    scroll_area.setVerticalScrollBar(v)
    scroll_area.setHorizontalScrollBar(h)
    # Under QStyleSheetStyle a QScrollArea paints an OPAQUE background
    # (pure black in every theme — it reads the unthemed app palette) in
    # the scrollbar gutter beneath our transparent bars: an 8px solid
    # strip over the frost/body on any page whose content overflows.
    # Descendant rules on the host view (e.g. "QWidget#x QScrollArea")
    # do NOT cure it — the QSS must sit on the widget itself. Appended
    # so a caller's own stylesheet survives. The selector only matches
    # QScrollArea proper; QListView callers (QAbstractScrollArea branch)
    # are unaffected and don't exhibit the bug.
    if isinstance(scroll_area, QScrollArea):
        existing = scroll_area.styleSheet()
        scroll_area.setStyleSheet(
            (existing + "\n" if existing else "")
            + "QScrollArea { background: transparent; border: none; }"
        )
    return v, h
