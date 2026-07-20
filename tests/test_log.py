"""dough.log — the opt-in rotating file log.

install() is process-global (root-logger handlers), so each test resets the
module's idempotency latch and detaches the handlers it added; the log dir is
monkeypatched to tmp_path so the suite never writes the real state dir.
"""

from __future__ import annotations

import logging

import pytest

from dough import log as dlog


@pytest.fixture(autouse=True)
def _fresh_install(tmp_path, monkeypatch):
    """Point the log dir at tmp_path and undo install()'s global effects."""
    monkeypatch.setattr(dlog, "log_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(dlog, "_installed", False)
    monkeypatch.setattr(dlog, "_file_path", None)
    root = logging.getLogger()
    before = list(root.handlers)
    before_level = root.level
    yield
    for h in root.handlers[:]:
        if h not in before:
            root.removeHandler(h)
            h.close()
    root.setLevel(before_level)


def test_install_creates_rotating_file_log(tmp_path):
    assert dlog.install() is True
    path = dlog.log_file_path()
    assert path is not None and path.parent == tmp_path / "logs"
    logging.getLogger("dough.test").info("hello from the suite")
    for h in logging.getLogger().handlers:
        h.flush()
    assert "hello from the suite" in path.read_text(encoding="utf-8")


def test_install_is_idempotent(tmp_path):
    root = logging.getLogger()
    n0 = len(root.handlers)
    dlog.install()
    n1 = len(root.handlers)
    dlog.install()  # second call must not stack handlers
    assert len(root.handlers) == n1
    assert n1 == n0 + 2  # console + file


def test_console_handler_stays_at_warning():
    dlog.install()
    consoles = [
        h
        for h in logging.getLogger().handlers
        if type(h) is logging.StreamHandler
    ]
    assert consoles and all(h.level == logging.WARNING for h in consoles)


def test_dough_log_env_sets_debug(monkeypatch):
    monkeypatch.setenv("DOUGH_LOG", "debug")
    dlog.install()
    assert logging.getLogger().level == logging.DEBUG


def test_unwritable_dir_degrades_without_raising(monkeypatch, tmp_path):
    def _boom():
        raise OSError("no state dir here")

    monkeypatch.setattr(dlog, "log_dir", _boom)
    assert dlog.install() is False
    assert dlog.log_file_path() is None


def test_rotation_caps_file_size(tmp_path, monkeypatch):
    monkeypatch.setattr(dlog, "_MAX_BYTES", 2_000)
    dlog.install()
    lg = logging.getLogger("dough.rotate")
    for i in range(200):
        lg.info("line %04d %s", i, "x" * 40)
    path = dlog.log_file_path()
    assert path.stat().st_size <= 2_100  # rolled over, never unbounded
    assert path.with_name(path.name + ".1").exists()
