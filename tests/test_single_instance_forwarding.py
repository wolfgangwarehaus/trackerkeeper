"""Second-launch file forwarding over the single-instance socket.

A real socket round-trip: the "primary" acquires the lock + listener in-process,
a fake "second launch" (another SingleInstance on the same key) acquires and is
refused — forwarding its argv — and the primary's signals fire once the event
loop spins. Keys are uuid-suffixed so parallel test runs can't collide.
"""

from __future__ import annotations

import uuid

import pytest

from dough.single_instance import SingleInstance, _normalize_args


@pytest.fixture()
def primary(qapp):
    si = SingleInstance(f"si-fwd-{uuid.uuid4().hex[:8]}")
    assert si.acquire() is True
    yield si
    if si._server is not None:
        si._server.close()
    if si._mem is not None:
        si._mem.detach()


def _spin(qapp, times: int = 20) -> None:
    for _ in range(times):
        qapp.processEvents()


def test_second_launch_forwards_files_and_raises(qapp, primary, tmp_path):
    doc = tmp_path / "clicked.pdf"
    doc.write_text("pdf!")
    raised, received = [], []
    primary.raise_requested.connect(lambda: raised.append(True))
    primary.files_received.connect(lambda paths: received.append(paths))

    second = SingleInstance(primary._key)
    assert second.acquire([str(doc)]) is False  # deferred to the primary
    _spin(qapp)

    assert raised == [True]
    assert received == [[str(doc)]]


def test_second_launch_without_args_only_raises(qapp, primary):
    raised, received = [], []
    primary.raise_requested.connect(lambda: raised.append(True))
    primary.files_received.connect(lambda paths: received.append(paths))

    second = SingleInstance(primary._key)
    assert second.acquire() is False
    _spin(qapp)

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
    _spin(qapp)

    assert raised == [True]
    assert received == []


def test_urls_pass_through_forwarding(qapp, primary):
    received = []
    primary.files_received.connect(lambda paths: received.append(paths))

    second = SingleInstance(primary._key)
    assert second.acquire(["https://example.com/doc.pdf"]) is False
    _spin(qapp)

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
