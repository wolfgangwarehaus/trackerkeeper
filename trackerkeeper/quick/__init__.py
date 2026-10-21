"""The phone interface — a Qt Quick front end over the same fleet.

The Widgets dashboard is a desktop utility window: dense columns, 26 px
buttons, a frosted body and a tray to live in. On a phone shell every one of
those is wrong — Plasma Mobile forces the window maximized and borderless,
draws no tray items, disables blur, and a finger can't hit a 26 px tick. So a
phone shell gets this instead: the same catalog, checkers, settings and
notifications (``trackerkeeper.fleet`` is the shared seam), drawn in QML by
``quick/qml/Main.qml``.

Which front end runs is decided once, at launch (:func:`wanted`):
``TRACKERKEEPER_UI=quick|widgets`` forces either; otherwise an UNDOCKED phone
shell (Plasma Mobile, Phosh) gets this one. If the QML can't load, :func:`run`
returns None and the caller falls back to the classic window — never nothing
on screen. Same shape as jellytoast's phone interface.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

QML_DIR = Path(__file__).resolve().parent / "qml"
ENV_UI = "TRACKERKEEPER_UI"


def is_phone_shell() -> bool:
    """A phone shell: Plasma Mobile (``startplasmamobile`` exports
    ``PLASMA_PLATFORM=phone:handset`` and ``QT_QUICK_CONTROLS_MOBILE=true``)
    or Phosh (``XDG_CURRENT_DESKTOP=Phosh:GNOME``). Linux only."""
    import sys

    if not sys.platform.startswith("linux"):
        return False
    if os.environ.get("PLASMA_PLATFORM", "").startswith("phone"):
        return True
    if os.environ.get("QT_QUICK_CONTROLS_MOBILE", "").lower() in ("1", "true"):
        return True
    return "phosh" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()


def is_docked() -> bool:
    """Plasma Mobile's docked (convergence) mode — the quick setting that
    gives windows their decorations back for a monitor + keyboard. Read from
    ``plasmamobilerc`` ``[General] convergenceModeEnabled``; False when
    unreadable. A docked phone is a desktop, so it gets the desktop UI."""
    cfg = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "plasmamobilerc"
    group = ""
    try:
        for line in cfg.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                group = line[1:-1]
            elif group == "General" and line.startswith("convergenceModeEnabled="):
                return line.split("=", 1)[1].strip().lower() == "true"
    except OSError:
        pass
    return False


def available() -> bool:
    """Whether this build can run the Qt Quick UI at all (a bundle that
    pruned QtQuick can't)."""
    try:
        import PySide6.QtQml  # noqa: F401
        import PySide6.QtQuick  # noqa: F401
        import PySide6.QtQuickControls2  # noqa: F401
    except Exception:
        return False
    return (QML_DIR / "Main.qml").is_file()


def wanted() -> bool:
    """Start the phone interface instead of the Widgets window?"""
    forced = os.environ.get(ENV_UI, "").strip().lower()
    if forced in ("quick", "widgets"):
        return forced == "quick" and available()
    return is_phone_shell() and not is_docked() and available()


def build_engine(app, *, start: bool = True):
    """The bridge objects + a loaded ``QQmlApplicationEngine``. ``start=False``
    skips the launch check and the periodic timer (tests)."""
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle

    from trackerkeeper.quick.fleet_model import Fleet
    from trackerkeeper.quick.icons import IconProvider
    from trackerkeeper.quick.theme import Theme

    # Our own components on the Basic style — never the platform style: Plasma
    # exports QT_QUICK_CONTROLS_STYLE=org.kde.breeze, which pip's PySide6
    # can't load (jellytoast learned this one first).
    if QQuickStyle.name() != "Basic":
        QQuickStyle.setStyle("Basic")
    engine = QQmlApplicationEngine()
    bridge = {"fleet": Fleet(engine, start=start), "theme": Theme(engine)}
    engine.addImageProvider("icon", IconProvider())
    ctx = engine.rootContext()
    for name, obj in bridge.items():
        ctx.setContextProperty(name, obj)
    engine._tk_keep = bridge   # keep the Python wrappers alive with the engine
    engine.load(str(QML_DIR / "Main.qml"))
    return engine


def run(app, single_instance=None) -> "int | None":
    """Run the phone interface to exit. ``None`` if it couldn't load — the
    caller falls back to the classic window."""
    try:
        engine = build_engine(app)
    except Exception:
        logger.exception("phone interface failed to start — using the classic window")
        return None
    roots = engine.rootObjects()
    if not roots:
        logger.error("phone interface failed to load (QML errors above) — "
                     "using the classic window")
        return None
    win = roots[0]

    def _raise():
        win.show()
        win.raise_()
        win.requestActivate()

    if single_instance is not None:
        single_instance.raise_requested.connect(_raise)
    size = os.environ.get("TRACKERKEEPER_QUICK_SIZE", "")   # e.g. 402x874 — desktop dev
    if "x" in size:
        w, h = (int(v) for v in size.lower().split("x", 1))
        win.resize(w, h)
    app._tk_quick_engine = engine
    # No tray on a phone shell (Plasma Mobile registers a host but draws no
    # items), so closing the window ends the app rather than hiding it.
    app.setQuitOnLastWindowClosed(True)
    return app.exec()
