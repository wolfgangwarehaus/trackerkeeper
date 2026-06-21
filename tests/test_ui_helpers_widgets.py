"""Runtime construction guards for the carved-from-music widgets.

Both subscribe to the phantom ``dough.player_state.PlayerBus`` for live
re-theming. ``CoverOverlayButton`` wraps the import in try/except (so it
constructs, but silently loses the subscription); ``EmptyState`` does NOT —
its import is unwrapped, so merely constructing the widget hard-crashes with
``ModuleNotFoundError`` (the roadmap mislabeled this as a quiet failure).
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from dough.ui_helpers import CoverOverlayButton, EmptyState


@pytest.mark.usefixtures("qapp")
def test_cover_overlay_button_constructs() -> None:
    """Wrapped phantom import → constructs today, but the theme subscription
    silently no-ops. After the rewire onto AppBus it should subscribe for real."""
    parent = QWidget()
    btn = CoverOverlayButton(parent)
    assert btn is not None


@pytest.mark.xfail(
    reason="P0: EmptyState.__init__ imports phantom dough.player_state UNWRAPPED, so "
    "constructing the widget raises ModuleNotFoundError. Rewire onto dough.bus.AppBus, "
    "then remove this xfail.",
)
@pytest.mark.usefixtures("qapp")
def test_empty_state_constructs() -> None:
    """Building an EmptyState must not raise — it's reusable chrome, not music."""
    es = EmptyState(headline="Nothing here", sub="yet")
    assert es is not None
