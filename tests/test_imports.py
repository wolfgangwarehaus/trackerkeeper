"""Import-smoke + the phantom-import guard.

Two distinct guards live here:

1. **Import-smoke** — every public ``trackerkeeper`` module imports cleanly on *this*
   platform. (Private per-platform backends — ``_windows`` / ``_linux`` / … —
   are skipped: the foreign ones legitimately won't import off their OS; the
   package dispatchers exercise the right one.)

2. **Phantom-import guard** — no statement anywhere in the package names a
   ``trackerkeeper.<x>`` module that doesn't ship. This is a *static* AST walk, so it
   catches the lazy imports nested inside functions that otherwise only blow up
   with ``ModuleNotFoundError`` when finally called (``ui_helpers`` is full of
   these, carved out of jellytoast's music layer).
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import pkgutil
from pathlib import Path

import pytest

import trackerkeeper


def _public_modules() -> list[str]:
    mods: list[str] = []
    for info in pkgutil.walk_packages(trackerkeeper.__path__, prefix="trackerkeeper."):
        leaf = info.name.rsplit(".", 1)[-1]
        if leaf == "__main__":
            continue  # importing it runs main()
        if leaf.startswith("_"):
            continue  # private per-platform backend (foreign ones won't import here)
        mods.append(info.name)
    return mods


@pytest.mark.usefixtures("qapp")
@pytest.mark.parametrize("modname", _public_modules())
def test_public_module_imports(modname: str) -> None:
    """Every public trackerkeeper module imports without error on this platform."""
    importlib.import_module(modname)


# ── phantom-import guard ────────────────────────────────────────────────────


def _dough_import_targets() -> list[tuple[str, Path, int]]:
    """Every absolute ``trackerkeeper.<x>`` an import statement names, anywhere in the
    package — including lazy imports nested in functions (a static AST walk, so
    we catch the ones that only ``ModuleNotFoundError`` when called)."""
    pkg_dir = Path(trackerkeeper.__file__).parent
    targets: list[tuple[str, Path, int]] = []
    for py in sorted(pkg_dir.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module
                if node.level == 0 and mod and (mod == "trackerkeeper" or mod.startswith("trackerkeeper.")):
                    targets.append((mod, py, node.lineno))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "trackerkeeper" or alias.name.startswith("trackerkeeper."):
                        targets.append((alias.name, py, node.lineno))
    return targets


# Modules that ship in a BUILT wheel but are legitimately absent from a raw
# source checkout — setuptools-scm writes trackerkeeper/_version.py at build time (the
# tag is the version; docs/BAKING.md §2). __init__ imports it behind a try/except
# fallback, so a missing _version.py is correct here, not a phantom.
_GENERATED = {"trackerkeeper._version"}


def _is_phantom(target: str, *, origin: Path) -> bool:
    # _version.py is build-generated; exempt it ONLY at its one try/except-guarded
    # fallback site (trackerkeeper/__init__.py). An unguarded import of it anywhere else
    # is a real phantom — it crashes in a source checkout — which is exactly what
    # this guard exists to catch, so the exemption must not be a blanket one.
    if target in _GENERATED and origin == Path(trackerkeeper.__file__):
        return False
    try:
        return importlib.util.find_spec(target) is None
    except ModuleNotFoundError:
        return True  # a submodule whose parent package itself doesn't exist


def test_no_phantom_dough_imports() -> None:
    """No statement imports a ``trackerkeeper.<x>`` module that doesn't ship (the
    build-generated _version.py is exempt only at its guarded site — see
    _GENERATED / _is_phantom)."""
    phantoms = sorted(
        {
            f"{t}  ({py.name}:{ln})"
            for (t, py, ln) in _dough_import_targets()
            if _is_phantom(t, origin=py)
        }
    )
    assert not phantoms, "phantom trackerkeeper.* imports:\n  " + "\n  ".join(phantoms)
