#!/usr/bin/env python3
"""One-shot CLI client for the dough test bridge (see dough/test_bridge.py).

The bridge only listens when the app was launched with DOUGH_TEST_BRIDGE=1.
This client connects to that per-user local socket, sends one JSON request,
prints the JSON response, and exits non-zero if the call errored.

Usage:
    python dev/ctl.py ping
    python dev/ctl.py windows
    python dev/ctl.py tree depth=3
    python dev/ctl.py click object=settingsButton
    python dev/ctl.py set_text object=searchInput text="hello"
    python dev/ctl.py screenshot path=/tmp/shot.png
    python dev/ctl.py theme mode=frosted_light
    python dev/ctl.py eval "win.windowTitle()"
    python dev/ctl.py exec "bus.show_settings.emit()"

Arguments after the op are ``key=value`` pairs; values parse as JSON where
they can (``depth=3`` is an int, ``value=true`` a bool) and fall back to the
raw string. ``eval`` / ``exec`` instead take the code as one positional arg.

Uses QLocalSocket (not raw sockets) so it resolves the socket name the same
way QLocalServer does on this platform. On Linux/macOS the socket lives under
$TMPDIR — run this client with the SAME TMPDIR as the app (the QA harness
convention is TMPDIR=/tmp on both sides), or it will resolve a different path
and report "connect failed".
"""

import json

# Allow running from anywhere: ensure the repo root is importable.
import os
import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalSocket

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dough.test_bridge import socket_name  # noqa: E402

_CONNECT_MS = 3000
_IO_MS = 10000


def call(payload: dict) -> dict:
    QCoreApplication(sys.argv)
    sock = QLocalSocket()
    sock.connectToServer(socket_name())
    if not sock.waitForConnected(_CONNECT_MS):
        return {
            "ok": False,
            "error": f"connect failed ({sock.errorString()}) — is the app running "
            f"with DOUGH_TEST_BRIDGE=1 (and the same TMPDIR)?",
        }
    sock.write((json.dumps(payload) + "\n").encode())
    sock.flush()
    # Drain COMPLETELY before waiting on the reply — on Windows a single
    # waitForBytesWritten can return with bytes still queued on the pipe
    # (the single-instance forwarding lesson).
    while sock.bytesToWrite() > 0:
        if not sock.waitForBytesWritten(_IO_MS):
            break
    buf = bytearray()
    while b"\n" not in buf:
        if not sock.waitForReadyRead(_IO_MS):
            break
        buf += bytes(sock.readAll())
    sock.disconnectFromServer()
    line = bytes(buf).split(b"\n", 1)[0].decode(errors="replace")
    if not line:
        return {"ok": False, "error": "no response from bridge"}
    try:
        return json.loads(line)
    except Exception as e:
        return {"ok": False, "error": f"unparseable response: {e!r}: {line!r}"}


def _parse_value(raw: str):
    try:
        return json.loads(raw)
    except Exception:
        return raw


def build_payload(argv: list) -> dict:
    op = argv[0]
    if op in ("eval", "exec"):
        return {"op": op, "code": argv[1] if len(argv) > 1 else ""}
    payload = {"op": op}
    for pair in argv[1:]:
        key, sep, val = pair.partition("=")
        if not sep:
            raise SystemExit(f"expected key=value, got {pair!r}")
        payload[key] = _parse_value(val)
    return payload


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 2
    resp = call(build_payload(sys.argv[1:]))
    print(json.dumps(resp, indent=2))
    return 0 if resp.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
