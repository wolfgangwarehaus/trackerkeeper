"""trackerkeeper — the wolfgang warehaus app base. See docs/PHILOSOPHY.md."""

from trackerkeeper.identity import configure


def _resolve_version() -> str:
    """The single version source (docs/BAKING.md §2 principle 4). In a built
    install, setuptools-scm has written ``trackerkeeper/_version.py`` from the git tag.
    In a raw source checkout it hasn't, so fall back to the installed-package
    metadata, then to a sentinel — never hardcode a number that could drift."""
    try:
        from trackerkeeper._version import version  # generated at build by setuptools-scm

        return version
    except ImportError:
        pass
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("trackerkeeper")
        except PackageNotFoundError:
            pass
    except ImportError:
        pass
    return "0.0.0+unknown"


__version__ = _resolve_version()

# Curated public API. configure() is eager — it must be callable before anything
# heavy imports (see trackerkeeper.identity: the font-scale loader reads QSettings at
# import time). The rest resolve LAZILY via __getattr__ so `import trackerkeeper` stays
# light: importing the chrome (window / app / design_tokens) would trip that
# import-time read before a fork's configure() could run. Reach for them
# (trackerkeeper.run_app, trackerkeeper.AppWindow, …) AFTER configuring.
_LAZY = {
    "run_app": ("trackerkeeper.app", "run_app"),
    "AppWindow": ("trackerkeeper.window", "AppWindow"),
    "AppBus": ("trackerkeeper.bus", "AppBus"),
    "get_bus": ("trackerkeeper.bus", "get_bus"),
    "Settings": ("trackerkeeper.settings", "Settings"),
    "get_settings": ("trackerkeeper.settings", "get_settings"),
}

__all__ = ["__version__", "configure", *_LAZY]


def __getattr__(name: str):
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(target[0]), target[1])
