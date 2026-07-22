"""
Single-instance enforcement.

Standard Qt pattern: QSharedMemory acts as the lock (its existence
proves an instance is running), QLocalServer accepts an out-of-band
"raise me" message from any subsequent launch attempts. Second launch
detects the lock, sends the message via QLocalSocket, exits cleanly.

Why both:
- QSharedMemory alone would let us detect duplicates but not signal
  the running instance to come forward.
- QLocalServer alone would work on a clean exit but races on startup
  (two simultaneous launches both try to create the server).
- Together: the shared-memory create() is atomic and acts as the
  arbiter, the local server is just the message channel.

Stale-segment recovery: if the previous instance was SIGKILL'd, the
shared-memory segment may persist on Linux. We detect this by trying
to *connect* to the local server when attach() succeeds — if no one's
listening, the holder is dead and we force-recover.

File forwarding: the second launch doesn't just say "raise me" — it
forwards its argv (file paths / URLs, the "double-click a document
while the app is already open" case) over the same socket as a small
JSON payload. The primary raises its window and emits
``files_received`` with the normalized list; ``run_app`` re-emits it
on ``AppBus.files_received`` so app code binds with zero references.
A legacy/bare connection (no parseable payload) still means "come
forward" — the raise never depends on the payload.
"""

import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, QSharedMemory, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger(__name__)


def _normalize_args(args) -> list:
    """Normalize a second launch's argv for forwarding: relative file paths
    resolve against the SECOND launch's cwd (the primary's cwd is unrelated —
    ``open doc.pdf`` from a shell must reach it absolute); URLs and
    option-looking tokens (``-…``) pass through untouched."""
    out = []
    for a in args or []:
        s = str(a)
        if not s or s.startswith("-"):
            continue
        # A real URL scheme (file:// http:// myapp://…) — not a Windows drive
        # letter, whose "C:" also contains a colon but is length 1.
        scheme = s.split(":", 1)[0] if ":" in s else ""
        if len(scheme) > 1 and (s[len(scheme) : len(scheme) + 3] == "://"):
            out.append(s)
            continue
        try:
            out.append(str(Path(s).expanduser().resolve()))
        except OSError:
            out.append(s)
    return out


def force_foreground(window) -> None:
    """Bring ``window`` to the actual foreground.

    On Windows, ``raise_()`` / ``activateWindow()`` only *flash* the
    taskbar button for a background process — the OS blocks
    ``SetForegroundWindow`` from a non-foreground process. The standard
    workaround is to temporarily attach our GUI thread's input queue to
    the current foreground window's thread, which makes the call honored.
    No-op on other platforms, where Qt's ``activateWindow()`` already
    foregrounds. Best-effort — never raises.
    """
    from trackerkeeper.platform_compat import IS_WINDOWS

    if not IS_WINDOWS:
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        # Pin the HWND/HANDLE signatures so a 64-bit handle isn't truncated
        # to a 32-bit c_int (ctypes' default) on the way in or back out — the
        # classic ctypes-on-Windows footgun (mirrors win_frameless._user32).
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        for _fn in ("BringWindowToTop", "SetForegroundWindow"):
            getattr(user32, _fn).argtypes = [wintypes.HWND]
        hwnd = int(window.winId())
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        fg = user32.GetForegroundWindow()
        our_tid = user32.GetWindowThreadProcessId(hwnd, None)
        fg_tid = user32.GetWindowThreadProcessId(fg, None)
        if fg_tid and fg_tid != our_tid:
            user32.AttachThreadInput(fg_tid, our_tid, True)
            try:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
            finally:
                user32.AttachThreadInput(fg_tid, our_tid, False)
        else:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
    except Exception as e:  # pragma: no cover — Windows-only
        logger.debug("force_foreground failed: %s", e)


class SingleInstance(QObject):
    """Acquire a per-key application-wide lock. If another instance
    already holds it, signal that instance to raise its window and tell
    the caller to exit. Holds the lock for the lifetime of this object,
    so keep it alive (don't let it be GC'd before the app quits)."""

    # Emitted on the GUI thread when another launch attempt connects
    # to our server. Wire this to the host window's show / raise /
    # activateWindow trio.
    raise_requested = Signal()

    # Emitted (after raise_requested) with the second launch's forwarded
    # file paths / URLs — absolute paths, normalized by _normalize_args on
    # the sending side. Only fires when there's actually something to open.
    files_received = Signal(list)

    # Per-key timeouts. Sub-second so a stale-segment retry doesn't
    # noticeably delay launch, but generous enough to absorb a busy
    # system's scheduler hiccups on a real running instance.
    _CONNECT_TIMEOUT_MS = 500
    _WRITE_TIMEOUT_MS = 500
    # How long a forwarding second launch waits for the primary's "ok" ACK
    # before closing. Generous: the primary may be mid-boot/busy, and the only
    # cost of the wait is a slightly slower second-launch exit.
    _ACK_TIMEOUT_MS = 2000

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self._key = key
        # Per-user socket name avoids collisions across user accounts
        # on a multi-user box (LocalServer's default abstract socket
        # is system-global on Linux).
        import getpass

        from trackerkeeper import identity

        self._socket_name = f"{identity.app()}-{getpass.getuser()}-{key}"
        # The shared-memory segment key must be per-user TOO. On Linux a
        # QSharedMemory key maps to a system-global ftok id, so a bare
        # key collides across user accounts: user B would attach() to
        # user A's segment, fail to reach A's per-user socket (treating
        # it as stale), then fail to create() the still-live segment —
        # and acquire() returns False, so B exits without ever showing a
        # window. Mirror the socket's per-user namespacing.
        self._mem_key = f"{self._socket_name}-shm"
        self._mem: "QSharedMemory | None" = None
        self._server: "QLocalServer | None" = None

    def acquire(self, forward_args=None) -> bool:
        """Try to acquire the lock. Returns True if we're the first
        instance (caller should proceed to build + show the window) or
        False if another instance was found and signaled (caller should
        exit cleanly). On True, also installs the QLocalServer listener
        so future launch attempts can ping us.

        ``forward_args`` (optional, typically ``sys.argv[1:]``) are the
        paths/URLs this launch was asked to open; when another instance is
        found they're normalized and forwarded to it alongside the raise."""
        args = _normalize_args(forward_args)
        mem = QSharedMemory(self._mem_key)
        if mem.attach():
            # Segment exists. Probe the holder via QLocalSocket — if
            # it's reachable, it's a real running instance; if not,
            # it's a stale segment from a crashed previous run.
            if self._signal_existing(args):
                mem.detach()
                return False
            # Stale. Detach so the OS releases the segment, then fall
            # through to create a fresh one.
            mem.detach()

        if not mem.create(1):
            # create() failed. Usually a real race (another launch won
            # between our attach probe and our create) — BUT under the
            # macOS App Sandbox QSharedMemory's POSIX-shm backing is
            # unavailable, so create() ALWAYS fails there. That left the
            # app unable to launch at all: every start saw create() fail,
            # logged "already running", and exited without ever showing a
            # window. So probe for a REAL instance first: if one answers,
            # defer to it; if not, the shared-memory lock is simply
            # unavailable here — fall through and let the QLocalServer
            # listener below be the authoritative single-instance gate
            # (its socket lives in the sandbox-allowed container tmp).
            if self._signal_existing(args):
                return False
            logger.warning(
                "shared-memory lock unavailable (%s); using the local "
                "socket as the single-instance gate",
                mem.errorString(),
            )
        else:
            # We hold the shared-memory lock.
            self._mem = mem

        # Stand up the listener.
        QLocalServer.removeServer(self._socket_name)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        if not self._server.listen(self._socket_name):
            # Listener failed (path conflict, perms, …). The lock is
            # still ours so duplicate launches will be detected, but
            # they won't be able to reach us. Best-effort log, then
            # carry on.
            logger.warning(
                "listener failed: %s", self._server.errorString()
            )
        return True

    def _signal_existing(self, args=None) -> bool:
        """Try to ping the running instance, forwarding this launch's argv
        (``args``, already normalized). Returns True on success (real
        instance reachable), False if the socket is unreachable (likely a
        stale shared-memory segment)."""
        sock = QLocalSocket()
        sock.connectToServer(self._socket_name)
        if not sock.waitForConnected(self._CONNECT_TIMEOUT_MS):
            return False
        # A JSON payload rather than the old bare b"raise": the connection
        # itself still means "come forward"; "args" carries the second
        # launch's files/URLs. Kept one-line-tiny — well under any local
        # socket buffering threshold.
        sock.write(json.dumps({"raise": True, "args": args or []}).encode("utf-8"))
        sock.flush()
        # Drain COMPLETELY before closing: on Windows the payload rides an
        # overlapped pipe writer on a pool thread — a single waitForBytesWritten
        # can return with bytes still queued, and a dying socket cancels the
        # in-flight write (the primary saw the connection, never the files;
        # win CI, 2026-07). Then, when we actually forwarded something, wait
        # briefly for the primary's "ok" ACK before closing — a handle closed
        # before the server READS can still drop buffered pipe data on
        # Windows. No ACK (legacy primary / timeout) degrades to the old
        # behavior: the raise is connection-triggered and never at risk.
        while sock.bytesToWrite() > 0:
            if not sock.waitForBytesWritten(self._WRITE_TIMEOUT_MS):
                break
        if args:
            sock.waitForReadyRead(self._ACK_TIMEOUT_MS)
        sock.disconnectFromServer()
        if sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
            sock.waitForDisconnected(self._WRITE_TIMEOUT_MS)
        return True

    def _on_new_connection(self):
        if self._server is None:
            return
        sock = self._server.nextPendingConnection()
        if sock is None:
            return
        # ANY connection means "another launch happened, please come
        # forward" — the raise must never depend on the payload parsing.
        self.raise_requested.emit()

        # Drain the payload ASYNCHRONOUSLY via readyRead/disconnected rather
        # than blocking waitForReadyRead loops: on Windows named pipes the
        # blocking waits inside the newConnection slot miss data that the
        # event loop delivers fine (the Qt-documented "may fail randomly on
        # Windows" caveat — seen live on the win CI runner: the raise landed,
        # the forwarded files didn't). Once the JSON parses whole, send the
        # "ok" ACK and close from OUR side — the sender holds its handle open
        # until the ACK, which is what keeps Windows from dropping buffered
        # pipe data behind a closed client handle.
        buf = bytearray()
        done = {"v": False}

        def _emit(args) -> None:
            if args:
                self.files_received.emit(args)

        def _try_parse() -> bool:
            try:
                payload = json.loads(bytes(buf).decode("utf-8"))
            except Exception:
                return False  # incomplete (or legacy) — keep accumulating
            done["v"] = True
            try:
                sock.write(b"ok")
                sock.flush()
            except Exception:
                pass
            sock.disconnectFromServer()
            sock.deleteLater()
            _emit([str(a) for a in payload.get("args") or []])
            return True

        def _read():
            buf.extend(bytes(sock.readAll()))
            if not done["v"]:
                _try_parse()

        def _finish():
            # Peer closed without a parsed payload — a legacy bare "raise"
            # ping (or line noise). One last parse over whatever arrived,
            # then let it be a plain raise.
            if done["v"]:
                return
            done["v"] = True
            buf.extend(bytes(sock.readAll()))
            sock.deleteLater()
            try:
                payload = json.loads(bytes(buf).decode("utf-8"))
                args = [str(a) for a in payload.get("args") or []]
            except Exception:
                args = []
            _emit(args)

        sock.readyRead.connect(_read)
        sock.disconnected.connect(_finish)
        # The peer may have written AND disconnected before these connections
        # existed — drain what's buffered, and finish now if it's already gone
        # (the disconnected signal would otherwise never fire).
        _read()
        if (
            not done["v"]
            and sock.state() == QLocalSocket.LocalSocketState.UnconnectedState
        ):
            _finish()
