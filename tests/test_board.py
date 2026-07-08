"""The dough board (dough/board.py) — the live maker surface. The FILE is the
API between maker, window, and agent, so the file half gets the real coverage:
deterministic round-trips, the seed template, and the window's write-backs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dough import board


def test_default_board_round_trips_byte_stable(tmp_path: Path) -> None:
    """Same board, same bytes — git diffs stay honest and the agent/window
    never fight over formatting."""
    p = tmp_path / board.FILENAME
    b = board.default_board("myapp")
    board.save(p, b)
    first = p.read_bytes()
    board.save(p, board.load(p))
    assert p.read_bytes() == first
    loaded = board.load(p)
    assert loaded["product"] == "myapp"
    for phase in board.PHASES:
        assert loaded[phase], f"seed left {phase} empty"


def test_save_escapes_hostile_strings(tmp_path: Path) -> None:
    p = tmp_path / board.FILENAME
    b = board.default_board("x")
    b["ingredients"][0]["note"] = 'say "hi"\\ and\nnewline\ttab'
    board.save(p, b)
    assert board.load(p)["ingredients"][0]["note"] == 'say "hi"\\ and\nnewline\ttab'


def test_load_tolerates_a_minimal_file(tmp_path: Path) -> None:
    """A hand-written board with only a goal still loads with every phase key."""
    p = tmp_path / board.FILENAME
    p.write_text('goal = "ship it"\n', encoding="utf-8")
    b = board.load(p)
    assert b["goal"] == "ship it"
    assert all(b[phase] == [] for phase in board.PHASES)


def test_board_path_anchors_to_the_checkout(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # CWD must not matter (same lesson as rig goldens)
    assert board.board_path().parent == board.repo_root()
    assert (board.repo_root() / "pyproject.toml").is_file()


@pytest.mark.usefixtures("qapp")
def test_window_toggles_write_the_file(tmp_path: Path) -> None:
    p = tmp_path / board.FILENAME
    board.save(p, board.default_board("myapp"))
    view = board._make_view(p)
    item = view._board["ingredients"][0]
    assert item["done"] is False
    view._set_done(item, True)
    on_disk = board.load(p)["ingredients"][0]
    assert on_disk["done"] is True
    assert on_disk["by"] == "maker" and on_disk["date"]


@pytest.mark.usefixtures("qapp")
def test_window_notes_and_added_items_write_the_file(tmp_path: Path) -> None:
    p = tmp_path / board.FILENAME
    board.save(p, board.default_board("myapp"))
    view = board._make_view(p)
    view._set_note(view._board["delivery"][0], "hold this until Friday")
    view._add_item("improvements", "dark mode for the docs site")
    on_disk = board.load(p)
    assert on_disk["delivery"][0]["note"] == "hold this until Friday"
    assert on_disk["improvements"][-1]["text"] == "dark mode for the docs site"
    assert on_disk["improvements"][-1]["by"] == "maker"


@pytest.mark.usefixtures("qapp")
def test_window_opens_on_the_first_unfinished_phase(tmp_path: Path) -> None:
    p = tmp_path / board.FILENAME
    b = board.default_board("myapp")
    for item in b["ingredients"]:
        item["done"] = True
    board.save(p, b)
    view = board._make_view(p)
    assert view._first_open_phase() == "baking"


def test_cli_init_seeds_and_refuses_overwrite(tmp_path, monkeypatch, capsys) -> None:
    p = tmp_path / board.FILENAME
    monkeypatch.setattr(board, "board_path", lambda: p)
    assert board.main(["--init"]) == 0
    assert p.is_file()
    assert board.main(["--init"]) == 1  # never clobbers a real board
