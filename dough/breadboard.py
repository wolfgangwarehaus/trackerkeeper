"""``dough breadboard`` — the live maker surface (docs/TODO.md §THE BREADBOARD).

The board is the thing the maker INTERACTS WITH during each step of building
with dough: one frosted window, one tab per phase (Ingredients → Baking →
Delivery → Improvements), holding the goals and checklists of the product.
Jump back to adjust the brief (logo, definitions), forward to scout delivery
channels. The AI agent fills and updates it; the maker checks, unchecks, and
leaves notes — and the agent RE-INGESTS those as directives (the protocol
lives in AGENTS.md).

**State is a file; the window is a view.** ``dough-breadboard.toml`` sits in the
checkout root, git-tracked, human-editable, AI-writable — the file is the API
between maker, window, and agent (the same two-way-door philosophy as the sync
manifest). The window file-watches and live-reloads on outside edits; its own
edits write straight back. No daemon, no IPC.

Schema (v1): ``schema``/``product``/``goal`` scalars, then one array-of-tables
per phase — items with ``text``, ``done``, ``by``, ``date``, ``note``. tomllib
reads it; :func:`save` emits it deterministically (no TOML-writer dependency).
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from datetime import date
from pathlib import Path

PHASES = ("ingredients", "baking", "delivery", "improvements")
_PHASE_TITLES = {
    "ingredients": "Ingredients",
    "baking": "Baking",
    "delivery": "Delivery",
    "improvements": "Improvements",
}

# The package this tool ships in — a fork's whole-word rename keeps it correct.
_PKG = (__package__ or "dough").split(".")[0]

# The board file is named after the APP (dough-breadboard.toml here, myapp-breadboard.toml
# in a fork) — derived from the package, not a literal, so the fork rename can't
# half-apply it (module docstrings say "dough-breadboard.toml" but mean this).
FILENAME = f"{_PKG}-breadboard.toml"


# ── the file half ────────────────────────────────────────────────────────────


def repo_root() -> Path:
    """The checkout root (nearest pyproject.toml above this file) — the board
    belongs to the repo, like the rig goldens."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


def board_path() -> Path:
    return repo_root() / FILENAME


def load(path: Path) -> dict:
    """The parsed board, with every phase key present (missing → empty)."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    for phase in PHASES:
        data.setdefault(phase, [])
    data.setdefault("schema", 1)
    data.setdefault("product", _PKG)
    data.setdefault("goal", "")
    return data


def _toml_str(s: str) -> str:
    """A one-line TOML basic string."""
    escaped = (
        str(s).replace("\\", "\\\\").replace('"', '\\"')
        .replace("\n", "\\n").replace("\t", "\\t")
    )
    return f'"{escaped}"'


def save(path: Path, board: dict) -> None:
    """Deterministic emit of the v1 schema — same input, same bytes, so git
    diffs stay honest and the agent/window never fight over formatting."""
    lines = [
        "# The breadboard — the live maker surface. The WINDOW (`{0}-breadboard`) and".format(_PKG),
        "# the AI AGENT both read and write this file; your edits here are directives",
        "# the agent re-ingests (see AGENTS.md). Git-tracked on purpose.",
        "",
        f"schema = {int(board.get('schema', 1))}",
        f"product = {_toml_str(board.get('product', _PKG))}",
        f"goal = {_toml_str(board.get('goal', ''))}",
    ]
    for phase in PHASES:
        for item in board.get(phase, []):
            lines += [
                "",
                f"[[{phase}]]",
                f"text = {_toml_str(item.get('text', ''))}",
                f"done = {'true' if item.get('done') else 'false'}",
                f"by = {_toml_str(item.get('by', ''))}",
                f"date = {_toml_str(item.get('date', ''))}",
                f"note = {_toml_str(item.get('note', ''))}",
            ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_board(product: str) -> dict:
    """A fresh board seeded with the maker workflow — the Ingredients list IS
    the brief's checklist; later phases start with their skeleton laps."""

    def items(*texts: str) -> list[dict]:
        return [{"text": t, "done": False, "by": "", "date": "", "note": ""} for t in texts]

    return {
        "schema": 1,
        "product": product,
        "goal": f"Ship {product} to real users through the Delivery matrix.",
        "ingredients": items(
            "Name + slug settled (dough new done)",
            "One-line summary + long description written into the sidecar",
            "Brand: logo SVG replaced, accent colour picked",
            "Definitions: who is this for, what does v1 do (the brief)",
            "Feature list drafted — MVP #1 chosen",
            "Delivery targets chosen (which channels matter for THIS app)",
        ),
        "baking": items(
            "MVP #1 built and boots (rig boot green)",
            "Tests green + ruff clean + bake --check clean",
            "First-looks polish pass on the real desktop",
            "rig baseline goldens baked (the visual-bump gate)",
        ),
        "delivery": items(
            "Version tagged (the tag IS the version)",
            "Release drafted by release.yml, reviewed, PUBLISHED",
            "Channels activated one by one (the `deliver` walkthroughs)",
        ),
        "improvements": items(
            "Pull base updates (sync_loaf) and re-verify",
            "Refine → re-bake → re-deliver: the forever lap",
        ),
    }


# ── the window half ──────────────────────────────────────────────────────────


def _make_view(path: Path):
    """The board window content. Imported lazily so the file half stays
    importable headless (tests, agents)."""
    from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer
    from PySide6.QtWidgets import (
        QCheckBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QScrollArea,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )

    from dough import ui_helpers
    from dough.design_tokens import TYPE_BODY, TYPE_DISPLAY, type_qss

    accent = ui_helpers.ACCENT

    class BoardView(QWidget):
        """Tabs across the phases; every interaction writes the file."""

        def __init__(self) -> None:
            super().__init__()
            self._path = Path(path)
            self._board = load(self._path)
            self._writing = False

            root = QVBoxLayout(self)
            root.setContentsMargins(18, 12, 18, 12)
            root.setSpacing(10)

            self._goal = QLabel(self._board.get("goal", ""))
            self._goal.setWordWrap(True)
            self._goal.setStyleSheet(type_qss(TYPE_DISPLAY) + "color:#ddd;")
            root.addWidget(self._goal)

            # the phase pills — jump anywhere: back to the brief, forward to delivery
            pills = QHBoxLayout()
            pills.setSpacing(6)
            self._pill_buttons: dict[str, QPushButton] = {}
            self._stack = QStackedWidget()
            for phase in PHASES:
                b = QPushButton(_PHASE_TITLES[phase])
                b.setCheckable(True)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setStyleSheet(
                    "QPushButton{border:1px solid rgba(255,255,255,0.16);"
                    "border-radius:14px;padding:5px 14px;background:transparent;color:#bbb;}"
                    f"QPushButton:checked{{background:{accent};color:#fff;"
                    f"border-color:{accent};}}"
                )
                b.clicked.connect(lambda _=False, ph=phase: self._show_phase(ph))
                pills.addWidget(b)
                self._pill_buttons[phase] = b
            pills.addStretch(1)
            root.addLayout(pills)
            root.addWidget(self._stack, 1)

            self._pages: dict[str, QWidget] = {}
            self._rebuild_pages()
            self._show_phase(self._first_open_phase())

            # outside edits (the agent, an editor, git) reload the view live
            self._watcher = QFileSystemWatcher([str(self._path)])
            self._watcher.fileChanged.connect(self._on_file_changed)
            self._rewatch = QTimer(self)
            self._rewatch.setSingleShot(True)
            self._rewatch.timeout.connect(self._ensure_watched)

        # ── phases ────────────────────────────────────────────────────────
        def _first_open_phase(self) -> str:
            for phase in PHASES:  # land the maker on the working phase
                if any(not i.get("done") for i in self._board.get(phase, [])):
                    return phase
            return PHASES[0]

        def _show_phase(self, phase: str) -> None:
            for ph, b in self._pill_buttons.items():
                b.setChecked(ph == phase)
            self._stack.setCurrentWidget(self._pages[phase])

        def _rebuild_pages(self) -> None:
            current = None
            for ph, b in self._pill_buttons.items():
                if b.isChecked():
                    current = ph
            while self._stack.count():
                w = self._stack.widget(0)
                self._stack.removeWidget(w)
                w.deleteLater()
            self._pages = {}
            for phase in PHASES:
                page = self._build_page(phase)
                self._pages[phase] = page
                self._stack.addWidget(page)
            if current:
                self._show_phase(current)

        def _build_page(self, phase: str) -> QWidget:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            inner = QWidget()
            vbox = QVBoxLayout(inner)
            vbox.setContentsMargins(2, 4, 2, 4)
            vbox.setSpacing(6)
            for item in self._board.get(phase, []):
                vbox.addLayout(self._build_row(phase, item))
            adder = QLineEdit()
            adder.setPlaceholderText(f"add a {_PHASE_TITLES[phase].lower()} item…")
            adder.setStyleSheet(
                "QLineEdit{background:rgba(255,255,255,0.06);border:1px solid "
                "rgba(255,255,255,0.12);border-radius:6px;padding:4px 8px;color:#ddd;}"
            )
            adder.returnPressed.connect(
                lambda ph=phase, e=adder: self._add_item(ph, e.text())
            )
            vbox.addWidget(adder)
            vbox.addStretch(1)
            scroll.setWidget(inner)
            return scroll

        def _build_row(self, phase: str, item: dict):
            from PySide6.QtWidgets import QHBoxLayout

            row = QHBoxLayout()
            row.setSpacing(8)
            box = QCheckBox(item.get("text", ""))
            box.setChecked(bool(item.get("done")))
            box.setStyleSheet(
                type_qss(TYPE_BODY)
                + f"QCheckBox{{color:#ddd;}}QCheckBox::indicator:checked{{background:{accent};"
                f"border:1px solid {accent};border-radius:3px;}}"
                "QCheckBox::indicator{width:14px;height:14px;border:1px solid "
                "rgba(255,255,255,0.35);border-radius:3px;}"
            )
            box.toggled.connect(lambda on, it=item: self._set_done(it, on))
            row.addWidget(box, 1)
            stamp = QLabel(
                f"{item.get('by', '')} {item.get('date', '')}".strip()
            )
            stamp.setStyleSheet("color:#777;font-size:11px;")
            row.addWidget(stamp)
            note = QLineEdit(item.get("note", ""))
            note.setPlaceholderText("note to the agent…")
            note.setFixedWidth(220)
            note.setStyleSheet(
                "QLineEdit{background:rgba(255,255,255,0.05);border:1px solid "
                "rgba(255,255,255,0.10);border-radius:6px;padding:3px 8px;color:#cbb8ff;}"
            )
            note.editingFinished.connect(
                lambda it=item, e=note: self._set_note(it, e.text())
            )
            row.addWidget(note)
            return row

        # ── edits (every one writes the file) ─────────────────────────────
        def _stamp(self, item: dict) -> None:
            item["by"] = "maker"
            item["date"] = date.today().isoformat()

        def _set_done(self, item: dict, on: bool) -> None:
            item["done"] = on
            self._stamp(item)
            self._write()

        def _set_note(self, item: dict, text: str) -> None:
            if item.get("note", "") == text:
                return
            item["note"] = text
            self._stamp(item)
            self._write()

        def _add_item(self, phase: str, text: str) -> None:
            text = text.strip()
            if not text:
                return
            self._board.setdefault(phase, []).append(
                {"text": text, "done": False, "by": "maker",
                 "date": date.today().isoformat(), "note": ""}
            )
            self._write()
            self._rebuild_pages()
            self._show_phase(phase)

        def _write(self) -> None:
            self._writing = True
            save(self._path, self._board)
            self._rewatch.start(200)  # editors/agents may replace the inode

        # ── live reload on outside edits ──────────────────────────────────
        def _ensure_watched(self) -> None:
            self._writing = False
            if str(self._path) not in self._watcher.files():
                self._watcher.addPath(str(self._path))

        def _on_file_changed(self, *_):
            self._rewatch.start(200)
            if self._writing:
                return  # our own write echoing back
            try:
                self._board = load(self._path)
            except Exception:
                return  # mid-edit / malformed — keep showing the last good state
            self._goal.setText(self._board.get("goal", ""))
            self._rebuild_pages()

    return BoardView()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{_PKG}-breadboard",
        description="The live maker board: goals + phase checklists, shared with the AI agent.",
    )
    parser.add_argument("--init", action="store_true",
                        help="seed a fresh dough-breadboard.toml (refuses to overwrite)")
    args = parser.parse_args(argv)

    path = board_path()
    if args.init:
        if path.exists():
            print(f"{path} already exists — not overwriting.", file=sys.stderr)
            return 1
        save(path, default_board(_PKG))
        print(f"seeded {path}. Open it with `{_PKG}-breadboard`.")
        return 0
    if not path.is_file():
        save(path, default_board(_PKG))
        print(f"(no board yet — seeded {path})")

    from dough.app import run_app

    return run_app(lambda window: _make_view(path), single_instance=False)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
