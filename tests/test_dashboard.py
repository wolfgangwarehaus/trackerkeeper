"""The dashboard's apply-results logic — the part that turns probe results into
new-update state, notifications, and saved cache. Built under qapp, offscreen,
no network (results are injected)."""

from __future__ import annotations

import pytest

from trackerkeeper import catalog
from trackerkeeper.sources import CheckResult


@pytest.fixture(autouse=True)
def _tmp_catalog(tmp_path):
    catalog.set_catalog_path(tmp_path / "catalog.json")
    yield
    catalog.set_catalog_path(None)


def _dash(qapp, items):
    catalog.save(items)
    from trackerkeeper.dashboard import Dashboard

    return Dashboard()


def test_results_apply_latest_and_flag_new(qapp):
    dash = _dash(qapp, [catalog.Item(name="Ghostty", kind="github",
                                     ref="ghostty-org/ghostty", installed="1.0")])
    dash._on_results({"Ghostty": CheckResult(latest="1.1", url="https://x",
                                             date="2026-07-01")})
    item = dash._items[0]
    assert item.latest == "1.1" and item.has_update()
    assert item.latest_date == "2026-07-01" and item.checked_at
    # persisted
    assert catalog.load()[0].latest == "1.1"


def test_new_update_fires_one_notification(qapp):
    from trackerkeeper.bus import AppBus

    fired = []
    AppBus.get().notify.connect(lambda t, b="": fired.append((t, b)))
    dash = _dash(qapp, [
        catalog.Item(name="Ghostty", kind="github", ref="a/b", installed="1.0"),
        catalog.Item(name="KDE", kind="arch", ref="plasma-desktop", installed="6.4.0"),
    ])
    dash._on_results({
        "Ghostty": CheckResult(latest="1.1", date="2026-07-01"),
        "KDE": CheckResult(latest="6.4.2-1", date="2026-07-02"),
    })
    assert len(fired) == 1
    title, body = fired[0]
    assert "2 new updates" in title
    assert "Ghostty" in body and "KDE" in body


def test_unreachable_source_keeps_last_known_and_marks_error(qapp):
    dash = _dash(qapp, [catalog.Item(name="Ghostty", kind="github", ref="a/b",
                                     installed="1.0", latest="1.1",
                                     latest_date="2026-06-01")])
    dash._on_results({})  # nothing answered
    item = dash._items[0]
    assert item.latest == "1.1"  # last-known preserved, NOT wiped
    assert item.error == "unreachable"


def test_already_surfaced_update_does_not_re_notify(qapp):
    from trackerkeeper.bus import AppBus

    fired = []
    AppBus.get().notify.connect(lambda t, b="": fired.append(t))
    dash = _dash(qapp, [catalog.Item(name="Ghostty", kind="github", ref="a/b",
                                     installed="1.0", latest="1.1")])
    # same latest we already showed → no new notification
    dash._on_results({"Ghostty": CheckResult(latest="1.1", date="2026-07-01")})
    assert fired == []


def test_mark_updated_clears_the_new_state(qapp):
    dash = _dash(qapp, [catalog.Item(name="Ghostty", installed="1.0", latest="1.1")])
    item = dash._items[0]
    assert item.has_update()
    dash._mark_updated(item)
    assert item.installed == "1.1" and not item.has_update()
    assert catalog.load()[0].installed == "1.1"


def test_sort_by_updated_and_by_channel(qapp):
    dash = _dash(qapp, [
        catalog.Item(name="A", kind="github", latest="1", latest_date="2026-07-20"),
        catalog.Item(name="B", kind="appstore", latest="2", latest_date="2026-07-24"),
        catalog.Item(name="C", kind="arch", latest="3", latest_date="2026-07-10"),
        catalog.Item(name="D", kind="manual"),  # no release date → always last
    ])
    dash._sort_key, dash._sort_desc = "updated", True
    assert [i.name for i in dash._sorted_items()] == ["B", "A", "C", "D"]  # newest first
    dash._sort_desc = False
    assert [i.name for i in dash._sorted_items()] == ["C", "A", "B", "D"]  # oldest first
    # undated stays at the bottom in BOTH directions
    assert dash._sorted_items()[-1].name == "D"
    dash._sort_key, dash._sort_desc = "channel", False
    # channels A→Z: App Store(B), Arch(C), GitHub(A), Manual(D)
    assert [i.name for i in dash._sorted_items()] == ["B", "C", "A", "D"]


def test_updated_sort_prefers_full_timestamp_over_date(qapp):
    dash = _dash(qapp, [
        catalog.Item(name="morning", kind="github", latest="1",
                     latest_date="2026-07-24", latest_at="2026-07-24T08:00:00Z"),
        catalog.Item(name="evening", kind="github", latest="1",
                     latest_date="2026-07-24", latest_at="2026-07-24T20:00:00Z"),
    ])
    dash._sort_key, dash._sort_desc = "updated", True
    assert [i.name for i in dash._sorted_items()] == ["evening", "morning"]


def test_grouped_view_orders_categories_and_sorts_within_each(qapp):
    dash = _dash(qapp, [
        catalog.Item(name="A", kind="github", group="PC", latest="1", latest_date="2026-07-20"),
        catalog.Item(name="B", kind="appstore", group="iPhone", latest="2", latest_date="2026-07-24"),
        catalog.Item(name="C", kind="steam", group="Gaming", latest="3", latest_date="2026-07-10"),
        catalog.Item(name="D", kind="github", group="Gaming", latest="4", latest_date="2026-07-22"),
        catalog.Item(name="E", kind="manual", group="", latest="", latest_date=""),
    ])
    dash._sort_key, dash._sort_desc = "updated", True
    view = dash._grouped_view()
    assert [g for g, _ in view] == ["Gaming", "iPhone", "PC", "Other"]  # A→Z, ungrouped last
    within = {g: [i.name for i in items] for g, items in view}
    assert within["Gaming"] == ["D", "C"]  # newest-first sort applies inside the group
    assert within["Other"] == ["E"]


def test_grouping_can_be_toggled_off(qapp):
    dash = _dash(qapp, [catalog.Item(name="A", kind="manual", group="PC")])
    assert dash._grouped is True          # auto-on when any item has a category
    dash._toggle_group()
    assert dash._grouped is False


def _grouped_fleet():
    return [
        catalog.Item(name="A", kind="github", group="PC", latest="1", latest_date="2026-07-20"),
        catalog.Item(name="B", kind="steam", group="Gaming", latest="2", latest_date="2026-07-24"),
        catalog.Item(name="C", kind="steam", group="Gaming", installed="1", latest="2"),
    ]


def test_collapsing_a_group_hides_its_cards_but_keeps_the_header(qapp):
    from trackerkeeper.dashboard import save_collapsed

    save_collapsed(set())
    try:
        dash = _dash(qapp, _grouped_fleet())
        dash._grouped = True
        dash._render()
        full = dash._list.count()
        dash._toggle_collapsed("Gaming")
        assert "Gaming" in dash._collapsed
        # two Gaming cards gone; its header (and everything else) stays
        assert dash._list.count() == full - 2
        dash._toggle_collapsed("Gaming")
        assert dash._list.count() == full
    finally:
        save_collapsed(set())


def test_collapsed_groups_persist(qapp):
    from trackerkeeper.dashboard import load_collapsed, save_collapsed

    save_collapsed(set())
    try:
        dash = _dash(qapp, _grouped_fleet())
        dash._toggle_collapsed("PC")
        assert load_collapsed() == {"PC"}          # written through to settings
        assert _dash(qapp, _grouped_fleet())._collapsed == {"PC"}  # and read back
    finally:
        save_collapsed(set())


def test_collapse_and_expand_all(qapp):
    from trackerkeeper.dashboard import save_collapsed

    save_collapsed(set())
    try:
        dash = _dash(qapp, _grouped_fleet())
        dash._grouped = True
        dash._set_all_collapsed(True)
        assert dash._collapsed == {"Gaming", "PC"}
        dash._set_all_collapsed(False)
        assert dash._collapsed == set()
    finally:
        save_collapsed(set())


def test_dashboard_construction_never_touches_the_network(qapp):
    """Offscreen construction must not auto-refresh (no network in CI/tests)."""
    dash = _dash(qapp, catalog.default_fleet())
    assert dash._worker is None  # no refresh worker was started
