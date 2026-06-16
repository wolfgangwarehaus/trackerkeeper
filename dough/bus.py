"""AppBus — the app-wide Qt signal bus (dough's decoupling spine).

UI surfaces emit *intents*; controllers react and emit *state*; neither side
holds a reference to the other. dough ships only the GENERIC chrome/app
signals here. An app adds its own by subclassing AppBus or standing up a
second domain bus (jellytoast, for instance, carries ~60 music signals on a
PlayerBus that subclasses this) — the base stays minimal on purpose.

Singleton access mirrors the pattern the lifted widgets expect::

    from dough.bus import AppBus
    AppBus.get().theme_changed.connect(widget.restyle)
    AppBus.get().theme_changed.emit()
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class AppBus(QObject):
    # ── Appearance ────────────────────────────────────────────────────
    theme_changed = Signal()          # palette / mode / font swap → re-stamp the app
    accent_changed = Signal(str)      # new accent hex

    # ── Window / navigation ───────────────────────────────────────────
    open_main_window = Signal()       # single-instance re-activate, tray, autostart
    show_settings = Signal()          # open the settings dialog
    navigate = Signal(object)         # generic navigation intent; app defines the payload

    # ── System ────────────────────────────────────────────────────────
    hotkeys_changed = Signal()        # global hotkeys reconfigured
    dpr_changed = Signal()            # device-pixel-ratio changed → re-rasterize cached art

    _instance: "AppBus | None" = None

    @classmethod
    def get(cls) -> "AppBus":
        """The process-wide bus. Created lazily so importing this module
        never requires a running QApplication."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


def get_bus() -> AppBus:
    """Convenience accessor — equivalent to ``AppBus.get()``."""
    return AppBus.get()
