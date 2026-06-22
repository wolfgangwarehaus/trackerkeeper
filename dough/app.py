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


def run_app(content_factory, *, identity=None, single_instance=True) -> int:
    """Boot a dough app and run it to exit. Does the cross-platform Qt setup
    every warehaus app needs — HiDPI rounding, app identity, persisted theme
    overrides, the theme-matched palette + icon — then shows an ``AppWindow``
    whose content is ``content_factory(window)``. Returns the process exit code.

    Wires the chrome an app shouldn't re-solve, all unconditionally:
      * **single instance** — a second launch raises the running window instead
        of opening a duplicate (pass ``single_instance=False`` to opt out);
      * **persisted theme** — accent / colour overrides load BEFORE the first
        widget so every surface stamps from the saved palette;
      * **the settings dialog** — wired to ``AppBus.show_settings``;
      * **window geometry** — restored on launch, saved on quit.

    ``identity`` (optional) is a mapping forwarded to :func:`dough.configure`
    (``org`` / ``app`` / ``display_name``). NOTE: for the import-time font scale
    to honour a custom identity, set it in ``dough.identity`` or call
    ``configure()`` BEFORE importing the app; Qt names, the AUMID, and QSettings
    all honour it here regardless.
    """
    from dough import identity as ident

    if identity:
        ident.configure(**identity)

    _setup_hidpi()
    try:
        from dough.windows_shortcut import set_process_app_user_model_id

        set_process_app_user_model_id()
    except Exception:
        pass

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(ident.app())
    app.setApplicationDisplayName(ident.display_name())
    app.setOrganizationName(ident.org())
    app.setApplicationVersion(__version__)
    # NOTE: the installed .desktop is named by the reverse-DNS app-id
    # (io.github.{owner}.{app}), so for the Wayland taskbar to associate the
    # window with its icon this should be ident.desktop_id(), and the .desktop's
    # StartupWMClass should match (X11). Left as the bare slug until both DEs can
    # be smoke-tested on a real desktop — see docs/TODO.md (baking Beat 2 defer).
    app.setDesktopFileName(ident.app())

    # Single instance: hand off to the already-running copy rather than opening
    # a second window. Keep the lock object alive for the process lifetime.
    si = None
    if single_instance:
        from dough.single_instance import SingleInstance

        si = SingleInstance(ident.app())
        if not si.acquire():
            return 0  # another instance was found and signalled to come forward
        app._dough_single_instance = si

    # Persisted accent / colour overrides must load BEFORE the first widget, so
    # every surface stamps from the saved palette rather than the defaults.
    from dough.color_tokens import load_persisted_overrides

    load_persisted_overrides()

    from dough.ui_helpers import apply_app_palette, make_app_icon

    app.setWindowIcon(QIcon(make_app_icon(64)))
    apply_app_palette()

    from dough.settings import get_settings
    from dough.window import AppWindow

    win = AppWindow(title=ident.display_name())
    get_settings().restore_geometry(win)  # no-op if nothing saved → keeps default
    win.set_content(content_factory(win))

    def _open_settings():
        from dough.settings_dialog import SettingsDialog

        SettingsDialog(win).exec()

    AppBus.get().show_settings.connect(_open_settings)

    from dough.single_instance import force_foreground

    if si is not None:
        si.raise_requested.connect(lambda: force_foreground(win))
    AppBus.get().open_main_window.connect(lambda: force_foreground(win))

    win.show()
    return app.exec()


def main() -> None:
    """The default entry: boot dough with the placeholder canvas. A fork either
    swaps the placeholder or calls :func:`run_app` with its own content."""
    sys.exit(run_app(lambda _window: _placeholder()))


if __name__ == "__main__":
    main()
