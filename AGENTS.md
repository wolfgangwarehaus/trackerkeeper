# AGENTS.md — the front door

You are an AI agent in a **dough** checkout. Orient in this order (the session
**opening** — the mirror of `docs/WIND-DOWN.md`, the closing):

1. Read this file (2 minutes).
2. Read the top block of **`docs/TODO.md`** — the handoff. It always leads with
   "pick up here": current state in a couple of lines, then the exact next steps.
3. Check the session task tracker (if your harness has one) and any memory /
   resume pointer from the last wind-down. Then go.

## What this repo is

dough is a **fork-and-own PySide6 app base** — a project starter, not a library.
Nobody ever `pip install dough` as a dependency; a maker clones it, runs
`dough-new <slug>`, and owns the result (a "**loaf**"). It solves the
cross-platform window chrome, the design system, and the packaging/release
machinery once, so a new app is mostly its own idea.

Two modes of work — know which one you're in:

- **Building WITH dough** (the product): person + GitHub + AI → their own
  cross-platform app. The workflow is **Ingredients** (the brief: name,
  features, aesthetic, targets) → **Baking** (the build loop on the owned
  base) → **Delivery** (guided per-channel release) — then the
  **Improvements loop**: Baking ⇄ Delivery, forever, with base updates pulled
  in via the sync door below.
- **Building dough** (this repo): improving the base itself. The arc is
  **app-led** — gaps surface in real apps (butterPDF, jellytoast) and get
  fixed *here*, in the base, so every future fork inherits the fix.

## Conventions (hard-earned — violating these regresses real fixes)

- **Identity flows from ONE seam**: `dough/identity.py` (runtime) and the
  `[tool.dough.metadata]` sidecar in `pyproject.toml` (build-time). Never
  write a literal slug / org / reverse-DNS id / AUMID anywhere else — the
  tests gate re-literalized ids, and `dough-new`'s whole-word rename depends
  on it.
- **Menus**: use `ui_helpers.opaque_menu()`, never a raw `QMenu` — it handles
  the blur-aware background, sizing, and click-outside dismiss.
- **KDE chrome**: KDE Wayland stays **decorated + a noborder KWin rule**
  (`dough/noborder/`), NOT `FramelessWindowHint`. The frameless shortcut
  breaks edge-resize and drag — it's been reverted once already; don't
  reintroduce it. (GNOME/wlroots get additive frameless in `window.py`.)
- **The core stays PySide6-only.** Heavy or native deps (PDF engines, mpv,
  pyobjc) go in `[project.optional-dependencies]`, never base `dependencies`.
- **Versions come from git tags** (setuptools-scm). Nothing is stamped into
  files; there is no version to bump.
- **The validation gate** before any commit:
  `ruff check .` + `pytest` + `python -m dough.bake --check`.
  After pushing, check **ALL** GitHub workflows (`gh run list`) — a
  workflow-file parse error fails as a separate 0-second run that a green
  `CI` check hides.

## The sync doors

- **UP** (`dev/sync.py` + `dev/shared.toml`): jellytoast refinements → dough.
- **DOWN** (`dev/sync_loaf.py` + `<loaf>/dough-sync.toml`): dough improvements
  → existing forks. This is the Improvements-phase infrastructure. See
  `docs/SYNC.md`.
- Workflows and root docs are **not** synced (package files only) — those
  fixes go to each repo by hand.

## Closing a session

Run the checklist in **`docs/WIND-DOWN.md`**: land green (all workflows) →
update the `docs/TODO.md` handoff → update memory/notes → reconcile tasks →
commit + push → leave a one-line resume pointer.

## Doc map

| Doc | What it holds |
| --- | --- |
| `README.md` | what you get, quick start, fork steps |
| `docs/PHILOSOPHY.md` | why fork-and-own |
| `docs/DESIGN.md` | the 7 first-looks principles (the visual defaults) |
| `docs/BAKING.md` | the `dough bake` renderer + the channel matrix spec |
| `docs/RELEASING.md` | cutting a release, channel activation secrets |
| `docs/MACOS.md` | the hardware-earned macOS gotchas |
| `docs/SYNC.md` | both sync doors |
| `docs/TODO.md` | **the handoff — read this every session** |
| `docs/WIND-DOWN.md` | the closing checklist |
| `docs/BACKPORT.md` / `docs/CHANGELOG.md` | history |
