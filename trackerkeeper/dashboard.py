"""The dashboard — your fleet at a glance, sorted by what's new.

One scrollable column of cards, newest-update-first. Each card shows what you
have vs what the source found, a changelog link, and one-tap "mark updated".
Refresh checks every auto source (github/arch) off the UI thread and fires a
desktop notification for anything genuinely new. Manual items hold what you
enter until a checker for their world exists.

The rule tracker keeper lives by: a card only ever shows a version a real
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

# the release channel a kind maps to — the column + a sort axis
_CHANNEL = {"github": "GitHub", "arch": "Arch", "appstore": "App Store",
            "cachyos": "CachyOS", "appledev": "Apple", "steam": "Steam",
            "manual": "Manual"}

# tracker keeper is a UTILITY window first — it lives in the tray and gets
# opened in a corner, so it has to stay readable narrow. These are the sizes
# the layout is designed against, not arbitrary minimums.
DEFAULT_SIZE = (480, 620)   # a tall, slim fleet list
MIN_SIZE = (300, 320)       # still usable: name, version, age

TIER_NARROW, TIER_MEDIUM, TIER_WIDE = "narrow", "medium", "wide"


def width_tier(width: int) -> str:
    """Which layout density fits ``width``. Columns drop off as it tightens:
    wide keeps the channel column, medium keeps only "how long ago", narrow
    also shortens the labels and margins."""
    if width < 420:
        return TIER_NARROW
    if width < 620:
        return TIER_MEDIUM
    return TIER_WIDE


def channel_label(item: catalog.Item) -> str:
    """The human name of the source an item updates through (its channel)."""
    return _CHANNEL.get(item.kind, item.kind or "—")


def _parse_iso(iso: str):
    """An ISO date or timestamp → an aware datetime (UTC assumed when the string
    carries no offset), or None if unparseable."""
    from datetime import datetime, timezone

    s = iso.strip().replace("Z", "+00:00")
    for candidate in (s, s[:10]):  # full form, then fall back to the date
        try:
            dt = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _bucket_days(days: int) -> str:
    if days < 7:
        return f"{days} days ago"
    if days < 30:
        w = days // 7
        return f"{w} week{'s' if w != 1 else ''} ago"
    if days < 365:
        m = days // 30
        return f"{m} month{'s' if m != 1 else ''} ago"
    y = days // 365
    return f"{y} year{'s' if y != 1 else ''} ago"


def humanize_age(iso: str, now=None) -> str:
    """A compact "how long ago" for an ISO date or full timestamp. Day-only
    inputs read by the calendar (today / yesterday / N days ago); a full
    timestamp gets hour + minute precision ("6 hours ago", "just now"). "" → ""."""
    iso = (iso or "").strip()
    if not iso:
        return ""
    from datetime import datetime, timezone

    now = now or datetime.now(timezone.utc)
    then = _parse_iso(iso)
    if then is None:
        return ""
    if "T" not in iso:  # day precision only — count whole calendar days
        days = (now.date() - then.date()).days
        if days <= 0:
            return "today"
        if days == 1:
            return "yesterday"
        return _bucket_days(days)
    sec = max(0, (now - then).total_seconds())
    if sec < 60:
        return "just now"
    if sec < 3600:
        m = int(sec // 60)
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if sec < 86400:
        h = int(sec // 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    days = int(sec // 86400)
    return "yesterday" if days == 1 else _bucket_days(days)


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
        self._sort_key = "updated"   # "updated" (by release recency) | "channel"
        self._sort_desc = True       # newest / Z→A first
        self._grouped = any(i.group for i in self._items)  # section by category
        self._tier = TIER_WIDE   # re-derived from the real width in resizeEvent
        self._tray = None

        # Utility sizing: a slim default and a genuinely small floor. The
        # window only takes the default when there's no saved geometry (run_app
        # stamps _geometry_restored) — a size you chose is never overridden.
        if window is not None:
            window.setMinimumSize(*MIN_SIZE)
            if not getattr(window, "_geometry_restored", False):
                window.resize(*DEFAULT_SIZE)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 10)
        root.setSpacing(8)
        self._root = root

        # ── header controls: the update-count badge, a check status, and the
        # Add / Check actions. Built once, then folded onto the window's top-bar
        # line when we have one (the dough-matched single top row); otherwise
        # they render as their own inline header row (tests, standalone). ──
        self._title = QLabel("tracker keeper")
        self._title.setStyleSheet(type_qss(TYPE_DISPLAY) + f"color:{ui_helpers.TEXT};")
        self._count = QLabel("")
        self._count.setStyleSheet(f"color:{_NEW};font-weight:600;")
        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{ui_helpers.TEXT_DIM};font-size:12px;")
        self._add_btn = self._chip_button("Add…", self._add_item)
        self._refresh_btn = self._chip_button("Check for updates", self._refresh)

        top_bar = getattr(self._window, "top_bar", None)
        if top_bar is not None and hasattr(top_bar, "add_action"):
            top_bar.insert_title_widget(self._count)          # badge beside the title
            top_bar.add_action(self._status)
            top_bar.add_action(self._add_btn)
            top_bar.add_action(self._refresh_btn)
            top_bar.add_menu_action("Add item…", self._add_item)
            top_bar.add_menu_action("Check for updates", self._refresh)
        else:
            header = QHBoxLayout()
            header.setSpacing(10)
            header.addWidget(self._title)
            header.addWidget(self._count)
            header.addStretch(1)
            header.addWidget(self._status)
            header.addWidget(self._add_btn)
            header.addWidget(self._refresh_btn)
            root.addLayout(header)

        # ── sort bar: choose the axis; click the active one to flip direction ──
        sortbar = QHBoxLayout()
        sortbar.setSpacing(8)
        sort_lab = QLabel("Sort")
        sort_lab.setStyleSheet(f"color:{ui_helpers.TEXT_DIM};font-size:11px;")
        sortbar.addWidget(sort_lab)
        self._sort_lab = sort_lab
        self._sort_updated = self._sort_chip("Updated", "updated")
        self._sort_channel = self._sort_chip("Channel", "channel")
        sortbar.addWidget(self._sort_updated)
        sortbar.addWidget(self._sort_channel)
        sortbar.addStretch(1)
        self._group_btn = QPushButton("Group")
        self._group_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._group_btn.clicked.connect(self._toggle_group)
        sortbar.addWidget(self._group_btn)
        root.addLayout(sortbar)

        # ── the fleet ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_host = QWidget()
        self._list = QVBoxLayout(self._list_host)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(9)
        scroll.setWidget(self._list_host)
        ui_helpers.install_autofade_scrollbars(scroll)  # the slim auto-fading pill
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

            # The tray presence — a watchtower's resting state. Real displays
            # only (offscreen/CI has no tray), and self-disabling when the
            # desktop doesn't support one.
            from trackerkeeper.tray import AppTray

            self._tray = AppTray(window, on_refresh=self._refresh) if window else None
            if self._tray is not None and self._tray.available:
                self._window.top_bar.add_menu_action(
                    "Hide to tray", self._tray._hide_window)
                self._sync_tray()

    # ── responsive: columns and labels drop off as the window narrows ──
    def resizeEvent(self, e):  # noqa: N802 (Qt override)
        super().resizeEvent(e)
        tier = width_tier(self.width())
        if tier != self._tier:
            self._tier = tier
            self._apply_tier()
            self._render()   # cards carry per-tier columns

    def _apply_tier(self) -> None:
        """Chrome outside the card list. The top bar is the tightest real estate:
        the check status goes first, then the Add / Check buttons themselves —
        they stay reachable in the hamburger menu, so nothing is lost, and the
        bar never squeezes its labels into unreadable slivers."""
        narrow, wide = self._tier == TIER_NARROW, self._tier == TIER_WIDE
        m = 8 if narrow else 12
        self._root.setContentsMargins(m, 6 if narrow else 8, m, 8 if narrow else 10)
        self._sort_lab.setVisible(not narrow)
        self._status.setVisible(wide)
        self._add_btn.setVisible(wide)          # menu keeps it below wide
        self._refresh_btn.setVisible(not narrow)
        self._refresh_btn.setText("Check for updates" if wide else "Check")
        self._count.setMinimumWidth(1)          # the badge clips before the buttons do

    def _sync_tray(self) -> None:
        if self._tray is not None and self._tray.available:
            self._tray.set_update_count(sum(1 for i in self._items if i.has_update()))

    # ── styling helpers ──
    def _chip_button(self, text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            "QPushButton{border:1px solid rgba(255,255,255,0.2);border-radius:9px;"
            "padding:6px 14px;background:transparent;color:#ddd;}"
            f"QPushButton:hover{{border-color:{_ACCENT};color:#fff;}}"
            "QPushButton:disabled{color:#666;border-color:rgba(255,255,255,0.08);}")
        # Never let the top bar squeeze a label into a sliver ("Add…" → "dd."):
        # the button holds its text width and the tier rules decide whether it's
        # shown at all.
        from PySide6.QtWidgets import QSizePolicy

        b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        b.clicked.connect(slot)
        return b

    # ── sort ──
    def _sort_chip(self, text: str, key: str) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: self._toggle_sort(key))
        return b

    def _toggle_sort(self, key: str) -> None:
        if self._sort_key == key:
            self._sort_desc = not self._sort_desc  # same axis → flip direction
        else:
            self._sort_key, self._sort_desc = key, True
        self._render()

    def _sync_sort_chips(self) -> None:
        for btn, key, label in ((self._sort_updated, "updated", "Updated"),
                                (self._sort_channel, "channel", "Channel")):
            active = self._sort_key == key
            arrow = (" ↓" if self._sort_desc else " ↑") if active else ""
            btn.setText(label + arrow)
            if active:
                btn.setStyleSheet(
                    "QPushButton{border:1px solid %s;border-radius:8px;padding:3px 11px;"
                    "background:rgba(255,255,255,0.10);color:#fff;font-size:11px;}"
                    % _ACCENT)
            else:
                btn.setStyleSheet(
                    "QPushButton{border:1px solid rgba(255,255,255,0.12);border-radius:8px;"
                    "padding:3px 11px;background:transparent;color:#aaa;font-size:11px;}"
                    "QPushButton:hover{color:#fff;border-color:rgba(255,255,255,0.3);}")

    def _group_header(self, category: str, items: list) -> QWidget:
        """A slim section label — the category, its count, and any updates in it."""
        n_up = sum(1 for i in items if i.has_update())
        tail = (f'  <span style="color:{_NEW};">{n_up} new</span>' if n_up
                else f'  <span style="color:#666;">{len(items)}</span>')
        lab = QLabel(f'<span style="letter-spacing:0.6px;">{_esc(category).upper()}</span>{tail}')
        lab.setTextFormat(Qt.TextFormat.RichText)
        lab.setContentsMargins(2, 8, 0, 0)
        lab.setStyleSheet(f"color:{ui_helpers.TEXT_DIM};font-size:11px;font-weight:700;")
        return lab

    def _sync_group_btn(self) -> None:
        on = self._grouped
        self._group_btn.setText("Grouped" if on else "Group")
        if on:
            self._group_btn.setStyleSheet(
                "QPushButton{border:1px solid %s;border-radius:8px;padding:3px 11px;"
                "background:rgba(255,255,255,0.10);color:#fff;font-size:11px;}" % _ACCENT)
        else:
            self._group_btn.setStyleSheet(
                "QPushButton{border:1px solid rgba(255,255,255,0.12);border-radius:8px;"
                "padding:3px 11px;background:transparent;color:#aaa;font-size:11px;}"
                "QPushButton:hover{color:#fff;border-color:rgba(255,255,255,0.3);}")

    def _sort_list(self, items: list) -> list:
        """``items`` in the chosen order. Items with no known release date always
        sink to the bottom, whichever direction is active."""
        if self._sort_key == "channel":
            out = sorted(items, key=lambda i: (channel_label(i).lower(), i.name.lower()))
            return list(reversed(out)) if self._sort_desc else out
        # "updated": by release recency (full timestamp when we have one)
        def recency(i: catalog.Item) -> str:
            return i.latest_at or i.latest_date
        dated = sorted((i for i in items if recency(i)),
                       key=lambda i: (recency(i), i.name.lower()))
        if self._sort_desc:
            dated.reverse()
        undated = sorted((i for i in items if not recency(i)),
                         key=lambda i: i.name.lower())
        return dated + undated

    def _sorted_items(self) -> list:
        return self._sort_list(self._items)

    def _grouped_view(self) -> list:
        """``[(category, sorted_items), …]`` — named categories A→Z, then the
        ungrouped ones under "Other". Each category is sorted independently by
        the active sort, so grouping and sorting compose."""
        buckets: dict[str, list] = {}
        for it in self._items:
            buckets.setdefault(it.group or "", []).append(it)
        names = sorted((g for g in buckets if g), key=str.lower)
        if "" in buckets:
            names.append("")
        return [(g or "Other", self._sort_list(buckets[g])) for g in names]

    def _toggle_group(self) -> None:
        self._grouped = not self._grouped
        self._render()

    # ── render ──
    def _render(self) -> None:
        while self._list.count():
            it = self._list.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._sync_sort_chips()
        self._sync_group_btn()
        if self._grouped and any(i.group for i in self._items):
            for category, items in self._grouped_view():
                self._list.addWidget(self._group_header(category, items))
                for item in items:
                    self._list.addWidget(self._card(item))
        else:
            for item in self._sorted_items():
                self._list.addWidget(self._card(item))
        self._list.addStretch(1)
        n = sum(1 for i in self._items if i.has_update())
        if self._tier == TIER_NARROW:   # the badge earns its width or goes
            self._count.setText(f"· {n} new" if n else "")
        else:
            self._count.setText(
                f"· {n} update{'s' if n != 1 else ''} available" if n else "· all current")
        self._sync_tray()

    def _card(self, item: catalog.Item) -> QWidget:
        card = QFrame()
        card.setStyleSheet(_CARD_NEW if item.has_update() else _CARD)
        narrow = self._tier == TIER_NARROW
        outer = QHBoxLayout(card)
        outer.setContentsMargins(10 if narrow else 14, 8 if narrow else 11,
                                 8 if narrow else 14, 8 if narrow else 11)
        outer.setSpacing(6 if narrow else 12)

        # left: name + platform + versions
        left = QVBoxLayout()
        left.setSpacing(3)
        topline = QLabel(
            (f'<span style="color:{_NEW};">●</span> ' if item.has_update() else "")
            + f'<b style="color:{ui_helpers.TEXT};">{_esc(item.name)}</b>'
            + (f'  <span style="color:{ui_helpers.TEXT_DIM};font-size:11px;">'
               f'{_esc(item.platform)}</span>' if item.platform else ""))
        topline.setTextFormat(Qt.TextFormat.RichText)
        # A label's size hint is its full text width, which would pin a floor on
        # how narrow the window can go — let both text lines shrink (and clip)
        # instead of blocking the resize.
        topline.setMinimumWidth(1)
        left.addWidget(topline)
        version = self._version_line(item)
        version.setMinimumWidth(1)
        left.addWidget(version)
        if item.error:
            err = QLabel("couldn't check — showing last known")
            err.setStyleSheet("color:#c98a2b;font-size:11px;")
            left.addWidget(err)
        outer.addLayout(left, 1)

        # columns: channel + how-long-ago (fixed widths so they align down the
        # list). The channel column is the first thing to go as we narrow — the
        # platform tag beside the name already hints at it.
        if self._tier == TIER_WIDE:
            chan = QLabel(channel_label(item))
            chan.setFixedWidth(78)
            chan.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            chan.setStyleSheet(f"color:{ui_helpers.TEXT_DIM};font-size:11px;")
            outer.addWidget(chan)
        age = QLabel(humanize_age(item.latest_at or item.latest_date))
        age.setFixedWidth(66 if self._tier == TIER_NARROW else 88)
        age.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        age.setStyleSheet("color:#8a8a8a;font-size:11px;")
        outer.addWidget(age)

        # right: changelog + actions ("changelog →" collapses to the arrow when
        # every pixel counts — the tooltip keeps it discoverable)
        if item.changelog_url or item.latest_url:
            text = "→" if self._tier == TIER_NARROW else "changelog →"
            link = QLabel(f'<a href="{item.latest_url or item.changelog_url}" '
                          f'style="color:{_ACCENT};text-decoration:none;">{text}</a>')
            link.setToolTip("Open the changelog")
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
            item.latest_at = res.at
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
        groups = {i.group for i in self._items if i.group}
        action, result = ItemDialog(self._window or self, existing_names=taken,
                                    groups=groups).prompt()
        if action == "save" and result is not None:
            self._items.append(result)
            catalog.save(self._items)
            self._render()

    def _edit_item(self, item: catalog.Item) -> None:
        from trackerkeeper.item_dialog import ItemDialog

        taken = {i.name.lower() for i in self._items if i is not item}
        groups = {i.group for i in self._items if i.group}
        action, _ = ItemDialog(self._window or self, item=item,
                               existing_names=taken, groups=groups).prompt()
        if action == "delete":
            self._remove(item)
        elif action == "save":
            catalog.save(self._items)  # item mutated in place
            self._render()


def _esc(s: str) -> str:
    import html

    return html.escape(s or "")


def build_content(window) -> QWidget:
    """The run_app content factory: tracker keeper's dashboard."""
    return Dashboard(window)
