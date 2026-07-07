"""dough's build-time metadata — the one source the oven renders every manifest from.

Build-time counterpart to :mod:`dough.identity` (runtime). ``identity`` owns the
LIVE app identity (org / app / display_name) and the reverse-DNS id projections
the RUNNING QApplication needs; this module reads the ``[tool.dough.metadata]``
sidecar in ``pyproject.toml`` — the descriptive / store fields a future
``dough bake`` stamps into the ``.desktop`` entry, the AppStream metainfo, deb
``control``, winget YAML, the PKGBUILD, and the landing page. None is
hand-authored (docs/BAKING.md §2).

This module never touches the running QApplication. Where the sidecar overlaps
``identity`` (the slugs) it projects the SAME ids through identity's pure helpers
(``aumid_for`` / ``app_id_base_for`` / ``cf_bundle_id_for``) — so the manifests
and the running app share one formula. ``tests/test_metadata.py`` asserts the two
data sources agree, so a hand-edit bypassing either fails CI (docs/BAKING.md §4).

The sidecar lives in ``pyproject.toml``, which ships in a source tree but not in
an installed wheel. The renderer always runs from a checkout, so :func:`load`
locates ``pyproject.toml`` by walking up from this file and raises
:class:`MetadataError` if it's absent.
"""

from __future__ import annotations

import copy
import tomllib
from functools import lru_cache
from pathlib import Path

from dough import identity


class MetadataError(RuntimeError):
    """The ``[tool.dough.metadata]`` sidecar is missing or malformed."""


def _find_pyproject() -> Path:
    """The nearest ``pyproject.toml`` at or above this file."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
    raise MetadataError(
        "pyproject.toml not found above dough/metadata.py — the baking-phase "
        "renderer runs from a source checkout, not an installed wheel."
    )


@lru_cache(maxsize=1)
def load() -> dict:
    """The raw ``[tool.dough.metadata]`` table, with the resolved package
    ``version`` folded in (the tag is the version — docs/BAKING.md §2). Cached
    per process; the sidecar is static within a build."""
    pyproject = _find_pyproject()
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    try:
        meta = dict(data["tool"]["dough"]["metadata"])
    except KeyError as exc:
        raise MetadataError(f"[tool.dough.metadata] missing from {pyproject}") from exc
    # Presence-only validation for now: full value/type/required-field checks
    # against packaging/metadata.schema.toml (docs/BAKING.md §7) are deferred to
    # the Beat-2 `dough bake` renderer — until then metadata_version is a forward
    # marker, not an enforced schema. We do guard the slugs projections() reads
    # by bare subscript, so a malformed sidecar fails here (legibly) rather than
    # with an opaque KeyError from a downstream function.
    if "metadata_version" not in meta:
        raise MetadataError(f"[tool.dough.metadata] has no metadata_version in {pyproject}")
    for key in ("org_slug", "app_slug", "github_owner", "repo_name"):
        if key not in meta:
            raise MetadataError(f"[tool.dough.metadata] missing required key {key!r} in {pyproject}")

    from dough import __version__

    meta.setdefault("version", __version__)
    # The PyPI DISTRIBUTION name ([project].name) — distinct from app_slug when
    # the slug is taken on PyPI (dough publishes as `dough-base`). Folded in from
    # pyproject so templates that address the dist (setuptools-scm's
    # …_FOR_<DIST> env var, pip specs) can't silently assume the slug.
    try:
        meta.setdefault("dist_name", data["project"]["name"])
    except KeyError as exc:
        raise MetadataError(f"[project] has no name in {pyproject}") from exc
    return meta


def projections() -> dict:
    """The ids / URLs DERIVED from the sidecar — never re-literalised
    (docs/BAKING.md §3.2). Computed with the very helpers the running app uses
    (``identity.*_for``), fed the sidecar's slugs, so the manifests and the live
    app cannot diverge; the verify gate proves it."""
    meta = load()
    org = meta["org_slug"]
    app = meta["app_slug"]
    owner = meta["github_owner"]
    repo = meta["repo_name"]
    homepage = f"https://github.com/{owner}/{repo}"
    return {
        "windows_aumid": identity.aumid_for(org, app),
        "app_id_base": identity.app_id_base_for(owner, app),
        "cf_bundle_id": identity.cf_bundle_id_for(org, app),
        "desktop_id": identity.app_id_base_for(owner, app),
        # the reverse-DNS VENDOR prefix (io.github.{owner}) — the AppStream
        # <developer id>, distinct from the full per-app component id.
        "vendor_id": f"io.github.{owner}",
        "homepage_url": homepage,
        "issues_url": f"{homepage}/issues",
        "releases_url": f"{homepage}/releases",
        "license_url": f"{homepage}/blob/main/LICENSE",
        # runtime User-Agent / API-client string (docs/BAKING.md §3.3)
        "client_identity": f"{app}/{meta['version']} (+{homepage})",
    }


def context() -> dict:
    """The full render context — the sidecar fields plus the derived
    projections, merged. This is exactly what a ``*.j2`` channel template
    consumes (Beat 2). Projections win on a key clash so a stray sidecar literal
    can never shadow a computed id. The sidecar half is deep-copied so a caller
    mutating a list value (categories, keywords, …) can't corrupt the lru_cached
    :func:`load` dict."""
    return {**copy.deepcopy(load()), **projections()}
