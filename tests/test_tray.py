"""The tray presence + the utility-window sizing. The pure pieces (tooltip
text, width tiers, prefs) test without a tray — CI has no system tray, which is
exactly the case AppTray must survive."""

from __future__ import annotations

import pytest

from trackerkeeper import catalog
from trackerkeeper.dashboard import (
    MIN_SIZE,
    TIER_MEDIUM,
    TIER_NARROW,
    TIER_WIDE,
    width_tier,
)
from trackerkeeper.tray import AppTray, close_to_tray, set_close_to_tray, tooltip_text


@pytest.fixture(autouse=True)
def _tmp_catalog(tmp_path):
    catalog.set_catalog_path(tmp_path / "catalog.json")
    yield
    catalog.set_catalog_path(None)


def test_tooltip_reads_the_fleet_state():
    assert tooltip_text("tracker keeper", 0) == "tracker keeper — all current"
    assert tooltip_text("tracker keeper", 1) == "tracker keeper — 1 update available"
    assert tooltip_text("tracker keeper", 3) == "tracker keeper — 3 updates available"


def test_width_tiers_drop_columns_as_it_narrows():
    assert width_tier(900) == TIER_WIDE
    assert width_tier(620) == TIER_WIDE
    assert width_tier(619) == TIER_MEDIUM
    assert width_tier(420) == TIER_MEDIUM
    assert width_tier(419) == TIER_NARROW
    assert width_tier(MIN_SIZE[0]) == TIER_NARROW  # the floor is still a real layout


def test_close_to_tray_pref_round_trips():
    before = close_to_tray()
    try:
        set_close_to_tray(False)
        assert close_to_tray() is False
        set_close_to_tray(True)
        assert close_to_tray() is True
    finally:
        set_close_to_tray(before)


def test_tray_self_disables_without_a_system_tray(qapp):
    """CI (offscreen) has no tray: constructing one must be harmless and leave
    `available` False, so close-to-tray can never hide a window with no way back."""
    from PySide6.QtGui import QCloseEvent

    from trackerkeeper.window import AppWindow

    win = AppWindow(title="t")
    tray = AppTray(win, on_refresh=lambda: None)
    if not tray.available:
        # the close event passes straight through — never swallowed
        assert tray.eventFilter(win, QCloseEvent()) is False
    win.close()


def test_dashboard_sizes_the_window_small_but_usable(qapp):
    """The utility default applies only when no saved geometry was restored."""
    from trackerkeeper.dashboard import DEFAULT_SIZE, Dashboard
    from trackerkeeper.window import AppWindow

    win = AppWindow(title="t")
    win._geometry_restored = False
    win.set_content(Dashboard(win))
    assert (win.width(), win.height()) == DEFAULT_SIZE
    assert (win.minimumWidth(), win.minimumHeight()) == MIN_SIZE
    win.close()


def test_a_restored_geometry_is_never_overridden(qapp):
    from trackerkeeper.dashboard import Dashboard
    from trackerkeeper.window import AppWindow

    win = AppWindow(title="t")
    win._geometry_restored = True
    win.resize(900, 700)
    win.set_content(Dashboard(win))
    assert (win.width(), win.height()) == (900, 700)
    win.close()


def test_tooltip_reports_the_unseen_count():
    from trackerkeeper.tray import tooltip_text

    assert tooltip_text("tk", 3, 1) == "tk — 3 updates available, 1 new"
    assert tooltip_text("tk", 3, 0) == "tk — 3 updates available"   # no ", 0 new"
    assert tooltip_text("tk", 0, 0) == "tk — all current"


def test_start_minimized_defaults_off_and_round_trips():
    from trackerkeeper import tray

    try:
        assert tray.start_minimized() is False   # a silent first run loses users
        tray.set_start_minimized(True)
        assert tray.start_minimized() is True
    finally:
        tray.set_start_minimized(False)


def test_will_have_tray_is_false_without_a_desktop_tray(qapp):
    """Offscreen has no tray — the predicate that gates start-in-tray must say
    so, or the app could launch with neither icon nor window."""
    from trackerkeeper import tray

    assert tray.will_have_tray() is False
