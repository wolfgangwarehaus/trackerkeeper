"""The source providers — the checkers that turn a tracked item into "what's
the latest version, and where's the changelog."

The whole product thesis lives here: there is no single "latest version" API,
so Tracker Keeper IS the uniform layer. Each provider is a small function
``(item, http) -> CheckResult | None`` for one KIND of source; growing coverage
is adding providers, one world at a time (github, arch today; rss, flatpak,
store pages next; firmware feeds later).

Network I/O goes through a single injected ``http`` seam (:func:`http_json`),
so every provider is unit-testable with a fake — no test touches the network,
exactly like ``deliver``'s detection probes.
"""

from __future__ import annotations

import json
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
    date: str = ""


def http_json(url: str) -> dict | None:
    """GET ``url`` and parse JSON, or None on any failure (offline, 404, rate
    limit, malformed). Sends a User-Agent — GitHub rejects requests without one.
    The single network seam: providers call it, tests replace it."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                                   "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


# ── the providers ────────────────────────────────────────────────────────────


def _github(item, http) -> CheckResult | None:
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
    return CheckResult(
        latest=str(tag).lstrip("vV") if str(tag)[:1] in "vV" else str(tag),
        url=data.get("html_url", "") or item.changelog_url,
        date=(data.get("published_at") or "")[:10],
    )


def _arch(item, http) -> CheckResult | None:
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
    return CheckResult(
        latest=f"{ver}-{rel}" if ver and rel else ver,
        url=f"https://archlinux.org/packages/{r.get('repo','')}/{r.get('arch','')}/{item.ref}/",
        date=(r.get("last_update") or "")[:10],
    )


def _manual(item, http) -> CheckResult | None:
    """A manual item has no source to poll — you set ``installed`` yourself.
    Returns None so a refresh leaves it untouched (never an error, never a
    fabricated 'latest')."""
    return None


_PROVIDERS = {
    "github": _github,
    "arch": _arch,
    "manual": _manual,
}


def check(item, http=http_json) -> CheckResult | None:
    """Run ``item``'s provider. Unknown kind or manual → None. Never raises: a
    provider that throws is swallowed to None so one bad item can't sink a
    whole refresh (the dashboard shows it as 'couldn't check')."""
    provider = _PROVIDERS.get(item.kind)
    if provider is None:
        return None
    try:
        return provider(item, http)
    except Exception:
        return None
