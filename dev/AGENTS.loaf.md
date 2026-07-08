# AGENTS.md — the front door

You are an AI agent in the **{{display}}** checkout — an app **baked from
[dough](https://github.com/wolfgangwarehaus/dough)** (the fork-and-own PySide6
base). This repo is OWNED: it is not dough, it does not depend on dough, and
you change anything here freely.

Orient in this order (the session **opening** — the mirror of
`docs/WIND-DOWN.md`, the closing):

1. Read this file (2 minutes).
2. Read **`{{slug}}-board.toml`** — the live maker board (goals + the
   Ingredients/Baking/Delivery/Improvements checklists). **Maker edits are
   DIRECTIVES**: an unchecked item is work, a check you didn't make is a
   decision, and every `note` is the maker steering you — re-ingest them
   before continuing. Update item states as you land work, and at wind-down.
   `{{slug}} board` opens the window; `{{slug}}-board --init` seeds a fresh one.
3. Read the top block of **`docs/TODO.md`** — the handoff that leads with
   "pick up here". If it doesn't exist yet, create it at your first wind-down.
4. Check the session task tracker (if your harness has one) and any memory /
   resume pointer from the last wind-down. Then go.

## Where you are in the workflow

Building with dough runs **Ingredients** (the brief: name, features,
aesthetic, delivery targets — the `[tool.{{slug}}.metadata]` sidecar in
`pyproject.toml`) → **Baking** (the build loop you're probably in) →
**Delivery** (per-channel release via the rendered `packaging/` tree) — then
the **Improvements loop**: Baking ⇄ Delivery, forever.

## Conventions inherited from the base (hard-earned — keep them)

- **Identity flows from ONE seam**: `{{slug}}/identity.py` (runtime) and the
  `[tool.{{slug}}.metadata]` sidecar (build-time). Never write a literal
  slug / org / reverse-DNS id / AUMID anywhere else — the tests gate it.
- **Menus**: use `ui_helpers.opaque_menu()`, never a raw `QMenu` — it handles
  the blur-aware background, sizing, and click-outside dismiss.
- **KDE chrome**: KDE Wayland stays **decorated + a noborder KWin rule**
  (`{{slug}}/noborder/`), NOT `FramelessWindowHint` — the frameless shortcut
  breaks edge-resize and drag. (GNOME/wlroots get additive frameless in
  `window.py`.)
- **Keep the core light.** Heavy or native deps go in
  `[project.optional-dependencies]` when they're optional to the app.
- **Versions come from git tags** (setuptools-scm). Nothing is stamped into
  files; there is no version to bump — tagging `vX.Y.Z` IS the release.
- **The validation gate** before any commit:
  `ruff check .` + `pytest` + `python -m {{slug}}.bake --check`.
  After pushing, check **ALL** GitHub workflows (`gh run list`) — a
  workflow-file parse error fails as a separate 0-second run that a green
  `CI` check hides.

## Pulling base improvements (the sync door)

dough keeps improving after your fork. From a dough checkout:

    python dev/sync_loaf.py --loaf <this repo>          # report drift
    python dev/sync_loaf.py --loaf <this repo> --apply  # write AUTO + NEW modules

Your `dough-sync.toml` records the relationship: `authored` files are yours
(never touched), `manual` files show upstream diffs to port by hand, the rest
sync automatically. Workflows and root docs do NOT sync — port those by hand.

## Closing a session

Run the checklist in **`docs/WIND-DOWN.md`**: land green (all workflows) →
update the `docs/TODO.md` handoff → update memory/notes → reconcile tasks →
commit + push → leave a one-line resume pointer.

## Doc map

| Doc | What it holds |
| --- | --- |
| `docs/TODO.md` | **the handoff — read this every session** |
| `docs/WIND-DOWN.md` | the closing checklist |
| `docs/DESIGN.md` | the 7 first-looks principles (the visual defaults) |
| `docs/BAKING.md` | the `{{slug}} bake` renderer + the channel matrix |
| `docs/RELEASING.md` | cutting a release, channel activation secrets |
| `docs/MACOS.md` | the hardware-earned macOS gotchas |
