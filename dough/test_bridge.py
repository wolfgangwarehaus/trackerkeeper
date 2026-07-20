"""Agent test bridge — a dev-only remote-control socket for driving the live app.

OFF by default. Only stood up when ``DOUGH_TEST_BRIDGE=1`` is set at launch
(wired in ``dough.app.run_app``; the fork transform renames the env prefix).

It opens a per-user ``QLocalServer`` (a Unix-domain socket / Windows named
pipe, distinct from the single-instance socket) that accepts newline-delimited
JSON requests and returns newline-delimited JSON responses. Because the server
lives on the GUI thread, each request is evaluated *on the GUI thread* — so it
can safely touch any Qt object, emit ``AppBus`` signals, call window methods,
and read back state.

This is the deterministic control path for driving the app under an agent (the
autonomous-QA pattern jellytoast proved on KDE Wayland / Windows / macOS):
where synthetic OS-level pointer/key input is unreliable (Wayland especially),
a harness instead posts in-process Qt events and reads the same state the UI
reads. See ``docs/TEST_BRIDGE.md``.

Wire protocol (one JSON object per line, UTF-8):

  request:   {"op": "ping"}
             {"op": "click", "object": "settingsButton"}
             {"op": "eval", "code": "<python expression>"}
             {"op": "exec", "code": "<python statements>"}
  response:  {"ok": true,  "result": <json-coerced value>}
             {"ok": false, "error": "<repr>", "traceback": "<str>"}

Built-in ops (all app-agnostic — an app adds its own via
:func:`register_command`):

  ping, windows, tree, click, set_text, screenshot,
  get_setting, set_setting, theme, raise, quit, eval, exec

TMPDIR is load-bearing on Linux/macOS: Qt materialises the local socket under
``QDir::tempPath()`` (``$TMPDIR``, falling back to ``/tmp``). The app and every
client must therefore share the same TMPDIR or they resolve *different* socket
paths and never meet — macOS hands each context a private per-user temp dir,
and sandboxed/systemd launches redirect it on Linux too. jellytoast's QA
harness pins ``TMPDIR=/tmp`` on BOTH sides for exactly this reason; do the
same when driving from a different shell than the one that launched the app.

Client-side idiom: never drive ``app.processEvents()`` / ``QTest.qWait()``
through eval/exec. Spinning a nested event loop inside a handler can tear a
``QLocalSocket`` down on a nested stack (a use-after-free SIGSEGV class the
guards below only partially absorb). To let deferred work settle, sleep on the
CLIENT between requests — the app's own loop keeps running.

SECURITY: eval/exec run arbitrary Python in-process. The server binds to a
user-private local socket (0600 / per-user pipe ACL) and ONLY listens when
DOUGH_TEST_BRIDGE=1. It must never be enabled in a shipped/packaged build.
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import traceback

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer

logger = logging.getLogger(__name__)


def socket_name() -> str:
    """The per-user local-socket name, derived from the identity seam. Shared
    by server and client so Qt resolves both to the same on-disk socket path
    (given a shared TMPDIR — see the module docstring)."""
    from dough import identity

    return f"{identity.app()}-test-bridge-{getpass.getuser()}"


def _coerce(value):
    """Best-effort JSON-safe coercion. Natively serialisable values pass
    through; everything else degrades to its ``repr`` (recursing into
    containers first so a dict/list of objects stays structured)."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(k): _coerce(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_coerce(v) for v in value]
        return repr(value)


# ── command registry ────────────────────────────────────────────────────────
# op name → handler(bridge, args) -> JSON-able result. Handlers run on the GUI
# thread; raising inside one becomes a structured {"ok": false, error,
# traceback} response. Apps EXTEND the bridge by registering their own ops —
# and may OVERRIDE a built-in by re-registering its name (this is also the
# platform hook: swap "screenshot" for a compositor-real backend, see below).

_COMMANDS: dict = {}


def register_command(name: str, handler) -> None:
    """Register (or override) a bridge op. ``handler(bridge, args)`` receives
    the live :class:`TestBridge` and the request dict; whatever it returns is
    JSON-coerced into ``result``. Example (in app code, before ``run_app``)::

        from dough import test_bridge

        def _open_document(bridge, args):
            AppBus.get().files_received.emit([args["path"]])
            return args["path"]

        test_bridge.register_command("open_document", _open_document)

    Then: ``python dev/ctl.py open_document path=/tmp/doc.pdf``."""
    _COMMANDS[str(name)] = handler


def _builtin(name: str):
    def deco(fn):
        _COMMANDS[name] = fn
        return fn

    return deco


def _find_widget(bridge, name: str):
    """Resolve a widget by ``objectName``, falling back to ``accessibleName``
    (so anything named for a screen reader is addressable for free — the a11y
    naming rule pays twice). Visible widgets win over hidden ones."""
    from PySide6.QtWidgets import QApplication

    if not name:
        raise ValueError("missing 'object' (an objectName or accessible name)")
    matches = [w for w in QApplication.allWidgets() if w.objectName() == name]
    if not matches:
        matches = [w for w in QApplication.allWidgets() if w.accessibleName() == name]
    if not matches:
        raise LookupError(f"no widget with objectName or accessibleName {name!r}")
    matches.sort(key=lambda w: (not w.isVisible(),))
    return matches[0]


def _widget_node(w, depth: int) -> dict:
    node = {
        "class": type(w).__name__,
        "name": w.objectName(),
        "a11y": w.accessibleName(),
        "visible": w.isVisible(),
        "enabled": w.isEnabled(),
        "geometry": [w.x(), w.y(), w.width(), w.height()],
    }
    text = getattr(w, "text", None)
    if callable(text):
        try:
            node["text"] = str(text())
        except Exception:
            pass
    if depth > 0:
        kids = [c for c in w.children() if hasattr(c, "isVisible")]  # widgets only
        if kids:
            node["children"] = [_widget_node(c, depth - 1) for c in kids]
    return node


@_builtin("ping")
def _cmd_ping(bridge, args) -> str:
    return "pong"


@_builtin("windows")
def _cmd_windows(bridge, args) -> list:
    """Top-level windows: class, objectName, title, visibility, geometry."""
    from PySide6.QtWidgets import QApplication

    return [
        {
            "class": type(w).__name__,
            "name": w.objectName(),
            "title": w.windowTitle(),
            "visible": w.isVisible(),
            "active": w.isActiveWindow(),
            "geometry": [w.x(), w.y(), w.width(), w.height()],
        }
        for w in QApplication.topLevelWidgets()
    ]


@_builtin("tree")
def _cmd_tree(bridge, args) -> dict:
    """The widget tree under ``object`` (default: the main window), ``depth``
    levels deep (default 8) — the agent's map of what's on screen."""
    root = _find_widget(bridge, args["object"]) if args.get("object") else bridge.win
    return _widget_node(root, int(args.get("depth", 8)))


@_builtin("click")
def _cmd_click(bridge, args) -> dict:
    """Click a widget by objectName / accessible name. Uses QTest, which posts
    *internal* Qt events (no compositor round-trip) — so real click handlers +
    hit-testing run deterministically even on Wayland, where synthetic OS-level
    input is unreliable. ``button`` may be "left" (default) or "right"."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    w = _find_widget(bridge, args.get("object", ""))
    btn = {
        "left": Qt.MouseButton.LeftButton,
        "right": Qt.MouseButton.RightButton,
    }[args.get("button", "left")]
    QTest.mouseClick(w, btn)
    return {"clicked": w.objectName() or w.accessibleName(), "class": type(w).__name__}


@_builtin("set_text")
def _cmd_set_text(bridge, args) -> dict:
    """Set the text of an input widget (QLineEdit / QTextEdit / QPlainTextEdit /
    anything with ``setText``)."""
    w = _find_widget(bridge, args.get("object", ""))
    text = str(args.get("text", ""))
    if hasattr(w, "setPlainText"):
        w.setPlainText(text)
    elif hasattr(w, "setText"):
        w.setText(text)
    else:
        raise TypeError(f"{type(w).__name__} has no setText/setPlainText")
    return {"object": w.objectName(), "text": text}


@_builtin("screenshot")
def _cmd_screenshot(bridge, args) -> dict:
    """Grab a widget (default: the main window) to a PNG at ``path``.

    CAVEAT (hardware-earned in jellytoast QA): ``QWidget.grab()`` renders the
    widget's OWN painting — it is blur-blind. Compositor effects (KWin blur,
    Windows Acrylic, macOS vibrancy) never appear in the shot, so a frosted
    surface looks like its translucent fallback. That's fine for layout /
    content / theme checks, which is why grab() is the base default. To judge
    frost, capture the real composited screen with the OS tool (spectacle /
    screencapture / a DXGI grabber) — or override this op via
    ``register_command("screenshot", ...)`` with a compositor-real backend for
    your platform; the registry is the platform hook."""
    target = _find_widget(bridge, args["object"]) if args.get("object") else bridge.win
    path = args.get("path") or ""
    if not path:
        raise ValueError("missing 'path'")
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    pm = target.grab()
    if not pm.save(path):
        raise RuntimeError(f"grab().save failed for {path}")
    return {"path": path, "width": pm.width(), "height": pm.height()}


@_builtin("get_setting")
def _cmd_get_setting(bridge, args):
    """Read a raw settings key (e.g. ``ui/theme_mode``) from the app's
    QSettings store."""
    from dough.settings import get_settings

    return _coerce(get_settings()._s.value(str(args.get("key", ""))))


@_builtin("set_setting")
def _cmd_set_setting(bridge, args) -> dict:
    """Write a raw settings key. NOTE: this writes the user's REAL config —
    a QA session must restore anything it flips (see docs/TEST_BRIDGE.md)."""
    from dough.settings import get_settings

    key = str(args.get("key", ""))
    if not key:
        raise ValueError("missing 'key'")
    s = get_settings()._s
    s.setValue(key, args.get("value"))
    s.sync()
    return {"key": key, "value": _coerce(args.get("value"))}


@_builtin("theme")
def _cmd_theme(bridge, args) -> dict:
    """Switch the theme live: sets ``theme_mode`` (auto | frosted_dark |
    frosted_light | dark | light) and emits ``AppBus.theme_changed`` so every
    surface re-stamps — the same path the Settings dialog takes."""
    from dough.bus import AppBus
    from dough.settings import get_settings

    mode = str(args.get("mode", ""))
    if not mode:
        raise ValueError("missing 'mode'")
    get_settings().theme_mode = mode
    AppBus.get().theme_changed.emit()
    return {"mode": mode}


@_builtin("raise")
def _cmd_raise(bridge, args) -> bool:
    """Bring the main window to the foreground (the single-instance raise
    path, including the Windows SetForegroundWindow workaround)."""
    from dough.single_instance import force_foreground

    win = bridge.win
    win.show()
    win.raise_()
    win.activateWindow()
    force_foreground(win)
    return True


@_builtin("quit")
def _cmd_quit(bridge, args) -> str:
    """Quit the app. The response is written first; the quit lands on the
    next event-loop pass so the socket can drain."""
    from PySide6.QtCore import QTimer

    QTimer.singleShot(0, bridge.app.quit)
    return "quitting"


class TestBridge(QObject):
    """The GUI-thread command/eval socket. See the module docstring.

    ``namespace_factory`` (optional) is a zero-arg callable returning a dict
    merged OVER the default eval/exec globals (``app``, ``win``, ``bus``,
    ``settings``, ``get_settings``, ``QApplication``, ``QTest``, ``Qt``,
    ``QPoint``). It is invoked fresh per request so late-bound objects (things
    built after first paint) resolve to their current value.
    """

    def __init__(self, app, window, namespace_factory=None):
        super().__init__(app)
        self.app = app
        self.win = window
        self._ns_factory = namespace_factory
        self._server: "QLocalServer | None" = None
        self._buffers: dict[int, bytearray] = {}
        self._socks: dict[int, object] = {}
        self._socket_name = socket_name()
        # Re-entrancy guard. If a handler spins a nested event loop
        # (app.processEvents(), QTest.qWait(), a modal exec()), Qt can deliver
        # another socket's readyRead on top of the current handler. Writing to /
        # tearing down a QLocalSocket from that nested stack is a use-after-free
        # (the documented SIGSEGV class). We refuse to process re-entrantly: the
        # bytes stay buffered and are drained when the outer handler unwinds. A
        # loop-spinning command thus won't get a nested RPC serviced until it
        # returns — by design.
        self._handling = False
        # Sockets whose client disconnected while a handler was parked in a
        # nested event loop (a modal opened by driven code). Torn down only
        # after the outer drain unwinds — deleteLater() from inside the nested
        # loop destroys the C++ socket under the parked frame, which is exactly
        # the use-after-free this guard exists to stop (jellytoast live-crash
        # 2026-07-05: delete-confirm modal + timed-out client).
        self._doomed: list = []

    def start(self) -> bool:
        QLocalServer.removeServer(self._socket_name)
        self._server = QLocalServer(self)
        # This socket evals arbitrary code on the GUI thread — restrict it to
        # the owning user so other local accounts on a shared box can't connect
        # while the dev flag is on (0600 on the Unix socket; ACL-equivalent on
        # Windows named pipes).
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._on_new_connection)
        if not self._server.listen(self._socket_name):
            logger.warning("test bridge listen failed: %s", self._server.errorString())
            return False
        logger.warning(
            "TEST BRIDGE listening on '%s' — remote control socket is OPEN (dev only)",
            self._socket_name,
        )
        return True

    # ── transport (lifted from jellytoast, crash-lessons intact) ──────────

    def _on_new_connection(self):
        if self._server is None:
            return
        sock = self._server.nextPendingConnection()
        if sock is None:
            return
        self._buffers[id(sock)] = bytearray()
        self._socks[id(sock)] = sock
        sock.readyRead.connect(lambda s=sock: self._on_ready_read(s))
        sock.disconnected.connect(lambda s=sock: self._on_disconnected(s))

    def _on_disconnected(self, sock):
        self._buffers.pop(id(sock), None)
        self._socks.pop(id(sock), None)
        if self._handling:
            # A handler further up this stack may still hold `sock`; park it
            # and let the drain tail sweep it once the stack is clear.
            self._doomed.append(sock)
            return
        sock.deleteLater()

    def _on_ready_read(self, sock):
        buf = self._buffers.get(id(sock))
        if buf is None:
            return
        buf += bytes(sock.readAll())
        if self._handling:
            # Re-entrant delivery from a nested event loop spun by driven
            # code. Leave the bytes buffered; the outer handler drains all
            # sockets when it unwinds (see the guard in __init__).
            return
        self._handling = True
        try:
            self._drain()
        finally:
            self._handling = False
            for doomed in self._doomed:
                doomed.deleteLater()
            self._doomed.clear()

    def _drain(self):
        """Process every buffered complete line across all live sockets,
        looping until no buffer holds a newline. Called only from the
        non-re-entrant outer handler."""
        progressed = True
        while progressed:
            progressed = False
            for sid in list(self._buffers.keys()):
                buf = self._buffers.get(sid)
                sock = self._socks.get(sid)
                while buf is not None and sock is not None and b"\n" in buf:
                    line, _, rest = buf.partition(b"\n")
                    buf[:] = rest
                    self._handle_line(sock, bytes(line))
                    progressed = True
                    buf = self._buffers.get(sid)

    def _handle_line(self, sock, raw: bytes):
        resp = self._evaluate(raw)
        if id(sock) not in self._socks:
            # Client gave up while the handler was parked (modal / slow op) —
            # nobody is listening for this response.
            return
        try:
            sock.write((json.dumps(resp) + "\n").encode())
            sock.flush()
        except Exception:
            logger.exception("test bridge failed to write response")

    # ── dispatch ──────────────────────────────────────────────────────────

    def _namespace(self) -> dict:
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication

        from dough.bus import AppBus
        from dough.settings import get_settings

        ns = {
            "app": self.app,
            "win": self.win,
            "bus": AppBus.get(),
            "settings": get_settings(),
            "get_settings": get_settings,
            "QApplication": QApplication,
            # In-process input: QTest posts internal Qt events (no
            # compositor), so QTest.mouseClick/keyClicks drive real click
            # handlers + hit-testing deterministically on Wayland — the
            # reliable real-interaction path.
            "QTest": QTest,
            "Qt": Qt,
            "QPoint": QPoint,
        }
        if self._ns_factory is not None:
            ns.update(self._ns_factory())
        return ns

    def _evaluate(self, raw: bytes) -> dict:
        try:
            req = json.loads(raw.decode())
        except Exception as e:
            return {"ok": False, "error": f"bad request: {e!r}"}
        op = req.get("op")
        if op in ("eval", "exec"):
            return self._eval_exec(op, req.get("code", ""))
        handler = _COMMANDS.get(op)
        if handler is None:
            return {
                "ok": False,
                "error": f"unknown op: {op!r} (known: {sorted(_COMMANDS)} + eval/exec)",
            }
        try:
            return {"ok": True, "result": _coerce(handler(self, req))}
        except Exception as e:
            return {"ok": False, "error": repr(e), "traceback": traceback.format_exc()}

    def _eval_exec(self, op: str, code: str) -> dict:
        try:
            ns = self._namespace()
        except Exception as e:
            return {"ok": False, "error": f"namespace error: {e!r}"}
        try:
            if op == "eval":
                return {"ok": True, "result": _coerce(eval(code, ns))}
            exec(code, ns)
            return {"ok": True, "result": None}
        except Exception as e:
            return {"ok": False, "error": repr(e), "traceback": traceback.format_exc()}
