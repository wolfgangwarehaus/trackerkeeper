"""Plural (numerus) forms — the end-to-end contract.

The idiom: ``self.tr("%n file(s)", "", n)`` on a QObject subclass. That exact
shape is load-bearing twice over (verified against pyside6 6.x, 2026-07):

* **Extraction** — pyside6-lupdate's Python parser emits ``<message
  numerus="yes">`` ONLY for ``self.tr(source, disambiguation, n)``. The
  free-function ``QCoreApplication.translate(ctx, source, disamb, n)`` is
  extracted WITHOUT numerus (a plain message), so plural-bearing strings must
  live on a QObject — that's why ``dough.i18n.fmt`` routes its unit strings
  through the ``_DurationUnits`` QObject rather than module-level translate.
* **Runtime** — ``QTranslator`` resolves the right ``<numerusform>`` from the
  CLDR plural rules of the catalog's language, and substitutes ``%n``;
  untranslated strings fall through to the English source with ``%n``
  replaced.

These tests build a tiny Spanish catalog (two plural classes), compile it
with pyside6-lrelease, and assert n=1 vs n=5 render differently — both for a
raw tr() call and through fmt_duration's translated units.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QObject, QTranslator

_TS = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="es">
<context>
    <name>_PluralProbe</name>
    <message numerus="yes">
        <source>%n file(s)</source>
        <translation>
            <numerusform>%n archivo</numerusform>
            <numerusform>%n archivos</numerusform>
        </translation>
    </message>
</context>
<context>
    <name>_DurationUnits</name>
    <message numerus="yes">
        <source>%n h</source>
        <comment>duration: hours, abbreviated</comment>
        <translation>
            <numerusform>%n hora</numerusform>
            <numerusform>%n horas</numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <source>%n min</source>
        <comment>duration: minutes, abbreviated</comment>
        <translation>
            <numerusform>%n minuto</numerusform>
            <numerusform>%n minutos</numerusform>
        </translation>
    </message>
</context>
</TS>
"""


def _lrelease() -> str | None:
    """The pyside6-lrelease next to the running interpreter (the venv), else
    whatever PATH has — mirrors dev/update_translations.sh's resolution."""
    candidate = Path(sys.executable).with_name("pyside6-lrelease")
    if candidate.exists():
        return str(candidate)
    return shutil.which("pyside6-lrelease")


class _PluralProbe(QObject):
    """Context class for the demo string — the documented plural idiom."""

    def files_label(self, n: int) -> str:
        return self.tr("%n file(s)", "", n)


@pytest.fixture()
def spanish_catalog(qapp, tmp_path):
    """Compile the test .ts and install it on the app; uninstall after so the
    session-scoped qapp never leaks Spanish into other tests."""
    lrelease = _lrelease()
    if lrelease is None:
        pytest.skip("pyside6-lrelease not available")
    ts = tmp_path / "probe_es.ts"
    qm = tmp_path / "probe_es.qm"
    ts.write_text(_TS, encoding="utf-8")
    subprocess.run(
        [lrelease, str(ts), "-qm", str(qm)], check=True, capture_output=True
    )
    tr = QTranslator()
    assert tr.load(str(qm)), "compiled catalog failed to load"
    assert QCoreApplication.installTranslator(tr)
    yield tr
    QCoreApplication.removeTranslator(tr)


class TestNumerusRuntime:
    def test_untranslated_falls_through_with_n(self, qapp):
        probe = _PluralProbe()
        assert probe.files_label(1) == "1 file(s)"
        assert probe.files_label(5) == "5 file(s)"

    def test_singular_vs_plural_resolve(self, qapp, spanish_catalog):
        probe = _PluralProbe()
        assert probe.files_label(1) == "1 archivo"
        assert probe.files_label(5) == "5 archivos"

    def test_translate_resolves_numerus_at_runtime(self, qapp, spanish_catalog):
        # Runtime numerus works through plain translate() too — it's only
        # lupdate EXTRACTION that requires the self.tr idiom.
        got = QCoreApplication.translate("_PluralProbe", "%n file(s)", "", 5)
        assert got == "5 archivos"

    def test_fmt_duration_units_translate(self, qapp, spanish_catalog):
        from dough.i18n.fmt import fmt_duration

        assert fmt_duration(3600 + 23 * 60) == "1 hora 23 minutos"
        assert fmt_duration(2 * 3600) == "2 horas"
