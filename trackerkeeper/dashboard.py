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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from trackerkeeper import catalog, sources, ui_helpers
from trackerkeeper.bus import AppBus
from trackerkeeper.design_tokens import (
    TYPE_CAPTION,
    TYPE_DISPLAY,
    TYPE_MICRO,
    TYPE_TINY,
    type_qss,
)
from trackerkeeper.top_bar import TopBar

_ACCENT = ui_helpers.ACCENT
# There used to be a separate "new" green (#56c48d) sitting a few points off the
# accent — two near-identical colours doing different jobs, which read as a
# printing error rather than a distinction. The accent is now the ONE colour that
# means "this is live news"; everything past is neutral. Read ui_helpers.ACCENT at
# render time (not import) so changing the accent in Settings lands on the next
# repaint instead of at the next launch.

# How long an update stays "fresh". After this it's still pending — you haven't
# installed it — but it stops shouting: no accent, and the text eases back.
FRESH_DAYS = 7

# The past-item text. A pinch under full white, not the 0.7 the secondary labels
# use — enough to feel settled beside a fresh row, not so much it reads disabled.
_TEXT_PAST = "rgba(255,255,255,0.78)"
_TEXT_PAST_DIM = "rgba(255,255,255,0.45)"   # its version line / changelog


def _rgba(hex_colour: str, alpha: float) -> str:
    """``#2fbe8a`` → ``rgba(47,190,138,0.08)``. Card tints follow whatever accent
    is live rather than freezing one brand colour into the stylesheet."""
    h = (hex_colour or "").lstrip("#")
    if len(h) != 6:
        return f"rgba(255,255,255,{alpha})"
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def is_fresh(item: catalog.Item, now=None) -> bool:
    """True when an item has an update that landed inside :data:`FRESH_DAYS`.

    An update with no known release date counts as fresh: we can't prove it's
    old, and quietly greying out something actionable is the worse failure."""
    if not item.has_update():
        return False
    stamp = item.latest_at or item.latest_date
    if not stamp:
        return True
    then = _parse_iso(stamp)
    if then is None:
        return True
    from datetime import datetime, timezone

    now = now or datetime.now(timezone.utc)
    return (now - then).days < FRESH_DAYS


# `.QFrame` (leading dot) matches the card's EXACT type only — a bare `QFrame`
# selector cascades into child QLabels (QLabel subclasses QFrame), boxing every
# line of text. Ask me how I know.
_CARD = (".QFrame{background:rgba(255,255,255,0.045);border:1px solid "
         "rgba(255,255,255,0.10);border-radius:12px;}")


def _card_qss(fresh: bool) -> str:
    """The card's own frame. Only a FRESH item gets the accent wash — a pending
    update that's a fortnight old shouldn't glow as loudly as one from an hour
    ago, or the list has no foreground."""
    if not fresh:
        return _CARD
    accent = ui_helpers.ACCENT
    return (f".QFrame{{background:{_rgba(accent, 0.08)};border:1px solid "
            f"{_rgba(accent, 0.40)};border-radius:12px;}}")


# tracker keeper is a UTILITY window first — it lives in the tray and gets
# opened in a corner, so it has to stay readable narrow. These are the sizes
# the layout is designed against, not arbitrary minimums.
DEFAULT_SIZE = (480, 620)   # a tall, slim fleet list
MIN_SIZE = (300, 320)       # still usable: name, version, age

TIER_NARROW, TIER_MEDIUM, TIER_WIDE = "narrow", "medium", "wide"

# Every control that sits on (or reads against) the top bar matches the window
# chrome's height, so Check / Add / ⋯ line up with the −□× buttons.
_CHROME_H = TopBar.BUTTON_SIZE[1]


# Which category sections are folded shut. UI state, so it lives in settings
# (the documented _s extension path) rather than the catalog — collapsing a
# group must never touch the tracked data.
_KEY_COLLAPSED = "app/collapsed_groups"


def load_collapsed() -> set:
    """The category names currently collapsed (empty on a fresh profile)."""
    import json

    from trackerkeeper.settings import get_settings

    raw = get_settings()._s.value(_KEY_COLLAPSED)
    if not raw:
        return set()
    try:
        return {str(n) for n in json.loads(str(raw))}
    except (ValueError, TypeError):
        return set()


def save_collapsed(names) -> None:
    import json

    from trackerkeeper.settings import get_settings

    get_settings()._s.setValue(_KEY_COLLAPSED, json.dumps(sorted(names)))


# ── the heartbeat ────────────────────────────────────────────────────────────
# tracker keeper rests in the tray for days at a time. Checking only at launch
# would mean the board shows you whatever the world looked like when you last
# booted it — which is exactly the thing this app exists to fix. The periodic
# check is what makes "what dropped today" true while the window is closed, and
# it's what gives the notifications something to fire about.
_KEY_INTERVAL = "app/refresh_interval_minutes"
DEFAULT_INTERVAL_MIN = 120
# A floor, not a preference: every checker hits someone else's server, and the
# unauthenticated GitHub API allows 60 requests an hour. Nothing below this is
# more useful — it's just louder.
MIN_INTERVAL_MIN = 15


def refresh_interval_minutes() -> int:
    """How often to re-check, in minutes. ``0`` disables the periodic check
    entirely (launch and the Check button still work); anything positive is
    clamped up to :data:`MIN_INTERVAL_MIN`."""
    from trackerkeeper.settings import get_settings

    raw = get_settings()._s.value(_KEY_INTERVAL)
    if raw is None or str(raw).strip() == "":
        return DEFAULT_INTERVAL_MIN
    try:
        minutes = int(str(raw))
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL_MIN
    return max(MIN_INTERVAL_MIN, minutes) if minutes > 0 else 0


def set_refresh_interval_minutes(minutes: int) -> None:
    from trackerkeeper.settings import get_settings

    get_settings()._s.setValue(_KEY_INTERVAL, int(minutes))


class _Card(QFrame):
    """A fleet card. Clicking anywhere that isn't a control opens the detail
    view — the buttons and the changelog link are real children, so they consume
    their own clicks and never reach this handler."""

    def __init__(self, on_click) -> None:
        super().__init__()
        self._on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):  # noqa: N802 (Qt override)
        if e.button() == Qt.MouseButton.LeftButton:
            self._on_click()
            return
        super().mousePressEvent(e)


# How a category section separates itself from the rows beneath it. A dim caps
# label over a flat run of cards left the groups blending into one list.
#
# Three things do the work, and a fourth was tried and dropped: a FILLED BAND
# behind the header is invisible here. The chrome is already near-black, so a
# dark band has nothing to darken against, and a light one lands within a few
# percent of the cards' own rgba(255,255,255,0.045). A light hairline reads on
# a dark background where neither of those does.
GROUP_RULE = "1px solid rgba(255,255,255,0.13)"   # under the header
GROUP_GAP = 10        # px above each section after the first
GROUP_INDENT = 12     # px the cards sit in from the section's left edge


class _GroupHeader(QFrame):
    """A category's clickable header row: a disclosure arrow, the name, and its
    count (or "N new" when the group is hiding updates — a collapsed section
    must never hide news)."""

    def __init__(self, html: str, on_click) -> None:
        super().__init__()
        self._on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        rule = (f"border-bottom:{GROUP_RULE};" if GROUP_RULE else "border:none;")
        self.setStyleSheet(".QFrame{background:transparent;border:none;" + rule + "}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 4, 2, 4)
        lay.setSpacing(0)
        lab = QLabel(html)
        lab.setTextFormat(Qt.TextFormat.RichText)
        lab.setStyleSheet(f"color:{ui_helpers.TEXT};font-weight:700;"
                          + type_qss(TYPE_MICRO))
        lay.addWidget(lab)
        lay.addStretch(1)

    def mousePressEvent(self, e):  # noqa: N802 (Qt override)
        if e.button() == Qt.MouseButton.LeftButton:
            self._on_click()
            return
        super().mousePressEvent(e)


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
    source = sources.BY_KIND.get(item.kind)
    return source.channel if source else (item.kind or "—")


def error_text(error: str) -> str:
    """What a failed check says on the card. The two failures need different
    words because they need different actions: an unreachable source will
    probably fix itself, a handle that matches nothing needs you to edit it."""
    if error == sources.NOT_FOUND:
        return "nothing matched this source — check the handle in ⋯"
    return "couldn't reach the source — showing last known"


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


def humanize_age_short(iso: str, now=None) -> str:
    """The age as 2–3 characters: ``9h``, ``4d``, ``2w``, ``3mo``, ``1y``.

    The narrow tier used to render the full phrase into a 62px box, which cut
    the NUMBER off the front and left "hours ago" — the one part carrying no
    information. Short forms fit whole."""
    iso = (iso or "").strip()
    if not iso:
        return ""
    from datetime import datetime, timezone

    then = _parse_iso(iso)
    if then is None:
        return ""
    now = now or datetime.now(timezone.utc)
    sec = max(0, (now - then).total_seconds())
    if "T" in iso:
        if sec < 3600:
            return "now" if sec < 60 else f"{int(sec // 60)}m"
        if sec < 86400:
            return f"{int(sec // 3600)}h"
    days = (now.date() - then.date()).days
    if days <= 0:
        return "today"
    if days < 7:
        return f"{days}d"
    if days < 30:
        return f"{days // 7}w"
    if days < 365:
        return f"{days // 30}mo"
    return f"{days // 365}y"


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


# How many source checks are in flight at once. Each one is a blocking HTTP GET
# with an 8s timeout, so checking serially made the whole refresh as slow as the
# SUM of its sources — and one unreachable mirror stalled every item queued
# behind it. Bounded so a large fleet can't open a socket per item.
MAX_PARALLEL_CHECKS = 8


class _RefreshWorker(QThread):
    """Checks every auto item off the UI thread, several at a time. Emits
    ``{name: CheckResult}`` for the ones that answered (a missing name = couldn't
    check / manual)."""

    done = Signal(object)

    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self._snapshot = snapshot  # list of Item (copies safe to read off-thread)
        self.reasons: dict = {}    # name -> why it came back empty (read after `done`)

    def run(self) -> None:  # noqa: N802 (Qt override)
        from concurrent.futures import ThreadPoolExecutor

        from trackerkeeper import sources

        auto = [i for i in self._snapshot if i.kind != "manual"]
        if not auto:
            self.done.emit({})
            return
        # check_with_reason never raises (it swallows to None), so map() can't be
        # derailed by one bad provider, and it keeps results aligned to inputs.
        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_CHECKS, len(auto)),
                                thread_name_prefix="tk-check") as pool:
            outcomes = list(pool.map(sources.check_with_reason, auto))
        # Why a check came back empty rides alongside, so a wrong handle reads as
        # a wrong handle instead of "the internet is down".
        self.reasons = {item.name: reason
                        for item, (_res, reason) in zip(auto, outcomes, strict=True)
                        if reason}
        self.done.emit({item.name: res
                        for item, (res, _reason) in zip(auto, outcomes, strict=True)
                        if res is not None})


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
        self._collapsed = load_collapsed()   # category names folded shut
        # The heartbeat timer. Stays None under offscreen (tests, CI, rig) — it
        # doubles as the "this is a real display, network is allowed" sentinel.
        self._periodic: object | None = None
        self._last_refresh: float | None = None   # time.monotonic() of the last result

        # Utility sizing: a slim default and a genuinely small floor. The
        # window only takes the default when there's no saved geometry (run_app
        # stamps _geometry_restored) — a size you chose is never overridden.
        if window is not None:
            window.setMinimumSize(*MIN_SIZE)
            if not getattr(window, "_geometry_restored", False):
                window.resize(*DEFAULT_SIZE)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 10)
        root.setSpacing(6)
        self._root = root

        # ── header controls: the update-count badge, a check status, and the
        # Add / Check actions. Built once, then folded onto the window's top-bar
        # line when we have one (the dough-matched single top row); otherwise
        # they render as their own inline header row (tests, standalone). ──
        self._title = QLabel("tracker keeper")
        self._title.setStyleSheet(type_qss(TYPE_DISPLAY) + f"color:{ui_helpers.TEXT};")
        self._count = QLabel("")
        self._count.setStyleSheet(f"color:{ui_helpers.ACCENT};font-weight:600;"
                                  + type_qss(TYPE_TINY))
        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{ui_helpers.TEXT_DIM};" + type_qss(TYPE_TINY))
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
            top_bar.add_menu_action("Collapse all groups",
                                    lambda: self._set_all_collapsed(True))
            top_bar.add_menu_action("Expand all groups",
                                    lambda: self._set_all_collapsed(False))
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
        sortbar.setSpacing(6)
        sort_lab = QLabel("Sort")
        sort_lab.setStyleSheet(f"color:{ui_helpers.TEXT_DIM};" + type_qss(TYPE_TINY))
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
        self._list.setSpacing(5)
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

            # …and keep checking. The timer runs whether or not the window is
            # visible — a watchtower hidden in the tray is still watching, and
            # this is the path that fires the "N new updates" notification.
            self._periodic = QTimer(self)
            self._periodic.timeout.connect(self._refresh)
            self.apply_refresh_interval()
            # Changing the interval in Settings re-arms the timer immediately —
            # a watchtower shouldn't need a relaunch to change how often it looks.
            AppBus.get().tracking_prefs_changed.connect(self.apply_refresh_interval)

            # The tray presence — a watchtower's resting state. Real displays
            # only (offscreen/CI has no tray), and self-disabling when the
            # desktop doesn't support one.
            from trackerkeeper.tray import AppTray

            self._tray = AppTray(window, on_refresh=self._refresh) if window else None
            if self._tray is not None and self._tray.available:
                self._window.top_bar.add_menu_action(
                    "Hide to tray", self._tray._hide_window)
                self._sync_tray()

    # ── the heartbeat ──
    def apply_refresh_interval(self) -> None:
        """(Re)arm the periodic check from the stored setting — at startup, and
        whenever Settings changes it. A no-op where there's no timer (offscreen)."""
        if self._periodic is None:
            return
        minutes = refresh_interval_minutes()
        if minutes <= 0:
            self._periodic.stop()
        else:
            self._periodic.start(minutes * 60 * 1000)

    def showEvent(self, e):  # noqa: N802 (Qt override)
        super().showEvent(e)
        # Opening the window from the tray should show a current board, not what
        # the last check found hours ago — but only when the data has actually
        # gone stale, so toggling the window isn't a burst of requests.
        self._refresh_if_stale()

    def hideEvent(self, e):  # noqa: N802 (Qt override)
        super().hideEvent(e)
        # You've looked — bank it. Marking seen on HIDE rather than on show is
        # what keeps the NEW badges visible for the whole time the window is
        # open; marking on show would clear them in the same instant they
        # appeared, which is the same as never showing them at all.
        self._mark_seen()

    def _mark_seen(self) -> None:
        """Record every currently-new update as seen, so the next time this
        window opens they're pending-but-not-news. Persisted — that's what makes
        "new since you last looked" survive a restart."""
        changed = False
        for item in self._items:
            if item.is_new():
                item.seen_version = item.latest
                changed = True
        if changed:
            catalog.save(self._items)

    def _refresh_if_stale(self) -> None:
        if self._periodic is None or self._last_refresh is None:
            return      # offscreen, or the launch check hasn't landed yet
        import time

        minutes = refresh_interval_minutes()
        if minutes > 0 and (time.monotonic() - self._last_refresh) >= minutes * 60:
            self._refresh()

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
        # A smaller title that reads in full beats a bigger one that elides —
        # step it down as the bar tightens.
        top_bar = getattr(self._window, "top_bar", None)
        if top_bar is not None and hasattr(top_bar, "set_title_scale"):
            top_bar.set_title_scale(0 if wide else (2 if narrow else 1))
        self._sort_lab.setVisible(not narrow)
        self._status.setVisible(wide)
        self._add_btn.setVisible(wide)          # menu keeps it below wide
        self._refresh_btn.setVisible(not narrow)
        self._refresh_btn.setText("Check for updates" if wide else "Check")
        # (the badge's width floor is set in _render, where its TEXT is known)

    def _sync_count_width(self, has_news: bool) -> None:
        """Give the badge a width floor that matches the text it's ACTUALLY
        showing — and none at all when it's showing nothing.

        This was set once per tier change, from whatever text happened to be
        there at the time, so a badge that later emptied out (everything
        current) kept reserving ~59px. The title paid for it: on a 360px bar it
        elided to "trac…" beside an invisible label holding a sixth of the row."""
        # No floor, ever. A reserved width here is width taken from the app's
        # own name — and an EMPTY badge reserving ~59px is what elided the title
        # to "trac…" on a 360px bar with visible space beside it.
        self._count.setMinimumWidth(0)

    def _sync_tray(self) -> None:
        if self._tray is not None and self._tray.available:
            self._tray.set_update_count(
                sum(1 for i in self._items if i.has_update()),
                sum(1 for i in self._items if i.is_new()))

    # ── styling helpers ──
    def _chip_button(self, text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            "QPushButton{border:1px solid rgba(255,255,255,0.2);border-radius:7px;"
            "padding:2px 10px;background:transparent;color:#ddd;}"
            f"QPushButton:hover{{border-color:{_ACCENT};color:#fff;}}"
            "QPushButton:disabled{color:#666;border-color:rgba(255,255,255,0.08);}"
            + type_qss(TYPE_TINY))
        b.setFixedHeight(_CHROME_H)   # flush with the window controls beside it
        # Never let the top bar squeeze a label into a sliver ("Add…" → "dd."):
        # the button holds its text width and the tier rules decide whether it's
        # shown at all.

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
                    "QPushButton{border:1px solid %s;border-radius:6px;padding:1px 9px;"
                    "background:rgba(255,255,255,0.10);color:#fff;}" % _ACCENT
                    + type_qss(TYPE_TINY))
            else:
                btn.setStyleSheet(
                    "QPushButton{border:1px solid rgba(255,255,255,0.12);border-radius:6px;"
                    "padding:1px 9px;background:transparent;color:#aaa;}"
                    "QPushButton:hover{color:#fff;border-color:rgba(255,255,255,0.3);}"
                    + type_qss(TYPE_TINY))

    def _group_header(self, category: str, items: list) -> QWidget:
        """A slim clickable section row — arrow, category, count / "N new"."""
        n_up = sum(1 for i in items if i.has_update())
        collapsed = category in self._collapsed
        arrow = "▸" if collapsed else "▾"
        tail = (f'  <span style="color:{ui_helpers.ACCENT};">{n_up} new</span>' if n_up
                else f'  <span style="color:#666;">{len(items)}</span>')
        html = (f'<span style="color:#999;">{arrow}</span>  '
                f'<span style="letter-spacing:1.1px;">{_esc(category).upper()}</span>{tail}')
        return _GroupHeader(html, lambda c=category: self._toggle_collapsed(c))

    def _toggle_collapsed(self, category: str) -> None:
        self._collapsed ^= {category}   # symmetric difference: toggle membership
        save_collapsed(self._collapsed)
        self._render()

    def _set_all_collapsed(self, collapsed: bool) -> None:
        names = {g for g, _ in self._grouped_view()} if collapsed else set()
        self._collapsed = names
        save_collapsed(names)
        self._render()

    def _sync_group_btn(self) -> None:
        on = self._grouped
        self._group_btn.setText("Grouped" if on else "Group")
        if on:
            self._group_btn.setStyleSheet(
                "QPushButton{border:1px solid %s;border-radius:6px;padding:1px 9px;"
                "background:rgba(255,255,255,0.10);color:#fff;}" % _ACCENT
                + type_qss(TYPE_TINY))
        else:
            self._group_btn.setStyleSheet(
                "QPushButton{border:1px solid rgba(255,255,255,0.12);border-radius:6px;"
                "padding:1px 9px;background:transparent;color:#aaa;}"
                "QPushButton:hover{color:#fff;border-color:rgba(255,255,255,0.3);}"
                + type_qss(TYPE_TINY))

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
            old = it.widget()
            if old is not None:
                # Un-parent FIRST: deleteLater alone leaves the widget a visible
                # child at its old geometry until the event loop gets around to
                # it, so the previous rows ghost over the new ones (collapsing a
                # group made it obvious). Same order as AppWindow.set_content.
                old.setParent(None)
                old.deleteLater()
        self._sync_sort_chips()
        self._sync_group_btn()
        if self._grouped and any(i.group for i in self._items):
            for n, (category, items) in enumerate(self._grouped_view()):
                if n and GROUP_GAP:
                    self._list.addSpacing(GROUP_GAP)
                self._list.addWidget(self._group_header(category, items))
                if category in self._collapsed:
                    continue        # header stays (it still reports "N new")
                for item in items:
                    self._list.addWidget(self._indent(self._card(item)))
        else:
            for item in self._sorted_items():
                self._list.addWidget(self._card(item))
        self._list.addStretch(1)
        n = sum(1 for i in self._items if i.has_update())
        if self._tier == TIER_NARROW:
            # Just the number. At this width the app's own NAME is worth more
            # bar than the word "new" is, and the count still reads.
            self._count.setText(f"· {n}" if n else "")
        elif self._tier == TIER_MEDIUM:
            # A middle length: the full phrase is ~150px and pushed the title to
            # "tracke…" at 420px, which is a poor trade for two extra words.
            self._count.setText(f"· {n} new" if n else "· all current")
        else:
            self._count.setText(
                f"· {n} update{'s' if n != 1 else ''} available" if n else "· all current")
        self._sync_count_width(n > 0)
        self._sync_tray()

    def _indent(self, card: QWidget) -> QWidget:
        """Step a card in from the section's left edge, so the rows read as
        belonging UNDER their category rather than merely following it. Returns
        the card untouched when indenting is off, or at the narrow tier where
        every pixel is already spoken for."""
        if not GROUP_INDENT or self._tier == TIER_NARROW:
            return card
        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(GROUP_INDENT, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(card)
        return holder

    def _card(self, item: catalog.Item) -> QWidget:
        card = _Card(lambda i=item: self._show_detail(i))
        fresh = is_fresh(item)
        accent = ui_helpers.ACCENT
        # Three states, not two: FRESH (news — full white name, accent
        # everywhere), PENDING-BUT-OLD (still yours to install, but it stops
        # shouting), and CURRENT (nothing to do). The old code only knew
        # has_update, so a month-old update looked exactly like this morning's.
        name_colour = ui_helpers.TEXT if fresh else _TEXT_PAST
        card.setStyleSheet(_card_qss(fresh))
        narrow = self._tier == TIER_NARROW
        outer = QHBoxLayout(card)
        # Dense by design: this is a scan-the-fleet list, not a reading surface.
        outer.setContentsMargins(8 if narrow else 10, 5, 6 if narrow else 8, 5)
        outer.setSpacing(6 if narrow else 10)

        # left: name + platform + versions
        left = QVBoxLayout()
        left.setSpacing(1)
        # The name line is a ROW of separate labels rather than one rich-text
        # label, so the name alone can elide while the dot, the NEW badge and
        # the platform tag keep their size. As one label, Qt clipped the whole
        # string at the frame edge and the name — the only part you navigate
        # by — was what disappeared.
        topline = QWidget()
        top_row = QHBoxLayout(topline)
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(5)
        # The dot marks "you have something to install" either way — a pending
        # update must never become invisible just because it got old — but it
        # only carries the accent while the news is fresh.
        if item.has_update():
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{accent if fresh else _TEXT_PAST_DIM};"
                              + type_qss(TYPE_CAPTION))
            top_row.addWidget(dot, 0)
        name = ui_helpers.ElidedLabel(item.name)
        # One tier down from body — the list scans denser, and because these are
        # tokens (not literal px) the Settings font-scale still applies.
        name.setStyleSheet(f"color:{name_colour};font-weight:700;"
                           + type_qss(TYPE_CAPTION))
        # A floor. Ignored size policy means the name yields space to every
        # fixed sibling, which at the medium tier squeezed it to NOTHING — the
        # card showed a platform tag and no name at all. It may elide; it may
        # not vanish.
        name.setMinimumWidth(64)
        top_row.addWidget(name, 1)
        # NEW marks what arrived since you last had the window open — an
        # update you've already seen keeps the dot but loses the shout.
        # It follows FRESHNESS for colour: if you've been away a month, a
        # three-week-old release is still news to you and still says NEW,
        # but it has no business shouting in accent next to this morning's.
        if item.is_new():
            badge = QLabel("NEW")
            badge.setStyleSheet(f"color:{accent if fresh else _TEXT_PAST_DIM};"
                                + type_qss(TYPE_CAPTION))
            top_row.addWidget(badge, 0)
        # The platform tag is a hint, and the name it was crowding is not — so
        # it only appears at the widest tier, alongside the channel column.
        if item.platform and self._tier == TIER_WIDE:
            plat = QLabel(item.platform)
            plat.setStyleSheet(f"color:{ui_helpers.TEXT_DIM};" + type_qss(TYPE_CAPTION))
            top_row.addWidget(plat, 0)
        left.addWidget(topline)
        left.addWidget(self._version_row(item, fresh, narrow))
        if item.error:
            err = QLabel(error_text(item.error))
            err.setStyleSheet("color:#c98a2b;" + type_qss(TYPE_TINY))
            left.addWidget(err)
        outer.addLayout(left, 1)

        # columns: channel + how-long-ago (fixed widths so they align down the
        # list). The channel column is the first thing to go as we narrow — the
        # platform tag beside the name already hints at it.
        if self._tier == TIER_WIDE:
            chan = QLabel(channel_label(item))
            chan.setFixedWidth(70)
            chan.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            chan.setStyleSheet(f"color:{ui_helpers.TEXT_DIM};" + type_qss(TYPE_TINY))
            outer.addWidget(chan)
        stamp = item.latest_at or item.latest_date
        age = QLabel(humanize_age_short(stamp) if narrow else humanize_age(stamp))
        if narrow:
            age.setToolTip(humanize_age(stamp))   # the full phrase on hover
        age.setFixedWidth(34 if narrow else 80)
        age.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        age.setStyleSheet("color:#8a8a8a;" + type_qss(TYPE_TINY))
        outer.addWidget(age)

        # right: changelog + actions ("changelog →" collapses to the arrow when
        # every pixel counts — the tooltip keeps it discoverable)
        if item.changelog_url or item.latest_url:
            # Full labels only at the WIDE tier. At 430px "changelog →" plus
            # "mark updated" cost ~175px of the row, which is why the NAME was
            # eliding to "SteamOS…" — the labels were being paid for out of the
            # one column that matters. Tooltips carry the meaning either way.
            text = "changelog →" if self._tier == TIER_WIDE else "→"
            # Escape the URL: it's user-entered (the Add/Edit dialog), and an
            # unescaped quote would close the href and let the rest of the string
            # become markup in a rich-text label.
            href = _esc(item.latest_url or item.changelog_url)
            # Accent only where there's fresh news to go and read. On settled
            # rows the link stays available but stops competing — nine accent
            # links down a list is just a green column, and nothing leads.
            link_colour = accent if fresh else _TEXT_PAST_DIM
            link = QLabel(f'<a href="{href}" '
                          f'style="color:{link_colour};text-decoration:none;">{text}</a>')
            link.setToolTip("Open the changelog")
            link.setTextFormat(Qt.TextFormat.RichText)
            link.setOpenExternalLinks(True)
            link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            outer.addWidget(link)
        if item.has_update():
            # "mark updated" is ~90px of button on a 300px window — it was
            # taking the room the name needed. A tick says the same thing.
            mark = self._mini("mark updated" if self._tier == TIER_WIDE else "✓",
                              lambda: self._mark_updated(item))
            mark.setToolTip(f"Mark {item.name} as updated to {item.latest}")
            outer.addWidget(mark)
        outer.addWidget(self._mini("⋯", lambda: self._edit_item(item)))
        return card

    def _version_row(self, item: catalog.Item, fresh: bool, narrow: bool) -> QWidget:
        """The version line as a row of labels, so the BUILD you'd move to keeps
        its colour and its room while the version you already have gives way."""
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        if item.has_update():
            # The BUILD you'd move to is the one number worth colouring — but
            # only while it's news. Past that it's just a fact, in plain text.
            new_colour = ui_helpers.ACCENT if fresh else _TEXT_PAST
            # At the narrow tier the version you HAVE is dropped entirely. Two
            # versions and an arrow in ~180px produced "202607" and "0.109." —
            # both unreadable. The one that matters is where you're going; the
            # detail view still shows the full before/after.
            if not narrow:
                have = ui_helpers.ElidedLabel(item.installed or "—")
                have.setStyleSheet(f"color:{ui_helpers.TEXT_DIM};"
                                   + type_qss(TYPE_CAPTION))
                arrow = QLabel("→")
                arrow.setStyleSheet(f"color:{ui_helpers.TEXT_DIM};"
                                    + type_qss(TYPE_CAPTION))
                lay.addWidget(have, 1)
                lay.addWidget(arrow, 0)
            want = ui_helpers.ElidedLabel(item.latest)
            want.setStyleSheet(f"color:{new_colour};font-weight:700;"
                               + type_qss(TYPE_CAPTION))
            lay.addWidget(want, 0 if not narrow else 1)
            if not narrow:
                lay.addStretch(1)
        else:
            text = f"{item.latest} · current" if item.latest else (item.installed or "—")
            lab = ui_helpers.ElidedLabel(text)
            lab.setStyleSheet(f"color:{_TEXT_PAST_DIM};" + type_qss(TYPE_CAPTION))
            lay.addWidget(lab, 1)
        return row

    def _mini(self, text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            "QPushButton{border:none;border-radius:6px;padding:2px 8px;"
            "background:rgba(255,255,255,0.06);color:#bbb;}"
            f"QPushButton:hover{{background:{_ACCENT};color:#fff;}}"
            + type_qss(TYPE_TINY))
        b.setFixedHeight(_CHROME_H)
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
        import time
        from datetime import datetime, timezone

        self._last_refresh = time.monotonic()   # what _refresh_if_stale measures
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        newly = []
        auto = [i for i in self._items if i.kind != "manual"]
        # Default to "unreachable" when the reason is unknown (a direct
        # _on_results call in a test): the conservative read of an empty result.
        reasons = getattr(self._worker, "reasons", {}) or {}
        for item in auto:
            res = results.get(item.name)
            if res is None:
                item.error = reasons.get(item.name, "unreachable")
                continue
            was_update_to = item.latest if item.has_update() else ""
            item.latest, item.latest_url, item.latest_date = res.latest, res.url, res.date
            item.latest_at, item.latest_notes = res.at, res.notes
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

    def _show_detail(self, item: catalog.Item) -> None:
        from trackerkeeper.detail_dialog import DetailDialog

        if DetailDialog(self._window or self, item=item).prompt() == "marked":
            catalog.save(self._items)   # the dialog mutated `installed` in place
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
