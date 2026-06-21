"""Runtime guard for ``dough.power``.

The phantom-import smoke does NOT catch this one: ``dough.power`` imports
perfectly cleanly. The failure is a runtime ``AttributeError`` inside
``SleepInhibitor.start()``, which connects to ``bus.playback_*`` signals the
generic ``AppBus`` doesn't define — so only *calling* ``start()`` surfaces it.
That's exactly why the roadmap calls for a runtime test here, not just import-smoke.
"""

from __future__ import annotations

import pytest

from dough.power import SleepInhibitor, is_supported


@pytest.mark.usefixtures("qapp")
def test_is_supported_is_safe() -> None:
    """``is_supported()`` only touches the backend, never the bus — safe today."""
    assert isinstance(is_supported(), bool)


@pytest.mark.xfail(
    reason="P0: SleepInhibitor.start() connects bus.playback_* signals AppBus lacks "
    "(runtime AttributeError). Recast power/ to explicit inhibit()/release() and drop "
    "the phantom bus wiring, then remove this xfail.",
)
@pytest.mark.usefixtures("qapp")
def test_sleep_inhibitor_start_does_not_crash() -> None:
    """Wiring up the inhibitor must not raise. (A PDF viewer has no playback —
    the base must not assume music signals exist.)"""
    inh = SleepInhibitor()
    inh.start()
    inh.stop()
