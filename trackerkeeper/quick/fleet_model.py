"""The fleet as QML sees it: a list model plus the verbs a phone needs.

``Fleet`` owns the catalog for the phone interface the way ``Dashboard`` does
for the Widgets one — load, refresh off the UI thread, mark updated, add /
edit / delete, "seen" banking — and everything it says about an item comes
from ``trackerkeeper.fleet``, so the two front ends can't drift on wording.
"""

from __future__ import annotations

import copy
import time

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QObject,
    Qt,
    QTimer,
    Signal,
    Slot,
)

from trackerkeeper import catalog, fleet, sources
from trackerkeeper.bus import AppBus

OTHER = "Other"   # the section ungrouped items sit under (same as the dashboard)

# role name -> (Item) -> value. Order is the role numbering.
_ROLES = {
    "name": lambda i: i.name,
    "platform": lambda i: i.platform,
    "section": lambda i: i.group or OTHER,
    "channel": fleet.channel_label,
    "installed": lambda i: i.installed,
    "latest": lambda i: i.latest,
    "hasUpdate": lambda i: i.has_update(),
    "isNew": lambda i: i.is_new(),
    "fresh": fleet.is_fresh,
    "age": lambda i: fleet.humanize_age_short(i.latest_at or i.latest_date),
    # A row's short form; the detail sheet carries fleet.error_text's full one.
    "error": lambda i: ("" if not i.error else
                        "no match" if i.error == sources.NOT_FOUND else "couldn't check"),
    # The second line of a row: the move you'd make, or what you're on.
    "versionLine": lambda i: version_line(i),
}
_ROLE_IDS = {Qt.ItemDataRole.UserRole + 1 + n: k for n, k in enumerate(_ROLES)}


def version_line(i) -> str:
    """``1.2.9 → 1.3.0`` when there's somewhere to go (``1.3.0 available`` if
    we don't know what you have); otherwise just the version you're on. No
    "· current" — a row with no dot and no arrow already says that."""
    if i.has_update():
        return f"{i.installed} → {i.latest}" if i.installed else f"{i.latest} available"
    return i.latest or i.installed or "not checked yet"


def order(items: list) -> list:
    """Grouped A→Z with "Other" last. Within a group, what needs you floats
    up — unseen updates, then ones you've seen but not installed — and each
    of those tiers runs newest release first, undated last.

    The desktop dashboard sorts a group by date alone; a phone is glanced at,
    so the rows worth acting on lead (ObtainX does the same)."""
    def recency(i):
        return i.latest_at or i.latest_date

    def tier(i):
        return 0 if i.is_new() else (1 if i.has_update() else 2)

    def within(group):
        out = []
        for t in (0, 1, 2):
            rows = [i for i in group if tier(i) == t]
            dated = sorted((i for i in rows if recency(i)),
                           key=lambda i: (recency(i), i.name.lower()), reverse=True)
            out += dated + sorted((i for i in rows if not recency(i)),
                                  key=lambda i: i.name.lower())
        return out

    buckets: dict[str, list] = {}
    for it in items:
        buckets.setdefault(it.group or "", []).append(it)
    names = sorted((g for g in buckets if g), key=str.lower)
    if "" in buckets:
        names.append("")
    return [i for g in names for i in within(buckets[g])]


class FleetModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list = []

    def set_rows(self, rows: list) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def touch(self) -> None:
        """Re-read every row's roles in place (ages tick over; no reset, so
        the list keeps its scroll position)."""
        if self._rows:
            self.dataChanged.emit(self.index(0), self.index(len(self._rows) - 1))

    def rowCount(self, parent=None):  # noqa: N802 (Qt override)
        return 0 if parent is not None and parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        key = _ROLE_IDS.get(role)
        return _ROLES[key](self._rows[index.row()]) if key else None

    def roleNames(self):  # noqa: N802 (Qt override)
        return {rid: QByteArray(k.encode()) for rid, k in _ROLE_IDS.items()}


class Fleet(QObject):
    changed = Signal()        # counts / groups / filter
    statusChanged = Signal()
    checkingChanged = Signal()

    def __init__(self, parent=None, *, start: bool = True):
        super().__init__(parent)
        self._items = catalog.load()
        self._filter = "all"
        self._checking = False
        self._status = ""
        self._worker = None
        self._last_refresh = None
        self._model = FleetModel(self)
        self._sync()
        self._ticker = QTimer(self)      # "2h" becomes "3h" without a refresh
        self._ticker.setInterval(60_000)
        self._ticker.timeout.connect(self._model.touch)
        self._ticker.start()
        self._periodic = None
        if start:
            self._periodic = QTimer(self)
            self._periodic.timeout.connect(self.refresh)
            self.apply_refresh_interval()
            AppBus.get().tracking_prefs_changed.connect(self.apply_refresh_interval)
            from PySide6.QtGui import QGuiApplication

            app = QGuiApplication.instance()
            if app is not None:
                app.applicationStateChanged.connect(self._on_app_state)
            QTimer.singleShot(400, self.refresh)   # the launch check

    # ── state QML binds to ──
    def _get_filter(self) -> str:
        return self._filter

    def _set_filter(self, value: str) -> None:
        if value != self._filter:
            self._filter = value or "all"
            self._sync()

    model = Property(QObject, lambda self: self._model, constant=True)
    filter = Property(str, _get_filter, _set_filter, notify=changed)
    groups = Property("QVariantList",
                      lambda self: sorted({i.group for i in self._items if i.group}, key=str.lower)
                      + ([OTHER] if any(not i.group for i in self._items) else []),
                      notify=changed)
    updateCount = Property(int, lambda self: sum(i.has_update() for i in self._items),
                           notify=changed)
    newCount = Property(int, lambda self: sum(i.is_new() for i in self._items), notify=changed)
    total = Property(int, lambda self: len(self._items), notify=changed)
    shown = Property(int, lambda self: self._model.rowCount(), notify=changed)
    checking = Property(bool, lambda self: self._checking, notify=checkingChanged)
    status = Property(str, lambda self: self._status, notify=statusChanged)

    def _filter_label(self) -> str:
        if self._filter == "new":
            return "Updates waiting"
        return "All" if self._filter in ("", "all") else self._filter

    def _last_checked(self) -> str:
        """The newest check on record, local HH:MM — so a fresh launch can say
        when it last looked before its own check lands."""
        stamps = [i.checked_at for i in self._items if i.checked_at]
        if not stamps:
            return ""
        local = fleet.local_time(max(stamps))
        return local[-5:].lstrip("0") if local else ""   # "4:20", not "04:20"

    def _subtitle(self) -> str:
        """The quiet line under the title: the view (only when it's filtered —
        "All" is noise) and when we last looked."""
        view = "" if self._filter in ("", "all") else self._filter_label()
        when = self._last_checked()
        state = "checking…" if self._checking else (f"checked {when}" if when else "")
        return " · ".join(p for p in (view, state) if p)

    filterLabel = Property(str, _filter_label, notify=changed)
    subtitle = Property(str, _subtitle, notify=statusChanged)
    # The ONE green thing in the header, and only when there's news.
    newsLine = Property(str, lambda self: (
        f"{self.newCount} new update{'s' if self.newCount != 1 else ''}"
        if self.newCount else ""), notify=changed)

    def _filter_options(self) -> list:
        opts = [{"key": "all", "label": "All", "count": len(self._items)},
                {"key": "new", "label": "Updates waiting",
                 "count": sum(i.has_update() for i in self._items)}]
        for g in self.groups:
            opts.append({"key": g, "label": g,
                         "count": sum(1 for i in self._items if (i.group or OTHER) == g)})
        return opts

    filterOptions = Property("QVariantList", _filter_options, notify=changed)

    @Slot(str, result=int)
    def sectionNews(self, section: str) -> int:  # noqa: N802 (QML API)
        """How many items in a section have an update (its header's count)."""
        return sum(1 for i in self._items if (i.group or OTHER) == section and i.has_update())

    def _visible(self) -> list:
        if self._filter == "new":
            return [i for i in self._items if i.has_update()]
        if self._filter not in ("", "all"):
            return [i for i in self._items if (i.group or OTHER) == self._filter]
        return self._items

    def _sync(self) -> None:
        self._model.set_rows(order(self._visible()))
        self.changed.emit()
        self.statusChanged.emit()

    def _find(self, name: str):
        return next((i for i in self._items if i.name == name), None)

    # ── checking ──
    def apply_refresh_interval(self) -> None:
        from trackerkeeper.dashboard import refresh_interval_minutes

        if self._periodic is None:
            return
        minutes = refresh_interval_minutes()
        if minutes > 0:
            self._periodic.start(minutes * 60_000)
        else:
            self._periodic.stop()

    @Slot()
    def refresh(self) -> None:
        if self._checking:
            return
        self._checking = True
        self.checkingChanged.emit()
        self._set_status("checking…")
        self._worker = fleet.RefreshWorker([copy.copy(i) for i in self._items], self)
        self._worker.done.connect(self._on_results)
        self._worker.start()

    def _on_results(self, results: dict) -> None:
        from datetime import datetime, timezone

        stamped = datetime.now(timezone.utc)
        self._last_refresh = time.monotonic()
        reasons = getattr(self._worker, "reasons", {}) or {}
        newly = fleet.apply_results(self._items, results, reasons, now=stamped)
        catalog.save(self._items)
        auto = [i for i in self._items if i.kind != "manual"]
        checked = sum(1 for i in auto if not i.error)
        self._checking = False
        self.checkingChanged.emit()
        self._set_status(f"checked {checked}/{len(auto)} · "
                         f"{stamped.astimezone().strftime('%H:%M')}")
        self._sync()
        if newly:
            AppBus.get().notify.emit(*fleet.news_text(newly))

    def _set_status(self, text: str) -> None:
        self._status = text
        self.statusChanged.emit()

    def _on_app_state(self, state) -> None:
        from trackerkeeper.dashboard import refresh_interval_minutes

        if state == Qt.ApplicationState.ApplicationActive:
            # Back in front after a while away: check if the last one is stale
            # (a backgrounded phone app's timer may not have fired).
            minutes = refresh_interval_minutes()
            if (self._last_refresh is not None and minutes > 0
                    and time.monotonic() - self._last_refresh >= minutes * 60):
                self.refresh()
        else:
            self.markSeen()   # you've looked; next time it's pending, not news

    # ── verbs ──
    @Slot()
    def markSeen(self) -> None:  # noqa: N802 (QML API)
        changed = False
        for item in self._items:
            if item.is_new():
                item.seen_version = item.latest
                changed = True
        if changed:
            catalog.save(self._items)
            self._sync()

    @Slot(str)
    def markUpdated(self, name: str) -> None:  # noqa: N802 (QML API)
        item = self._find(name)
        if item is not None and item.has_update():
            item.installed = item.latest
            catalog.save(self._items)
            self._sync()

    @Slot(str)
    def remove(self, name: str) -> None:
        self._items = [i for i in self._items if i.name != name]
        catalog.save(self._items)
        self._sync()

    @Slot(str, result="QVariantMap")
    def item(self, name: str) -> dict:
        """Everything the detail sheet / edit page shows for one item."""
        i = self._find(name)
        if i is None:
            return {}
        stamp = i.latest_at or i.latest_date
        return {
            "name": i.name, "platform": i.platform, "group": i.group, "kind": i.kind,
            "ref": i.ref, "installed": i.installed, "latest": i.latest,
            "changelogUrl": fleet.changelog_link(i),
            "ownChangelogUrl": i.changelog_url,
            "channel": fleet.channel_label(i), "age": fleet.humanize_age(stamp),
            "checked": fleet.local_time(i.checked_at) if i.checked_at else "",
            "notes": i.latest_notes, "hasUpdate": i.has_update(), "isNew": i.is_new(),
            "error": fleet.error_text(i.error) if i.error else "",
        }

    @Slot(result="QVariantList")
    def sources(self) -> list:
        """The source picker: every checker, as the Add dialog lists them."""
        return [{"kind": s.kind, "label": s.label, "hint": s.hint} for s in sources.SOURCES]

    @Slot(str, "QVariantMap", result=str)
    def save(self, original: str, data: dict) -> str:
        """Add (``original`` = "") or edit an item. Returns "" on success, else
        the problem to show — the same rules as the desktop Add dialog."""
        name = str(data.get("name", "")).strip()
        if not name:
            return "A name is required."
        taken = {i.name.lower() for i in self._items if i.name != original}
        if name.lower() in taken:
            return "You're already tracking something by that name."
        kind = str(data.get("kind", "manual")) or "manual"
        ref = str(data.get("ref", "")).strip()
        src = sources.BY_KIND.get(kind)
        problem = src.ref_problem(ref) if src else ""
        if problem:
            return problem
        target = self._find(original) if original else None
        if target is None:
            target = catalog.Item(name=name)
            self._items.append(target)
        target.name = name
        target.platform = str(data.get("platform", "")).strip()
        target.group = str(data.get("group", "")).strip()
        target.kind = kind
        target.ref = "" if kind == "manual" else ref
        target.installed = str(data.get("installed", "")).strip()
        target.changelog_url = str(data.get("changelogUrl", "")).strip()
        catalog.save(self._items)
        self._sync()
        return ""
