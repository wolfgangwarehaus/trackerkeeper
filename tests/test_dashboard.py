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


# ── the refresh heartbeat ────────────────────────────────────────────────────


def test_refresh_interval_defaults_clamps_and_disables(qapp):
    from trackerkeeper.dashboard import (
        DEFAULT_INTERVAL_MIN,
        MIN_INTERVAL_MIN,
        refresh_interval_minutes,
        set_refresh_interval_minutes,
    )
    from trackerkeeper.settings import get_settings

    try:
        set_refresh_interval_minutes(240)
        assert refresh_interval_minutes() == 240
        # below the floor is raised to it — every check hits someone else's server
        set_refresh_interval_minutes(1)
        assert refresh_interval_minutes() == MIN_INTERVAL_MIN
        # 0 means "manual only", and is NOT clamped up
        set_refresh_interval_minutes(0)
        assert refresh_interval_minutes() == 0
        # a garbage stored value falls back to the default rather than raising
        get_settings()._s.setValue("app/refresh_interval_minutes", "soon")
        assert refresh_interval_minutes() == DEFAULT_INTERVAL_MIN
    finally:
        get_settings()._s.remove("app/refresh_interval_minutes")


def test_offscreen_dashboard_arms_no_timer(qapp):
    """The heartbeat must never start headless — it would reach the network."""
    dash = _dash(qapp, catalog.default_fleet())
    assert dash._periodic is None
    dash.apply_refresh_interval()        # safe no-op, not an AttributeError
    dash._refresh_if_stale()             # ditto — and starts no worker
    assert dash._worker is None


def test_worker_checks_sources_concurrently_and_skips_manual(qapp):
    """One slow source must not hold up the others (the old serial loop did)."""
    import threading
    import time

    from trackerkeeper.dashboard import _RefreshWorker

    items = [catalog.Item(name=f"I{n}", kind="github", ref="a/b") for n in range(6)]
    items.append(catalog.Item(name="manual-one", kind="manual"))
    inflight, peak, lock = 0, 0, threading.Lock()

    def fake_check(item, *a, **kw):
        nonlocal inflight, peak
        with lock:
            inflight += 1
            peak = max(peak, inflight)
        time.sleep(0.05)
        with lock:
            inflight -= 1
        return CheckResult(latest="9", date="2026-07-25"), ""

    import trackerkeeper.sources as sources_mod

    real = sources_mod.check_with_reason
    sources_mod.check_with_reason = fake_check
    try:
        worker = _RefreshWorker([*items])
        got = {}
        worker.done.connect(got.update)
        worker.start()
        assert worker.wait(10_000)
        qapp.processEvents()
    finally:
        sources_mod.check_with_reason = real

    assert peak > 1, f"checks ran serially (peak in-flight {peak})"
    assert "manual-one" not in got      # manual items are never polled
    assert len(got) == 6


def test_worker_with_only_manual_items_emits_empty(qapp):
    from trackerkeeper.dashboard import _RefreshWorker

    worker = _RefreshWorker([catalog.Item(name="M", kind="manual")])
    got = []
    worker.done.connect(got.append)
    worker.start()
    assert worker.wait(5_000)
    qapp.processEvents()
    assert got == [{}]


# ── "new since you last looked" ──────────────────────────────────────────────


def test_is_new_is_distinct_from_has_update():
    it = catalog.Item(name="X", installed="1.0", latest="1.1")
    assert it.has_update() and it.is_new()      # available AND unseen
    it.seen_version = "1.1"
    assert it.has_update() and not it.is_new()  # still pending, no longer news
    it.latest = "1.2"                           # a newer one lands → news again
    assert it.is_new()
    it.installed = "1.2"
    assert not it.has_update() and not it.is_new()


def test_seen_state_persists_across_a_reload(qapp):
    dash = _dash(qapp, [catalog.Item(name="G", kind="github", installed="1.0",
                                     latest="1.1")])
    assert dash._items[0].is_new()
    dash._mark_seen()
    # the whole point: a restart must not re-shout an update you already saw
    assert catalog.load()[0].seen_version == "1.1"
    assert not catalog.load()[0].is_new()
    assert catalog.load()[0].has_update()      # but it IS still pending


def test_hiding_the_window_banks_what_you_saw(qapp):
    dash = _dash(qapp, [catalog.Item(name="G", kind="github", installed="1.0",
                                     latest="1.1")])
    dash.show()                                 # Qt only delivers hideEvent
    qapp.processEvents()                        # to a widget that was visible
    dash.hide()
    qapp.processEvents()
    assert not dash._items[0].is_new()


def test_mark_seen_ignores_items_with_no_update(qapp):
    dash = _dash(qapp, [catalog.Item(name="G", kind="github", installed="1.0",
                                     latest="1.0")])
    dash._mark_seen()
    # nothing to see → nothing recorded (an empty seen_version stays empty)
    assert dash._items[0].seen_version == ""


def test_error_text_separates_the_two_failures():
    from trackerkeeper import sources
    from trackerkeeper.dashboard import error_text

    assert "check the handle" in error_text(sources.NOT_FOUND)
    assert "couldn't reach" in error_text(sources.UNREACHABLE)
    assert "couldn't reach" in error_text("")   # unknown -> the conservative read


def test_results_store_the_release_notes(qapp):
    dash = _dash(qapp, [catalog.Item(name="G", kind="github", installed="1.0")])
    dash._on_results({"G": CheckResult(latest="1.1", date="2026-07-25",
                                       notes="• Fixed a thing")})
    assert dash._items[0].latest_notes == "• Fixed a thing"
    assert catalog.load()[0].latest_notes == "• Fixed a thing"   # persisted


def test_detail_dialog_builds_and_explains_an_empty_body(qapp):
    from trackerkeeper.detail_dialog import DetailDialog

    # a source that structurally cannot carry notes must SAY so, not show a blank
    d = DetailDialog(item=catalog.Item(name="KDE", kind="arch", ref="plasma-desktop",
                                       installed="6.7.3-1", latest="6.7.3-1"))
    assert "package index" in d._no_notes_reason()
    d2 = DetailDialog(item=catalog.Item(name="G", kind="github", installed="1.0",
                                        latest="1.1", latest_notes="• Fixed"))
    assert d2._item.latest_notes == "• Fixed"


def test_detail_dialog_mark_updated_mutates_the_item(qapp):
    from trackerkeeper.detail_dialog import DetailDialog

    item = catalog.Item(name="G", kind="github", installed="1.0", latest="1.1")
    d = DetailDialog(item=item)
    d._on_mark()
    assert item.installed == "1.1" and not item.has_update()
    assert d._marked is True    # so prompt() reports "marked" and the caller saves
