"""dough app entry point.

``main()`` does the cross-platform Qt setup every warehaus app needs — HiDPI
rounding, app identity, the theme-matched palette, the app icon — then shows an
``AppWindow`` with a placeholder. Fork it: set your identity, swap the
placeholder for your content, wire your own controllers onto ``AppBus``.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dough import __version__, ui_helpers
from dough.bus import AppBus

# Fork: rename to your app. Keep org == app so the QSettings handle matches
# design_tokens._load_font_scale (QSettings("dough", "dough")).
APP_NAME = "dough"


def _setup_hidpi() -> None:
    """Resolution independence: pass fractional scale through untouched (Qt 6.7+
    talks wp_fractional_scale_v1 to KWin natively) and let widgets size from the
    scaled tokens. Must run before QApplication is constructed."""
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


def _placeholder() -> QWidget:
    """The blank canvas a fresh fork boots to. Replace with your content via
    ``window.set_content(...)``."""
    from dough.design_tokens import BTN_PRIMARY, TYPE_BODY, TYPE_DISPLAY, button_qss, type_qss

    w = QWidget()
    w.setStyleSheet("background: transparent;")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(40, 40, 40, 56)
    lay.addStretch(1)

    title = QLabel("dough")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet(f"color: {ui_helpers.TEXT}; {type_qss(TYPE_DISPLAY)}")
    lay.addWidget(title)

    sub = QLabel("your app starts here — edit dough/app.py")
    sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sub.setStyleSheet(f"color: {ui_helpers.TEXT_DIM}; {type_qss(TYPE_BODY)}")
    lay.addWidget(sub)

    btn = QPushButton("Open Settings")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(button_qss(BTN_PRIMARY))
    btn.clicked.connect(lambda: AppBus.get().show_settings.emit())
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(btn)
    row.addStretch(1)
    lay.addSpacing(18)
    lay.addLayout(row)

    lay.addStretch(2)
    return w


def main() -> None:
    _setup_hidpi()
    try:
        from dough.windows_shortcut import set_process_app_user_model_id

        set_process_app_user_model_id()
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_NAME)

    from dough.ui_helpers import apply_app_palette, make_app_icon

    app.setWindowIcon(QIcon(make_app_icon(64)))
    apply_app_palette()

    from dough.window import AppWindow

    win = AppWindow(title=APP_NAME)
    win.set_content(_placeholder())

    def _open_settings():
        from dough.settings_dialog import SettingsDialog

        SettingsDialog(win).exec()

    AppBus.get().show_settings.connect(_open_settings)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
