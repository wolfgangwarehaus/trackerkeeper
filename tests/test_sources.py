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
