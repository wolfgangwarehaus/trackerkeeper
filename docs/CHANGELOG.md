# Changelog

All notable changes to trackerkeeper are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/) and **the git tag is the version** (setuptools-scm).

Cutting a release moves the `[Unreleased]` section below into a dated
`[X.Y.Z]` heading, then `git tag vX.Y.Z`. `release.yml` lifts that section verbatim
into the GitHub release notes (falling back to auto-generated notes if the tag has
no matching section). See `docs/RELEASING.md`.

## [Unreleased]

### Changed
- **The brand accent moved to the identity seam.** It had been edited into
  `theme.py`, `color_tokens.py`, `settings.py` and `icons.py` — base files the
  dough sync owns — and a routine `sync_loaf --apply` reverted the whole brand
  to dough's violet in one command, with the test suite green throughout. It now
  lives in `identity.py` (the file this app already owns), the pressed shade
  derives from it, and those four sync cleanly again. Verified by running a full
  sync and checking the brand came out the other side.
- **A checker is declared once.** Adding a source used to mean editing six
  places across four files, with nothing keeping them in step — a missing label
  was a `KeyError` the moment the Add dialog opened, and a missing validation
  arm silently accepted a handle that would never resolve. There's now one
  `Source` record per checker and everything derives from it.

### Fixed
- `rig probe` / `rig shot` no longer fail opaquely when the app is already
  running. Both launch their own copy to observe; single-instance hands the
  second launch back to the first, so they were measuring a process that had
  already exited and reporting "the window never appeared". They now say so and
  tell you to close it.
- The changelog is linted by the test suite, because `release.yml` lifts it
  verbatim into the release notes and nothing else reads it until it ships.

## [0.1.2] — 2026-07-26

The looks pass. tracker keeper stops wearing dough's placeholder, learns to tell
you *what* changed rather than only *that* something did, and becomes usable at
the 300px width it always advertised.

### Added
- **A real logo, and a brand accent to match.** The first two releases shipped
  wearing dough's placeholder blob. The mark is a refresh wheel closing on a
  check — the ring is the update cycle, the check is "you're current" — with the
  gap and arrowhead in the bottom-right, the one quadrant the check's diagonal
  never crosses. One accent throughout, because a two-tone draft put a
  near-white check on the ring that vanished on light backgrounds. The default
  accent moves from dough's violet to the brand green `#2fbe8a` (already the
  "Green" preset), so a fresh profile's chrome matches its own icon.
- **Per-item detail.** Click any card to see what actually changed — the release
  notes the checkers were already fetching and throwing away. GitHub's release
  body, Steam's announcement, the App Store's "What's New", Flathub's release
  description and any RSS entry's body all land here, normalised to plain text.
  A source that structurally can't carry notes (a package index, an ISO mirror)
  says so rather than showing an empty box.

  Notes render as **plain text, never rich text**: the body is written by a
  third party, and handing arbitrary remote HTML to a Qt rich-text widget would
  pull in remote images and let a stranger control the markup. The changelog
  link still goes to the fully formatted original.

### Changed
- **The fleet list has a foreground.** A card had two states — pending or not —
  so a month-old update looked exactly like one from an hour ago, and every row
  wore the same green. Now there are three: **fresh** (an update inside a week)
  leads with a full-white name and the accent on the dot, the new build and the
  changelog link; **pending but older** keeps its dot and its *mark updated*
  button — it's still yours to install — but eases back to neutral; **current**
  sits quietest of all.
- **One accent, not two near-identical greens.** The "new" colour (`#56c48d`)
  sat a few points off the accent (`#2fbe8a`) while meaning something different,
  which read as a printing error rather than a distinction. The accent is now
  the single colour meaning *live news*, and card tints derive from whatever
  accent is active rather than a frozen hex — so picking another accent
  recolours the list properly.
- **Category sections read as sections.** A dim caps label over a flat run of
  cards left the groups blending into one list. The header is brighter and
  carries a hairline rule, the cards step in beneath it, and sections are
  separated by a gap.
- **The app name reads in full at every width.** The title steps down the type
  ladder as the bar tightens (subhead → body → caption) instead of eliding, and
  the update badge shortens with it — `· 3 updates available`, then `· 3 new`,
  then just `· 3`. At 300px the app's own name is worth more of that row than
  two extra words.

### Fixed
- **The app is legible at its minimum width.** At 300px the fleet list was
  unusable: names chopped to `Stea` / `Game` / `Slay`, versions to `202607`, the
  age column showing `hours ago` with the number cut off the front, and the title
  reading `tracker keepeı`. Four causes: `QLabel` clips instead of eliding (there
  is now a shared `ui_helpers.ElidedLabel`); the name shared one rich-text label
  with the platform tag, so the name was what disappeared; the full-text
  *changelog →* and *mark updated* buttons cost ~175px of a 430px row and are now
  a `→` and a `✓` below the widest tier; and the age column gets compact forms
  (`13h`, `4d`, `2w`, `3mo`) that fit whole, with the full phrase on hover.
- **An empty update badge no longer reserves space.** Its width floor was
  computed once per layout tier from whatever text happened to be there, so a
  badge that later emptied out kept holding ~59px — and the title paid for it,
  eliding beside an invisible label occupying a sixth of the bar.
- The Steam checker asked for `maxlength=1`, truncating every announcement body
  to a single character — invisible while only the title was read, and exactly
  what the detail view needed.
- **The visual baseline was guarding a screen users never see.** The rig grabbed
  dough's placeholder canvas rather than the app's own first screen, so the
  golden would have passed through any dashboard regression. Fixed upstream in
  dough, so every app built from it gets a baseline that tracks its real UI.

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

**The rule it lives by:** a card only ever shows a version a **real source
returned**. A check that can't reach a source keeps the last-known value and
says "couldn't check" — tracker keeper never invents a latest.

<!-- release-notes-end -->
