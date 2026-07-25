"""Guard: the suite must never write to the developer's real per-user store.

Tests mutate settings through the SHIPPED ``get_settings()`` handle (e.g.
test_accent_live flips ``accent_color``). ``get_settings()`` keys off
``QSettings(identity.org(), identity.app())`` — the real config path — so
without isolation a plain ``pytest`` run clobbers the maker's live settings.
conftest sets it up at import; these prove it holds, so a future edit that drops
the isolation fails HERE instead of silently eating the maker's accent on the
next app restart.

**Two things have to be true, not one.** QStandardPaths test mode redirects
*paths*, but QSettings' NativeFormat is a different STORE per platform, and only
Linux's is a path that test mode can reach:

- **Linux** — an INI file under XDG config: test mode applies.
- **macOS** — a CFPreferences ``.plist``: test mode does NOT apply.
- **Windows** — the ``HKEY_CURRENT_USER`` registry: not a path at all.

So test mode alone left macOS and Windows writing to the maker's real store, and
CI caught exactly that (``~/Library/Preferences/…plist`` and
``HKEY_CURRENT_USER\\Software\\…``). Forcing ``IniFormat`` routes every platform
through QStandardPaths, which is what makes the redirect universal. Both halves
are asserted below — drop either and two of three platforms leak.

Everything here is derived from Qt at runtime rather than matched against a
literal path: the sandbox is ``~/.qttest`` on Unix and macOS but ``qttest`` (no
dot) under AppData on Windows, and hardcoding one shape is how this guard became
Linux-only in the first place.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

from trackerkeeper.settings import get_settings


def _config_root(test_mode: bool) -> Path:
    """Qt's writable generic-config dir with test mode forced on or off.
    Restores the previous mode unconditionally — leaking it off would silently
    unprotect every test that runs after this one."""
    was = QStandardPaths.isTestModeEnabled()
    try:
        QStandardPaths.setTestModeEnabled(test_mode)
        return Path(QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.GenericConfigLocation)).resolve()
    finally:
        QStandardPaths.setTestModeEnabled(was)


def test_qt_test_mode_is_enabled():
    assert QStandardPaths.isTestModeEnabled(), (
        "QStandardPaths test mode is off — QSettings writes would hit the real "
        "config store. conftest must call setTestModeEnabled(True) at import."
    )


def test_settings_default_format_is_ini():
    """The half that protects macOS and Windows.

    Test mode redirects paths, but NativeFormat on those two isn't a path — it's
    a plist and the registry. Without IniFormat they escape the sandbox no matter
    what test mode says.
    """
    assert QSettings.defaultFormat() == QSettings.Format.IniFormat, (
        "QSettings.defaultFormat() is not IniFormat — on macOS and Windows the "
        "suite would write to the developer's real plist/registry. conftest must "
        "call setDefaultFormat(IniFormat) before any QSettings is constructed."
    )


def test_the_handle_actually_adopts_that_format(qapp):
    """Setting the default format is not enough — the handle has to USE it.

    ``QSettings(org, app)`` hardwires NativeFormat and ignores
    ``setDefaultFormat()``. On Linux that is invisible, because NativeFormat is
    already an INI file under XDG config, so every path assertion still passes
    while macOS and Windows quietly resolve to a plist and the registry. This is
    the one check that fails on ALL THREE platforms when the handle is built with
    the bare ctor — which is why it exists as its own test.
    """
    assert get_settings()._s.format() == QSettings.Format.IniFormat, (
        "the Settings handle ignored setDefaultFormat() — it must be built with "
        "the (format, scope, org, app) ctor passing QSettings.defaultFormat(), "
        "not the bare (org, app) form."
    )


def test_settings_handle_is_isolated(qapp):
    """The live Settings handle resolves inside the test sandbox on EVERY
    platform, and is not reachable from the real per-user config dir."""
    path = Path(get_settings()._s.fileName()).resolve()
    sandbox = _config_root(test_mode=True)
    real = _config_root(test_mode=False)

    assert sandbox in path.parents, f"settings escaped the sandbox: {path}"
    assert real not in path.parents, f"settings hit the real config dir: {path}"


def test_the_handle_is_a_plain_file(qapp):
    """Otherwise the isolation above is decorative: `fileName()` under Windows
    NativeFormat returns a registry pseudo-path, which no amount of
    QStandardPaths redirection can sandbox."""
    name = get_settings()._s.fileName()
    assert "HKEY_" not in name, f"settings handle is a registry key: {name}"
    assert name.endswith((".ini", ".conf")), f"settings handle is not a file: {name}"
