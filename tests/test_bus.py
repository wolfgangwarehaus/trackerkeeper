"""The AppBus contract — dough's decoupling spine stays generic.

These are permanent invariants, not P0 xfails: the base bus ships only generic
chrome signals and carries NO music signals. The power/ recast depends on the
second invariant (it must not re-introduce playback_* to make itself compile).
"""

from __future__ import annotations

import pytest

from dough.bus import AppBus, get_bus

GENERIC_SIGNALS = {
    "theme_changed",
    "accent_changed",
    "open_main_window",
    "show_settings",
    "navigate",
    "hotkeys_changed",
    "dpr_changed",
    "notify",
}

# The music signals jellytoast's PlayerBus adds on top — the base must NOT have
# them. (power/__init__.py currently assumes these exist; that's the P0 bug.)
PLAYBACK_SIGNALS = {
    "playback_started",
    "playback_resumed",
    "playback_paused",
    "playback_stopped",
    "playback_ended",
}


@pytest.mark.usefixtures("qapp")
def test_appbus_exposes_generic_signals() -> None:
    bus = AppBus.get()
    missing = sorted(s for s in GENERIC_SIGNALS if not hasattr(bus, s))
    assert not missing, f"AppBus is missing generic signals: {missing}"


@pytest.mark.usefixtures("qapp")
def test_appbus_stays_music_agnostic() -> None:
    """The base bus must not grow playback_* signals — keeping it generic is the
    whole point, and it's the invariant the power/ recast relies on."""
    bus = AppBus.get()
    leaked = sorted(s for s in PLAYBACK_SIGNALS if hasattr(bus, s))
    assert not leaked, f"AppBus leaked music signals: {leaked}"


@pytest.mark.usefixtures("qapp")
def test_get_bus_is_singleton() -> None:
    assert get_bus() is AppBus.get()
