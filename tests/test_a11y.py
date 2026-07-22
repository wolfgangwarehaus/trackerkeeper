"""Accessibility gate — every interactive control announces as SOMETHING.

The rule (docs/ACCESSIBILITY.md): an interactive widget must expose a
non-empty ``accessibleName()`` OR visible text — an icon-only button with
neither is a silent, unlabeled tab stop to a screen reader. This test walks
the real surfaces a bare fork ships (the demo window + the settings dialog)
and fails on any violator, so future apps inherit the honesty check.

Opt-out: ``setProperty("a11y_exempt", True)`` — for genuinely decorative
controls only, used sparingly (zero in bare trackerkeeper).
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QAbstractButton, QComboBox, QWidget

from trackerkeeper.selector import Selector


def _announces(w: QWidget) -> bool:
    if w.accessibleName():
        return True
    text = getattr(w, "text", None)
    return bool(text and text())


def _violations(root: QWidget) -> list[str]:
    out = []
    interactive = list(root.findChildren(QAbstractButton))
    interactive += list(root.findChildren(QComboBox))
    # Selector IS a QPushButton (caught above) — listed for clarity should
    # its base class ever change.
    interactive += [w for w in root.findChildren(Selector) if w not in interactive]
    for w in interactive:
        if w.property("a11y_exempt"):
            continue
        if not _announces(w):
            out.append(
                f"{type(w).__name__}(objectName={w.objectName()!r}, "
                f"tooltip={w.toolTip()!r})"
            )
    return out


@pytest.mark.usefixtures("qapp")
def test_demo_window_all_controls_announce() -> None:
    from trackerkeeper.app import _placeholder
    from trackerkeeper.window import AppWindow

    win = AppWindow(title="trackerkeeper")
    win.set_content(_placeholder())
    bad = _violations(win)
    assert not bad, f"controls with no accessible name or text: {bad}"


@pytest.mark.usefixtures("qapp")
def test_settings_dialog_all_controls_announce() -> None:
    from trackerkeeper.settings_dialog import SettingsDialog

    dlg = SettingsDialog()
    bad = _violations(dlg)
    assert not bad, f"controls with no accessible name or text: {bad}"
    dlg.close()


class TestIconButtonNaming:
    """The constructor/fallback contract on the kit's icon-only button."""

    def test_explicit_name(self, qapp) -> None:
        from trackerkeeper.icon_button import IconButton

        b = IconButton(accessible_name="Play")
        assert b.accessibleName() == "Play"

    def test_tooltip_falls_back_to_name(self, qapp) -> None:
        from trackerkeeper.icon_button import IconButton

        b = IconButton()
        b.setToolTip("Shuffle")
        assert b.accessibleName() == "Shuffle"

    def test_explicit_name_wins_over_tooltip(self, qapp) -> None:
        from trackerkeeper.icon_button import IconButton

        b = IconButton(accessible_name="Play")
        b.setToolTip("Play the current queue")
        assert b.accessibleName() == "Play"
        # A tooltip that differs from the name becomes the description.
        assert b.accessibleDescription() == "Play the current queue"

    def test_top_bar_buttons_named(self, qapp) -> None:
        from trackerkeeper.window import AppWindow

        win = AppWindow(title="trackerkeeper")
        assert win.top_bar.settings_btn.accessibleName() == "Settings"


class TestFrostedDialogA11y:
    def test_title_becomes_accessible_name(self, qapp) -> None:
        from trackerkeeper.frosted_dialog import FrostedDialog

        dlg = FrostedDialog(title="Import failed")
        assert dlg.accessibleName() == "Import failed"
        assert dlg.windowTitle() == "Import failed"
        dlg.close()

    def test_close_glyph_named(self, qapp) -> None:
        from PySide6.QtWidgets import QPushButton

        from trackerkeeper.frosted_dialog import FrostedDialog

        dlg = FrostedDialog(title="x")
        glyphs = [b for b in dlg.findChildren(QPushButton) if b.text() == "✕"]
        assert glyphs and all(b.accessibleName() == "Close" for b in glyphs)
        dlg.close()

    def test_focus_lands_on_a_control(self, qapp) -> None:
        from trackerkeeper.frosted_dialog import FrostedMessageDialog

        dlg = FrostedMessageDialog(None, title="t", text="body")
        dlg.show()
        qapp.processEvents()
        fw = dlg.focusWidget()
        assert fw is not None and fw is not dlg
        dlg.close()
