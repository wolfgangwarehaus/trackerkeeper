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
import os
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

# A parked agent silent this long is sitting at its prompt, so a reload can't
# interrupt real work. Shorter and a reload lands between two lines of a
# streaming turn. Tests override it.
AGENT_IDLE_SECONDS = 4.0

# What the Wind down… button TYPES at a live agent (the board write is the
# durable half; this is the poke that makes it happen now). Phrased as the maker
# would ask for it, and it names the ritual + the clear so the agent doesn't have
# to go looking. TRACKERKEEPER_WIND_DOWN_PROMPT overrides it.
WIND_DOWN_PROMPT = (
    "wind down — I pressed the button, so the board's agent_request asks for it. "
    "Run the wind-down ritual in docs/WIND-DOWN.md, and clear agent_request in "
    "the same commit that lands the work."
)


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
    import re

    _ensure_ids(board)
    # The header names THIS board's window binary — derive it from the board's own
    # product (slugified: lowercased, non-alphanumerics dropped — "tracker keeper"
    # → "trackerkeeper"), not _PKG, so trackerkeeper's breadboard saving a SIBLING loaf's
    # board (via the project switcher) doesn't rewrite its header to
    # `trackerkeeper-breadboard`.
    _win = re.sub(r"[^a-z0-9-]", "", board.get("product", _PKG).lower()) or _PKG
    lines = [
        "# The breadboard — the live maker surface. The WINDOW (`{0}-breadboard`) and".format(
            _win),
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
            for key in ("summary", "by", "date", "note"):
                val = item.get(key, "")
                if val:  # omit-empty: a blank summary/stamp/note writes no line
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


# ── self-reload (agent-driven) ────────────────────────────────────────────────


def _reload_marker_path(board: Path) -> Path:
    """The per-project runtime marker the window watches; `trackerkeeper-breadboard
    reload` touches it to ask for a self-reload. Keyed by the board's absolute
    path (so two checkouts don't cross-signal) and kept in the temp dir so it
    never lands in the repo."""
    import hashlib
    import tempfile

    h = hashlib.sha1(str(Path(board).resolve()).encode()).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"{_PKG}-breadboard-reload-{h}"


def _validate_reload_imports() -> tuple[bool, str]:
    """Prove the on-disk code still imports BEFORE we exec into it — a syntax
    error the agent just left would otherwise crash-loop the relaunch. A fresh
    subprocess imports the surfaces a relaunch needs; non-zero means don't reload
    (stay on the good in-memory code)."""
    import subprocess

    mods = ("app", "window", "breadboard", "terminal", "ui_helpers")
    code = "import " + ", ".join(f"{_PKG}.{m}" for m in mods)
    try:
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=60)
    except Exception as e:  # pragma: no cover - subprocess spawn failure
        return False, str(e)
    return r.returncode == 0, (r.stderr.strip() or r.stdout.strip())


# ── the window half ──────────────────────────────────────────────────────────


def _make_view(path: Path, restore: dict | None = None, window=None):
    """The breadboard window content. Imported lazily so the file half stays
    importable headless (tests, agents).

    ``restore`` (set only by a self-reload relaunch) re-opens the same phase +
    agent drawer and resumes the agent conversation once the window is live."""
    import re

    from PySide6.QtCore import QFileSystemWatcher, QPointF, Qt, QThread, QTimer, Signal
    from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPixmap
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
        QSplitter,
        QSplitterHandle,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )

    from trackerkeeper import ui_helpers
    from trackerkeeper.design_tokens import TYPE_BODY, TYPE_DISPLAY, TYPE_TITLE, type_qss
    from trackerkeeper.settings import get_settings

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

    class _DotHandle(QSplitterHandle):
        """A splitter grip painted as a short, centered row of dots (a column of
        dots when the splitter is horizontal) — quieter and cleaner than Qt's
        native handle texture."""

        _N = 5          # dot count
        _GAP = 7.0      # spacing between dot centers
        _D = 3.0        # dot diameter

        def paintEvent(self, e) -> None:  # noqa: N802
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 55))  # faint, over the frost
            c = self.rect().center()
            span = (self._N - 1) * self._GAP
            r = self._D / 2
            for i in range(self._N):
                off = i * self._GAP - span / 2
                # Vertical splitter → horizontal row; horizontal → vertical column.
                if self.orientation() == Qt.Orientation.Vertical:
                    p.drawEllipse(QPointF(c.x() + off, c.y()), r, r)
                else:
                    p.drawEllipse(QPointF(c.x(), c.y() + off), r, r)
            p.end()

    class _DottedSplitter(QSplitter):
        """A QSplitter whose handle is the tidy dotted grip (:class:`_DotHandle`)."""

        def createHandle(self):  # noqa: N802 — Qt override
            return _DotHandle(self.orientation(), self)

    class _ColumnScroll(QScrollArea):
        """One kanban column's scrollable card list. The auto-fade pill sits in a
        RESERVED gutter to the right of the cards (inside the lane bezel), so it
        never overlaps a card. Horizontal scrolling is off — cards wrap to fit.

        Plain wheel scrolls THIS column (the one under the cursor). Holding SHIFT
        scrolls all four columns together — ``siblings`` is the shared list of the
        row's column scrollers (mutated in place as they're built, so it's full by
        the time any wheel event fires)."""

        def __init__(self, inner: QWidget, siblings: list) -> None:
            super().__init__()
            self.setWidgetResizable(True)
            self.setFrameShape(QFrame.Shape.NoFrame)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.setWidget(inner)
            # a gutter-reserving auto-fade bar: the pill paints in the 12px gutter
            # beside the cards (not over them), and the frost shows through it.
            ui_helpers.install_autofade_scrollbars(self)
            self._siblings = siblings

        def wheelEvent(self, e) -> None:  # noqa: N802
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # SHIFT → move every column in lockstep. Some platforms remap a
                # Shift+wheel onto the horizontal axis, so take whichever is live.
                pd, ad = e.pixelDelta(), e.angleDelta()
                px = (pd.y() or pd.x()) or int((ad.y() or ad.x()) / 120 * 48)
                for s in self._siblings:
                    bar = s.verticalScrollBar()
                    bar.setValue(bar.value() - px)
                e.accept()
                return
            super().wheelEvent(e)  # plain wheel: just this column

    class BoardView(QWidget):
        """Tabs across the top; every interaction writes the file."""

        def __init__(self, window=None) -> None:
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
            self._done_sort = "newest"  # Done column order: newest-first or oldest-first

            root = QVBoxLayout(self)
            root.setContentsMargins(16, 10, 16, 12)
            root.setSpacing(10)

            # ── the maker controls ────────────────────────────────────────
            # The single window TOP BAR hosts the hamburger (project picker + Open
            # + Wind down) and only a tiny wind-down status note. The Agent toggle
            # is NOT here — it lives pinned at the BOTTOM of the board (built below).
            self._window = window
            self._projects = discover_projects()
            self._wind_tip = (
                "Ask the agent to run the wind-down ritual for this project\n"
                "(land green → update the handoff → commit + push). Written into\n"
                "the board as agent_request — the agent fulfils it and clears it.")
            self._winddown_note = QLabel("")
            self._winddown_note.setStyleSheet("color:#8f8;font-size:11px;")
            # ⌨ Agent — a real Claude Code terminal beside the board it drives.
            # The toggle sits at the bottom (added after the split): "⌨ Agent" when
            # closed, "hide ✕" when open. Created here so _prime_agent_button and
            # the restore path can touch it before the bottom row is built.
            self._agent_btn = ui_helpers.RoundedButton("⌨ Agent", variant="ghost")
            self._agent_btn.setCheckable(True)
            # drop clicked(checked)'s bool arg — it must NOT land in force_off,
            # which would force the drawer closed the instant you open it.
            self._agent_btn.clicked.connect(lambda _=False: self._toggle_agent())
            self._prime_agent_button()
            self._install_top_bar(window)  # into the window titlebar (or a no-op)
            # Self-reload is agent-driven, not a button: after the agent edits
            # trackerkeeper it runs `trackerkeeper-breadboard reload`, which touches a marker we
            # file-watch (_watch_reload_marker / _on_reload_marker) → we restart
            # onto the new code and resume its session (claude --continue).

            # ── the 4 phase tabs — the row directly under the top bar ─────────
            pill_row = QHBoxLayout()
            pill_row.setSpacing(6)
            self._pill_buttons: dict[str, QPushButton] = {}
            for phase in PHASES:
                b = ui_helpers.RoundedButton(_PHASE_TITLES[phase], variant="pill",
                                             radius=15)
                b.setMinimumHeight(30)
                b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                b.clicked.connect(lambda _=False, ph=phase: self._show_phase(ph))
                pill_row.addWidget(b, 1)
                self._pill_buttons[phase] = b
            root.addLayout(pill_row)

            # ── board (top) + agent terminal drawer (bottom), splittable ──
            self._split = _DottedSplitter(Qt.Orientation.Vertical)
            self._split.setChildrenCollapsible(False)
            self._split.setHandleWidth(11)  # room for the dotted grip
            board_pane = QWidget()
            self._board_pane = board_pane
            bp = QVBoxLayout(board_pane)
            bp.setContentsMargins(0, 0, 0, 0)
            bp.setSpacing(10)

            # a labelled north-star: a "CURRENT GOAL" kicker over the goal line, so
            # it's clear this is the objective for now (vs. the app's PURPOSE on
            # Ingredients — what the app fundamentally is).
            bp.addWidget(self._kicker("Current goal"))
            self._goal = QLabel(self._board.get("goal", ""))
            self._goal.setWordWrap(True)
            # a heading, not a banner — DISPLAY (20/700) read as comically large;
            # TITLE (16/600) keeps it larger-and-bold without dominating (August).
            self._goal.setStyleSheet(type_qss(TYPE_TITLE) + "color:#ddd;")
            bp.addWidget(self._goal)

            self._stack = QStackedWidget()
            bp.addWidget(self._stack, 1)
            self._split.addWidget(board_pane)

            # remembered dock (bottom / left / right) — read before the drawer
            # is built so its dock button can label the current side
            self._agent_dock = get_settings().agent_dock
            self._term_host = self._build_agent_drawer()
            self._term_host.setVisible(False)
            self._term = None  # the live TerminalWidget, spawned on first open
            self._resume_agent = False  # one-shot: next spawn resumes the pinned id
            self._agent_session_id: str | None = None  # pins the agent's thread
            # Swapping projects PARKS the current agent instead of killing it: its
            # terminal (and the live claude behind it) is stashed here by project
            # path, kept running off-layout, and re-attached when you come back.
            # value: (TerminalWidget, session_id, was_open).
            self._parked_agents: dict[str, tuple] = {}
            self._split.addWidget(self._term_host)
            root.addWidget(self._split, 1)

            # ── the Agent control strip, pinned at the BOTTOM of the board ────
            # Closed: just "⌨ Agent" (opens the drawer). Open: the agent title on
            # the left, then a matched trio on the right — dock, restart, and the
            # toggle (now "hide ✕"). The title + dock + restart show ONLY while the
            # agent is open; the drawer itself has no header anymore.
            self._agent_title = QLabel("")
            self._agent_title.setStyleSheet("color:#999;font-size:11px;")
            self._dock_btn = ui_helpers.RoundedButton(self._dock_label(), variant="ghost")
            self._dock_btn.setToolTip("Dock the agent bottom / right / left of the board")
            self._dock_btn.clicked.connect(self._cycle_agent_dock)
            self._restart_btn = ui_helpers.RoundedButton("restart", variant="ghost")
            self._restart_btn.setToolTip("Restart the agent process")
            self._restart_btn.clicked.connect(self._restart_agent)
            for b in (self._dock_btn, self._restart_btn, self._agent_btn):
                b.setMinimumHeight(28)  # a matched trio
            bottom = QHBoxLayout()
            bottom.setContentsMargins(0, 0, 0, 0)
            bottom.setSpacing(6)
            bottom.addWidget(self._agent_title)
            bottom.addStretch(1)
            bottom.addWidget(self._dock_btn)
            bottom.addWidget(self._restart_btn)
            bottom.addWidget(self._agent_btn)
            root.addLayout(bottom)
            self._set_agent_controls(False)  # dock/restart/title hidden until open

            # apply orientation + board↔terminal order now; sizes wait for open
            self._apply_agent_dock(resize=False)

            self._pages: dict[str, QWidget] = {}
            self._rebuild_pages()
            self._show_phase(self._first_open_phase())

            # outside edits (the agent, an editor, git) reload the view live
            self._watcher = QFileSystemWatcher([str(self._path)])
            self._watcher.fileChanged.connect(self._on_file_changed)
            self._rewatch = QTimer(self)
            self._rewatch.setSingleShot(True)
            self._rewatch.timeout.connect(self._ensure_watched)

            # `trackerkeeper-breadboard reload` (the agent, after editing trackerkeeper) touches a
            # per-project marker; watch it and self-reload onto the new code.
            self._reload_watcher: QFileSystemWatcher | None = None
            self._reload_nonce = ""  # the last reload nonce acted on
            # A reload asked for while ANOTHER project's agent is mid-turn waits
            # here until they all fall idle (see _request_reload).
            self._pending_reload = False
            self._reload_wait: QTimer | None = None
            self._watch_reload_marker()

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

            # a self-reload relaunch restores its place once the window is live
            # (after show + layout, so the split sizes for the real geometry)
            if restore:
                QTimer.singleShot(0, lambda: self._apply_restore(restore))

        def _on_theme(self) -> None:
            nonlocal accent
            accent = ui_helpers.ACCENT  # refresh the frozen closure local
            # pills + wind + agent are painted RoundedButtons — they read ACCENT
            # live and repaint themselves (register_for_theme). Only the rebuilt
            # cards need re-stamp with the new accent.
            self._rebuild_pages()  # re-bakes cards/checkboxes/adders with the new accent

        def _cleanup(self) -> None:
            self._launch_timer.stop()
            if self._reload_wait is not None:
                self._reload_wait.stop()
            if self._probe is not None and self._probe.isRunning():
                self._probe.wait(3000)
            self._stop_agent()
            # Parked (background) agents are live claude processes — stop them all
            # so a quit or self-reload doesn't leak orphaned ptys. (A reload then
            # resumes only the CURRENT project's thread; parked threads persist on
            # disk and spawn fresh when you revisit.)
            for term, _sid, _open in self._parked_agents.values():
                term.stop()
            self._parked_agents.clear()

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
            # Just the terminal — the title + dock/restart/hide controls all live in
            # the bottom control strip now (built in __init__).
            host = QWidget()
            v = QVBoxLayout(host)
            v.setContentsMargins(0, 6, 0, 0)
            v.setSpacing(4)
            self._term_slot = QVBoxLayout()
            self._term_slot.setContentsMargins(0, 0, 0, 0)
            v.addLayout(self._term_slot, 1)
            return host

        # ── agent dock: bottom / right / left of the board ────────────────
        _DOCK_LABELS = {"bottom": "⬓ bottom", "right": "◨ right", "left": "◧ left"}

        def _dock_label(self) -> str:
            return self._DOCK_LABELS.get(self._agent_dock, "⬓ bottom")

        def _apply_agent_dock(self, resize: bool = True) -> None:
            """Reorient the splitter and order the board/terminal panes for the
            current dock. Horizontal for left/right, vertical for bottom; the
            terminal leads the pair only when docked left."""
            pos = self._agent_dock
            horizontal = pos in ("left", "right")
            self._split.setOrientation(
                Qt.Orientation.Horizontal if horizontal else Qt.Orientation.Vertical)
            first, second = (
                (self._term_host, self._board_pane) if pos == "left"
                else (self._board_pane, self._term_host))
            self._split.insertWidget(0, first)   # moves the existing widgets —
            self._split.insertWidget(1, second)  # QSplitter re-parents in place
            if getattr(self, "_dock_btn", None) is not None:
                self._dock_btn.setText(self._dock_label())
            if resize and self._term_host.isVisible():
                self._resize_agent_split()

        def _resize_agent_split(self) -> None:
            """Give the terminal a comfortable slice — ~40% tall docked bottom,
            ~42% wide docked to a side — with the board taking the rest."""
            horizontal = self._agent_dock in ("left", "right")
            total = max(1, self._split.width() if horizontal else self._split.height())
            term = int(total * (0.42 if horizontal else 0.40))
            board = max(1, total - term)
            self._split.setSizes(
                [term, board] if self._agent_dock == "left" else [board, term])

        def _cycle_agent_dock(self) -> None:
            order = ("bottom", "right", "left")
            self._agent_dock = order[(order.index(self._agent_dock) + 1) % len(order)]
            get_settings().agent_dock = self._agent_dock
            self._apply_agent_dock(resize=True)

        def _set_agent_controls(self, on: bool) -> None:
            """Show the drawer's controls — the title + dock + restart — only while
            the agent is open; closed, just the ⌨ Agent toggle remains."""
            for w in (self._agent_title, self._dock_btn, self._restart_btn):
                w.setVisible(on)

        def _toggle_agent(self, force_off: bool = False) -> None:
            show = self._agent_btn.isChecked() and not force_off
            self._agent_btn.setChecked(show)
            # the one bottom control flips label with state: open → "hide ✕"
            self._agent_btn.setText("hide ✕" if show else "⌨ Agent")
            self._set_agent_controls(show)
            self._term_host.setVisible(show)
            if show:
                if self._term is None:
                    self._spawn_agent()
                self._resize_agent_split()  # size for the current dock
                if self._term is not None:
                    self._term.setFocus()

        def _spawn_agent(self) -> None:
            from trackerkeeper import terminal

            slug = _project_info(self._root)["slug"]
            resume, self._resume_agent = self._resume_agent, False  # consume one-shot
            if resume and self._agent_session_id:
                # Auto-continue: a reload resume submits a "continue" so the agent
                # picks the interrupted turn back up on its own (no maker typing it).
                # TRACKERKEEPER_AGENT_RESUME_PROMPT overrides the message; empty disables it.
                cont = os.environ.get("TRACKERKEEPER_AGENT_RESUME_PROMPT", "continue") or None
                argv = terminal.claude_argv(
                    session_id=self._agent_session_id, resume=True,
                    prompt=cont)  # THIS thread back, and keep going
            else:
                # fresh: pin a new id so a later reload resumes THIS conversation,
                # not whatever claude was most-recently active in the project dir
                self._agent_session_id = terminal.new_session_id()
                argv = terminal.claude_argv(session_id=self._agent_session_id)
            self._agent_title.setText(
                f"⌨ claude · {slug}  ({self._root})"
                + ("  — resuming" if resume else ""))
            self._term = terminal.TerminalWidget(argv, cwd=self._root)
            self._term.exited.connect(self._on_agent_exit)
            self._term.submitted.connect(self._on_agent_submitted)
            self._term_slot.addWidget(self._term)

        def _stop_agent(self) -> None:
            if self._term is not None:
                self._term.stop()
                self._term.setParent(None)
                self._term.deleteLater()
                self._term = None

        def _park_agent(self) -> None:
            """Swapping away from a project: stash its agent WITHOUT killing it.
            Pull the live terminal out of the layout and hide it, but keep the
            widget (and so its pty + the claude behind it) alive — the socket
            notifier keeps draining output in the background. Re-entering the
            project re-attaches this exact terminal via :meth:`_unpark_agent`."""
            if self._term is None:
                return
            self._term_slot.removeWidget(self._term)
            self._term.hide()  # parent stays the drawer host; just off-layout
            self._parked_agents[str(self._path)] = (
                self._term, self._agent_session_id, not self._term_host.isHidden())
            self._term = None
            self._agent_session_id = None

        def _unpark_agent(self) -> bool:
            """Re-entering a project: if it has a parked (still-running) agent,
            drop it back into the drawer exactly as it was. Returns True if one
            was restored."""
            parked = self._parked_agents.pop(str(self._path), None)
            if parked is None:
                return False
            term, sid, was_open = parked
            self._term = term
            self._agent_session_id = sid
            self._term_slot.addWidget(term)
            term.show()  # clears the park-time hide; drawer visibility governs
            if was_open:
                self._agent_btn.setChecked(True)
                self._toggle_agent()  # shows + sizes the drawer; term is set → no spawn
            return True

        def _restart_agent(self) -> None:
            self._stop_agent()
            self._spawn_agent()
            self._term.setFocus()

        def _on_agent_exit(self, code: int) -> None:
            term = self.sender()
            if term is self._term and self._term is not None:
                self._agent_title.setText(
                    self._agent_title.text() + f"  — exited ({code}); press restart")
                return
            # A PARKED agent ended while its project was off the bench — forget it
            # so returning spawns a fresh session rather than re-attaching a corpse.
            for key, (t, _sid, _open) in list(self._parked_agents.items()):
                if t is term:
                    t.deleteLater()
                    del self._parked_agents[key]
                    break

        # ── self-reload: restart onto the code now on disk ────────────────
        def _current_phase(self) -> str:
            for ph, b in self._pill_buttons.items():
                if b.isChecked():
                    return ph
            return self._first_open_phase()

        def _watch_reload_marker(self) -> None:
            """(Re)point the reload watcher at THIS project's marker. Reset it to
            empty first so a nonce left by the exec that just restarted us can't
            immediately re-fire, and re-key on a project switch so a reload always
            targets the project on the bench."""
            marker = _reload_marker_path(self._path)
            self._reload_nonce = ""  # armed: nothing acted on for this project yet
            try:
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text("", encoding="utf-8")  # BEFORE addPath → no self-trigger
            except OSError:
                return
            if self._reload_watcher is None:
                self._reload_watcher = QFileSystemWatcher(self)
                self._reload_watcher.fileChanged.connect(self._on_reload_marker)
            elif self._reload_watcher.files():
                self._reload_watcher.removePaths(self._reload_watcher.files())
            self._reload_watcher.addPath(str(marker))

        def _on_reload_marker(self, path: str) -> None:
            """The marker changed — but ONLY a genuine reload request restarts us:
            a fresh, non-empty nonce written by `trackerkeeper-breadboard reload`.

            The marker lives in shared temp, so it draws filesystem events we must
            NOT read as "restart now": a /tmp sweeper deleting it, the empty reset
            `_watch_reload_marker` writes, or a re-touch of the nonce we already
            acted on. Treating every fileChanged as a restart turned a routine tmp
            cleanup into a boot loop (each restart auto-submitting "continue" to
            the resumed agent). Re-arm the watch on every event — a rewrite or
            delete drops the inotify watch — then act only on a new nonce.
            _request_reload exec's away on success and returns only if the code on
            disk doesn't import."""
            marker = Path(path)
            try:
                nonce = marker.read_text(encoding="utf-8").strip()
            except OSError:  # gone (swept) or unreadable → not a reload request
                nonce = ""
                try:  # put it back so the watch has something to hold
                    marker.parent.mkdir(parents=True, exist_ok=True)
                    marker.write_text("", encoding="utf-8")
                except OSError:
                    pass
            if str(path) not in self._reload_watcher.files():
                self._reload_watcher.addPath(str(path))
            if not nonce or nonce == self._reload_nonce:
                return  # noise on a shared-temp file, not the agent asking
            self._reload_nonce = nonce
            self._request_reload()

        def _apply_restore(self, r: dict) -> None:
            """Re-open the saved phase + the bench agent drawer after a self-reload,
            and RE-SPAWN every OTHER project's parked agent (hidden, resumed +
            auto-continuing) so a reload doesn't knock out work in any project."""
            phase = r.get("phase")
            if phase in PHASES:
                self._show_phase(phase)
            if not self._agent_btn.isEnabled():
                return
            here = str(self._path)
            for a in r.get("parked", []):
                proj, sid, was_open = a.get("project"), a.get("session_id"), a.get("open")
                if sid and proj != here:  # the bench one is handled below
                    self._respawn_parked(proj, sid, was_open)
            if r.get("agent"):
                # restore the pinned id BEFORE spawning so the resume targets the
                # exact same conversation (claude --resume <id>), not "most recent"
                self._agent_session_id = r.get("session_id")
                self._resume_agent = bool(r.get("resume")) and bool(self._agent_session_id)
                self._agent_btn.setChecked(True)
                self._toggle_agent()

        def _respawn_parked(self, project: str, session_id: str, was_open: bool) -> None:
            """Bring a NON-bench project's agent back to life after a reload: a
            hidden, parked terminal that resumes the pinned thread and auto-continues
            its interrupted turn, ready to re-attach when you switch to that project."""
            from trackerkeeper import terminal

            cont = os.environ.get("TRACKERKEEPER_AGENT_RESUME_PROMPT", "continue") or None
            argv = terminal.claude_argv(session_id=session_id, resume=True, prompt=cont)
            term = terminal.TerminalWidget(
                argv, cwd=str(Path(project).parent), parent=self._term_host)
            term.exited.connect(self._on_agent_exit)
            term.hide()
            self._parked_agents[project] = (term, session_id, bool(was_open))

        def _busy_projects(self) -> list[str]:
            """Which OTHER projects have an agent mid-turn right now (sorted names).

            Only PARKED agents count. The bench agent is excluded on purpose: a
            reload is normally requested BY it (`trackerkeeper-breadboard reload` after it
            edited trackerkeeper), so it's mid-turn by definition — waiting on it would
            mean never reloading at all. Busy is DETECTED from the pty, not
            recorded: a working claude streams output, an idle one sits silent."""
            busy = []
            for proj, (term, _sid, _open) in self._parked_agents.items():
                if term.idle_seconds() < AGENT_IDLE_SECONDS:
                    busy.append(Path(proj).parent.name or proj)
            return sorted(busy)

        def _defer_reload(self, busy: list[str]) -> None:
            """Hold the reload while `busy` projects work; re-check on a timer and
            let it through the moment they're quiet. The maker sees what it's
            waiting on rather than an app that silently refuses to restart."""
            self._pending_reload = True
            self._winddown_note.setText(
                "reload waiting on " + ", ".join(busy) + "…")
            if self._reload_wait is None:
                self._reload_wait = QTimer(self)
                self._reload_wait.setInterval(1000)
                self._reload_wait.timeout.connect(self._retry_pending_reload)
            self._reload_wait.start()

        def _retry_pending_reload(self) -> None:
            """Tick while a reload is queued: still busy → refresh the note (the
            set of working projects can change); all idle → take the reload."""
            if not self._pending_reload:
                self._cancel_pending_reload()
                return
            busy = self._busy_projects()
            if busy:
                self._winddown_note.setText(
                    "reload waiting on " + ", ".join(busy) + "…")
                return
            self._request_reload()  # clears the pending state, then exec's away

        def _cancel_pending_reload(self) -> None:
            """Drop any queued reload and its note (it either landed or was blocked)."""
            self._pending_reload = False
            if self._reload_wait is not None:
                self._reload_wait.stop()
            if self._winddown_note.text().startswith("reload waiting on"):
                self._winddown_note.setText("")

        def _request_reload(self) -> None:
            from PySide6.QtWidgets import QMessageBox

            ok, err = _validate_reload_imports()
            if not ok:
                QMessageBox.warning(
                    self, "Reload blocked",
                    "The code on disk didn't import — not restarting (your running "
                    "app is untouched). Fix this, then reload again:\n\n"
                    + (err or "(no detail)")[-1500:])
                self._cancel_pending_reload()
                return
            # Never yank the app out from under ANOTHER project's working agent:
            # restarting kills its pty mid-turn, and the resume re-drives it with a
            # bare "continue". Queue instead and fire the moment they're all idle.
            busy = self._busy_projects()
            if busy:
                self._defer_reload(busy)
                return
            self._cancel_pending_reload()
            # PARKED agents (other projects, running in the background) must survive
            # the reload too — otherwise it knocks out work in every project but the
            # one on the bench. Capture them so _apply_restore re-spawns each.
            parked = [
                {"project": proj, "session_id": sid, "open": was_open}
                for proj, (_term, sid, was_open) in self._parked_agents.items() if sid
            ]
            restore = {
                "project": str(self._path),
                "phase": self._current_phase(),
                # resume the agent only if a terminal is live right now
                "agent": self._term is not None and not self._term_host.isHidden(),
                "resume": self._term is not None,
                "session_id": self._agent_session_id,  # resume THIS exact thread
                "parked": parked,  # every OTHER project's live agent, resumed too
            }
            get_settings().save_geometry(self.window())  # execv skips closeEvent
            self._cleanup()  # stop probes/timers + close the pty (claude flushed)
            import json

            os.environ["TRACKERKEEPER_BREADBOARD_RESTORE"] = json.dumps(restore)
            argv = [sys.executable, "-m", f"{_PKG}.breadboard", *sys.argv[1:]]
            try:
                os.execve(sys.executable, argv, os.environ)
            except OSError as e:  # exec failed → we're still alive; report it
                os.environ.pop("TRACKERKEEPER_BREADBOARD_RESTORE", None)
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.critical(self, "Reload failed", f"Couldn't relaunch:\n{e}")

        # ── the top bar: title = <app> · <project ▾ dropdown> + hamburger ─
        def _install_top_bar(self, window) -> None:
            """Fold the maker controls into the window's single top bar: the current
            project is a DROPDOWN right in the title (``<app> · <project> ▾`` — a
            click switches loaf, a pinch faster than the menu); Open and Wind down
            hang off the hamburger; the small wind-down note rides the bar. A no-op
            when there's no window (headless / tests)."""
            top = getattr(window, "top_bar", None)
            if top is None or not hasattr(top, "set_menu_builder"):
                return
            self._project_btn = QPushButton("")
            self._project_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._project_btn.setToolTip("Switch project")
            self._project_btn.setStyleSheet(
                "QPushButton{border:none;background:transparent;color:#cfd2da;"
                "font-size:14px;font-weight:600;padding:2px 8px;border-radius:6px;}"
                "QPushButton:hover{background:rgba(255,255,255,0.08);color:#fff;}")
            self._project_btn.clicked.connect(self._open_project_menu)
            top.add_left_widget(self._project_btn)
            top.set_menu_builder(self._populate_menu)
            top.add_right_widget(self._winddown_note)
            self._update_title()

        def _update_title(self) -> None:
            """Title reads ``<app> ·`` with the current project as the ▾ dropdown
            beside it — "trackerkeeper · trackerkeeper ▾" here, "trackerkeeper · butterpdf ▾" with a sibling
            on the bench."""
            top = getattr(self._window, "top_bar", None)
            if top is None or not hasattr(top, "title"):
                return
            app = self._window.windowTitle() or _PKG
            proj = self._board.get("product", "")
            top.title.setText(f"{app}  ·" if proj else app)
            if getattr(self, "_project_btn", None) is not None:
                self._project_btn.setText(f"{proj}  ▾")

        def _fill_project_menu(self, menu) -> None:
            """Populate the project dropdown: every discovered loaf, the one on the
            bench ticked; picking one switches. Split from :meth:`_open_project_menu`
            so it can be driven without blocking on a modal exec()."""
            for product, bpath in self._projects:
                label = product + ("  (here)" if bpath == self._home_path else "")
                act = menu.addAction(label)
                act.setCheckable(True)
                act.setChecked(Path(bpath) == self._path)
                act.triggered.connect(lambda _=False, p=bpath: self._pick_project(p))

        def _open_project_menu(self) -> None:
            """The title's project dropdown, dropped under the button. Built fresh
            per open (so it's frosted + accent-current)."""
            from trackerkeeper import ui_helpers

            menu = ui_helpers.opaque_menu(self, blur_corner_radius=8)
            self._fill_project_menu(menu)
            btn = self._project_btn
            menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

        def _populate_menu(self, menu) -> None:
            """The hamburger — now just Open project… and Wind down… (project
            switching moved to the title dropdown). Built fresh per open."""
            menu.addAction("Open project…").triggered.connect(self._open_project)
            wind = menu.addAction("Wind down…")
            wind.setToolTip(self._wind_tip)
            wind.triggered.connect(self._request_wind_down)

        def _pick_project(self, bpath) -> None:
            if Path(bpath) != self._path:
                self.set_project(Path(bpath))

        def _open_project(self) -> None:
            """Open a board that wasn't auto-discovered — pick its
            ``*-breadboard.toml`` and put it on the bench."""
            from PySide6.QtWidgets import QFileDialog

            picked, _ = QFileDialog.getOpenFileName(
                self, "Open a breadboard", str(self._root),
                "Breadboard (*-breadboard.toml);;All files (*)")
            if not picked:
                return
            p = Path(picked)
            if not any(bp == p for _, bp in self._projects):  # remember it in the picker
                self._projects.append((_project_info(p.parent)["slug"], p))
            self.set_project(p)  # next hamburger open rebuilds with the new loaf

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
            self._park_agent()  # keep this project's agent running in the background
            self._agent_btn.setChecked(False)
            self._agent_btn.setText("⌨ Agent")  # reset label; _unpark flips it back if open
            self._term_host.setVisible(False)
            self._watcher.removePath(str(self._path))
            self._path = Path(new_path)
            self._root = self._path.parent
            self._board = load(self._path)
            self._channel_rows = None
            self._winddown_note.setText("")
            self._watcher.addPath(str(self._path))
            self._watch_reload_marker()  # a reload now targets THIS project
            self._goal.setText(self._board.get("goal", ""))
            self._update_title()  # <app> · <new project>
            self._rebuild_pages()
            self._show_phase(self._first_open_phase())
            self._unpark_agent()  # bring back this project's agent if it's still live

        def _is_home(self) -> bool:
            return self._path == self._home_path

        def _request_wind_down(self) -> None:
            """The board write is the durable half — it survives a closed window and
            whoever opens the project next. But a file nothing announces is a request
            an agent mid-session never sees, so when THIS project's agent is live we
            also type the ask straight into its prompt."""
            self._board["agent_request"] = (
                f"wind down — requested by the maker {date.today().isoformat()}"
            )
            self._write()
            prompt = os.environ.get("TRACKERKEEPER_WIND_DOWN_PROMPT") or WIND_DOWN_PROMPT
            self._winddown_note.setText(
                "handing the wind-down to the agent…" if self._send_to_agent(prompt)
                else "wind-down requested — the agent will land it")

        def _send_to_agent(self, text: str) -> bool:
            """Hand `text` to this project's live agent and REVEAL the drawer, so the
            maker watches it arrive instead of trusting a note. False when no agent is
            running here (nothing to poke — the board write stands on its own).

            True means only that a live terminal took the keystrokes; whether they
            SUBMITTED lands later on ``submitted`` (the terminal withholds the Return
            when the text never echoes — see :meth:`terminal.TerminalWidget.send_prompt`).
            Revealing the drawer either way is the point: if a dialog is sitting on the
            agent's prompt, the maker now sees the dialog instead of a silent nothing.

            Mid-turn is fine and deliberate: Claude Code queues input typed while it
            works, so the ask lands at the end of the current turn rather than being
            dropped. The current project's agent is always ``self._term`` — a sibling's
            is parked, and parked agents belong to their own board's button."""
            term = self._term
            if term is None or not term.send_prompt(text):
                return False
            if not self._agent_btn.isChecked():  # closed (or never opened) → show it
                self._agent_btn.setChecked(True)
                self._toggle_agent()
            return True

        def _on_agent_submitted(self, ok: bool) -> None:
            """Settle the wind-down note once the terminal knows whether its Return
            went in. Leaves any OTHER status alone — a queued reload owns the same
            label and must not be overwritten by a stale send."""
            if not self._winddown_note.text().startswith("handing the wind-down"):
                return
            self._winddown_note.setText(
                "wind-down sent to the agent" if ok else
                "the agent didn't take it — the request is on the board")

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
            # Never scroll sideways — content WRAPS to the width instead of clipping
            # off the right edge (these are single-column text pages).
            s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            s.setWidget(inner)
            # the slim, auto-fading accent pills the app family uses everywhere
            # (no track, no gutter fill — just the handle over the frost)
            ui_helpers.install_autofade_scrollbars(s)
            return s

        @staticmethod
        def _kicker(text: str) -> QLabel:
            """A small uppercase section header — a consistent, quiet label that
            groups the cover page's sections without competing with the content."""
            lab = QLabel(text.upper())
            lab.setStyleSheet("color:#7c7c88;font-size:11px;font-weight:700;")
            lab.setContentsMargins(2, 6, 0, 0)
            return lab

        # ── Ingredients: the app summary page ─────────────────────────────
        def _build_ingredients(self) -> QWidget:
            side = _project_info(self._root)
            self._slug = side["slug"]
            inner = QWidget()
            vbox = QVBoxLayout(inner)
            vbox.setContentsMargins(4, 4, 4, 4)
            vbox.setSpacing(9)

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

            vbox.addWidget(self._kicker("Purpose"))
            self._purpose = QPlainTextEdit(self._board.get("purpose", ""))
            self._purpose.setPlaceholderText(
                "Boil the app down — who is this for? what does v1 do? what's "
                "deliberately out? (the agent reads this)")
            self._purpose.setFixedHeight(84)
            self._purpose.setStyleSheet(f"QPlainTextEdit{{{_EDIT_QSS}}}")
            self._purpose.textChanged.connect(self._purpose_changed)
            vbox.addWidget(self._purpose)

            if side["feature_cards"]:
                vbox.addWidget(self._kicker("Features"))
                for fc in side["feature_cards"]:
                    body = self._wrappable(fc.get("body", ""))
                    lab = QLabel(f"<b>{fc.get('title', '')}</b> — {body}")
                    lab.setWordWrap(True)
                    lab.setTextFormat(Qt.TextFormat.RichText)
                    lab.setStyleSheet(type_qss(TYPE_BODY) + "color:#bbb;")
                    lab.setContentsMargins(2, 0, 0, 0)
                    vbox.addWidget(lab)

            # A setup aid for the ingredients phase: check items off as the initial
            # pieces land, and they DROP OFF the cover page (kept in the file, just
            # hidden) so a finished brief reads clean. The adder stays to add more.
            vbox.addWidget(self._kicker("Checklist"))
            for item in self._board.get("ingredients", []):
                if not item.get("done"):
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
            # NO side margins: the lane band spans the full viewport width so its
            # left/right edges land flush with the agent terminal below (which has
            # no scrollbar gutter). The vertical pill floats (see _OverlayScrollArea).
            row.setContentsMargins(0, 4, 0, 4)
            row.setSpacing(10)
            titles = {"now": "Now", "next": "Next", "later": "Later", "done": "Done ✓"}
            col_scrolls: list = []  # the 4 column scrollers, shared for Shift+wheel
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

                # header — the title, plus a newest/oldest toggle on Done
                head = QHBoxLayout()
                head.setContentsMargins(0, 0, 0, 0)
                title = QLabel(titles[col])
                title.setStyleSheet(
                    f"color:{'#8f8' if col == 'done' else '#fff'};font-weight:bold;")
                head.addWidget(title)
                head.addStretch(1)
                if col == "done":
                    newest = self._done_sort == "newest"
                    sort_btn = QPushButton("newest ↓" if newest else "oldest ↑")
                    sort_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    sort_btn.setToolTip("Sort completed items newest- or oldest-first")
                    sort_btn.setStyleSheet(
                        "QPushButton{border:none;border-radius:6px;padding:1px 8px;"
                        "background:rgba(255,255,255,0.06);color:#9a9;font-size:11px;}"
                        "QPushButton:hover{background:rgba(140,255,140,0.18);color:#fff;}")
                    sort_btn.clicked.connect(self._toggle_done_sort)
                    head.addWidget(sort_btn)
                v.addLayout(head)

                # the CARDS ride in their OWN bounded, independently-scrollable
                # area, so a long column scrolls itself instead of stretching the
                # whole board taller. Plain wheel scrolls this column; Shift+wheel
                # scrolls all four together (see _ColumnScroll). The pill sits in a
                # gutter beside the cards, never over them.
                cards = QWidget()
                cl = QVBoxLayout(cards)
                cl.setContentsMargins(0, 0, 0, 0)
                cl.setSpacing(6)
                for item in self._baking_items(col):
                    cl.addWidget(self._build_card(item, col))
                cl.addStretch(1)
                scroll = _ColumnScroll(cards, col_scrolls)
                col_scrolls.append(scroll)
                v.addWidget(scroll, 1)  # fills the column's spare height

                if col != "done":
                    adder = QLineEdit()
                    adder.setPlaceholderText("add…")
                    adder.setStyleSheet(f"QLineEdit{{{_EDIT_QSS}}}")
                    adder.returnPressed.connect(
                        lambda c=col, e=adder: self._add_item("baking", e.text(), priority=c))
                    v.addWidget(adder)  # pinned below the scroll, always reachable
                row.addWidget(frame, 1)
            return inner  # columns are self-bounded; the page itself never scrolls

        def _baking_items(self, col: str) -> list:
            """The baking items in ``col``, in display order. The Done column is
            sorted by completion ``date`` per :attr:`_done_sort` (newest- or
            oldest-first, stable within a day); the priority columns keep file
            order."""
            items = [
                it for it in self._board.get("baking", [])
                if (it.get("done") and col == "done")
                or (not it.get("done") and it.get("priority") == col)]
            if col == "done":
                items.sort(key=lambda it: it.get("date", ""),
                           reverse=self._done_sort == "newest")
            return items

        def _toggle_done_sort(self) -> None:
            self._done_sort = "oldest" if self._done_sort == "newest" else "newest"
            self._rebuild_pages()

        @staticmethod
        def _wrappable(text: str, n: int = 16) -> str:
            """Let a word-wrap QLabel break an over-long unbroken token (a path, a
            code identifier) instead of forcing the whole column wider — which
            clipped the rightmost lane until you stretched the window. Splits any
            run of >``n`` non-space chars with zero-width breaks (U+200B: invisible,
            not a real space, so the text still reads and copies cleanly-ish)."""
            import re

            zwsp = "​"

            def _split(m):
                tok = m.group(0)
                return zwsp.join(tok[i:i + n] for i in range(0, len(tok), n))

            return re.sub(r"\S{%d,}" % (n + 1), _split, text)

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
            # Lead with the agent's plain-language SUMMARY (what the task takes care
            # of) so the card reads naturally; fall back to the precise `text` when
            # there's no summary. Clicking the card opens a frosted popup with the
            # full detail (see _open_card_detail).
            text = item.get("text", "")
            summary = (item.get("summary") or "").strip()
            lab = QLabel(self._wrappable(summary or text))
            lab.setWordWrap(True)
            lab.setStyleSheet(
                type_qss(TYPE_BODY) + ("color:#9a9;" if done else "color:#ddd;"))
            v.addWidget(lab)
            card.setCursor(Qt.CursorShape.PointingHandCursor)

            def _open(e, it=item, c=col):
                from PySide6.QtCore import Qt as _Qt
                if e.button() == _Qt.MouseButton.LeftButton:
                    self._open_card_detail(it, c)

            card.mousePressEvent = _open  # a click anywhere but the mini-buttons
            stamp = f"{item.get('by', '')} {item.get('date', '')}".strip()
            if stamp or item.get("note"):
                meta = QLabel(self._wrappable(
                    stamp + ("  ·  " + item["note"] if item.get("note") else "")))
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

        def _open_card_detail(self, item: dict, col: str) -> None:
            """Expand a card into a frosted popup (same chrome as Settings): the
            plain summary as the headline, then the full precise text, the note, and
            the stamp — whatever detail the card carries, laid out to read."""
            from trackerkeeper.frosted_dialog import FrostedDialog

            text = item.get("text", "")
            summary = (item.get("summary") or "").strip()
            title = "Done" if col == "done" else col.capitalize()
            dlg = FrostedDialog(self.window(), title=title, min_width=440)
            cl = dlg.content_layout

            head = QLabel(summary or text)
            head.setWordWrap(True)
            head.setStyleSheet(type_qss(TYPE_TITLE) + "color:#fff;")
            cl.addWidget(head)

            def _detail(kick: str, body_text: str) -> None:
                cl.addWidget(self._kicker(kick))
                lbl = QLabel(body_text)
                lbl.setWordWrap(True)
                lbl.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                    | Qt.TextInteractionFlag.TextSelectableByKeyboard)
                lbl.setStyleSheet(type_qss(TYPE_BODY) + "color:#cfd2da;")
                cl.addWidget(lbl)

            if summary and text and summary != text:
                _detail("Detail", text)  # the precise wording / directive
            if item.get("note"):
                _detail("Note", item["note"])
            stamp = f"{item.get('by', '')} {item.get('date', '')}".strip()
            if stamp:
                s = QLabel(stamp)
                s.setStyleSheet("color:#777;font-size:11px;")
                cl.addWidget(s)
            dlg.exec()

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
            # An indicator-only checkbox + a WORD-WRAPPING label beside it: a
            # QCheckBox won't wrap its own text, so a long brief item would force the
            # whole page wider than the window (and clip). Top-align so a wrapped,
            # multi-line item still lines up with the tick.
            box = QCheckBox()
            box.setChecked(bool(item.get("done")))
            box.setStyleSheet(
                f"QCheckBox::indicator:checked{{background:{accent};"
                f"border:1px solid {accent};border-radius:3px;}}"
                "QCheckBox::indicator{width:14px;height:14px;border:1px solid "
                "rgba(255,255,255,0.35);border-radius:3px;}")
            box.toggled.connect(lambda on, it=item: self._set_done(it, on))
            row.addWidget(box, 0, Qt.AlignmentFlag.AlignTop)
            lab = QLabel(self._wrappable(item.get("text", "")))
            lab.setWordWrap(True)
            lab.setStyleSheet(type_qss(TYPE_BODY) + "color:#ddd;")
            row.addWidget(lab, 1)
            stamp = QLabel(f"{item.get('by', '')} {item.get('date', '')}".strip())
            stamp.setStyleSheet("color:#777;font-size:11px;")
            row.addWidget(stamp, 0, Qt.AlignmentFlag.AlignTop)
            note = QLineEdit(item.get("note", ""))
            note.setPlaceholderText("note to the agent…")
            # flex, don't pin: shrinks on a narrow window instead of clipping
            note.setMinimumWidth(120)
            note.setMaximumWidth(240)
            note.setStyleSheet(
                "QLineEdit{background:rgba(255,255,255,0.05);border:1px solid "
                "rgba(255,255,255,0.10);border-radius:6px;padding:3px 8px;color:#cbb8ff;}")
            note.editingFinished.connect(lambda it=item, e=note: self._set_note(it, e.text()))
            row.addWidget(note, 0, Qt.AlignmentFlag.AlignTop)
            return row

        # ── edits (every one writes the file) ─────────────────────────────
        def _stamp(self, item: dict) -> None:
            item["by"] = "maker"
            item["date"] = date.today().isoformat()

        def _set_done(self, item: dict, on: bool) -> None:
            item["done"] = on
            self._stamp(item)
            self._write()
            self._rebuild_pages()  # a checked ingredients item drops off the page

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

    return BoardView(window)


# ── the headless CLI (agent-facing: edit the board without hand-writing TOML) ──


def _find_item(board: dict, iid: str) -> "tuple[str | None, dict | None]":
    """(phase, item) for the item whose id is ``iid``, or (None, None)."""
    for phase in PHASES:
        for item in board.get(phase, []):
            if item.get("id") == iid:
                return phase, item
    return None, None


def _print_board(board: dict, only: str | None = None) -> None:
    """A readable dump — the ids + state every other subcommand takes as input."""
    req = board.get("agent_request", "")
    if req and not only:
        print(f"! agent_request: {req}")
    for phase in ([only] if only else PHASES):
        items = board.get(phase, [])
        openn = sum(1 for i in items if not i.get("done"))
        print(f"# {phase}  ({openn} open / {len(items)})")
        for it in items:
            box = "x" if it.get("done") else " "
            prio = (f" [{it.get('priority')}]"
                    if phase == "baking" and it.get("priority") else "")
            note = f"  — {it['note']}" if it.get("note") else ""
            summ = f"  ~ {it['summary']}" if it.get("summary") else ""
            print(f"  [{box}] {it.get('id', '??????')}  {it.get('text', '')}{prio}{summ}{note}")


def _cmd_reload(board: Path) -> int:
    """Ask the running breadboard window to restart onto the code now on disk,
    resuming this agent session (`claude --continue`). This is how the agent
    ships its own edits to the app it's running inside — no maker button.

    Validates the code imports FIRST: a syntax error the agent just left is
    reported here (non-zero exit) and the running app is left untouched. On
    success it touches the marker the window file-watches; the window validates
    again, saves its place, and exec's into the new code."""
    ok, err = _validate_reload_imports()
    if not ok:
        print("reload blocked — the code on disk didn't import; the running app "
              "is untouched. Fix this, then reload again:\n" + (err or "(no detail)"),
              file=sys.stderr)
        return 1
    import time

    marker = _reload_marker_path(board)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(time.time_ns()), encoding="utf-8")  # a fresh nonce → fires the watch
    except OSError as e:
        print(f"couldn't signal the window: {e}", file=sys.stderr)
        return 1
    print("reload requested — the breadboard restarts onto your new code and this "
          "session resumes automatically. If another project's agent is mid-turn "
          "the restart waits until it's idle, so it may not be instant.")
    return 0


def _apply_cmd(args, path: Path) -> int:
    """Run one headless subcommand: load → mutate → byte-stable save. The open
    window's file-watch live-reloads each change, so the maker sees it land."""
    if args.cmd == "reload":  # not a board edit — signals the running window
        return _cmd_reload(path)
    if not path.is_file():
        print(f"no board at {path} — seed one with `{_PKG}-breadboard --init`",
              file=sys.stderr)
        return 1
    board = load(path)

    if args.cmd == "list":
        _print_board(board, args.phase)
        return 0

    if args.cmd == "add":
        item = {
            "text": args.text, "done": bool(args.done),
            "by": args.by, "date": date.today().isoformat(), "note": args.note or "",
            "summary": args.summary or "",
        }
        if args.phase == "baking":
            item["priority"] = args.priority or "next"
        board.setdefault(args.phase, []).append(item)
        save(path, board)  # mints the stable id in place
        print(item["id"])  # the handle for a later check/note/rm
        return 0

    if args.cmd == "request":
        board["agent_request"] = "" if args.clear else args.text
        save(path, board)
        print("agent_request cleared" if args.clear or not args.text
              else f"agent_request set: {board['agent_request']}")
        return 0

    # everything below addresses one existing item by its id
    phase, item = _find_item(board, args.id)
    if item is None:
        print(f"no breadboard item with id {args.id!r} "
              f"(run `{_PKG}-breadboard list` to see ids)", file=sys.stderr)
        return 1
    if args.cmd == "check":
        item["done"] = not args.off
        item["by"] = args.by
        item["date"] = date.today().isoformat()
        if args.note is not None:
            item["note"] = args.note
        msg = "reopened" if args.off else "done"
    elif args.cmd == "note":
        item["note"] = args.text
        msg = "note set"
    elif args.cmd == "summary":
        item["summary"] = args.text
        msg = "summary set"
    elif args.cmd == "priority":
        if phase != "baking":
            print(f"priority applies to baking items; {args.id} is in {phase}",
                  file=sys.stderr)
            return 1
        item["priority"] = args.priority
        msg = f"priority → {args.priority}"
    elif args.cmd == "rm":
        board[phase].remove(item)
        msg = "removed"
    save(path, board)
    print(f"{args.id}: {msg}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f"{_PKG}-breadboard",
        description="The live maker board: goals + phase checklists, shared with the AI agent.",
    )
    parser.add_argument("--init", action="store_true",
                        help=f"seed a fresh {FILENAME} (refuses to overwrite)")
    sub = parser.add_subparsers(
        dest="cmd", metavar="<command>",
        help="edit the board headlessly (no window); omit to open the window")

    p = sub.add_parser("list", help="print items with their ids + state")
    p.add_argument("phase", nargs="?", choices=PHASES, help="only this phase")

    p = sub.add_parser("add", help="add an item to a phase; prints its new id")
    p.add_argument("phase", choices=PHASES)
    p.add_argument("text")
    p.add_argument("--priority", choices=PRIORITIES, help="baking column (default next)")
    p.add_argument("--by", default="agent", help="who added it (default agent)")
    p.add_argument("--note", default="", help="a note on the item")
    p.add_argument("--summary", default="",
                   help="plain-language one-liner shown on the card (the precise "
                        "`text` stays as the hover detail)")
    p.add_argument("--done", action="store_true", help="add it already checked")

    p = sub.add_parser("check", help="mark an item done (--off to reopen)")
    p.add_argument("id")
    p.add_argument("--off", action="store_true", help="uncheck instead of check")
    p.add_argument("--by", default="agent")
    p.add_argument("--note", default=None, help="also set the item's note")

    p = sub.add_parser("note", help="set an item's note")
    p.add_argument("id")
    p.add_argument("text")

    p = sub.add_parser(
        "summary", help="set an item's plain-language card summary (natural language)")
    p.add_argument("id")
    p.add_argument("text")

    p = sub.add_parser("priority", help="move a baking item between kanban columns")
    p.add_argument("id")
    p.add_argument("priority", choices=PRIORITIES)

    p = sub.add_parser("rm", help="remove an item")
    p.add_argument("id")

    p = sub.add_parser("request", help="set / clear the top-level agent_request")
    p.add_argument("text", nargs="?", default="")
    p.add_argument("--clear", action="store_true", help="clear it (once you've fulfilled it)")

    sub.add_parser(
        "reload",
        help="restart the running app onto your new code (resumes this session)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    path = board_path()
    if args.init:
        if path.exists():
            print(f"{path} already exists — not overwriting.", file=sys.stderr)
            return 1
        save(path, default_board(_PKG))
        print(f"seeded {path}. Open it with `{_PKG}-breadboard`.")
        return 0
    if getattr(args, "cmd", None):  # a headless subcommand → no window
        return _apply_cmd(args, path)
    if not path.is_file():
        save(path, default_board(_PKG))
        print(f"(no board yet — seeded {path})")

    # a self-reload relaunch hands us its place back through the environment;
    # pop it so it never leaks into the agent subprocess or a later reload
    restore = _read_restore_env()
    if restore and restore.get("project"):
        rp = Path(restore["project"])
        if rp.is_file():
            path = rp  # re-open the SAME project the maker was on

    from trackerkeeper.app import run_app

    return run_app(lambda window: _make_view(path, restore, window),
                   single_instance=False)


def _read_restore_env() -> dict | None:
    """Decode + consume the self-reload restore token (see BoardView._request_
    reload). Popped from the environment so it can't leak downstream."""
    import json

    raw = os.environ.pop("TRACKERKEEPER_BREADBOARD_RESTORE", None)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
