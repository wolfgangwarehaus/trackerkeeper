"""Stub autostart backend for platforms with no launch-on-login mechanism
(Linux, Windows, and macOS each have a real backend). Every call returns
False so the settings UI can hide the toggle and call sites no-op cleanly.
"""

from __future__ import annotations


def is_supported() -> bool:
    return False


def is_enabled() -> bool:
    return False


def enable() -> bool:
    return False


def disable() -> bool:
    return False
