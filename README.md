<h1 align="center">dough</h1>

<p align="center">
  A frosted, cross-platform <a href="https://doc.qt.io/qtforpython/">PySide6</a>
  app base — the shared starter every wolfgang warehaus app is baked from.
</p>

dough is a **fork-and-own starter**, not a dependency. Clone it, rename it,
delete what you don't need, and build. It solves the cross-platform window
chrome, the design system, and the platform scaffolding *once* — so a new app
is mostly its own idea plus a thin layer on top.

It boots to a themed, frosted, frameless window with a live Settings dialog —
a blank canvas with the hard parts already done. See
[`docs/PHILOSOPHY.md`](docs/PHILOSOPHY.md) for the why.

## What you get

- **`AppWindow`** — a frosted, frameless main window that's borderless on KDE
  Wayland and Windows (with the native-frame smooth-resize fix), shapes
  compositor blur to a rounded self-painted body, and falls back to a
  near-opaque panel where blur isn't available (never see-through).
- **Design system** — a three-family theme (frosted dark/light + solid), accent
  presets with WCAG-safe glyph contrast, scalable typography tiers, a 4-based
  spacing/radius scale. Live theme + accent switching, OS-following auto mode.
- **Widget kit** — `FrostedDialog`, the `Selector` dropdown, `IconButton` with
  crisp HiDPI icons, keyboard-nav helpers, a top bar that doubles as the titlebar.
- **Cross-platform scaffolding** — `platform_compat`, threaded `async_io`, the
  per-platform backend pattern (autostart / notifications / power), a minimal
  `AppBus` signal bus, slim persistent `Settings`, single-instance.
- **HiDPI done right** — PassThrough fractional scaling + device-pixel snapping.

## Quick start

```bash
git clone https://github.com/wolfgangwarehaus/dough.git
cd dough
pip install -e .
python -m dough          # or: dough  (the console script)
```

Runs straight from a checkout — the flat layout means no install is strictly
required (`python -m dough`).

## Make it yours

1. **Rename the package + identity.** Rename the `dough/` package to your app,
   then update the identity in three places (all currently `"dough"`):
   `dough/app.py` `APP_NAME`, `dough/settings.py` `_ORG`/`_APP`, and the
   `QSettings("dough", "dough")` pair in `dough/design_tokens.py::_load_font_scale`.
2. **Swap the placeholder.** Replace `dough/app.py::_placeholder()` and call
   `window.set_content(your_widget)`.
3. **Extend the bus.** Add your app's signals by subclassing `AppBus`
   (`dough/bus.py`); the base stays minimal.
4. **Keep it light.** Heavy/native deps (a PDF engine, mpv, …) go in
   `[project.optional-dependencies]`, never the PySide6-only core.

## Layout

```
dough/
  app.py          # main() + the placeholder you replace
  window.py       # AppWindow — the frosted cross-platform chrome
  top_bar.py      # the titlebar / top bar
  settings_dialog.py
  bus.py          # AppBus (signal bus)
  settings.py     # slim QSettings wrapper
  theme.py  design_tokens.py  color_tokens.py  ui_helpers.py   # the design system
  blur/  win_frameless.py  frosted_dialog.py  selector.py  icon_button.py  icons.py
  autostart/  notifications/  power/   # per-platform backend pattern
docs/PHILOSOPHY.md
```

## License

GPL-2.0-or-later (matching the warehaus family). It's a starter you own — feel
free to relicense your fork.
