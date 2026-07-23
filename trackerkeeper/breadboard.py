"""``trackerkeeper breadboard`` — the live maker surface (docs/TODO.md §THE BREADBOARD).

The breadboard is the thing the maker INTERACTS WITH during each step of
building with trackerkeeper: one frosted window, tabs across the top for the phases —
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
import secrets
import sys
import tomllib
from datetime import date
from pathlib import Path

SCHEMA = 2  # v2: every item carries a stable `id`; empty fields are omitted
PHASES = ("ingredients", "baking", "delivery", "improvements")
_PHASE_TITLES = {
    "ingredients": "Ingredients",
    "baking": "Baking",
    "delivery": "Delivery",
    "improvements": "Improvements",
}
PRIORITIES = ("now", "next", "later")

# The package this tool ships in — a fork's whole-word rename keeps it correct.
_PKG = (__package__ or "trackerkeeper").split(".")[0]

# The board file is named after the APP (trackerkeeper-breadboard.toml here,
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
    baking items carrying a priority. A schema-1 file (no ids) loads fine —
    ids are minted on the next :func:`save`."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    for phase in PHASES:
        data.setdefault(phase, [])
    data.setdefault("schema", SCHEMA)
    data.setdefault("product", _PKG)
    data.setdefault("goal", "")
    data.setdefault("purpose", "")
    data.setdefault("agent_request", "")
    for item in data["baking"]:
        if item.get("priority") not in PRIORITIES:
            item["priority"] = "next"
    return data


def _new_id() -> str:
    """A short, collision-improbable item id (6 hex chars) — the stable handle
    the agent and git history reference an item by, immune to reordering."""
    return secrets.token_hex(3)


def _ensure_ids(board: dict) -> None:
    """Mint a stable `id` for every item that lacks one (or collides), in
    place. Idempotent: an item that already has a unique id keeps it, so
    ids survive edits, reorders, and round-trips."""
    seen: set[str] = set()
    for phase in PHASES:
        for item in board.get(phase, []):
            iid = item.get("id")
            while not iid or iid in seen:
                iid = _new_id()
            item["id"] = iid
            seen.add(iid)


def discover_projects(home: Path | None = None) -> list[tuple[str, Path]]:
    """(product, board-file) for this checkout AND its sibling checkouts that
    carry a breadboard — the maker's project switcher. The home project is
    always first."""
    home = home or repo_root()
    out: list[tuple[str, Path]] = []
    for d in [home] + sorted(
        p for p in home.parent.iterdir() if p.is_dir() and p != home
    ):
        boards = sorted(d.glob("*-breadboard.toml"))
        if not boards or not (d / "pyproject.toml").is_file():
            continue
        try:
            product = load(boards[0]).get("product", d.name)
        except Exception:
            continue  # malformed board — skip, don't break the switcher
        out.append((product, boards[0]))
    return out


def _toml_str(s: str) -> str:
    """A one-line TOML basic string."""
    escaped = (
        str(s).replace("\\", "\\\\").replace('"', '\\"')
        .replace("\n", "\\n").replace("\t", "\\t")
    )
    return f'"{escaped}"'


def save(path: Path, board: dict) -> None:
    """Deterministic emit — same input, same bytes, so git diffs stay honest
    and the agent/window never fight over formatting. Mints stable ids first
    (see :func:`_ensure_ids`) and OMITS empty ``by``/``date``/``note`` so the
    file stays skimmable and hand-editable — "the file IS the API" only holds
    while a human still wants to open it."""
    _ensure_ids(board)
    lines = [
        "# The breadboard — the live maker surface. The WINDOW (`{0}-breadboard`) and".format(_PKG),
        "# the AI AGENT both read and write this file; your edits here are directives",
        "# the agent re-ingests (see AGENTS.md). Git-tracked on purpose.",
        "",
        # a save always emits the CURRENT format, so it declares the current
        # schema — this is how a hand-written schema-1 file upgrades on write
        f"schema = {SCHEMA}",
        f"product = {_toml_str(board.get('product', _PKG))}",
        f"goal = {_toml_str(board.get('goal', ''))}",
        f"purpose = {_toml_str(board.get('purpose', ''))}",
        # the maker's direct line: "wind down" etc. — the agent fulfils + clears
        f"agent_request = {_toml_str(board.get('agent_request', ''))}",
    ]
    for phase in PHASES:
        for item in board.get(phase, []):
            lines += [
                "",
                f"[[{phase}]]",
                f"id = {_toml_str(item['id'])}",
                f"text = {_toml_str(item.get('text', ''))}",
                f"done = {'true' if item.get('done') else 'false'}",
            ]
            if phase == "baking":
                prio = item.get("priority", "next")
                lines.append(
                    f"priority = {_toml_str(prio if prio in PRIORITIES else 'next')}"
                )
            for key in ("by", "date", "note"):
                val = item.get(key, "")
                if val:  # omit-empty: a blank stamp/note writes no line
                    lines.append(f"{key} = {_toml_str(val)}")
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
        "schema": SCHEMA,
        "product": product,
        "goal": f"Ship {product} to real users through the Delivery matrix.",
        "purpose": "",
        "ingredients": items(
            "Name + slug settled (trackerkeeper new done)",
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


def _project_info(root: Path) -> dict:
    """Summary-card facts (slug, display name, summary, feature cards, icon)
    for ANY checkout root — a generic ``[tool.<slug>.metadata]`` scan (the
    sidecar key is renamed per fork, same lesson as sync_loaf._identity), so
    the switcher can show a sibling loaf's card, not just this checkout's.
    Degrades to directory-name basics on anything malformed."""
    try:
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        for section in data.get("tool", {}).values():
            meta = section.get("metadata") if isinstance(section, dict) else None
            if isinstance(meta, dict) and "app_slug" in meta:
                return {
                    "slug": meta["app_slug"],
                    "display_name": meta.get("display_name", meta["app_slug"]),
                    "summary": meta.get("summary", ""),
                    "feature_cards": meta.get("feature_cards", []),
                    "icon": str(root / meta.get("icon_svg_source", "")),
                }
    except Exception:
        pass
    return {"slug": root.name, "display_name": root.name, "summary": "",
            "feature_cards": [], "icon": ""}


# ── the window half ──────────────────────────────────────────────────────────


def _make_view(path: Path):
    """The breadboard window content. Imported lazily so the file half stays
    importable headless (tests, agents)."""
    import re

    from PySide6.QtCore import QFileSystemWatcher, Qt, QThread, QTimer, Signal
    from PySide6.QtGui import QDesktopServices, QPixmap
    from PySide6.QtWidgets import (
        QApplication,
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

    from trackerkeeper import ui_helpers
    from trackerkeeper.design_tokens import TYPE_BODY, TYPE_DISPLAY, type_qss

    accent = ui_helpers.ACCENT

    _EDIT_QSS = (
        "background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);"
        "border-radius:6px;padding:4px 8px;color:#ddd;"
    )
    # `.QFrame` (exact type) not `QFrame` — a bare selector cascades the border
    # into child QLabels (QLabel subclasses QFrame), boxing every line of text.
    _CARD_QSS = (
        ".QFrame{background:rgba(255,255,255,0.045);border:1px solid "
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
        """deliver's DETECTED state — the trust engine. Runs off the UI thread
        (git/gh/network). Emits ``{"tag", "channels":[...]}`` where each channel
        is a dict carrying its live step states, the next guide, and — when
        LIVE — the real store URL + install command for the celebratory card.
        Emits the exception if probing itself failed. Every value here is a
        true probe result: nothing is asserted, so a green can't be faked."""

        ready = Signal(object)

        def run(self) -> None:  # noqa: N802 (Qt override)
            try:
                from trackerkeeper import deliver

                ctx = deliver._ctx()
                channels = []
                for ch in deliver._channels():
                    states = ch.states(ctx)
                    guide = ""
                    for step, st in zip(ch.steps, states, strict=True):
                        if st is not True:
                            guide = step.guide(ctx)
                            break
                    live = bool(states) and all(s is True for s in states)
                    channels.append({
                        "key": ch.key,
                        "title": ch.title,
                        "note": ch.note,
                        "stub": ch.stub,
                        "alert": ch.alert(ctx),
                        "steps": [(s.title, st)
                                  for s, st in zip(ch.steps, states, strict=True)],
                        "guide": guide,
                        "live": live,
                        "store_url": ch.store_url(ctx) if live else "",
                        "install_cmd": ch.install_cmd(ctx) if live else "",
                    })
                self.ready.emit({"tag": ctx.tag, "channels": channels})
            except Exception as exc:  # pragma: no cover - defensive
                self.ready.emit(exc)

    class BoardView(QWidget):
        """Tabs across the top; every interaction writes the file."""

        def __init__(self) -> None:
            super().__init__()
            self._path = Path(path)
            self._root = self._path.parent
            self._home_path = board_path()
            self._board = load(self._path)
            self._writing = False
            self._probe: _ChannelProbe | None = None
            self._channel_rows = None  # probed on first Delivery open; Refresh re-runs
            self._probe_tag = None
            # launch mode — the self-refreshing board while a release is in flight
            self._launch_timer = QTimer(self)
            self._launch_timer.setSingleShot(True)
            self._launch_timer.timeout.connect(self._start_probe)
            self._launch_active = False
            self._launch_interval = 0
            self._launch_polls = 0
            self._launch_stable = 0
            self._last_state_sig = None
            self._settled_sig = None  # the state we auto-stopped on — don't re-arm for it
            self._live_since: dict = {}  # channel key → wall-clock it flipped LIVE (this session)

            root = QVBoxLayout(self)
            root.setContentsMargins(16, 10, 16, 12)
            root.setSpacing(10)

            # ── the project bar: which loaf is on the bench + wind-down ──
            projbar = QHBoxLayout()
            projbar.setSpacing(8)
            plabel = QLabel("Project")
            plabel.setStyleSheet("color:#888;")
            projbar.addWidget(plabel)
            from trackerkeeper.selector import Selector, selector_qss

            self._project_sel = Selector()
            self._project_sel.setStyleSheet(selector_qss())
            self._projects = discover_projects()
            for product, bpath in self._projects:
                label = product + ("  (here)" if bpath == self._home_path else "")
                self._project_sel.addItem(label, str(bpath))
            idx = self._project_sel.findData(str(self._path))
            if idx >= 0:
                self._project_sel.setCurrentIndex(idx)
            self._project_sel.setFixedWidth(240)
            self._project_sel.currentIndexChanged.connect(self._on_project_pick)
            projbar.addWidget(self._project_sel)
            projbar.addStretch(1)
            self._winddown_note = QLabel("")
            self._winddown_note.setStyleSheet("color:#8f8;font-size:11px;")
            projbar.addWidget(self._winddown_note)
            wind = QPushButton("Wind down…")
            wind.setToolTip(
                "Ask the agent to run the wind-down ritual for this project\n"
                "(land green → update the handoff → commit + push). Written into\n"
                "the board as agent_request — the agent fulfils it and clears it.")
            wind.setCursor(Qt.CursorShape.PointingHandCursor)
            self._wind_btn = wind
            wind.setStyleSheet(self._ghost_btn_qss())
            wind.clicked.connect(self._request_wind_down)
            projbar.addWidget(wind)
            # ⌨ Agent — a real Claude Code terminal beside the board it drives.
            self._agent_btn = QPushButton("⌨ Agent")
            self._agent_btn.setCheckable(True)
            self._agent_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._agent_btn.setStyleSheet(self._ghost_btn_qss())
            # drop clicked(checked)'s bool arg — it must NOT land in force_off,
            # which would force the drawer closed the instant you open it.
            self._agent_btn.clicked.connect(lambda _=False: self._toggle_agent())
            self._prime_agent_button()
            projbar.addWidget(self._agent_btn)
            root.addLayout(projbar)

            # ── board (top) + agent terminal drawer (bottom), splittable ──
            from PySide6.QtWidgets import QSplitter

            self._split = QSplitter(Qt.Orientation.Vertical)
            self._split.setChildrenCollapsible(False)
            self._split.setHandleWidth(6)
            board_pane = QWidget()
            bp = QVBoxLayout(board_pane)
            bp.setContentsMargins(0, 0, 0, 0)
            bp.setSpacing(10)

            pills = QHBoxLayout()
            pills.setSpacing(6)
            self._pill_buttons: dict[str, QPushButton] = {}
            for phase in PHASES:
                b = QPushButton(_PHASE_TITLES[phase])
                b.setCheckable(True)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setMinimumHeight(30)
                b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                b.setStyleSheet(self._pill_qss())
                b.clicked.connect(lambda _=False, ph=phase: self._show_phase(ph))
                pills.addWidget(b, 1)
                self._pill_buttons[phase] = b
            bp.addLayout(pills)

            self._goal = QLabel(self._board.get("goal", ""))
            self._goal.setWordWrap(True)
            self._goal.setStyleSheet(type_qss(TYPE_DISPLAY) + "color:#ddd;")
            bp.addWidget(self._goal)

            self._stack = QStackedWidget()
            bp.addWidget(self._stack, 1)
            self._split.addWidget(board_pane)

            self._term_host = self._build_agent_drawer()
            self._term_host.setVisible(False)
            self._term = None  # the live TerminalWidget, spawned on first open
            self._split.addWidget(self._term_host)
            root.addWidget(self._split, 1)

            self._pages: dict[str, QWidget] = {}
            self._rebuild_pages()
            self._show_phase(self._first_open_phase())

            # outside edits (the agent, an editor, git) reload the view live
            self._watcher = QFileSystemWatcher([str(self._path)])
            self._watcher.fileChanged.connect(self._on_file_changed)
            self._rewatch = QTimer(self)
            self._rewatch.setSingleShot(True)
            self._rewatch.timeout.connect(self._ensure_watched)

            # Let a running channel probe finish before teardown — closing the
            # window mid-probe would otherwise abort ("QThread destroyed while
            # running"). Off-thread work is short (git/gh); wait briefly.
            app = QApplication.instance()
            if app is not None:
                app.aboutToQuit.connect(self._cleanup)

            # Live accent: the whole view bakes `accent` (a _make_view closure
            # local) into its QSS, which _propagate_theme_constants can't reach.
            # On a theme change, refresh that local and re-stamp/rebuild.
            from trackerkeeper.bus import register_for_theme

            register_for_theme(self, self._on_theme)

        def _pill_qss(self) -> str:
            return (
                "QPushButton{border:1px solid rgba(255,255,255,0.16);"
                "border-radius:15px;padding:5px 10px;background:transparent;color:#bbb;}"
                f"QPushButton:checked{{background:{accent};color:#fff;"
                f"border-color:{accent};}}"
            )

        def _ghost_btn_qss(self) -> str:
            return (
                "QPushButton{border:1px solid rgba(255,255,255,0.2);border-radius:8px;"
                "padding:5px 14px;background:transparent;color:#ccc;}"
                f"QPushButton:hover{{border-color:{accent};color:#fff;}}")

        def _on_theme(self) -> None:
            nonlocal accent
            accent = ui_helpers.ACCENT  # refresh the frozen closure local
            for b in self._pill_buttons.values():
                b.setStyleSheet(self._pill_qss())
            self._wind_btn.setStyleSheet(self._ghost_btn_qss())
            self._agent_btn.setStyleSheet(self._ghost_btn_qss())
            from trackerkeeper.selector import selector_qss

            self._project_sel.setStyleSheet(selector_qss())
            self._rebuild_pages()  # re-bakes cards/checkboxes/adders with the new accent

        def _cleanup(self) -> None:
            self._launch_timer.stop()
            if self._probe is not None and self._probe.isRunning():
                self._probe.wait(3000)
            self._stop_agent()

        # ── the agent terminal (⌨) ────────────────────────────────────────
        def _prime_agent_button(self) -> None:
            from trackerkeeper import terminal

            if not terminal.is_supported():
                self._agent_btn.setEnabled(False)
                self._agent_btn.setToolTip(
                    "The embedded terminal needs a POSIX pty + pyte "
                    "(pip install 'trackerkeeper-base[terminal]'); not available here.")
            elif not terminal.agent_available():
                self._agent_btn.setEnabled(False)
                self._agent_btn.setToolTip(
                    "Claude Code (`claude`) isn't on PATH — install it, or set "
                    "TRACKERKEEPER_AGENT_CMD to the command to run.")
            else:
                self._agent_btn.setToolTip(
                    "Open a Claude Code terminal in this project — talk to the "
                    "agent right beside the board it edits.")

        def _build_agent_drawer(self) -> QWidget:
            host = QWidget()
            v = QVBoxLayout(host)
            v.setContentsMargins(0, 6, 0, 0)
            v.setSpacing(4)
            bar = QHBoxLayout()
            self._agent_title = QLabel("")
            self._agent_title.setStyleSheet("color:#999;font-size:11px;")
            bar.addWidget(self._agent_title)
            bar.addStretch(1)
            restart = QPushButton("restart")
            restart.setCursor(Qt.CursorShape.PointingHandCursor)
            restart.setStyleSheet(self._mini_agent_qss())
            restart.clicked.connect(self._restart_agent)
            bar.addWidget(restart)
            close = QPushButton("hide ✕")
            close.setCursor(Qt.CursorShape.PointingHandCursor)
            close.setStyleSheet(self._mini_agent_qss())
            close.clicked.connect(lambda: self._toggle_agent(force_off=True))
            bar.addWidget(close)
            v.addLayout(bar)
            self._term_slot = QVBoxLayout()
            self._term_slot.setContentsMargins(0, 0, 0, 0)
            v.addLayout(self._term_slot, 1)
            return host

        @staticmethod
        def _mini_agent_qss() -> str:
            return ("QPushButton{border:none;border-radius:6px;padding:3px 10px;"
                    "background:rgba(255,255,255,0.06);color:#bbb;font-size:11px;}"
                    "QPushButton:hover{background:rgba(255,255,255,0.14);color:#fff;}")

        def _toggle_agent(self, force_off: bool = False) -> None:
            show = self._agent_btn.isChecked() and not force_off
            self._agent_btn.setChecked(show)
            self._term_host.setVisible(show)
            if show:
                if self._term is None:
                    self._spawn_agent()
                # give the terminal ~40% of the height on first reveal
                total = max(1, self._split.height())
                self._split.setSizes([int(total * 0.6), int(total * 0.4)])
                if self._term is not None:
                    self._term.setFocus()

        def _spawn_agent(self) -> None:
            from trackerkeeper import terminal

            slug = _project_info(self._root)["slug"]
            self._agent_title.setText(f"⌨ claude · {slug}  ({self._root})")
            self._term = terminal.TerminalWidget(terminal.claude_argv(), cwd=self._root)
            self._term.exited.connect(self._on_agent_exit)
            self._term_slot.addWidget(self._term)

        def _stop_agent(self) -> None:
            if self._term is not None:
                self._term.stop()
                self._term.setParent(None)
                self._term.deleteLater()
                self._term = None

        def _restart_agent(self) -> None:
            self._stop_agent()
            self._spawn_agent()
            self._term.setFocus()

        def _on_agent_exit(self, code: int) -> None:
            if self._term is not None:
                self._agent_title.setText(
                    self._agent_title.text() + f"  — exited ({code}); press restart")

        # ── project switching + the wind-down request ─────────────────────
        def _on_project_pick(self, _idx: int) -> None:
            data = self._project_sel.currentData()
            if data and Path(data) != self._path:
                self.set_project(Path(data))

        def set_project(self, new_path: Path) -> None:
            """Put another checkout's board on the bench: reload state, re-anchor
            the summary card + watcher; live channel detection stays home-only
            (deliver probes THIS checkout — a sibling's truth needs its own
            `<slug>-breadboard`)."""
            self._launch_timer.stop()  # a new project's delivery is its own story
            self._launch_active = False
            self._last_state_sig = None
            self._settled_sig = None
            self._live_since = {}
            self._stop_agent()  # the terminal is scoped to a project dir
            self._agent_btn.setChecked(False)
            self._term_host.setVisible(False)
            self._watcher.removePath(str(self._path))
            self._path = Path(new_path)
            self._root = self._path.parent
            self._board = load(self._path)
            self._channel_rows = None
            self._winddown_note.setText("")
            self._watcher.addPath(str(self._path))
            self._goal.setText(self._board.get("goal", ""))
            self._rebuild_pages()
            self._show_phase(self._first_open_phase())

        def _is_home(self) -> bool:
            return self._path == self._home_path

        def _request_wind_down(self) -> None:
            self._board["agent_request"] = (
                f"wind down — requested by the maker {date.today().isoformat()}"
            )
            self._write()
            self._winddown_note.setText("wind-down requested — the agent will land it")

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
            # the slim, auto-fading accent pills the app family uses everywhere
            # (no track, no gutter fill — just the handle over the frost)
            ui_helpers.install_autofade_scrollbars(s)
            return s

        # ── Ingredients: the app summary page ─────────────────────────────
        def _build_ingredients(self) -> QWidget:
            side = _project_info(self._root)
            self._slug = side["slug"]
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

            assets = self._root / getattr(self, "_slug", _PKG) / "assets"
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
                # a soft LANE, not a bordered box — the cards are the boxes, so
                # the column just needs a faint tint to read as a drop zone
                # (borders-in-borders got heavy — August's note).
                frame.setStyleSheet(
                    ".QFrame{background:rgba(255,255,255,0.025);border:none;"
                    "border-radius:10px;}")
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
                ".QFrame{background:rgba(255,255,255,0.06);border:1px solid "
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
                    "QPushButton{border:none;border-radius:4px;color:#8a8a8a;"
                    "background:transparent;}"  # no resting chip — only hover fills
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
            if not self._is_home():
                away = QLabel(
                    "Live channel detection runs in the project's own checkout — "
                    f"open it with `{_project_info(self._root)['slug']}-breadboard`. "
                    "The board's own delivery items are below.")
                away.setWordWrap(True)
                away.setStyleSheet("color:#888;")
                v.addWidget(away)
                for item in self._board.get("delivery", []):
                    v.addLayout(self._build_check_row(item))
                v.addWidget(self._build_adder("delivery"))
                v.addStretch(1)
                return self._scroll(inner)
            bar = QHBoxLayout()
            self._delivery_status = QLabel("")
            self._delivery_status.setWordWrap(True)
            self._delivery_status.setStyleSheet("color:#888;")
            bar.addWidget(self._delivery_status, 1)
            _btn_qss = (
                "QPushButton{border:1px solid rgba(255,255,255,0.2);border-radius:8px;"
                "padding:4px 12px;background:transparent;color:#ccc;}"
                f"QPushButton:hover{{border-color:{accent};}}"
                f"QPushButton:checked{{border-color:{accent};color:{accent};}}")
            self._watch_btn = QPushButton("Watch")
            self._watch_btn.setCheckable(True)
            self._watch_btn.setToolTip(
                "While a release is in flight, keep re-probing so channels flip to LIVE "
                "on their own. Auto-arms when a tag exists and something isn't live yet.")
            self._watch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._watch_btn.setStyleSheet(_btn_qss)
            self._watch_btn.clicked.connect(self._toggle_watch)
            bar.addWidget(self._watch_btn)
            refresh = QPushButton("Refresh")
            refresh.setCursor(Qt.CursorShape.PointingHandCursor)
            refresh.setStyleSheet(_btn_qss)
            refresh.clicked.connect(self._start_probe)
            bar.addWidget(refresh)
            v.addLayout(bar)

            self._channels_box = QVBoxLayout()
            self._channels_box.setSpacing(8)
            v.addLayout(self._channels_box)
            self._watch_btn.setChecked(self._launch_active)
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
            if not self._launch_active:
                self._delivery_status.setText("probing channels…")
            self._probe = _ChannelProbe(self)
            self._probe.ready.connect(self._on_probe_ready)
            self._probe.start()

        # ── launch mode: the board that moves on its own ──────────────────
        # While a release is in flight, re-probe on a backing-off cadence so
        # channels flip ▶→✓→LIVE without the maker touching anything. Every
        # green is still a real probe result — the timer never fakes state.
        _LAUNCH_START_MS = 5000
        _LAUNCH_MAX_MS = 20000
        _LAUNCH_STOP_STABLE = 3   # settle after N unchanged polls
        _LAUNCH_MAX_POLLS = 60    # hard backstop

        @staticmethod
        def _state_sig(channels) -> tuple:
            return tuple((c["key"], c["live"], sum(1 for _, s in c["steps"] if s is True))
                         for c in channels)

        def _all_live(self, channels) -> bool:
            real = [c for c in channels if not c["stub"] and not c["alert"]]
            return bool(real) and all(c["live"] for c in real)

        def _toggle_watch(self) -> None:
            if self._watch_btn.isChecked():
                self._start_launch(manual=True)
            else:
                self._stop_launch("stopped by maker")

        def _start_launch(self, manual: bool = False) -> None:
            if self._launch_active:
                return
            self._launch_active = True
            self._launch_interval = self._LAUNCH_START_MS
            self._launch_polls = 0
            self._launch_stable = 0
            if manual:
                self._settled_sig = None  # the maker overrides the settle latch
            self._watch_btn.setChecked(True)
            self._watch_btn.setText("Watching ●")
            # A manual click kicks a probe now; an AUTO arm from _on_probe_ready
            # rides the timer it's about to set (no redundant double-probe).
            if manual and not (self._probe and self._probe.isRunning()):
                self._start_probe()

        def _stop_launch(self, why: str, sig=None) -> None:
            self._launch_active = False
            self._launch_timer.stop()
            self._settled_sig = sig  # don't auto-re-arm for this same state
            self._watch_btn.setChecked(False)
            self._watch_btn.setText("Watch")

        def _on_probe_ready(self, payload) -> None:
            if isinstance(payload, Exception):
                self._delivery_status.setText(f"probe failed: {payload}")
                self._stop_launch("probe error")
                return
            channels = payload["channels"]
            self._probe_tag = payload["tag"]
            sig = self._state_sig(channels)
            changed = sig != self._last_state_sig
            # stamp the wall-clock of any channel we WATCHED flip live this run
            from datetime import datetime

            prev = {c["key"]: c["live"] for c in (self._channel_rows or [])}
            for c in channels:
                if c["live"] and not prev.get(c["key"]) and c["key"] not in self._live_since:
                    self._live_since[c["key"]] = datetime.now().strftime("%H:%M")
            self._last_state_sig = sig
            self._channel_rows = channels
            self._render_channels(channels)

            all_live = self._all_live(channels)
            # auto-arm launch mode: a tag exists, the release isn't fully live,
            # and we haven't already settled on this exact state (no re-arm loop)
            if (not self._launch_active and self._probe_tag and not all_live
                    and sig != self._settled_sig):
                self._start_launch()

            if self._launch_active:
                self._launch_polls += 1
                self._launch_stable = 0 if changed else self._launch_stable + 1
                if all_live:
                    self._stop_launch("all channels live", sig)
                    self._delivery_status.setText("✓ every channel is LIVE — shipped.")
                elif (self._launch_stable >= self._LAUNCH_STOP_STABLE
                      or self._launch_polls >= self._LAUNCH_MAX_POLLS):
                    self._stop_launch("settled", sig)
                    self._delivery_status.setText(
                        "state settled — press Watch to keep polling, or Refresh once.")
                else:
                    if changed:
                        self._launch_interval = self._LAUNCH_START_MS  # reset on progress
                    else:
                        self._launch_interval = min(
                            int(self._launch_interval * 1.5), self._LAUNCH_MAX_MS)
                    self._launch_timer.start(self._launch_interval)
                    secs = self._launch_interval // 1000
                    self._delivery_status.setText(
                        f"● watching for go-live — re-probing every {secs}s "
                        f"(poll {self._launch_polls}). Every green is a real probe.")
            else:
                self._delivery_status.setText(
                    "detected state — ✓ done · ▶ next · ? unknowable from here")

        def _render_channels(self, channels) -> None:
            while self._channels_box.count():
                it = self._channels_box.takeAt(0)
                if it.widget():
                    it.widget().deleteLater()
            for c in channels:
                if c["live"]:
                    self._channels_box.addWidget(self._live_card(c))
                else:
                    self._channels_box.addWidget(self._pending_card(c))

        def _live_card(self, c) -> QWidget:
            """The celebratory row: a channel the probe found fully LIVE, with
            the real public URL + the one-line install command. This card is
            the payoff — a green nobody can fake, because it's detected."""
            card = QFrame()
            card.setStyleSheet(
                ".QFrame{background:rgba(86,196,141,0.10);border:1px solid "
                "rgba(86,196,141,0.45);border-radius:10px;}")
            cv = QVBoxLayout(card)
            cv.setContentsMargins(14, 11, 14, 12)
            cv.setSpacing(7)
            since = self._live_since.get(c["key"])
            head = QLabel(
                f'{c["title"]}   '
                f'<span style="color:#56c48d;font-weight:700;">● LIVE</span>'
                + (f'   <span style="color:#6a8;font-size:11px;">went live {since}</span>'
                   if since else ""))
            head.setTextFormat(Qt.TextFormat.RichText)
            head.setStyleSheet("color:#fff;font-weight:600;")
            cv.addWidget(head)
            if c["store_url"]:
                link = QLabel(
                    f'<a href="{c["store_url"]}" style="color:{accent};'
                    f'text-decoration:none;">{c["store_url"]} →</a>')
                link.setTextFormat(Qt.TextFormat.RichText)
                link.setOpenExternalLinks(True)
                link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                cv.addWidget(link)
            if c["install_cmd"]:
                cmd = QLineEdit(c["install_cmd"])
                cmd.setReadOnly(True)
                cmd.setCursorPosition(0)
                cmd.setToolTip("select-all + copy")
                cmd.setStyleSheet(
                    "QLineEdit{background:rgba(0,0,0,0.30);border:1px solid "
                    "rgba(255,255,255,0.10);border-radius:6px;padding:6px 10px;"
                    "color:#dfe;font-family:monospace;font-size:13px;}")
                cv.addWidget(cmd)
            return card

        def _pending_card(self, c) -> QWidget:
            card = QFrame()
            card.setStyleSheet(_CARD_QSS)
            cv = QVBoxLayout(card)
            cv.setContentsMargins(12, 8, 12, 8)
            cv.setSpacing(4)
            alert = c["alert"]
            head = QLabel(c["title"] + (f"   —   ⚠ {alert}" if alert else "")
                          + ("   [stub]" if c["stub"] else ""))
            head.setStyleSheet(
                "color:#f88;font-weight:bold;" if alert else "color:#fff;font-weight:bold;")
            cv.addWidget(head)
            if c["note"]:
                n = QLabel(c["note"])
                n.setWordWrap(True)
                n.setStyleSheet("color:#888;font-size:11px;")
                cv.addWidget(n)
            marks = {True: ("✓", "#56c48d"), False: ("▶", accent), None: ("?", "#888")}
            for step_title, st in c["steps"]:
                mark, color = marks.get(st, ("?", "#888"))
                s = QLabel(f'<span style="color:{color};">{mark}</span>  {step_title}')
                s.setTextFormat(Qt.TextFormat.RichText)
                s.setStyleSheet("color:#ccc;")
                cv.addWidget(s)
            if c["guide"]:
                g = QLabel(_linkify(c["guide"]))
                g.setTextFormat(Qt.TextFormat.RichText)
                g.setOpenExternalLinks(True)
                g.setWordWrap(True)
                g.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                g.setStyleSheet(
                    "color:#aaa;background:rgba(0,0,0,0.25);border-radius:6px;"
                    "padding:6px;font-family:monospace;font-size:11px;")
                cv.addWidget(g)
            return card

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

    from trackerkeeper.app import run_app

    return run_app(lambda window: _make_view(path), single_instance=False)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
