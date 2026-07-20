#!/usr/bin/env python3
"""sync_loaf — push dough base improvements DOWN into an existing loaf (fork).

dough is a fork-and-own starter: ``dough new`` stamps a new app by renaming the
package and whole-word-replacing dough's identity (slug / org / owner). That
makes the loaf a *diverged copy* of dough's shared modules. This is the door
that carries later dough improvements back into that fork — the mirror of
``dev/sync.py`` (which pipes jellytoast refinements UP into dough).

    python dev/sync_loaf.py --loaf ~/Projects/butterPDF            # report drift
    python dev/sync_loaf.py --loaf ~/Projects/butterPDF --apply    # write AUTO + NEW modules
    python dev/sync_loaf.py --loaf ~/Projects/butterPDF --record   # stamp synced_from = dough HEAD
    python dev/sync_loaf.py --loaf ~/Projects/butterPDF --init     # seed the loaf's dough-sync.toml

How a loaf module is reproduced from dough's: take dough's current file and apply
the SAME whole-word identity replace ``dough new`` did (dough→slug, org, owner).
For an AUTO module (pure shared code) that reproduces the loaf's copy exactly, so
``--apply`` overwrites it to bring the fork up to date. Categories:

  * AUTO   — shared module in both; transformed-dough differs from the loaf copy
             → offer to overwrite (``--apply``).
  * NEW    — dough has a shared module the loaf lacks (e.g. a package added after
             the fork) → offer to add it, transformed (``--apply``).
  * MANUAL — a module the fork hand-customized (listed in dough-sync.toml). Never
             overwritten; dough's upstream diff since ``synced_from`` is shown so
             the maker ports it by hand.
  * authored / in-sync — the fork's own files (listed) and unchanged modules: skipped.

The per-loaf manifest ``<loaf>/dough-sync.toml`` records ``synced_from`` (the
dough commit last reconciled) + the fork's ``authored`` / ``manual`` file lists.
Identity (slug/org/owner) is read from each side's ``[tool.dough.metadata]``.
"""

from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOUGH_ROOT = HERE.parent
DOUGH_PKG = DOUGH_ROOT / "dough"
# Shared text suffixes carried down (code + the KWin effect template assets). The
# brand SVG is intentionally excluded — a fork owns its own brand (name-diverged).
_SYNC_SUFFIXES = {".py", ".json", ".js"}
# Generated / not-shared files that live in the package dir but must never sync.
_SKIP_NAMES = {"_version.py"}  # setuptools-scm output, gitignored, per-build


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    ).stdout


def _git_ok(repo: Path, *args: str) -> bool:
    """True iff git exits 0 — for probes where empty stdout is ambiguous
    (a failed `git diff bad-rev..HEAD` is empty too, which would read as
    'no upstream changes ✓' — exactly the silent blind spot this tool exists
    to prevent)."""
    return (
        subprocess.run(["git", "-C", str(repo), *args], capture_output=True).returncode == 0
    )


def _identity(pyproject: Path) -> tuple[str, str, str]:
    """(slug, org, owner) from a checkout's ``[tool.<pkg>.metadata]`` sidecar.
    ``dough new`` renames the tool-table key to the fork's slug, so scan
    ``[tool.*]`` for the metadata table rather than assuming ``tool.dough``."""
    tool = tomllib.load(open(pyproject, "rb")).get("tool", {})
    for section in tool.values():
        meta = section.get("metadata") if isinstance(section, dict) else None
        if isinstance(meta, dict) and "app_slug" in meta:
            return meta["app_slug"], meta["org_slug"], meta["github_owner"]
    raise KeyError(f"no [tool.<pkg>.metadata] with app_slug in {pyproject}")


def _make_transform(old: tuple[str, str, str], new: tuple[str, str, str]):
    """Whole-word replace mirroring ``dough new`` (owner, org, slug order), plus
    each pair's UPPER_SNAKE env-var prefix (``DOUGH_*`` → ``BUTTERPDF_*`` — ``_``
    is a word char, so ``\\b`` alone never reaches it). Same patterns as
    scaffold._replace_in_tree, so an AUTO module renders byte-for-byte identical
    to what the fork was stamped with; keep the two in step."""
    old_slug, old_org, old_owner = old
    new_slug, new_org, new_owner = new
    pairs = [(old_owner, new_owner), (old_org, new_org), (old_slug, new_slug)]
    patterns = [
        (re.compile(rf"\b{re.escape(o)}\b"), n) for o, n in pairs if o != n
    ]
    patterns += [
        (re.compile(rf"\b{re.escape(o.upper())}_"), f"{n.upper()}_")
        for o, n in pairs
        if o != n and o.upper() != n.upper()
    ]
    # …and the lowercase_snake prefix (``dough_<code>.qm`` i18n catalog
    # basenames → ``butterpdf_<code>.qm``) — found the hard way on the
    # 2026-07-20 butterPDF sync, where the i18n module shipped looking
    # for dough_*.qm inside butterpdf.i18n.
    patterns += [
        (re.compile(rf"\b{re.escape(o.lower())}_"), f"{n.lower()}_")
        for o, n in pairs
        if o != n and o.lower() != n.lower()
    ]
    # The degenerate-identity org repair (mirrors scaffold._identity_org_repairs):
    # when dough's org == owner but the loaf's differ, the generic replace stamps
    # the OWNER into identity.py's org-semantic lines — re-stamp them so the
    # transform reproduces what `dough new` + its step-4b repair produced.
    repairs: list[tuple[str, str]] = []
    if old_org == old_owner and new_org != new_owner:
        repairs = [
            (f'_org = "{new_owner}"', f'_org = "{new_org}"'),
            ("_owner: str | None = None", f'_owner: str | None = "{new_owner}"'),
        ]

    def transform(text: str) -> str:
        for pattern, repl in patterns:
            text = pattern.sub(repl, text)
        for old_lit, new_lit in repairs:
            text = text.replace(old_lit, new_lit)
        return text

    return transform


def _diff(cur: str, cand: str, rel: str, slug: str) -> str:
    return "".join(
        difflib.unified_diff(
            cur.splitlines(True),
            cand.splitlines(True),
            f"a/{slug}/{rel}",
            f"b/{slug}/{rel} (from dough)",
        )
    )


def _init_manifest(loaf: Path, manifest: Path, slug: str) -> int:
    if manifest.exists():
        print(f"{manifest} already exists — not overwriting.", file=sys.stderr)
        return 1
    head = _git(DOUGH_ROOT, "rev-parse", "--short", "HEAD").strip()
    manifest.write_text(
        f'''# dough→loaf sync manifest (see dough/dev/sync_loaf.py). Lives in the loaf.
# Records the dough base relationship for `python dev/sync_loaf.py --loaf .`.

# The dough commit this loaf was last reconciled against. `--record` stamps it.
# Seeded to dough HEAD at init; set it to the commit you actually forked from if
# you want the first sync to surface everything dough changed since.
synced_from = "{head}"

# Files (relative to the {slug}/ package dir) the fork OWNS — net-new app code or
# modules it fully rewrote. Sync never reads or writes these.
authored = [
]

# Files derived from dough but hand-customized. Sync shows dough's upstream diff
# since `synced_from` so you port changes by hand (never blind-overwrites).
manual = [
]
''',
        encoding="utf-8",
    )
    print(f"seeded {manifest} (synced_from = {head}). Curate authored/manual, then re-run.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--loaf", required=True, type=Path, help="path to the loaf (fork) checkout")
    ap.add_argument("--apply", action="store_true", help="write drifted AUTO + NEW modules into the loaf")
    ap.add_argument("--record", action="store_true", help="stamp the loaf's synced_from = dough HEAD")
    ap.add_argument("--init", action="store_true", help="seed the loaf's dough-sync.toml and exit")
    args = ap.parse_args()

    loaf = args.loaf.resolve()
    loaf_pyproject = loaf / "pyproject.toml"
    if not loaf_pyproject.is_file():
        print(f"error: {loaf_pyproject} not found — is --loaf a loaf checkout?", file=sys.stderr)
        return 2
    slug, org, owner = _identity(loaf_pyproject)
    loaf_pkg = loaf / slug
    if not loaf_pkg.is_dir():
        print(f"error: package dir {loaf_pkg} not found", file=sys.stderr)
        return 2

    manifest = loaf / "dough-sync.toml"
    if args.init:
        return _init_manifest(loaf, manifest, slug)
    if not manifest.is_file():
        print(f"error: {manifest} not found — run with --init first.", file=sys.stderr)
        return 2

    m = tomllib.load(open(manifest, "rb"))
    synced_from = m.get("synced_from", "")
    authored = set(m.get("authored", []))
    manual = set(m.get("manual", []))

    # A stale/garbage synced_from makes every `git diff synced_from..HEAD` exit
    # 128 with EMPTY output — indistinguishable from "no upstream changes" if
    # trusted blind. Fail loud instead.
    if synced_from and not _git_ok(DOUGH_ROOT, "cat-file", "-e", f"{synced_from}^{{commit}}"):
        print(
            f"error: synced_from = {synced_from!r} does not resolve to a commit in "
            f"{DOUGH_ROOT} — fix the loaf's dough-sync.toml (MANUAL reports would "
            "silently read as clean).",
            file=sys.stderr,
        )
        return 2

    transform = _make_transform(_identity(DOUGH_ROOT / "pyproject.toml"), (slug, org, owner))
    head = _git(DOUGH_ROOT, "rev-parse", "--short", "HEAD").strip()

    auto_drift, new_mods, manual_drift = [], [], []
    for f in sorted(DOUGH_PKG.rglob("*")):
        if not f.is_file() or f.suffix not in _SYNC_SUFFIXES:
            continue
        rel = f.relative_to(DOUGH_PKG).as_posix()
        if "/__pycache__/" in f"/{rel}" or f.name in _SKIP_NAMES or rel in authored:
            continue
        dest = loaf_pkg / rel
        if rel in manual:
            d = (
                _git(DOUGH_ROOT, "diff", f"{synced_from}..HEAD", "--", f"dough/{rel}")
                if synced_from
                else ""
            )
            if d.strip():
                manual_drift.append((rel, d))
            continue
        cand = transform(f.read_text(encoding="utf-8"))
        if not dest.exists():
            new_mods.append((rel, cand, dest))
            continue
        if cand != dest.read_text(encoding="utf-8"):
            auto_drift.append((rel, _diff(dest.read_text(encoding="utf-8"), cand, rel, slug), cand, dest))

    if args.apply and (auto_drift or new_mods):
        # Never clobber uncommitted loaf work: an edit to a shared module not
        # yet promoted to `manual` would be overwritten UNRECOVERABLY (git can
        # restore committed clobbers; it can't restore these).
        targets = [dest for _rel, _d, _cand, dest in auto_drift] + [
            dest for _rel, _cand, dest in new_mods
        ]
        if _git_ok(loaf, "rev-parse", "--is-inside-work-tree"):
            dirty = _git(
                loaf, "status", "--porcelain", "--", *[str(t) for t in targets]
            ).strip()
            if dirty:
                print(
                    "error: --apply refused — these sync targets have uncommitted "
                    f"changes in the loaf:\n{dirty}\n"
                    "Commit/stash them (or promote the files to `manual` in "
                    "dough-sync.toml) and re-run.",
                    file=sys.stderr,
                )
                return 2
        for _rel, _d, cand, dest in auto_drift:
            dest.write_text(cand, encoding="utf-8")
        for _rel, cand, dest in new_mods:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(cand, encoding="utf-8")

    print(f"dough HEAD: {head}   loaf '{slug}' last synced: {synced_from or '(never)'}\n")

    if auto_drift:
        print(f"== AUTO modules drifted ({len(auto_drift)}) ==")
        for rel, d, _cand, _dest in auto_drift:
            print(f"\n--- {rel} ---\n{d or '(differs)'}")
        print(f"\n{'[applied — review + commit in the loaf]' if args.apply else '(run with --apply to update)'}")
    else:
        print("AUTO modules: in sync ✓")

    if new_mods:
        verb = "added" if args.apply else "would add"
        print(f"\n== NEW in dough — not in the loaf ({len(new_mods)}) — {verb} ==")
        for rel, _cand, _dest in new_mods:
            print(f"  + {slug}/{rel}")
        if not args.apply:
            print("(run with --apply to add them)")

    if manual_drift:
        print(f"\n== MANUAL modules with upstream changes ({len(manual_drift)}) — port by hand ==")
        for rel, d in manual_drift:
            print(f"\n--- {slug}/{rel}  (upstream: dough/{rel}) ---\n{d}")
    else:
        print("\nMANUAL modules: no upstream changes since last sync ✓")

    if args.record:
        manifest.write_text(
            re.sub(r'synced_from = "[^"]*"', f'synced_from = "{head}"', manifest.read_text())
        )
        print(f"\n[recorded synced_from = {head} in {manifest}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
