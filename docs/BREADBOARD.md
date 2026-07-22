# THE BREADBOARD — the board that tells the truth about your app

> The moat, stated once. dough's competitive audit (2026-07-21) found the delivery
> pipeline is table-stakes-plus (copyable in months) and the *defensible* position is
> the **combination** — and the two hardest-to-clone parts are the finished design
> system and **the breadboard**. This is the direction that makes the breadboard the
> moat. Synthesized from a 4-lens design panel; full provenance in the AI memory
> [[breadboard-moat-direction]].

## The thesis

The breadboard is a **trust instrument**: a live, git-tracked TOML window whose every
green mark is *detected from the real machine and the real internet* — a probed PyPI
name, a landed tag, a published release, a composited screenshot of the frosted window
— **never a box someone typed**. `deliver.py` already proved the principle that state
is DETECTED, never recorded, so it cannot drift or lie. The magic is extending that one
principle to the **entire board** and letting the maker *watch it happen*.

That is the moat: **a green you can't fake is a green a competitor can only draw, not
earn** — and it's the only thing that makes "hand an AI the keys to a store-bound
native app" a safe sentence to say.

## The signature moment (the demo, the README hero)

Delivery tab, frosted dark. Six channel rows sit grey. The maker types one line into the
note field on the GitHub row — "ship v0.1.0, PyPI + AUR" — and clicks **Ship it** (the
twin of the shipped "Wind down…"). That writes a request into `<slug>-breadboard.toml`.
In the terminal beside the window, the AI agent — already watching the file — says
"picking up: ship v0.1.0," runs `git tag && git push`, and surfaces the one step it must
never do for the maker: "review + publish → `gh release view v0.1.0 --web`." The maker's
hands leave the keyboard. **Nobody touches the window and it starts moving**: it
re-arms the existing `_ChannelProbe` on a timer, the GitHub row starts a live clock —
"building on Actions… 0:14." The maker clicks the one publish link. Then they just watch
PyPI's steps flip ▶→✓ and snap to **LIVE**, unfurling a fat green link:
`pip install <slug> · pypi.org/project/<slug> →`. Then AUR: `yay -S <slug> → LIVE`.
Freeze frame — logo, two real store commands, glowing green, "3 of 6 channels live."
*"I typed one sentence. The AI shipped my desktop app to the stores while I watched. I
never ran a build command."* Every green is a true probe result, not an animation of hope.

## The build ladder (next → fully magical)

Each item is grounded in substrate dough already has. **Start at 1; item 3 is the
MVP-of-magic — demoable the day it lands.**

1. **Stable item ids + omit-empty serializer** · *S · enabler.* Schema 1→2: a short
   stable `id` on every item at write; `save()` drops empty fields. Makes board history
   exact across commits and lets the agent reference `item <id>` unambiguously. The quiet
   enabler under everything below.
2. **The LIVE card** · *S · high.* Add `store_url` + `install_cmd` to each `Channel` in
   `deliver.py`. When a channel reaches all-✓, its steps collapse into a celebratory row:
   the real store URL as a big link + the one-line install command. This card *is* the
   screenshot (today LIVE just says "nothing to do").
3. **Launch mode: the self-refreshing board** · *M · signature · ← MVP-of-magic.* When a
   `v*` tag exists whose channels aren't all LIVE, the Delivery tab arms a QTimer that
   re-runs `_ChannelProbe` on a ~5s cadence with backoff, auto-stopping when everything's
   LIVE or idle. ✓s appear on their own as Actions builds; each flip fades green and
   stamps its real go-live wall-clock. The difference between a checklist and a movie.
4. **Ship it + the request queue** · *M · high.* Promote the single `agent_request` scalar
   into ordered `[[requests]]` (`text`/`by`/`date` → `done`+`evidence`). "Wind down…"
   becomes one of several one-click templates ("Ship v0.1.0," "Advance Delivery") + free
   text; the agent drains FIFO and stamps each. Removes the one-directive-at-a-time bottleneck.
5. **The ledger + green-flip receipt** · *M · high.* On LIVE, mint a permanent
   `[[shipped]]` entry: app + version + real public URL + first-shipped date (persisted —
   live detection goes stale offline). The row pulses green (restrained glow, not confetti);
   the receipt exports as a small PNG ship-card. "butterPDF is on the internet" is the
   biggest moment the tool ever shows.
6. **The "since you left" ribbon** · *M · signature.* On open, `git log --follow` the
   breadboard TOML, `git show <sha>:<path>` → `load()` each snapshot, diff item states
   between the maker's last-seen sha (stored in `~/.local/state`, never in git) and HEAD:
   "Since Saturday — the agent moved 4 cards to Done, you checked 2 ingredients, and PyPI
   went green." Off-thread, sha-cached, degrades gracefully. Why you open the board with
   your coffee even when nothing's shipping.
7. **Proof marks — checks the machine earns** · *L · signature.* Extend "detected, not
   asserted" *inward* to Baking. An `[item.proof]` sub-table; when the agent flips an item
   done, the board (in a QThread) launches the maker's real app under
   `DOUGH_TEST_BRIDGE=1` in a scoped ephemeral subprocess, drives it via the bridge
   (widgets addressable by dough's a11y names), runs `rig baseline`, captures a real
   compositor spectacle shot (never blur-blind `grab()`). A hollow "proofing…" tick turns
   solid green with a 120px thumbnail of the maker's own frosted window: "booted 1.4s ·
   frost composited · app_id ✓ · 0.3% drift." A proofed check looks distinct from a
   hand-ticked one.
8. **The Bake gate + staleness + proof-as-CI** · *M · high.* One honest readiness verdict
   joining every ground-truth source: rig baseline green + `bake --check`/ruff/pytest clean
   + zero open HIGH Improvements + Delivery preconditions. The `git tag` control stays
   rendered-but-inert until green. Proofs store the commit they were earned against and go
   **stale** (amber, gate → red) when `git diff <proof-commit>..HEAD` touches the app
   package. A headless `dough breadboard --proof` runs the same probes in `release.yml`, so
   local trust instrument and pipeline gate share code and can't disagree.

## Why uncloneable

Every green is **collateralized by the whole owned loop** — the finished frosted app, the
compositor rig with visual goldens, the live 8-channel detector, the in-process test
bridge, the co-written file — and no feature works with a part missing. A **packaging
tool** is a CLI that writes files and exits: no window to photograph, no frost to
composite, no live per-channel LIVE detection, no second party to hand work to — it can
emit a `.deb` but structurally cannot show you the *moment* it went live, because it has
no board to show it on. An **AI web-builder** owns a chat box and a preview iframe: no
native identity to probe, no eight store channels, no exec bridge into a real Qt process,
no git-tracked TOML two separate processes mutate — its state is a transcript that
evaporates and never reaches a store. To clone a *single* proofed check, either would
first have to rebuild the entire substrate — i.e. rebuild dough. The launch animation is
easy to copy; **the thing that makes the animation *true* is the whole product.** And
because it's fork-and-own, the contract ships inside the maker's own repo as TOML + a
documented socket — no vendor to deprecate it, works with any agent.

## Traps to avoid (the discipline that keeps it real)

- **Vanity gamification.** No streaks, points, badges, "momentum scores" — a serious maker
  closes that. Every event is a real thing with a real byline and, for ships, a real URL.
  "PyPI went green," never "you earned 50 points."
- **A ✓ that isn't detected.** The cardinal sin. The timer reflects only true probe
  results; `?` stays `?`; squatted reads conflict, offline reads unknown, never a false
  LIVE. A manual uncheck is a decision the probe must not re-check.
- **Proofing that's slow, blind, or a footgun.** On-demand / on-agent-write, cached against
  the commit, cancellable. Degrade to `?` where the probe can't run (CI, headless, macOS
  without KDE legs) exactly as `rig.probe` declines — a proof flashing RED where it can't
  *see* is worse than none. Scoped ephemeral subprocess with guaranteed teardown (a proof
  that leaves the bridge armed is a security hole). Spectacle shot, never `grab()`.
- **Overclaiming.** A proof proves only what it measures. Keep proof *kind* legible (booted
  vs. baseline-clean vs. driven-interaction); never let a boot-proof masquerade as "it works."
- **Schema creep.** Don't turn a skimmable TOML into a bug tracker nobody hand-edits — the
  moment it stops being plain-text-editable, "the file IS the API" breaks. The omit-empty
  serializer (item 1) is load-bearing.
- **The "by Friday" claim.** Honest only for the fast lane (GitHub/PyPI/AUR/winget). MSIX
  (Partner Center + WACK) and macOS ($99/yr Apple, notarization) run a store-review clock in
  days-to-weeks; the human-owned account/publish steps can't be automated away. Demo the
  fast channels; keep the board candid about the slow ones.
- **Motion tone.** The frosted system is restrained — launch sequences and green-flips glow
  and fade, never bounce and sparkle.
