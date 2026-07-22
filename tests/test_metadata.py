"""The baking-phase metadata core — the verify half of "one source → generate →
verify nothing drifted" (docs/BAKING.md §2), in test form before the renderer
(``trackerkeeper bake``) exists.

Four guards:

1. **Sidecar shape** — ``[tool.trackerkeeper.metadata]`` loads, is schema-versioned, and
   carries the inputs the renderer needs.
2. **The §4 guarantee** — the build-time projections (computed from the sidecar
   slugs) EQUAL the runtime seam's projections (computed from the live identity).
   One formula, two data sources, proven to agree.
3. **No [project] ↔ sidecar drift** — the fields that live in BOTH
   ``[project]`` and the sidecar (description↔summary, keywords, license,
   requires-python, the maintainer) are identical. This is the exact failure
   mode the sidecar exists to kill (jellytoast carried six summary wordings and
   three publisher strings — docs/BAKING.md §1).
4. **No re-literalised ids** — no composite reverse-DNS / AUMID id appears as a
   hardcoded string anywhere in the package except the seam that defines the
   formula. notifications/_windows.py used to carry ``"wolfgangwarehaus.trackerkeeper"``;
   this guard keeps it (and any future copy) gone.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import trackerkeeper
from trackerkeeper import identity, metadata


@pytest.fixture(scope="module")
def sidecar() -> dict:
    return metadata.load()


@pytest.fixture(scope="module")
def pyproject() -> dict:
    return tomllib.loads(metadata._find_pyproject().read_text(encoding="utf-8"))


# ── 1. sidecar shape ─────────────────────────────────────────────────────────


def test_sidecar_is_schema_versioned(sidecar: dict) -> None:
    assert sidecar["metadata_version"] == 1


def test_sidecar_carries_the_inputs(sidecar: dict) -> None:
    """The ~9 inputs everything else derives from (docs/BAKING.md §3.1)."""
    for key in (
        "app_slug",
        "org_slug",
        "github_owner",
        "repo_name",
        "display_name",
        "summary",
        "license_spdx",
        "maintainer_email",
        "entry_point",
    ):
        assert sidecar.get(key), f"sidecar missing input: {key}"


def test_sidecar_slugs_match_the_runtime_seam(sidecar: dict) -> None:
    """The overlap fields (docs/BAKING.md §4): the sidecar's build-time slugs are
    the same strings trackerkeeper.identity exposes at runtime."""
    assert sidecar["app_slug"] == identity.app()
    assert sidecar["org_slug"] == identity.org()
    assert sidecar["github_owner"] == identity.owner()
    assert sidecar["display_name"] == identity.display_name()


# ── 2. the §4 guarantee: projections agree across the two sources ────────────


def test_projections_match_the_runtime_seam() -> None:
    """The crux of docs/BAKING.md §4: the ids the renderer stamps into manifests
    (projected from the sidecar) equal the ids the running app computes (from the
    live identity). A hand-edit that bypasses either source breaks this."""
    proj = metadata.projections()
    assert proj["windows_aumid"] == identity.windows_aumid()
    assert proj["app_id_base"] == identity.app_id_base()
    assert proj["cf_bundle_id"] == identity.cf_bundle_id()
    assert proj["desktop_id"] == identity.desktop_id()


def test_projection_values_are_canonical() -> None:
    proj = metadata.projections()
    assert proj["app_id_base"] == "io.github.wolfgangwarehaus.trackerkeeper"
    assert proj["windows_aumid"] == "wolfgangwarehaus.trackerkeeper"
    assert proj["cf_bundle_id"] == "com.wolfgangwarehaus.trackerkeeper"
    # desktop_id == app_id_base, but pin it independently so a drift in its own
    # formula (e.g. appending ".desktop" or lowercasing) is caught — elsewhere
    # it's only ever asserted RELATIONALLY (== app_id_base), which moves together.
    assert proj["desktop_id"] == "io.github.wolfgangwarehaus.trackerkeeper"
    assert proj["homepage_url"] == "https://github.com/wolfgangwarehaus/trackerkeeper"
    assert proj["client_identity"] == f"trackerkeeper/{trackerkeeper.__version__} (+{proj['homepage_url']})"


def test_context_merges_and_projections_win(sidecar: dict) -> None:
    ctx = metadata.context()
    assert ctx["summary"] == sidecar["summary"]  # sidecar field carried through
    assert ctx["app_id_base"] == identity.app_id_base()  # projection carried through


# ── 3. no [project] ↔ sidecar drift ──────────────────────────────────────────


def test_project_summary_matches_sidecar(pyproject: dict, sidecar: dict) -> None:
    assert pyproject["project"]["description"] == sidecar["summary"]


def test_project_keywords_match_sidecar(pyproject: dict, sidecar: dict) -> None:
    assert pyproject["project"]["keywords"] == sidecar["keywords"]


def test_project_license_matches_sidecar(pyproject: dict, sidecar: dict) -> None:
    assert pyproject["project"]["license"]["text"] == sidecar["license_spdx"]


# The Trove license classifier is a THIRD copy of the license (PyPI surfaces it
# prominently). Keep it derivable from license_spdx so a fork that re-licenses
# can't leave a stale GPLv2+ classifier — the exact multi-wording drift the
# sidecar exists to kill (docs/BAKING.md §1).
_SPDX_TO_TROVE = {
    "GPL-2.0-or-later": "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)",
    # extend as new fork licenses are adopted
}


def test_project_license_classifier_matches_sidecar(pyproject: dict, sidecar: dict) -> None:
    spdx = sidecar["license_spdx"]
    expected = _SPDX_TO_TROVE.get(spdx)
    assert expected, f"no Trove classifier mapped for license_spdx={spdx!r}; add it to _SPDX_TO_TROVE"
    assert expected in pyproject["project"]["classifiers"]


def test_project_requires_python_matches_sidecar(pyproject: dict, sidecar: dict) -> None:
    assert pyproject["project"]["requires-python"] == sidecar["requires_python"]


def test_project_maintainer_matches_sidecar(pyproject: dict, sidecar: dict) -> None:
    author = pyproject["project"]["authors"][0]
    assert author["name"] == sidecar["maintainer_name"]
    assert author["email"] == sidecar["maintainer_email"]


def test_project_entry_point_matches_sidecar(pyproject: dict, sidecar: dict) -> None:
    # the gui-script target is the sidecar entry_point
    assert pyproject["project"]["gui-scripts"]["trackerkeeper"] == sidecar["entry_point"]


# ── 4. no re-literalised composite ids ───────────────────────────────────────


def test_no_hardcoded_composite_ids_outside_the_seam() -> None:
    """No source outside trackerkeeper/identity.py (where the formula lives) may carry a
    composite reverse-DNS / AUMID id — those are PROJECTIONS, computed, never
    typed (docs/BAKING.md §3.2).

    The patterns are FROZEN canonical literals (not read from the live identity
    seam) so a prior test's configure() can never change what the guard polices.
    The scan is case-insensitive (Windows AUMIDs and macOS bundle ids are
    case-folded by their target systems) and also flags the id PREFIXES, so a
    copy assembled across lines or via an f-string — which the assembled string
    would never match as a verbatim substring — still trips it."""
    import re

    org, app = "wolfgangwarehaus", "trackerkeeper"  # trackerkeeper's frozen canonical org/app
    patterns = [
        re.compile(re.escape(f"{org}.{app}"), re.I),  # windows_aumid
        re.compile(r"io\.github\." + re.escape(org), re.I),  # app_id_base / desktop_id prefix
        re.compile(r"com\." + re.escape(org) + r"\.", re.I),  # cf_bundle_id prefix
    ]
    pkg_dir = Path(trackerkeeper.__file__).parent
    exempt = {"identity.py", "_version.py"}  # the formula home; the generated file
    # NOTE: scope is the trackerkeeper/ *.py package only. When the Beat-2 `trackerkeeper bake`
    # renderer + its templates land, extend this to also scan the *.j2 templates
    # and any checked-in manifest fixtures (.desktop / metainfo / deb control /
    # winget YAML / PKGBUILD) — those aren't .py and don't live under trackerkeeper/.
    offenders: list[str] = []
    for py in sorted(pkg_dir.rglob("*.py")):
        if py.name in exempt:
            continue
        text = py.read_text(encoding="utf-8")
        for pat in patterns:
            if pat.search(text):
                offenders.append(f"{py.relative_to(pkg_dir)}: matches {pat.pattern!r}")
    assert not offenders, "re-literalised composite ids (use trackerkeeper.identity):\n  " + "\n  ".join(
        offenders
    )
