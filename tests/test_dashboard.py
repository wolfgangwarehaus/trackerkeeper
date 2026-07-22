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


def test_dashboard_construction_never_touches_the_network(qapp):
    """Offscreen construction must not auto-refresh (no network in CI/tests)."""
    dash = _dash(qapp, catalog.default_fleet())
    assert dash._worker is None  # no refresh worker was started
