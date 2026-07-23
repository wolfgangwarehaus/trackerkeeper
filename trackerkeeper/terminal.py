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
# The terminal sits ON GLASS like the kanban cards: a faint translucent panel
# over the window's frost, not an opaque box. Default cells fill nothing (the
# frost shows through); only cells with an explicit colour paint a background.
_PANEL = QColor(14, 15, 22, 96)          # ~38% — dims the frost enough for text
_REVERSE_TEXT = QColor("#14151c")        # dark text for reverse-video cells


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
                os.environ["TERM"] = "xterm-256color"
                os.environ.setdefault("COLORTERM", "truecolor")
                os.execvp(self._argv[0], self._argv)
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
        self._stream.feed(data)
        self.update()

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
        p = QPainter(self)
        default_fg = QColor(_DEFAULT_FG)
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


def claude_argv(resume: bool = False) -> list[str]:
    """The command the breadboard runs — the Claude Code CLI. Overridable via
    TRACKERKEEPER_AGENT_CMD (e.g. a wrapper, or a plain shell to try the terminal).

    ``resume`` adds ``--continue`` so a relaunched breadboard picks the last
    conversation in the project dir back up — the seam that lets trackerkeeper reload
    its own code without dropping the agent session. Only the default ``claude``
    path gets the flag; an explicit override is always run verbatim."""
    import shlex

    override = os.environ.get("TRACKERKEEPER_AGENT_CMD")
    if override:
        return shlex.split(override)
    return ["claude", "--continue"] if resume else ["claude"]


def agent_available() -> bool:
    """True if the agent command resolves on PATH (so the breadboard can offer
    the terminal, or explain that Claude Code isn't installed)."""
    import shutil

    argv = claude_argv()
    return bool(argv) and shutil.which(argv[0]) is not None


if sys.platform == "win32":  # pragma: no cover - documented gap
    # Keep the symbols importable on Windows (is_supported() already returns
    # False) so the breadboard can import this module unconditionally.
    pass
