"""macOS global menu bar + Dock-click reopen — native-app conventions.

macOS shows a single global menu bar (App / File / Edit / View / Window / Help).
A Qt app with no ``QMenuBar`` presents as a menu-less window — the #1 "this is a
half-finished port" tell. This module builds that bar (Qt relocates it to the
global menu area and maps About/Settings/Quit into the bold, app-named
application menu by QAction *menu role* — the role, not the label text, drives
the relocation) plus the Dock-click reopen behaviour. macOS-only; imported
lazily from ``app.main()`` behind ``IS_MACOS``.

Mostly pure PySide6. The two native touch-points — overwriting the running
bundle's ``CFBundleName`` (:func:`set_app_name`) and stripping Qt's auto-added
Services / About-Qt items (:func:`_strip_app_menu_noise`) — reach through
pyobjc, imported lazily and guarded so a non-mac or missing-pyobjc box degrades
to a no-op rather than raising. Everything here is best-effort and never raises
into boot.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import QApplication, QMenuBar, QMessageBox

from dough import identity, metadata
from dough.bus import AppBus

logger = logging.getLogger(__name__)


def set_app_name(name: str | None = None) -> None:
    """Force the macOS application-menu name. A from-source ``python -m dough``
    run shows "Python" in the menu bar (no .app bundle → the process name); the
    frozen ``.app`` already gets the right name from its ``CFBundleName``.
    Overwrite the running bundle's ``CFBundleName`` via pyobjc so the app menu
    reads the display name either way. ``name`` defaults to
    :func:`identity.display_name`. MUST run before ``QApplication`` builds the
    native menu. Best-effort; never raises."""
    if name is None:
        name = identity.display_name()
    try:
        from Foundation import NSBundle  # lazy + guarded (macOS + pyobjc only)

        bundle = NSBundle.mainBundle()
        if bundle is None:
            return
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info is not None:
            info["CFBundleName"] = name
    except Exception:
        pass


def install(window, help_url: str | None = None) -> None:
    """Build the global menu bar + Dock-reopen. Call once, after the window
    exists. ``help_url`` defaults to the metadata homepage. Never raises."""
    try:
        if help_url is None:
            try:
                help_url = metadata.projections().get("homepage_url", "")
            except Exception:
                help_url = ""
        _install_menubar(window, help_url)
        _install_dock_reopen(window)
        # Deferred: Qt builds the native app menu (with its auto-added Services
        # + About Qt) on the event loop, so strip them once it exists.
        QTimer.singleShot(0, _strip_app_menu_noise)
        logger.info("macOS menu bar installed")
    except Exception as e:  # pragma: no cover — macOS-only
        logger.info("macOS menu bar setup failed: %s", e)


# ── menu bar ────────────────────────────────────────────────────────────


def _install_menubar(window, help_url: str):
    name = identity.display_name()

    mb = QMenuBar()
    window.setMenuBar(mb)  # QMainWindow → relocated to the global menu bar on Mac
    window._dough_macos_menubar = mb  # keep a strong ref

    SK = QKeySequence.StandardKey
    MR = QAction.MenuRole

    # App-menu items — Qt RELOCATES these into the native (bold, app-named)
    # application menu by their menu ROLE (not their label text), no matter
    # which menu they're attached to. We hang them on File (they vanish from
    # File on relocation) rather than create a dedicated menu, which would be
    # left empty + show a redundant app-named menu in the bar.
    file_menu = mb.addMenu("File")
    _act(file_menu, window, f"About {name}", role=MR.AboutRole, slot=lambda: _about(window))
    _act(file_menu, window, "Settings…", role=MR.PreferencesRole, key=SK.Preferences,
         slot=lambda: AppBus.get().show_settings.emit())
    _act(file_menu, window, f"Quit {name}", role=MR.QuitRole, slot=lambda: _quit())
    _act(file_menu, window, "Close Window", key=SK.Close,
         slot=lambda: (QApplication.activeWindow() or window).close())

    # Edit — present so system text shortcuts + the Services menu work; each
    # item dispatches to the focused widget's matching method.
    edit_menu = mb.addMenu("Edit")
    for label, key, meth in (
        ("Undo", SK.Undo, "undo"),
        ("Redo", SK.Redo, "redo"),
        (None, None, None),
        ("Cut", SK.Cut, "cut"),
        ("Copy", SK.Copy, "copy"),
        ("Paste", SK.Paste, "paste"),
        ("Select All", SK.SelectAll, "selectAll"),
    ):
        if label is None:
            edit_menu.addSeparator()
            continue
        _act(edit_menu, window, label, key=key,
             slot=lambda _=False, m=meth: _dispatch_edit(m))

    # View
    view_menu = mb.addMenu("View")
    _act(view_menu, window, "Enter Full Screen", key=SK.FullScreen,
         slot=lambda: _toggle_fullscreen(window))

    # Window
    win_menu = mb.addMenu("Window")
    _act(win_menu, window, "Minimize", key="Ctrl+M",
         slot=lambda: (QApplication.activeWindow() or window).showMinimized())
    _act(win_menu, window, "Zoom", slot=lambda: _zoom(window))

    # Help
    help_menu = mb.addMenu("Help")
    _act(help_menu, window, f"{name} Help",
         slot=lambda: help_url and QDesktopServices.openUrl(QUrl(help_url)))


def _strip_app_menu_noise():
    """Remove Qt's auto-added **Services** submenu + **About Qt** from the
    application menu — both are noise for an end-user app (Services surfaces the
    OS's Development tools; About Qt is a toolkit detail) — and collapse the
    separators they leave behind. Native (pyobjc) because Qt owns these items;
    lazy + guarded. Best-effort; never raises."""
    try:
        from AppKit import NSApplication  # lazy + guarded (macOS + pyobjc only)

        app = NSApplication.sharedApplication()
        app.setServicesMenu_(None)
        main = app.mainMenu()
        if main is None or main.numberOfItems() == 0:
            return
        appmenu = main.itemAtIndex_(0).submenu()
        if appmenu is None:
            return
        for title in ("Services", "About Qt"):
            idx = appmenu.indexOfItemWithTitle_(title)
            if idx >= 0:
                appmenu.removeItemAtIndex_(idx)
        _collapse_separators(appmenu)
    except Exception as e:  # pragma: no cover — macOS-only
        logger.debug("strip app-menu noise failed: %s", e)


def _collapse_separators(menu):
    """Drop leading / trailing / consecutive separator items."""
    while menu.numberOfItems() and menu.itemAtIndex_(0).isSeparatorItem():
        menu.removeItemAtIndex_(0)
    while menu.numberOfItems() and menu.itemAtIndex_(
        menu.numberOfItems() - 1
    ).isSeparatorItem():
        menu.removeItemAtIndex_(menu.numberOfItems() - 1)
    i = 1
    while i < menu.numberOfItems():
        if menu.itemAtIndex_(i).isSeparatorItem() and menu.itemAtIndex_(
            i - 1
        ).isSeparatorItem():
            menu.removeItemAtIndex_(i)
        else:
            i += 1


def _act(menu, parent, text, *, role=None, key=None, slot=None):
    a = QAction(text, parent)
    # Always set a role explicitly: default to NoRole so Qt's macOS text
    # heuristic can't silently relocate a non-app item (e.g. anything that
    # looks like "settings"/"about"/"quit") into the application menu.
    a.setMenuRole(role if role is not None else QAction.MenuRole.NoRole)
    if key is not None:
        a.setShortcut(QKeySequence(key))
    if slot is not None:
        a.triggered.connect(slot)
    menu.addAction(a)
    return a


# ── Dock-click reopen (boot-safe) ───────────────────────────────────────


class _DockReopenFilter(QObject):
    """Re-show the main window when the app is activated with no window
    visible (Dock click). Boot-safe: only acts AFTER it has observed the
    window visible at least once, so it never fights the boot reveal."""

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._shown_once = False

    def eventFilter(self, obj, event):
        w = self._window
        try:
            if w.isVisible():
                self._shown_once = True
            elif (
                self._shown_once
                and event.type() == QEvent.Type.ApplicationStateChange
                and QApplication.applicationState() == Qt.ApplicationState.ApplicationActive
            ):
                w.show()
                w.raise_()
                w.activateWindow()
        except Exception:  # pragma: no cover — macOS-only
            pass
        return False


def _install_dock_reopen(window):
    f = _DockReopenFilter(window)
    window._dough_macos_dock_reopen = f
    QApplication.instance().installEventFilter(f)


# ── helpers ─────────────────────────────────────────────────────────────


def _about(window):
    from dough import __version__

    title = identity.display_name()
    summary = ""
    try:
        summary = metadata.load().get("summary", "")
    except Exception:
        pass
    body = f"<b>{title}</b>"
    if __version__:
        body += f"<br>Version {__version__}"
    if summary:
        body += f"<br><br>{summary}"
    QMessageBox.about(window, title, body)


def _quit():
    QApplication.quit()


def _dispatch_edit(method: str):
    w = QApplication.focusWidget()
    fn = getattr(w, method, None)
    if callable(fn):
        fn()


def _toggle_fullscreen(window):
    w = QApplication.activeWindow() or window
    (w.showNormal if w.isFullScreen() else w.showFullScreen)()


def _zoom(window):
    w = QApplication.activeWindow() or window
    (w.showNormal if w.isMaximized() else w.showMaximized)()
