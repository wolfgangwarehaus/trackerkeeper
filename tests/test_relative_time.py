"""The "how long ago" column + the channel column: pure display helpers, so no
qapp and no clock — ``now`` is injected for determinism."""

from __future__ import annotations

from datetime import datetime, timezone

from trackerkeeper import catalog
from trackerkeeper.dashboard import channel_label, humanize_age

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


def test_channel_labels_map_each_kind():
    assert channel_label(catalog.Item(name="x", kind="appstore")) == "App Store"
    assert channel_label(catalog.Item(name="x", kind="arch")) == "Arch"
    assert channel_label(catalog.Item(name="x", kind="github")) == "GitHub"
    assert channel_label(catalog.Item(name="x", kind="manual")) == "Manual"
