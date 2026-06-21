"""The boot-smoke, as a real test.

ci.yml already boots dough via an inline ``python -c``; this is the same path
expressed as a pytest case so it runs in the suite, gates locally, and can grow
assertions. It's the fork-and-own promise in one test: AppWindow + the
placeholder + the settings dialog construct and show without error.
"""

from __future__ import annotations

import pytest


@pytest.mark.usefixtures("qapp")
def test_app_boots(qapp) -> None:
    import dough.app as app_module
    from dough.window import AppWindow

    win = AppWindow(title="dough")
    win.set_content(app_module._placeholder())
    win.show()
    qapp.processEvents()
    assert win.isVisible()


@pytest.mark.usefixtures("qapp")
def test_settings_dialog_opens(qapp) -> None:
    from dough.settings_dialog import SettingsDialog
    from dough.window import AppWindow

    win = AppWindow(title="dough")
    dlg = SettingsDialog(win)
    dlg.show()
    qapp.processEvents()
    assert dlg is not None
