"""The baking-phase renderer + its generate-then-verify gate (docs/BAKING.md §2).

The committed ``packaging/`` tree is RENDERED output, never hand-authored. These
guard that contract:

1. **In sync** — a fresh render equals what's committed (the ``dough bake
   --check`` gate). A hand-edit of a rendered manifest, or a stale render after a
   metadata change, fails here — forcing the edit into the template instead.
2. **Ids are projections** — the reverse-DNS id stamped into the .desktop /
   metainfo / filenames is exactly ``identity.app_id_base()``, never a literal.
3. **Valid output** — the metainfo is well-formed XML; nothing carries an
   unrendered ``{{ }}`` / ``{% %}`` marker.
4. **Version-stable** — no committed artifact bakes the marketing version (the
   tag is the version; ``<releases>`` is injected at release time, not committed).

jinja2 is a build-time-only (``bake``/``dev``) dependency; a env without it skips.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("jinja2")

import dough
from dough import bake, identity, metadata


@pytest.fixture(scope="module")
def packaging_dir() -> Path:
    return bake._repo_root() / "packaging"


def _committed_files(packaging_dir: Path):
    """The committed (rendered) files — skips the templates/ sources and any stray
    __pycache__ a tool may drop next to launch.py / the spec."""
    for path in sorted(packaging_dir.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(packaging_dir).parts
        if "templates" in parts or "__pycache__" in parts:
            continue
        yield path


def test_packaging_is_in_sync(packaging_dir: Path) -> None:
    """The committed tree equals a fresh render — the generate-then-verify gate."""
    drift = bake.check(packaging_dir)
    assert not drift, "packaging out of sync (run `dough bake`):\n  " + "\n  ".join(drift)


def test_render_is_deterministic(packaging_dir: Path) -> None:
    assert bake.render(packaging_dir) == bake.render(packaging_dir)


def test_expected_artifacts_render(packaging_dir: Path) -> None:
    """The first-channel set: freedesktop pair, deb + appimage builders, the
    PyInstaller spec + launcher — with the app-id resolved into the filenames."""
    rendered = set(bake.render(packaging_dir))
    app_id = identity.app_id_base()
    assert {
        f"{app_id}.desktop",
        f"{app_id}.metainfo.xml",
        "deb/build_deb.sh",
        "appimage/build_appimage.sh",
        f"pyinstaller/{identity.app()}.spec",
        "pyinstaller/launch.py",
    } <= rendered


def test_ids_are_projections_not_literals(packaging_dir: Path) -> None:
    """The reverse-DNS id in the freedesktop files is the computed projection."""
    rendered = bake.render(packaging_dir)
    app_id = identity.app_id_base()
    desktop = rendered[f"{app_id}.desktop"]
    assert f"Icon={app_id}\n" in desktop
    assert f"StartupWMClass={identity.app()}\n" in desktop
    metainfo = rendered[f"{app_id}.metainfo.xml"]
    assert f"<id>{app_id}</id>" in metainfo
    assert f"<launchable type=\"desktop-id\">{identity.desktop_id()}.desktop</launchable>" in metainfo


def test_no_unrendered_markers(packaging_dir: Path) -> None:
    """No committed artifact carries an unrendered jinja marker (StrictUndefined
    would have raised at render, but guard the committed files too)."""
    offenders: list[str] = []
    for path in _committed_files(packaging_dir):
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".iss":
            # Inno uses {{ (the AppId escape), {#define} and {const} — all close
            # with a SINGLE }. Jinja syntax always closes with }} / %} / #}, which
            # Inno never emits — so flag those (still catches an unrendered
            # {{ var }} or {# comment #} that somehow reached the file).
            bad = "}}" in text or "%}" in text or "#}" in text
        else:
            bad = "{{" in text or "{%" in text or "{#" in text
        if bad:
            offenders.append(str(path.relative_to(packaging_dir)))
    assert not offenders, "unrendered template markers in: " + ", ".join(offenders)


def test_renders_are_version_stable(packaging_dir: Path) -> None:
    """No committed artifact bakes the version — else the gate would flap every
    commit (setuptools-scm bumps __version__ each commit). The version reaches
    manifests only at release time (docs/BAKING.md §6.2)."""
    version = dough.__version__
    offenders: list[str] = []
    for path in _committed_files(packaging_dir):
        if version in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(packaging_dir)))
    assert not offenders, f"version {version!r} baked into: " + ", ".join(offenders)


def test_metainfo_is_well_formed_xml(packaging_dir: Path) -> None:
    import xml.dom.minidom

    xml.dom.minidom.parseString(bake.render(packaging_dir)[f"{identity.app_id_base()}.metainfo.xml"])


def test_release_block_injected_only_with_a_version(packaging_dir: Path) -> None:
    """The committed metainfo omits <releases> (no release_version in the default
    context); passing one at render time injects it — the release-time hook."""
    metainfo_name = f"{identity.app_id_base()}.metainfo.xml"
    assert "<releases>" not in bake.render(packaging_dir)[metainfo_name]
    ctx = {**metadata.context(), "release_version": "9.9.9", "release_date": "2099-01-01"}
    injected = bake.render(packaging_dir, ctx)[metainfo_name]
    assert '<release version="9.9.9"' in injected and "2099-01-01" in injected


def test_release_render_defaults_a_valid_date(tmp_path: Path, packaging_dir: Path) -> None:
    """`dough bake --release-version` WITHOUT --release-date self-defaults a real
    date — AppStream rejects a <release> with an empty date, so date="" would be
    silently-invalid output. Rendered into a copy so the committed tree is intact."""
    import re

    shutil.copytree(packaging_dir / "templates", tmp_path / "templates")
    rc = bake.main(["--packaging", str(tmp_path), "--release-version", "1.2.3"])  # no date
    assert rc == 0
    metainfo = (tmp_path / f"{identity.app_id_base()}.metainfo.xml").read_text(encoding="utf-8")
    assert '<release version="1.2.3"' in metainfo
    assert 'date=""' not in metainfo
    assert re.search(r'date="\d{4}-\d{2}-\d{2}"', metainfo), "release date must be a real ISO date"


def test_check_ignores_release_version(packaging_dir: Path) -> None:
    """`dough bake --check --release-version X` must NOT inject a <release> or
    report drift — the gate stays version-free (main() calls check() with no ctx).
    Load-bearing for the CI gate: a refactor threading ctx into check() would break it."""
    rc = bake.main(["--packaging", str(packaging_dir), "--check", "--release-version", "9.9.9"])
    assert rc == 0


# ── the gate proves VALIDITY, not just template-match ────────────────────────


def test_rendered_desktop_has_required_keys(packaging_dir: Path) -> None:
    desktop = (packaging_dir / f"{identity.app_id_base()}.desktop").read_text(encoding="utf-8")
    assert desktop.startswith("[Desktop Entry]")
    assert desktop.endswith("\n")  # POSIX text file — guards the trailing-newline regression
    for key in (
        "Type=Application",
        f"Name={identity.display_name()}",
        f"Exec={identity.app()}",
        f"Icon={identity.app_id_base()}",
    ):
        assert key in desktop, f"desktop missing {key!r}"


def test_rendered_shell_scripts_pass_bash_n(packaging_dir: Path) -> None:
    """Every rendered shell artifact (build + smoke scripts + the PKGBUILD) is
    syntactically valid shell — validity, not just template-match."""
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash not available")
    scripts = [p for p in _committed_files(packaging_dir) if p.suffix == ".sh" or p.name == "PKGBUILD"]
    assert scripts, "no shell scripts found to check"
    for path in sorted(scripts):
        result = subprocess.run([bash, "-n", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, f"{path} failed bash -n:\n{result.stderr}"


def test_rendered_python_compiles(packaging_dir: Path) -> None:
    """The spec + launcher are valid Python (compile() only checks syntax — it
    writes no .pyc, so it can't pollute packaging/)."""
    for rel in (f"pyinstaller/{identity.app()}.spec", "pyinstaller/launch.py"):
        path = packaging_dir / rel
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_rendered_xml_and_plist_are_well_formed(packaging_dir: Path) -> None:
    """Structural validity for the MSIX manifest + the macOS entitlements — XML /
    plist no other gate parses (a malformed manifest would otherwise pass)."""
    import plistlib
    import xml.dom.minidom

    xml.dom.minidom.parse(str(packaging_dir / "msix" / "AppxManifest.xml"))
    with (packaging_dir / "macos" / "entitlements.plist").open("rb") as fh:
        plistlib.load(fh)


def test_rendered_cask_is_valid_ruby(packaging_dir: Path) -> None:
    """The Homebrew cask is valid Ruby syntax (skipped where ruby is absent)."""
    ruby = shutil.which("ruby")
    if not ruby:
        pytest.skip("ruby not available")
    cask = packaging_dir / "macos" / f"{identity.app()}.rb"
    result = subprocess.run([ruby, "-c", str(cask)], capture_output=True, text=True)
    assert result.returncode == 0, f"cask failed ruby -c:\n{result.stderr}"


def test_bake_cli_injects_release(tmp_path: Path, packaging_dir: Path) -> None:
    """`dough bake --release-version` writes the <release> block (the release-time
    render); the plain CLI / --check stays version-free. Rendered into a copy so
    the committed tree is untouched."""
    shutil.copytree(packaging_dir / "templates", tmp_path / "templates")
    rc = bake.main(
        ["--packaging", str(tmp_path), "--release-version", "1.2.3", "--release-date", "2026-01-01"]
    )
    assert rc == 0
    metainfo = (tmp_path / f"{identity.app_id_base()}.metainfo.xml").read_text(encoding="utf-8")
    assert '<release version="1.2.3"' in metainfo and "2026-01-01" in metainfo


def test_templates_use_projections_not_literal_ids(packaging_dir: Path) -> None:
    """Templates must reference {{ app_id_base }} / {{ vendor_id }} etc., never a
    hardcoded composite id — else a fork renaming itself silently ships dough's
    ids into its manifests (the rendered output legitimately carries the literals;
    only the .j2 sources are scanned)."""
    import re

    org, app = "wolfgangwarehaus", "dough"  # frozen canonical org/app
    patterns = [
        re.compile(re.escape(f"{org}.{app}"), re.I),
        re.compile(r"io\.github\." + re.escape(org), re.I),
        re.compile(r"com\." + re.escape(org) + r"\.", re.I),
    ]
    offenders: list[str] = []
    for tpl in sorted((packaging_dir / "templates").rglob("*.j2")):
        text = tpl.read_text(encoding="utf-8")
        for pat in patterns:
            if pat.search(text):
                offenders.append(f"{tpl.relative_to(packaging_dir)}: matches {pat.pattern!r}")
    assert not offenders, "templates with hardcoded composite ids (use a projection):\n  " + "\n  ".join(
        offenders
    )


def test_version_info_filevers_are_ints(tmp_path: Path, packaging_dir: Path) -> None:
    """The Windows VSVersionInfo filevers must be 4 integers for ANY tag — incl. a
    PEP 440 pre-release (0.1.0rc1) — else the eval'd version file is a SyntaxError
    that crashes the freeze. Rendered into a copy so the committed tree is intact."""
    import re

    shutil.copytree(packaging_dir / "templates", tmp_path / "templates")
    cases = {
        "0.1.0": "(0, 1, 0, 0)",
        "1.2.10": "(1, 2, 10, 0)",
        "0.1.0rc1": "(0, 1, 0, 0)",  # PEP 440 pre-release: leading-digit run per segment
        "2.0.0.dev5": "(2, 0, 0, 0)",
    }
    for version, expected in cases.items():
        assert bake.main(["--packaging", str(tmp_path), "--release-version", version]) == 0
        vinfo = (tmp_path / "windows" / "version_info.txt").read_text(encoding="utf-8")
        compile(vinfo, "version_info.txt", "exec")  # valid Python (no bare 0rc1)
        match = re.search(r"filevers=(\([^)]*\))", vinfo)
        assert match and match.group(1) == expected, f"{version}: filevers {match and match.group(1)}"


def test_check_catches_every_drift_class(tmp_path: Path, packaging_dir: Path) -> None:
    """check() flags content drift, a missing file, an orphan (no template makes
    it), and a .sh that lost its executable bit — rendered into an isolated copy."""
    shutil.copytree(packaging_dir / "templates", tmp_path / "templates")
    bake.write(tmp_path)
    assert bake.check(tmp_path) == []  # a fresh render is clean

    app_id = identity.app_id_base()
    (tmp_path / f"{app_id}.desktop").write_text("tampered\n", encoding="utf-8")
    assert any("drift" in d for d in bake.check(tmp_path))
    bake.write(tmp_path)

    (tmp_path / "deb" / "build_deb.sh").unlink()
    assert any("missing" in d for d in bake.check(tmp_path))
    bake.write(tmp_path)

    stale = tmp_path / "deb" / "STALE.sh"
    stale.write_text("#!/bin/sh\n", encoding="utf-8")
    assert any("orphan" in d for d in bake.check(tmp_path))
    stale.unlink()

    if os.name == "posix":  # exec bits are POSIX semantics; check() skips them on Windows
        (tmp_path / "deb" / "build_deb.sh").chmod(0o644)
        assert any("not executable" in d for d in bake.check(tmp_path))
