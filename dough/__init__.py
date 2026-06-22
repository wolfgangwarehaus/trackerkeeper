"""dough — the wolfgang warehaus app base. See docs/PHILOSOPHY.md."""

from dough.identity import configure


def _resolve_version() -> str:
    """The single version source (docs/BAKING.md §2 principle 4). In a built
    install, setuptools-scm has written ``dough/_version.py`` from the git tag.
    In a raw source checkout it hasn't, so fall back to the installed-package
    metadata, then to a sentinel — never hardcode a number that could drift."""
    try:
        from dough._version import version  # generated at build by setuptools-scm

        return version
    except ImportError:
        pass
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("dough")
        except PackageNotFoundError:
            pass
    except ImportError:
        pass
    return "0.0.0+unknown"


__version__ = _resolve_version()

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
