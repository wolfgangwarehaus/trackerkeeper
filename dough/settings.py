"""Slim persistent settings (QSettings-backed).

dough keeps a tiny, generic settings surface: theme, accent, font scale,
window-chrome toggles, and a couple of platform-integration switches. Apps add
their own keys by subclassing ``Settings`` or calling ``get_settings()._s``
(the raw ``QSettings``) directly.

The handle is ``QSettings(identity.org(), identity.app())`` — the SAME pair
``design_tokens`` uses at import time, so font scaling resolves identically
whether or not a QApplication exists yet. Fork note: set your identity once in
``dough.identity`` (or via ``dough.configure(...)``); this reads from there.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings

from dough import identity


def _as_bool(val, default: bool) -> bool:
    # QSettings round-trips bools as "true"/"false" strings on some backends.
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on")
    if val is None:
        return default
    return bool(val)


class Settings:
    """Typed accessors over a single ``QSettings`` handle. Every property has a
    getter (with a sensible default) and a setter that writes + syncs."""

    def __init__(self) -> None:
        self._s = QSettings(identity.org(), identity.app())

    def _set(self, key: str, value) -> None:
        self._s.setValue(key, value)
        self._s.sync()

    # ── Appearance ────────────────────────────────────────────────────
    @property
    def theme_mode(self) -> str:  # auto | frosted_dark | frosted_light | dark | light
        return str(self._s.value("ui/theme_mode", "auto"))

    @theme_mode.setter
    def theme_mode(self, v: str) -> None:
        self._set("ui/theme_mode", v)

    @property
    def accent_color(self) -> str:
        return str(self._s.value("ui/accent_color", "#7C66D0"))

    @accent_color.setter
    def accent_color(self, v: str) -> None:
        self._set("ui/accent_color", v)

    @property
    def follow_system_accent(self) -> bool:
        # Follow the desktop's accent colour (XDG portal / DWM / AppKit) —
        # read at launch + watched live by dough.system_accent. Off by default.
        return _as_bool(self._s.value("ui/follow_system_accent"), False)

    @follow_system_accent.setter
    def follow_system_accent(self, v: bool) -> None:
        self._set("ui/follow_system_accent", bool(v))

    @property
    def font_scale(self) -> str:  # small | default | large | largest
        return str(self._s.value("ui/font_scale", "default"))

    @font_scale.setter
    def font_scale(self, v: str) -> None:
        self._set("ui/font_scale", v)

    @property
    def font_family(self) -> str:
        # User-chosen UI text font family; "" means the system/built-in default.
        # Applied app-wide via the global QSS font-family rule + app.setFont;
        # SVG icons are never affected.
        return str(self._s.value("ui/font_family", ""))

    @font_family.setter
    def font_family(self, v: str) -> None:
        self._set("ui/font_family", v)

    # ── Window chrome ─────────────────────────────────────────────────
    @property
    def native_window_border(self) -> bool:
        return _as_bool(self._s.value("ui/native_window_border"), False)

    @native_window_border.setter
    def native_window_border(self, v: bool) -> None:
        self._set("ui/native_window_border", bool(v))

    @property
    def square_corners(self) -> bool:
        # When True every rounded corner in the UI — windows, tiles, dialogs,
        # buttons, popups — is squared off; genuinely circular controls (round
        # icon buttons, slider handles) stay round. Baked into design_tokens at
        # module import, so it takes effect on the next launch.
        return _as_bool(self._s.value("ui/square_corners"), False)

    @square_corners.setter
    def square_corners(self, v: bool) -> None:
        self._set("ui/square_corners", bool(v))

    @property
    def auto_hide_scrollbars(self) -> bool:
        """Minimal fading scrollbars (default) vs always-visible standard ones. The
        SETTING is dough-base; an app wires install_autofade_scrollbars on its own
        scroll areas when this is on (dough can't know which scroll areas an app has)."""
        return _as_bool(self._s.value("ui/auto_hide_scrollbars"), True)

    @auto_hide_scrollbars.setter
    def auto_hide_scrollbars(self, v: bool) -> None:
        self._set("ui/auto_hide_scrollbars", bool(v))

    @property
    def show_tooltips(self) -> bool:
        return _as_bool(self._s.value("ui/show_tooltips"), True)

    @show_tooltips.setter
    def show_tooltips(self, v: bool) -> None:
        self._set("ui/show_tooltips", bool(v))

    @property
    def language(self) -> str:
        # UI language override — a bare code like "es", or "" (default) to
        # follow the system locale. "en" pins English (skips the system
        # locale). Read by dough.i18n at boot; restart-applied.
        return self._s.value("ui/language", "", type=str)

    @language.setter
    def language(self, v: str) -> None:
        self._set("ui/language", (v or "").strip().lower())

    # ── Platform integration toggles ──────────────────────────────────
    @property
    def autostart(self) -> bool:
        return _as_bool(self._s.value("app/autostart"), False)

    @autostart.setter
    def autostart(self, v: bool) -> None:
        self._set("app/autostart", bool(v))

    @property
    def check_for_updates(self) -> bool:
        # Daily GitHub latest-release check (dough.updates) — the chip in the
        # top bar. On by default; auto-updating channels (Store / MAS / AUR)
        # are suppressed regardless of this toggle.
        return _as_bool(self._s.value("app/check_for_updates"), True)

    @check_for_updates.setter
    def check_for_updates(self, v: bool) -> None:
        self._set("app/check_for_updates", bool(v))

    @property
    def update_last_check_time(self) -> int:
        # Unix timestamp of the last update check — the daily throttle.
        try:
            return int(self._s.value("app/update_last_check_time", 0))
        except (TypeError, ValueError):
            return 0

    @update_last_check_time.setter
    def update_last_check_time(self, v: int) -> None:
        self._set("app/update_last_check_time", int(v))

    @property
    def update_dismissed_version(self) -> str:
        # The release tag the user dismissed — that version never re-nags.
        return self._s.value("app/update_dismissed_version", "", type=str)

    @update_dismissed_version.setter
    def update_dismissed_version(self, v: str) -> None:
        self._set("app/update_dismissed_version", str(v or ""))

    @property
    def notify_on_track_change(self) -> bool:
        # Generic "show notifications" toggle (name kept for the lifted
        # notifications backend); rename freely in a fork.
        return _as_bool(self._s.value("app/notify_on_track_change"), True)

    @notify_on_track_change.setter
    def notify_on_track_change(self, v: bool) -> None:
        self._set("app/notify_on_track_change", bool(v))

    # ── Window geometry ───────────────────────────────────────────────
    def save_geometry(self, win) -> None:
        self._s.setValue("win/geometry", win.saveGeometry())
        self._s.sync()

    def restore_geometry(self, win) -> bool:
        g = self._s.value("win/geometry")
        if isinstance(g, QByteArray) and not g.isEmpty():
            win.restoreGeometry(g)
            return True
        return False

    def flush(self) -> None:
        """Force-write to disk. Call after a settings change on a shutdown
        path that may skip the QSettings destructor flush (e.g. a tray Quit)."""
        self._s.sync()


_inst: "Settings | None" = None


def get_settings() -> Settings:
    global _inst
    if _inst is None:
        _inst = Settings()
    return _inst
