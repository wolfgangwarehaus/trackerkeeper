"""i18n.fmt — locale-aware formatting helpers.

Pins the default QLocale per test (that's what every helper reads) and
asserts against known CLDR output for locales whose separators/order differ
from English — the point of the module is that "1,234.5" is NOT universal.
"""

from __future__ import annotations

import datetime

import pytest
from PySide6.QtCore import QLocale

from trackerkeeper.i18n import fmt


@pytest.fixture()
def pin_locale():
    """Set the default QLocale for a test, restore after — the helpers all
    format with QLocale() (the default), so this is the whole seam."""
    saved = QLocale()

    def _pin(name: str) -> None:
        QLocale.setDefault(QLocale(name))

    yield _pin
    QLocale.setDefault(saved)


class TestNumbers:
    def test_int_grouping_en(self, pin_locale):
        pin_locale("en_US")
        assert fmt.fmt_int(1234567) == "1,234,567"

    def test_int_grouping_de(self, pin_locale):
        pin_locale("de_DE")
        assert fmt.fmt_int(1234567) == "1.234.567"

    def test_int_grouping_es(self, pin_locale):
        pin_locale("es_ES")
        assert fmt.fmt_int(1234567) == "1.234.567"

    def test_decimal_de_swaps_separators(self, pin_locale):
        pin_locale("de_DE")
        assert fmt.fmt_decimal(1234.5) == "1.234,50"

    def test_decimal_en(self, pin_locale):
        pin_locale("en_US")
        assert fmt.fmt_decimal(1234.5) == "1,234.50"

    def test_decimal_precision(self, pin_locale):
        pin_locale("en_US")
        assert fmt.fmt_decimal(0.125, prec=3) == "0.125"

    def test_percent_takes_a_fraction(self, pin_locale):
        pin_locale("en_US")
        assert fmt.fmt_percent(0.42) == "42%"

    def test_percent_de_decimal(self, pin_locale):
        pin_locale("de_DE")
        assert fmt.fmt_percent(0.425, prec=1) == "42,5%"


class TestDatetime:
    _DT = datetime.datetime(2026, 7, 19, 15, 4)

    def test_order_differs_en_vs_de(self, pin_locale):
        pin_locale("en_US")
        en = fmt.fmt_datetime(self._DT)
        pin_locale("de_DE")
        de = fmt.fmt_datetime(self._DT)
        assert en != de
        # en_US leads month-first (7/19), de_DE day-first with dots (19.07).
        assert en.startswith("7/19")
        assert de.startswith("19.07")

    def test_de_24h_clock(self, pin_locale):
        pin_locale("de_DE")
        assert "15:04" in fmt.fmt_datetime(self._DT)

    def test_accepts_qdatetime(self, pin_locale):
        from PySide6.QtCore import QDateTime

        pin_locale("en_US")
        assert fmt.fmt_datetime(QDateTime(self._DT)) == fmt.fmt_datetime(self._DT)


class TestFileSize:
    def test_si_units_en(self, pin_locale):
        pin_locale("en_US")
        assert fmt.fmt_file_size(1_536_000) == "1.54 MB"

    def test_si_units_de_comma(self, pin_locale):
        pin_locale("de_DE")
        assert fmt.fmt_file_size(1_536_000) == "1,54 MB"

    def test_small_stays_bytes(self, pin_locale):
        pin_locale("en_US")
        assert fmt.fmt_file_size(512) == "512 bytes"


class TestDuration:
    # Untranslated, the numerus sources fall through with %n substituted —
    # the English rendering. A shipped catalog swaps per-language forms
    # (exercised end-to-end in test_i18n_plurals.py).
    def test_two_largest_units(self):
        assert fmt.fmt_duration(3600 + 23 * 60) == "1 h 23 min"

    def test_minutes_seconds(self):
        assert fmt.fmt_duration(23 * 60 + 4) == "23 min 4 s"

    def test_whole_units_drop_empty_tail(self):
        assert fmt.fmt_duration(7200) == "2 h"
        assert fmt.fmt_duration(300) == "5 min"

    def test_zero_and_negative_clamp(self):
        assert fmt.fmt_duration(0) == "0 s"
        assert fmt.fmt_duration(-5) == "0 s"

    def test_ms_keyword(self):
        assert fmt.fmt_duration(ms=83_000) == "1 min 23 s"

    def test_exactly_one_input(self):
        with pytest.raises(TypeError):
            fmt.fmt_duration()
        with pytest.raises(TypeError):
            fmt.fmt_duration(5, ms=5)
