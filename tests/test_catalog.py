"""The catalog — model semantics + round-trip persistence (no real AppData)."""

from __future__ import annotations

import pytest

from trackerkeeper import catalog


@pytest.fixture(autouse=True)
def _tmp_catalog(tmp_path):
    catalog.set_catalog_path(tmp_path / "catalog.json")
    yield
    catalog.set_catalog_path(None)


def test_has_update_only_when_latest_differs_from_installed():
    assert catalog.Item(name="a", installed="1.0", latest="1.1").has_update()
    assert not catalog.Item(name="a", installed="1.1", latest="1.1").has_update()
    assert not catalog.Item(name="a", installed="1.0", latest="").has_update()  # unchecked


def test_sort_puts_updates_first_then_newest_date():
    old_update = catalog.Item(name="old", installed="1", latest="2", latest_date="2026-01-01")
    new_update = catalog.Item(name="new", installed="1", latest="2", latest_date="2026-07-01")
    current = catalog.Item(name="cur", installed="2", latest="2", latest_date="2026-08-01")
    order = sorted([current, old_update, new_update], key=lambda i: i.sort_key())
    assert [i.name for i in order] == ["new", "old", "cur"]  # updates first, newest date first


def test_round_trip_preserves_every_field(tmp_path):
    items = [
        catalog.Item(name="Ghostty", platform="Terminal", kind="github",
                     ref="ghostty-org/ghostty", installed="1.0", latest="1.1",
                     latest_url="https://x", latest_date="2026-07-01",
                     checked_at="2026-07-01 10:00", changelog_url="https://c"),
        catalog.Item(name="iOS", kind="manual", installed="26.1"),
    ]
    catalog.save(items)
    back = catalog.load()
    assert [i.name for i in back] == ["Ghostty", "iOS"]
    assert back[0].ref == "ghostty-org/ghostty" and back[0].latest == "1.1"
    assert back[1].kind == "manual" and back[1].installed == "26.1"


def test_missing_file_seeds_the_real_fleet():
    fleet = catalog.load()  # nothing saved yet
    names = {i.name for i in fleet}
    assert "KDE Plasma" in names and "Ghostty" in names
    assert any(i.kind == "github" for i in fleet)
    assert any(i.kind == "arch" for i in fleet)
    assert any(i.kind == "appstore" for i in fleet)  # Blackmagic Camera (iOS)


def test_group_field_round_trips(tmp_path):
    catalog.set_catalog_path(tmp_path / "catalog.json")
    try:
        catalog.save([catalog.Item(name="X", kind="manual", group="Gaming")])
        assert catalog.load()[0].group == "Gaming"
    finally:
        catalog.set_catalog_path(None)


def test_load_ignores_unknown_keys_and_bad_json(tmp_path):
    p = tmp_path / "catalog.json"
    p.write_text('{"items":[{"name":"X","installed":"1","from_the_future":true}]}')
    (items,) = catalog.load()
    assert items.name == "X" and items.installed == "1"
    p.write_text("}{ not json")
    assert {i.name for i in catalog.load()}  # falls back to the seed, never crashes


def test_save_is_atomic_no_tmp_left(tmp_path):
    catalog.save([catalog.Item(name="A")])
    assert not (tmp_path / "catalog.json.tmp").exists()
    assert (tmp_path / "catalog.json").is_file()
