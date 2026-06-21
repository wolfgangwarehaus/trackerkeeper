"""dough's identity seam — the one place app identity lives.

A fork renames itself by setting its identity ONCE. The simplest path is to edit
the three defaults below after renaming the package. For programmatic control,
call :func:`configure` before importing anything heavy::

    import dough
    dough.configure(org="acme", app="myapp", display_name="My App")
    from dough.app import main
    main()

Why it must come first, and why a function rather than ``QApplication``: the
font-scale loader in :mod:`dough.design_tokens` reads ``QSettings(org, app)`` at
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

# dough's own identity. `org` is the organization / vendor (Qt's
# organizationName, the QSettings org handle, and the {org} half of the AUMID);
# `app` is the application slug (Qt's applicationName, the QSettings app handle,
# the desktop / Wayland app name); `display_name` is the human-facing name (the
# window title / Qt applicationDisplayName). A fork overrides these.
_org = "wolfgangwarehaus"
_app = "dough"
_display_name = "dough"


def configure(
    *,
    org: str | None = None,
    app: str | None = None,
    display_name: str | None = None,
) -> None:
    """Set the app identity. Call ONCE, before importing ``dough.design_tokens``
    or ``dough.app`` (the font-scale loader reads the org/app pair at import
    time). Any argument left ``None`` keeps its current value, so a fork can pass
    only what differs."""
    global _org, _app, _display_name
    if org is not None:
        _org = org
    if app is not None:
        _app = app
    if display_name is not None:
        _display_name = display_name


def org() -> str:
    """Organization / vendor slug — Qt organizationName + the QSettings org."""
    return _org


def app() -> str:
    """Application slug — Qt applicationName + the QSettings app + desktop name."""
    return _app


def display_name() -> str:
    """Human-facing app name — window title / Qt applicationDisplayName."""
    return _display_name


def windows_aumid() -> str:
    """``{org}.{app}`` — the Windows AppUserModelID (taskbar / Start-menu
    identity). Also the seed for the winget PackageIdentifier and the MSIX
    Identity Name; see docs/BAKING.md §3.2."""
    return f"{_org}.{_app}"
