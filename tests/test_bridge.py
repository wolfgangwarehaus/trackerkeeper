"""Agent test bridge — driven end-to-end over the real socket.

The app runs as an actual SUBPROCESS (offscreen, DOUGH_TEST_BRIDGE=1) and the
test process is the client — the production shape. In-process both-ends would
deadlock by construction: the server handles requests on the GUI thread, and a
blocking client wait on that same thread would starve it (the same reason the
single-instance forwarding test uses a subprocess).

The subprocess registers a custom command BEFORE run_app, so the test also
proves the app-extension hook round-trips. Its identity is a uuid-suffixed
slug so the socket name (and, via a scratch XDG_CONFIG_HOME, the settings
store) can't collide with a real app or a parallel test run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid

import pytest
from PySide6.QtNetwork import QLocalSocket

_CONNECT_MS = 1000
_IO_MS = 15000

_APP_SCRIPT = """
import sys
import dough

# Identity FIRST (before anything heavy imports) — the uuid slug isolates the
# socket name and the QSettings handle.
dough.configure(org="dough-tests", app=sys.argv[1], display_name="bridge probe")

from dough import test_bridge

def _echo(bridge, args):
    return {"echo": args.get("value"), "win_title": bridge.win.windowTitle()}

test_bridge.register_command("echo", _echo)

from PySide6.QtWidgets import QLineEdit, QPushButton, QVBoxLayout, QWidget

def _content(win):
    w = QWidget()
    lay = QVBoxLayout(w)
    btn = QPushButton("Probe")
    btn.setObjectName("probeButton")
    btn.clicked.connect(
        lambda: win.setProperty("probe_clicks", int(win.property("probe_clicks") or 0) + 1)
    )
    edit = QLineEdit()
    edit.setObjectName("probeInput")
    lay.addWidget(btn)
    lay.addWidget(edit)
    return w

from dough.app import run_app

sys.exit(run_app(_content, single_instance=False))
"""


def _call(name: str, payload: dict, timeout_ms: int = _IO_MS) -> dict:
    """One blocking request/response round-trip, jt_ctl-style. Drains the
    write completely before waiting on the reply (the Windows named-pipe
    lesson from single_instance: one waitForBytesWritten can return with
    bytes still queued, and a dying handle cancels the in-flight write)."""
    sock = QLocalSocket()
    sock.connectToServer(name)
    if not sock.waitForConnected(_CONNECT_MS):
        return {"ok": False, "error": f"connect failed: {sock.errorString()}"}
    sock.write((json.dumps(payload) + "\n").encode())
    sock.flush()
    while sock.bytesToWrite() > 0:
        if not sock.waitForBytesWritten(timeout_ms):
            break
    buf = bytearray()
    while b"\n" not in buf:
        if not sock.waitForReadyRead(timeout_ms):
            break
        buf += bytes(sock.readAll())
    sock.disconnectFromServer()
    line = bytes(buf).split(b"\n", 1)[0].decode(errors="replace")
    if not line:
        return {"ok": False, "error": "no response"}
    return json.loads(line)


class _Session:
    def __init__(self, proc, sock_name, tmpdir):
        self.proc = proc
        self.sock_name = sock_name
        self.tmpdir = tmpdir

    def call(self, op: str, **kw) -> dict:
        return _call(self.sock_name, {"op": op, **kw})

    def ok(self, op: str, **kw):
        r = self.call(op, **kw)
        assert r.get("ok"), f"{op} failed: {r}"
        return r.get("result")


@pytest.fixture(scope="module")
def bridge(qapp, tmp_path_factory):
    """The app subprocess with the bridge listening, shared by the module's
    tests (boot is the expensive part; each test drives distinct state)."""
    import getpass

    tmp = tmp_path_factory.mktemp("bridge")
    slug = f"dough-bridgetest-{uuid.uuid4().hex[:8]}"
    sock_name = f"{slug}-test-bridge-{getpass.getuser()}"

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        DOUGH_TEST_BRIDGE="1",
        # Auto-update channel ⇒ the deferred update check never touches the
        # network from a test subprocess.
        DOUGH_CHANNEL="aur",
        # Scratch config home so settings writes never land in the real
        # user config (Linux/macOS; on Windows the uuid slug isolates, and
        # the wind-down clears the store before quitting).
        XDG_CONFIG_HOME=str(tmp / "config"),
        PYTHONPATH=repo_root + os.pathsep + os.environ.get("PYTHONPATH", ""),
    )
    err_path = tmp / "stderr.txt"
    with open(err_path, "wb") as err:
        proc = subprocess.Popen(
            [sys.executable, "-c", _APP_SCRIPT, slug],
            env=env,
            cwd=repo_root,
            stderr=err,
        )
    # Wait for boot: the bridge starts after win.show(), so a successful ping
    # proves the whole run_app path came up with the flag on.
    deadline = time.monotonic() + 30
    last = None
    while time.monotonic() < deadline:
        last = _call(sock_name, {"op": "ping"})
        if last.get("ok"):
            break
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    if not (last or {}).get("ok"):
        proc.kill()
        pytest.fail(
            f"bridge never answered ping: {last}\n--- app stderr ---\n"
            + err_path.read_text(errors="replace")
        )
    sess = _Session(proc, sock_name, tmp)
    yield sess
    # Wind down: clear the scratch settings store, then quit over the bridge;
    # kill only if the polite path stalls.
    if proc.poll() is None:
        _call(sock_name, {"op": "exec", "code": "get_settings()._s.clear()"})
        _call(sock_name, {"op": "quit"})
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_ping(bridge):
    assert bridge.ok("ping") == "pong"


def test_windows_lists_main_window(bridge):
    wins = bridge.ok("windows")
    assert any(w["class"] == "AppWindow" for w in wins)


def test_tree_reads_content_widgets(bridge):
    tree = bridge.ok("tree")
    flat = json.dumps(tree)
    assert '"probeButton"' in flat
    assert '"probeInput"' in flat


def test_click_by_object_name_fires_handler(bridge):
    before = bridge.ok("eval", code="int(win.property('probe_clicks') or 0)")
    res = bridge.ok("click", object="probeButton")
    assert res["clicked"] == "probeButton"
    after = bridge.ok("eval", code="int(win.property('probe_clicks') or 0)")
    assert after == before + 1


def test_set_text_round_trips(bridge):
    bridge.ok("set_text", object="probeInput", text="hello bridge")
    # Read back through the tree (the agent's own path)…
    tree = bridge.ok("tree", object="probeInput", depth=0)
    assert tree["text"] == "hello bridge"
    # …and through eval, proving the escape hatch coexists with commands.
    from_eval = bridge.ok(
        "eval", code="[w.text() for w in app.allWidgets() if w.objectName()=='probeInput'][0]"
    )
    assert from_eval == "hello bridge"


def test_settings_get_set_round_trip(bridge):
    bridge.ok("set_setting", key="qa/probe", value=42)
    assert bridge.ok("get_setting", key="qa/probe") == 42


def test_theme_switch_applies(bridge):
    res = bridge.ok("theme", mode="dark")
    assert res["mode"] == "dark"
    assert bridge.ok("eval", code="settings.theme_mode") == "dark"


def test_screenshot_writes_png(bridge):
    path = str(bridge.tmpdir / "shot.png")
    res = bridge.ok("screenshot", path=path)
    assert os.path.exists(path) and os.path.getsize(path) > 0
    assert res["width"] > 0 and res["height"] > 0


def test_registered_custom_command_round_trips(bridge):
    res = bridge.ok("echo", value={"nested": [1, 2, 3]})
    assert res["echo"] == {"nested": [1, 2, 3]}
    assert res["win_title"] == "bridge probe"


def test_unknown_op_is_a_structured_error(bridge):
    r = bridge.call("play_music")
    assert r["ok"] is False
    assert "unknown op" in r["error"]


def test_socket_name_follows_identity(qapp):
    from dough import identity, test_bridge

    identity.configure(app="loafling")  # restored by the conftest identity fixture
    assert test_bridge.socket_name().startswith("loafling-test-bridge-")


def test_coerce_degrades_to_repr():
    from dough.test_bridge import _coerce

    class Opaque:
        def __repr__(self):
            return "<opaque>"

    assert _coerce({"a": Opaque(), "b": [1, Opaque()]}) == {
        "a": "<opaque>",
        "b": [1, "<opaque>"],
    }
