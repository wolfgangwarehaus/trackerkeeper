"""i18n — language resolution + the empty-catalog contract.

Covers the boot-time layer only: which language ``trackerkeeper.i18n`` resolves
(Settings override → system locale → English fallback) and that install()
degrades cleanly while no catalog ships (bare trackerkeeper's SHIPPED_LANGUAGES is
empty). Catalog-loading itself is exercised in a fork the moment it ships one
— the loader is a verbatim lift of jellytoast's, which has a shipped-catalog
test against its Spanish .qm.
"""

import pytest

from trackerkeeper import i18n
from trackerkeeper.settings import get_settings


@pytest.fixture()
def _lang_settings(qapp):
    s = get_settings()
    saved = s.language
    yield s
    s.language = saved


class TestResolvedLanguage:
    def test_override_wins(self, _lang_settings):
        _lang_settings.language = "es"
        assert i18n.resolved_language() == "es"

    def test_explicit_english_means_source(self, _lang_settings):
        # "en" is the source language — no catalog, so it resolves to ""
        # (nothing to install) even though it was an explicit pick.
        _lang_settings.language = "en"
        assert i18n.resolved_language() == ""

    def test_override_normalized(self, _lang_settings):
        _lang_settings.language = "  ES "
        assert i18n.resolved_language() == "es"

    def test_empty_falls_to_system(self, _lang_settings, monkeypatch):
        _lang_settings.language = ""
        # Pin the system locale so the assert doesn't depend on the host.
        from PySide6.QtCore import QLocale

        monkeypatch.setattr(QLocale, "uiLanguages", lambda self: ["de-DE", "en-US"])
        assert i18n.resolved_language() == "de"


class TestInstall:
    def test_no_shipped_catalog_stays_english(self, qapp, _lang_settings):
        # Bare trackerkeeper ships no catalogs — an explicit pick degrades to English
        # (returns "") and installs nothing.
        _lang_settings.language = "es"
        assert i18n.install(qapp) == ""
        assert i18n._translators == []

    def test_english_installs_nothing(self, qapp, _lang_settings):
        _lang_settings.language = "en"
        assert i18n.install(qapp) == ""
        assert i18n._translators == []
