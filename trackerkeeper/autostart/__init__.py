"""Launch-on-login control. Public API is platform-agnostic; the actual
implementation lives in a per-OS backend module.

Public API:
    is_supported() -> bool   # backend can fulfil enable/disable
    is_enabled() -> bool     # currently set to launch on login
    enable() -> bool         # turn on; True iff the change took effect
    disable() -> bool        # turn off; True iff a previous entry was removed

Linux: writes/reads the XDG autostart entry in ~/.config/autostart.
Windows (MSIX package): the AppxManifest ``startupTask``, toggled through
the ``Windows.ApplicationModel.StartupTask`` WinRT API — packages can't use
the Run key.
Windows (Inno .exe / pip / source): a value under the per-user Run
registry key.
macOS: a LaunchAgent .plist in ~/Library/LaunchAgents with RunAtLoad for the
Dev-ID/.dmg/pip/source builds; an SMAppService login item for the sandboxed
Mac App Store build.
Everything else: the unsupported backend returns False from every call so
call sites can no-op cleanly.
"""

from __future__ import annotations

from trackerkeeper.platform_compat import IS_LINUX, IS_MACOS, IS_WINDOWS, is_msix_packaged

if IS_LINUX:
    from trackerkeeper.autostart import _linux as _backend
elif IS_WINDOWS and is_msix_packaged():
    from trackerkeeper.autostart import _msix as _backend
elif IS_WINDOWS:
    from trackerkeeper.autostart import _windows as _backend
elif IS_MACOS:
    from trackerkeeper.autostart import _macos as _backend
else:
    from trackerkeeper.autostart import _unsupported as _backend


def is_supported() -> bool:
    return _backend.is_supported()


def is_enabled() -> bool:
    return _backend.is_enabled()


def enable() -> bool:
    return _backend.enable()


def disable() -> bool:
    return _backend.disable()
