# dough roadmap — toward stand-alone, then re-injection

Captured from the `dough-agnostic-audit` (2026-06-16, 5-dimension audit +
adversarial critique). **P0 is prepped but deferred — execute next week.**

## Keystone decision: hybrid, leaning library

Ship the proven **leaf tier** as a real `import dough` dependency:
design system (`theme`, `color_tokens`, `design_tokens`), widget kit
(`frosted_dialog`, `selector`, `icon_button`, `custom_tooltip`,
`smooth_scroll`, `ui_helpers`-minus-music), `blur/`, and the platform
scaffolding (`win_frameless`, `keyboard_focus`, `async_io`, `platform_compat`,
`single_instance`, the backends). Keep **`AppWindow` + `AppBus` as thin
*subclassable bases*, NOT a turnkey app framework**. The fork-and-own flow
survives only as the "brand-new app from scratch" on-ramp. The sync door
(`dev/sync.py` + `dev/shared.toml` + the jellytoast nudge) **retires last**,
once the pull is proven module-by-module.

Why hybrid: jellytoast's `JellytoastWindow` (2381 LOC, 5 app-specific mixins)
and `PlayerBus` have never consumed dough's bases — they're reverse-engineered
ideals. Forcing them into a turnkey library is the deepest, riskiest surgery
and buys nothing. The leaf tier is proven; ship that, keep the spine thin.

## dough is NOT stand-alone-safe today (verified against code)

These would crash / mislead a fresh importer — they are the reason P0 exists:

1. **`ui_helpers.py` crashes on call** — `start_seed_radio` (~1754-1804) and
   `open_create_smart_playlist` (~1809-1893) import four modules dough doesn't
   ship (`dough.player_state`, `dough.providers`, `dough.smart_playlists`,
   `dough.smart_playlist_editor`) and read `get_settings().smart_playlists`
   (no such property).
2. **`power/` crashes immediately** — `SleepInhibitor.start()`
   (`power/__init__.py:64-75`) connects to `bus.playback_started/resumed/
   paused/stopped/ended`; `AppBus` (`bus.py:23-33`) defines none of them.
3. **Live re-theming silently broken** — `CoverOverlayButton`
   (`ui_helpers.py:1129`) + `EmptyState` (1278) subscribe to the phantom
   `dough.player_state.PlayerBus` (caught by a try/except, so it just dies
   quiet).
4. **App identity hardcoded in ~14 files**, not the 3 the README claims
   (settings, design_tokens, app, all notification + autostart backends,
   `windows_shortcut` AUMID, `single_instance` prefix, `blur` Wayland app_id).
5. **Zero unit tests** on ~8100 LOC. (Note: `ci.yml` DOES exist — lint +
   offscreen boot smoke; the task is *adding a pytest job*, not creating CI.)

## P0 — the gate (execute next week; nothing public until green)

Order matters: **stand up the test harness FIRST** so the deletions/rewiring
land guarded.

1. **Test foundation.** Create `tests/` + `conftest.py` (a `qapp` fixture);
   add a `pytest` job to the existing `.github/workflows/ci.yml`. Tests:
   - import-smoke: import every public dough module + grep for any
     `from dough.<x>` targeting a nonexistent module (catches the phantoms).
   - a **runtime** test that actually instantiates `SleepInhibitor().start()`
     — the import-smoke does NOT catch the `power/` `AttributeError` (it's a
     runtime `.connect`, not an import).
   - port jellytoast's tests for the **pure-lift (AUTO)** modules first
     (`theme`, `design_tokens`, `color_tokens`, `async_io`, `win_frameless`,
     `blur`, `keyboard_focus`, `smooth_scroll`, `platform_compat`,
     `single_instance`, `settings`) via the `shared.toml` rename transforms;
     **hand-write** tests for the MANUAL/diverged ones (`ui_helpers`,
     `window`) — don't run diverged code through faithful-lift transforms.
2. **Self-consistency.** Delete the two dead music functions; rewire
   `CoverOverlayButton` + `EmptyState` off the phantom bus onto
   `dough.bus.AppBus` and drop the try/except. `grep -rn dough.player_state
   dough/` to catch the whole class.
3. **Resolve `power/`.** Recast `SleepInhibitor` to explicit
   `inhibit()/release()` calls (keep the generic `_windows`/`_linux`
   `SetThreadExecutionState`/ScreenSaver backends — only the bus wiring is
   music-specific), OR move `power/` to jellytoast. A PDF viewer has no
   playback.
4. **Identity seam (minimal).** A `configure(org, app, display_name)` that
   fixes the ONE hard problem: the font-scale loader reads
   `QSettings("dough","dough")` at **import time** (`design_tokens.py:53`),
   before QApplication exists — so identity cannot come from
   `applicationName()`. Route `settings.py:18-19,36`, `design_tokens.py:53`,
   `app.py:30,89-93` through it. **Lazy-read** AUMID / desktop-id / Categories
   / description from the running QApplication (they're read post-construction)
   — do NOT build a 7-field dataclass.

## After P0 (later beats, for context)

- **P1:** `run_app(content_factory, *, identity=…)` entry + curated
  `__init__.py` public API; wire the shipped-but-dead subsystems
  (`single_instance`, `color_tokens.load_persisted_overrides()` BEFORE first
  widget, geometry save/restore) unconditionally; an `AppBus.get()`
  configurable-factory seam (PREREQUISITE for the window/bus prototype).
  **Prototype** `JellytoastWindow` subclassing `dough.AppWindow` on a branch
  BEFORE committing — if it can't be done without untangling the 5 mixins,
  keep window/bus app-owned (partial inversion is fine).
- **P2:** migrate jellytoast module-by-module behind re-export shims
  (`jellytoast.theme` → `from dough.theme import *`), green against its 3000+
  tests. **Bus ordering is the dangerous cross-repo constraint:** register
  `PlayerBus` as the `AppBus` singleton factory BEFORE the first leaf-module
  shim flips, or per-module inversion silently splits the bus (breaks live
  re-theming + ~60 music signals).
- **P3 / polish:** docstring sweep (PlayerBus→AppBus, music examples → neutral),
  `jt*` objectName + `JT_` env renames, split `icons.py` into a chrome core vs
  a `dough.icons.media` extra, correct PHILOSOPHY's false
  "identity from applicationName()" claim.

## Don't build (audit trims — astronaut work for a 1-3 app family)

7-field identity dataclass · `JT_`→`DOUGH_` deprecation-alias layer ·
pre-configure fail-loud tripwire · four new doc files (fold into
PHILOSOPHY/README) · per-feature opt-out flags in `run_app` · cookiecutter /
plugin registry / multi-app-per-process DI.

## Sequencing gotchas

- `sync.py --apply` can't be "gated behind CI" (CI runs post-commit) — run
  `pytest` **locally** after `--apply`, before committing the sync.
- Two "quick wins" (delete dead music fns, rewire off `player_state`) are
  actually P0 gate items — land the smoke test first so they're guarded.
