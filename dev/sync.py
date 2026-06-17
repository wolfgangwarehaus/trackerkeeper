#!/usr/bin/env python3
"""sync — pipe jellytoast refinements UP into the dough base.

dough was built by copying + genericizing jellytoast's shared modules, so the
two hold diverged copies. This is the door that propagates upstream refinements
(a blur fix, a chrome tweak, a new widget) from jellytoast into dough.

    python dev/sync.py --jellytoast ~/Projects/jellytoast            # report drift
    python dev/sync.py --jellytoast ~/Projects/jellytoast --apply    # update AUTO modules
    python dev/sync.py --jellytoast ~/Projects/jellytoast --record   # stamp synced_from = jellytoast HEAD

AUTO modules (pure lift): the transforms in shared.toml reproduce dough's copy
from jellytoast's, so drift is shown as a diff and ``--apply`` overwrites it
(you review + commit). MANUAL modules (genericized — ui_helpers, window): the
UPSTREAM diff since ``synced_from`` is shown so you port it by hand.

Direction is jellytoast → dough only (refinements bubble UP to the base). The
long-term plan (B) is to invert this — jellytoast imports dough — at which point
this door retires.
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
DOUGH_PKG = HERE.parent / "dough"
MANIFEST = HERE / "shared.toml"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    ).stdout


def _transformed(text: str, transforms: list) -> str:
    for t in transforms:
        text = text.replace(t["find"], t["replace"])
    return text


def _diff(cur: str, cand: str, label: str) -> str:
    return "".join(
        difflib.unified_diff(
            cur.splitlines(True),
            cand.splitlines(True),
            f"a/dough/{label}",
            f"b/dough/{label} (from jellytoast)",
        )
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jellytoast", required=True, type=Path, help="path to the jellytoast checkout")
    ap.add_argument("--apply", action="store_true", help="overwrite drifted AUTO modules")
    ap.add_argument("--record", action="store_true", help="stamp synced_from = jellytoast HEAD")
    args = ap.parse_args()

    m = tomllib.load(open(MANIFEST, "rb"))
    transforms = m.get("transform", [])
    authored = set(m.get("authored", []))
    manual = set(m.get("manual", []))
    overrides = m.get("source_override", {})
    synced_from = m.get("synced_from", "")

    jt = args.jellytoast.resolve()
    jt_pkg = jt / "jellytoast"
    if not jt_pkg.is_dir():
        print(f"error: {jt_pkg} not found — is --jellytoast a jellytoast checkout?", file=sys.stderr)
        return 2
    head = _git(jt, "rev-parse", "--short", "HEAD").strip()

    auto_drift, manual_drift = [], []
    for f in sorted(DOUGH_PKG.rglob("*.py")):
        rel = f.relative_to(DOUGH_PKG).as_posix()
        if rel in authored or "/assets/" in f.as_posix():
            continue
        src_rel = overrides.get(rel, rel)
        src = jt_pkg / src_rel
        if not src.exists():
            continue  # dough-original module with no upstream
        if rel in manual:
            d = (
                _git(jt, "diff", f"{synced_from}..HEAD", "--", f"jellytoast/{src_rel}")
                if synced_from
                else ""
            )
            if d.strip():
                manual_drift.append((rel, src_rel, d))
            continue
        cand = _transformed(src.read_text(), transforms)
        if cand != f.read_text():
            auto_drift.append((rel, _diff(f.read_text(), cand, rel)))
            if args.apply:
                f.write_text(cand)

    print(f"jellytoast HEAD: {head}   dough last synced: {synced_from or '(never)'}\n")

    if auto_drift:
        print(f"== AUTO modules drifted ({len(auto_drift)}) ==")
        for rel, d in auto_drift:
            print(f"\n--- {rel} ---\n{d or '(differs)'}")
        print(f"\n{'[applied — review + commit]' if args.apply else '(run with --apply to update)'}")
    else:
        print("AUTO modules: in sync ✓")

    if manual_drift:
        print(f"\n== MANUAL modules with upstream changes ({len(manual_drift)}) — port by hand ==")
        for rel, src_rel, d in manual_drift:
            print(f"\n--- {rel}  (upstream: jellytoast/{src_rel}) ---\n{d}")
    else:
        print("MANUAL modules: no upstream changes since last sync ✓")

    if args.record:
        MANIFEST.write_text(
            re.sub(r'synced_from = "[^"]*"', f'synced_from = "{head}"', MANIFEST.read_text())
        )
        print(f"\n[recorded synced_from = {head}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
