# dough — TODO / handoff

Status as of **2026-06-22**. The **baking-phase channel matrix is complete** (PyPI ·
`.deb` · AppImage · AUR · Windows Inno+winget · MSIX · macOS — all wired; dormant ones
light up per account/secret), and this session **set dough's product direction**.
Paused mid-Ingredients on the first app. The full thesis/vocabulary/phases live in the
AI memory (`dough-thesis-vocabulary`); this is the human pick-up list. See also
`docs/BAKING.md` (the release machinery) and `docs/ROADMAP.md`.

## The product direction (settled this session)

- **Headline: "build anywhere, deliver everywhere"** = build on any **host**
  (Linux/Mac/Windows), deliver to every **target** (the channel matrix).
- **The product is *building with dough*** — a person + **GitHub + AI** → their own
  cross-platform app. *Building dough* (improving the base) is enabling work;
  *forking dough itself* is a niche option, not the headline.
- **Vocabulary** (to fold into PHILOSOPHY.md): **building dough** (deliverable = dough,
  label *core*) vs **building with dough** (deliverable = an app, a "loaf", label
  *app*); **host** (runs on) vs **target** (ships to). dough is **self-baking** (built
  with its own oven). `rise`+`bake` are phases *inside* building-with-dough.
- **The maker workflow = phases: Ingredients → Baking → Delivery.**
  - **Ingredients** — the brief: big research + planning (name, features, aesthetic/UI,
    custom icon, reuse-from-dough, delivery targets) → fills the sidecar + a plan doc.
  - **Baking** — the build loop (GitHub + AI + user) on the owned base + `dough bake`.
  - **Delivery** — guided per-target **helpers** that walk the maker from "built" to
    "live" (artifact + account + secret + submission). The machinery exists; the
    guided activation doesn't.

## ▶ Pick up here next trip: dogfood butterPDF through the workflow

Design the "building with dough" experience **by doing it** — run the first app,
**butterPDF**, through Ingredients → Baking → Delivery, and let the real friction write
the tooling + docs. Resume sequence:

1. **Finish butterPDF's Ingredients brief.** butterPDF is an **empty greenfield folder**
   at `/home/august/Projects/butterPDF` (a PDF tool, frosted aesthetic, wolfgang
   warehaus brand: dough→butter→jelly). Needs the user's seed for **what it is /
   features** (a reader? merge/organize? annotator?), then draft the full brief:
   identity (`butterpdf`), features, aesthetic/UI, custom icon (butter motif),
   reuse-vs-net-new (a PDF engine — Qt's `QtPdf`, currently EXCLUDED in the spec, gets
   re-enabled), delivery targets. **Structuring this brief = designing dough's reusable
   Ingredients template.**
2. **Build `dough new <slug>` — the entry verb (full rename / own-it).** Scope approved;
   rename survey done (below). A `dough.scaffold:main` console script (`dough-new`):
   git-mv the package → slug, global identity replace (`dough`→slug,
   `wolfgangwarehaus`→org), rename the tooling table key + the scripts, set identity +
   display, **mint a fresh `inno_appid_guid`**, rename the brand SVG, update the test
   literals, strip the dev scaffolding, replace AGENTS.md, re-bake. **Validate** on a
   throwaway copy of dough → `pytest` + `<slug> bake --check` green (fully testable,
   unlike the channels). Then use it to scaffold butterPDF.
3. **Write `AGENTS.md`** (root, auto-discovered) — the AI front door; headline at top;
   two modes, leading with "you're building WITH dough."
4. **Build the Delivery per-target helpers** — stateful interactive walkthroughs
   (e.g. a Windows helper: GitHub `.exe` → winget account/fork/token + submit →
   Partner Center register + Store apply + MSIX submit). Turn RELEASING.md /
   STORE-SUBMISSION.md from docs into guided activation. Design against butterPDF's
   real channels.
5. **Realign the docs vocabulary** — `dough bake` = RENDER (Baking); the release
   pipeline = **Delivery**. "The baking phase" in BAKING.md is mostly Delivery.

### `dough new` rename surface (survey done)
~330 `dough` refs / ~67 `wolfgangwarehaus`, but identity is centralized (the seam +
the sidecar), so it's a global identity-replace + package rename + GUID mint + re-bake.
Strip: `dev/` (run.sh, shared.toml, sync.py), `docs/SYNC.md`. Touch: entry points
(`[project.gui-scripts] dough`, `[project.scripts] dough-bake`), `version_file =
"dough/_version.py"`, package-data `"dough.assets"`, brand `dough/assets/dough.svg`,
the `[tool.dough.metadata]` table key (+ `bake.py`'s lookup). Decisions locked: full
rename incl. the table key; keep BAKING/PHILOSOPHY as renamed reference, strip the
process docs.

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
- **Baking phase — Beat 3 (the release pipeline)**: `release.yml` — the two-phase
  spine (docs/BAKING.md §6): on a `v*` tag, install → resolve the version from
  setuptools-scm (one source for the wheel + deb + AppImage + metainfo) →
  `dough bake --release-version` (inject the `<release>`, dated to the tagged
  commit) → PyInstaller → build the `.deb` + AppImage + sdist/wheel → SHA256SUMS +
  Sigstore attestations → **draft** GitHub release (curated CHANGELOG notes,
  idempotent create-or-update) → human publishes → `release:[published]` →
  `pypi-publish.yml` DOWNLOADS the release's sdist/wheel (same bytes) and uploads
  via OIDC. `dough bake` gained `--release-version`/`--release-date` (fail-loud
  guards so it can't dirty the committed tree); `vendor_id` projection;
  `docs/CHANGELOG.md` + `docs/RELEASING.md`; a `dough bake --check` CI gate.
  Validated by a 4-dimension adversarial review (22 confirmed; all in-scope fixed:
  version single-sourcing, date single-sourcing, the publish-the-same-bytes chain,
  the empty-date AppStream bug). 89 passed, ruff clean. **PyPI is now end-to-end.**
- **Baking phase — Beat 4 (Linux hardening + the Arch channel)**: cross-distro
  **container smoke** templates (`smoke_test_{deb,appimage}.sh`, mpv-stripped) wired
  into `release.yml` as clean-container jobs — proves the deb/AppImage self-contain
  the Qt-xcb closure (what the in-runner boot can't). **AUR** channel: `PKGBUILD.j2`
  (pure-Python source build; `SETUPTOOLS_SCM_PRETEND_VERSION` since the tag tarball
  has no `.git`) + `aur.yml` (dormant behind `AUR_SSH_PRIVATE_KEY`).
  **`release-checklist.yml`** + template (propagation issue on tag). Validated by a
  4-dimension adversarial review. 89 passed, ruff clean.
- **Baking phase — Beat 5 (the Windows channel)**: the PyInstaller spec is now
  platform-aware (one spec; lean Qt excludes + a Windows icon/`version_info`
  branch); `windows/version_info.txt.j2` (the `VSVersionInfo` jellytoast omits —
  §5's "biggest canonical Windows gap"); `windows/{{app_slug}}.iss.j2` (Inno, the
  AppId brace-escaped, a conditional `SetupIconFile`); a **minted immutable**
  `inno_appid_guid` in the sidecar. `build-windows` job in `release.yml`
  (`windows-latest`: rasterize the `.ico`, render version_info + .iss, freeze,
  iscc → `.exe` + portable `.zip`; Azure Trusted Signing dormant). **winget**:
  `winget.yml` (dormant behind `WINGET_TOKEN`; `winget-releaser` generates the
  manifests from the published `.exe`, so none are checked in). Validated by a
  4-dimension adversarial review. 89 passed, ruff clean. **Authored + reviewed
  but CI-validated only — no Windows to build/test here.**
- **Baking phase — Beat 6 (the last channels: MSIX + macOS)**: **MSIX/Store**
  (manual-first) — `msix/AppxManifest.xml.j2` (full-trust packaged-classic, Identity
  = `windows_aumid`, StartupTask, `runFullTrust`), `make-assets.sh.j2` (the tile
  matrix from the SVG), `STORE-SUBMISSION.md.j2` (the manual cert-review + local
  WACK/test-sign QA runbook). **macOS** (dormant) — the spec's `darwin` BUNDLE
  branch (`.app` + `Info.plist` + `cf_bundle_id`), `entitlements.plist`, the
  Homebrew `cask`, and `macos.yml` (the full sign-every-Mach-O → `create-dmg` →
  `notarytool` → `staple` → cask-bump chain, gated behind the Apple secrets). Minted
  the immutable `inno_appid_guid`; the gate now structurally validates the MSIX XML
  / entitlements plist / cask Ruby. Validated by a 4-dimension adversarial review
  (20 confirmed, all actionable fixed). **Authored + reviewed, CI-validated only —
  no Windows/macOS/Partner-Center here.** 91 passed, ruff clean.

Suite: **91 passed** (+1 skipped: cask `ruby -c`; green across shuffle seeds +
xdist), ruff clean. **All 6 beats are pushed** (`main` even with origin); no git tags
yet — `git tag v0.1.0` cuts the first release.

## Standing technical TODOs (the dough base)

Base maintenance, secondary to the product push above. In rough priority order.

### 1. Cut v0.1.0 (whenever)  ·  ready
The channel matrix is complete: `git tag v0.1.0 && git push origin v0.1.0`.
`release.yml` drafts it (Linux + Windows); you review + publish; PyPI / AUR / winget /
macOS / MSIX light up per their (dormant) secrets. **First-run caveats:** the Windows +
(if activated) macOS jobs run for the FIRST time on that tag — CI-validated only, so
watch them. PyPI's first publish needs the one-time pending-publisher setup
(RELEASING.md). (Doing the first app via `dough new` may reshuffle whether dough itself
even gets a v0.1.0 vs going straight to butterPDF — revisit.)

### 2. `setDesktopFileName` → `identity.desktop_id()`  ·  needs a real desktop
The last functional gap. The `.desktop`'s `StartupWMClass` → `app_id_base` too
(review-confirmed HIGH: the installed `.desktop` is named by the reverse-DNS id, so
the Wayland taskbar icon won't associate until this lands). **Needs KDE Wayland +
X11 smoke-testing** — a guided session, like the JellytoastWindow inversion.

### 3. Remaining channels (low priority)  ·  greenfield / deferred
A hosted **apt/PPA** repo (signed Release/InRelease via reprepro + Pages) and the
**landing page** (`site/` + `pages.yml`). Skip **Flathub** (the Generative-AI ban
disqualifies a `Co-Authored-By: Claude` lineage — docs/BAKING.md §5).

### 4. Wire the shipped-but-dead subsystems into `run_app`  ·  ready (P1 leftover)
`notifications/` and `autostart/` ship but nothing calls them. `notifications/` is
now routed through `dough.identity`; **`autostart/` still holds bare-slug `"dough"`
literals** the review confirmed are fork-blind (`_linux.py` `.desktop` basename /
`Name=`/`Icon=`/`Exec -m dough` — and the source-copy path looks for `dough.desktop`
while an installer ships `io.github.…dough.desktop`, so the copy branch never
matches; `_windows.py` `_VALUE_NAME`/`-m dough`; `_flatpak.py` `commandline
["dough"]`). Route them through `dough.identity` (use `desktop_id()` for the
`.desktop`/icon names, `display_name()` for `Name=`) and wire them opt-in in `run_app`.

### 5. JellytoastWindow full inversion  ·  needs the real desktop + a server
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

### 6. P3 polish sweep  ·  low priority, cosmetic
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
