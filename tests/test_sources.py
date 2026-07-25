"""The source providers — every checker is exercised with a FAKE http seam, so
no test touches the network (the same discipline as deliver's detection)."""

from __future__ import annotations

from trackerkeeper import catalog, sources


def _fake(payloads: dict):
    """An http seam that returns a canned payload per URL substring."""
    def http(url: str):
        for frag, data in payloads.items():
            if frag in url:
                return data
        return None
    return http


def test_github_provider_reads_latest_release():
    item = catalog.Item(name="Ghostty", kind="github", ref="ghostty-org/ghostty")
    http = _fake({"repos/ghostty-org/ghostty/releases/latest": {
        "tag_name": "v1.1.3", "html_url": "https://gh/rel/1.1.3",
        "published_at": "2026-07-01T12:00:00Z"}})
    res = sources.check(item, http)
    assert res.latest == "1.1.3"  # the leading v is stripped
    assert res.url == "https://gh/rel/1.1.3"
    assert res.date == "2026-07-01"
    assert res.at == "2026-07-01T12:00:00Z"  # full timestamp kept for "N hours ago"


def test_github_provider_needs_owner_slash_repo():
    item = catalog.Item(name="x", kind="github", ref="notarepo")
    assert sources.check(item, _fake({})) is None


def test_arch_provider_reads_pkgver_and_prefers_stable():
    item = catalog.Item(name="KDE Plasma", kind="arch", ref="plasma-desktop")
    http = _fake({"archlinux.org/packages/search/json": {"results": [
        {"pkgname": "plasma-desktop", "pkgver": "6.4.2", "pkgrel": "2",
         "repo": "extra-testing", "arch": "x86_64", "last_update": "2026-07-10T00:00:00Z"},
        {"pkgname": "plasma-desktop", "pkgver": "6.4.1", "pkgrel": "1",
         "repo": "extra", "arch": "x86_64", "last_update": "2026-07-01T00:00:00Z"},
        {"pkgname": "other", "pkgver": "9", "pkgrel": "9", "repo": "extra"},
    ]}})
    res = sources.check(item, http)
    assert res.latest == "6.4.1-1"  # stable 'extra' preferred over 'extra-testing'
    assert res.date == "2026-07-01"
    assert "plasma-desktop" in res.url


def test_arch_provider_none_when_no_exact_match():
    item = catalog.Item(name="x", kind="arch", ref="nope")
    http = _fake({"search/json": {"results": [{"pkgname": "notnope", "pkgver": "1"}]}})
    assert sources.check(item, http) is None


def test_appstore_provider_reads_version_and_release_date_by_bundle_id():
    item = catalog.Item(name="Blackmagic Camera", kind="appstore",
                        ref="com.blackmagic-design.DaVinciCamera")
    http = _fake({"itunes.apple.com/lookup?bundleId=com.blackmagic-design.DaVinciCamera": {
        "resultCount": 1, "results": [{
            "version": "3.4",
            "currentVersionReleaseDate": "2026-07-22T08:00:00Z",
            "trackViewUrl": "https://apps.apple.com/us/app/blackmagic-camera/id6449580241"}]}})
    res = sources.check(item, http)
    assert res.latest == "3.4"
    assert res.date == "2026-07-22"
    assert res.at == "2026-07-22T08:00:00Z"
    assert res.url == "https://apps.apple.com/us/app/blackmagic-camera/id6449580241"


def test_appstore_provider_looks_up_numeric_track_id():
    item = catalog.Item(name="x", kind="appstore", ref="6449580241")
    http = _fake({"lookup?id=6449580241": {
        "results": [{"version": "3.4", "trackViewUrl": "https://apps.apple.com/x"}]}})
    res = sources.check(item, http)
    assert res.latest == "3.4"


def test_appstore_provider_none_on_empty_results():
    """A wrong/unknown bundle id returns an empty result set — fail safe to None,
    never another app's version."""
    item = catalog.Item(name="x", kind="appstore", ref="com.nope.nope")
    assert sources.check(item, _fake({"lookup": {"resultCount": 0, "results": []}})) is None


def test_appstore_provider_needs_a_ref():
    assert sources.check(catalog.Item(name="x", kind="appstore", ref=""), _fake({})) is None


_CACHY_INDEX = (
    '<a href="../">../</a>'
    '<a href="260426/">260426/</a>'
    '<a href="260628/">260628/</a>'
    '<a href="260530/">260530/</a>'
)


def test_cachyos_provider_picks_the_latest_iso_snapshot():
    item = catalog.Item(name="CachyOS", kind="cachyos", ref="desktop")
    res = sources.check(item, http_text=lambda url: _CACHY_INDEX)
    assert res.latest == "2026-06-28"   # newest YYMMDD folder → ISO date
    assert res.date == "2026-06-28"
    assert res.url == "https://mirror.cachyos.org/ISO/desktop/260628/"


def test_cachyos_provider_defaults_to_desktop_edition():
    seen = {}
    def http_text(url):
        seen["url"] = url
        return _CACHY_INDEX
    sources.check(catalog.Item(name="CachyOS", kind="cachyos", ref=""), http_text=http_text)
    assert seen["url"] == "https://mirror.cachyos.org/ISO/desktop/"


def test_cachyos_provider_rejects_an_unknown_edition():
    item = catalog.Item(name="CachyOS", kind="cachyos", ref="bogus")
    assert sources.check(item, http_text=lambda url: _CACHY_INDEX) is None


def test_cachyos_provider_none_when_index_unreachable():
    item = catalog.Item(name="CachyOS", kind="cachyos", ref="kde")
    assert sources.check(item, http_text=lambda url: None) is None


_APPLE_RSS = """<rss><channel>
<item><title>TestFlight Update</title><link>https://d/tf</link>
  <pubDate>Tue, 21 Jul 2026 13:00:00 PDT</pubDate></item>
<item><title>iOS 27.0 beta 4 (24A5390f)</title><link>https://d/ios27b4</link>
  <pubDate>Mon, 20 Jul 2026 10:00:00 PDT</pubDate></item>
<item><title>iOS 26.6 RC (23G71)</title><link>https://d/rc</link>
  <pubDate>Mon, 13 Jul 2026 10:00:00 PDT</pubDate></item>
<item><title>iOS 27.0 beta (24A5355q)</title><link>https://d/ios27b1</link>
  <pubDate>Mon, 06 Jul 2026 10:00:00 PDT</pubDate></item>
</channel></rss>"""


def test_appledev_returns_newest_entry_matching_the_os_filter():
    item = catalog.Item(name="iOS Beta", kind="appledev", ref="iOS 27")
    res = sources.check(item, http_text=lambda url: _APPLE_RSS)
    assert res.latest == "iOS 27.0 beta 4 (24A5390f)"  # newest iOS 27, not the older beta 1
    assert res.date == "2026-07-20"
    assert res.url == "https://d/ios27b4"


def test_appledev_filter_does_not_match_a_different_os():
    item = catalog.Item(name="x", kind="appledev", ref="macOS 27")
    assert sources.check(item, http_text=lambda url: _APPLE_RSS) is None


def test_appledev_needs_a_filter():
    item = catalog.Item(name="x", kind="appledev", ref="")
    assert sources.check(item, http_text=lambda url: _APPLE_RSS) is None


def test_appledev_none_when_feed_unreachable():
    item = catalog.Item(name="x", kind="appledev", ref="iOS 27")
    assert sources.check(item, http_text=lambda url: None) is None


def _steam_news(items):
    return {"appnews": {"appid": 2868840, "newsitems": items}}


def test_steam_prefers_patchnotes_and_extracts_the_version():
    from datetime import datetime, timezone
    ts = 1752710400
    news = _steam_news([
        {"title": "The Neowsletter", "url": "https://s/news", "date": ts + 100,
         "feedname": "steam_community_announcements", "tags": []},
        {"title": "Beta Patch Notes - v0.109.0", "url": "https://s/patch", "date": ts,
         "gid": "999", "feedname": "steam_community_announcements", "tags": ["patchnotes"]},
    ])
    item = catalog.Item(name="StS2", kind="steam", ref="2868840")
    res = sources.check(item, _fake({"GetNewsForApp": news}))
    assert res.latest == "0.109.0"          # version pulled from the patch-note title
    assert res.url == "https://s/patch"     # the feed's own (working) link, not a constructed one
    assert res.date == datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def test_steam_url_falls_back_to_the_news_hub():
    news = _steam_news([
        {"title": "Patch v1.0", "date": 1752710400, "gid": "1",
         "feedname": "steam_community_announcements", "tags": ["patchnotes"]},  # no url
    ])
    res = sources.check(catalog.Item(name="x", kind="steam", ref="2868840"),
                        _fake({"GetNewsForApp": news}))
    assert res.url == "https://store.steampowered.com/news/app/2868840"


def test_steam_falls_back_to_newest_when_no_patchnotes():
    news = _steam_news([
        {"title": "Big Sale!", "url": "https://s/sale", "date": 1752710400,
         "feedname": "PCGamesN", "tags": []},
    ])
    item = catalog.Item(name="x", kind="steam", ref="2868840")
    res = sources.check(item, _fake({"GetNewsForApp": news}))
    assert res.latest == "Big Sale!"  # no version in title → the title stands in


def test_steam_needs_a_numeric_appid():
    assert sources.check(catalog.Item(name="x", kind="steam", ref="notanid"),
                         _fake({"GetNewsForApp": _steam_news([])})) is None


def test_steam_none_when_no_news():
    item = catalog.Item(name="x", kind="steam", ref="2868840")
    assert sources.check(item, _fake({"GetNewsForApp": _steam_news([])})) is None


def test_manual_never_fetches():
    item = catalog.Item(name="iOS beta", kind="manual", installed="26.1")
    assert sources.check(item, _fake({"anything": {"x": 1}})) is None


def test_unknown_kind_is_none():
    assert sources.check(catalog.Item(name="x", kind="rss"), _fake({})) is None


def test_a_throwing_provider_is_swallowed():
    def boom(url):
        raise RuntimeError("network exploded")
    item = catalog.Item(name="x", kind="github", ref="a/b")
    assert sources.check(item, boom) is None  # one bad item can't sink a refresh


def test_offline_http_returns_none_not_a_fake_version():
    """The cardinal rule: unreachable → None, never an invented 'latest'."""
    item = catalog.Item(name="x", kind="github", ref="a/b")
    assert sources.check(item, lambda url: None) is None


# ── the generic RSS / Atom checker ───────────────────────────────────────────

_RSS_FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>KDE Announcements</title>
  <item>
    <title>Plasma 6.7.4 released</title>
    <link>https://kde.org/announcements/plasma/6/6.7.4/</link>
    <pubDate>Thu, 24 Jul 2026 09:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Plasma 6.7.3 released</title>
    <link>https://kde.org/announcements/plasma/6/6.7.3/</link>
    <pubDate>Tue, 15 Jul 2026 09:00:00 GMT</pubDate>
  </item>
  <item>
    <title>KDE Gear 26.08 released</title>
    <link>https://kde.org/announcements/gear/26.08.0/</link>
    <pubDate>Wed, 23 Jul 2026 09:00:00 GMT</pubDate>
  </item>
</channel></rss>"""

_ATOM_FEED = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Release v3.2.1</title>
    <link rel="alternate" href="https://example.org/releases/3.2.1"/>
    <updated>2026-07-20T12:30:00Z</updated>
  </entry>
</feed>"""


def _no_json(url: str):
    """The JSON seam for feed tests — a feed checker must never reach for it."""
    raise AssertionError(f"an RSS check requested JSON: {url}")


def _item(**kw):
    kw.setdefault("name", "F")
    kw.setdefault("kind", "rss")
    return catalog.Item(**kw)


def test_rss_takes_the_newest_entry_and_extracts_the_version():
    res = sources.check(_item(ref="https://kde.org/feed.xml"),
                        http=_no_json, http_text=lambda u: _RSS_FEED)
    assert res.latest == "6.7.4"          # parsed out of the title
    assert res.url == "https://kde.org/announcements/plasma/6/6.7.4/"
    assert res.date == "2026-07-24"


def test_rss_title_filter_selects_within_one_busy_feed():
    """One feed, several tracked items — the filter is what separates them."""
    res = sources.check(_item(ref="https://kde.org/feed.xml gear"),
                        http=_no_json, http_text=lambda u: _RSS_FEED)
    assert res.latest == "26.08"
    assert res.date == "2026-07-23"       # NOT the newest entry overall


def test_rss_filter_matching_nothing_returns_none():
    assert sources.check(_item(ref="https://kde.org/feed.xml krita"),
                         http=_no_json, http_text=lambda u: _RSS_FEED) is None


def test_atom_feed_reads_href_links_and_iso_dates():
    """Atom's self-closing <link href> and ISO <updated> need different parsing
    from RSS's <link>text</link> and RFC-822 <pubDate>."""
    res = sources.check(_item(ref="https://example.org/atom.xml"),
                        http=_no_json, http_text=lambda u: _ATOM_FEED)
    assert res.latest == "3.2.1"
    assert res.url == "https://example.org/releases/3.2.1"
    assert res.date == "2026-07-20"


def test_rss_title_without_a_version_falls_back_to_the_title():
    feed = ("<rss><channel><item><title>Big summer update</title>"
            "<link>https://x/y</link></item></channel></rss>")
    res = sources.check(_item(ref="https://x/feed"),
                        http=_no_json, http_text=lambda u: feed)
    assert res.latest == "Big summer update"


def test_rss_rejects_a_non_url_ref_without_fetching():
    """A ref that isn't a URL must fail closed, not get pasted into a request."""
    called = []
    assert sources.check(_item(ref="plasma-desktop"),
                         http=_no_json,
                         http_text=lambda u: called.append(u) or "") is None
    assert called == []


def test_rss_unreachable_feed_is_none_not_a_guess():
    assert sources.check(_item(ref="https://x/feed"),
                         http=_no_json, http_text=lambda u: None) is None


_TITLELESS_FEED = """<?xml version="1.0"?>
<rss><channel>
  <item><title/><link>https://kde.org/announcements/plasma/6/6.7.3/</link>
    <pubDate>Tue, 14 Jul 2026 00:00:00 +0000</pubDate></item>
  <item><title/><link>https://kde.org/announcements/gear/26.04.3/</link>
    <pubDate>Thu, 02 Jul 2026 00:00:00 +0000</pubDate></item>
</channel></rss>"""


def test_rss_reads_a_feed_with_empty_titles():
    """KDE's own announcement feed ships <title/> and puts the release in the
    URL — a title-only reader sees an empty feed."""
    res = sources.check(_item(ref="https://kde.org/announcements/index.xml"),
                        http=_no_json, http_text=lambda u: _TITLELESS_FEED)
    assert res.latest == "6.7.3"
    assert res.date == "2026-07-14"


def test_rss_filter_matches_the_link_when_there_is_no_title():
    res = sources.check(_item(ref="https://kde.org/announcements/index.xml gear"),
                        http=_no_json, http_text=lambda u: _TITLELESS_FEED)
    assert res.latest == "26.04.3"


def test_rss_skips_entries_it_cannot_name_at_all():
    """No title, no version in the link → skip it rather than invent a version."""
    feed = ("<rss><channel><item><title/><link>https://x/blog/hello</link></item>"
            "<item><title>Release 2.0</title><link>https://x/r/2.0</link></item>"
            "</channel></rss>")
    res = sources.check(_item(ref="https://x/feed"),
                        http=_no_json, http_text=lambda u: feed)
    assert res.latest == "2.0"      # fell through to the entry it CAN name


# ── conditional requests + the optional token ────────────────────────────────


class _FakeResponse:
    def __init__(self, body: bytes, headers: dict):
        self._body, self.headers = body, headers

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_urlopen(monkeypatch, responses):
    """Replace urlopen with a scripted sequence; records each request's headers."""
    import urllib.request

    seen = []
    queue = list(responses)

    def fake_urlopen(req, timeout=None):
        seen.append(dict(req.headers))
        result = queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


def test_second_fetch_sends_the_etag_and_a_304_reuses_the_payload(monkeypatch):
    """The point of the whole thing: on GitHub a 304 costs no rate-limit quota."""
    import urllib.error

    sources.clear_cache()
    seen = _patch_urlopen(monkeypatch, [
        _FakeResponse(b'{"tag_name": "v2.0"}', {"ETag": '"abc123"'}),
        urllib.error.HTTPError("u", 304, "Not Modified", {}, None),
    ])
    url = "https://api.github.com/repos/a/b/releases/latest"
    assert sources.http_json(url) == {"tag_name": "v2.0"}
    assert sources.http_json(url) == {"tag_name": "v2.0"}   # served from cache
    # first request carries no validator; the second asks "still v2.0?"
    assert "If-none-match" not in {k.lower(): k for k in seen[0]}
    assert seen[1].get("If-none-match") == '"abc123"'
    sources.clear_cache()


def test_last_modified_is_used_when_there_is_no_etag(monkeypatch):
    import urllib.error

    sources.clear_cache()
    seen = _patch_urlopen(monkeypatch, [
        _FakeResponse(b"<rss/>", {"Last-Modified": "Wed, 23 Jul 2026 10:00:00 GMT"}),
        urllib.error.HTTPError("u", 304, "Not Modified", {}, None),
    ])
    assert sources.http_text("https://x/feed") == "<rss/>"
    assert sources.http_text("https://x/feed") == "<rss/>"
    assert seen[1].get("If-modified-since") == "Wed, 23 Jul 2026 10:00:00 GMT"
    sources.clear_cache()


def test_a_304_with_nothing_cached_is_a_failure_not_a_lie(monkeypatch):
    """Can't serve a body we never had — must be None, never a stale guess."""
    import urllib.error

    sources.clear_cache()
    _patch_urlopen(monkeypatch, [urllib.error.HTTPError("u", 304, "", {}, None)])
    assert sources.http_json("https://api.github.com/x") is None
    sources.clear_cache()


def test_a_real_http_error_is_still_a_failure(monkeypatch):
    """HTTPError subclasses URLError — catching it for 304 must not swallow 404."""
    import urllib.error

    sources.clear_cache()
    _patch_urlopen(monkeypatch, [urllib.error.HTTPError("u", 404, "Not Found", {}, None)])
    assert sources.http_json("https://api.github.com/nope") is None
    sources.clear_cache()


def test_a_response_without_validators_is_not_cached(monkeypatch):
    sources.clear_cache()
    seen = _patch_urlopen(monkeypatch, [
        _FakeResponse(b'{"a": 1}', {}),
        _FakeResponse(b'{"a": 2}', {}),
    ])
    assert sources.http_json("https://x/j") == {"a": 1}
    assert sources.http_json("https://x/j") == {"a": 2}   # refetched, not cached
    assert "If-none-match" not in seen[1]
    sources.clear_cache()


def test_the_token_goes_to_github_and_nowhere_else(monkeypatch):
    """A token in the environment must never reach a mirror or a feed."""
    sources.clear_cache()
    monkeypatch.setenv("TRACKERKEEPER_GITHUB_TOKEN", "ghp_secret")
    seen = _patch_urlopen(monkeypatch, [
        _FakeResponse(b"{}", {}),
        _FakeResponse(b"body", {}),
    ])
    sources.http_json("https://api.github.com/repos/a/b/releases/latest")
    sources.http_text("https://mirror.cachyos.org/ISO/desktop/")
    assert seen[0].get("Authorization") == "Bearer ghp_secret"
    assert "Authorization" not in seen[1]
    sources.clear_cache()


def test_no_token_means_no_authorization_header(monkeypatch):
    sources.clear_cache()
    for name in ("TRACKERKEEPER_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    seen = _patch_urlopen(monkeypatch, [_FakeResponse(b"{}", {})])
    sources.http_json("https://api.github.com/repos/a/b/releases/latest")
    assert "Authorization" not in seen[0]
    sources.clear_cache()


# ── why a check came back empty ──────────────────────────────────────────────


def test_reason_is_not_found_when_the_source_answers_but_has_no_match():
    """A typo'd app id: the API is perfectly reachable, it just has no such app."""
    item = catalog.Item(name="X", kind="appstore", ref="9999999999")
    res, reason = sources.check_with_reason(item, _fake({"itunes.apple.com": {"results": []}}))
    assert res is None and reason == sources.NOT_FOUND


def test_reason_is_unreachable_when_the_fetch_itself_fails():
    item = catalog.Item(name="X", kind="appstore", ref="6449580241")
    res, reason = sources.check_with_reason(item, _fake({}))   # every fetch -> None
    assert res is None and reason == sources.UNREACHABLE


def test_a_ref_rejected_before_any_fetch_is_not_found_not_unreachable():
    """github with no slash never gets as far as the network — that's a bad
    handle, and calling it 'unreachable' would send you debugging your wifi."""
    item = catalog.Item(name="X", kind="github", ref="notarepo")
    res, reason = sources.check_with_reason(item, _fake({}))
    assert res is None and reason == sources.NOT_FOUND


def test_rss_filter_matching_nothing_is_not_found():
    item = catalog.Item(name="X", kind="rss", ref="https://x/feed nosuchthing")
    res, reason = sources.check_with_reason(
        item, _no_json, http_text=lambda u: _RSS_FEED)
    assert res is None and reason == sources.NOT_FOUND


def test_a_successful_check_has_no_reason():
    item = catalog.Item(name="X", kind="rss", ref="https://x/feed")
    res, reason = sources.check_with_reason(
        item, _no_json, http_text=lambda u: _RSS_FEED)
    assert res is not None and reason == ""


def test_manual_items_are_never_an_error():
    res, reason = sources.check_with_reason(catalog.Item(name="M", kind="manual"))
    assert res is None and reason == ""


def test_a_provider_that_raises_reads_as_unreachable():
    def boom(url):
        raise RuntimeError("kaboom")

    item = catalog.Item(name="X", kind="arch", ref="plasma-desktop")
    res, reason = sources.check_with_reason(item, boom)
    assert res is None and reason == sources.UNREACHABLE


# ── flatpak ──────────────────────────────────────────────────────────────────

_FLATHUB = {"flathub.org/api/v2/appstream/org.videolan.VLC": {
    "name": "VLC",
    "releases": [
        {"version": "3.0.22", "timestamp": "1750000000", "type": "stable"},
        {"version": "4.0.0-dev", "timestamp": "1790000000", "type": "development"},
        {"version": "3.0.23", "timestamp": "1767225600", "type": "stable",
         "url": "https://vlc/news/3.0.23"},
    ]}}


def test_flatpak_takes_the_newest_STABLE_not_the_newest_overall():
    """A development build is newer by timestamp — promoting the user onto it
    would misrepresent 'latest', the same trap _github avoids with pre-releases."""
    item = catalog.Item(name="VLC", kind="flatpak", ref="org.videolan.VLC")
    res = sources.check(item, _fake(_FLATHUB))
    assert res.latest == "3.0.23"
    assert res.url == "https://vlc/news/3.0.23"
    assert res.date == "2026-01-01"


def test_flatpak_falls_back_to_the_flathub_page_without_a_release_url():
    data = {"flathub.org/api/v2/appstream/org.kde.krita": {
        "releases": [{"version": "5.3.2", "timestamp": "1767225600", "type": "stable"}]}}
    item = catalog.Item(name="Krita", kind="flatpak", ref="org.kde.krita")
    res = sources.check(item, _fake(data))
    assert res.url == "https://flathub.org/apps/org.kde.krita"


def test_flatpak_uses_development_only_when_there_is_no_stable():
    data = {"flathub.org/api/v2/appstream/x.y": {
        "releases": [{"version": "0.9-beta", "timestamp": "1767225600",
                      "type": "development"}]}}
    res = sources.check(catalog.Item(name="X", kind="flatpak", ref="x.y"), _fake(data))
    assert res.latest == "0.9-beta"


def test_flatpak_with_no_releases_is_not_found():
    data = {"flathub.org/api/v2/appstream/x.y": {"name": "X", "releases": []}}
    res, reason = sources.check_with_reason(
        catalog.Item(name="X", kind="flatpak", ref="x.y"), _fake(data))
    assert res is None and reason == sources.NOT_FOUND


def test_flatpak_survives_a_junk_timestamp():
    data = {"flathub.org/api/v2/appstream/x.y": {
        "releases": [{"version": "1.0", "timestamp": "not-a-number", "type": "stable"}]}}
    res = sources.check(catalog.Item(name="X", kind="flatpak", ref="x.y"), _fake(data))
    assert res.latest == "1.0" and res.date == ""


def test_flatpak_rejects_a_ref_that_is_not_an_app_id():
    item = catalog.Item(name="X", kind="flatpak", ref="owner/repo")
    assert sources.check(item, _fake({})) is None
