"""``dough breadboard`` — the live maker surface (docs/TODO.md §THE BREADBOARD).

The breadboard is the thing the maker INTERACTS WITH during each step of
building with dough: one frosted window, tabs across the top for the phases —
jump back to the brief, forward to the delivery channels. The AI agent fills
and updates it; the maker checks, unchecks, moves cards and leaves notes — and
the agent RE-INGESTS those as directives (the protocol lives in AGENTS.md).

Each phase gets its own shape (August's design, 2026-07-08):

* **Ingredients** — the app summary page: logo + name + summary from the
  metadata sidecar, an editable "purpose" (boil the app down), the feature
  cards, then the brief's checklist.
* **Baking** — a kanban: priority columns (Now / Next / Later / Done); cards
  move with ◀ ▶, complete with ✓, delete with ✕; the agent populates, the
  maker steers.
* **Delivery** — the real channel list from ``deliver``: per-platform steps
  with DETECTED states, links, and the next action's guide.
* **Improvements** — the forever-lap checklist.

**State is a file; the window is a view.** ``<slug>-breadboard.toml`` sits in
the checkout root, git-tracked, human-editable, AI-writable — the file is the
API between maker, window, and agent (the same two-way-door philosophy as the
sync manifest). The window file-watches and live-reloads on outside edits; its
own edits write straight back. No daemon, no IPC.

Schema (v1): ``schema``/``product``/``goal``/``purpose`` scalars, then one
array-of-tables per phase — items with ``text``, ``done``, ``by``, ``date``,
``note``, and (baking only) ``priority`` in {now, next, later}. tomllib reads
it; :func:`save` emits it deterministically (no TOML-writer dependency).
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
PRIORITIES = ("now", "next", "later")

# The package this tool ships in — a fork's whole-word rename keeps it correct.
_PKG = (__package__ or "dough").split(".")[0]

# The board file is named after the APP (dough-breadboard.toml here,
# myapp-breadboard.toml in a fork) — derived from the package, not a literal,
# so the fork rename can't half-apply it.
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
    """The parsed board, with every phase key present (missing → empty) and
    baking items carrying a priority."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    for phase in PHASES:
        data.setdefault(phase, [])
    data.setdefault("schema", 1)
    data.setdefault("product", _PKG)
    data.setdefault("goal", "")
    data.setdefault("purpose", "")
    for item in data["baking"]:
        if item.get("priority") not in PRIORITIES:
            item["priority"] = "next"
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
        f"purpose = {_toml_str(board.get('purpose', ''))}",
    ]
    for phase in PHASES:
        for item in board.get(phase, []):
            lines += [
                "",
                f"[[{phase}]]",
                f"text = {_toml_str(item.get('text', ''))}",
                f"done = {'true' if item.get('done') else 'false'}",
            ]
            if phase == "baking":
                prio = item.get("priority", "next")
                lines.append(
                    f"priority = {_toml_str(prio if prio in PRIORITIES else 'next')}"
                )
            lines += [
                f"by = {_toml_str(item.get('by', ''))}",
                f"date = {_toml_str(item.get('date', ''))}",
                f"note = {_toml_str(item.get('note', ''))}",
            ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_board(product: str) -> dict:
    """A fresh board seeded with the maker workflow — the Ingredients list IS
    the brief's checklist; later phases start with their skeleton laps."""

    def items(*texts: str, prio: str | None = None) -> list[dict]:
        out = [{"text": t, "done": False, "by": "", "date": "", "note": ""} for t in texts]
        if prio:
            for it in out:
                it["priority"] = prio
        return out

    return {
        "schema": 1,
        "product": product,
        "goal": f"Ship {product} to real users through the Delivery matrix.",
        "purpose": "",
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
            prio="now",
        )
        + items(
            "First-looks polish pass on the real desktop",
            "rig baseline goldens baked (the visual-bump gate)",
            prio="next",
        ),
        "delivery": items(
            "Version tagged (the tag IS the version)",
            "Release drafted by release.yml, reviewed, PUBLISHED",
        ),
        "improvements": items(
            "Pull base updates (sync_loaf) and re-verify",
            "Refine → re-bake → re-deliver: the forever lap",
        ),
    }


def _sidecar() -> dict:
    """The metadata sidecar (display name, summary, feature cards, icon path)
    for the Ingredients summary card — degrades to package-name basics when
    unavailable (installed wheel, malformed pyproject)."""
    try:
        from dough import metadata

        meta = metadata.load()
        return {
            "display_name": meta.get("display_name", _PKG),
            "summary": meta.get("summary", ""),
            "feature_cards": meta.get("feature_cards", []),
            "icon": str(repo_root() / meta.get("icon_svg_source", "")),
        }
    except Exception:
        return {"display_name": _PKG, "summary": "", "feature_cards": [], "icon": ""}


# ── the window half ──────────────────────────────────────────────────────────


def _make_view(path: Path):
    """The breadboard window content. Imported lazily so the file half stays
    importable headless (tests, agents)."""
    import re

    from PySide6.QtCore import QFileSystemWatcher, Qt, QThread, QTimer, Signal
    from PySide6.QtGui import QDesktopServices, QPixmap
    from PySide6.QtWidgets import (
        QCheckBox,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )

    from dough import ui_helpers
    from dough.design_tokens import TYPE_BODY, TYPE_DISPLAY, type_qss

    accent = ui_helpers.ACCENT

    _EDIT_QSS = (
        "background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);"
        "border-radius:6px;padding:4px 8px;color:#ddd;"
    )
    _CARD_QSS = (
        "QFrame{background:rgba(255,255,255,0.045);border:1px solid "
        "rgba(255,255,255,0.10);border-radius:10px;}"
    )

    def _linkify(text: str) -> str:
        import html

        escaped = html.escape(text)
        escaped = re.sub(
            r"(https?://[^\s<]+)",
            rf'<a href="\1" style="color:{accent};">\1</a>',
            escaped,
        )
        return escaped.replace("\n", "<br>")

    class _ChannelProbe(QThread):
        """deliver's detections hit git/gh/the network — never on the UI
        thread. Emits [(title, note, alert, [(step_title, state)], guide)],
        or the exception when probing itself failed."""

        ready = Signal(object)

        def run(self) -> None:  # noqa: N802 (Qt override)
            try:
                from dough import deliver

                ctx = deliver._ctx()
                rows = []
                for ch in deliver._channels():
                    states = ch.states(ctx)
                    guide = ""
                    for step, st in zip(ch.steps, states, strict=True):
                        if st is not True:
                            guide = step.guide(ctx)
                            break
                    rows.append(
                        (ch.title, ch.note, ch.alert(ctx),
                         [(s.title, st) for s, st in zip(ch.steps, states, strict=True)], guide)
                    )
                self.ready.emit(rows)
            except Exception as exc:  # pragma: no cover - defensive
                self.ready.emit(exc)

    class BoardView(QWidget):
        """Tabs across the top; every interaction writes the file."""

        def __init__(self) -> None:
            super().__init__()
            self._path = Path(path)
            self._board = load(self._path)
            self._writing = False
            self._probe: _ChannelProbe | None = None
            self._channel_rows = None  # probed on first Delivery open; Refresh re-runs

            root = QVBoxLayout(self)
            root.setContentsMargins(16, 10, 16, 12)
            root.setSpacing(10)

            # ── the tabs, ACROSS THE TOP, sharing the full width ─────────
            pills = QHBoxLayout()
            pills.setSpacing(6)
            self._pill_buttons: dict[str, QPushButton] = {}
            for phase in PHASES:
                b = QPushButton(_PHASE_TITLES[phase])
                b.setCheckable(True)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setMinimumHeight(30)
                b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                b.setStyleSheet(
                    "QPushButton{border:1px solid rgba(255,255,255,0.16);"
                    "border-radius:15px;padding:5px 10px;background:transparent;color:#bbb;}"
                    f"QPushButton:checked{{background:{accent};color:#fff;"
                    f"border-color:{accent};}}"
                )
                b.clicked.connect(lambda _=False, ph=phase: self._show_phase(ph))
                pills.addWidget(b, 1)
                self._pill_buttons[phase] = b
            root.addLayout(pills)

            self._goal = QLabel(self._board.get("goal", ""))
            self._goal.setWordWrap(True)
            self._goal.setStyleSheet(type_qss(TYPE_DISPLAY) + "color:#ddd;")
            root.addWidget(self._goal)

            self._stack = QStackedWidget()
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
            if phase == "delivery" and self._channel_rows is None:
                self._start_probe()

        def _rebuild_pages(self) -> None:
            current = None
            for ph, b in self._pill_buttons.items():
                if b.isChecked():
                    current = ph
            while self._stack.count():
                w = self._stack.widget(0)
                self._stack.removeWidget(w)
                w.deleteLater()
            self._pages = {
                "ingredients": self._build_ingredients(),
                "baking": self._build_baking(),
                "delivery": self._build_delivery(),
                "improvements": self._build_checklist_page("improvements"),
            }
            for phase in PHASES:
                self._stack.addWidget(self._pages[phase])
            if current:
                self._show_phase(current)

        @staticmethod
        def _scroll(inner: QWidget) -> QScrollArea:
            s = QScrollArea()
            s.setWidgetResizable(True)
            s.setFrameShape(QFrame.Shape.NoFrame)
            s.setWidget(inner)
            return s

        # ── Ingredients: the app summary page ─────────────────────────────
        def _build_ingredients(self) -> QWidget:
            side = _sidecar()
            inner = QWidget()
            vbox = QVBoxLayout(inner)
            vbox.setContentsMargins(2, 4, 2, 4)
            vbox.setSpacing(10)

            card = QFrame()
            card.setStyleSheet(_CARD_QSS)
            head = QHBoxLayout(card)
            head.setContentsMargins(14, 12, 14, 12)
            head.setSpacing(14)
            logo = QLabel()
            pm = QPixmap(side["icon"]) if side["icon"] else QPixmap()
            if not pm.isNull():
                logo.setPixmap(pm.scaled(
                    64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
            else:
                logo.setText("◌")
                logo.setStyleSheet("font-size:40px;color:#666;")
            head.addWidget(logo)
            names = QVBoxLayout()
            title = QLabel(side["display_name"])
            title.setStyleSheet(type_qss(TYPE_DISPLAY) + "color:#fff;")
            names.addWidget(title)
            summary = QLabel(side["summary"])
            summary.setWordWrap(True)
            summary.setStyleSheet("color:#aaa;")
            names.addWidget(summary)
            head.addLayout(names, 1)
            brand = QPushButton("Brand assets…")
            brand.setToolTip("Open the assets folder (the logo SVG lives there)")
            brand.setCursor(Qt.CursorShape.PointingHandCursor)
            brand.setStyleSheet(
                "QPushButton{border:1px solid rgba(255,255,255,0.2);border-radius:8px;"
                "padding:6px 12px;background:transparent;color:#ccc;}"
                f"QPushButton:hover{{border-color:{accent};color:#fff;}}"
            )
            brand.clicked.connect(self._open_brand_assets)
            head.addWidget(brand)
            vbox.addWidget(card)

            purpose_label = QLabel("Purpose — boil the app down (the agent reads this)")
            purpose_label.setStyleSheet("color:#888;")
            vbox.addWidget(purpose_label)
            self._purpose = QPlainTextEdit(self._board.get("purpose", ""))
            self._purpose.setPlaceholderText(
                "Who is this for? What does v1 do? What is deliberately out?")
            self._purpose.setFixedHeight(84)
            self._purpose.setStyleSheet(f"QPlainTextEdit{{{_EDIT_QSS}}}")
            self._purpose.textChanged.connect(self._purpose_changed)
            vbox.addWidget(self._purpose)

            if side["feature_cards"]:
                feats = QLabel("Major features")
                feats.setStyleSheet("color:#888;")
                vbox.addWidget(feats)
                for fc in side["feature_cards"]:
                    lab = QLabel(f"•  <b>{fc.get('title', '')}</b> — {fc.get('body', '')}")
                    lab.setWordWrap(True)
                    lab.setTextFormat(Qt.TextFormat.RichText)
                    lab.setStyleSheet("color:#bbb;")
                    vbox.addWidget(lab)

            checklist = QLabel("The brief's checklist")
            checklist.setStyleSheet("color:#888;")
            vbox.addWidget(checklist)
            for item in self._board.get("ingredients", []):
                vbox.addLayout(self._build_check_row(item))
            vbox.addWidget(self._build_adder("ingredients"))
            vbox.addStretch(1)
            return self._scroll(inner)

        def _open_brand_assets(self) -> None:
            from PySide6.QtCore import QUrl

            assets = repo_root() / _PKG / "assets"
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(assets)))

        def _purpose_changed(self) -> None:
            self._board["purpose"] = self._purpose.toPlainText()
            self._write()

        # ── Baking: the kanban ─────────────────────────────────────────────
        def _build_baking(self) -> QWidget:
            inner = QWidget()
            row = QHBoxLayout(inner)
            row.setContentsMargins(2, 4, 2, 4)
            row.setSpacing(10)
            titles = {"now": "Now", "next": "Next", "later": "Later", "done": "Done ✓"}
            for col in (*PRIORITIES, "done"):
                frame = QFrame()
                frame.setStyleSheet(_CARD_QSS)
                v = QVBoxLayout(frame)
                v.setContentsMargins(10, 8, 10, 8)
                v.setSpacing(6)
                head = QLabel(titles[col])
                head.setStyleSheet(
                    f"color:{'#8f8' if col == 'done' else '#fff'};font-weight:bold;")
                v.addWidget(head)
                for item in self._board.get("baking", []):
                    in_col = (item.get("done") and col == "done") or (
                        not item.get("done") and item.get("priority") == col)
                    if in_col:
                        v.addWidget(self._build_card(item, col))
                if col != "done":
                    adder = QLineEdit()
                    adder.setPlaceholderText("add…")
                    adder.setStyleSheet(f"QLineEdit{{{_EDIT_QSS}}}")
                    adder.returnPressed.connect(
                        lambda c=col, e=adder: self._add_item("baking", e.text(), priority=c))
                    v.addWidget(adder)
                v.addStretch(1)
                row.addWidget(frame, 1)
            return self._scroll(inner)

        def _build_card(self, item: dict, col: str) -> QWidget:
            card = QFrame()
            done = col == "done"
            card.setStyleSheet(
                "QFrame{background:rgba(255,255,255,0.06);border:1px solid "
                + ("rgba(140,255,140,0.25)" if done else "rgba(255,255,255,0.14)")
                + ";border-radius:8px;}"
            )
            v = QVBoxLayout(card)
            v.setContentsMargins(8, 6, 8, 6)
            v.setSpacing(4)
            lab = QLabel(item.get("text", ""))
            lab.setWordWrap(True)
            lab.setStyleSheet(
                type_qss(TYPE_BODY) + ("color:#9a9;" if done else "color:#ddd;"))
            v.addWidget(lab)
            stamp = f"{item.get('by', '')} {item.get('date', '')}".strip()
            if stamp or item.get("note"):
                meta = QLabel(stamp + ("  ·  " + item["note"] if item.get("note") else ""))
                meta.setWordWrap(True)
                meta.setStyleSheet("color:#777;font-size:11px;")
                v.addWidget(meta)
            btns = QHBoxLayout()
            btns.setSpacing(4)

            def _mini(text, tip, slot, disabled=False):
                b = QPushButton(text)
                b.setFixedSize(24, 20)
                b.setToolTip(tip)
                b.setEnabled(not disabled)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setStyleSheet(
                    "QPushButton{border:none;border-radius:4px;color:#999;"
                    "background:rgba(255,255,255,0.06);}"
                    f"QPushButton:hover{{color:#fff;background:{accent};}}"
                    "QPushButton:disabled{color:#444;}")
                b.clicked.connect(slot)
                btns.addWidget(b)

            order = [*PRIORITIES, "done"]
            i = order.index(col)
            _mini("◀", "move left", lambda: self._move_card(item, order[max(0, i - 1)]),
                  disabled=i == 0)
            _mini("▶", "move right",
                  lambda: self._move_card(item, order[min(len(order) - 1, i + 1)]),
                  disabled=i == len(order) - 1)
            if not done:
                _mini("✓", "done", lambda: self._move_card(item, "done"))
            _mini("✕", "remove", lambda: self._remove_item("baking", item))
            btns.addStretch(1)
            v.addLayout(btns)
            return card

        def _move_card(self, item: dict, col: str) -> None:
            item["done"] = col == "done"
            if col in PRIORITIES:
                item["priority"] = col
            self._stamp(item)
            self._write()
            self._rebuild_pages()

        def _remove_item(self, phase: str, item: dict) -> None:
            self._board[phase] = [i for i in self._board.get(phase, []) if i is not item]
            self._write()
            self._rebuild_pages()

        # ── Delivery: the platform checklist (deliver's detections) ───────
        def _build_delivery(self) -> QWidget:
            inner = QWidget()
            v = QVBoxLayout(inner)
            v.setContentsMargins(2, 4, 2, 4)
            v.setSpacing(10)
            bar = QHBoxLayout()
            self._delivery_status = QLabel("")
            self._delivery_status.setStyleSheet("color:#888;")
            bar.addWidget(self._delivery_status)
            bar.addStretch(1)
            refresh = QPushButton("Refresh")
            refresh.setCursor(Qt.CursorShape.PointingHandCursor)
            refresh.setStyleSheet(
                "QPushButton{border:1px solid rgba(255,255,255,0.2);border-radius:8px;"
                "padding:4px 12px;background:transparent;color:#ccc;}"
                f"QPushButton:hover{{border-color:{accent};}}")
            refresh.clicked.connect(self._start_probe)
            bar.addWidget(refresh)
            v.addLayout(bar)

            self._channels_box = QVBoxLayout()
            self._channels_box.setSpacing(8)
            v.addLayout(self._channels_box)
            if self._channel_rows is not None:
                self._render_channels(self._channel_rows)

            extra = QLabel("Extra delivery items")
            extra.setStyleSheet("color:#888;")
            v.addWidget(extra)
            for item in self._board.get("delivery", []):
                v.addLayout(self._build_check_row(item))
            v.addWidget(self._build_adder("delivery"))
            v.addStretch(1)
            return self._scroll(inner)

        def _start_probe(self) -> None:
            if self._probe and self._probe.isRunning():
                return
            self._delivery_status.setText("probing channels…")
            self._probe = _ChannelProbe(self)
            self._probe.ready.connect(self._on_probe_ready)
            self._probe.start()

        def _on_probe_ready(self, rows) -> None:
            if isinstance(rows, Exception):
                self._delivery_status.setText(f"probe failed: {rows}")
                return
            self._channel_rows = rows
            self._delivery_status.setText(
                "detected state — ✓ done · ▶ next · ? unknowable from here")
            self._render_channels(rows)

        def _render_channels(self, rows) -> None:
            while self._channels_box.count():
                it = self._channels_box.takeAt(0)
                if it.widget():
                    it.widget().deleteLater()
            marks = {True: ("✓", "#8f8"), False: ("▶", accent), None: ("?", "#888")}
            for title, note, alert, steps, guide in rows:
                card = QFrame()
                card.setStyleSheet(_CARD_QSS)
                cv = QVBoxLayout(card)
                cv.setContentsMargins(12, 8, 12, 8)
                cv.setSpacing(4)
                head = QLabel(title + (f"   —   ⚠ {alert}" if alert else ""))
                head.setStyleSheet(
                    "color:#f88;font-weight:bold;" if alert
                    else "color:#fff;font-weight:bold;")
                cv.addWidget(head)
                if note:
                    n = QLabel(note)
                    n.setWordWrap(True)
                    n.setStyleSheet("color:#888;font-size:11px;")
                    cv.addWidget(n)
                for step_title, st in steps:
                    mark, color = marks.get(st, ("?", "#888"))
                    s = QLabel(f'<span style="color:{color};">{mark}</span>  {step_title}')
                    s.setTextFormat(Qt.TextFormat.RichText)
                    s.setStyleSheet("color:#ccc;")
                    cv.addWidget(s)
                if guide:
                    g = QLabel(_linkify(guide))
                    g.setTextFormat(Qt.TextFormat.RichText)
                    g.setOpenExternalLinks(True)
                    g.setWordWrap(True)
                    g.setTextInteractionFlags(
                        Qt.TextInteractionFlag.TextBrowserInteraction)
                    g.setStyleSheet(
                        "color:#aaa;background:rgba(0,0,0,0.25);border-radius:6px;"
                        "padding:6px;font-family:monospace;font-size:11px;")
                    cv.addWidget(g)
                self._channels_box.addWidget(card)

        # ── shared checklist rows (Ingredients tail + Improvements) ───────
        def _build_checklist_page(self, phase: str) -> QWidget:
            inner = QWidget()
            vbox = QVBoxLayout(inner)
            vbox.setContentsMargins(2, 4, 2, 4)
            vbox.setSpacing(6)
            for item in self._board.get(phase, []):
                vbox.addLayout(self._build_check_row(item))
            vbox.addWidget(self._build_adder(phase))
            vbox.addStretch(1)
            return self._scroll(inner)

        def _build_adder(self, phase: str) -> QLineEdit:
            adder = QLineEdit()
            adder.setPlaceholderText(f"add a {_PHASE_TITLES[phase].lower()} item…")
            adder.setStyleSheet(f"QLineEdit{{{_EDIT_QSS}}}")
            adder.returnPressed.connect(
                lambda ph=phase, e=adder: self._add_item(ph, e.text()))
            return adder

        def _build_check_row(self, item: dict) -> QHBoxLayout:
            row = QHBoxLayout()
            row.setSpacing(8)
            box = QCheckBox(item.get("text", ""))
            box.setChecked(bool(item.get("done")))
            box.setStyleSheet(
                type_qss(TYPE_BODY)
                + f"QCheckBox{{color:#ddd;}}QCheckBox::indicator:checked{{background:{accent};"
                f"border:1px solid {accent};border-radius:3px;}}"
                "QCheckBox::indicator{width:14px;height:14px;border:1px solid "
                "rgba(255,255,255,0.35);border-radius:3px;}")
            box.toggled.connect(lambda on, it=item: self._set_done(it, on))
            row.addWidget(box, 1)
            stamp = QLabel(f"{item.get('by', '')} {item.get('date', '')}".strip())
            stamp.setStyleSheet("color:#777;font-size:11px;")
            row.addWidget(stamp)
            note = QLineEdit(item.get("note", ""))
            note.setPlaceholderText("note to the agent…")
            note.setFixedWidth(220)
            note.setStyleSheet(
                "QLineEdit{background:rgba(255,255,255,0.05);border:1px solid "
                "rgba(255,255,255,0.10);border-radius:6px;padding:3px 8px;color:#cbb8ff;}")
            note.editingFinished.connect(lambda it=item, e=note: self._set_note(it, e.text()))
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

        def _add_item(self, phase: str, text: str, priority: str | None = None) -> None:
            text = text.strip()
            if not text:
                return
            item = {"text": text, "done": False, "by": "maker",
                    "date": date.today().isoformat(), "note": ""}
            if phase == "baking":
                item["priority"] = priority if priority in PRIORITIES else "next"
            self._board.setdefault(phase, []).append(item)
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
            if hasattr(self, "_purpose"):
                if self._purpose.toPlainText() != self._board.get("purpose", ""):
                    self._purpose.blockSignals(True)
                    self._purpose.setPlainText(self._board.get("purpose", ""))
                    self._purpose.blockSignals(False)
            self._rebuild_pages()

    return BoardView()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{_PKG}-breadboard",
        description="The live maker board: goals + phase checklists, shared with the AI agent.",
    )
    parser.add_argument("--init", action="store_true",
                        help=f"seed a fresh {FILENAME} (refuses to overwrite)")
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
