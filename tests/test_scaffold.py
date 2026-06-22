"""Unit coverage for `dough new` (dough.scaffold) — the pure pieces.

The full rename is validated end-to-end by running it on a throwaway copy of the
repo (manual / CI), not here — a nested pytest-in-pytest would be slow and awkward.
These lock the two riskiest pure bits: the whole-word identity replace and the slug
guard.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dough import scaffold


@pytest.mark.parametrize("bad", ["Butter", "butter-pdf", "1app", "butter pdf", "", "dough.x"])
def test_slug_validation_rejects_bad_slugs(bad: str) -> None:
    """A bad slug fails at argparse, before anything touches the repo."""
    with pytest.raises(SystemExit):
        scaffold.main([bad])


def test_replace_in_tree_is_whole_word(tmp_path: Path) -> None:
    """The identity replace hits standalone + quoted + dotted occurrences but NOT a
    mid-identifier substring (so `_dough_helper` survives — cosmetic, never breaks
    behaviour)."""
    f = tmp_path / "x.py"
    f.write_text(
        "import dough\n"
        "from dough.app import main\n"
        "x = _dough_helper()  # the dough brand\n"
        "g = 'dough._version'\n",
        encoding="utf-8",
    )
    scaffold._replace_in_tree(tmp_path, [("dough", "butterpdf")])
    out = f.read_text(encoding="utf-8")
    assert "import butterpdf\n" in out
    assert "from butterpdf.app import main" in out
    assert "_dough_helper()" in out  # mid-identifier: untouched
    assert "the butterpdf brand" in out  # standalone word: replaced
    assert "'butterpdf._version'" in out  # quoted: replaced


def test_replace_in_tree_skips_binary_and_caches(tmp_path: Path) -> None:
    """Only text files in scope are touched; a __pycache__ entry is skipped."""
    (tmp_path / "__pycache__").mkdir()
    cached = tmp_path / "__pycache__" / "m.cpython-313.pyc"
    cached.write_bytes(b"dough\x00binary")
    scaffold._replace_in_tree(tmp_path, [("dough", "butterpdf")])
    assert cached.read_bytes() == b"dough\x00binary"  # untouched
