# Changelog

All notable changes to trackerkeeper are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/) and **the git tag is the version** (setuptools-scm).

Cutting a release moves the `[Unreleased]` section below into a dated
`[X.Y.Z]` heading, then `git tag vX.Y.Z`. `release.yml` lifts that section verbatim
into the GitHub release notes (falling back to auto-generated notes if the tag has
no matching section). See `docs/RELEASING.md`.

## [Unreleased]

### Added
- **Per-item detail.** Click any card to see what actually changed — the release
  notes the checkers were already fetching and throwing away. GitHub's release
  body, Steam's announcement, the App Store's "What's New", Flathub's release
  description, and any RSS entry's body all land here, normalised to plain text.
  A source that structurally can't carry notes (a package index, an ISO mirror)
  says so rather than showing an empty box.
  Notes render as **plain text, never rich text**: the body is written by a third
  party, and handing arbitrary remote HTML to a Qt rich-text widget would pull in
  remote images and let a stranger control the markup. The changelog link still
  goes to the fully formatted original.

### Fixed
- The Steam checker asked for `maxlength=1`, truncating every announcement body
  to a single character — invisible while only the title was read, and exactly
  what the detail view needed.

## [0.1.1] — 2026-07-25

The watchtower actually watches now. v0.1.0 only checked at launch, so a
tray-resident app showed you whatever the world looked like when you booted it;
this release adds the heartbeat, tells you what's new *since you last looked*,
and grows the checker count from six to eight.

### Added
- **A Flatpak checker** (`flatpak`) — Flathub app id (`org.videolan.VLC`) via
  Flathub's appstream API. With `arch` beside it that's most of a Linux desktop
  covered. Prefers the newest **stable** release: the feed carries development
  builds too, and quietly promoting you onto a beta would misrepresent "latest".
- **An optional GitHub token** — set `TRACKERKEEPER_GITHUB_TOKEN` (or
  `GITHUB_TOKEN` / `GH_TOKEN`) to raise GitHub's unauthenticated 60 requests/hour
  to 5000. Read from the environment, never stored by the app, and sent **only**
  to `api.github.com` — a token in your environment is never handed to a distro
  mirror or a changelog feed.
- **A generic RSS / Atom checker** (`rss`) — the widest-coverage source yet, and
  the answer for the long tail: most projects publish releases as a feed even
  when they expose no API at all. `ref` is the feed URL, optionally followed by
  a space and a filter phrase (`https://…/index.xml plasma`) so one busy feed
  can serve several tracked items. Handles both feed dialects, and falls back to
  the entry link when a feed ships empty titles — as KDE's own does.
- **The heartbeat.** tracker keeper now re-checks on a timer (every 2 hours by
  default, 15 minutes minimum, `0` for manual-only) instead of once at launch —
  and the timer runs whether or not the window is open, because a watchtower
  resting in the tray is still watching. Opening the window from the tray also
  re-checks when the data has gone stale, so what you see is current.

### Changed
- **Checks run concurrently** (up to 8 at a time) rather than one after another.
  A refresh used to take as long as the *sum* of its sources, and one
  unreachable mirror stalled every item queued behind it.
- **Conditional requests.** Every fetch now sends `If-None-Match` /
  `If-Modified-Since` and serves the cached body on a `304`. On GitHub a 304
  costs **no rate-limit quota**, which is what makes a two-hourly heartbeat
  affordable in the first place.
- **A failed check says which failure it was.** "Couldn't reach the source" and
  "nothing matched this source — check the handle" need different reactions;
  reporting both as "couldn't check" sent you debugging your network when the
  actual problem was a typo'd app id.
- **New since you last looked.** An update that arrives while you're away is
  now marked `NEW` until you actually open the window, and the state is stored
  — so a restart doesn't re-shout what you already saw, and it doesn't quietly
  drop it either. The tray tooltip reports it too ("3 updates available, 1 new").
- **Settings gained a Tracking section**: how often to check (15 minutes to 12
  hours, or only when you ask), show the tray icon, close-to-tray, and start in
  the tray. The interval re-arms live — no relaunch to change how often a
  watchtower watches.

### Fixed
- A changelog URL is now escaped before it reaches the card's rich-text label —
  those URLs are user-entered, and an unescaped quote could close the `href` and
  let the rest of the string render as markup.
- **The release tooling broke its own first release.** The Inno Setup template
  carried a sample `/DAppVersion=0.1.0`, and the gate asserting no committed file
  bakes the current version saw that as live the moment v0.1.0 was tagged. That
  gate also matched substrings, so `1.0.0` would have matched inside the MSIX
  placeholder `1.0.0.0` and failed the same way at v1.0.0. Both fixed upstream in
  dough, so no future release — here or in any other app built from it — trips
  over them.

### Internal
- **The test suite was writing to your real settings.** It had no isolation at
  all, so `pytest` edited `~/.config/<org>/trackerkeeper.conf` — a run could
  silently discard collapsed groups you'd set. Closing it properly took three
  Qt calls plus the shipped `Settings` constructor (which used the bare
  `QSettings(org, app)` form, hardwiring NativeFormat); production behaviour is
  unchanged.
- **The intermittent CI abort had a root cause**, and it wasn't the test being
  blamed: `processEvents()` never delivers `DeferredDelete`, so the whole suite's
  widgets were destroyed at once by the first test to spin a real nested event
  loop. Fixing it also roughly halved the suite's runtime.

## [0.1.0] — 2026-07-25

The first release. tracker keeper is a **watchtower, not an updater**: it tells
you what's new across everything you own and links the changelog — it never
downloads, installs, or applies anything.

### Added
- **The dashboard** — your fleet in one scrollable column, newest-update-first.
  Each card shows what you have vs what the source found, how long ago it
  dropped, its release channel, and a changelog link. Sort by recency or
  channel (click the active chip to flip direction), group into your own
  categories, and collapse the sections you're not watching today.
- **Six source checkers**, each a small function behind two injected network
  seams so no test ever touches the network:

  | kind | source | handle (`ref`) |
  | --- | --- | --- |
  | `github` | GitHub releases API | `owner/repo` |
  | `arch` | archlinux.org package search | the pkgname |
  | `appstore` | Apple iTunes Lookup | track id **or** bundle id |
  | `appledev` | Apple developer-releases feed | an OS filter — "iOS 27" |
  | `steam` | Steam news API | the numeric appid |
  | `cachyos` | the mirror's dated ISO index | the edition |

  Plus `manual` — the universal fallback for a world no checker reaches yet.
- **A tray presence.** The app rests in the system tray with the update count
  in its tooltip, a menu (Show / Check / Settings / Quit), click-to-toggle, and
  close-to-tray. It self-disables where the desktop has no tray, so the window
  can never be trapped invisible.
- **Utility sizing** — a 480×620 default that stays readable down to a 300px
  strip, dropping columns and labels as it narrows rather than squeezing them.
- **Desktop notifications** when a check finds something genuinely new.
- The baking phase: a single metadata source (`[tool.trackerkeeper.metadata]`), the
  `trackerkeeper bake` renderer, and the first channels — PyPI, a loose `.deb`, and an
  AppImage — generated from one source and verified against drift.

### The rule it lives by
A card only ever shows a version a **real source returned**. A check that can't
reach a source keeps the last-known value and says "couldn't check" — tracker
keeper never invents a latest.

<!-- release-notes-end -->
