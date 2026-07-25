# Changelog

All notable changes to trackerkeeper are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/) and **the git tag is the version** (setuptools-scm).

Cutting a release moves the `[Unreleased]` section below into a dated
`[X.Y.Z]` heading, then `git tag vX.Y.Z`. `release.yml` lifts that section verbatim
into the GitHub release notes (falling back to auto-generated notes if the tag has
no matching section). See `docs/RELEASING.md`.

## [Unreleased]

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
