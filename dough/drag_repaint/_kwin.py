"""KWin scripted-effect backend for the drag-repaint fix.

Installs dough's bundled scripted effect into the user's KWin effects
directory, flips its `kwinrc` enable key, and asks KWin to (re)load it —
all idempotent, all best-effort.

The effect ships as an identity-agnostic **template** under
`effect/dragrepaint/` (a `metadata.json` + `contents/code/main.js` pair, both
carrying the ``{{app_id}}`` token). `install()` renders the token from the
running app's identity (``dough.identity.app()``) as it copies the effect into
place, so a fork matches *its own* windows with no source edit and no `dough
new` re-namespacing — the effect id becomes ``{app}_dragrepaint``, and the
JS scopes to the app's wmclass.

Why copy-and-load rather than just write a `kwinrc` key: a freshly
enabled effect isn't picked up until KWin is told to load it, and we
want the fix live on first launch without a compositor restart.

Everything degrades to a silent no-op: missing tools, an unwritable
data dir, a KWin that rejects the effect — none of it should ever take
down the app. The artifact is a cosmetic bug; the fix is best-effort.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from dough import identity

# The effect ships as a template (see module docstring); this token is
# replaced with the app slug when the effect is rendered into place.
_APP_ID_TOKEN = "{{app_id}}"

# Bundled template source: dough/drag_repaint/effect/dragrepaint/. The dir is
# NOT app-named — the concrete id is derived from identity at install time.
_SOURCE_DIR = Path(__file__).resolve().parent / "effect" / "dragrepaint"


def _app_id() -> str:
    return identity.app()


def _effect_id() -> str:
    """The rendered KWin plugin id — also the kwinrc [Plugins] key stem
    (`<id>Enabled`) and the effects dir name. Derived from the live identity."""
    return f"{_app_id()}_dragrepaint"


def is_supported() -> bool:
    """KDE Wayland with `kwriteconfig` + `qdbus` on PATH, and the
    bundled effect actually present in the package. A False here is
    what `__init__`'s callers read to skip the work entirely."""
    return bool(_kwriteconfig_bin() and _qdbus_bin() and _SOURCE_DIR.is_dir())


def install() -> bool:
    """Idempotently install, enable, and load the effect. Renders the
    bundled template into the user's effects dir (over any existing copy),
    sets the `kwinrc` key, and asks KWin to reload. Returns True on success,
    False if unsupported or the copy failed."""
    if not is_supported():
        return False
    dest = _dest_dir()
    try:
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(_SOURCE_DIR, dest)
        _render_identity(dest)
    except OSError:
        return False
    _set_enabled(True)
    _reload_effect()
    return True


def uninstall() -> bool:
    """Idempotently unload, disable, and delete the effect. Returns
    True if the environment is supported (i.e. the work was attempted),
    False otherwise."""
    if not is_supported():
        return False
    _effects_call("unloadEffect", _effect_id())
    _set_enabled(False)
    try:
        shutil.rmtree(_dest_dir())
    except OSError:
        pass
    return True


def diagnose() -> dict:
    """Runtime paths + tool resolution — call from a debug hook and log
    the dict if the effect isn't taking."""
    return {
        "backend": "kwin",
        "is_supported": is_supported(),
        "app_id": _app_id(),
        "effect_id": _effect_id(),
        "source_dir": str(_SOURCE_DIR),
        "source_present": _SOURCE_DIR.is_dir(),
        "dest_dir": str(_dest_dir()),
        "kwriteconfig": _kwriteconfig_bin(),
        "qdbus": _qdbus_bin(),
    }


# ── internals ─────────────────────────────────────────────────────────


def _render_identity(dest: Path) -> None:
    """Replace the ``{{app_id}}`` token with the app slug in every rendered
    file (metadata.json + main.js), so the installed effect carries the
    concrete id / wmclass match. Only the two small text assets exist here."""
    app_id = _app_id()
    for path in dest.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if _APP_ID_TOKEN in text:
            path.write_text(text.replace(_APP_ID_TOKEN, app_id), encoding="utf-8")


def _data_home() -> Path:
    """XDG_DATA_HOME, or its ~/.local/share default."""
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    return Path(xdg) if xdg else Path.home() / ".local" / "share"


def _dest_dir() -> Path:
    return _data_home() / "kwin" / "effects" / _effect_id()


def _kwriteconfig_bin() -> str | None:
    for cand in ("kwriteconfig6", "kwriteconfig5"):
        path = shutil.which(cand)
        if path:
            return path
    return None


def _qdbus_bin() -> str | None:
    for cand in ("qdbus6", "qdbus-qt6", "qdbus"):
        path = shutil.which(cand)
        if path:
            return path
    return None


def _set_enabled(on: bool) -> None:
    """Write the `kwinrc` [Plugins] enable key for the effect."""
    bin_ = _kwriteconfig_bin()
    if not bin_:
        return
    try:
        subprocess.run(
            [
                bin_, "--file", "kwinrc", "--group", "Plugins",
                "--key", f"{_effect_id()}Enabled", "true" if on else "false",
            ],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def _effects_call(method: str, *args: str) -> None:
    """Invoke a method on KWin's `/Effects` D-Bus object (loadEffect /
    unloadEffect)."""
    bin_ = _qdbus_bin()
    if not bin_:
        return
    try:
        subprocess.run(
            [bin_, "org.kde.KWin", "/Effects", method, *args],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def _reload_effect() -> None:
    """Unload-then-load so a refreshed main.js is re-read by KWin."""
    _effects_call("unloadEffect", _effect_id())
    _effects_call("loadEffect", _effect_id())
