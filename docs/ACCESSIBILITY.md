# Accessibility

trackerkeeper's kit ships accessible by default, and a test keeps forks honest. Three
rules — they cost minutes at build time and are near-impossible to retrofit:

## 1. Name everything

Every interactive control must expose a non-empty `accessibleName()` **or**
visible text. An icon-only button with neither is a silent, unlabeled tab
stop to a screen reader.

- `IconButton(accessible_name="Settings")` — the preferred, explicit path.
  When omitted, the button's **tooltip doubles as its accessible name** (so
  every `setToolTip` call site is covered), and a tooltip that *differs*
  from an explicit name becomes the `accessibleDescription`. A button shown
  with neither logs a debug warning.
- `Selector(accessible_name="Theme")` — a selector reads as its current
  *value* ("Frosted dark"); pass the row label so it announces as
  "Theme, Frosted dark". Its popup inherits the name.
- `FrostedDialog(title=...)` mirrors the title into the window title and the
  dialog's accessible name; the ✕ glyph announces as "Close".
- `CircleSwatch` mirrors its tooltip into the name (same contract as
  IconButton).
- Wrap names in `self.tr(...)` like any user-facing string.

**Enforcement**: `tests/test_a11y.py` walks the demo window + settings
dialog and fails on any `QAbstractButton`/combo-like control that announces
as nothing. Fork the test along with the base; point it at your real
surfaces. Escape hatch for genuinely decorative controls, used sparingly:
`w.setProperty("a11y_exempt", True)` (bare trackerkeeper uses it zero times).

## 2. Focus must be visible

Anything focusable shows where focus is: chrome buttons use the platform
style's native focus indicator, `Selector` brightens its accent border on
`:focus`, list surfaces paint the accent keyboard-cursor ring via the
`trackerkeeper.keyboard_focus` recipe (`keyboard_focus_in/out`,
`keyboard_cursor_active`, `paint_kb_row_ring`). If you suppress an outline
in QSS, you owe a replacement affordance in the same commit.

## 3. A keyboard path for every mouse path

Anything clickable must be reachable and activatable without a mouse:
`install_arrow_nav` for horizontal button clusters, `install_row_grid_nav`
for hand-built row surfaces, Esc dismisses dialogs, and `FrostedDialog`
drops focus on the first interactive control at open. Popups already handle
arrows + Enter (`QMenu` natively; the long-list `Selector` focuses its list
on show).

## Screen-reader smoke testing

Automated checks catch *missing* names, not *bad* ones — eyeball with a real
reader occasionally:

- **Linux**: Orca (`orca` package; Super+Alt+S toggles it under GNOME; on
  KDE launch it manually). Qt speaks AT-SPI — run the app, Tab through, and
  listen for every stop announcing a sensible action word.
- **Windows**: Narrator (Win+Ctrl+Enter) or NVDA.
- **macOS**: VoiceOver (Cmd+F5).

Worth a pass whenever you add a new surface or rename chrome buttons.
