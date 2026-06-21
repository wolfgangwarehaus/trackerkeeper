"""The identity seam — configure() is the one place app identity lives.

These lock the runtime half of the seam: dough's own defaults, the deterministic
id projections, the QSettings handle keying off the SAME pair (the import-time
coupling the seam exists to fix), and that configure() reidentifies the whole app.
"""

from __future__ import annotations

import pytest

from dough import identity


def test_default_identity() -> None:
    assert identity.org() == "wolfgangwarehaus"
    assert identity.app() == "dough"
    assert identity.display_name() == "dough"


def test_windows_aumid_projection() -> None:
    # {org}.{app} — also the winget PackageIdentifier seed + MSIX Identity Name.
    assert identity.windows_aumid() == "wolfgangwarehaus.dough"


@pytest.mark.usefixtures("qapp")
def test_settings_handle_keys_off_identity() -> None:
    """The QSettings handle (settings.py) keys off the SAME org/app pair the seam
    holds — the pair design_tokens also reads at import time."""
    from dough.settings import Settings

    s = Settings()._s
    assert s.organizationName() == identity.org()
    assert s.applicationName() == identity.app()


def test_configure_reidentifies_then_restores() -> None:
    """configure() reidentifies the app and the projections follow. Restores
    dough's own identity so the rest of the suite is unaffected."""
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
    assert identity.windows_aumid() == "wolfgangwarehaus.dough"
