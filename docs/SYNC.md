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

## Adding a new shared module

If dough lifts another module from jellytoast later, add it implicitly (any
`dough/<x>.py` whose `jellytoast/<x>.py` exists is treated as AUTO) — or, if it
was genericized, list it under `manual` in `shared.toml`. Authored-fresh dough
modules (the bus, the window/app wiring) are listed under `authored` so sync
skips them.
