"""KWin window-rule backend. Writes a ``noborder`` Force rule into KDE's
``~/.config/kwinrulesrc`` and reconfigures KWin so it takes effect immediately.

Why this exists: trackerkeeper's main window is server-side-decorated on KDE Wayland
(so compositor blur survives a drag — a ``Qt.FramelessWindowHint`` window loses
it). This rule tells KWin to draw no decoration for the window, so it still
looks frameless.

Scope of the rule: matches the app's wmclass (``identity.app()``, set via
``setDesktopFileName``) with a substring matcher, so any X11/Wayland WM_CLASS
quirk Qt or KWin might add is tolerated. No title match — the window title is
free to change (e.g. a document name) without the rule falling off.

The rule UUID is persisted in QSettings so removing (native-border mode) cleanly
deletes the same rule we wrote, even across runs.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid as _uuid

from PySide6.QtCore import QSettings

from trackerkeeper import identity

_DESCRIPTION = "trackerkeeper — borderless frameless main window (managed)"
# QSettings key holding the main-window rule UUID.
_MAIN_NOBORDER_KEY = "kwin/noborder_main_rule_uuid"

_NOBORDER_RULE_FIELDS = (
    "Description",
    "clientmachine",
    "clientmachinematch",
    "wmclass",
    "wmclassmatch",
    "wmclasscomplete",
    "noborder",
    "noborderrule",
)


def is_supported() -> bool:
    """KDE Wayland *and* the kwriteconfig/kreadconfig/qdbus tools are on
    PATH. Returns False on any minimal install missing those tools."""
    return bool(_kwriteconfig_bin() and _kreadconfig_bin() and _qdbus_bin())


def install_main_window_noborder() -> bool:
    """Idempotently install (or refresh) the ``noborder`` Force rule for the
    main window. Returns True on success, False if the environment isn't
    supported.

    Install this EARLY (before the window maps) so a fresh launch never flashes
    a titlebar. Idempotent + persisted, so it's a no-op refresh on every
    subsequent launch — self-healing if System Settings ever rewrites
    kwinrulesrc and drops the rule."""
    if not is_supported():
        return False

    qs = _qsettings()
    rule_uuid = qs.value(_MAIN_NOBORDER_KEY, "", type=str)
    if not rule_uuid:
        rule_uuid = str(_uuid.uuid4())
        qs.setValue(_MAIN_NOBORDER_KEY, rule_uuid)
    _ensure_in_rules_list(rule_uuid)
    _write_noborder_rule_body(rule_uuid)
    _reconfigure_kwin()
    return True


def remove_main_window_noborder() -> bool:
    """Idempotently remove the main window's ``noborder`` rule (the user turned
    native window decorations back on). Returns True if a rule was present and
    removed, False if there was nothing to do."""
    if not is_supported():
        return False

    qs = _qsettings()
    rule_uuid = qs.value(_MAIN_NOBORDER_KEY, "", type=str)
    if not rule_uuid:
        return False
    _remove_from_rules_list(rule_uuid)
    _delete_noborder_rule_group(rule_uuid)
    qs.remove(_MAIN_NOBORDER_KEY)
    _reconfigure_kwin()
    return True


def diagnose() -> dict:
    """Returns the runtime values KWin would match against, plus the tools we'd
    shell out to. Handy for figuring out why a rule isn't sticking — call from a
    debug toggle and log the dict."""
    return {
        "backend": "kwin",
        "is_supported": is_supported(),
        "kwriteconfig": _kwriteconfig_bin(),
        "kreadconfig": _kreadconfig_bin(),
        "qdbus": _qdbus_bin(),
        "rule_wmclass": identity.app(),
    }


# ── internals ─────────────────────────────────────────────────────────


def _qsettings() -> QSettings:
    """The trackerkeeper identity QSettings handle — the same
    ``QSettings(identity.org(), identity.app())`` pair the app uses, so the
    stored rule UUID lives alongside the app's other settings."""
    return QSettings(identity.org(), identity.app())


def _kwriteconfig_bin() -> str | None:
    for cand in ("kwriteconfig6", "kwriteconfig5"):
        path = shutil.which(cand)
        if path:
            return path
    return None


def _kreadconfig_bin() -> str | None:
    for cand in ("kreadconfig6", "kreadconfig5"):
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


def _kreadconfig(group: str, key: str, default: str = "") -> str:
    bin_ = _kreadconfig_bin()
    if not bin_:
        return default
    try:
        out = subprocess.run(
            [bin_, "--file", "kwinrulesrc", "--group", group, "--key", key,
             "--default", default],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return (out.stdout or "").strip()
    except Exception:
        return default


def _kwriteconfig(group: str, key: str, value: str) -> None:
    bin_ = _kwriteconfig_bin()
    if not bin_:
        return
    try:
        subprocess.run(
            [bin_, "--file", "kwinrulesrc", "--group", group, "--key", key, value],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def _kdeleteconfig_key(group: str, key: str) -> None:
    bin_ = _kwriteconfig_bin()
    if not bin_:
        return
    try:
        subprocess.run(
            [bin_, "--file", "kwinrulesrc", "--group", group, "--key", key, "--delete"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def _ensure_in_rules_list(rule_uuid: str) -> None:
    """Append our UUID to [General].rules and bump count, unless already
    present. Both keys are kept in sync — KWin reads `rules` for the ordered
    list and `count` for length validation."""
    raw = _kreadconfig("General", "rules", "")
    rules = [r for r in raw.split(",") if r]
    if rule_uuid in rules:
        return
    rules.append(rule_uuid)
    _kwriteconfig("General", "rules", ",".join(rules))
    _kwriteconfig("General", "count", str(len(rules)))


def _remove_from_rules_list(rule_uuid: str) -> None:
    raw = _kreadconfig("General", "rules", "")
    rules = [r for r in raw.split(",") if r and r != rule_uuid]
    _kwriteconfig("General", "rules", ",".join(rules))
    _kwriteconfig("General", "count", str(len(rules)))


def _write_noborder_rule_body(rule_uuid: str) -> None:
    """Scope: wmclass contains ``identity.app()`` (substring + complete=true, so
    WM_CLASS quirks are tolerated). Action: noborder=true with noborderrule=2
    (Force) — KWin draws no decoration for the matched window. ``noborderrule``
    value 2 (= Force) verified against KWin 6.6."""
    fields = {
        "Description": _DESCRIPTION,
        "clientmachine": "localhost",
        "clientmachinematch": "0",
        "wmclass": identity.app(),
        "wmclassmatch": "2",  # 2 = substring
        "wmclasscomplete": "true",
        "noborder": "true",
        "noborderrule": "2",  # 2 = Force
    }
    for key, val in fields.items():
        _kwriteconfig(rule_uuid, key, val)


def _delete_noborder_rule_group(rule_uuid: str) -> None:
    # kwriteconfig has no "delete group" — wipe each key we wrote.
    for key in _NOBORDER_RULE_FIELDS:
        _kdeleteconfig_key(rule_uuid, key)


def _reconfigure_kwin() -> None:
    """Tell KWin to reread kwinrulesrc. Cheap, no shell restart needed.
    Never kquitapp / killall plasmashell — reconfigure is the only refresh we
    ever issue."""
    bin_ = _qdbus_bin()
    if not bin_:
        return
    try:
        subprocess.run(
            [bin_, "org.kde.KWin", "/KWin", "reconfigure"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass
