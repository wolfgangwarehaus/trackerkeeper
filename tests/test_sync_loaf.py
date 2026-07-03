"""Tests for the dough→loaf down-door (dev/sync_loaf.py).

The script lives under dev/ (stripped from forks), so it's loaded by path. We
cover the two correctness-critical, git-independent helpers:

  * ``_identity`` — must read the sidecar under ``[tool.<pkg>.metadata]``
    generically, since ``dough new`` renames the tool-table key to the slug.
  * ``_make_transform`` — must reproduce ``dough new``'s whole-word identity
    replace exactly (so an AUTO module renders byte-for-byte), and must NOT
    touch substrings or the identity-agnostic ``{{app_id}}`` effect token.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "dev" / "sync_loaf.py"


@pytest.fixture(scope="module")
def sl():
    spec = importlib.util.spec_from_file_location("_sync_loaf", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_identity_reads_renamed_tool_table(sl, tmp_path):
    # A loaf's sidecar lives under [tool.<slug>.metadata], not tool.dough.
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.butterpdf.metadata]\n'
        'app_slug = "butterpdf"\n'
        'org_slug = "wolfgangwarehaus"\n'
        'github_owner = "wolfgangwarehaus"\n'
    )
    assert sl._identity(pyproject) == ("butterpdf", "wolfgangwarehaus", "wolfgangwarehaus")


def test_identity_raises_without_sidecar(sl, tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[tool.ruff]\nline-length = 100\n')
    with pytest.raises(KeyError):
        sl._identity(pyproject)


def test_transform_whole_word_only(sl):
    transform = sl._make_transform(
        ("dough", "doughorg", "doughowner"),
        ("butterpdf", "wolfgangwarehaus", "wolfgangwarehaus"),
    )
    # Whole-word identity references are replaced…
    assert transform("from dough import identity") == "from butterpdf import identity"
    assert transform("org = doughorg") == "org = wolfgangwarehaus"
    # …but substrings are NOT (mirrors scaffold's \b-escaped replace).
    assert transform("doughnut") == "doughnut"
    assert transform("sourdough") == "sourdough"


def test_transform_leaves_effect_token_untouched(sl):
    # The drag_repaint effect template is identity-agnostic; the transform must
    # not disturb its {{app_id}} token (it's rendered later, from identity).
    transform = sl._make_transform(
        ("dough", "org", "owner"), ("butterpdf", "org", "owner")
    )
    js = 'cls.indexOf("{{app_id}}") !== -1'
    assert transform(js) == js


def test_transform_owner_before_org_and_slug(sl):
    # Order matters when owner is a superstring; \b keeps them distinct, and the
    # slug replace must not corrupt an already-substituted org/owner.
    transform = sl._make_transform(
        ("dough", "dough", "dough"),  # degenerate: all three equal
        ("butterpdf", "butterpdf", "butterpdf"),
    )
    assert transform("dough dough dough") == "butterpdf butterpdf butterpdf"


def test_noop_transform_when_identity_matches(sl):
    transform = sl._make_transform(("dough", "o", "w"), ("dough", "o", "w"))
    assert transform("from dough import x") == "from dough import x"


def test_transform_renames_env_var_prefixes(sl):
    # X2: DOUGH_* env vars must re-namespace on sync exactly as `dough new`
    # does at fork time ('_' is a word char — \bdough\b never reaches them).
    transform = sl._make_transform(
        ("dough", "org", "owner"), ("butterpdf", "org", "owner")
    )
    assert transform('os.environ.get("DOUGH_OPAQUE")') == 'os.environ.get("BUTTERPDF_OPAQUE")'
    assert transform("DOUGH_NO_DRAG_REPAINT") == "BUTTERPDF_NO_DRAG_REPAINT"
    # Suffix forms stay untouched (none exist in the tree; jinja renders those).
    assert transform("V_FOR_DOUGH") == "V_FOR_DOUGH"


def test_transform_matches_scaffold_on_env_vars(sl):
    # The parity promise: sync_loaf reproduces what `dough new` stamped —
    # byte-for-byte — including the env-prefix rename.
    from pathlib import Path as _P

    from dough import scaffold

    src = 'import dough\nDOUGH_OPAQUE = "DOUGH_BLUR_FORCE"\n'
    transform = sl._make_transform(("dough", "o", "w"), ("butterpdf", "o", "w"))
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        f = _P(td) / "m.py"
        f.write_text(src, encoding="utf-8")
        scaffold._replace_in_tree(_P(td), [("o", "o"), ("dough", "butterpdf")])
        assert f.read_text(encoding="utf-8") == transform(src)
