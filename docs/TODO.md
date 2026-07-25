# TODO — the handoff

**Read this first.** Current state in two lines, then exactly what to do next,
then the standing backlog.

## Where things stand (2026-07-25)

**v0.1.0 is tagged and built.** The release workflow produced a complete draft —
`.deb`, AppImage (+`.zsync`), Windows setup `.exe` + portable `.zip`, sdist,
wheel, `SHA256SUMS`, Sigstore attestations. It is **unpublished**: reviewing and
clicking Publish on GitHub is the one deliberate human gate, and publishing
fires `pypi-publish.yml` (PyPI via OIDC).

Since the tag, `main` has moved on with the heartbeat, "new since you last
looked", the Tracking settings section, and a generic RSS/Atom checker — all
under `[Unreleased]` in the changelog, i.e. the substance of an 0.2.0.

The app is a tray-resident watchtower over a 9-item fleet, every item
auto-checked, that now **keeps checking on a timer whether or not the window is
open**. CI is green on all five legs.

## Pick up here (in order)

1. **Publish the v0.1.0 draft** — review it at
   `gh release view v0.1.0 --web`, then Publish. Delivery item `267380`.
   (The tag was force-moved once, onto `edcf503`, so the released commit is
   green; the draft is idempotently rebuilt on any re-push of the tag.)
2. **Ship Linux-first** (delivery `0a95b7`): AUR + deb/AppImage via
   `trackerkeeper-deliver`. Note `aur.yml` stays dormant until an
   `AUR_SSH_PRIVATE_KEY` secret exists **and** AUR reopens new-package
   registration.
3. **Then 0.2.0** when the `[Unreleased]` block feels complete — the two
   cheapest wins on the board are conditional requests (`cb0d95`) and
   distinguishing "no match" from "unreachable" (`4e3124`).

## Resolved: the CI abort that cost a re-run on most pushes

**Root cause found, and it was not in the single-instance code.** conftest's
`_isolate_qt_windows` closed and `deleteLater()`'d every top-level widget after
each test, then called `processEvents()` — but **`processEvents()` does not
deliver `DeferredDelete`**. Qt only reaps those when an event loop unwinds to
the nesting level that posted them, and that fixture never runs one:

```python
w = QWidget(); w.deleteLater()
app.processEvents()                                   # -> still alive
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)  # -> destroyed
```

So every `deleteLater()`'d widget in the suite stayed alive until the first test
that spun a **real nested `QEventLoop`** — `_spin()` in
`test_single_instance_forwarding` — which then destroyed hundreds at once, in
arbitrary order, each carrying native blur / event-filter state. That explains
every symptom: always the same point, always right after
`test_settings_migration` (its alphabetical predecessor), roaming across all
three OSes, passing locally on a single file, and cleared by `rerun --failed`
(which runs that file alone).

Fixed in `tests/conftest.py` with an explicit `sendPostedEvents(DeferredDelete)`.
Side effect: the suite got **~2× faster** (8–10 s → ~4 s) while running more
tests, because every `processEvents()` had been walking an ever-growing object
graph. If an abort ever returns, look for a *new* fixture that defers deletion
without reaping it.

## What exists now (so you don't re-derive it)

**Seven checkers**, all in `sources.py`, each a `(item, http, http_text)`
function behind two injected network seams (so no test touches the network):

| kind | source | notes |
| --- | --- | --- |
| `github` | GitHub releases API | latest **stable** (pre-releases skipped by design) |
| `arch` | archlinux.org JSON search | prefers stable repo over testing |
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

- **More checkers**: Flatpak (baking `f7a5a3`, Arch half already shipped) —
  Flathub's `/api/v2/appstream/<id>` is the obvious way in.
- **Conditional requests** (`cb0d95`) — ETag/`If-None-Match` + optional GitHub
  token. Matters more now that checks run every 2 h by default.
- **"No match" vs "unreachable"** (`4e3124`) — a typo'd ref currently reads as a
  network blip.
- **Per-item detail view** (`ba86e2`) — GitHub hands you `body` and Steam
  `contents` for free; both are currently discarded in favour of a link.
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
