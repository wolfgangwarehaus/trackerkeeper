"""``dough bake`` — render the packaging tree from the one metadata source.

The oven half of the baking phase (docs/BAKING.md §2): walk
``packaging/templates/**/*.j2``, render each template's BODY *and its filename*
(filenames carry ``{{ app_id_base }}`` etc.) from :func:`dough.metadata.context`,
and write the result under ``packaging/``. None of the manifests is hand-authored.

The verify half is :func:`check`: re-render into memory and diff against the
committed files — reporting a hand-edit, a stale render, a missing file, AND an
orphan (a committed file no template produces). A CI gate (``dough bake --check``,
mirrored by ``tests/test_bake.py``) fails the build on any drift. jellytoast
*lints* its manifests after the fact; dough regenerates and proves nothing drifted.

Jinja2 is a build-time-only dependency (the ``bake`` extra) — the shipped app
never imports it. ``StrictUndefined`` makes a template that references a missing
context key a hard error, so a template/metadata mismatch fails loudly at render.
"""

from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path

from dough import metadata

TEMPLATES_SUBDIR = "templates"


class BakeError(RuntimeError):
    """A render/verify failure (missing engine, colliding outputs, …)."""


def _repo_root() -> Path:
    """The repo root — the dir holding pyproject.toml (and packaging/)."""
    return metadata._find_pyproject().parent


def _environment(templates_dir: Path):
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined
    except ImportError as exc:  # pragma: no cover — exercised only without the extra
        raise BakeError(
            "dough bake needs Jinja2 — install the bake extra: pip install 'dough[bake]'"
        ) from exc
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        undefined=StrictUndefined,  # a missing context key is a hard error
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,  # shell / desktop / XML — escape per-field with |e
    )


def _committed_files(packaging_dir: Path) -> list[Path]:
    """Every committed (non-source) file under ``packaging/`` — skips the
    ``templates/`` sources and any stray ``__pycache__``."""
    out: list[Path] = []
    for path in sorted(packaging_dir.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(packaging_dir).parts
        if TEMPLATES_SUBDIR in parts or "__pycache__" in parts:
            continue
        out.append(path)
    return out


def render(packaging_dir: Path, ctx: dict | None = None) -> dict[str, str]:
    """Render every ``*.j2`` under ``<packaging>/templates`` and return
    ``{output_relpath: rendered_text}`` — the output path has the rendered
    filename (``{{ app_id_base }}`` resolved) with the ``.j2`` suffix dropped.
    Keys are POSIX relpaths on every OS. Raises :class:`BakeError` if two
    templates resolve to the same output path (one would silently shadow the
    other)."""
    ctx = metadata.context() if ctx is None else ctx
    templates_dir = packaging_dir / TEMPLATES_SUBDIR
    env = _environment(templates_dir)
    out: dict[str, str] = {}
    for tpl in sorted(templates_dir.rglob("*.j2")):
        rel = tpl.relative_to(templates_dir)
        out_rel = env.from_string(rel.with_suffix("").as_posix()).render(**ctx)  # render the path too
        if out_rel in out:
            raise BakeError(f"two templates render to the same output path: {out_rel}")
        out[out_rel] = env.get_template(rel.as_posix()).render(**ctx)
    return out


def write(packaging_dir: Path, ctx: dict | None = None) -> dict[str, str]:
    """Render and write the tree under ``packaging_dir``. Writes LF newlines on
    every OS (committed files are LF; shell scripts break with CRLF) and gives
    ``.sh`` outputs the executable bit. Returns the rendered map."""
    rendered = render(packaging_dir, ctx)
    for rel, body in rendered.items():
        dest = packaging_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8", newline="\n")  # never CRLF
        if dest.suffix == ".sh":
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return rendered


def check(packaging_dir: Path, ctx: dict | None = None) -> list[str]:
    """Return a list of drift descriptions (empty ⇒ in sync). Catches: a missing
    file, a content/byte difference (CRLF included — compared as bytes), a ``.sh``
    that lost its executable bit, and an ORPHAN (a committed file no template
    produces)."""
    rendered = render(packaging_dir, ctx)
    drift: list[str] = []
    for rel, body in rendered.items():
        dest = packaging_dir / rel
        if not dest.is_file():
            drift.append(f"missing (run `dough bake`): {rel}")
            continue
        if dest.read_bytes() != body.encode("utf-8"):
            drift.append(f"drift (re-run `dough bake`): {rel}")
        elif dest.suffix == ".sh" and not (dest.stat().st_mode & stat.S_IXUSR):
            drift.append(f"not executable (re-run `dough bake`): {rel}")
    produced = set(rendered)
    for path in _committed_files(packaging_dir):
        rel = path.relative_to(packaging_dir).as_posix()
        if rel not in produced:
            drift.append(f"orphan (delete it, or add a template): {rel}")
    return drift


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dough-bake",
        description="Render the packaging tree from [tool.dough.metadata] (docs/BAKING.md §2).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed files match a fresh render; exit 1 on drift (the CI gate)",
    )
    parser.add_argument(
        "--packaging",
        type=Path,
        default=None,
        help="packaging dir (default: <repo>/packaging)",
    )
    args = parser.parse_args(argv)
    packaging_dir = args.packaging or (_repo_root() / "packaging")

    try:
        if args.check:
            drift = check(packaging_dir)
            if drift:
                print("packaging out of sync with [tool.dough.metadata]:", file=sys.stderr)
                print("  " + "\n  ".join(drift), file=sys.stderr)
                return 1
            print("packaging is in sync with [tool.dough.metadata].")
            return 0
        rendered = write(packaging_dir)
    except BakeError as exc:
        print(f"dough bake: {exc}", file=sys.stderr)
        return 1
    print(f"rendered {len(rendered)} file(s) into {packaging_dir}:")
    print("  " + "\n  ".join(sorted(rendered)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
