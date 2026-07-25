"""The source providers — the checkers that turn a tracked item into "what's
the latest version, and where's the changelog."

The whole product thesis lives here: there is no single "latest version" API,
so tracker keeper IS the uniform layer. Each provider is a small function
``(item, http, http_text) -> CheckResult | None`` for one KIND of source;
growing coverage is adding providers, one world at a time (github, arch,
appstore, cachyos, appledev, steam, and the generic rss feed reader today;
flatpak next).

Network I/O goes through two injected seams — :func:`http_json` (JSON APIs) and
:func:`http_text` (HTML / plain-text pages, e.g. a mirror's directory index) —
so every provider is unit-testable with a fake and no test touches the network,
exactly like ``deliver``'s detection probes.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from trackerkeeper import __version__

_TIMEOUT = 8
_UA = f"trackerkeeper/{__version__} (+https://github.com/wolfgangwarehaus/trackerkeeper)"


@dataclass(frozen=True)
class CheckResult:
    """What a provider found: the newest version string, its changelog/release
    URL, and the ISO date (YYYY-MM-DD) it was published (empty if unknown)."""

    latest: str
    url: str = ""
    date: str = ""      # day precision (YYYY-MM-DD) — back-compat + sorting
    at: str = ""        # the source's full ISO timestamp when it gives one, else ""


def http_json(url: str) -> dict | None:
    """GET ``url`` and parse JSON, or None on any failure (offline, 404, rate
    limit, malformed). Sends a User-Agent — GitHub rejects requests without one.
    A network seam: providers call it, tests replace it."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                                   "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def http_text(url: str) -> str | None:
    """GET ``url`` and return the decoded body, or None on any failure. The seam
    for providers that read HTML or plain text (a directory index, an RSS feed)
    rather than a JSON API. Tests replace it with a canned string."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.read().decode("utf-8", "ignore")
    except (urllib.error.URLError, OSError):
        return None


# ── the providers ────────────────────────────────────────────────────────────


def _github(item, http, http_text) -> CheckResult | None:
    """Latest GitHub release for ``owner/repo`` (item.ref). Covers a huge slice
    of open apps, tools, and games. Unauthenticated: 60 req/hr is plenty for a
    personal fleet; a rate-limited response is just None (shown as 'couldn't
    check', never a wrong version)."""
    if "/" not in item.ref:
        return None
    data = http(f"https://api.github.com/repos/{item.ref}/releases/latest")
    if not isinstance(data, dict):
        return None
    tag = data.get("tag_name") or data.get("name") or ""
    if not tag:
        return None
    published = data.get("published_at") or ""
    return CheckResult(
        latest=str(tag).lstrip("vV") if str(tag)[:1] in "vV" else str(tag),
        url=data.get("html_url", "") or item.changelog_url,
        date=published[:10],
        at=published,
    )


def _arch(item, http, http_text) -> CheckResult | None:
    """Latest Arch Linux package version for ``item.ref`` (the pkgname) via
    archlinux.org's JSON search. Great for the Linux desktop fleet — KDE
    Plasma (plasma-desktop), Mesa, systemd, and friends track here even on
    Arch-derived distros."""
    data = http(f"https://archlinux.org/packages/search/json/?name={item.ref}")
    if not isinstance(data, dict):
        return None
    results = [r for r in data.get("results", []) if r.get("pkgname") == item.ref]
    if not results:
        return None
    # prefer a stable repo (core/extra) over testing when the pkg is in several
    results.sort(key=lambda r: (r.get("repo") in ("core-testing", "extra-testing"),))
    r = results[0]
    ver = r.get("pkgver", "")
    rel = r.get("pkgrel", "")
    last = r.get("last_update") or ""
    return CheckResult(
        latest=f"{ver}-{rel}" if ver and rel else ver,
        url=f"https://archlinux.org/packages/{r.get('repo','')}/{r.get('arch','')}/{item.ref}/",
        date=last[:10],
        at=last,
    )


def _appstore(item, http, http_text) -> CheckResult | None:
    """Latest App Store version via Apple's public iTunes Lookup API — the whole
    iOS / Mac App Store tail in one checker, no auth. ``item.ref`` is either the
    numeric track id (all digits, e.g. ``6449580241``) or the bundle id (e.g.
    ``com.blackmagic-design.DaVinciCamera``); a wrong id fails safe to None,
    never another app's version. The lookup returns the store's ``version`` and
    ``currentVersionReleaseDate`` — exactly the "what's new, when" this tracks."""
    ref = item.ref.strip()
    if not ref:
        return None
    key = "id" if ref.isdigit() else "bundleId"
    data = http(f"https://itunes.apple.com/lookup?{key}={ref}&country=us")
    if not isinstance(data, dict):
        return None
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    ver = r.get("version") or ""
    if not ver:
        return None
    released = r.get("currentVersionReleaseDate") or ""
    return CheckResult(
        latest=str(ver),
        url=r.get("trackViewUrl", "") or item.changelog_url,
        date=released[:10],
        at=released,
    )


# the CachyOS ISO editions served under mirror.cachyos.org/ISO/<edition>/
_CACHY_EDITIONS = ("desktop", "handheld", "kde", "cli")


def _cachyos(item, http, http_text) -> CheckResult | None:
    """Latest CachyOS release. The distro is rolling — there's no version API —
    but its mirror serves a browsable ISO index whose snapshot folders are dated
    ``YYMMDD`` (``.../ISO/desktop/260628/cachyos-desktop-linux-260628.iso``). The
    newest folder IS the latest release. ``item.ref`` picks the edition
    (``desktop`` default; also ``kde`` / ``handheld`` / ``cli``); the snapshot
    date doubles as the version, so a newer ISO than yours reads as an update."""
    edition = (item.ref or "desktop").strip().lower()
    if edition not in _CACHY_EDITIONS:
        return None
    # NOT named `html` — that would shadow the module-level `import html` that
    # _rss_field's unescape depends on, and the next person to reach for it here
    # would get a string back instead of the module.
    page = http_text(f"https://mirror.cachyos.org/ISO/{edition}/")
    if not page:
        return None
    snapshots = re.findall(r'href="(\d{6})/"', page)  # YYMMDD folders
    if not snapshots:
        return None
    latest = max(snapshots)  # fixed-width YYMMDD sorts chronologically
    iso_date = f"20{latest[0:2]}-{latest[2:4]}-{latest[4:6]}"
    return CheckResult(
        latest=iso_date,  # the snapshot date is the "version" for a rolling distro
        url=f"https://mirror.cachyos.org/ISO/{edition}/{latest}/",
        date=iso_date,
    )


# Apple's developer releases feed — every OS build (betas + finals) Apple ships,
# newest first: iOS, iPadOS, macOS, watchOS, tvOS, visionOS.
_APPLE_RELEASES_RSS = "https://developer.apple.com/news/releases/rss/releases.rss"
_MONTHS = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


def _rss_field(entry: str, tag: str) -> str:
    """The text of ``<tag>…</tag>`` inside one feed entry (CDATA unwrapped,
    entities decoded), or ""."""
    m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", entry, re.DOTALL)
    if not m:
        return ""
    val = m.group(1).strip()
    cdata = re.search(r"<!\[CDATA\[(.*?)\]\]>", val, re.DOTALL)
    if cdata:
        val = cdata.group(1).strip()
    return html.unescape(val)


def _rss_date(pubdate: str) -> str:
    """An RSS RFC-822 ``pubDate`` ("Tue, 21 Jul 2026 13:00:00 PDT") → ISO date.
    Pulled by regex so a named timezone (PDT) can't trip a strict parser."""
    m = re.search(r"(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{4})", pubdate or "")
    if not m:
        return ""
    day, mon, year = m.groups()
    month = _MONTHS.get(mon)
    return f"{year}-{month:02d}-{int(day):02d}" if month else ""


def _appledev(item, http, http_text) -> CheckResult | None:
    """Latest Apple release matching ``item.ref`` from the developer releases
    feed. ``ref`` is a title filter — "iOS 27", "macOS 27", "watchOS 27" — and
    the newest matching entry wins (betas included), e.g. "iOS 27.0 beta 4
    (24A5390f)". The one clean auto-source for the otherwise-manual Apple tail:
    no OS-update API exists, but this feed lists every build Apple ships."""
    needle = (item.ref or "").strip().lower()
    if not needle:
        return None
    xml = http_text(_APPLE_RELEASES_RSS)
    if not xml:
        return None
    for entry in re.findall(r"<item>(.*?)</item>", xml, re.DOTALL):  # newest first
        title = _rss_field(entry, "title")
        if title and needle in title.lower():
            return CheckResult(
                latest=title,
                url=_rss_field(entry, "link") or "https://developer.apple.com/news/releases/",
                date=_rss_date(_rss_field(entry, "pubDate")),
            )
    return None


def _feed_entries(xml: str) -> list:
    """Every entry of an RSS (``<item>``) or Atom (``<entry>``) feed, in feed
    order — which is newest-first for essentially every changelog feed."""
    entries = re.findall(r"<item[\s>](.*?)</item>", xml, re.DOTALL)
    return entries or re.findall(r"<entry[\s>](.*?)</entry>", xml, re.DOTALL)


def _entry_link(entry: str) -> str:
    """An entry's URL. RSS puts it in ``<link>text</link>``; Atom uses a
    self-closing ``<link href="…"/>``, which has no text for _rss_field to find."""
    text = _rss_field(entry, "link")
    if text:
        return text
    m = re.search(r'<link[^>]*\bhref="([^"]+)"', entry)
    return m.group(1) if m else ""


def _entry_date(entry: str) -> str:
    """An entry's publication date as ISO ``YYYY-MM-DD``. RSS carries RFC-822 in
    ``<pubDate>``; Atom carries ISO-8601 in ``<published>`` / ``<updated>``."""
    pub = _rss_field(entry, "pubDate")
    if pub:
        return _rss_date(pub)
    for tag in ("published", "updated"):
        val = _rss_field(entry, tag)
        if re.match(r"\d{4}-\d{2}-\d{2}", val):
            return val[:10]
    return ""


def _entry_label(entry: str) -> str:
    """What names this entry: its title, or — when the feed leaves titles empty —
    the version out of its link. KDE's own announcement feed does exactly that,
    shipping ``<title/>`` and putting the release in the URL
    (``…/announcements/plasma/6/6.7.3/``), so a title-only reader sees nothing."""
    title = _rss_field(entry, "title")
    if title:
        return title
    m = re.search(r"/v?(\d+(?:\.\d+)*)/?$", _entry_link(entry))
    return m.group(1) if m else ""


def _version_from_title(title: str) -> str:
    """A version out of an entry title when there's an obvious one ("Plasma
    6.7.3 released" → "6.7.3"), else the title itself. Same rule the Steam
    checker uses: a title IS a usable version when it's all the source gives."""
    m = re.search(r"\bv?(\d+(?:\.\d+)+)", title)
    return m.group(1) if m else title.strip()


def _rss(item, http, http_text) -> CheckResult | None:
    """Latest entry from ANY RSS or Atom feed — the widest-coverage checker here.
    Most projects, distros, and desktops publish releases as a feed even when
    they expose no API at all, so this is the generic answer for the long tail.

    ``item.ref`` is the feed URL, optionally followed by a space and a filter
    phrase the entry title must contain (``https://…/feed.xml plasma``) — one
    busy feed can then serve several tracked items. URLs can't contain spaces,
    so the split is unambiguous. The newest matching entry wins.
    """
    ref = (item.ref or "").strip()
    url, _, needle = ref.partition(" ")
    if not url.lower().startswith(("http://", "https://")):
        return None
    xml = http_text(url)
    if not xml:
        return None
    needle = needle.strip().lower()
    for entry in _feed_entries(xml):
        label = _entry_label(entry)
        if not label:
            continue
        link = _entry_link(entry)
        # Filter on the link as well as the title: a title-less feed (KDE) can
        # only be narrowed by its URL path, and "plasma" reads the same either way.
        if needle and needle not in f"{label} {link}".lower():
            continue
        return CheckResult(
            latest=_version_from_title(label),
            url=link or item.changelog_url,
            date=_entry_date(entry),
        )
    return None


def _steam(item, http, http_text) -> CheckResult | None:
    """Latest update for a Steam game via the public (no-auth) news API.
    ``item.ref`` is the numeric appid (e.g. Slay the Spire 2 = ``2868840``). The
    feed carries sales and press alongside patches, so prefer entries tagged
    ``patchnotes``, then the developer's own announcements, then whatever's
    newest. A version in the title ("… v0.109.0") becomes the version; else the
    title stands in. Covers the whole Steam library — games AND apps."""
    appid = (item.ref or "").strip()
    if not appid.isdigit():
        return None
    data = http("https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
                f"?appid={appid}&count=20&maxlength=1")
    if not isinstance(data, dict):
        return None
    items = (data.get("appnews") or {}).get("newsitems") or []
    if not items:
        return None

    def first(pred):
        return next((it for it in items if pred(it)), None)

    chosen = (first(lambda it: "patchnotes" in (it.get("tags") or []))
              or first(lambda it: it.get("feedname") == "steam_community_announcements")
              or items[0])  # feed is newest-first
    title = chosen.get("title") or ""
    ver = re.search(r"v?(\d+(?:\.\d+)+)", title)
    ts = chosen.get("date")
    # The feed's own `url` is Steam's canonical link — it redirects to the live
    # post (a constructed /news/app/<id>/view/<gid> 404s: the news gid isn't that
    # URL's id). Fall back to the game's news hub, which is always valid.
    url = chosen.get("url") or f"https://store.steampowered.com/news/app/{appid}"
    return CheckResult(
        latest=ver.group(1) if ver else title,
        url=url,
        date=_unix_date(ts),
        at=_unix_iso(ts),
    )


def _unix_date(ts) -> str:
    """A Unix timestamp (seconds) → ISO date, or "" if falsy/bad."""
    return _unix(ts, "%Y-%m-%d")


def _unix_iso(ts) -> str:
    """A Unix timestamp (seconds) → full ISO-8601 UTC, or "" if falsy/bad."""
    return _unix(ts, "%Y-%m-%dT%H:%M:%SZ")


def _unix(ts, fmt: str) -> str:
    if not ts:
        return ""
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).strftime(fmt)
    except (ValueError, OSError, OverflowError):
        return ""


def _manual(item, http, http_text) -> CheckResult | None:
    """A manual item has no source to poll — you set ``installed`` yourself.
    Returns None so a refresh leaves it untouched (never an error, never a
    fabricated 'latest')."""
    return None


_PROVIDERS = {
    "github": _github,
    "arch": _arch,
    "appstore": _appstore,
    "cachyos": _cachyos,
    "appledev": _appledev,
    "steam": _steam,
    "rss": _rss,
    "manual": _manual,
}


def check(item, http=http_json, http_text=http_text) -> CheckResult | None:
    """Run ``item``'s provider. Unknown kind or manual → None. Never raises: a
    provider that throws is swallowed to None so one bad item can't sink a
    whole refresh (the dashboard shows it as 'couldn't check')."""
    provider = _PROVIDERS.get(item.kind)
    if provider is None:
        return None
    try:
        return provider(item, http, http_text)
    except Exception:
        return None
