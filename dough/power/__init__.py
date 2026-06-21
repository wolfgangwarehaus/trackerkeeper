"""Cross-platform "keep the machine awake" inhibitor.

A :class:`SleepInhibitor` asks the OS to hold off *system* sleep on demand:
the host app calls :meth:`SleepInhibitor.inhibit` when it needs the machine
to stay awake (a video playing, a slideshow presenting, a long export running)
and :meth:`SleepInhibitor.release` when it's done. dough owns the cross-platform
*how*, never the app-specific *when* — the base bus has no playback signals to
watch, so an app drives the inhibitor from its own events. The screen is
intentionally NOT kept awake — most workloads don't need the display, and users
expect the monitor to dim normally.

Backend (selected once per process, mirroring ``dough.autostart`` /
``dough.notifications``):
- Windows: ``SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)``
- Linux:   ``org.freedesktop.ScreenSaver`` Inhibit/UnInhibit (best-effort)
- other:   no-op
"""

from __future__ import annotations

import logging
from types import ModuleType

from PySide6.QtCore import QObject

logger = logging.getLogger(__name__)

_backend: ModuleType | None = None


def _select_backend() -> ModuleType:
    global _backend
    if _backend is not None:
        return _backend

    from dough.platform_compat import IS_LINUX, IS_WINDOWS

    if IS_WINDOWS:
        from dough.power import _windows as backend
    elif IS_LINUX:
        from dough.power import _linux as backend
    else:
        from dough.power import _unsupported as backend

    _backend = backend
    return _backend


def is_supported() -> bool:
    return _select_backend().is_supported()


class SleepInhibitor(QObject):
    """Holds off system sleep on demand.

    Driven by explicit :meth:`inhibit` / :meth:`release` — the host app decides
    WHEN (wire them to whatever events make sense; both accept extra args so they
    double as Qt signal slots), dough provides the cross-platform HOW. Idempotent:
    only true not-held↔held transitions reach the OS backend, and a backend
    failure never propagates (best-effort, like the notifications facade).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._inhibited = False

    def inhibit(self, *_):
        if self._inhibited:
            return
        try:
            if _select_backend().inhibit():
                self._inhibited = True
        except Exception as e:  # pragma: no cover — defensive
            logger.debug("sleep inhibit failed: %s", e)

    def release(self, *_):
        if not self._inhibited:
            return
        try:
            _select_backend().release()
        except Exception as e:  # pragma: no cover — defensive
            logger.debug("sleep release failed: %s", e)
        finally:
            self._inhibited = False
