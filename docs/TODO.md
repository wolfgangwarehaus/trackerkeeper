# TODO — the handoff

**Read this first.** Current state in two lines, then exactly what to do next,
then the standing backlog.

## Where things stand (2026-07-24)

tracker keeper is a **working app**: a tray-resident watchtower over a 9-item
fleet, every item auto-checked by a real source (no manual entries left), with a
sortable/groupable/collapsible dashboard that scales from a 300 px utility strip
to full screen. Everything is committed and pushed to `main`; CI is green on all
five legs (lint-and-smoke, tests ×3 OSes, build) and `rig probe` PASSes on KDE
Wayland.

The MVP gate on the breadboard is met. **v0.1.0 has not been cut yet** — that's
the next real milestone.

## Pick up here (in order)

1. **Cut v0.1.0.** Versions come from git tags (setuptools-scm) — there is no
   version to bump, so `git tag v0.1.0 && git push --tags` IS the release. Then
   watch the release workflow and confirm artifacts. Delivery item `267380` on
   the breadboard.
2. **Decide the flaky-test question** (below) — it costs a CI re-run on most
   pushes and erodes the "never wind down red" gate.
3. **Ship Linux-first** (delivery `0a95b7`): AUR + deb/AppImage via
   `trackerkeeper-deliver`.

## Known issue: a flaky test blocking first-try green

`tests/test_single_instance_forwarding.py` aborts with **SIGABRT (exit 134)** on
CI — 3 of the last 4 pushes, on both `ubuntu-latest` and `macos-latest`, always
at the same point (right as the module starts, after `test_settings_migration`).
It **passes locally every time** and is unrelated to any recent feature work.
`gh run rerun --failed` clears it every time.

Three ways forward, unresolved: (a) dig in properly — it doesn't reproduce
locally, so it means iterating against CI; (b) harden the fixture teardown
(delete the `QLocalServer`, drop the signal connections, clear the socket file)
— cheap and plausible but unproven against a heisenbug; (c) leave it and re-run.
Recommendation was (b), then watch.

## What exists now (so you don't re-derive it)

**Six checkers**, all in `sources.py`, each a `(item, http, http_text)`
function behind two injected network seams (so no test touches the network):

| kind | source | notes |
| --- | --- | --- |
| `github` | GitHub releases API | latest **stable** (pre-releases skipped by design) |
| `arch` | archlinux.org JSON search | prefers stable repo over testing |
| `appstore` | Apple iTunes Lookup | app id **or** bundle id; the whole iOS/Mac store |
| `appledev` | Apple developer-releases RSS | `ref` is an OS filter — "iOS 27", "macOS 27" |
| `steam` | Steam news API | filters to `patchnotes`; version parsed from the title |
| `cachyos` | mirror ISO index | rolling distro — newest `YYMMDD` snapshot folder |
| `manual` | — | the universal fallback; never fabricates a version |

**The cardinal rule** (holds everywhere): a card only ever shows a version a
real source returned. Unreachable → "couldn't check", never an invented latest.

**UI:** one top bar (hamburger + settings left, title + badge, actions right,
window controls) — the dashboard folds its header onto it via
`TopBar.add_action()` / `insert_title_widget()` / `add_menu_action()`. Below it:
sort chips (Updated / Channel, click the active one to flip direction), a Group
toggle, then collapsible category sections. Density comes from the design-token
type ladder (CAPTION/TINY/MICRO), never literal px, so the font-scale setting
still works. `width_tier()` drops columns as the window narrows.

**Tray** (`tray.py`): tooltip carries the update count, menu (Show / Check /
Settings / Quit), click-to-toggle, close-to-tray. Self-disables when the desktop
has no tray so the window can never be trapped invisible.

## Standing backlog

- **Settings UI for the tray** — `show_tray_icon` / `close_to_tray` are live
  prefs with sensible defaults but no toggles in the Settings dialog.
- **Start minimized to tray** — so autostart boots straight to the tray.
- **More checkers**: Flatpak (baking `f7a5a3`, Arch half already shipped),
  RSS/Atom feeds (`cc76e7`).
- **"New since you last looked" + desktop notifications** (`914799`).
- **Per-item detail view** (`ba86e2`).
- **Brand**: replace the placeholder logo SVG + pick an accent (ingredient
  `ac9750`) — currently riding the system accent.
- **rig baseline goldens** now that the UI has settled (`eb70cb`).
- **CachyOS `kde` edition** doesn't parse (different mirror layout); `desktop`,
  `handheld`, `cli` work.

## Gotchas worth keeping

- **Two catalogs.** `default_fleet()` in `catalog.py` is the seed for a *fresh*
  install; the live fleet is `~/.local/share/wolfgangwarehaus/trackerkeeper/catalog.json`
  and **the file wins**. Editing only the seed changes nothing for an existing
  user — that cost a debugging round early on.
- **Stop the app before hand-editing that JSON**, or the running instance
  overwrites your edit on its next save.
- **`rig probe` needs no other instance running** — single-instance refuses the
  probe's second launch and the X11 leg reports "(no window)" as a false FAIL.
- **Re-render must un-parent before `deleteLater`**, or old rows ghost over the
  new layout.
- `top_bar.py` is now `manual` in `dough-sync.toml` (it was unclassified, i.e.
  AUTO — a sync would have silently overwritten the hamburger work); `tray.py`
  is `authored`.
