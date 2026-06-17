# dough — philosophy

**dough** is the shared base every wolfgang warehaus app is baked from. It's
the cross-platform window chrome, the design system, and the platform
scaffolding — solved once, so a new app is mostly *its own idea* plus a thin
layer on top. toast (jellytoast) was the first loaf; dough is the starter
everything else rises from.

dough is a **fork-and-own starter**, not a dependency. Clone it, rename it,
delete what you don't need, and build. It gives you base classes and helpers;
it never imposes a framework, a lifecycle, or an architecture.

Three things make dough good. Each is a principle, *why* it holds (research +
what jellytoast proved in production), and what it means concretely here.

---

## 1. A good creation medium

- **Boots to a window with almost no app code.** The hundreds of lines of
  frameless / blur / native-frame / HiDPI handling live in the `AppWindow`
  base. A new app is `class MyWindow(AppWindow): ...` plus content. You never
  re-solve chrome.
- **Degrades to a no-op off its platform.** Blur, the Windows native frame,
  autostart, notifications — each silently falls back where it isn't
  supported (`blur/_unsupported`, the frosted fallback alpha). That's *why*
  one codebase runs on KDE/Wayland and Windows without `if platform:`
  scattered through app code.
- **One decoupled bus.** `AppBus` (Qt signals): the UI emits intents, the
  backend reacts, neither holds a reference to the other. dough ships only the
  generic chrome signals; an app extends the bus with its own. (jellytoast's
  `PlayerBus` grew to 60+ signals — dough keeps the bus minimal on purpose.)

## 2. Light & tight (for making new things)

- **Core is PySide6-only.** Heavy or native dependencies (a PDF engine, mpv,
  a cast stack) live behind `[project.optional-dependencies]`, never in the
  core. `python-mpv` loads `libmpv` *at import time* — exactly what must stay
  out of the base. dough core installs in seconds with zero native libs.
- **One identity, parameterized once.** App name / app-id / repo URL come from
  `QApplication.applicationName()` and one config block — not hardcoded across
  twenty packaging, autostart, and D-Bus files.
- **Flat, runnable layout.** A single `dough/` package, `python -m dough`, no
  install needed from a checkout. Fork → rename → run.
- **Batteries, templated.** Packaging (deb / flatpak / winget / AUR), CI,
  release, and a landing-page template ship with `{{placeholders}}` so a new
  app is installable on day one, not month three.

## 3. Looks good across platforms, resolutions, and mediums

- **Three-tier design tokens** — *primitive → semantic → component*. Primitives
  are raw values; semantic tokens name *intent* (`wash_hover`,
  `surface_input`, `text_dim`); components compose them. A re-skin is a token
  edit, never a code hunt. Tokens can export to JSON so the app and the
  landing page share one source of truth.
- **Never raw px — only scalable tokens.** Type tiers (`size_px × FONT_SCALE`),
  a 4-based spacing scale, a radius scale. Resolution independence is one base
  times a scale factor, applied uniformly.
- **HiDPI / fractional scaling, done right.** PassThrough rounding +
  `setPixelSize` + device-pixel snapping (`round(x·dpr)/dpr`) to kill the
  fractional-DPI smear. Lifted from jellytoast — and documented, because the
  snapping math is correct but non-obvious.
- **A theme that survives missing capabilities.** Frosted glass with an honest
  fallback: blur present → ~67% glass; no blur → ~92% near-opaque, so a
  surface never goes broken-see-through. `body_color_for(theme, status)` routes
  to the right alpha. An app that wants a flat opaque look just sets
  `theme.blur = False`.
- **Adaptive, not fixed.** Model/view/delegate for large lists (documented as a
  pattern — the perf wall jellytoast hit), settle-timer + pre-scaled caches for
  smooth resize, OS-following light/dark, accent presets with a WCAG
  `contrast_ink()` so glyphs stay legible over any accent.

---

## What dough refines vs. jellytoast

dough is jellytoast's proven cross-platform/visual engine, minus the music,
plus four deliberate refinements:

1. **`AppBus`** (minimal, generic) instead of a 60-signal `PlayerBus`.
2. **Parameterized identity** (one app-name source) instead of `"jellytoast"`
   hardcoded across autostart / notifications / packaging / D-Bus.
3. **PySide6-only core**, heavy deps optional.
4. **Three-tier tokens** (+ optional JSON export) instead of semantic-only.

## Conventions inherited from jellytoast

- No autoformatter; wrap by editorial judgment, match surrounding code.
- All network/disk I/O goes through `dough.async_io` — never a raw
  `threading.Thread`.
- Qt thread affinity: create/touch a `QTimer`/`QObject` only on its owning
  thread; hop back with `QTimer.singleShot(0, app, fn)` / a queued signal.
- Categorical values are `str`-backed enums, not bare strings.
