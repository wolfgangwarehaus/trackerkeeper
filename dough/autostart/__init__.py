"""Launch-on-login control. Public API is platform-agnostic; the actual
implementation lives in a per-OS backend module.

Public API:
    is_supported() -> bool   # backend can fulfil enable/disable
    is_enabled() -> bool     # currently set to launch on login
    enable() -> bool         # turn on; True iff the change took effect
    disable() -> bool        # turn off; True iff a previous entry was removed

Linux: writes/reads ~/.config/autostart/dough.desktop (XDG).
Linux under Flatpak: the XDG Background portal instead — the sandbox's
autostart dir is private and Flathub forbids the filesystem grant
(see dough/autostart/_flatpak.py for the contract drift).
Windows: a value under the per-user Run registry key.
macOS: not yet implemented — the unsupported backend returns False from
every call so call sites can no-op cleanly.
"""

from __future__ import annotations

from dough.platform_compat import IS_FLATPAK, IS_LINUX, IS_WINDOWS

if IS_LINUX and IS_FLATPAK:
    from dough.autostart import _flatpak as _backend
elif IS_LINUX:
    from dough.autostart import _linux as _backend
elif IS_WINDOWS:
    from dough.autostart import _windows as _backend
else:
    from dough.autostart import _unsupported as _backend


def is_supported() -> bool:
    return _backend.is_supported()


def is_enabled() -> bool:
    return _backend.is_enabled()


def enable() -> bool:
    return _backend.enable()


def disable() -> bool:
    return _backend.disable()
