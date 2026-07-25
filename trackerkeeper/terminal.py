"""An embedded terminal — a PTY-backed VT emulator widget.

A real terminal in a frosted window: it forks a pseudo-terminal, execs a
command (the breadboard runs ``claude`` in the project dir), emulates the VT
stream with ``pyte`` (so a full TUI — cursor moves, colours, the alt-screen —
renders), and paints the character grid itself. Keystrokes and resizes are
forwarded to the child, so it behaves like any terminal.

POSIX only (``pty``); Windows has no ptyfork here — :func:`is_supported`
returns False there and the breadboard shows a note instead. ``pyte`` is a soft
dependency (the ``terminal`` / ``dev`` extra): absent, :func:`is_supported`
is False and nothing imports it at module load.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QSize, QSocketNotifier, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QPainter
from PySide6.QtWidgets import QWidget


def is_supported() -> bool:
    """True where an embedded terminal can run: a POSIX pty + pyte installed."""
    if os.name != "posix":
        return False
    try:
        import pty  # noqa: F401

        import pyte  # noqa: F401
    except Exception:
        return False
    return True


# ANSI 16-colour palette (a calm dark set that reads on the frosted body). pyte
# names yellow "brown"; it also emits 6-hex-digit strings for 256/truecolour.
_ANSI = {
    "black": "#20202a", "red": "#e06c75", "green": "#98c379", "brown": "#d9b06a",
    "blue": "#61afef", "magenta": "#c678dd", "cyan": "#56b6c2", "white": "#c8ccd4",
    "brightblack": "#6b7280", "brightred": "#ef7b85", "brightgreen": "#b5e08e",
    "brightbrown": "#f0c988", "brightblue": "#7cc0ff", "brightmagenta": "#d79bec",
    "brightcyan": "#74d3de", "brightwhite": "#ffffff",
}
_DEFAULT_FG = "#e2e4ec"
# The terminal sits ON GLASS like the kanban lanes, and matches THEM for a
# cohesive board: the same faint white wash over the window's frost the breadboard
# columns use (rgba(255,255,255,0.025)), not a darker opaque box. Default cells
# fill nothing (the frost shows through); only cells with an explicit colour paint.
_PANEL = QColor(255, 255, 255, 6)        # ~2.5% white — matches the kanban lanes
_REVERSE_TEXT = QColor("#14151c")        # dark text for reverse-video cells
_RADIUS = 10                             # rounded panel corners — match the lanes

# pyte stores private DECSET modes shifted left 5 bits (mode << 5). A TUI that
# enables any mouse-tracking mode wants wheel events forwarded (Claude Code turns
# on all three + SGR 1006); we translate the wheel into mouse escapes so it can
# scroll. See wheelEvent.
_MOUSE_MODES = frozenset({1000 << 5, 1002 << 5, 1003 << 5})
_SGR_MOUSE = 1006 << 5


def _qcolor(token: str, default: QColor) -> QColor:
    if token == "default":
        return default
    named = _ANSI.get(token)
    if named:
        return QColor(named)
    if len(token) == 6 and all(c in "0123456789abcdefABCDEF" for c in token):
        return QColor(f"#{token}")
    return default


# Qt key → terminal byte sequence (the non-text keys). Text keys go through
# e.text(); Ctrl+letter is handled separately (the C0 control char).
def _special_key(key, text, shift: bool = False) -> bytes | None:
    from PySide6.QtCore import Qt as _Qt

    # Shift+Tab reaches us either as Key_Backtab or as Key_Tab+Shift (platform-
    # dependent). Both must send the terminal back-tab (CBT) sequence ESC [ Z —
    # what TUIs read as shift-tab, e.g. Claude Code's "cycle permission mode".
    if key == _Qt.Key.Key_Backtab or (key == _Qt.Key.Key_Tab and shift):
        return b"\x1b[Z"
    table = {
        _Qt.Key.Key_Return: b"\r", _Qt.Key.Key_Enter: b"\r",
        _Qt.Key.Key_Backspace: b"\x7f", _Qt.Key.Key_Tab: b"\t",
        _Qt.Key.Key_Escape: b"\x1b",
        _Qt.Key.Key_Up: b"\x1b[A", _Qt.Key.Key_Down: b"\x1b[B",
        _Qt.Key.Key_Right: b"\x1b[C", _Qt.Key.Key_Left: b"\x1b[D",
        _Qt.Key.Key_Home: b"\x1b[H", _Qt.Key.Key_End: b"\x1b[F",
        _Qt.Key.Key_PageUp: b"\x1b[5~", _Qt.Key.Key_PageDown: b"\x1b[6~",
        _Qt.Key.Key_Delete: b"\x1b[3~", _Qt.Key.Key_Insert: b"\x1b[2~",
    }
    return table.get(key)


class TerminalWidget(QWidget):
    """A live terminal running ``argv`` in ``cwd``. Emits :attr:`exited` when the
    child process ends."""

    exited = Signal(int)

    def __init__(self, argv, cwd=None, parent=None) -> None:
        super().__init__(parent)
        import pyte

        self._argv = list(argv)
        self._cwd = str(cwd) if cwd else None
        self._fd = -1
        self._pid = -1
        self._notifier: QSocketNotifier | None = None
        self._dead = False
        self._last_output = time.monotonic()  # for idle_seconds() — see below
        self._wheel_accum = 0  # sub-notch wheel delta, so touchpads scroll too

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setAcceptDrops(True)  # drag an image in → its path reaches the agent
        # No opaque autofill: paintEvent lays down a translucent glass panel so
        # the window's frost shows through (the terminal reads like a card).

        self._font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self._font.setStyleHint(QFont.StyleHint.TypeWriter)
        self._font.setPointSizeF(max(9.5, self._font.pointSizeF() or 10.5))
        fm = QFontMetricsF(self._font)
        self._cw = fm.horizontalAdvance("M")
        self._ch = fm.height()
        self._ascent = fm.ascent()

        cols, rows = 80, 24
        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.ByteStream(self._screen)

        self._start()

    # ── process ──────────────────────────────────────────────────────────
    def _start(self) -> None:
        import pty

        pid, fd = pty.fork()
        if pid == 0:  # child
            try:
                if self._cwd:
                    os.chdir(self._cwd)
                env = agent_env()  # a clean TOP-LEVEL session (see agent_env)
                env["TERM"] = "xterm-256color"
                env.setdefault("COLORTERM", "truecolor")
                os.execvpe(self._argv[0], self._argv, env)
            except Exception:
                os._exit(127)
        self._pid, self._fd = pid, fd
        self._notifier = QSocketNotifier(fd, QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._read)

    def _read(self) -> None:
        try:
            data = os.read(self._fd, 65536)
        except OSError:
            data = b""
        if not data:
            self._on_exit()
            return
        self._last_output = time.monotonic()
        self._stream.feed(data)
        self.update()

    def idle_seconds(self) -> float:
        """How long since the child last wrote anything.

        This is how the breadboard tells a WORKING agent from one parked at its
        prompt without having to ask it: a ``claude`` mid-turn streams output
        continuously, while an idle session sits silent. A dead terminal is
        infinitely idle (nothing to interrupt)."""
        if self._dead:
            return float("inf")
        return max(0.0, time.monotonic() - self._last_output)

    def _on_exit(self) -> None:
        if self._dead:
            return
        self._dead = True
        if self._notifier is not None:
            self._notifier.setEnabled(False)
        code = 0
        try:
            _, status = os.waitpid(self._pid, os.WNOHANG)
            code = os.waitstatus_to_exitcode(status) if status else 0
        except Exception:
            pass
        self.update()
        self.exited.emit(code)

    def stop(self) -> None:
        """Terminate the child and release the pty (idempotent)."""
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier = None
        if self._pid > 0 and not self._dead:
            import signal

            for sig in (signal.SIGHUP, signal.SIGTERM):
                try:
                    os.kill(self._pid, sig)
                except ProcessLookupError:
                    break
            try:
                os.waitpid(self._pid, os.WNOHANG)
            except Exception:
                pass
        if self._fd >= 0:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = -1
        self._dead = True

    # ── geometry / resize ────────────────────────────────────────────────
    def _grid(self) -> tuple[int, int]:
        cols = max(2, int(self.width() / self._cw)) if self._cw else 80
        rows = max(1, int(self.height() / self._ch)) if self._ch else 24
        return cols, rows

    def resizeEvent(self, e) -> None:  # noqa: N802
        cols, rows = self._grid()
        self._screen.resize(rows, cols)
        if self._fd >= 0:
            import fcntl
            import struct
            import termios

            try:
                fcntl.ioctl(self._fd, termios.TIOCSWINSZ,
                            struct.pack("HHHH", rows, cols, 0, 0))
            except OSError:
                pass
        super().resizeEvent(e)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(int(self._cw * 80) + 4, int(self._ch * 20) + 4)

    # ── input ────────────────────────────────────────────────────────────
    def focusNextPrevChild(self, nxt) -> bool:  # noqa: N802, ARG002
        # A terminal owns Tab and Shift+Tab (completion; TUI mode-cycling). Qt's
        # default steals both for focus traversal BEFORE keyPressEvent — return
        # False so they fall through to us and reach the child instead. (You
        # leave the terminal by clicking out, like any real terminal.)
        return False

    def _write(self, data: bytes) -> None:
        """Forward bytes to the child pty (keystrokes, pastes, dropped paths)."""
        if self._dead or self._fd < 0:
            return
        try:
            os.write(self._fd, data)
        except OSError:
            pass

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if self._dead or self._fd < 0:
            return
        mods = e.modifiers()
        key, text = e.key(), e.text()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        # Paste — Ctrl+V, Ctrl+Shift+V, or Shift+Insert. A clipboard IMAGE is
        # materialised to a temp file and its PATH is sent (how the agent ingests
        # a pasted image); text is sent as a bracketed paste.
        if (ctrl and key == Qt.Key.Key_V) or (shift and key == Qt.Key.Key_Insert):
            self._paste()
            return
        payload: bytes | None = None
        seq = _special_key(key, text, shift)
        if seq is not None:
            payload = seq
        elif ctrl and text and text.isalpha():
            payload = bytes([ord(text.lower()) & 0x1F])  # Ctrl+C → \x03, etc.
        elif text:
            payload = text.encode("utf-8")
        if payload:
            self._write(payload)
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        self.setFocus()
        super().mousePressEvent(e)

    def wheelEvent(self, e) -> None:  # noqa: N802
        # A TUI that tracks the mouse scrolls on wheel events — Claude Code
        # enables SGR mouse (1006) + the alt-screen. Translate the wheel into
        # mouse-wheel escapes and forward them. Without mouse tracking there's
        # nothing to scroll (we keep no local scrollback), so let it pass.
        if self._dead or self._fd < 0:
            return
        mode = getattr(self._screen, "mode", frozenset())
        if not (mode & _MOUSE_MODES):
            super().wheelEvent(e)
            return
        self._wheel_accum += e.angleDelta().y()
        steps = int(self._wheel_accum / 120)  # 120 units == one wheel notch
        if steps == 0:
            e.accept()
            return
        self._wheel_accum -= steps * 120
        button = 64 if steps > 0 else 65  # 64 = wheel up, 65 = wheel down
        pos = e.position()
        col = min(self._screen.columns, max(1, int(pos.x() / self._cw) + 1)) if self._cw else 1
        row = min(self._screen.lines, max(1, int(pos.y() / self._ch) + 1)) if self._ch else 1
        sgr = _SGR_MOUSE in mode
        out = bytearray()
        for _ in range(abs(steps)):
            if sgr:  # CSI < Cb ; Cx ; Cy M  (press; wheel has no release)
                out += f"\x1b[<{button};{col};{row}M".encode()
            else:  # legacy X10: button + coords, each offset by 32
                out += b"\x1b[M" + bytes((button + 32, col + 32, row + 32))
        self._write(bytes(out))
        e.accept()

    # ── images: drag an image in, or paste one (Ctrl+V) ──────────────────
    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        md = e.mimeData()
        paths: list[str] = []
        if md.hasUrls():  # a real file (the common case) → send its path verbatim
            paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
        if not paths and md.hasImage():  # raw image data (e.g. from a browser)
            saved = self._materialize_image(md.imageData())
            if saved:
                paths = [saved]
        if paths:
            self.setFocus()
            self._insert_paths(paths)
            e.acceptProposedAction()

    def _paste(self) -> None:
        from PySide6.QtWidgets import QApplication

        md = QApplication.clipboard().mimeData()
        if md.hasImage():
            saved = self._materialize_image(QApplication.clipboard().image())
            if saved:
                self._insert_paths([saved])
                return
        if md.hasUrls():  # a file copied in the file manager
            paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
            if paths:
                self._insert_paths(paths)
                return
        if md.hasText():
            self._write(self._bracketed(md.text()))

    def _insert_paths(self, paths) -> None:
        """Write image/file PATHS into the prompt (space-separated, shell-quoted
        so spaces survive) with a trailing space and NO newline — the agent picks
        the path up as input and attaches the image; the maker keeps typing."""
        import shlex

        self._write((" ".join(shlex.quote(p) for p in paths) + " ").encode("utf-8"))

    @staticmethod
    def _materialize_image(img) -> "str | None":
        """Save a QImage (clipboard/drag data) to a temp PNG; return its path.
        Lets a pasted screenshot reach the agent with zero external clipboard
        tools. Returns None if there's no usable image."""
        from PySide6.QtGui import QImage

        if not isinstance(img, QImage) or img.isNull():
            return None
        import tempfile

        out = Path(tempfile.gettempdir()) / "trackerkeeper-terminal-images"
        out.mkdir(parents=True, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix="paste-", suffix=".png", dir=str(out))
        os.close(fd)
        return path if img.save(path, "PNG") else None

    def _bracketed(self, text: str) -> bytes:
        # Wrap pasted text in bracketed-paste markers when the child turned the
        # mode on (Claude Code does) so a multi-line paste doesn't submit
        # line-by-line; otherwise send it raw. pyte stores private DECSET modes
        # shifted left 5 bits, so 2004 lands as 2004<<5 — accept either form.
        raw = text.encode("utf-8")
        mode = getattr(self._screen, "mode", ())
        if 2004 in mode or (2004 << 5) in mode:
            return b"\x1b[200~" + raw + b"\x1b[201~"
        return raw

    # ── paint ────────────────────────────────────────────────────────────
    def paintEvent(self, e) -> None:  # noqa: N802
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainterPath

        p = QPainter(self)
        default_fg = QColor(_DEFAULT_FG)
        # Rounded glass panel — corners match the kanban cards/lanes above. Clip
        # everything (panel + cells + cursor) to the rounded rect so the frost
        # shows through the corners. Cells already overlap by 1px (see below), so
        # antialiasing the clip edge won't open seams between them.
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), _RADIUS, _RADIUS)
        p.setClipPath(clip)
        # The glass panel — translucent, so the frost behind the window blends
        # through (matches the kanban cards). No opaque box.
        p.fillRect(self.rect(), _PANEL)
        p.setFont(self._font)
        buf = self._screen.buffer
        cur = self._screen.cursor
        cw, chh = self._cw, self._ch
        for y in range(self._screen.lines):
            row = buf[y]
            yy = y * chh
            for x in range(self._screen.columns):
                cell = row[x]
                data = cell.data or " "
                fg = _qcolor(cell.fg, default_fg)
                # A "default" bg means transparent — the panel/frost shows. Only
                # an explicitly-coloured cell paints a background block.
                explicit_bg = cell.bg != "default"
                bg = _qcolor(cell.bg, default_fg) if explicit_bg else None
                xx = x * cw
                if cell.reverse:
                    # Reverse video: the fg colour becomes the block; text flips
                    # to a dark ink that reads on it (default cells included).
                    p.fillRect(int(xx), int(yy), int(cw) + 1, int(chh) + 1, fg)
                    fg = _REVERSE_TEXT
                elif bg is not None:
                    p.fillRect(int(xx), int(yy), int(cw) + 1, int(chh) + 1, bg)
                if data != " ":
                    if cell.bold:
                        f = QFont(self._font)
                        f.setBold(True)
                        p.setFont(f)
                    p.setPen(fg)
                    p.drawText(int(xx), int(yy + self._ascent), data)
                    if cell.bold:
                        p.setFont(self._font)
        # cursor block (only when focused + alive)
        if self.hasFocus() and not self._dead:
            cx, cy = cur.x * cw, cur.y * chh
            p.fillRect(int(cx), int(cy), int(cw), int(chh),
                       QColor(214, 216, 224, 160))
        p.end()

    # ── lifecycle ────────────────────────────────────────────────────────
    def closeEvent(self, e) -> None:  # noqa: N802
        self.stop()
        super().closeEvent(e)


def new_session_id() -> str:
    """A fresh Claude Code session id (UUID) to pin the agent's conversation to."""
    import uuid

    return str(uuid.uuid4())


def claude_argv(session_id: str | None = None, resume: bool = False,
                prompt: str | None = None) -> list[str]:
    """The command the breadboard runs — the Claude Code CLI. Overridable via
    TRACKERKEEPER_AGENT_CMD (e.g. a wrapper, or a plain shell to try the terminal).

    We PIN the agent to a specific ``session_id`` (``--session-id`` on a fresh
    start) so a later reload can ``--resume`` that EXACT conversation — never
    ``--continue``, which resumes "the most recent conversation in this dir" and
    so can grab another ``claude`` running in the same project (e.g. the maker's
    own outer session). ``resume`` picks that pinned thread back up. An explicit
    override is always run verbatim.

    ``prompt`` is a trailing positional message ``claude`` submits on start — how
    a reload RESUME auto-continues the interrupted turn (so the maker doesn't have
    to type "continue" after trackerkeeper restarts to apply the agent's own edits).

    ``TRACKERKEEPER_AGENT_REMOTE_CONTROL`` (opt-in, off by default) appends
    ``--remote-control`` so the session is drivable from the Claude mobile app; a
    non-boolean value also names the Remote Control session."""
    import shlex

    override = os.environ.get("TRACKERKEEPER_AGENT_CMD")
    if override:
        return shlex.split(override)
    if session_id and resume:
        argv = ["claude", "--resume", session_id]  # resume THIS exact thread
    elif session_id:
        argv = ["claude", "--session-id", session_id]  # pin a fresh thread
    elif resume:
        argv = ["claude", "--continue"]  # legacy fallback (no id to pin)
    else:
        argv = ["claude"]
    # Auto mode by default (the Shift+Tab auto-accept state) so the agent lands
    # ready to drive the board without the maker re-arming it each relaunch.
    # TRACKERKEEPER_AGENT_PERMISSION_MODE overrides (any `claude --permission-mode`
    # value); set it empty to pass no flag and take Claude Code's own default.
    mode = os.environ.get("TRACKERKEEPER_AGENT_PERMISSION_MODE", "auto")
    if mode:
        argv += ["--permission-mode", mode]
    # Remote Control — drive THIS session from the Claude mobile app / claude.ai —
    # is opt-in via TRACKERKEEPER_AGENT_REMOTE_CONTROL, off by default (no flag). A truthy
    # value enables it (`--remote-control`); any other value also NAMES the session
    # (`--remote-control <name>`). With it set, a FRESH spawn comes up controllable
    # and, crucially, a post-reload `--resume` re-advertises — so a maker driving
    # from mobile isn't dropped when trackerkeeper restarts to apply the agent's own code
    # edits. (A project SWAP never drops it: the pty is parked alive, not respawned.)
    rc = os.environ.get("TRACKERKEEPER_AGENT_REMOTE_CONTROL", "")
    if rc:
        argv.append("--remote-control")
        if rc.strip().lower() not in {"1", "true", "yes", "on"}:
            argv.append(rc)
    if prompt:  # trailing positional — claude submits it on start (auto-continue)
        argv.append(prompt)
    return argv


def agent_available() -> bool:
    """True if the agent command resolves on PATH (so the breadboard can offer
    the terminal, or explain that Claude Code isn't installed)."""
    import shutil

    argv = claude_argv()
    return bool(argv) and shutil.which(argv[0]) is not None


# Claude Code stamps its own session into the environment. A `claude` that
# INHERITS these markers concludes it's running NESTED inside another Claude
# session (a "child") and runs in a mode that NEVER writes its conversation to
# disk — so a later ``claude --resume <id>`` finds nothing and the chat comes up
# FULLY EMPTY. The breadboard is itself usually launched from inside a Claude
# session (the desktop app, or an agent), so it would pass these straight
# through to the embedded agent and silently break reload-resume. The single
# trigger observed is CLAUDE_CODE_CHILD_SESSION, but the whole CLAUDE_CODE_*
# namespace is Claude Code's own runtime state (none of it user config), so we
# drop all of it plus the few non-prefixed identity markers. Auth (ANTHROPIC_*)
# and user config (CLAUDE_CONFIG_DIR) are deliberately LEFT intact — the agent
# still needs to authenticate; it just must not masquerade as a child session.
_HOST_SESSION_ENV = frozenset({
    "CLAUDECODE", "CLAUDE_PID", "CLAUDE_AGENT_SDK_VERSION", "AI_AGENT",
})


def agent_env(base: "dict | None" = None) -> dict:
    """The child environment for the embedded agent: a copy of ``base`` (the
    current process env by default) with the HOST Claude session's markers
    stripped so the agent runs as a clean TOP-LEVEL session that persists (and
    can therefore be ``--resume``d after a reload). Pure + testable; never
    mutates ``base``."""
    env = dict(os.environ if base is None else base)
    for key in list(env):
        if key.startswith("CLAUDE_CODE_") or key in _HOST_SESSION_ENV:
            del env[key]
    return env


if sys.platform == "win32":  # pragma: no cover - documented gap
    # Keep the symbols importable on Windows (is_supported() already returns
    # False) so the breadboard can import this module unconditionally.
    pass
