"""Versioned settings migrations — the run-once boot upgrade path.

The SHAPE is lifted from jellytoast's ``settings_migration.py`` (the org-rename
/ theme-axes one-shots that healed real installs); dough ships the generic
runner — a schema version stamped under ``meta/schema_version`` plus an ordered
migration table — with jellytoast's app-specific migrations stripped. Migration
0 below is a documented no-op that exists purely as the worked example.

``run_app`` calls :func:`migrate` before ``Settings`` is first read, so every
accessor sees post-migration keys. A fresh install runs every migration once
(each must therefore be a no-op on an empty store) and lands on
``CURRENT_SCHEMA_VERSION``.

The add-a-migration recipe (a fork's, or dough's own):

1. Write a function ``_migrate_to_N(qs: QSettings) -> None`` that rewrites the
   OLD key layout into the new one. It must be idempotent-per-install (the
   version stamp guarantees one run, but a crash mid-migration re-runs it) and
   tolerant of an empty store (fresh installs run it too).
2. Append it to ``MIGRATIONS`` — its index + 1 IS the schema version it
   produces; ``CURRENT_SCHEMA_VERSION`` follows automatically. Never reorder or
   delete entries: installed apps carry stamps that index into this list.
3. Add a test: seed a QSettings with the old layout, ``migrate(qs)``, assert
   the new layout + the bumped stamp (see ``tests/test_settings_migration.py``).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QSettings

logger = logging.getLogger(__name__)

# Where the schema stamp lives in the app's QSettings store.
_VERSION_KEY = "meta/schema_version"


def _migrate_to_1(qs: QSettings) -> None:
    """Example migration (a documented no-op). A real one rewrites keys, e.g.::

        old = qs.value("ui/theme", None)
        if old is not None:
            qs.setValue("ui/theme_mode", old)
            qs.remove("ui/theme")
    """


# Ordered: MIGRATIONS[n] upgrades a version-n store to version n+1. Append-only.
MIGRATIONS = [
    _migrate_to_1,
]

CURRENT_SCHEMA_VERSION = len(MIGRATIONS)


def _open_qsettings() -> QSettings:
    """The app's QSettings store, on the identity seam — the same (org, app)
    pair ``dough.settings.Settings`` opens. The (format, scope, org, app) ctor
    honours ``QSettings.setDefaultFormat`` so tests can redirect the store to a
    throwaway INI file (the bare two-arg form hardwires NativeFormat)."""
    from dough import identity

    return QSettings(
        QSettings.defaultFormat(),
        QSettings.Scope.UserScope,
        identity.org(),
        identity.app(),
    )


def stored_version(qs: QSettings) -> int:
    """The store's stamped schema version. A store with settings but no stamp
    is version 0 (pre-versioning); a completely EMPTY store is a fresh install
    and still starts at 0 — migrations must no-op on it."""
    try:
        return int(qs.value(_VERSION_KEY, 0))
    except (TypeError, ValueError):
        return 0


def migrate(qs: QSettings | None = None) -> int:
    """Run every pending migration, stamp the result, return the version the
    store landed on. Each step is stamped INDIVIDUALLY so a crash between
    steps resumes (not repeats) the finished ones. Best-effort: a failing
    migration is logged and aborts the run at its version — the app still
    boots, and the next launch retries from there."""
    if qs is None:
        qs = _open_qsettings()
    version = stored_version(qs)
    for target, step in enumerate(MIGRATIONS[version:], start=version + 1):
        try:
            step(qs)
        except Exception:
            logger.exception("settings migration to v%s failed — will retry next boot", target)
            break
        qs.setValue(_VERSION_KEY, target)
        qs.sync()
        version = target
        logger.info("settings migrated to schema v%s", target)
    return version
