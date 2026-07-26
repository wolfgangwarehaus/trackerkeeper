# TODO — the handoff

**Read this first.** Current state in two lines, then exactly what to do next,
then the standing backlog.

## Where things stand (2026-07-26)

**Three releases are out.** v0.1.2 — the looks pass — is published on GitHub
(7 artifacts) and PyPI, verified by a clean-venv `pip install trackerkeeper==0.1.2`.
Publishing is now hands-off end to end: the Trusted Publisher is registered, so
the PyPI leg rides every tag.

Since that tag, `main` carries a refactor (a checker is declared **once**, not in
six places across four files), a changelog lint, and a dough sync
(`85b7957..9acb395`) — all under `[Unreleased]`, i.e. an 0.1.3's worth of
housekeeping rather than a feature release. Nothing is half-landed.

The app is a tray-resident watchtower over the maker's real fleet with **eight
auto-checkers** plus the manual fallback, checking on a timer whether or not the
window is open. Everything is green: `ruff`, 493 tests, `bake --check`, `rig
boot` / `probe` / `baseline` (0.00% drift), and CI on all legs.

## Pick up here (in order)

1. **Grow the checker library** (improvements `bb5d4c`) — this is the moat, and
   it's the only open item that isn't housekeeping or blocked. `rss` is the
   widest-coverage way in for a new source; reach for a bespoke checker only when
   a source has no feed.
2. **Cut v0.1.3** when `[Unreleased]` feels worth shipping (it's currently a
   refactor + two fixes). `docs/RELEASING.md`; the tag IS the version.
3. **The two `later` baking cards**, when you want structural work rather than
   product: extract the Qt-free logic out of `dashboard.py` (`086ae4`, 704 lines
   of mixed pure/widget code) and give `Item` a stable id (`9a6b97` — refresh
   results are keyed by *name* today, which `ItemDialog`'s uniqueness check makes
   work by convention rather than by structure).

**Not actionable:** AUR (delivery `0a95b7`) is externally blocked — it needs an
`AUR_SSH_PRIVATE_KEY` secret *and* AUR to reopen new-package registration (frozen
since the 2026 malware wave). deb + AppImage already ship on every release.

## What exists now (so you don't re-derive it)

**Eight checkers**, all in `sources.py`, each a `(item, http, http_text)`
function behind two injected network seams (so no test touches the network).
Each one is a single `Source` record — kind, label, help text, checker,
validator — and the Add dialog, the validation and the labels all derive from
it, so adding a checker means adding one entry:

| kind | source | notes |
| --- | --- | --- |
| `github` | GitHub releases API | latest **stable** (pre-releases skipped by design) |
| `arch` | archlinux.org JSON search | prefers stable repo over testing |
| `flatpak` | Flathub appstream API | prefers the newest **stable** release (the feed carries dev builds) |
| `appstore` | Apple iTunes Lookup | app id **or** bundle id; the whole iOS/Mac store |
| `appledev` | Apple developer-releases RSS | `ref` is an OS filter — "iOS 27", "macOS 27" |
| `steam` | Steam news API | filters to `patchnotes`; version parsed from the title |
| `cachyos` | mirror ISO index | rolling distro — newest `YYMMDD` snapshot folder |
| `rss` | **any** RSS/Atom feed | `ref` = feed URL + optional title filter |
| `manual` | — | the universal fallback; never fabricates a version |

`rss` is the widest-coverage one and the answer for the long tail. `ref` is the
feed URL, optionally followed by a space and a filter phrase
(`https://kde.org/announcements/index.xml plasma`) — URLs can't contain spaces,
so the split is unambiguous. It reads both dialects, and when a feed ships empty
`<title/>` elements it takes the version from the entry **link** instead — KDE's
own announcement feed does exactly that, and a title-only reader sees nothing.

**The heartbeat** (`dashboard.py`): a `QTimer` re-checks every 2 h by default
(15 min floor, `0` = manual only), running whether or not the window is visible;
showing the window re-checks when stale. The timer stays `None` under offscreen,
which doubles as the "network is allowed" sentinel — headless runs never reach
the network. Checks run **concurrently** (pool of 8), so one dead mirror can't
stall the rest.

**"New since you last looked"**: `Item.seen_version` + `is_new()`. `has_update()`
stays true until you install, so it can't tell *pending* from *news*; `is_new()`
is an update you haven't laid eyes on, and it's persisted. Banked on
`hideEvent` — banking on show would clear the badges in the instant they
appeared. Notifications deliberately still fire only when `latest` **changes**;
firing on "unseen" would re-notify every cycle until you looked.

**The cardinal rule** (holds everywhere): a card only ever shows a version a
real source returned. Unreachable → "couldn't check", never an invented latest.

**UI:** one top bar (hamburger + settings left, title + badge, actions right,
window controls) — the dashboard folds its header onto it via
`TopBar.add_action()` / `insert_title_widget()` / `add_menu_action()`. Below it:
sort chips (Updated / Channel, click the active one to flip direction), a Group
toggle, then collapsible category sections. Density comes from the design-token
type ladder (CAPTION/TINY/MICRO), never literal px, so the font-scale setting
still works. `width_tier()` drops columns as the window narrows.

**Tray** (`tray.py`): tooltip carries the update count *and* the unseen count
("3 updates available, 1 new"), menu (Show / Check / Settings / Quit),
click-to-toggle, close-to-tray, start-in-tray. Self-disables when the desktop
has no tray so the window can never be trapped invisible —
`tray.will_have_tray()` is the single predicate for that, and start-in-tray is
gated on it (skipping the show without a tray would launch a process with no
icon *and* no window).

**Settings** now has a TRACKING section: check interval, show tray icon,
close-to-tray, start-in-tray. The interval re-arms the live dashboard through
`AppBus.tracking_prefs_changed` — no relaunch.

## Standing backlog

Everything that was listed here through v0.1.2 has shipped — Flatpak, conditional
requests, "no match" vs "unreachable", the per-item detail view, the brand, and
the rig goldens. What's actually left:

- **More checkers** (improvements `bb5d4c`) — store pages, more feeds,
  per-platform firmware. The open-ended one; the moat.
- **Extract the Qt-free logic out of `dashboard.py`** (baking `086ae4`) —
  `humanize_age` / `_parse_iso` / `_bucket_days`, the sort keys and `width_tier`
  are pure functions testable without a widget.
- **A stable `Item` id** (baking `9a6b97`) — `_RefreshWorker` emits
  `{item.name: result}`, safe by convention only.
- **AUR** (delivery `0a95b7`) — externally blocked, see the top of this file.
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
- **`processEvents()` does not deliver `DeferredDelete`.** This was the CI abort
  that cost a re-run on most pushes: conftest `deleteLater()`'d every widget but
  never reaped them, so hundreds died at once inside the first *real* nested
  `QEventLoop` (`_spin()` in `test_single_instance_forwarding`). Fixed with an
  explicit `sendPostedEvents(None, QEvent.Type.DeferredDelete)` — which also made
  the suite ~2× faster, since every `processEvents()` had been walking an
  ever-growing object graph. If the abort ever returns, look for a *new* fixture
  that defers deletion without reaping it.
- **Classify a file in `dough-sync.toml` the MOMENT you customize it.** Twice now
  an unclassified (therefore AUTO) file has been one `sync_loaf --apply` from
  being silently reverted — most recently `settings.py` / `theme.py` /
  `color_tokens.py` / `icons.py`, i.e. the entire brand accent, plus a deleted
  `ElidedLabel`. The suite stays green through it, because "the accent is the
  wrong colour" is not something tests notice; only reading the diff caught it.
  All four are `manual` now, as are `top_bar.py`, `settings_dialog.py`, `bus.py`
  and `rig.py`; `tray.py` and `detail_dialog.py` are `authored`.
