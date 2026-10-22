"""The fleet, minus any widgets — what both front ends share.

The Widgets dashboard (``dashboard.py``) and the phone interface
(``trackerkeeper/quick``) draw the same list differently, but they agree on
what it SAYS: how old an update is, whether it's still fresh news, what a
failed check means, and how a refresh's answers fold back into the catalog.
That agreement lives here, testable without a widget.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from trackerkeeper import catalog, sources

# How long an update stays "fresh". After this it's still pending — you haven't
# installed it — but it stops shouting: no accent, and the text eases back.
FRESH_DAYS = 7

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


def local_time(iso: str) -> str:
    """A stored timestamp → the same moment on the viewer's own clock,
    ``YYYY-MM-DD HH:MM``. "" / unparseable → "".

    Timestamps are *persisted* in UTC so a catalog stays portable; only the
    display is localized. Skipping this step made the provenance line lie by a
    whole timezone — "checked 17:29" shown at 13:29 EDT, four hours in the
    future, which reads as a clock bug rather than an offset."""
    then = _parse_iso(iso or "")
    if then is None:
        return ""
    return then.astimezone().strftime("%Y-%m-%d %H:%M")


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


class RefreshWorker(QThread):
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


def apply_results(items: list, results: dict, reasons: dict | None = None,
                  now=None) -> list:
    """Fold a refresh's answers (``{name: CheckResult}``) into ``items`` in
    place and return the ones that became NEWLY new — an update we hadn't
    already surfaced, which is what earns a notification.

    An item that didn't answer keeps its last-known values and gets an error:
    the reason the worker recorded, else "unreachable" (the conservative read
    of an empty result). Manual items are never touched."""
    from datetime import datetime, timezone

    stamped = now or datetime.now(timezone.utc)
    when = stamped.strftime("%Y-%m-%d %H:%M")   # stored: UTC
    reasons = reasons or {}
    newly = []
    for item in items:
        if item.kind == "manual":
            continue
        res = results.get(item.name)
        if res is None:
            item.error = reasons.get(item.name, "unreachable")
            continue
        was_update_to = item.latest if item.has_update() else ""
        item.latest, item.latest_url, item.latest_date = res.latest, res.url, res.date
        item.latest_at, item.latest_notes = res.at, res.notes
        item.checked_at, item.error = when, ""
        if item.has_update() and item.latest != was_update_to:
            newly.append(item)
    return newly


def news_text(newly: list) -> tuple[str, str]:
    """The desktop notification for a refresh's newly-new items."""
    names = ", ".join(i.name for i in newly[:4])
    more = f" +{len(newly) - 4} more" if len(newly) > 4 else ""
    return (f"{len(newly)} new update{'s' if len(newly) != 1 else ''}",
            f"{names}{more}")


def upstream_version(item: catalog.Item) -> str:
    """The version as the project names it: Arch's ``6.8.1-1`` carries a
    packaging release (``-1``) that no upstream URL knows about."""
    if item.kind == "arch" and "-" in item.latest:
        return item.latest.rsplit("-", 1)[0]
    return item.latest


def changelog_link(item: catalog.Item) -> str:
    """Where "changelog" goes for an item, best first:

    1. a link YOU set containing ``{version}`` — filled with the latest
       version (``kde.org/announcements/plasma/6/{version}/``,
       ``fex-emu.com/{version}/``): you've said exactly where each
       release's notes live, so it beats anything a source guesses;
    2. the source's own link, when that link IS release notes (a GitHub
       release, a Steam patch post, Apple's notes page);
    3. the link you set;
    4. whatever the source returned (a package or store page beats nothing).
    """
    own = (item.changelog_url or "").strip()
    if "{version}" in own:
        if item.latest:
            return own.replace("{version}", upstream_version(item))
        own = ""          # no version yet — a template isn't a link
    source = sources.BY_KIND.get(item.kind)
    if item.latest_url and (source is None or source.notes_link):
        return item.latest_url
    return own or item.latest_url
