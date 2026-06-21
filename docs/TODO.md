# dough — TODO / handoff

Status as of **2026-06-21**. dough is stand-alone-safe, tested, and library-shaped;
the jellytoast inversion is validated as feasible. This is the pick-up list for
next time. See `docs/ROADMAP.md` (the P0→P3 plan) and `docs/BAKING.md` (the
release-phase spec) for the why.

## Done this round

- **P0 — stand-alone-safe gate** (merged to `main`): test foundation + pytest CI
  job; deleted the dead music functions; rewired `CoverOverlayButton`/`EmptyState`
  onto `AppBus`; recast `power/` to explicit `inhibit()/release()`; the identity
  seam (`dough/identity.py` + `dough.configure()`), fixing the import-time
  `QSettings` coupling.
- **`docs/BAKING.md`** — the baking-phase spec (one metadata source → every
  manifest → verify; the channel matrix; dynamic versioning; templated `packaging/`).
- **P1 beat 1** — `run_app()` entry, curated lazy public API, `AppBus.set_factory()`.
- **P1 beat 2** — `AppWindow` extension seams (`_make_top_bar`, `set_footer`,
  `_paint_body_backdrop`) + per-test Qt-window isolation (killed a teardown segfault).
- **Inversion go/no-go** — validated GO: bus half proven live (a now-removed
  jellytoast worktree spike), window half proven by `test_jellytoast_shaped_window`.

Suite: **54 passed**, ruff clean. `main` is **9 commits ahead of `origin` (unpushed)**.

## TODO — in rough priority order

### 1. Push `main` to `origin`  ·  ready, quick
9 commits are local-only. Nothing else is blocked on it, but it's the cheapest win.

### 2. Baking phase — kickoff  ·  ready (unblocked by the identity seam)
Start the proven, low-effort tier from `docs/BAKING.md`:
- `[tool.dough.metadata]` sidecar in `pyproject.toml` (the ~9 inputs → ~26-field union).
- Dynamic versioning (`setuptools-scm`, tag-is-the-version) + the generate-then-verify renderer.
- First channels: **PyPI**, **AppImage**, **loose `.deb`** (lift + templatize from jellytoast).
- Defer macOS (present-but-dormant), hosted apt/PPA, Flathub (policy-blocked — skip flathub.org).

### 3. Wire the shipped-but-dead subsystems into `run_app`  ·  ready (P1 leftover)
`notifications/` and `autostart/` ship but nothing calls them, and they still hold
hardcoded `"dough"` identity literals. Route them through `dough.identity` and wire
them (opt-in) in `run_app`.

### 4. JellytoastWindow full inversion  ·  needs the real desktop + a server
The real jellytoast PR. Validated feasible; mechanical but **needs a KDE Wayland
desktop + a Jellyfin/Subsonic server to smoke-test the visual chrome**. Do it as a
guided session on the machine. Steps (also in the AI memory handoff):
- `PlayerBus(dough.bus.AppBus)`; delete its `_instance`/`get()`; dedup the 4 colliding
  signals; `AppBus.set_factory(PlayerBus)` in `main()` after `QApplication()`, before
  the first bus touch.
- `__main__` entry shim: `dough.configure(org='jellytoast', app='jellytoast',
  display_name='Jellytoast')` **before** importing `jellytoast.app` (import-time
  font-scale read). Keep `app='jellytoast'` to preserve the existing QSettings key
  (else saved geometry/theme silently reset).
- `JellytoastWindow(*mixins, dough.window.AppWindow)`; delete the duplicated chrome
  (`__init__` chrome block + the chrome-internals block); override `_make_top_bar`
  (JtTopBar), `set_content` (content_stack), `set_footer` (np_bar),
  `_paint_body_backdrop` (FauxFrost), `closeEvent` (minimize-to-tray).
- Smoke on KDE Wayland: blur, frameless drag/edge-resize, rounded-body squaring when
  maximized, music top bar, page switching, pinned np_bar, theme re-stamp.

### 5. P3 polish sweep  ·  low priority, cosmetic
- Route the remaining `notifications/` + `autostart/` identity literals through `dough.identity`.
- Rename the `[JT.Lnk]` C# namespace in `windows_shortcut.py`.
- `JT_*` env vars + `jt*` objectName renames (currently self-consistent, harmless).
- Docstring sweep: `PlayerBus`→`AppBus`, music examples → neutral.
- Split `icons.py` into a chrome core vs a `dough.icons.media` extra.
- Fix `docs/PHILOSOPHY.md`'s false "identity comes from `applicationName()`" claim
  (it's now `dough.configure()` / `dough.identity`).
