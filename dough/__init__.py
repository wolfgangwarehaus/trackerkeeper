"""dough — the wolfgang warehaus app base. See docs/PHILOSOPHY.md."""

from dough.identity import configure

__version__ = "0.1.0"

# Curated public API. configure() is eager — it must be callable before anything
# heavy imports (see dough.identity: the font-scale loader reads QSettings at
# import time). The rest resolve LAZILY via __getattr__ so `import dough` stays
# light: importing the chrome (window / app / design_tokens) would trip that
# import-time read before a fork's configure() could run. Reach for them
# (dough.run_app, dough.AppWindow, …) AFTER configuring.
_LAZY = {
    "run_app": ("dough.app", "run_app"),
    "AppWindow": ("dough.window", "AppWindow"),
    "AppBus": ("dough.bus", "AppBus"),
    "get_bus": ("dough.bus", "get_bus"),
    "Settings": ("dough.settings", "Settings"),
    "get_settings": ("dough.settings", "get_settings"),
}

__all__ = ["__version__", "configure", *_LAZY]


def __getattr__(name: str):
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(target[0]), target[1])
