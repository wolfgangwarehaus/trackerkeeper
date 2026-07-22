"""The dough board (dough/breadboard.py) — the live maker surface. The FILE is the
API between maker, window, and agent, so the file half gets the real coverage:
deterministic round-trips, the seed template, and the window's write-backs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dough import breadboard as board


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


# ── v2: priorities (the kanban), purpose (the summary page) ──────────────────


def test_priority_and_purpose_round_trip(tmp_path: Path) -> None:
    p = tmp_path / board.FILENAME
    b = board.default_board("myapp")
    b["purpose"] = "a PDF tool for humans\nno AGPL"
    b["baking"][0]["priority"] = "now"
    board.save(p, b)
    loaded = board.load(p)
    assert loaded["purpose"] == "a PDF tool for humans\nno AGPL"
    assert loaded["baking"][0]["priority"] == "now"
    # every baking item normalizes to a valid priority; other phases carry none
    assert all(i["priority"] in board.PRIORITIES for i in loaded["baking"])
    assert all("priority" not in i for i in loaded["delivery"])


def test_bogus_priority_normalizes_to_next(tmp_path: Path) -> None:
    p = tmp_path / board.FILENAME
    p.write_text(
        'goal = "g"\n[[baking]]\ntext = "x"\ndone = false\npriority = "urgent!!"\n',
        encoding="utf-8",
    )
    assert board.load(p)["baking"][0]["priority"] == "next"


@pytest.mark.usefixtures("qapp")
def test_kanban_move_updates_priority_and_done(tmp_path: Path) -> None:
    p = tmp_path / board.FILENAME
    board.save(p, board.default_board("myapp"))
    view = board._make_view(p)
    item = view._board["baking"][0]
    assert (item["priority"], item["done"]) == ("now", False)
    view._move_card(item, "later")
    assert board.load(p)["baking"][0]["priority"] == "later"
    view._move_card(view._board["baking"][0], "done")
    on_disk = board.load(p)["baking"][0]
    assert on_disk["done"] is True
    view._move_card(view._board["baking"][0], "now")  # out of Done reopens it
    on_disk = board.load(p)["baking"][0]
    assert (on_disk["priority"], on_disk["done"]) == ("now", False)


@pytest.mark.usefixtures("qapp")
def test_kanban_remove_deletes_from_the_file(tmp_path: Path) -> None:
    p = tmp_path / board.FILENAME
    board.save(p, board.default_board("myapp"))
    view = board._make_view(p)
    before = len(view._board["baking"])
    view._remove_item("baking", view._board["baking"][0])
    assert len(board.load(p)["baking"]) == before - 1


@pytest.mark.usefixtures("qapp")
def test_purpose_edits_write_the_file(tmp_path: Path) -> None:
    p = tmp_path / board.FILENAME
    board.save(p, board.default_board("myapp"))
    view = board._make_view(p)
    view._purpose.setPlainText("boiled down")
    assert board.load(p)["purpose"] == "boiled down"


# ── the project switcher + the wind-down request ─────────────────────────────


def test_discover_projects_finds_home_and_siblings(tmp_path: Path) -> None:
    home = tmp_path / "dough"
    sib = tmp_path / "butterpdf"
    plain = tmp_path / "not-a-loaf"
    for d in (home, sib, plain):
        d.mkdir()
    (home / "pyproject.toml").write_text("")
    (sib / "pyproject.toml").write_text("")
    board.save(home / "dough-breadboard.toml", board.default_board("dough"))
    board.save(sib / "butterpdf-breadboard.toml", board.default_board("butterPDF"))
    (plain / "readme.txt").write_text("no pyproject, no board")

    found = board.discover_projects(home)
    assert [name for name, _ in found] == ["dough", "butterPDF"]  # home first
    assert found[0][1].parent == home


def test_agent_request_round_trips(tmp_path: Path) -> None:
    p = tmp_path / board.FILENAME
    b = board.default_board("x")
    b["agent_request"] = "wind down — requested by the maker 2026-07-08"
    board.save(p, b)
    assert board.load(p)["agent_request"].startswith("wind down")
    b["agent_request"] = ""  # the agent clears it after fulfilment
    board.save(p, b)
    assert board.load(p)["agent_request"] == ""


@pytest.mark.usefixtures("qapp")
def test_wind_down_button_writes_the_request(tmp_path: Path, monkeypatch) -> None:
    p = tmp_path / board.FILENAME
    board.save(p, board.default_board("x"))
    view = board._make_view(p)
    view._request_wind_down()
    assert "wind down" in board.load(p)["agent_request"]


@pytest.mark.usefixtures("qapp")
def test_set_project_switches_the_bench(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    for d in (a, b):
        d.mkdir()
        (d / "pyproject.toml").write_text("")
    pa = a / "a-breadboard.toml"
    pb = b / "b-breadboard.toml"
    ba = board.default_board("appA")
    ba["goal"] = "goal A"
    board.save(pa, ba)
    bb = board.default_board("appB")
    bb["goal"] = "goal B"
    board.save(pb, bb)

    view = board._make_view(pa)
    assert view._goal.text() == "goal A"
    view.set_project(pb)
    assert view._goal.text() == "goal B"
    assert view._board["product"] == "appB"
    # edits after the switch land in the NEW project's file
    view._set_done(view._board["ingredients"][0], True)
    assert board.load(pb)["ingredients"][0]["done"] is True
    assert board.load(pa)["ingredients"][0]["done"] is False


# ── v2: stable ids + omit-empty serializer (the moat's foundation) ───────────


def test_every_item_gets_a_stable_id(tmp_path: Path) -> None:
    p = tmp_path / board.FILENAME
    b = board.default_board("x")
    board.save(p, b)
    loaded = board.load(p)
    ids = [it["id"] for ph in board.PHASES for it in loaded[ph]]
    assert all(ids) and len(ids) == len(set(ids))  # present + unique


def test_ids_survive_edits_and_reorder(tmp_path: Path) -> None:
    p = tmp_path / board.FILENAME
    b = board.default_board("x")
    board.save(p, b)
    b = board.load(p)
    first = b["baking"][0]["id"]
    b["baking"].reverse()            # reorder
    b["baking"][0]["note"] = "edit"  # edit another
    board.save(p, b)
    after = {it["id"] for it in board.load(p)["baking"]}
    assert first in after  # the id followed its item, not its position


def test_omit_empty_keeps_the_file_skimmable(tmp_path: Path) -> None:
    p = tmp_path / board.FILENAME
    b = board.default_board("x")
    b["ingredients"][0]["note"] = "keep me"
    board.save(p, b)
    text = p.read_text()
    # a blank by/date/note writes NO line; the one real note survives
    assert 'note = "keep me"' in text
    assert 'note = ""' not in text and 'by = ""' not in text
    assert board.load(p)["ingredients"][0]["note"] == "keep me"


def test_schema1_file_upgrades_on_next_save(tmp_path: Path) -> None:
    """A hand-written schema-1 board (no ids) loads, then gains ids + schema 2
    the first time it's saved — no migration step, no data loss."""
    p = tmp_path / board.FILENAME
    p.write_text(
        'schema = 1\ngoal = "g"\n[[baking]]\ntext = "old item"\ndone = false\n',
        encoding="utf-8",
    )
    b = board.load(p)
    assert b["baking"][0].get("id") in (None, "")  # not yet minted
    board.save(p, b)
    reloaded = board.load(p)
    assert reloaded["schema"] == 2
    assert reloaded["baking"][0]["id"]
    assert reloaded["baking"][0]["text"] == "old item"
