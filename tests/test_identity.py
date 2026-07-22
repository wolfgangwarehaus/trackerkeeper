"""The identity seam — configure() is the one place app identity lives.

These lock the runtime half of the seam: trackerkeeper's own defaults, the deterministic
id projections, the QSettings handle keying off the SAME pair (the import-time
coupling the seam exists to fix), and that configure() reidentifies the whole app.
"""

from __future__ import annotations

import pytest

from trackerkeeper import identity


def test_default_identity() -> None:
    assert identity.org() == "wolfgangwarehaus"
    assert identity.app() == "trackerkeeper"
    assert identity.display_name() == "tracker keeper"


def test_windows_aumid_projection() -> None:
    # {org}.{app} — also the winget PackageIdentifier seed + MSIX Identity Name.
    assert identity.windows_aumid() == "wolfgangwarehaus.trackerkeeper"


def test_reverse_dns_projections() -> None:
    """The reverse-DNS / vendor ids every channel keys off (docs/BAKING.md §3.2).
    owner() defaults to org(); desktop_id() is app_id_base()."""
    assert identity.owner() == "wolfgangwarehaus"
    assert identity.app_id_base() == "io.github.wolfgangwarehaus.trackerkeeper"
    assert identity.cf_bundle_id() == "com.wolfgangwarehaus.trackerkeeper"
    assert identity.desktop_id() == identity.app_id_base()


def test_pure_projection_helpers() -> None:
    """The pure helpers the build-time renderer (trackerkeeper.metadata) shares with the
    runtime seam — same formula, explicit inputs."""
    assert identity.aumid_for("acme", "myapp") == "acme.myapp"
    assert identity.app_id_base_for("acme", "myapp") == "io.github.acme.myapp"
    assert identity.cf_bundle_id_for("acme", "myapp") == "com.acme.myapp"


def test_owner_overrides_independently_of_org() -> None:
    """owner can diverge from org (a fork published under a different GitHub
    account than its vendor slug). Restores trackerkeeper's identity after — including
    the raw ``_owner`` sentinel (configure() can't reset it to None, so the
    track-org default would be lost otherwise)."""
    saved_org, saved_app = identity.org(), identity.app()
    saved_owner_raw = identity._owner  # the None/track-org sentinel, white-box
    try:
        identity.configure(org="vendor", app="thing", owner="ghuser")
        assert identity.app_id_base() == "io.github.ghuser.thing"
        assert identity.cf_bundle_id() == "com.vendor.thing"
        assert identity.windows_aumid() == "vendor.thing"
    finally:
        identity.configure(org=saved_org, app=saved_app)
        identity._owner = saved_owner_raw
    assert identity.owner() == "wolfgangwarehaus"  # tracks org again
    assert identity.app_id_base() == "io.github.wolfgangwarehaus.trackerkeeper"


@pytest.mark.usefixtures("qapp")
def test_settings_handle_keys_off_identity() -> None:
    """The QSettings handle (settings.py) keys off the SAME org/app pair the seam
    holds — the pair design_tokens also reads at import time."""
    from trackerkeeper.settings import Settings

    s = Settings()._s
    assert s.organizationName() == identity.org()
    assert s.applicationName() == identity.app()


def test_configure_reidentifies_then_restores() -> None:
    """configure() reidentifies the app and the projections follow. Restores
    trackerkeeper's own identity so the rest of the suite is unaffected."""
    saved = (identity.org(), identity.app(), identity.display_name())
    try:
        identity.configure(org="acme", app="myapp", display_name="My App")
        assert identity.org() == "acme"
        assert identity.app() == "myapp"
        assert identity.display_name() == "My App"
        assert identity.windows_aumid() == "acme.myapp"
        # partial update keeps the rest
        identity.configure(display_name="Renamed")
        assert identity.org() == "acme" and identity.app() == "myapp"
        assert identity.display_name() == "Renamed"
    finally:
        identity.configure(org=saved[0], app=saved[1], display_name=saved[2])
    assert identity.windows_aumid() == "wolfgangwarehaus.trackerkeeper"
