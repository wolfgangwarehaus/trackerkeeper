"""trackerkeeper.diagnostics — the support report: complete, bounded, secret-free."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from trackerkeeper import diagnostics


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    import trackerkeeper.settings as smod

    s = smod.Settings.__new__(smod.Settings)
    s._s = QSettings(str(tmp_path / "store.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(smod, "_inst", s)
    return s


def test_report_carries_identity_and_versions(qapp, isolated_settings):
    from trackerkeeper import __version__, identity

    report = diagnostics.collect_report()
    assert identity.app() in report
    assert __version__ in report
    assert "qt:" in report and "PySide6" in report
    assert "session:" in report
    assert "blur:" in report


def test_report_reflects_settings_values(qapp, isolated_settings):
    isolated_settings.theme_mode = "frosted_light"
    report = diagnostics.collect_report()
    assert "mode=frosted_light" in report
    assert "ui/theme_mode = frosted_light" in report


def test_report_never_contains_secrets(qapp, isolated_settings):
    qs = isolated_settings._s
    qs.setValue("credentials/api_token", "v1:SUPERSECRETBLOB")
    qs.setValue("server/token", "plain-old-leak")
    qs.setValue("scrobble/password", "hunter2")
    qs.setValue("ui/theme_mode", "dark")
    report = diagnostics.collect_report()
    assert "SUPERSECRETBLOB" not in report
    assert "plain-old-leak" not in report
    assert "hunter2" not in report
    # No settings LINE from the credentials/ subtree (the section header
    # legitimately mentions the word).
    settings_section = report.split("---")[1]
    assert "credentials/api_token" not in settings_section
    assert "ui/theme_mode = dark" in report  # normal keys still present


def test_report_binary_values_summarized(qapp, isolated_settings):
    from PySide6.QtCore import QByteArray

    isolated_settings._s.setValue("win/geometry", QByteArray(b"\x01\x02\x03\x04"))
    report = diagnostics.collect_report()
    assert "win/geometry = <binary 4B>" in report


def test_report_tails_the_log_when_installed(qapp, isolated_settings, tmp_path, monkeypatch):
    from trackerkeeper import log as dlog

    logf = tmp_path / "trackerkeeper.log"
    lines = [f"line {i}" for i in range(150)]
    logf.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(dlog, "_file_path", logf)
    report = diagnostics.collect_report()
    assert "  line 149\n" in report  # the newest line survives
    assert "  line 10\n" not in report  # …the oldest of 150 is beyond the ~100 tail


def test_report_explains_missing_log(qapp, isolated_settings, monkeypatch):
    from trackerkeeper import log as dlog

    monkeypatch.setattr(dlog, "_file_path", None)
    report = diagnostics.collect_report()
    assert "file logging not installed" in report


def test_copy_to_clipboard(qapp, isolated_settings):
    assert diagnostics.copy_to_clipboard() is True
    from PySide6.QtWidgets import QApplication

    assert "diagnostics" in QApplication.clipboard().text()


def test_settings_dialog_button_copies(qapp, isolated_settings):
    from trackerkeeper.settings_dialog import SettingsDialog

    dlg = SettingsDialog()
    try:
        dlg.diagnostics_btn.click()
        from PySide6.QtWidgets import QApplication

        assert "diagnostics" in QApplication.clipboard().text()
        assert dlg._restart_note.text() != ""
    finally:
        dlg.close()
