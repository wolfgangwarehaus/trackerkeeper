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
    _factory = None  # optional callable -> AppBus (subclass); see set_factory()

    @classmethod
    def set_factory(cls, factory) -> None:
        """Register the factory that builds the process-wide bus the first time
        :meth:`get` is called. An app with a richer bus — a subclass carrying its
        own signals (jellytoast's ``PlayerBus``, ~60 of them) — registers it here
        so every leaf widget that calls ``AppBus.get()`` shares the ONE bus. Must
        run BEFORE the first ``get()`` (raises otherwise): the singleton is built
        once and cached, so a late factory would silently split the bus."""
        if AppBus._instance is not None:
            raise RuntimeError(
                "AppBus singleton already exists — set_factory() must run before "
                "the first AppBus.get()"
            )
        AppBus._factory = factory

    @classmethod
    def get(cls) -> "AppBus":
        """The process-wide bus. Created lazily (via the registered factory, if
        any) so importing this module never requires a running QApplication. The
        singleton lives on ``AppBus`` itself, so a subclass's ``get()`` returns
        the same instance."""
        if AppBus._instance is None:
            AppBus._instance = AppBus._factory() if AppBus._factory else cls()
        return AppBus._instance


def get_bus() -> AppBus:
    """Convenience accessor — equivalent to ``AppBus.get()``."""
    return AppBus.get()
