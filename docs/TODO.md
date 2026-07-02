# dough — TODO / handoff

Status as of **2026-06-22**. The **baking-phase channel matrix is complete**, the product
direction is settled (below), **`dough new` is built**, and the first app **butterPDF** is
**scaffolded, has a working PDF viewer (MVP #1), and drove a deep first-looks polish that's
now BACKPORTED into dough** (see `docs/DESIGN.md` + `docs/BACKPORT.md`). The full
thesis/vocabulary/status live in the AI memory (`dough-thesis-vocabulary`); this is the
human pick-up list. See also `docs/BAKING.md`, `docs/DESIGN.md`, `docs/MACOS.md`, `docs/WIND-DOWN.md`.

**Since then (2026-07-01):** absorbed jellytoast's macOS work + refinements into the base
(commit `9314681`, merged + pushed to `main`) — see the shipped entry below. The sync door
moved: `dev/shared.toml` `synced_from` is now `7357dad` and most shared modules are `manual`.

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

## ▶ Wind-down 2026-07-02 — MILESTONES A + B DONE; next = C (ship)

**Big session.** The interleaved, butterPDF-led arc drove dough + butterPDF a long way.
State now (all committed + pushed; dough `main` @ `945a434`, butterPDF `main` @ `92cf97b`):

- **Milestone A (reconnect the fork) ✅** — A1 chrome-machinery (`dough/drag_repaint/` +
  `dough/noborder/`, identity-templated so `dough new` needs no re-namespacing), A2 the
  **dough→loaf sync tool** (`dev/sync_loaf.py`, `docs/SYNC.md`), A3 butterPDF is a **public
  repo** (github.com/wolfgangwarehaus/butterPDF, CI green), A4 butterPDF **fully synced**
  onto dough's current base. All visual-smoked on real KDE Wayland.
- **Milestone B (butterPDF MVP) ✅ — v1 feature-complete.** B1 AcroForm fill (own rendered
  view + 6 document backgrounds + image-preserving smart dark mode + non-modal live
  settings), B2 correct save/flatten (regenerated appearance streams — verified in Adobe/
  browser), B3 Quick-sign (draw/type/import → place → composite as image XObject w/ SMask),
  B4 converters (PDF⇄PNG/JPEG), B5 safe-open + XFA-decline. 131 tests green. butterPDF deps
  now: PySide6 + numpy + pypdf + pikepdf + img2pdf (installed on this machine via
  `--break-system-packages`).

**Next = Milestone C (ship):** C1 Delivery per-target helpers (Linux-first) → C2 cut dough
`v0.1.0` → C3 butterPDF's first real release. Plus the standing dough TODOs below.

**NEW product directions this session (capture, then design into C):**
- **The IMPROVEMENTS phase** (user insight) — the workflow is a LOOP, not linear:
  Ingredients (once) → **Baking ⇄ Delivery (forever)**; every lap after launch is an
  Improvement (refine → re-bake → re-deliver updates). C1's helpers must be UPDATE-aware
  (version bump, changelog, RE-release, store re-review), and the dough→loaf sync (A2) is
  Improvements-phase infrastructure. See [[dough-thesis-vocabulary]].
- **Session open/close SYSTEMS** (user insight) — dough should ship tried-and-true session
  lifecycle: an **opening** (AGENTS.md front door + read the handoff TODO + memory/resume
  pointer → orient with zero ramp-up) and a **closing** (the `docs/WIND-DOWN.md` checklist).
  Closing exists as a policy doc; the opening isn't formalized (AGENTS.md unwritten). Make
  both first-class, part of "building with dough" — possibly a `dough session` helper.

## The settled goal + game plan (2026-07-02) — for reference

> **dough exists to make *building WITH dough* real.** Success for this arc = **butterPDF
> v1 ships to real users through dough's Delivery matrix**, and every dough gap butterPDF
> hits gets fixed *in the base* — including a **reusable dough→loaf sync** so the app
> family can pull base improvements without re-forking.

Two settled decisions: the arc is **interleaved and butterPDF-led** (drive dough purely by
finishing butterPDF; fix each dough gap as it surfaces), and we **build the dough→loaf sync
tool now** (butterPDF diverged Jun-22, pre-macOS; divergence gets managed, not permanent).

The live task list is in the session tracker (13 tasks, A/B/C milestones). butterPDF's
side is `../butterPDF/docs/TODO.md`. Milestones:

**A — reconnect the fork, close the chrome gap** *(dough-heavy, unblocks everything)*
1. **A1 · chrome-machinery backport UP** (butterPDF→dough — `docs/BACKPORT.md` ranks 9–10):
   port **`drag_repaint`** (the NVIDIA drag-trails KWin effect, proven in butterPDF) + a
   **generic wmclass `keep_above`** noborder package into dough; wire in `run_app`
   (drag_repaint AFTER `show`, keep_above BEFORE `show`); pair with cross-cutting §2
   (`setDesktopFileName → desktop_id()`). **`dough new` must re-namespace both KWin assets
   on fork** (effect id `dough_dragrepaint` + the keep_above wmclass — the whole-word
   `\bdough\b` replace does NOT catch `dough_dragrepaint`). Smoke on real KDE Wayland.
2. **A2 · the dough→loaf sync tool** — generalize `dev/sync.py` + `dev/shared.toml` into a
   per-fork updater that pushes base improvements DOWN into an existing loaf (AUTO/MANUAL
   split mirroring the jellytoast→dough up-door; records a sync point). The structural
   answer to "how do improvements reach existing forks?"
3. **A3/A4 · butterPDF** — give it a git remote (`gh repo create` + push), then pull
   dough's post-fork gains via A2 (validates the tool on a real fork).

**B — butterPDF MVP engine** (the net-new wedge; see `../butterPDF/docs/TODO.md`):
AcroForm fill → correct save/flatten (the make-or-break Adobe+print round-trip) →
Quick-sign → converters → safe-open + XFA-decline. Deps: `pypdf`/`pikepdf`/`img2pdf`.

**C — ship it (dogfood Delivery)**
- **C1 · Delivery per-target helpers** (Linux-first) — stateful walkthroughs (artifact →
  account → secret → submit), designed against butterPDF's real channels.
- **C2 · cut dough `v0.1.0`** (see §1 below) so butterPDF depends on a tagged base.
- **C3 · butterPDF's first real release** through the matrix — the end-to-end Delivery proof.

**Cross-cutting (close as they surface):**
- **Write `AGENTS.md`** (root, auto-discovered) — the AI front door; lead with "you're
  building WITH dough"; record the `opaque_menu`-not-raw-`QMenu` convention.
- **`setDesktopFileName → desktop_id()`** + `StartupWMClass → app_id_base` (needs KDE
  Wayland+X11 smoke — pairs with A1).
- **Wire autostart/notifications** opt-in into `run_app` (§4 below) + Settings toggle.
- **Realign the docs vocabulary** — `dough bake` = RENDER (Baking); the release pipeline =
  **Delivery**. "The baking phase" in BAKING.md is mostly Delivery.

## Shipped 2026-07-01 — jellytoast → dough macOS absorption

Piped 72 commits of jellytoast drift UP into the base (sync `de045ad`→`7357dad`), genericized
and hand-reconciled so nothing regressed the identity seam / first-looks polish / load-bearing
frameless decision. Merged + pushed to `main` (commit `9314681`, 54 files).
- **New macOS primitives** (pyobjc lazy+guarded → no-op off-mac): real `blur/_macos.py`
  NSVisualEffectView vibrancy (replaced the stub) + Reduce-Transparency observer;
  `blur/_faux_frost.py` painted fallback; `macos_window.py` + `macos_menubar.py` (native menu,
  music-stripped, Settings→`AppBus.show_settings`); `notifications/_macos.py`;
  `autostart/_macos.py` + `_msix.py`; `platform_compat` `is_msix_packaged`/`is_macos_sandboxed`/
  `is_linux_wayland`.
- **Refinements:** square-corners `rad()` + live font-family picker; `window.py`
  `_resolve_chrome_mode()` refactor + additive GNOME/wlroots frameless (KDE stays decorated);
  `theme.py` mac glass-alpha arms; selector scrollable dropdown + `dough_native_scroll`.
- **Packaging:** `macos.yml` honest-floor pin + offscreen smoke + API-key notarization +
  build provenance + universal2; single darwin `macos` pyobjc extra (base stays PySide6-only);
  dormant mpv-free MAS signing templates. `docs/MACOS.md` captures the hardware-earned gotchas.
- **Decisions:** Flatpak RETIRED (`_flatpak.py` deleted); `media_controls` EXCLUDED
  (music/PlayerBus-coupled); `cf_bundle_id()` the macOS bundle-id convention; all `JT_*`→`DOUGH_*`.
- Verified: 102 passed, ruff clean, `dough bake --check` clean, sync in-sync, a 6-dimension
  adversarial review = 0 confirmed findings. New mac code is **CI-validated only** (no Mac here).

## Shipped this session (the butterPDF run, 2026-06-22)

- **`dough new <slug>`** (commit `8d9610e`) — the entry verb: strip dev scaffolding →
  git-mv the package + brand SVG → whole-word identity replace → fix display/GUID/summary →
  clear + re-bake packaging → validate green. Tested on git + non-git paths, org-swap incl.
- **butterPDF born + baked** (its own repo, `da6e306..666e3c6`): scaffolded via `dough new`;
  **MVP #1 = the PDF viewer** (QtPdf/PDFium — open/render/zoom/page-nav); a long first-looks
  polish loop (frameless single chrome, frosted gutters, even pill-bezels, slim live-accent
  auto-hiding scrollbars, frosted fit-to-content dialogs, `opaque_menu` dropdown, one-Fit
  footer); and the **NVIDIA drag-trails bug fixed** by porting jellytoast's `drag_repaint`
  KWin effect (a real dough gap — never lifted).
- **dough first-looks backport** (commits `2719dd8` + `a892cb5`) — folded the design defaults
  into dough: resize-filter slider-yield, the AutoFadeScrollBar slim-accent pill, `CenteredBar`,
  `frost_scroll_surface`, `settings.auto_hide_scrollbars`, FrostedDialog frameless-gate +
  fit-to-content, `TopBar(CenteredBar)`; plus **`docs/DESIGN.md`** (the 7 first-looks
  principles) + **`docs/BACKPORT.md`** (the full analysis + what's deferred).

## Done earlier (the baking phase + P0/P1)

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
`notifications/` and `autostart/` ship but nothing calls them. **Identity routing DONE**
(2026-07-01 macOS pass): both now route through `dough.identity` — `autostart/_linux.py`'s
`.desktop` basename/`Name=`/`Icon=`/`Exec` use `desktop_id()`/`display_name()`/`app()` (fixing
the copy-branch mismatch), `_windows.py` `_VALUE_NAME`/launch command use `app()`, the music
`Comment`/`Categories` are stripped, `_flatpak.py` is retired, and the new `_macos.py`/`_msix.py`
route through `cf_bundle_id()`/`app()`. **What remains: wire them opt-in in `run_app`** (they're
still never called) — plus expose the `autostart` toggle in Settings and drive `notifications`
from real app events.

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
  - ~~`dough/windows_shortcut.py` — `dough.exe` / `dough.ico` / `dough.lnk` paths~~ **DONE
    2026-07-01** (routed through `identity.app()`; AUMID + Description were already routed).
  - `dough/power/_linux.py:56` — `Inhibit("dough", "Playing music")`: a music-domain
    leftover in a generic base. Use `identity.app()` + a neutral reason. **(still open)**
  - (`autostart/` identity is now DONE — see §4.)
- Rename the `[JT.Lnk]` C# namespace in `windows_shortcut.py`.
- ~~`JT_*` env vars~~ **DONE 2026-07-01** (all renamed to `DOUGH_*`; the `JT_WIN_GLASS_ALPHA`
  leak fixed). `jt*` objectName renames (`jtSelector`, `doughWindow` etc.) still open — cosmetic.
- Docstring sweep: `PlayerBus`→`AppBus`, music examples → neutral.
- Split `icons.py` into a chrome core vs a `dough.icons.media` extra.
- Fix `docs/PHILOSOPHY.md`'s false "identity comes from `applicationName()`" claim
  (it's now `dough.configure()` / `dough.identity`).
