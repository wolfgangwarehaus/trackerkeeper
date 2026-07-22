"""Locale-aware formatting — the one door user-visible numbers go through.

Never f-string a number, date, or size into a user-visible string: ``f"{n}"``
bakes in English digits/separators ("1,234.5") that read wrong — or ambiguous
— in most locales (German swaps them: "1.234,5"). Route every value through
these helpers instead; each one formats with ``QLocale()`` (the default
locale, which tracks the app's installed language — Qt derives it from the
system, and a fork that pins language can ``QLocale.setDefault`` alongside
its translator install).

.. code-block:: python

    from trackerkeeper.i18n.fmt import fmt_int, fmt_duration

    label.setText(self.tr("{0} items · {1}").format(
        fmt_int(count), fmt_duration(total_seconds)))

Everything here is a thin veneer over ``QLocale`` — Qt owns the CLDR data —
EXCEPT :func:`fmt_duration`: Qt has no native duration formatter, so that one
is hand-rolled from translated unit strings with plural (numerus) forms. It's
deliberately the only hand-rolled piece; if Qt ever grows one, delete ours.
"""

from __future__ import annotations

import datetime as _datetime

from PySide6.QtCore import QDateTime, QLocale, QObject


def fmt_int(n: int) -> str:
    """``1234567`` → ``"1,234,567"`` (en) / ``"1.234.567"`` (de/es) — the
    locale's digit grouping."""
    return QLocale().toString(int(n))


def fmt_decimal(x: float, prec: int = 2) -> str:
    """``1234.5`` → ``"1,234.50"`` (en) / ``"1.234,50"`` (de) — fixed
    ``prec`` decimals with the locale's separators."""
    return QLocale().toString(float(x), "f", prec)


def fmt_percent(fraction: float, prec: int = 0) -> str:
    """``0.42`` → ``"42%"`` with the locale's number formatting and percent
    sign. Takes a FRACTION (0..1), not a pre-multiplied percentage.

    Composed as number + ``QLocale().percent()`` — Qt exposes the localized
    sign but not the CLDR placement pattern, so locales that prefix the sign
    (Turkish "%42") get the suffix form. Acceptable for a base; revisit if a
    fork ships one of those locales.
    """
    loc = QLocale()
    return loc.toString(float(fraction) * 100.0, "f", prec) + loc.percent()


def fmt_datetime(
    dt: "_datetime.datetime | QDateTime",
    format: QLocale.FormatType = QLocale.FormatType.ShortFormat,
) -> str:
    """A date+time in the locale's own order and separators — ``ShortFormat``
    (default) is the compact everyday form ("7/19/26 3:04 PM" en_US,
    "19.07.26 15:04" de). Accepts a Python ``datetime`` or a ``QDateTime``."""
    if isinstance(dt, _datetime.datetime):
        dt = QDateTime(dt)
    return QLocale().toString(dt, format)


def fmt_file_size(n_bytes: int) -> str:
    """``1536000`` → ``"1.54 MB"`` (en) / ``"1,54 MB"`` (de) — SI units
    (kB/MB/GB, powers of 1000) via ``QLocale.formattedDataSize``."""
    return QLocale().formattedDataSize(
        int(n_bytes), 2, QLocale.DataSizeFormat.DataSizeSIFormat
    )


class _DurationUnits(QObject):
    """Translated duration unit strings — a QObject solely so the strings go
    through ``self.tr(source, disambiguation, n)``, the ONE Python idiom
    pyside6-lupdate extracts as a numerus (plural-forms) message. The
    module-level functions people actually call wrap :func:`fmt_duration`;
    plain ``QCoreApplication.translate(..., n)`` is NOT picked up as numerus
    by lupdate's Python parser (verified 2026-07), so don't "simplify" this
    class away."""

    def hours(self, n: int) -> str:
        # "h" needs no English plural; translators fill one numerusform per
        # plural class of their language.
        return self.tr("%n h", "duration: hours, abbreviated", n)

    def minutes(self, n: int) -> str:
        return self.tr("%n min", "duration: minutes, abbreviated", n)

    def seconds(self, n: int) -> str:
        return self.tr("%n s", "duration: seconds, abbreviated", n)

    def join(self, big: str, small: str) -> str:
        # The two-unit joiner ("1 h 23 min"). A translated template rather
        # than a hardcoded space so locales that join differently (or reverse
        # order) can express it.
        return self.tr("{0} {1}", "duration: joins two units, largest first").format(
            big, small
        )


_units: _DurationUnits | None = None


def _get_units() -> _DurationUnits:
    global _units
    if _units is None:
        _units = _DurationUnits()
    return _units


def fmt_duration(seconds: float | None = None, *, ms: int | None = None) -> str:
    """A duration as its two largest non-zero units — ``"1 h 23 min"``,
    ``"23 min 4 s"``, ``"42 s"`` — built from translated, plural-aware unit
    strings (see :class:`_DurationUnits`; Qt has no native duration
    formatter, so this is the module's one hand-rolled formatter).

    Pass EITHER ``seconds`` (positional) or ``ms=`` (keyword). Sub-minute
    remainders under an hour show seconds; whole hours/minutes drop the empty
    tail (``"2 h"``, not ``"2 h 0 min"``). Zero → ``"0 s"``.
    """
    if (seconds is None) == (ms is None):
        raise TypeError("fmt_duration takes exactly one of `seconds` or `ms`")
    total = int(round(ms / 1000.0)) if ms is not None else int(round(seconds))
    if total < 0:
        total = 0
    u = _get_units()
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return u.join(u.hours(h), u.minutes(m)) if m else u.hours(h)
    if m:
        return u.join(u.minutes(m), u.seconds(s)) if s else u.minutes(m)
    return u.seconds(s)
