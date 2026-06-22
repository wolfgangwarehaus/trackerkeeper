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
        if "{{" in text or "{%" in text or "{#" in text:
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


def test_release_render_without_date_does_not_crash(packaging_dir: Path) -> None:
    """A release render that supplies only release_version (no release_date) must
    not blow up under StrictUndefined — release_date defaults to empty."""
    import xml.dom.minidom

    ctx = {**metadata.context(), "release_version": "1.2.3"}  # deliberately no release_date
    metainfo = bake.render(packaging_dir, ctx)[f"{identity.app_id_base()}.metainfo.xml"]
    assert '<release version="1.2.3"' in metainfo
    xml.dom.minidom.parseString(metainfo)  # still well-formed


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
    """The build scripts are syntactically valid shell (validity, not just match)."""
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash not available")
    for rel in ("deb/build_deb.sh", "appimage/build_appimage.sh"):
        result = subprocess.run(
            [bash, "-n", str(packaging_dir / rel)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"{rel} failed bash -n:\n{result.stderr}"


def test_rendered_python_compiles(packaging_dir: Path) -> None:
    """The spec + launcher are valid Python (compile() only checks syntax — it
    writes no .pyc, so it can't pollute packaging/)."""
    for rel in (f"pyinstaller/{identity.app()}.spec", "pyinstaller/launch.py"):
        path = packaging_dir / rel
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


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

    (tmp_path / "deb" / "build_deb.sh").chmod(0o644)
    assert any("not executable" in d for d in bake.check(tmp_path))
