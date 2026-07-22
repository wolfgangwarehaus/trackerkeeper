# Delivery helpers — design + v1 (C1)

> **STATUS: v1 BUILT, 2026-07-03** — `trackerkeeper/deliver.py` (`trackerkeeper-deliver` /
> `python -m trackerkeeper.deliver`), tests in `tests/test_deliver.py`. The open
> questions below were resolved as proposed (separate verb; helper-only
> selection; interactive-only). One design addition earned in the first real
> run: **name-ownership detection** — a channel-namespace probe compares the
> found project's URLs to our repo, because a squatted name must read
> **NAME CONFLICT**, never LIVE. (Found live immediately: PyPI `trackerkeeper` is a
> 2015-era third-party package — see the C2 note in `docs/TODO.md`. PyPI
> `butterpdf` and AUR `trackerkeeper`/`butterpdf` are free.)

## The problem

The Delivery machinery exists (the channel matrix, `release.yml`, the dormant
per-channel workflows gated on secrets) but the **guided activation doesn't**:
getting from "built app" to "live on a channel" today means reading
`docs/RELEASING.md` + `docs/BAKING.md` §5 and reverse-engineering which
accounts, secrets, and clicks each channel needs. That's exactly the part a
maker (person + AI) hits once per channel and never remembers.

And per the **Improvements loop**, delivery isn't one-shot: every lap after
launch is a RE-delivery (bump → changelog → re-release → store re-review), so
the helpers must know the difference between *first activation* and *an
update lap*.

## The shape: `deliver` — a stateful, re-entrant walkthrough

A new shared module `trackerkeeper/deliver.py` (+ console script `{slug}-deliver`,
synced to loaves like `bake`):

    butterpdf-deliver              # the status board: every channel, its state
    butterpdf-deliver pypi         # walk THIS channel's next steps
    butterpdf-deliver --release    # the update lap: bump → notes → tag → watch

### State comes from reality, not a state file

Each channel's state is **detected**, never recorded, so the walkthrough is
idempotent and can't drift:

| Signal | How it's read |
| --- | --- |
| version/tag exists | `git tag` / `setuptools-scm` |
| release published | `gh release view` |
| channel secret set | `gh secret list` (names only — never values) |
| PyPI project live | `https://pypi.org/pypi/{name}/json` |
| AUR package live | `https://aur.archlinux.org/rpc/v5/info/{name}` |
| winget merged | the winget-pkgs manifest path |
| workflow green | `gh run list --workflow <channel>.yml` (ALL workflows rule) |

The only stored bit is the maker's **channel selection** (which channels this
app targets), which belongs in the metadata sidecar as
`delivery_channels = [...]` — Ingredients-phase data, next to everything else.

### A channel = an ordered list of steps

Each step: `id`, `title`, `detect() -> done/pending/blocked`, `guide()` (what
to do — the exact command, URL, or console path), and `kind` (`local` — the
helper can run it; `account` — a human creates something; `secret` — a human
pastes `gh secret set NAME`; `publish` — a human clicks publish). The helper
never performs `account`/`secret`/`publish` steps itself — it detects them and
prints the exact action. AI-friendly output is the point: a maker's agent can
read the board and drive the `local` steps, and knows precisely what to hand
back to the human.

### v1 scope: Linux-first, butterPDF-led

Channels in v1 (what butterPDF's C3 actually needs):

1. **github-release** (deb + AppImage + wheel ride on it): tag → draft →
   publish → container smokes green.
2. **pypi**: pending-publisher setup (prints the exact 4 values) → publish →
   verify the JSON endpoint.
3. **aur**: ssh keygen → AUR account → `gh secret set AUR_SSH_PRIVATE_KEY` →
   verify the RPC endpoint.

Windows (Inno/winget), MSIX, macOS ship as **stubbed boards** (steps listed,
detection where free, marked "needs Windows/macOS/accounts") — the structure
is there, activation follows hardware/accounts.

### The update lap (`--release`)

When every selected channel is already live, `deliver` switches from
activation to the Improvements lap:

1. changelog check — `docs/CHANGELOG.md` has an entry newer than the last tag
   (refuses to proceed on an empty lap);
2. version bump = the tag (nothing to edit — reprints the settled rule);
3. `git tag vX.Y.Z && git push origin vX.Y.Z` → watch `release.yml`;
4. publish the draft (human) → watch the fan-out (pypi/aur/winget jobs);
5. per-channel post-checks (PyPI JSON shows the new version, AUR bumped,
   store re-review reminders for MSIX/macOS).

## What C1 is NOT

- Not a TUI/GUI — plain, agent-readable console output (the visual setup
  belongs to the later Ingredients tooling).
- Not a rewrite of release.yml — the helpers *drive and observe* the existing
  machinery, never duplicate it.
- Not autonomous account creation — humans own accounts, secrets, and the
  publish click; the helper makes each such step a 30-second paste.

## Open questions (for the review)

1. `deliver` as a separate console script vs a `bake deliver` subcommand?
   (Proposal: separate — bake renders, deliver ships; the vocabulary split.)
2. Should `delivery_channels` gate `release.yml` jobs too (skip unselected
   channels), or stay helper-only in v1? (Proposal: helper-only v1.)
3. Does the status board belong in CI (a scheduled "delivery health" job)?
   (Proposal: later — v1 is interactive.)
