"""Structured file logging — opt-in, env-driven, rotation-capped.

``install()`` attaches two handlers to the root logger:

  * a ``RotatingFileHandler`` (~1 MB × 3 backups) under the app's state dir —
    ``<AppDataLocation>/logs/<app>.log`` — so a user can hand back a bounded,
    recent log instead of an unbounded one (or nothing);
  * a console ``StreamHandler`` at WARNING, so a terminal launch stays quiet
    unless something is actually wrong.

Level comes from the ``TRACKERKEEPER_LOG`` env var (``debug`` / ``info`` / ``warning``,
default ``info``) — nothing is persisted in Settings; a support request is
"relaunch with TRACKERKEEPER_LOG=debug", not a toggle hunt. ``run_app`` calls
``install()`` early (right after the Qt identity names are set, so
``AppDataLocation`` resolves to the per-app dir); a base app that skips
``run_app`` opts in by calling ``install()`` itself. Idempotent, best-effort,
never fatal.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_MAX_BYTES = 1_000_000  # ~1 MB per file …
_BACKUP_COUNT = 3  # … × 3 rotated backups ≈ 4 MB worst-case on disk
_installed = False
_file_path: Path | None = None


def _level_from_env() -> int:
    """Root level from ``TRACKERKEEPER_LOG`` (debug/info/warning/error), default INFO."""
    name = (os.environ.get("TRACKERKEEPER_LOG") or "info").strip().upper()
    return getattr(logging, name, logging.INFO)


def log_dir() -> Path:
    """The app's log directory — ``<AppDataLocation>/logs``. Falls back to a
    hand-built per-identity path when Qt's location resolves without the app
    segment (i.e. before the QApplication names are set)."""
    from PySide6.QtCore import QStandardPaths

    from trackerkeeper import identity

    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    p = Path(base) if base else Path.home()
    # Before setApplicationName/setOrganizationName, AppDataLocation is the bare
    # platform root (~/.local/share) — append the identity pair so the logs
    # never land outside the app's own tree.
    if identity.app() not in p.parts:
        p = p / identity.org() / identity.app()
    return p / "logs"


def log_file_path() -> Path | None:
    """The active log file, or None while ``install()`` hasn't run/succeeded.
    (``trackerkeeper.diagnostics`` tails this for the support report.)"""
    return _file_path


def install() -> bool:
    """Attach the rotating file handler + the WARNING console handler to the
    root logger. Returns True when the file handler landed. Idempotent —
    a second call is a no-op — and never raises (an unwritable state dir just
    means no file log)."""
    global _installed, _file_path
    if _installed:
        return _file_path is not None
    _installed = True

    root = logging.getLogger()
    root.setLevel(_level_from_env())

    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(console)

    try:
        from trackerkeeper import identity

        d = log_dir()
        d.mkdir(parents=True, exist_ok=True)
        _file_path = d / f"{identity.app()}.log"
        fh = RotatingFileHandler(
            _file_path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
        fh.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(fh)
        return True
    except Exception:
        _file_path = None
        return False


def open_logs_dir() -> bool:
    """Open the log directory in the platform file manager. Returns False when
    there's nothing to open (install() never ran / no writable dir)."""
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        d = log_dir()
        if not d.is_dir():
            return False
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(d))))
    except Exception:
        return False
