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
