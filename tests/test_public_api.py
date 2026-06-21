"""P1 — the curated public API, the AppBus factory seam, and run_app boot.

`import dough` must stay light (only identity + version eager) so a fork's
configure() can run before the chrome's import-time font-scale read; the rest of
the public surface resolves lazily. The AppBus factory seam is the prerequisite
for inverting an app's richer bus (jellytoast's PlayerBus) onto dough's base.
"""

from __future__ import annotations

import pytest


def test_public_api_resolves() -> None:
    import dough

    assert callable(dough.configure)  # eager
    assert callable(dough.run_app)  # lazy
    assert dough.AppWindow.__name__ == "AppWindow"
    assert callable(dough.get_settings)

    from dough.bus import AppBus

    assert dough.AppBus is AppBus


def test_import_dough_stays_light() -> None:
    """`import dough` must NOT pull the chrome (which reads QSettings at import
    time). design_tokens / window / app load only on first access."""
    import sys

    import dough  # noqa: F401  (ensure imported)

    # configure must be eagerly available...
    assert "dough.identity" in sys.modules
    # ...but accessing the lazy API is what imports the heavy modules. We can't
    # assert they're absent (other tests import them), so just prove the lazy
    # hook resolves a heavy module on demand.
    assert dough.run_app.__module__ == "dough.app"


def test_unknown_attr_raises() -> None:
    import dough

    with pytest.raises(AttributeError):
        dough.does_not_exist  # noqa: B018


@pytest.mark.usefixtures("qapp")
def test_appbus_factory_seam() -> None:
    """An app can register a bus subclass as the process-wide singleton, and the
    ordering guard rejects a late registration."""
    from dough.bus import AppBus

    saved_inst, saved_factory = AppBus._instance, AppBus._factory
    try:
        AppBus._instance = None
        AppBus._factory = None

        class MyBus(AppBus):
            pass

        AppBus.set_factory(MyBus)
        bus = AppBus.get()
        assert isinstance(bus, MyBus)
        assert AppBus.get() is bus  # cached singleton

        # set_factory after the singleton exists is an ordering error.
        with pytest.raises(RuntimeError):
            AppBus.set_factory(MyBus)
    finally:
        AppBus._instance, AppBus._factory = saved_inst, saved_factory


@pytest.mark.usefixtures("qapp")
def test_run_app_boots(monkeypatch) -> None:
    """run_app builds + shows the app and runs the loop. Patch exec() so it
    doesn't block, and disable the single-instance lock so the test holds none."""
    from PySide6.QtWidgets import QApplication, QLabel

    import dough

    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    code = dough.run_app(lambda window: QLabel("hi"), single_instance=False)
    assert code == 0
