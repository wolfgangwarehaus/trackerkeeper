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
from dough.platform_compat import IS_MACOS


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


# Held for the process lifetime so faulthandler's file sink isn't garbage-
# collected / closed out from under it on GUI-subsystem builds.
_CRASH_LOG_FH = None


def _diag_log_dir():
    """Best-effort writable dir for crash / diagnostic logs, resolved WITHOUT a
    QApplication (this runs before one exists). Windows → ``%LOCALAPPDATA%\\
    {app}``; otherwise ``$XDG_CACHE_HOME`` (or ``~/.cache``) ``/{app}`` — where
    ``{app}`` is the configured identity slug. Returns None if nothing writable."""
    import os as _os

    from dough import identity as _ident

    try:
        if _os.name == "nt":
            base = _os.environ.get("LOCALAPPDATA") or _os.path.expanduser("~")
        else:
            base = _os.environ.get("XDG_CACHE_HOME") or _os.path.join(
                _os.path.expanduser("~"), ".cache"
            )
        d = _os.path.join(base, _ident.app())
        _os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        return None


def _enable_faulthandler() -> None:
    """Convert a hard native crash (e.g. a cross-thread ``~QObject``) into an
    attributable Python + C stack instead of silent process death.

    On a normal interpreter this writes to stderr. Under a GUI-subsystem
    interpreter (a pipx ``.exe`` gui-script on Windows / ``pythonw``)
    ``sys.stderr`` is ``None`` and a bare ``enable()`` raises ``RuntimeError`` —
    which would both kill the app before ``app.exec()`` AND leave a windowed
    build's crash with zero trace. So there we instead point faulthandler at a
    ``crash.log`` file and attach a file log (``{app}.log``, level from
    ``DOUGH_LOG_LEVEL``, default INFO) the user can hand back."""
    import faulthandler

    if sys.stderr is not None:
        try:
            faulthandler.enable()
        except Exception:
            # e.g. a stderr replaced by a fileno-less stream (test capture,
            # embedded hosts) — losing the crash hook must never be fatal.
            pass
        return

    # stderr is None (GUI-subsystem build) — route to files instead.
    d = _diag_log_dir()
    if not d:
        return
    import os as _os

    global _CRASH_LOG_FH
    try:
        _CRASH_LOG_FH = open(_os.path.join(d, "crash.log"), "a", buffering=1)
        faulthandler.enable(file=_CRASH_LOG_FH, all_threads=True)
    except Exception:
        pass
    try:
        import logging as _logging

        from dough import identity as _ident

        level = (_os.environ.get("DOUGH_LOG_LEVEL") or "INFO").upper()
        fh = _logging.FileHandler(_os.path.join(d, f"{_ident.app()}.log"))
        fh.setFormatter(
            _logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root = _logging.getLogger()
        root.addHandler(fh)
        root.setLevel(getattr(_logging, level, _logging.INFO))
    except Exception:
        pass


def _reconcile_autostart() -> None:
    """Re-assert an ENABLED launch-on-login entry at boot. ``enable()`` rewrites
    the OS entry (XDG .desktop / Run key / LaunchAgent), self-healing a stale
    ``Exec``/command after the executable or venv moved. Strictly opt-in: dough
    never turns autostart ON — only the Settings toggle does; if it's off or
    unsupported this is a no-op. Best-effort, never fatal."""
    try:
        from dough import autostart

        if autostart.is_supported() and autostart.is_enabled():
            autostart.enable()
    except Exception:
        pass


def _wire_notifications(bus) -> None:
    """Route ``AppBus.notify`` (title, body) to the desktop-notification
    backend. App code emits the signal from its real events with zero imports;
    ``dough.notifications`` no-ops where unsupported and never raises."""

    def _notify(title: str, body: str = "") -> None:
        try:
            from dough import notifications

            notifications.notify(title, body)
        except Exception:
            pass

    bus.notify.connect(_notify)


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
      * **window geometry** — restored on launch, saved on quit;
      * **launch on login** — re-asserts a user-enabled autostart entry (the
        Settings toggle turns it on; dough never does);
      * **desktop notifications** — ``AppBus.notify.emit(title, body)`` reaches
        the OS notification backend (silent no-op where unsupported).

    ``identity`` (optional) is a mapping forwarded to :func:`dough.configure`
    (``org`` / ``app`` / ``display_name``). NOTE: for the import-time font scale
    to honour a custom identity, set it in ``dough.identity`` or call
    ``configure()`` BEFORE importing the app; Qt names, the AUMID, and QSettings
    all honour it here regardless.
    """
    from dough import identity as ident

    if identity:
        ident.configure(**identity)

    # Crash/diagnostic logging first, so a native SIGSEGV during boot is still
    # attributable (writes to files under a GUI-subsystem interpreter where
    # stderr is None). Best-effort; never fatal.
    _enable_faulthandler()

    _setup_hidpi()
    try:
        from dough.windows_shortcut import set_process_app_user_model_id

        set_process_app_user_model_id()
    except Exception:
        pass

    # macOS: set the application-menu name BEFORE QApplication builds the
    # native menu, so a from-source run reads the app name rather than "Python"
    # (a frozen .app already gets it from CFBundleName). Only ordering
    # constraint here. No-op off macOS.
    if IS_MACOS:
        from dough import macos_menubar

        macos_menubar.set_app_name()

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(ident.app())
    app.setApplicationDisplayName(ident.display_name())
    app.setOrganizationName(ident.org())
    app.setApplicationVersion(__version__)
    # The installed .desktop is named by the reverse-DNS app-id
    # (io.github.{owner}.{app}), so the desktop file name must carry
    # desktop_id() for the taskbar to associate the window with its installed
    # icon. Verified live (KDE, 2026-07-03): on Wayland this value becomes the
    # window's app_id; on X11 Qt exports it as _KDE_NET_WM_DESKTOP_FILE (KDE's
    # association path) while WM_CLASS stays the bare applicationName slug —
    # which is why the .desktop's StartupWMClass keeps the slug (non-KDE X11
    # matches on WM_CLASS). The KWin machinery survives the app_id change by
    # design: the noborder rule and the drag_repaint effect both match the
    # bare slug as a SUBSTRING (proven: noBorder=true under the new app_id).
    app.setDesktopFileName(ident.desktop_id())

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

    # Persist any pending QSettings writes (window geometry, theme overrides, …)
    # before the process exits. A hard quit that skips the window's closeEvent
    # (e.g. app.quit() from a tray/menu) still reaches aboutToQuit — without
    # this the most recent toggles are silently lost on the next launch.
    def _flush_settings():
        try:
            get_settings().flush()
        except Exception:
            pass

    app.aboutToQuit.connect(_flush_settings)

    # Launch-on-login + desktop notifications — the shipped subsystems, wired:
    # autostart re-asserts an entry the user enabled (Settings toggle) so it
    # survives a moved executable; AppBus.notify(title, body) reaches the OS
    # notification backend. Both opt-in and best-effort.
    _reconcile_autostart()
    _wire_notifications(AppBus.get())

    # macOS: the global menu bar (App/File/Edit/View/Window/Help) + native
    # window chrome (transparent titlebar / full-size content view) — native
    # conventions a Qt app otherwise lacks. Pure PySide6; only built on macOS,
    # best-effort/no-op elsewhere.
    if IS_MACOS:
        from dough import macos_menubar, macos_window

        macos_menubar.install(win)
        macos_window.apply(win)

    # KDE Wayland borderless chrome: the main window stays server-side-decorated
    # (so compositor blur survives a drag — a Qt-frameless window loses it) and a
    # KWin `noborder` Force rule strips the visible decoration. Reconcile it
    # BEFORE show so a fresh launch never flashes a titlebar; idempotent +
    # self-healing, a no-op off KDE Wayland. `native_window_border` opts back into
    # the real server-side titlebar.
    from dough import noborder

    if get_settings().native_window_border:
        noborder.remove_main_window_noborder()
    else:
        noborder.install_main_window_noborder()

    win.show()

    # KWin drag-repaint effect — installed AFTER show (off the first-paint path;
    # it only matters once a drag begins). Forces KWin's full-repaint render path
    # while one of the app's windows is dragged, killing the NVIDIA-EGL stale-blur
    # "line artifact" (KWin bug 455526/457727). Idempotent, best-effort, a no-op
    # off KDE Wayland; DOUGH_NO_DRAG_REPAINT=1 removes it instead.
    from dough import drag_repaint

    drag_repaint.sync()

    return app.exec()


def main() -> None:
    """The default entry: boot dough with the placeholder canvas. A fork either
    swaps the placeholder or calls :func:`run_app` with its own content."""
    sys.exit(run_app(lambda _window: _placeholder()))


if __name__ == "__main__":
    main()
