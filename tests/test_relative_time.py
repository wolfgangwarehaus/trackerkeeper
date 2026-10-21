"""The "how long ago" column + the channel column: pure display helpers, so no
qapp and no clock — ``now`` is injected for determinism."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from trackerkeeper import catalog
from trackerkeeper.dashboard import channel_label, humanize_age, local_time

NOW = datetime(2026, 7, 24, 14, 20, tzinfo=timezone.utc)


def test_empty_is_blank():
    assert humanize_age("", NOW) == ""
    assert humanize_age(None, NOW) == ""


def test_day_precision_reads_by_calendar():
    assert humanize_age("2026-07-24", NOW) == "today"
    assert humanize_age("2026-07-23", NOW) == "yesterday"
    assert humanize_age("2026-07-22", NOW) == "2 days ago"
    assert humanize_age("2026-07-03", NOW) == "3 weeks ago"
    assert humanize_age("2026-05-24", NOW) == "2 months ago"


def test_full_timestamp_gets_hour_and_minute_precision():
    assert humanize_age("2026-07-24T08:20:00Z", NOW) == "6 hours ago"
    assert humanize_age("2026-07-24T14:05:00Z", NOW) == "15 minutes ago"
    assert humanize_age("2026-07-24T14:19:40Z", NOW) == "just now"
    assert humanize_age("2026-07-24T14:19:00Z", NOW) == "1 minute ago"


def test_future_or_skew_never_negative():
    assert humanize_age("2026-07-24T15:00:00Z", NOW) == "just now"


_needs_tzset = pytest.mark.skipif(
    not hasattr(time, "tzset"), reason="TZ only rebinds the local zone on POSIX")


@_needs_tzset
def test_checked_stamp_reads_on_the_local_clock(monkeypatch):
    """The stored stamp is UTC; the provenance line shows the viewer's own
    clock. New York in August is UTC-4, so a 17:29Z stamp displays as 13:29 —
    the exact four-hour lie this helper exists to kill.

    ``monkeypatch.undo()`` restores the TZ *variable*, but only a second
    ``tzset()`` rebinds the process to it — without that, every test after this
    one silently runs in New York."""
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        assert local_time("2026-08-10 17:29") == "2026-08-10 13:29"
        assert local_time("2026-08-10T17:29:00Z") == "2026-08-10 13:29"
        assert local_time("2026-08-10 02:15") == "2026-08-09 22:15"  # date rolls back
    finally:
        monkeypatch.undo()
        time.tzset()


def test_local_time_ignores_what_it_cannot_parse():
    assert local_time("") == ""
    assert local_time(None) == ""
    assert local_time("whenever") == ""


def test_channel_labels_map_each_kind():
    assert channel_label(catalog.Item(name="x", kind="appstore")) == "App Store"
    assert channel_label(catalog.Item(name="x", kind="arch")) == "Arch"
    assert channel_label(catalog.Item(name="x", kind="github")) == "GitHub"
    assert channel_label(catalog.Item(name="x", kind="manual")) == "Manual"
