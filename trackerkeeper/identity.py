"""trackerkeeper's identity seam — the one place app identity lives.

A fork renames itself by setting its identity ONCE. The simplest path is to edit
the three defaults below after renaming the package. For programmatic control,
call :func:`configure` before importing anything heavy::

    import trackerkeeper
    trackerkeeper.configure(org="acme", app="myapp", display_name="My App")
    from trackerkeeper.app import main
    main()

Why it must come first, and why a function rather than ``QApplication``: the
font-scale loader in :mod:`trackerkeeper.design_tokens` reads ``QSettings(org, app)`` at
IMPORT time — before a QApplication exists — so the identity it keys off cannot
come from ``QApplication.applicationName()``. This module holds it instead, so
``design_tokens``, ``settings``, and the app shell all read the SAME pair, and
the projections (the Windows AUMID, the single-instance key) derive from it
rather than being re-literalised across a dozen files.

The split (see docs/BAKING.md §4): this seam owns RUNTIME identity — ``org``,
``app``, ``display_name``, and their deterministic id projections. Descriptive /
packaging metadata (summary, license, categories, screenshots, the reverse-DNS
app-id the installers key off) lives in the build-time metadata sidecar, NOT here.
"""

from __future__ import annotations

# trackerkeeper's own identity. `org` is the organization / vendor (Qt's
# organizationName, the QSettings org handle, and the {org} half of the AUMID);
# `app` is the application slug (Qt's applicationName, the QSettings app handle,
# the desktop / Wayland app name); `display_name` is the human-facing name (the
# window title / Qt applicationDisplayName); `owner` is the GitHub owner (the
# {owner} of the reverse-DNS app-id). A fork overrides these. `owner` defaults to
# `org` — they coincide for these projects, so a fork that renames only `org`
# gets a matching `app_id_base` for free.
_org = "wolfgangwarehaus"
_app = "trackerkeeper"
_display_name = "Tracker Keeper"
_owner: str | None = None  # None ⇒ track `org` (see owner())


def configure(
    *,
    org: str | None = None,
    app: str | None = None,
    display_name: str | None = None,
    owner: str | None = None,
) -> None:
    """Set the app identity. Call ONCE, before importing ``trackerkeeper.design_tokens``
    or ``trackerkeeper.app`` (the font-scale loader reads the org/app pair at import
    time). Any argument left ``None`` keeps its current value, so a fork can pass
    only what differs. ``owner`` is the GitHub owner for the reverse-DNS app-id;
    leave it unset and it tracks ``org``."""
    global _org, _app, _display_name, _owner
    if org is not None:
        _org = org
    if app is not None:
        _app = app
    if display_name is not None:
        _display_name = display_name
    if owner is not None:
        _owner = owner


def org() -> str:
    """Organization / vendor slug — Qt organizationName + the QSettings org."""
    return _org


def app() -> str:
    """Application slug — Qt applicationName + the QSettings app + desktop name."""
    return _app


def display_name() -> str:
    """Human-facing app name — window title / Qt applicationDisplayName."""
    return _display_name


def owner() -> str:
    """GitHub owner — the ``{owner}`` half of ``app_id_base``. Defaults to
    ``org`` when not configured explicitly."""
    return _owner if _owner is not None else _org


# ── id projections ──────────────────────────────────────────────────────────
# The reverse-DNS / vendor ids every channel keys off, derived from the identity
# above. Each has a PURE helper (``*_for(...)``) that takes its inputs
# explicitly, plus a no-arg runtime form that feeds it the live identity. The
# build-time renderer (trackerkeeper.metadata) calls the SAME pure helpers with the
# sidecar's slugs — so the manifests and the running app share one formula, and
# the verify gate (tests/test_metadata.py) proves the two data sources agree.
# See docs/BAKING.md §3.2.


def aumid_for(org: str, app: str) -> str:
    """``{org}.{app}`` — the Windows AppUserModelID, the winget
    PackageIdentifier seed, and the MSIX Identity Name."""
    return f"{org}.{app}"


def app_id_base_for(owner: str, app: str) -> str:
    """``io.github.{owner}.{app}`` — the single most load-bearing id: the
    reverse-DNS application identity (Flatpak/freedesktop/.desktop/icon names,
    deb+AppImage+AUR install paths, the Wayland app_id). Immutable once
    published."""
    return f"io.github.{owner}.{app}"


def cf_bundle_id_for(org: str, app: str) -> str:
    """``com.{org}.{app}`` — the macOS CFBundleIdentifier and the cask ``zap``."""
    return f"com.{org}.{app}"


def windows_aumid() -> str:
    """The live Windows AppUserModelID — ``aumid_for(org, app)``."""
    return aumid_for(_org, _app)


def app_id_base() -> str:
    """The live reverse-DNS app-id — ``app_id_base_for(owner, app)``."""
    return app_id_base_for(owner(), _app)


def cf_bundle_id() -> str:
    """The live macOS bundle id — ``cf_bundle_id_for(org, app)``."""
    return cf_bundle_id_for(_org, _app)


def desktop_id() -> str:
    """The freedesktop desktop-id — the basename of the installed
    ``{app_id_base}.desktop`` and the value ``setDesktopFileName`` should carry
    so the Wayland taskbar associates the window with its installed icon. Equal
    to :func:`app_id_base`."""
    return app_id_base()
