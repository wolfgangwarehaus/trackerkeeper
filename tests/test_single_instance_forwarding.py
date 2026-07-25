"""Second-launch file forwarding over the single-instance socket.

A real round-trip: the "primary" acquires the lock + listener in-process; the
second launch runs as an actual SUBPROCESS (like production) that acquires the
same key, is refused, and forwards its argv — the primary's signals fire once
the event loop spins. A subprocess rather than an in-process fake because the
forwarding protocol is a blocking-client ↔ event-loop-server ACK handshake:
same-thread both-ends would deadlock the ACK by construction. Keys are
uuid-suffixed so parallel test runs can't collide.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest

from trackerkeeper.single_instance import SingleInstance, _normalize_args

_SECOND_LAUNCH = """
import sys
from PySide6.QtCore import QCoreApplication
app = QCoreApplication([])
from trackerkeeper.single_instance import SingleInstance
si = SingleInstance(sys.argv[1])
# acquire() must be REFUSED (the test process holds the lock); exit 0 then.
sys.exit(0 if not si.acquire(sys.argv[2:]) else 3)
"""


def _second_launch(key: str, args: list[str]) -> subprocess.Popen:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.Popen(
        [sys.executable, "-c", _SECOND_LAUNCH, key, *args],
        env=env,
        cwd=repo_root,
    )


def _reap_deferred_deletes(qapp) -> None:
    """Actually destroy everything handed to ``deleteLater()``.

    ``_on_new_connection`` defers every incoming QLocalSocket this way, so a test
    that ends without a real event-loop pass leaves live sockets queued for
    destruction. Reaping them explicitly — while their server is still alive — is
    the difference between a clean teardown and Qt destroying them later, in the
    wrong order, which aborts the whole pytest process with no traceback.
    """
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()


@pytest.fixture()
def primary(qapp):
    si = SingleInstance(f"si-fwd-{uuid.uuid4().hex[:8]}")
    assert si.acquire() is True

    yield si

    # Teardown order is load-bearing — see _reap_deferred_deletes. Drop the
    # tests' own connections first so a late-delivered signal can't re-enter a
    # lambda holding a list that's already gone out of scope.
    from PySide6.QtNetwork import QLocalServer

    for signal in (si.raise_requested, si.files_received):
        try:
            signal.disconnect()
        except (RuntimeError, TypeError):
            pass        # nothing was connected — Qt raises rather than no-op'ing
    if si._server is not None:
        si._server.close()
        _reap_deferred_deletes(qapp)     # sockets die while the server still exists
        si._server.deleteLater()
        si._server = None
    if si._mem is not None:
        si._mem.detach()
        si._mem = None
    # Unlink the stale socket file. Without this a crashed/killed run leaves one
    # behind and the NEXT listen() on that name inherits it.
    QLocalServer.removeServer(si._socket_name)
    _reap_deferred_deletes(qapp)


def _spin(qapp, cond=None, timeout_ms: int = 3000) -> None:
    """Run the REAL event loop until ``cond()`` holds (or the timeout).

    Not processEvents() spins: on Windows the server-side named-pipe reader
    completes via overlapped I/O that only delivers when the dispatcher
    actually blocks in an alertable wait — bare processEvents() loops never
    do, so the forwarded payload 'never arrives' there (seen on win CI)."""
    from PySide6.QtCore import QEventLoop, QTimer

    deadline = 0
    step = 50
    while deadline < timeout_ms:
        if cond is not None and cond():
            return
        loop = QEventLoop()
        QTimer.singleShot(step, loop.quit)
        loop.exec()
        deadline += step
        if cond is None:
            return  # one real-loop pass is the point when there's no condition


def test_second_launch_forwards_files_and_raises(qapp, primary, tmp_path):
    doc = tmp_path / "clicked.pdf"
    doc.write_text("pdf!")
    raised, received = [], []
    primary.raise_requested.connect(lambda: raised.append(True))
    primary.files_received.connect(lambda paths: received.append(paths))

    proc = _second_launch(primary._key, [str(doc)])
    _spin(qapp, lambda: received, timeout_ms=15000)
    assert proc.wait(timeout=15) == 0  # the second launch deferred + exited

    assert raised == [True]
    assert received == [[str(doc)]]


def test_second_launch_without_args_only_raises(qapp, primary):
    raised, received = [], []
    primary.raise_requested.connect(lambda: raised.append(True))
    primary.files_received.connect(lambda paths: received.append(paths))

    proc = _second_launch(primary._key, [])
    _spin(qapp, lambda: raised, timeout_ms=15000)
    assert proc.wait(timeout=15) == 0
    _spin(qapp)  # one extra settle pass — files_received must NOT trail in

    assert raised == [True]
    assert received == []  # no payload → no files_received, raise only


def test_legacy_bare_raise_ping_still_raises(qapp, primary):
    # A pre-forwarding build (or line noise) writes a non-JSON message; the
    # raise must never depend on the payload parsing.
    from PySide6.QtNetwork import QLocalSocket

    raised, received = [], []
    primary.raise_requested.connect(lambda: raised.append(True))
    primary.files_received.connect(lambda paths: received.append(paths))

    sock = QLocalSocket()
    sock.connectToServer(primary._socket_name)
    assert sock.waitForConnected(500)
    sock.write(b"raise")
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    _spin(qapp, lambda: raised, timeout_ms=1000)
    _spin(qapp)  # settle — a bare ping must never turn into files_received

    assert raised == [True]
    assert received == []


def test_urls_pass_through_forwarding(qapp, primary):
    received = []
    primary.files_received.connect(lambda paths: received.append(paths))

    proc = _second_launch(primary._key, ["https://example.com/doc.pdf"])
    _spin(qapp, lambda: received, timeout_ms=15000)
    assert proc.wait(timeout=15) == 0

    assert received == [["https://example.com/doc.pdf"]]


# ── argv normalization (the sending side) ─────────────────────────────


def test_normalize_resolves_relative_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "doc.pdf").write_text("x")
    assert _normalize_args(["doc.pdf"]) == [str(tmp_path / "doc.pdf")]


def test_normalize_keeps_urls_and_drops_options():
    args = ["--minimized", "-v", "https://example.com/x", "file:///tmp/a.pdf"]
    assert _normalize_args(args) == ["https://example.com/x", "file:///tmp/a.pdf"]


def test_normalize_empty_and_none():
    assert _normalize_args(None) == []
    assert _normalize_args([]) == []
