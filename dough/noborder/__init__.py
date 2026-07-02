"""KWin ``noborder`` window rule for dough's borderless main window.

On KDE Wayland dough's main window is deliberately **server-side-decorated**
(NOT ``Qt.FramelessWindowHint``): KWin's blur effect drops blur for
*undecorated* windows while they move, so a decorated window keeps its frost
through a drag. A KWin ``noborder`` Force rule then strips the *visible*
decoration so the window still looks frameless — the top bar is the titlebar.
Without this rule a fresh launch shows a doubled chrome (native titlebar + the
app's own top bar); with it, the single-chrome first-looks default holds.

The rule is matched on the app's **wmclass** (``dough.identity.app()``, the
app_id set via ``setDesktopFileName``) — stable regardless of the window title,
so an app is free to put a document name in its title. (jellytoast matched on an
exact title; dough matches wmclass so the title stays free.)

Public API:
    is_supported() -> bool               # backend can install/remove the rule
    install_main_window_noborder()       # idempotent install (borderless)
    remove_main_window_noborder()        # idempotent remove (native border)
    diagnose() -> dict                   # backend-specific debug snapshot

Wire it in ``run_app`` BEFORE the window maps (so a fresh launch never flashes a
titlebar): install when borderless, remove when the user has opted into
``native_window_border``. Idempotent + persisted, so every launch self-heals.

Linux + KDE + Wayland: the ``_kwin`` backend writes the rule into kwinrulesrc
and asks KWin to reconfigure. Anywhere else (X11, Windows, macOS, GNOME/wlroots
Wayland): the unsupported backend no-ops every call — those platforms either
honour the frame natively or use ``Qt.FramelessWindowHint`` and need no rule.

Note: KWin *keep-above* (always-on-top) rules — a jellytoast mini-player
feature — are intentionally not ported; dough has no generic use for one yet.
The rule-writing internals here are the pattern if a fork wants to add it.
"""

from __future__ import annotations

from dough.platform_compat import is_kde_wayland

# KDE Wayland is the only environment needing a compositor-side rule. Choose the
# backend at import time; the gate is stable for the life of the process.
if is_kde_wayland():
    from dough.noborder import _kwin as _backend
else:
    from dough.noborder import _unsupported as _backend


def is_supported() -> bool:
    return _backend.is_supported()


def install_main_window_noborder() -> bool:
    return _backend.install_main_window_noborder()


def remove_main_window_noborder() -> bool:
    return _backend.remove_main_window_noborder()


def diagnose() -> dict:
    return _backend.diagnose()
