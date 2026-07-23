# AGENTS.md — the front door

You are an AI agent in the **Tracker Keeper** checkout — an app **baked from
[dough](https://github.com/wolfgangwarehaus/dough)** (the fork-and-own PySide6
base). This repo is OWNED: it is not dough, it does not depend on dough, and
you change anything here freely.

Orient in this order (the session **opening** — the mirror of
`docs/WIND-DOWN.md`, the closing):

1. Read this file (2 minutes).
2. Read **`trackerkeeper-breadboard.toml`** — the live maker board (goals + the
   Ingredients/Baking/Delivery/Improvements checklists). **Maker edits are
   DIRECTIVES**: an unchecked item is work, a check you didn't make is a
   decision, and every `note` is the maker steering you — re-ingest them
   before continuing. If **`agent_request`** is set (the window's Wind down…
   button writes it), FULFIL it (wind down = run `docs/WIND-DOWN.md`) and clear
   the field in the same commit. Update item states as you land work, and at
   wind-down. `trackerkeeper-breadboard` opens the window (`--init` seeds a fresh one).
3. Read the top block of **`docs/TODO.md`** — the handoff that leads with
   "pick up here". If it doesn't exist yet, create it at your first wind-down.
4. Check the session task tracker (if your harness has one) and any memory /
   resume pointer from the last wind-down. Then go.

## Where you are in the workflow

Building with dough runs **Ingredients** (the brief: name, features,
aesthetic, delivery targets — the `[tool.trackerkeeper.metadata]` sidecar in
`pyproject.toml`) → **Baking** (the build loop you're probably in) →
**Delivery** (per-channel release via the rendered `packaging/` tree) — then
the **Improvements loop**: Baking ⇄ Delivery, forever.

## Working the breadboard (the surface you share with the maker)

`trackerkeeper-breadboard.toml` is the contract between three parties — the
maker, the breadboard **window**, and you. All three read AND write it, and it's
git-tracked so its history is the project's. The window (`trackerkeeper-breadboard`)
watches the file and **live-reloads the instant you save it**, so the maker
watches your edits land. It is the source of truth for *what to do next* — keep
it honest as you work, don't let it drift behind reality.

**The contract**

- Maker edits are **directives** — re-ingest before continuing: an unchecked item
  is work, a check you didn't make is a decision, a `note` is the maker steering.
- **`agent_request`** (top-level) is the maker's direct line — the window's
  Wind down… / Ship it buttons write it. FULFIL it, then **clear it in the same
  commit** that lands the work.
- As you land work: flip `done = true`, stamp `by = "agent"` + today's `date`,
  and leave a one-line `note` on what happened. Add items for work you discover.
  Commit the board **in the same commit** as the code it describes.

**The file format** — schema 2; mirror it exactly. The window re-emits a
byte-stable form on every save, so keep your edits minimal and valid TOML and the
diffs stay clean:

- Top level: `schema`, `product`, `goal`, `purpose`, `agent_request`.
- Four phase arrays of tables: `[[ingredients]]`, `[[baking]]`, `[[delivery]]`,
  `[[improvements]]`.
- Each item: `id` (6 hex — a **stable handle; never change or drop it**), `text`,
  `done` (bool); optional `by` / `date` (ISO `YYYY-MM-DD`) / `note` (omit when
  empty). Edit items **in place** by their `id` — don't reorder gratuitously.
- **Baking items also carry `priority`** = `now` | `next` | `later` (the kanban
  columns); new baking work defaults to `next`. `trackerkeeper-breadboard --init`
  seeds a fresh board.

## Conventions inherited from the base (hard-earned — keep them)

- **Identity flows from ONE seam**: `trackerkeeper/identity.py` (runtime) and the
  `[tool.trackerkeeper.metadata]` sidecar (build-time). Never write a literal
  slug / org / reverse-DNS id / AUMID anywhere else — the tests gate it.
- **Menus**: use `ui_helpers.opaque_menu()`, never a raw `QMenu` — it handles
  the blur-aware background, sizing, and click-outside dismiss.
- **KDE chrome**: KDE Wayland stays **decorated + a noborder KWin rule**
  (`trackerkeeper/noborder/`), NOT `FramelessWindowHint` — the frameless shortcut
  breaks edge-resize and drag. (GNOME/wlroots get additive frameless in
  `window.py`.)
- **Keep the core light.** Heavy or native deps go in
  `[project.optional-dependencies]` when they're optional to the app.
- **Versions come from git tags** (setuptools-scm). Nothing is stamped into
  files; there is no version to bump — tagging `vX.Y.Z` IS the release.
- **The validation gate** before any commit:
  `ruff check .` + `pytest` + `python -m trackerkeeper.bake --check`.
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
| `docs/BAKING.md` | the `trackerkeeper bake` renderer + the channel matrix |
| `docs/RELEASING.md` | cutting a release, channel activation secrets |
| `docs/MACOS.md` | the hardware-earned macOS gotchas |
