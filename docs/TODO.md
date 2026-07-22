# dough — TODO / handoff

Status as of **2026-07-03**. The **baking-phase channel matrix is complete**, the product
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

## ▶ Wind-down 2026-07-21 — the audit, the moat, and the breadboard grows magical

**The strategy day.** A competitive audit (docs/… + artifact) found the delivery
pipeline is table-stakes-plus (copyable) and dough's moat is the COMBINATION —
with the design system and **the breadboard** the hardest-to-clone parts. We
committed to making the breadboard the moat and started building it.

- **The thesis (docs/BREADBOARD.md):** the breadboard is a TRUST INSTRUMENT —
  every green is DETECTED from the real machine/internet, never a typed
  checkbox (extending deliver.py's "state is detected, never recorded" to the
  whole board), and the maker WATCHES it happen. Pitch sharpened to "AI + one
  person → a native desktop app in the stores by Friday" (fast lane). Full
  8-item build ladder in that doc + the AI memory [[breadboard-moat-direction]].
- **Built + shipped (both repos, 3-OS CI green):**
  - Item 1 — stable item ids + omit-empty serializer (schema 1→2). Ids survive
    reorders; empty fields write no line (keeps the TOML hand-editable).
  - Item 2 — the LIVE card: deliver.py Channels gained store_url + install_cmd;
    a fully-✓ channel collapses into a green card with the real URL + a copyable
    install command.
  - Item 3 — launch mode: when a v* tag isn't all-LIVE, the Delivery tab
    auto-arms a backing-off QTimer that re-runs _ChannelProbe; channels flip on
    their own, each stamped with its real go-live wall-clock; settle-latch +
    Watch toggle; home-only; probe cleanup on quit. The MVP-of-magic.
- **Fixed a pre-existing macOS CI red** (not from this work — red since bf4bfc2,
  the test-bridge landing): `test_bridge._widget_node` filtered children by
  `hasattr(isVisible)` to mean "widgets only", but QAction has isVisible() too →
  the walk crashed on `.accessibleName()`. macOS carries QActions in the tree
  where Linux doesn't, so it only reddened the mac leg (green locally). Now
  `isinstance(QWidget)` + a regression test. Also re-baked a stale settings
  baseline in both repos (the dialog gained follow-accent/updates/diagnostics
  rows in a prior foundation commit; render verified stable + complete).

**Resume sequence:**
1. **Breadboard item 4 — Ship it + the [[requests]] queue** (promote the
   agent_request scalar to an ordered queue; the project-bar gets one-click
   "Ship v0.1.0" / "Advance Delivery" templates). Then items 5–8 (ledger +
   green-flip receipt, the "since you left" ribbon, proof marks, the Bake gate).
2. **The still-open ship path** (unchanged, now demoable via launch mode):
   August's last feel verdicts → S1/S2 (HIGH) in butterPDF → roll a [0.1.0]
   CHANGELOG → `git tag v0.1.0` → C3. Tagging v0.1.0 is now also the first real
   test of launch mode against a live release.

## ★ NEW product direction 2026-07-08 (user): THE BREADBOARD — a live maker surface (named by August: a breadboard is where you prototype)

**The insight:** dough needs something the maker INTERACTS WITH during each step
of the process — not just docs the AI reads. An **active checklist window** that
pops up alongside the work: the main goals, the per-phase checklists, the current
session's items — **filled and updated by the AI agent**, **adjustable by the
maker** (checking/unchecking/rewording items steers the product), and
**re-ingestable**: the agent reads the maker's edits and notes back from the
board and changes course. The board is the interaction surface for the whole
Ingredients → Baking ⇄ Delivery loop.

**Design sketch (settle at build time):**
- **State is a file, the window is a view.** A structured, git-tracked file in
  the loaf (e.g. `dough-board.toml`: goals, phases, items w/ checked/by/date,
  a freeform notes block per item). Human-editable, AI-writable — the same
  two-way-door philosophy as the sync manifest. The window file-watches and
  live-reloads; edits in the window write back. No daemon, no IPC — the FILE is
  the API between maker, window, and agent.
- **`dough board` verb** (ships in the package like rig/deliver → every loaf
  has it): opens a frosted AppWindow — goals up top, phase sections
  (Ingredients / Baking / Delivery / Improvements) with checkable items, a
  notes pane per item. Checking an item stamps who/when; a "note to the agent"
  field is the maker's steering wheel.
- **Agent protocol** (goes in AGENTS.md): read the board at session OPEN
  (with the TODO handoff); before acting on a phase, reconcile its checklist;
  at wind-down, update item states + add next-session items. Maker notes are
  DIRECTIVES — reingest them before continuing. This formalizes the
  session-open/close SYSTEMS item (2026-07-02) into something visible.
- **Relationship to existing pieces:** deliver.py's detected channel board
  stays the Delivery section's ground truth (the board can embed/launch it);
  docs/TODO.md stays the deep handoff log; the BOARD is the active surface.
- **MVP cut:** board file schema + `dough board` window (view/check/note) +
  AGENTS.md protocol + `dough new` seeds a fresh board from the Ingredients
  template. Detection-backed auto-checking (tests green? tag exists?) comes
  later — hand-checked first, wired to rig/deliver probes as they prove out.

## ▶ Wind-down 2026-07-08 — the walkthrough day: blur, breadboard, and the app grows

**All green + pushed, 3-OS CI verified** (dough 225 passed, butterPDF 192; both
`main` even with origin). August's guided walkthrough drove the whole day —
every item below started as his eyes or his direction:

- **The venv blur bug** (his catch: "is this fallback blur? it has the grain"):
  pip PySide6's bundled Qt can't see the distro's KWindowSystem platform plugin
  → blur read UNSUPPORTED on a blur-capable KWin → grainy faux-frost. Fixed
  with a targeted shim library path (blur/_kwin.py `_ensure_platform_plugin`,
  live-proven UNSUPPORTED→ACTIVE in both apps). Faux-frost grain also halved
  on his verdict.
- **THE BREADBOARD shipped and grew up in one day** (his direction + naming):
  `dough breadboard` / `<slug>-breadboard` — the live maker surface. State is
  `<slug>-breadboard.toml` (git-tracked; the FILE is the API between maker,
  window, and agent; deterministic emit; live file-watch reload). v2: tabs
  across the top; Ingredients = app summary page (sidecar logo/name/summary,
  Brand assets…, editable `purpose`, feature cards); Baking = a kanban
  (Now/Next/Later/Done, per-item `priority`); Delivery = deliver.py's REAL
  channel detections with linkified guides (probed off-thread, home-only);
  plus the PROJECT BAR: a switcher across sibling checkouts' boards and
  "Wind down…" → `agent_request` (the AGENTS.md protocol: fulfil + clear).
  AGENTS.md session-open step 2 in both repos + the loaf template.
- **CircleSwatch** (his catch: dots along circle paths): QSS circles stroke
  four arcs, quadrant seams leave AA dots — painted fill+ring widget in
  ui_helpers, converted dough settings + butterPDF settings/ink swatches;
  settings goldens re-baked (eyeballed) in both repos.
- **butterPDF walkthrough features** (his asks): frosted field context menus
  (the default black QLineEdit popup was the one un-themed surface) with
  "Insert today's date" + "Sign document here…"; a bare-page context menu;
  IN-PLACE text boxes (type on the page, click to re-edit, drag to move,
  empty self-removes — makes NON-interactive PDFs fillable); the walkthrough's
  R5 cross-viewer check PASSED (flatten verified in Okular/Firefox).

**Resume sequence:**
1. **August's remaining feel verdicts** (the last pre-tag human item):
   drag/zoom/scroll, dark document backgrounds, and the wide-placed-signature
   resolution judgment (place one ~half page width, zoom the save; if soft →
   supersample the ink canvas 2-3×). Plus the notification + autostart eyeball.
2. **S1 + S2 engine fixes** in butterPDF (HIGH; session chips exist —
   hierarchical-field save data loss, rotated-page coordinates).
3. **Roll a `[0.1.0]` CHANGELOG section → `git tag v0.1.0`** (first
   Windows/macOS release runs — watch them) → PyPI pending-publisher setup
   (`dough-base`) → **C3** via `butterpdf-deliver`.
4. Breadboard fast-follows when wanted: drag-and-drop kanban cards,
   detection-backed auto-checking, an editable goal field.

## ▶ Wind-down 2026-07-07 — new-machine setup + the autonomous audit day

**Fresh Linux install (CachyOS) fully stood up and both repos audited hard; all
green + pushed + 3-OS CI verified** (dough `main` @ `c3438c1`, butterPDF @ `c5f2575`;
local `.venv` in each, Python 3.14 / PySide6 6.11; dough 204 passed, butterPDF 180).
A 3-agent autonomous pass (release dry-run, code review, PDF-engine stress test)
found and FIXED 9 dough bugs pre-tag: the AUR pretend-version was slug-keyed
(gitless builds silently shipped 0.0.0 → `dist_name` in the bake context,
`…_FOR_DOUGH_BASE`), frozen builds omitted the drag_repaint effect payload,
deliver.py probed git in the CWD not the checkout + read unauthed gh as
"not drafted" (now `?`), rig baseline's goldens were CWD-relative + grabs
inherited stray `QT_*` (both could poison/split goldens), `dough new` corrupted
`org_slug` when a fork separates org from owner (the degenerate-identity repair,
mirrored in sync_loaf), and sync_loaf trusted a garbage `synced_from` (false
"no upstream changes ✓") + `--apply` could clobber uncommitted loaf edits.
butterPDF: `cryptography` declared (AES owner-password PDFs used to silently
lose the form), and the stress test's S1/S2/S3 engine findings are recorded in
`../butterPDF/docs/TODO.md` (S1 hierarchical-field save DATA LOSS + S2
rotated-page misplacement are HIGH — fix before or right after C3).
Walkthrough artifacts regenerated on this machine: `/tmp/butterpdf_sample_form.pdf`,
`/tmp/walk_filled_v2.pdf`, `/tmp/walk_flattened_v2.pdf` (flatten verified
programmatically: 0 fields left, baked ✕ from the R1 repair renders in QtPdf).

**Resume sequence:**
1. **Loaf sync** — butterPDF has pending AUTO drift from the rig/deliver fixes:
   `python dev/sync_loaf.py --loaf ../butterPDF --apply` → test → commit → `--record`.
2. **August's in-person tail** (10 min): open `/tmp/walk_flattened_v2.pdf` in
   Okular/Firefox (name baked, ✕ visible, nothing editable) + drag/zoom/scroll/ink
   feel verdicts in the live app + eyeball dough's Settings autostart toggle and a
   real notification.
3. **S1 + S2 engine fixes** in butterPDF (session chips exist), then **tag dough
   `v0.1.0`** (changelog: roll an `[0.1.0]` section first or accept generated
   notes) → **C3** via `butterpdf-deliver`.

## ▶ Wind-down 2026-07-03 — the audit + autonomous batch + C1 + rigging + walkthrough day

**Everything green + pushed; both repos on the 3-OS CI matrix.** dough highlights: the CI
truth-check fixes (below), AGENTS.md (+ the `dough new` loaf template), the P3 sweep + X2,
run_app autostart/notifications wiring, `setDesktopFileName(desktop_id())` (live-probed),
`rig.py` (boot/probe/shot — the RIGGING direction seeded), `deliver.py` (C1 v1 + the
NAME-CONFLICT finding: PyPI `dough` is TAKEN), PR #1 merged. butterPDF: the whole
walkthrough refinement set landed live (smooth ink, baked ✕, grey-on-dark fills, CLI
front, editable install). **LATE ADDITIONS (same day): R5 fixed
(pypdf flatten left widgets editable → true pikepdf flatten, cross-viewer-proven),
`rig baseline` built (goldens in both repos), and the C2 NAMING DECIDED — dough
publishes as `dough-base` on PyPI (import/scripts/AUR keep `dough`; `dough new`
pins forks to their slug; deliver.py is dist-aware). Resume: (1) the walkthrough's
FEEL verdicts (5 min in the app — the checklist is in the session notes/#6), (2)
pick the tag order and `git tag v0.1.0` (the last C2 act), (3) C3 via
`butterpdf-deliver`, (4) rigging build-out (chrome invariants, GNOME legs).**

## ▶ Audit 2026-07-03 — CI truth-check + workflow fixes

A full-state audit found the repos healthy locally but **CI quietly red in two ways**
(both fixed this session, in dough AND butterPDF):

- **`macos.yml` was rejected by GitHub at parse time** on EVERY push since Beat 6 —
  a 0-second "workflow file issue" failure. Cause: `secrets.HOMEBREW_TAP_TOKEN` inside
  a step-level `if:` (the `secrets` context isn't valid in `if:` expressions). Fixed
  with the same job-level env gate the file already used for `HAVE_APPLE` (`HAVE_TAP`).
- **butterPDF's `lint-and-smoke` job was red since B1**: it installed a hardcoded
  `ruff PySide6` while the boot smoke imports the real app (numpy/pypdf/…). Fixed by
  installing the project itself (`pip install ruff -e .` + `fetch-depth: 0` for
  setuptools-scm) — in butterPDF AND in dough's ci.yml (the template `dough new`
  forks), so future loaves stay green when they add deps.

Lesson recorded: **"CI green" claims must name the workflow** — the `CI` workflow was
green while `macos.yml` failed on the same pushes. Local health at audit time: dough
160 passed + ruff clean + `bake --check` clean; butterPDF 131 passed + ruff clean;
both `main` even with origin. Workflows are NOT covered by the dough→loaf sync
manifest (it only maps package files) — workflow fixes go to each repo by hand.

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

**Next = Milestone C (ship):** ~~C1 Delivery per-target helpers~~ **C1 v1 BUILT 2026-07-03**
(`dough/deliver.py` — the board / per-channel walkthroughs / the update lap; state DETECTED
from git+gh+endpoints; docs/DELIVERY.md updated) → C2 cut dough `v0.1.0` → C3 butterPDF's
first real release. **⚠ C2 DECISION (found by the first board run): the PyPI name `dough`
is TAKEN** (a 2015-era third-party package, v0.6.0) — dough itself can't publish to PyPI
under its own name. Options: a different `[project].name` (e.g. `dough-base`; the import
package keeps `dough`), or skip PyPI for the base (apps are the product — `butterpdf` IS
free on PyPI, and AUR is clear for both). Decide at C2.

**NEW product direction 2026-07-03 (user): RIGGING & TESTING is part of the pipeline.**
dough should always be able to *rig up and test* — visual bumps, code bumps, every
platform. **Seeded today: `dough/rig.py`** (ships in the package → syncs to loaves):
`rig boot` (offscreen boot smoke — now THE ci.yml smoke, one source), `rig probe`
(live-KDE ground truth: Wayland app_id == desktop_id, noBorder, X11 WM_CLASS +
`_KDE_NET_WM_DESKTOP_FILE` — the probe that caught the StartupWMClass review error),
`rig shot` (screenshot the live window → a maker or an AI can SEE the app; proven —
the shot verified the single-chrome noborder look). All dogfooded green on the real
desktop. **Roadmap:** cross-OS CI test matrix (branch `ci-cross-os`, CI-validating);
visual BASELINES (`rig shot` + stored goldens + diff — the visual-bump gate); more
chrome invariants (blur active, drag/edge-resize, maximize squaring); GNOME/wlroots
probe legs; wire `rig probe`/`shot` into the wind-down + walkthrough rituals.
**PR #1 (ci-cross-os) MERGED 2026-07-03** — the ubuntu+windows+macos matrix is live in
BOTH repos (butterPDF's first 3-OS run: green), with what the first Windows run caught:
`.gitattributes` `* text=auto eol=lf` (runner autocrlf broke the byte-exact bake gate),
POSIX-gated exec bits in `bake.py`, and three platform-naive test fixes.

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
- ~~**Realign the docs vocabulary**~~ **DONE 2026-07-03** — BAKING.md now carries a
  terminology note: `dough bake` = RENDER (run during Baking); "the baking phase" in that
  doc = the **Delivery** machinery.

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

### 2. `setDesktopFileName` → `identity.desktop_id()`  ·  DONE 2026-07-03 (code + live probe)
`run_app` now sets `setDesktopFileName(desktop_id())`. **Probed live on the real KDE
session** (KWin-script `resourceClass` + `xprop`): Wayland app_id = the reverse-DNS id ✓;
the noborder rule still matches (substring design — `noBorder=true` under the new app_id) ✓;
X11 exports `_KDE_NET_WM_DESKTOP_FILE` = the id (KDE's association path) while `WM_CLASS`
stays the bare slug — so the review's "`StartupWMClass` → `app_id_base`" claim was WRONG:
`StartupWMClass` must keep `{{ app_slug }}` to match `WM_CLASS` on non-KDE X11 (rationale
now in the template). **Remaining (eyes, in-person):** install a built `.deb`/AppImage and
confirm the taskbar icon + grouping actually associate on KDE Wayland; a GNOME X11 check
if available.

### 3. Remaining channels (low priority)  ·  greenfield / deferred
A hosted **apt/PPA** repo (signed Release/InRelease via reprepro + Pages) and the
**landing page** (`site/` + `pages.yml`). Skip **Flathub** (the Generative-AI ban
disqualifies a `Co-Authored-By: Claude` lineage — docs/BAKING.md §5).

### 4. Wire the shipped-but-dead subsystems into `run_app`  ·  DONE 2026-07-03
`notifications/` and `autostart/` are now LIVE. Identity routing was done 2026-07-01
(everything routes through `dough.identity`; `_flatpak.py` retired). **2026-07-03:**
`run_app` re-asserts a user-enabled autostart entry at boot (`_reconcile_autostart` —
self-heals a moved exe path; strictly opt-in, dough never turns it ON), the Settings
dialog gained a "Launch on login" toggle (shown only when `autostart.is_supported()`;
the OS entry is the source of truth — no QSettings mirror), and `AppBus.notify(title,
body)` routes to `dough.notifications` (`_wire_notifications`) so apps drive desktop
notifications from real events with zero imports. Covered by `tests/test_app_wiring.py`.
**Remaining (visual):** eyeball the toggle + a real notification on KDE — piggyback the
next guided session.

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

### 6. P3 polish sweep  ·  MOSTLY DONE 2026-07-03
- Route the remaining bare-slug identity literals through `dough.identity`:
  - ~~`dough/windows_shortcut.py` paths~~ **DONE 2026-07-01**.
  - ~~`dough/power/_linux.py` `Inhibit("dough", "Playing music")`~~ **DONE 2026-07-03**
    (`identity.app()` + a neutral reason; docstring de-musicked).
  - (`autostart/` identity is now DONE — see §4.)
- ~~Rename the `[JT.Lnk]` C# namespace~~ **DONE 2026-07-03** (→ `[Shortcut.Lnk]`, fork-neutral).
- ~~`JT_*` env vars~~ **DONE 2026-07-01**. ~~`jt*` objectNames~~ **DONE 2026-07-03**
  (`doughFrostedDialog`/`doughFrostedTitle`/`doughSelector`/`doughSelectorList`, plus the
  `_jt_*` attrs). **X2 also DONE 2026-07-03**: `dough new` + `sync_loaf` now re-namespace
  `DOUGH_*` env vars (the `\bDOUGH_` prefix pattern in both transforms, parity-tested).
- ~~Docstring sweep~~ **DONE 2026-07-03** (`PlayerBus`→`AppBus` incl. the code aliases;
  music examples neutralized; bus.py/window.py keep their genuinely historical mentions).
- Split `icons.py` into a chrome core vs a `dough.icons.media` extra. **(open — deferred:
  string-keyed dict, no functional gain until a loaf wants to drop the media glyphs)**
- ~~`docs/PHILOSOPHY.md` false identity claim~~ — already fixed (it cites `identity.py` /
  `dough.configure()`); the item was stale.
