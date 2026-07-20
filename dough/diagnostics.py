"""Diagnostics bundle — the one-click support report.

``collect_report()`` returns a plain-text snapshot of everything a bug report
usually needs three round-trips to gather: app identity + version, platform /
OS / session type, Qt + PySide6 versions, the active theme and the verified
blur status (with the human reason), a settings dump, and the tail of the log
file when ``dough.log`` is installed.

Secrets NEVER appear: the ``credentials/`` subtree is skipped wholesale and
any key whose name smells like a secret (token / password / secret / key /
auth) is redacted — the report is designed to be pasted into a public issue.

The Settings dialog's "Copy diagnostics" button puts the report on the
clipboard; headless callers can just print it.
"""

from __future__ import annotations

import sys

# Settings keys are skipped when their path contains one of these fragments —
# belt-and-braces on top of the credentials/ subtree exclusion, so an app that
# stashes a secret under its own key (jellytoast's server/token) is still safe.
_SECRET_FRAGMENTS = ("credentials/", "token", "password", "secret", "auth", "api_key")


def _is_secret_key(key: str) -> bool:
    k = key.lower()
    return any(frag in k for frag in _SECRET_FRAGMENTS)


def _session_type() -> str:
    """wayland / x11 / windows / macos — the platform half a paste never
    includes but a chrome bug always needs."""
    import os

    from dough.platform_compat import IS_LINUX, IS_MACOS, IS_WINDOWS

    if IS_WINDOWS:
        return "windows"
    if IS_MACOS:
        return "macos"
    if IS_LINUX:
        session = os.environ.get("XDG_SESSION_TYPE") or "unknown"
        desktop = os.environ.get("XDG_CURRENT_DESKTOP") or ""
        return f"{session}{f' ({desktop})' if desktop else ''}"
    return sys.platform


def _settings_lines() -> list[str]:
    from dough.settings import get_settings

    qs = get_settings()._s
    lines = []
    for key in sorted(qs.allKeys()):
        if _is_secret_key(key):
            continue
        try:
            val = qs.value(key)
        except Exception:
            val = "<unreadable>"
        if isinstance(val, (bytes, bytearray)) or type(val).__name__ == "QByteArray":
            val = f"<binary {len(val)}B>"  # window geometry etc. — noise, not signal
        lines.append(f"  {key} = {val}")
    return lines or ["  (empty)"]


def _log_tail(max_lines: int = 100) -> list[str]:
    """The last ~100 lines of the active log file, or a one-line explanation
    when file logging isn't installed. Bounded read (64 KB) so a huge log
    can't stall the settings dialog."""
    try:
        from dough import log as dlog

        path = dlog.log_file_path()
        if path is None or not path.is_file():
            return ["  (file logging not installed — launch with DOUGH_LOG=debug)"]
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 65536))
            text = f.read().decode("utf-8", "replace")
        lines = text.splitlines()[-max_lines:]
        return [f"  {ln}" for ln in lines] or ["  (log is empty)"]
    except Exception as e:
        return [f"  (log unavailable: {e})"]


def collect_report() -> str:
    """The full plain-text diagnostics report. Every section is best-effort —
    a failing probe becomes a line in the report, never an exception out of
    the support path."""
    import platform

    from dough import __version__, identity

    out: list[str] = []
    out.append(f"=== {identity.display_name()} diagnostics ===")
    out.append(f"app: {identity.app()} {__version__} (org {identity.org()})")

    # ── platform ──────────────────────────────────────────────────────
    try:
        out.append(f"os: {platform.platform()}")
    except Exception:
        out.append("os: <unavailable>")
    out.append(f"session: {_session_type()}")
    out.append(f"python: {sys.version.split()[0]}")
    try:
        import PySide6
        from PySide6.QtCore import qVersion

        out.append(f"qt: {qVersion()} (PySide6 {PySide6.__version__})")
    except Exception:
        out.append("qt: <unavailable>")

    # ── theme + blur ──────────────────────────────────────────────────
    try:
        from dough.settings import get_settings

        s = get_settings()
        out.append(
            f"theme: mode={s.theme_mode} accent={s.accent_color} "
            f"font_scale={s.font_scale}"
        )
    except Exception:
        out.append("theme: <unavailable>")
    try:
        from dough import blur

        out.append(f"blur: {blur.status().value} — {blur.reason()}")
    except Exception:
        out.append("blur: <unavailable>")
    try:
        from dough import updates

        out.append(f"channel: {updates.get_channel()}")
    except Exception:
        pass

    # ── settings (secrets excluded) ───────────────────────────────────
    out.append("")
    out.append("--- settings (credentials/secrets excluded) ---")
    try:
        out.extend(_settings_lines())
    except Exception as e:
        out.append(f"  (settings unavailable: {e})")

    # ── log tail ──────────────────────────────────────────────────────
    out.append("")
    out.append("--- log tail (last 100 lines) ---")
    out.extend(_log_tail())

    return "\n".join(out) + "\n"


def copy_to_clipboard() -> bool:
    """collect_report() → the system clipboard. Returns False when there's no
    QApplication (headless caller — print the report instead)."""
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return False
        QApplication.clipboard().setText(collect_report())
        return True
    except Exception:
        return False
