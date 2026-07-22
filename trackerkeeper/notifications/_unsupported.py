"""Stub notifications backend for platforms where desktop notifications
aren't wired up yet, and the graceful-degradation target when a real
backend can't be imported (missing package/runtime). `is_supported()`
returns False so settings UI can hide notification preferences, and
`notify()` is a silent no-op.
"""

from __future__ import annotations


def is_supported() -> bool:
    return False


def notify(
    title: str,
    body: str = "",
    icon: str | None = None,
    app_name: str | None = None,
    tag: str | None = None,
) -> None:
    return None
