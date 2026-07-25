"""One tracked item, in full — what changed, when, and where to read more.

The dashboard card is a scanning surface: name, versions, age, a link. This is
the other half — the release notes the checkers already fetch and the list has
no room for. Opened by clicking a card.

**Notes render as PLAIN TEXT, never rich text.** The body is written by a third
party (a GitHub release, a Steam announcement, a stranger's RSS feed), and
handing that to a Qt rich-text widget would let it pull remote images — a
tracking pixel by any other name — and take control of the markup. ``sources.
plain_notes()`` flattens every dialect on the way in; the "changelog →" link
stays for the fully formatted original.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
)

from trackerkeeper import catalog, ui_helpers
from trackerkeeper.design_tokens import TYPE_CAPTION, TYPE_TINY, type_qss
from trackerkeeper.frosted_dialog import FrostedDialog

_NEW = "#56c48d"


class DetailDialog(FrostedDialog):
    """The full read on one item. Returns ``"marked"`` from :meth:`prompt` when
    the user marked it updated, else ``"close"``."""

    def __init__(self, parent=None, *, item: catalog.Item) -> None:
        super().__init__(parent, title=item.name, icon_name="", min_width=460)
        self._item = item
        self._marked = False

        from trackerkeeper.dashboard import channel_label, error_text, humanize_age

        # ── the headline: what you have vs what's out there ──
        if item.has_update():
            head = (f'<span style="color:{ui_helpers.TEXT_DIM};">'
                    f'{_esc(item.installed or "—")}</span>'
                    f'  <span style="color:{ui_helpers.TEXT_DIM};">→</span>  '
                    f'<b style="color:{_NEW};">{_esc(item.latest)}</b>')
        elif item.latest:
            head = (f'<span style="color:{ui_helpers.TEXT};">{_esc(item.latest)}</span>'
                    f'  <span style="color:{ui_helpers.TEXT_DIM};">· current</span>')
        else:
            head = (f'<span style="color:{ui_helpers.TEXT};">'
                    f'{_esc(item.installed or "—")}</span>')
        self.content_layout.addWidget(self._rich(head, TYPE_CAPTION))

        # ── the provenance line: which source said so, and when ──
        bits = [channel_label(item)]
        # …but not "Steam · Steam": the platform tag is freeform, and for several
        # sources the obvious label is exactly the channel's name.
        if item.platform and item.platform.strip().lower() != bits[0].lower():
            bits.append(item.platform)
        age = humanize_age(item.latest_at or item.latest_date)
        if age:
            bits.append(age)
        if item.checked_at:
            bits.append(f"checked {item.checked_at}")
        self.content_layout.addWidget(
            self._dim("  ·  ".join(bits)))

        if item.error:
            self.content_layout.addWidget(self._warn(error_text(item.error)))

        # ── what changed ──
        self.content_layout.addWidget(self._dim("WHAT CHANGED"))
        body = QPlainTextEdit()
        body.setReadOnly(True)
        body.setPlainText(item.latest_notes or self._no_notes_reason())
        body.setMinimumHeight(150)
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body.setStyleSheet(
            "QPlainTextEdit{background:rgba(255,255,255,0.05);border:1px solid "
            "rgba(255,255,255,0.12);border-radius:8px;padding:8px;"
            f"color:{ui_helpers.TEXT};}}" + type_qss(TYPE_TINY))
        ui_helpers.install_autofade_scrollbars(body)
        self.content_layout.addWidget(body, 1)

        # ── actions ──
        row = QHBoxLayout()
        url = item.latest_url or item.changelog_url
        if url:
            link = QLabel(f'<a href="{_esc(url)}" style="color:{ui_helpers.ACCENT};'
                          f'text-decoration:none;">changelog →</a>')
            link.setTextFormat(Qt.TextFormat.RichText)
            link.setOpenExternalLinks(True)
            link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            row.addWidget(link)
        row.addStretch(1)
        if item.has_update():
            mark = QPushButton("Mark updated")
            mark.setCursor(Qt.CursorShape.PointingHandCursor)
            mark.clicked.connect(self._on_mark)
            row.addWidget(mark)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.reject)
        row.addWidget(close)
        self.content_layout.addLayout(row)

    def _no_notes_reason(self) -> str:
        """Never a blank box: say WHY there's nothing, because "no notes" and
        "this source can't carry notes" are different facts."""
        if self._item.kind in ("arch", "cachyos"):
            return ("This source publishes versions, not release notes — it's a "
                    "package index / ISO mirror, so there's nothing to quote.\n\n"
                    "The changelog link goes to where the notes actually live.")
        if not self._item.latest:
            return "Nothing checked yet — hit Check for updates."
        return ("The source didn't include release notes for this version.\n\n"
                "The changelog link still goes to its page.")

    def _on_mark(self) -> None:
        self._item.installed = self._item.latest
        self._marked = True
        self.accept()

    # ── small builders ──
    def _rich(self, html_text: str, token) -> QLabel:
        lab = QLabel(html_text)
        lab.setTextFormat(Qt.TextFormat.RichText)
        lab.setWordWrap(True)
        lab.setStyleSheet(type_qss(token))
        return lab

    def _dim(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setStyleSheet(f"color:{ui_helpers.TEXT_DIM};" + type_qss(TYPE_TINY))
        return lab

    def _warn(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setStyleSheet("color:#c98a2b;" + type_qss(TYPE_TINY))
        return lab

    def prompt(self) -> str:
        self.exec()
        return "marked" if self._marked else "close"


def _esc(s: str) -> str:
    import html

    return html.escape(s or "")
