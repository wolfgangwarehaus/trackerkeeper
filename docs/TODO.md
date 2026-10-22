# TODO — the handoff

**Read this first.** Current state in two lines, then exactly what to do next,
then the standing backlog.

## Where things stand (2026-10-22)

**v0.1.3 is tagged** — the phone interface release. It's the first release with
a Flatpak, a Windows Arm64 build, and the phone interface inside the `.deb` /
AppImage (the bundles used to strip Qt Quick). The tag builds a DRAFT; publish
it on GitHub to fire PyPI. August has the phone interface running from the
checkout on the phone (the redesign: ⋮ filter, green only for news), and the
update checks were audited: all 9 sources right, every changelog link now opens
real release notes.

**Your dev session IS a Plasma Mobile session** (`PLASMA_PLATFORM=phone:handset`),
streamed to the phone. So on this machine the app picks the phone UI, and
`tests/conftest.py` pins `TRACKERKEEPER_UI=widgets` so app-booting tests still
drive the desktop window. Run the rig with `TRACKERKEEPER_UI=widgets` too.

## Pick up here (in order)

1. **The Add tool — august's "most major work for this app"** (improvements
   `67f73e`). Today Add is a raw form: pick a checker, type its handle. Make it
   work across lots of scenarios and sources: paste anything (a GitHub / Steam /
   App Store / Flathub / AUR / feed URL → kind + ref detected), search a source
   by name, preview the latest version before saving, suggest a changelog link
   (`{version}` templates). Same logic for both front ends — put it beside
   `sources.py`, not in a dialog. Pairs with more checkers (`bb5d4c`) and the
   per-item version pattern (Purple Turnip reads as a filename).
2. **Switch on the dormant channels** — each needs august, not code
   (`docs/RELEASING.md` has the table): copy jellytoast's 7 Apple secrets for
   macOS; `WINGET_TOKEN`; AUR key + package registration; reserve the name in
   Partner Center for the Microsoft Store. Mac App Store isn't ported yet.
3. **Phone Settings** (baking `cf38ae`) — the phone has no way to reach
   Settings (interval, theme, accent, back to the desktop UI).

Later: a live QML rig (`9395a5`), the rest of `086ae4`, a stable `Item` id
(`9a6b97`), a dual-arch Windows installer (Arm64 ships a portable zip today).

## The phone interface (so you don't re-derive it)

- **Choice:** `quick.wanted()` — `TRACKERKEEPER_UI=quick|widgets` forces; else an
  undocked phone shell (`PLASMA_PLATFORM=phone*`, `QT_QUICK_CONTROLS_MOBILE`, or
  `XDG_CURRENT_DESKTOP` containing Phosh). Docked = `plasmamobilerc`
  `convergenceModeEnabled=true` → desktop window. Hooked into `run_app` after the
  shared boot (identity, logging, migrations, i18n, single instance, theme,
  notifications); a QML load failure falls through to the window.
- **Bridge:** `quick/fleet_model.py` `Fleet` (list model + verbs: refresh,
  markUpdated, remove, save with the Add dialog's validation, markSeen on app
  backgrounding) over **`fleet.py`**, the widget-free logic both UIs share.
  `quick/theme.py` is opaque and follows the OS light/dark switch live.
  `quick/icons.py` holds the extra glyphs — not in `icons.py`, which dough syncs.
- **QML:** `Main.qml` (list, chips, pull-to-check, + button), `ItemRow.qml`,
  `DetailSheet.qml`, `EditPage.qml`, plus small components on the **Basic** style
  (never the platform style: Plasma exports `org.kde.breeze`, which pip's PySide6
  can't load).
- **No tray on a phone:** Plasma Mobile registers a tray host but draws no items,
  so `tray.will_have_tray()` is False on an undocked phone shell.
- **Testing:** `tests/test_quick.py` loads the real QML offscreen. List delegates
  are *visual* children — walk `childItems()`, not `findChildren()`. Offscreen
  ignores `setColorScheme`; force dark via `settings.theme_mode = "frosted_dark"`.
  The app venv (`.venv`, PySide6 6.11) differs from system python (6.12) — run
  both when touching QML.

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
- **Finish extracting the Qt-free logic out of `dashboard.py`** (baking
  `086ae4`) — the pure helpers moved to `fleet.py` on 2026-10-21; left are
  `refresh_interval_minutes` and the sort/group ordering, which
  `quick/fleet_model.order` currently duplicates.
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
- **`rig probe` / `rig shot` need no other instance running** — single-instance
  refuses the second launch and the X11 leg reports "(no window)" as a false
  FAIL. `shot` says so plainly when it detects one; it has also been seen to
  fail once with a bare "capture failed" and then pass on an immediate retry, so
  treat a lone `shot` failure as a flake and re-run before chasing it.
- **An editable install's version stamp goes stale, and the app nags about it.**
  `trackerkeeper/_version.py` is written by setuptools-scm at *install* time and
  is gitignored, so it freezes at whatever the install saw. The checkout here was
  stamped `0.0.1.dev105+gd66291d9b` — from before v0.1.0 was ever tagged — so the
  in-app update check compared it against GitHub's latest and the top bar sat
  there saying "Update 0.1.2" on a build that was seven commits *ahead* of it.
  Nothing was wrong with the code. `pip install -e .` regenerates the stamp. If
  the desktop icon's app ever claims to be behind, check `__version__` first.
- **A visual golden only guards the tier it was grabbed at.** `width_tier()`
  makes the tight and wide layouts genuinely different UIs — the platform tag,
  the channel column and the full button labels only exist above 620px. The gate
  grabbed one size for months *and it wasn't even the size the rig asked for*:
  `_grab_shots` resized before `set_content`, and the Dashboard resizes the
  window to `DEFAULT_SIZE` when there's no restored geometry (under the scratch
  identity, always), so the resize was silently overwritten. Now `window` +
  `window_wide` + `settings`. If you add another responsive breakpoint, it needs
  its own golden or it is unguarded.
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
