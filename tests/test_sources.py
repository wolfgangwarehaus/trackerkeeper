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
