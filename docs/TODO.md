# dough — TODO / handoff

Status as of **2026-06-22**. dough is stand-alone-safe, tested, and library-shaped;
the jellytoast inversion is validated as feasible; the **baking phase is underway**
(the metadata core + the `dough bake` renderer + the first Linux channels landed).
This is the pick-up list for next time. See `docs/ROADMAP.md` (the P0→P3 plan) and
`docs/BAKING.md` (the release-phase spec) for the why.

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
- **Baking phase — Beat 1 (the metadata core)**: the `[tool.dough.metadata]`
  sidecar (one source: ~9 inputs + the descriptive/store union, schema-versioned);
  the projection engine on `dough/identity.py` (pure `aumid_for`/`app_id_base_for`/
  `cf_bundle_id_for` helpers + runtime `app_id_base`/`cf_bundle_id`/`desktop_id`/
  `owner`); `dough/metadata.py` (build-time sidecar reader — `load`/`projections`/
  `context`); **dynamic versioning** via `setuptools-scm` (the tag is the version;
  generated `dough/_version.py` + a source-checkout fallback in `__init__`); and
  the **verify gate** (`tests/test_metadata.py`: projections == seam, `[project]`↔
  sidecar no-drift incl. the Trove license classifier, and a case-insensitive
  fragment scan forbidding re-literalised composite ids). Killed the
  `notifications/_windows.py` AUMID literal (now `identity.windows_aumid()`).
  Validated by a 4-dimension adversarial review (21 findings, all confirmed ones
  fixed). Wheel build proven end-to-end.
- **Baking phase — Beat 2 (the `dough bake` renderer + first Linux channels)**:
  `dough/bake.py` — renders `packaging/templates/**/*.j2` (filenames + bodies)
  from `metadata.context()`, `--check` is the generate-then-verify gate (catches
  content drift, missing, **orphan**, and lost-exec-bit). Templates: freedesktop
  (`.desktop` + AppStream metainfo — both pass `appstreamcli`/`desktop-file-validate`),
  loose `.deb` (`build_deb.sh`, PySide6-core Qt-xcb Depends closure, DEP-5
  copyright conditional on the SPDX), AppImage (`build_appimage.sh`, vendors the Qt
  xcb closure, rasterizes a PNG `.DirIcon`), PyInstaller onedir spec + launcher.
  **PyPI**: `pypi-publish.yml` (OIDC Trusted Publishing) + a CI `build` gate
  (`python -m build` + `twine check`). `bake`/`jinja2` is a build-time-only extra.
  Validated by a 4-dimension adversarial review (26 confirmed; all in-scope fixed:
  orphan detection, posix/LF cross-platform writes, exec-bit checks, vendor-prefix
  `<developer id>`, validity assertions in the gate). 86 passed, ruff clean.

Suite: **86 passed** (green across shuffle seeds + xdist), ruff clean. Beat 1 is
**pushed**; Beat 2 is committed locally (**unpushed**).

## TODO — in rough priority order

### 1. Push Beat 2 to `origin`  ·  ready, quick
The renderer + templates + PyPI workflow commits are local-only. Cheapest win.

### 2. Baking phase — Beat 3 (release.yml + the remaining channels)  ·  ready
The first channels' build scripts exist but **have no CI caller yet** (an honest
gap — they can't run on a tag until `release.yml` lands). From `docs/BAKING.md`
§6 (the two-phase pipeline) + §8:
- **`release.yml`** — the orchestration spine (lift jellytoast's 366-line one):
  on a `v*` tag, `dough bake` (inject `release_version`/`release_date`) → PyInstaller
  → build the `.deb` + AppImage (pin `ubuntu-22.04` for the glibc floor) →
  SHA256SUMS → **draft** GitHub release → human publishes → `release:[published]`
  fans out to PyPI (already wired) and `release:[released]` to the download-based
  channels. The first `git tag v0.1.0` makes `__version__` concrete.
- **`setDesktopFileName` → `identity.desktop_id()`** + the `.desktop`'s
  `StartupWMClass` → `app_id_base` (review-confirmed HIGH: the installed `.desktop`
  is named by the reverse-DNS id, so the Wayland taskbar icon won't associate until
  this lands). **Needs KDE Wayland + X11 smoke-testing** — a guided session.
- Remaining channels: **winget**, **AUR**, **MSIX/Store**, **Windows Inno** — lift
  + templatize from jellytoast (`.github/workflows/{winget,aur}.yml`,
  `packaging/{windows,msix}/`). Defer macOS (`macos_team_id` placeholder ready),
  hosted apt/PPA, Flathub (policy-blocked — skip flathub.org).
- When the channel manifests/`*.j2` land, extend the `test_metadata.py` composite-id
  gate to scan them too (it's `dough/**/*.py`-scoped today).

### 3. Wire the shipped-but-dead subsystems into `run_app`  ·  ready (P1 leftover)
`notifications/` and `autostart/` ship but nothing calls them. `notifications/` is
now routed through `dough.identity`; **`autostart/` still holds bare-slug `"dough"`
literals** the review confirmed are fork-blind (`_linux.py` `.desktop` basename /
`Name=`/`Icon=`/`Exec -m dough` — and the source-copy path looks for `dough.desktop`
while an installer ships `io.github.…dough.desktop`, so the copy branch never
matches; `_windows.py` `_VALUE_NAME`/`-m dough`; `_flatpak.py` `commandline
["dough"]`). Route them through `dough.identity` (use `desktop_id()` for the
`.desktop`/icon names, `display_name()` for `Name=`) and wire them opt-in in `run_app`.

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
- Route the remaining bare-slug identity literals through `dough.identity` (review-confirmed):
  - `dough/windows_shortcut.py` — `dough.exe` / `%LOCALAPPDATA%/dough/dough.ico` /
    `dough.lnk` (the AUMID + Description are already routed; these paths aren't).
  - `dough/power/_linux.py:56` — `Inhibit("dough", "Playing music")`: a music-domain
    leftover in a generic base. Use `identity.app()` + a neutral reason.
  - (`autostart/` is tracked above in §3.)
- Rename the `[JT.Lnk]` C# namespace in `windows_shortcut.py`.
- `JT_*` env vars + `jt*` objectName renames (currently self-consistent, harmless).
- Docstring sweep: `PlayerBus`→`AppBus`, music examples → neutral.
- Split `icons.py` into a chrome core vs a `dough.icons.media` extra.
- Fix `docs/PHILOSOPHY.md`'s false "identity comes from `applicationName()`" claim
  (it's now `dough.configure()` / `dough.identity`).
