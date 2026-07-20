"""``dough new`` — scaffold a fresh OWNED app from this dough checkout.

``dough-new <slug> --display "My App" --org <owner> [--summary "…"]`` turns THIS
clone of dough into an owned ``<slug>`` app: it renames the package, rewrites every
dough identity reference, mints a fresh installer id, strips dough's own dev
scaffolding, re-renders the packaging tree, and leaves the repo green
(``pytest`` + ``<slug> bake --check``).

It is **destructive and in-place** — run it on a fresh clone you intend to own
(docs/PHILOSOPHY.md: "fork and own"). This is the entry verb for *building with
dough*: the one command from a dough checkout to a real app repo.

Identity is centralized (the seam + the ``[tool.dough.metadata]`` sidecar), so the
rewrite is a whole-word identity replace (old slug/org/owner → new) plus the brand
asset rename, the display-name + GUID fixes, and a re-bake. Descriptive prose in the
sidecar (long_description, feature_cards) is slug-substituted, not rewritten — the
maker edits it during Baking.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from dough import metadata

# dough's own dev scaffolding — a fork is an app, not the base, so these go.
_STRIP = ["dev", "docs/SYNC.md", "docs/ROADMAP.md", "docs/TODO.md"]
# text suffixes whose identity references get rewritten.
_TEXT_SUFFIXES = {".py", ".toml", ".md", ".yml", ".yaml", ".j2", ".svg", ".cfg", ".ini", ".txt", ".sh"}
_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "venv", "dist", "build"}


def _run(cmd: list[str], cwd: Path, **kw):
    return subprocess.run(cmd, cwd=str(cwd), text=True, **kw)


def _git(root: Path) -> bool:
    return (root / ".git").is_dir()


def _move(root: Path, src: str, dst: str) -> None:
    if _git(root):
        _run(["git", "mv", src, dst], root, check=True)
    else:
        (root / src).rename(root / dst)


def _remove(root: Path, rel: str) -> None:
    target = root / rel
    if not target.exists():
        return
    if _git(root):
        # -f: the rendered-packaging clear runs after the content-replace, so some
        # targets have local modifications git rm would otherwise refuse to drop.
        _run(["git", "rm", "-rfq", "--", rel], root, check=True)
    elif target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()


def _text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(root).parts
        if any(d in _SKIP_DIRS for d in parts):
            continue
        if path.suffix.lower() in _TEXT_SUFFIXES or path.name == ".gitignore":
            yield path


def _replace_in_tree(root: Path, pairs: list[tuple[str, str]]) -> None:
    """Whole-word replace each (old → new) across every text file, plus each
    pair's UPPER_SNAKE env-var prefix (``DOUGH_*`` → ``BUTTERPDF_*``) — ``_``
    is a word character, so the ``\\b`` word pattern alone never reaches it.
    Mirrored by dev/sync_loaf.py ``_make_transform``; keep the two in step."""
    patterns = [(re.compile(rf"\b{re.escape(old)}\b"), new) for old, new in pairs if old != new]
    patterns += [
        (re.compile(rf"\b{re.escape(old.upper())}_"), f"{new.upper()}_")
        for old, new in pairs
        if old != new and old.upper() != new.upper()
    ]
    # …and the lowercase_snake prefix (``dough_<code>.qm`` i18n catalog
    # basenames). Mirrored in dev/sync_loaf.py — keep in step.
    patterns += [
        (re.compile(rf"\b{re.escape(old.lower())}_"), f"{new.lower()}_")
        for old, new in pairs
        if old != new and old.lower() != new.lower()
    ]
    if not patterns:
        return
    for path in _text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new = text
        for pattern, repl in patterns:
            new = pattern.sub(repl, new)
        if new != text:
            path.write_text(new, encoding="utf-8")


def _sub_in_file(path: Path, replacements: list[tuple[str, str]]) -> None:
    """Literal substring replace (each old → new) in one file."""
    text = path.read_text(encoding="utf-8")
    for old, new in replacements:
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


def _identity_org_repairs(
    old_org: str, old_owner: str, new_org: str, new_owner: str
) -> list[tuple[str, str]]:
    """Repairs for identity.py after the whole-word replace, for the DEGENERATE
    case: dough's own org and owner coincide ("wolfgangwarehaus"), so the
    replace cannot tell org-sites from owner-sites — owner runs first, so every
    coincident literal became the OWNER. When a fork separates the two, re-stamp
    the org-semantic ``_org`` and pin ``_owner`` explicitly (it defaults to
    tracking ``org``, which would now be wrong). Mirrored by
    dev/sync_loaf.py ``_make_transform``; keep the two in step."""
    if old_org != old_owner or new_org == new_owner:
        return []
    return [
        (f'_org = "{new_owner}"', f'_org = "{new_org}"'),
        ("_owner: str | None = None", f'_owner: str | None = "{new_owner}"'),
    ]


def _scaffold(root: Path, slug: str, display: str, new_org: str, new_owner: str, summary: str | None) -> None:
    sidecar = metadata.load()
    old_slug = sidecar["app_slug"]
    old_org = sidecar["org_slug"]
    old_owner = sidecar["github_owner"]
    old_summary = sidecar["summary"]
    old_guid = sidecar["store_secrets_of_record"]["inno_appid_guid"]

    # Read the loaf AGENTS.md template BEFORE the strip (it lives in dev/, which
    # goes) — it's written to the root AFTER the identity replace, so its prose
    # about dough-the-base survives the whole-word dough→slug rewrite.
    agents_tpl_path = root / "dev" / "AGENTS.loaf.md"
    agents_tpl = agents_tpl_path.read_text(encoding="utf-8") if agents_tpl_path.is_file() else None

    # 1. strip dough's own dev scaffolding.
    for rel in _STRIP:
        _remove(root, rel)

    # 2. rename the package dir + the brand asset.
    _move(root, old_slug, slug)
    old_asset = f"{slug}/assets/{old_slug}.svg"
    if (root / old_asset).is_file():
        _move(root, old_asset, f"{slug}/assets/{slug}.svg")

    # 3. whole-word identity replace across the tree (owner first — it's a superstring
    #    of org when they coincide, but escaped \b keeps them distinct anyway).
    _replace_in_tree(root, [(old_owner, new_owner), (old_org, new_org), (old_slug, slug)])

    # 3.5 the fork's AGENTS.md — the AI front door. dough's own copy talks about
    #     building the BASE (and the replace above just mangled it anyway); the
    #     loaf gets the app-oriented version from the template read in before
    #     the strip.
    if agents_tpl:
        (root / "AGENTS.md").write_text(
            agents_tpl.replace("{{slug}}", slug).replace("{{display}}", display),
            encoding="utf-8",
        )

    # 4. fix the fields the whole-word replace can't: the display name (it was set to
    #    the slug by the slug-replace), a freshly-minted immutable installer GUID, and
    #    (if given) the summary — which lives in two synced places ([project] +sidecar).
    pyproject = root / "pyproject.toml"
    fixes: list[tuple[str, str]] = []
    # The PyPI distribution name: dough publishes as "dough-base" (the bare name
    # is squatted on PyPI), and the whole-word replace above just turned it into
    # "{slug}-base" — a fork's distribution IS its slug, so pin it back.
    fixes.append((f'name = "{slug}-base"', f'name = "{slug}"'))
    if display != slug:
        fixes.append((f'display_name = "{slug}"', f'display_name = "{display}"'))
        _sub_in_file(root / slug / "identity.py", [(f'_display_name = "{slug}"', f'_display_name = "{display}"')])
        # the only test that pins the literal display value
        ti = root / "tests" / "test_identity.py"
        if ti.is_file():
            _sub_in_file(ti, [(f'identity.display_name() == "{slug}"', f'identity.display_name() == "{display}"')])
    if old_guid:
        fixes.append((f'inno_appid_guid = "{old_guid}"', f'inno_appid_guid = "{str(uuid.uuid4()).upper()}"'))
    if summary:
        fixes.append((f'description = "{old_summary}"', f'description = "{summary}"'))
        fixes.append((f'summary = "{old_summary}"', f'summary = "{summary}"'))
    # 4b. the degenerate-identity org repair (see _identity_org_repairs): the
    #     sidecar's org_slug and identity.py's _org/_owner got the OWNER stamped
    #     into them when org ≠ owner — re-stamp the org-semantic sites. The
    #     projections gate (tests/test_metadata.py) holds the two sides equal.
    if old_org == old_owner and new_org != new_owner:
        fixes.append((f'org_slug = "{new_owner}"', f'org_slug = "{new_org}"'))
        _sub_in_file(
            root / slug / "identity.py",
            _identity_org_repairs(old_org, old_owner, new_org, new_owner),
        )
    if fixes:
        _sub_in_file(pyproject, fixes)

    # 5. clear the OLD rendered packaging — its filenames carry the old identity
    #    (io.github.…dough.desktop), which the content-replace can't touch, so the
    #    re-bake's new names would otherwise leave orphans. templates/ stays.
    pkg = root / "packaging"
    if pkg.is_dir():
        for path in sorted(pkg.rglob("*"), reverse=True):
            rel = path.relative_to(root)
            if "templates" in rel.parts:
                continue
            if path.is_file():
                _remove(root, str(rel))

    # 6. re-render the packaging tree under the new identity (a fresh subprocess so it
    #    imports the RENAMED package), then validate.
    print(f"  rendering {slug}'s packaging…")
    _run([sys.executable, "-m", f"{slug}.bake"], root, check=True, capture_output=True)


def _validate(root: Path, slug: str) -> int:
    print("  validating (bake --check + pytest)…")
    check = _run([sys.executable, "-m", f"{slug}.bake", "--check"], root, capture_output=True)
    if check.returncode != 0:
        print("FAILED: bake --check\n" + check.stdout + check.stderr, file=sys.stderr)
        return 1
    tests = _run([sys.executable, "-m", "pytest", "-q"], root, capture_output=True)
    if tests.returncode != 0:
        print("FAILED: pytest\n" + tests.stdout[-3000:] + tests.stderr[-2000:], file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dough-new",
        description="Scaffold a fresh OWNED app from this dough checkout (destructive, in-place).",
    )
    parser.add_argument("slug", help="the new app's package slug — a lowercase identifier (e.g. butterpdf)")
    parser.add_argument("--display", help="human display name (default: the slug)")
    parser.add_argument("--org", help="org / vendor slug (default: keep dough's)")
    parser.add_argument("--owner", help="GitHub owner for the reverse-DNS app-id (default: --org)")
    parser.add_argument("--summary", help="one-line app summary")
    parser.add_argument("--root", type=Path, default=None, help="repo root (default: this checkout)")
    args = parser.parse_args(argv)

    slug = args.slug
    if not re.fullmatch(r"[a-z][a-z0-9_]*", slug):
        parser.error(f"slug must be a lowercase Python identifier (got {slug!r})")
    root = (args.root or metadata._find_pyproject().parent).resolve()

    sidecar = metadata.load()
    if slug == sidecar["app_slug"]:
        parser.error(f"this checkout is already {slug!r}")
    if not (root / sidecar["app_slug"]).is_dir():
        parser.error(f"no package dir {sidecar['app_slug']}/ at {root} — run inside a dough checkout")

    display = args.display or slug
    new_org = args.org or sidecar["org_slug"]
    new_owner = args.owner or new_org

    print(f"dough new → scaffolding '{slug}' (display '{display}', org '{new_org}') in {root}")
    _scaffold(root, slug, display, new_org, new_owner, args.summary)
    rc = _validate(root, slug)
    if rc == 0:
        print(f"✓ {slug} is ready — owned, rendered, and green. Build your app.")
    return rc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
