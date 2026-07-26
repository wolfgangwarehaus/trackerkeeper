"""Guard the file that becomes the public release notes.

``release.yml`` lifts a version's section out of ``docs/CHANGELOG.md``
**verbatim** into the GitHub release. Nothing else ever reads that file
end-to-end, so a mistake in it is invisible right up until it's published under
the project's name — the worst possible moment to notice.

That already nearly happened here: appending to ``[Unreleased]`` across several
working sessions left a section with ``### Changed`` and ``### Fixed`` in it
twice, which would have shipped as duplicated headings in the v0.1.2 notes. It
was caught by eye while cutting the release, which is not a control.

These checks are cheap and they run in the normal suite, so the failure surfaces
when the changelog is edited rather than when it is published.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CHANGELOG = Path(__file__).resolve().parents[1] / "docs" / "CHANGELOG.md"

_VERSION_HEADING = re.compile(r"^## \[(?P<ver>[^\]]+)\](?:\s+—\s+(?P<date>\S+))?\s*$")
_SECTION_HEADING = re.compile(r"^### (?P<name>.+?)\s*$")
# Keep a Changelog's vocabulary, plus the one we add for developer-facing notes.
_ALLOWED_SECTIONS = {"Added", "Changed", "Deprecated", "Removed", "Fixed",
                     "Security", "Internal"}


def _releases() -> list[tuple[str, str, list[str]]]:
    """``[(version, date, [section names]), …]`` in file order."""
    out: list[tuple[str, str, list[str]]] = []
    for line in CHANGELOG.read_text(encoding="utf-8").splitlines():
        m = _VERSION_HEADING.match(line)
        if m:
            out.append((m.group("ver"), m.group("date") or "", []))
            continue
        m = _SECTION_HEADING.match(line)
        if m and out:
            out[-1][2].append(m.group("name"))
    return out


def _as_tuple(ver: str) -> tuple[int, ...]:
    return tuple(int(p) for p in ver.split(".") if p.isdigit())


def test_changelog_exists_and_has_an_unreleased_section():
    assert CHANGELOG.is_file(), f"no changelog at {CHANGELOG}"
    versions = [v for v, _, _ in _releases()]
    assert versions, "no version headings"
    assert versions[0] == "Unreleased", (
        f"the first heading must be [Unreleased], got [{versions[0]}] — that's "
        "where the next release's notes accumulate"
    )


def test_no_release_repeats_a_section_heading():
    """The one that nearly shipped. Two "### Fixed" blocks in a release read as
    a mistake to anyone opening the release page, and the fix (merge them) is
    invisible unless someone reads the whole section."""
    for ver, _, sections in _releases():
        dupes = {s for s in sections if sections.count(s) > 1}
        assert not dupes, (
            f"[{ver}] repeats {sorted(dupes)} — merge them into one block; "
            "release.yml lifts this section verbatim into the release notes"
        )


def test_section_headings_are_the_standard_vocabulary():
    for ver, _, sections in _releases():
        unknown = set(sections) - _ALLOWED_SECTIONS
        assert not unknown, (
            f"[{ver}] uses {sorted(unknown)}; Keep a Changelog defines "
            f"{sorted(_ALLOWED_SECTIONS)}"
        )


def test_every_released_version_is_dated():
    for ver, date, _ in _releases():
        if ver == "Unreleased":
            continue
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", date), (
            f"[{ver}] has no ISO date — the heading must read "
            f"'## [{ver}] — YYYY-MM-DD'"
        )


def test_versions_run_newest_first():
    released = [v for v, _, _ in _releases() if v != "Unreleased"]
    ordered = sorted(released, key=_as_tuple, reverse=True)
    assert released == ordered, (
        f"versions are out of order: {released} should be {ordered}"
    )


def test_no_version_appears_twice():
    versions = [v for v, _, _ in _releases()]
    dupes = {v for v in versions if versions.count(v) > 1}
    assert not dupes, f"duplicated version heading(s): {sorted(dupes)}"


@pytest.mark.parametrize("marker", ["<!-- release-notes-end -->"])
def test_the_release_notes_end_marker_survives(marker):
    """release.yml stops extracting at this marker; losing it would append the
    tail of the file to whatever release is cut next."""
    assert marker in CHANGELOG.read_text(encoding="utf-8"), (
        f"{marker} is gone — release.yml uses it to bound the extracted notes"
    )


def test_the_current_version_can_be_extracted():
    """Mirror what release.yml's awk does, so a section that exists but can't be
    lifted (a stray heading level, a typo in the version) fails here instead of
    producing an empty release body."""
    import trackerkeeper

    ver = trackerkeeper.__version__.split("+")[0]
    released = {v for v, _, _ in _releases()}
    if ver not in released:
        pytest.skip(f"{ver} is a dev build with no changelog section yet")
    text = CHANGELOG.read_text(encoding="utf-8")
    body = text.split(f"## [{ver}]", 1)[1].split("\n## [", 1)[0]
    assert body.strip(), f"[{ver}] section is empty — the release notes would be blank"
