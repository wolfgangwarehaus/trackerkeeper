# Wind-down policy

Run this at the **end of every working session** (when you — or an AI agent — are stopping,
checkpointing, or pausing). The goal: the next session, or a fresh machine, or a different
person, resumes with **zero ramp-up**, from a **known-good state**. A long session's context
lives only in the conversation; the wind-down makes it durable + actionable.

## The checklist (in order)

1. **Land it green.** Every repo you touched passes `ruff check`, `pytest`, and
   `<app> bake --check` — and after pushing, **check ALL GitHub workflows** (`gh run list`),
   not just the `CI` check: a workflow-file parse error (e.g. a `secrets` reference inside
   an `if:`) fails as a separate 0-second run that a green `CI` badge hides. Never wind
   down red — leave unfinished work behind a clear marker (an `xfail`, or a `TODO` with
   the trigger condition), not broken.

2. **Update the handoff doc** — `docs/TODO.md`, the single "pick up here next":
   - current state in 1–2 lines,
   - the **prioritized resume sequence** (the exact next 1–3 steps),
   - then the standing backlog.
   Lead with what to do *next*, not a history dump.

3. **Update the project notes** — the cross-session facts (status, the decisions made + their
   *why*, the next step). For this project those live in the AI's memory + `docs/BACKPORT.md`
   + `BRIEF.md`. Use absolute dates. Don't duplicate what git/the code already records.

4. **Reconcile the task list.** Mark done, prune stale, add the concrete next-session items.

5. **Commit + push.** Commit the docs/handoff with a clear message and **push** so the
   handoff survives a machine change. Call out any repo that's local-only (no remote yet).

6. **Leave a resume pointer.** End with one line: *"next session, start at: &lt;X&gt;."*

## Why each step

- **Green** means the next session debugs *new* work, not yesterday's.
- **One handoff doc** beats scattered notes — there's a single place to look.
- **The "why"** behind a decision is the part that's expensive to reconstruct later.
- **Push** is what turns "saved on my laptop" into "the team/the next machine has it."
- **The resume pointer** is the difference between 30 seconds and 30 minutes of re-orientation.
