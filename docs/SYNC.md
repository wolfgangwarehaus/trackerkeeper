# Syncing refinements UP into dough

dough was built by **copying + genericizing** jellytoast's shared modules
(window chrome, theme, blur, the widget kit, the platform backends). That means
the two repos hold *diverged copies* of that shared code. When you improve a
shared thing in jellytoast — a blur-fallback tweak, a resize fix, a new widget —
it does **not** reach dough on its own.

This is the door that pipes those refinements **up** into the base, so every
warehaus app that forks dough inherits them.

> **Direction is jellytoast → dough only.** Refinements bubble *up* to the base.
> The long-term plan (B) is to invert this so jellytoast (and future apps) just
> `import dough` — at which point this door retires and there's a single source
> of truth. We're on A until dough stabilizes.

## The tool

```bash
# from the dough checkout, pointed at your jellytoast checkout:
python dev/sync.py --jellytoast ~/Projects/jellytoast            # report drift (no writes)
python dev/sync.py --jellytoast ~/Projects/jellytoast --apply    # update AUTO modules in place
python dev/sync.py --jellytoast ~/Projects/jellytoast --record   # stamp the new sync point
```

It splits the shared modules (declared in [`dev/shared.toml`](../dev/shared.toml))
into two kinds:

- **AUTO** — pure lifts (e.g. `win_frameless`, `selector`, `blur/`, `theme`,
  `design_tokens`). The string transforms in `shared.toml`
  (`jellytoast`→`dough`, the bus alias) reproduce dough's copy from jellytoast's
  exactly. `sync.py` shows the diff; `--apply` overwrites them — you review +
  commit.
- **MANUAL** — genericized beyond a rename (`ui_helpers`, where the music
  image-loader was carved out; `window.py`, extracted from jellytoast's
  `app.py` chrome). A blind overwrite would re-add the stripped music, so
  `sync.py` shows only the **upstream diff since the last sync** and you port it
  by hand.

`synced_from` in `shared.toml` records the jellytoast commit dough was last
reconciled against; `--record` advances it after a sync.

## The workflow

1. Refine shared code in jellytoast (normal PR, merged to its `main`).
2. The **dough-sync nudge** on the jellytoast PR reminds you when a change
   touches a shared path (so it's never silently forgotten).
3. In the dough checkout: `python dev/sync.py --jellytoast … ` to see what
   drifted. `--apply` the AUTO ones, hand-port the MANUAL ones.
4. Review the diff, commit to dough, and `--record` to advance the sync point.

## The down-door: dough → a loaf (fork)

The up-door above carries jellytoast refinements INTO dough. The **down-door**
(`dev/sync_loaf.py`) carries dough improvements the other way — into an existing
**loaf** (an app forked with `dough new`). This is how a fork-and-own app pulls
base updates without re-forking; it's the mechanism the fork-and-own model rests
on (see `docs/PHILOSOPHY.md`).

```bash
# from the dough checkout, pointed at your loaf:
python dev/sync_loaf.py --loaf ~/Projects/butterPDF --init     # seed the loaf's manifest
python dev/sync_loaf.py --loaf ~/Projects/butterPDF            # report drift (no writes)
python dev/sync_loaf.py --loaf ~/Projects/butterPDF --apply    # write AUTO + NEW modules
python dev/sync_loaf.py --loaf ~/Projects/butterPDF --record   # stamp synced_from = dough HEAD
```

It reproduces a loaf's copy of a shared module by applying the **same whole-word
identity replace `dough new` did** (dough→slug, org, owner) to dough's *current*
source, then diffs against the loaf. Four outcomes:

- **AUTO** — a shared module in both; transformed-dough differs → `--apply`
  overwrites the loaf's copy (you review + commit in the loaf).
- **NEW** — dough gained a module the loaf lacks (a package added after the fork,
  e.g. `noborder/`) → `--apply` adds it, transformed.
- **MANUAL** — a module the fork hand-customized (listed in the loaf's manifest).
  Never overwritten; dough's upstream diff since `synced_from` is shown to port
  by hand — exactly like the up-door's MANUAL handling.
- **authored / in-sync** — the fork's own files (listed) and unchanged modules:
  skipped.

The per-loaf manifest `<loaf>/dough-sync.toml` holds `synced_from` (the dough
commit last reconciled) plus the fork's `authored` / `manual` lists. **Curate
those lists before `--apply`** — anything the maker changed (its window, its
content, its `app.py`) must be `manual` or `authored`, or a blind AUTO overwrite
would clobber it. Identity (slug/org/owner) is read from each side's
`[tool.<pkg>.metadata]`, so nothing is duplicated in the manifest.

> Direction is dough → loaf. Today the tool lives in dough and points at a loaf;
> a later step ships a thin `--loaf .` wrapper into new forks via `dough new` so a
> maker updates from within their own repo.

## Adding a new shared module

If dough lifts another module from jellytoast later, add it implicitly (any
`dough/<x>.py` whose `jellytoast/<x>.py` exists is treated as AUTO) — or, if it
was genericized, list it under `manual` in `shared.toml`. Authored-fresh dough
modules (the bus, the window/app wiring) are listed under `authored` so sync
skips them.
