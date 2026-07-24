"""Add or edit a tracked item — a small frosted form.

One dialog for both: ``ItemDialog(parent)`` adds a fresh item;
``ItemDialog(parent, item=…)`` edits an existing one (prefilled, with a Delete).
:meth:`prompt` runs it modally and returns ``(action, item)`` where action is
``"save"`` / ``"delete"`` / ``"cancel"`` — the dashboard acts on that.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from trackerkeeper import catalog, ui_helpers
from trackerkeeper.frosted_dialog import FrostedDialog
from trackerkeeper.selector import Selector, selector_qss

_KIND_LABELS = {
    "github": "GitHub releases  (owner/repo)",
    "arch": "Arch package  (package name)",
    "appstore": "App Store  (iOS / Mac — app id or bundle id)",
    "cachyos": "CachyOS ISO  (edition: desktop / kde / handheld / cli)",
    "manual": "Manual  (you set the version)",
}
_REF_HINT = {
    "github": "owner/repo  ·  e.g. ghostty-org/ghostty",
    "arch": "package name  ·  e.g. plasma-desktop",
    "appstore": "app id or bundle id  ·  e.g. 6449580241 or com.apple.FinalCutApp.companion",
    "cachyos": "edition  ·  desktop (default) · kde · handheld · cli",
    "manual": "",
}


class ItemDialog(FrostedDialog):
    def __init__(self, parent=None, *, item: catalog.Item | None = None,
                 existing_names: set[str] | None = None) -> None:
        editing = item is not None
        super().__init__(parent, title="Edit item" if editing else "Track something",
                         icon_name="", min_width=440)
        self.setStyleSheet(self.styleSheet() + selector_qss())
        self._item = item
        self._existing = existing_names or set()

        self._name = self._field("Name", item.name if editing else "")
        self._platform = self._field(
            "Platform / label", item.platform if editing else "",
            placeholder="Linux · Steam · iOS · Firmware …")

        self.content_layout.addWidget(self._label("Source"))
        self._kind = Selector()
        for kind in catalog.KINDS:
            self._kind.addItem(_KIND_LABELS[kind], kind)
        self._kind.setFixedWidth(300)
        self._select(self._kind, item.kind if editing else "github")
        self._kind.currentIndexChanged.connect(self._sync_ref_hint)
        self.content_layout.addWidget(self._kind)

        self._ref = self._field("Source handle", item.ref if editing else "")
        self._installed = self._field(
            "Installed / current version", item.installed if editing else "",
            placeholder="what you have now (optional for auto sources)")
        self._changelog = self._field(
            "Changelog URL", item.changelog_url if editing else "",
            placeholder="https://…  (optional)")

        self._err = QLabel("")
        self._err.setStyleSheet("color:#d0524a;font-size:12px;")
        self.content_layout.addWidget(self._err)

        row = QHBoxLayout()
        if editing:
            delete = QPushButton("Delete")
            delete.setStyleSheet(
                "QPushButton{border:1px solid rgba(208,82,74,0.5);border-radius:8px;"
                "padding:6px 14px;background:transparent;color:#d0524a;}"
                "QPushButton:hover{background:rgba(208,82,74,0.15);}")
            delete.clicked.connect(self._on_delete)
            row.addWidget(delete)
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        save = QPushButton("Save" if editing else "Track it")
        save.setDefault(True)
        save.clicked.connect(self._on_save)
        row.addWidget(save)
        self.content_layout.addLayout(row)

        self._action = "cancel"
        self._sync_ref_hint()
        self._name.setFocus()

    # ── builders ──
    def _label(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{ui_helpers.TEXT_DIM};font-size:12px;")
        return lab

    def _field(self, label: str, value: str, placeholder: str = "") -> QLineEdit:
        self.content_layout.addWidget(self._label(label))
        edit = QLineEdit(value)
        edit.setPlaceholderText(placeholder)
        edit.setStyleSheet(
            "QLineEdit{background:rgba(255,255,255,0.06);border:1px solid "
            "rgba(255,255,255,0.14);border-radius:7px;padding:6px 10px;color:#eee;}"
            f"QLineEdit:focus{{border-color:{ui_helpers.ACCENT};}}")
        self.content_layout.addWidget(edit)
        return edit

    @staticmethod
    def _select(sel: Selector, value: str) -> None:
        idx = sel.findData(value)
        sel.setCurrentIndex(idx if idx >= 0 else 0)

    def _sync_ref_hint(self, *_) -> None:
        kind = self._kind.currentData()
        self._ref.setPlaceholderText(_REF_HINT.get(kind, ""))
        self._ref.setEnabled(kind != "manual")

    # ── actions ──
    def _on_save(self) -> None:
        name = self._name.text().strip()
        if not name:
            self._err.setText("A name is required.")
            return
        if name.lower() in self._existing:
            self._err.setText("You're already tracking something by that name.")
            return
        kind = self._kind.currentData()
        ref = self._ref.text().strip()
        if kind == "github" and "/" not in ref:
            self._err.setText("GitHub source wants owner/repo (e.g. ghostty-org/ghostty).")
            return
        if kind == "arch" and not ref:
            self._err.setText("Arch source wants a package name (e.g. plasma-desktop).")
            return
        if kind == "appstore" and not ref:
            self._err.setText("App Store source wants an app id or bundle id.")
            return
        target = self._item or catalog.Item(name=name)
        target.name = name
        target.platform = self._platform.text().strip()
        target.kind = kind
        target.ref = "" if kind == "manual" else ref
        target.installed = self._installed.text().strip()
        target.changelog_url = self._changelog.text().strip()
        self._result = target
        self._action = "save"
        self.accept()

    def _on_delete(self) -> None:
        self._action = "delete"
        self.accept()

    def prompt(self) -> tuple[str, catalog.Item | None]:
        """Run modally → ``(action, item)``. On "save" the item is the new or
        edited Item; otherwise None."""
        if self.exec() != QDialog.DialogCode.Accepted:
            return ("cancel", None)
        if self._action == "delete":
            return ("delete", self._item)
        return ("save", getattr(self, "_result", None))
