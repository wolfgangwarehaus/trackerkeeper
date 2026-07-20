"""dough.settings_migration — the versioned run-once migration runner.

Each test hands migrate() an explicit INI-backed QSettings under tmp_path, so
nothing touches the real per-user store.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from dough import settings_migration as sm


@pytest.fixture()
def qs(tmp_path):
    settings = QSettings(str(tmp_path / "store.ini"), QSettings.Format.IniFormat)
    yield settings
    settings.sync()


def test_fresh_store_lands_on_current_version(qs):
    assert sm.stored_version(qs) == 0
    assert sm.migrate(qs) == sm.CURRENT_SCHEMA_VERSION
    assert sm.stored_version(qs) == sm.CURRENT_SCHEMA_VERSION


def test_migrate_is_idempotent(qs, monkeypatch):
    calls = []
    monkeypatch.setattr(sm, "MIGRATIONS", [lambda s: calls.append(1)])
    sm.migrate(qs)
    sm.migrate(qs)  # stamped — the step must not run again
    assert calls == [1]


def test_migrations_run_in_order_from_stored_version(qs, monkeypatch):
    ran = []
    monkeypatch.setattr(
        sm,
        "MIGRATIONS",
        [lambda s: ran.append("v1"), lambda s: ran.append("v2"), lambda s: ran.append("v3")],
    )
    qs.setValue("meta/schema_version", 1)  # v1 already applied on this install
    assert sm.migrate(qs) == 3
    assert ran == ["v2", "v3"]


def test_migration_rewrites_keys(qs, monkeypatch):
    def split_theme(s: QSettings) -> None:
        old = s.value("ui/theme", None)
        if old is not None:
            s.setValue("ui/theme_mode", old)
            s.remove("ui/theme")

    monkeypatch.setattr(sm, "MIGRATIONS", [split_theme])
    qs.setValue("ui/theme", "frosted_dark")
    sm.migrate(qs)
    assert qs.value("ui/theme_mode") == "frosted_dark"
    assert not qs.contains("ui/theme")


def test_failing_migration_stops_and_retries_next_boot(qs, monkeypatch):
    ran = []

    def boom(s):
        raise RuntimeError("mid-flight failure")

    monkeypatch.setattr(
        sm, "MIGRATIONS", [lambda s: ran.append("v1"), boom, lambda s: ran.append("v3")]
    )
    assert sm.migrate(qs) == 1  # v1 stamped, v2 aborted, v3 never reached
    assert sm.stored_version(qs) == 1
    assert ran == ["v1"]
    # "Next boot" with the step fixed: resumes at v2, doesn't repeat v1.
    monkeypatch.setattr(
        sm,
        "MIGRATIONS",
        [lambda s: ran.append("v1-again"), lambda s: ran.append("v2"), lambda s: ran.append("v3")],
    )
    assert sm.migrate(qs) == 3
    assert ran == ["v1", "v2", "v3"]


def test_garbage_stamp_reads_as_zero(qs):
    qs.setValue("meta/schema_version", "not-a-number")
    assert sm.stored_version(qs) == 0
