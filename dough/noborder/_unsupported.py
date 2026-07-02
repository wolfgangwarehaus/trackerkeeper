"""No-op noborder backend for everything that isn't KDE Wayland.

The ``noborder`` KWin rule is a KDE-Wayland-specific workaround: it strips the
visible decoration from dough's server-side-decorated main window. On Windows,
macOS, X11, and non-KDE Wayland (GNOME, Sway, …) dough is either natively framed
or uses ``Qt.FramelessWindowHint``, so there is no compositor rule to write and
every call no-ops.
"""

from __future__ import annotations

from dough.platform_compat import (
    IS_LINUX,
    IS_MACOS,
    IS_WINDOWS,
    is_kde_desktop,
    will_be_wayland,
)


def is_supported() -> bool:
    return False


def install_main_window_noborder() -> bool:
    return False


def remove_main_window_noborder() -> bool:
    return False


def diagnose() -> dict:
    return {
        "backend": "unsupported",
        "is_supported": False,
        "is_linux": IS_LINUX,
        "is_windows": IS_WINDOWS,
        "is_macos": IS_MACOS,
        "is_kde": is_kde_desktop(),
        "is_wayland": will_be_wayland(),
    }
