"""The dashboard — your fleet at a glance, sorted by what's new.

One scrollable column of cards, newest-update-first. Each card shows what you
have vs what the source found, a changelog link, and one-tap "mark updated".
Refresh checks every auto source (github/arch) off the UI thread and fires a
desktop notification for anything genuinely new. Manual items hold what you
enter until a checker for their world exists.

The rule Tracker Keeper lives by: a card only ever shows a version a real
source returned. A refresh that can't reach a source leaves the last-known
value and says "couldn't check" — it never invents a "latest".
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from trackerkeeper import catalog, ui_helpers
from trackerkeeper.bus import AppBus
from trackerkeeper.design_tokens import TYPE_BODY, TYPE_DISPLAY, type_qss

_ACCENT = ui_helpers.ACCENT
_NEW = "#56c48d"
# `.QFrame` (leading dot) matches the card's EXACT type only — a bare `QFrame`
# selector cascades into child QLabels (QLabel subclasses QFrame), boxing every
# line of text. Ask me how I know.
_CARD = (".QFrame{background:rgba(255,255,255,0.045);border:1px solid "
         "rgba(255,255,255,0.10);border-radius:12px;}")
_CARD_NEW = (".QFrame{background:rgba(86,196,141,0.08);border:1px solid "
             "rgba(86,196,141,0.40);border-radius:12px;}")


class _RefreshWorker(QThread):
    """Checks every auto item off the UI thread. Emits ``{name: CheckResult}``
    for the ones that answered (missing name = couldn't check / manual)."""

    done = Signal(object)

    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self._snapshot = snapshot  # list of Item (copies safe to read off-thread)

    def run(self) -> None:  # noqa: N802 (Qt override)
        from trackerkeeper import sources

        out = {}
        for item in self._snapshot:
            if item.kind == "manual":
                continue
            res = sources.check(item)
            if res is not None:
                out[item.name] = res
        self.done.emit(out)


class Dashboard(QWidget):
    def __init__(self, window=None) -> None:
        super().__init__()
        self._window = window
        self._items = catalog.load()
        self._worker: _RefreshWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 18)
        root.setSpacing(12)

        # ── header: title + update count + actions ──
        header = QHBoxLayout()
        header.setSpacing(10)
        self._title = QLabel("Tracker Keeper")
        self._title.setStyleSheet(type_qss(TYPE_DISPLAY) + f"color:{ui_helpers.TEXT};")
        header.addWidget(self._title)
        self._count = QLabel("")
        self._count.setStyleSheet(f"color:{_NEW};font-weight:600;")
        header.addWidget(self._count)
        header.addStretch(1)
        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{ui_helpers.TEXT_DIM};font-size:12px;")
        header.addWidget(self._status)
        self._add_btn = self._chip_button("Add…", self._add_item)
        header.addWidget(self._add_btn)
        self._refresh_btn = self._chip_button("Check for updates", self._refresh)
        header.addWidget(self._refresh_btn)
        root.addLayout(header)

        # ── the fleet ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_host = QWidget()
        self._list = QVBoxLayout(self._list_host)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(9)
        scroll.setWidget(self._list_host)
        root.addWidget(scroll, 1)

        self._render()

        # Auto-check shortly after launch — the "what's new today" reflex. Only
        # on a real display: never under offscreen (the CI boot smoke, rig, and
        # the test suite), so a headless run never reaches the network.
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None and app.platformName() != "offscreen":
            from PySide6.QtCore import QTimer

            QTimer.singleShot(1500, self._refresh)

    # ── styling helpers ──
    def _chip_button(self, text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            "QPushButton{border:1px solid rgba(255,255,255,0.2);border-radius:9px;"
            "padding:6px 14px;background:transparent;color:#ddd;}"
            f"QPushButton:hover{{border-color:{_ACCENT};color:#fff;}}"
            "QPushButton:disabled{color:#666;border-color:rgba(255,255,255,0.08);}")
        b.clicked.connect(slot)
        return b

    # ── render ──
    def _render(self) -> None:
        while self._list.count():
            it = self._list.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for item in sorted(self._items, key=lambda i: i.sort_key()):
            self._list.addWidget(self._card(item))
        self._list.addStretch(1)
        n = sum(1 for i in self._items if i.has_update())
        self._count.setText(f"· {n} update{'s' if n != 1 else ''} available" if n else "· all current")

    def _card(self, item: catalog.Item) -> QWidget:
        card = QFrame()
        card.setStyleSheet(_CARD_NEW if item.has_update() else _CARD)
        outer = QHBoxLayout(card)
        outer.setContentsMargins(14, 11, 14, 11)
        outer.setSpacing(12)

        # left: name + platform + versions
        left = QVBoxLayout()
        left.setSpacing(3)
        topline = QLabel(
            (f'<span style="color:{_NEW};">●</span> ' if item.has_update() else "")
            + f'<b style="color:{ui_helpers.TEXT};">{_esc(item.name)}</b>'
            + (f'  <span style="color:{ui_helpers.TEXT_DIM};font-size:11px;">'
               f'{_esc(item.platform)}</span>' if item.platform else ""))
        topline.setTextFormat(Qt.TextFormat.RichText)
        left.addWidget(topline)
        left.addWidget(self._version_line(item))
        if item.error:
            err = QLabel("couldn't check — showing last known")
            err.setStyleSheet("color:#c98a2b;font-size:11px;")
            left.addWidget(err)
        outer.addLayout(left, 1)

        # right: changelog + actions
        if item.changelog_url or item.latest_url:
            link = QLabel(f'<a href="{item.latest_url or item.changelog_url}" '
                          f'style="color:{_ACCENT};text-decoration:none;">changelog →</a>')
            link.setTextFormat(Qt.TextFormat.RichText)
            link.setOpenExternalLinks(True)
            link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            outer.addWidget(link)
        if item.has_update():
            mark = self._mini("mark updated", lambda: self._mark_updated(item))
            outer.addWidget(mark)
        outer.addWidget(self._mini("⋯", lambda: self._edit_item(item)))
        return card

    def _version_line(self, item: catalog.Item) -> QLabel:
        inst = item.installed or "—"
        if item.has_update():
            body = (f'<span style="color:{ui_helpers.TEXT_DIM};">{_esc(inst)}</span>'
                    f'  <span style="color:{ui_helpers.TEXT_DIM};">→</span>  '
                    f'<b style="color:{_NEW};">{_esc(item.latest)}</b>')
        elif item.latest:
            body = f'<span style="color:{ui_helpers.TEXT_DIM};">{_esc(item.latest)} · current</span>'
        else:
            body = f'<span style="color:{ui_helpers.TEXT_DIM};">{_esc(inst)}</span>'
        if item.latest_date:
            body += f'  <span style="color:#777;font-size:11px;">{item.latest_date}</span>'
        lab = QLabel(body)
        lab.setTextFormat(Qt.TextFormat.RichText)
        lab.setStyleSheet(type_qss(TYPE_BODY))
        return lab

    def _mini(self, text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            "QPushButton{border:none;border-radius:7px;padding:5px 10px;"
            "background:rgba(255,255,255,0.06);color:#bbb;font-size:12px;}"
            f"QPushButton:hover{{background:{_ACCENT};color:#fff;}}")
        b.clicked.connect(slot)
        return b

    # ── refresh (off-thread) ──
    def _refresh(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._refresh_btn.setEnabled(False)
        self._status.setText("checking…")
        import copy

        self._worker = _RefreshWorker([copy.copy(i) for i in self._items], self)
        self._worker.done.connect(self._on_results)
        self._worker.start()

    def _on_results(self, results: dict) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        newly = []
        auto = [i for i in self._items if i.kind != "manual"]
        for item in auto:
            res = results.get(item.name)
            if res is None:
                item.error = "unreachable"
                continue
            was_update_to = item.latest if item.has_update() else ""
            item.latest, item.latest_url, item.latest_date = res.latest, res.url, res.date
            item.checked_at, item.error = now, ""
            # "newly new": it now has an update we hadn't already surfaced
            if item.has_update() and item.latest != was_update_to:
                newly.append(item)
        catalog.save(self._items)
        self._render()
        self._refresh_btn.setEnabled(True)
        checked = sum(1 for i in auto if not i.error)
        self._status.setText(f"checked {checked}/{len(auto)} · {now.split(' ')[1]}")
        if newly:
            names = ", ".join(i.name for i in newly[:4])
            more = f" +{len(newly) - 4} more" if len(newly) > 4 else ""
            AppBus.get().notify.emit(
                f"{len(newly)} new update{'s' if len(newly) != 1 else ''}",
                f"{names}{more}")

    # ── mutations ──
    def _mark_updated(self, item: catalog.Item) -> None:
        item.installed = item.latest
        catalog.save(self._items)
        self._render()

    def _remove(self, item: catalog.Item) -> None:
        self._items = [i for i in self._items if i is not item]
        catalog.save(self._items)
        self._render()

    def _add_item(self) -> None:
        from trackerkeeper.item_dialog import ItemDialog

        taken = {i.name.lower() for i in self._items}
        action, result = ItemDialog(self._window or self, existing_names=taken).prompt()
        if action == "save" and result is not None:
            self._items.append(result)
            catalog.save(self._items)
            self._render()

    def _edit_item(self, item: catalog.Item) -> None:
        from trackerkeeper.item_dialog import ItemDialog

        taken = {i.name.lower() for i in self._items if i is not item}
        action, _ = ItemDialog(self._window or self, item=item,
                               existing_names=taken).prompt()
        if action == "delete":
            self._remove(item)
        elif action == "save":
            catalog.save(self._items)  # item mutated in place
            self._render()


def _esc(s: str) -> str:
    import html

    return html.escape(s or "")


def build_content(window) -> QWidget:
    """The run_app content factory: Tracker Keeper's dashboard."""
    return Dashboard(window)
