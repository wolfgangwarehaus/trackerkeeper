"""Import-smoke + the phantom-import guard.

Two distinct guards live here:

1. **Import-smoke** — every public ``dough`` module imports cleanly on *this*
   platform. (Private per-platform backends — ``_windows`` / ``_linux`` / … —
   are skipped: the foreign ones legitimately won't import off their OS; the
   package dispatchers exercise the right one.)

2. **Phantom-import guard** — no statement anywhere in the package names a
   ``dough.<x>`` module that doesn't ship. This is a *static* AST walk, so it
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

import dough


def _public_modules() -> list[str]:
    mods: list[str] = []
    for info in pkgutil.walk_packages(dough.__path__, prefix="dough."):
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
    """Every public dough module imports without error on this platform."""
    importlib.import_module(modname)


# ── phantom-import guard ────────────────────────────────────────────────────


def _dough_import_targets() -> list[tuple[str, Path, int]]:
    """Every absolute ``dough.<x>`` an import statement names, anywhere in the
    package — including lazy imports nested in functions (a static AST walk, so
    we catch the ones that only ``ModuleNotFoundError`` when called)."""
    pkg_dir = Path(dough.__file__).parent
    targets: list[tuple[str, Path, int]] = []
    for py in sorted(pkg_dir.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module
                if node.level == 0 and mod and (mod == "dough" or mod.startswith("dough.")):
                    targets.append((mod, py, node.lineno))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "dough" or alias.name.startswith("dough."):
                        targets.append((alias.name, py, node.lineno))
    return targets


def _is_phantom(target: str) -> bool:
    try:
        return importlib.util.find_spec(target) is None
    except ModuleNotFoundError:
        return True  # a submodule whose parent package itself doesn't exist


def test_no_phantom_dough_imports() -> None:
    """No statement imports a ``dough.<x>`` module that doesn't ship."""
    phantoms = sorted(
        {f"{t}  ({py.name}:{ln})" for (t, py, ln) in _dough_import_targets() if _is_phantom(t)}
    )
    assert not phantoms, "phantom dough.* imports:\n  " + "\n  ".join(phantoms)
