"""Runtime guard for ``trackerkeeper.power``.

The phantom-import smoke does NOT catch this one: ``trackerkeeper.power`` imports
perfectly cleanly. The bug it guards was a runtime ``AttributeError`` inside the
old ``SleepInhibitor.start()``, which connected to ``bus.playback_*`` signals the
generic ``AppBus`` never defines — only *calling* it surfaced the failure, which
is exactly why a runtime test is needed here and import-smoke isn't enough. The
recast drives the inhibitor by explicit ``inhibit()`` / ``release()`` with no bus
at all.
"""

from __future__ import annotations

import pytest

from trackerkeeper.power import SleepInhibitor, is_supported


@pytest.mark.usefixtures("qapp")
def test_is_supported_is_safe() -> None:
    """``is_supported()`` only touches the backend, never the bus — safe."""
    assert isinstance(is_supported(), bool)


@pytest.mark.usefixtures("qapp")
def test_sleep_inhibitor_explicit_api_does_not_crash() -> None:
    """The inhibitor is driven by explicit inhibit()/release() — no music bus.
    A backend failure (e.g. no D-Bus session under CI) is swallowed best-effort,
    so neither call ever raises. (A PDF viewer has no playback; the base must not
    assume playback_* signals exist.)"""
    inh = SleepInhibitor()
    inh.inhibit()
    inh.release()
    inh.release()  # idempotent — releasing when not held is a no-op
