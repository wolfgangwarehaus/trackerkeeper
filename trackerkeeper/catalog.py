"""The catalog — the maker's tracked fleet, and how it persists.

An :class:`Item` is one thing you watch for updates (an app, a device, a game).
It carries what you HAVE (``installed``) and what the last check FOUND
(``latest`` + date + url), so the dashboard reads offline from cache and only
the network refresh mutates the "latest" side. "There's a new update" is simply
``latest`` present and ``!= installed``.

State is a JSON file under the app data dir (``QStandardPaths.AppDataLocation``),
so it travels with the user, not the code. The path is resolved lazily and can
be overridden (tests, a portable mode) via :func:`set_catalog_path`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

# source KINDS the app knows how to check (sources.py owns the checkers). A
# manual item has no checker — you set `installed` yourself and it never fetches.
KINDS = ("github", "arch", "appstore", "cachyos", "manual")


@dataclass
class Item:
    """One tracked thing. ``kind`` picks the checker; ``ref`` is that checker's
    handle (github: ``owner/repo``; arch: the package name; manual: unused)."""

    name: str
    platform: str = ""          # freeform label: "Linux", "Steam", "iOS", "Firmware"…
    kind: str = "manual"        # one of KINDS
    ref: str = ""               # checker handle
    installed: str = ""         # the version you have / last acknowledged
    changelog_url: str = ""     # where to read what changed
    # ── last-check cache (only the refresh writes these) ──
    latest: str = ""            # newest version the source reported
    latest_url: str = ""        # release/changelog URL from the source
    latest_date: str = ""       # ISO date (YYYY-MM-DD) the latest was published
    latest_at: str = ""         # full ISO timestamp of the latest, when the source
                                # gives one — drives "N hours ago"; "" if day-only
    checked_at: str = ""        # ISO timestamp of the last successful check
    error: str = ""             # last check's error, if any (else "")

    def has_update(self) -> bool:
        """True when the source found a version you don't have yet."""
        return bool(self.latest) and self.latest != self.installed

    def sort_key(self) -> tuple:
        """Newest-update-first: items WITH an update rank above those without,
        then by the latest release date (descending), then name."""
        return (0 if self.has_update() else 1, _neg_date(self.latest_date), self.name.lower())


def _neg_date(iso: str) -> str:
    """A descending-by-date sort helper: map an ISO date to a string that sorts
    in reverse. Empty (unknown date) sorts last."""
    if not iso:
        return "0000-00-00"
    # invert each digit so lexical ascending == date descending
    return "".join(str(9 - int(c)) if c.isdigit() else c for c in iso)


_VALID = {f.name for f in fields(Item)}


def item_from_dict(d: dict) -> Item:
    """Build an Item from stored JSON, ignoring unknown keys so an older or
    newer file never crashes the load."""
    return Item(**{k: v for k, v in d.items() if k in _VALID})


# ── persistence ──────────────────────────────────────────────────────────────

_override_path: Path | None = None


def set_catalog_path(path: Path | None) -> None:
    """Pin the catalog file (tests, portable mode). None → resolve normally."""
    global _override_path
    _override_path = Path(path) if path else None


def catalog_path() -> Path:
    """The catalog JSON path — the override, else ``<AppData>/catalog.json``.
    Resolving AppData needs a QApplication with the identity names set (run_app
    does this); falls back to an XDG-style path so headless/agent use still
    works."""
    if _override_path is not None:
        return _override_path
    base = _appdata_dir()
    return base / "catalog.json"


def _appdata_dir() -> Path:
    try:
        from PySide6.QtCore import QStandardPaths

        loc = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
        if loc:
            return Path(loc)
    except Exception:
        pass
    import os

    from trackerkeeper import identity

    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    return Path(base) / identity.app()


def load() -> list[Item]:
    """The stored fleet, or the seed on first run (a missing/blank file)."""
    path = catalog_path()
    if not path.is_file():
        return default_fleet()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = [item_from_dict(d) for d in raw.get("items", [])]
        return items if items else default_fleet()
    except (json.JSONDecodeError, OSError):
        return default_fleet()


def save(items: list[Item]) -> None:
    """Write the fleet atomically (tmp + replace) so a crash mid-write never
    truncates the catalog."""
    path = catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": 1, "items": [asdict(i) for i in items]}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ── the seed: the maker's real fleet ─────────────────────────────────────────


def default_fleet() -> list[Item]:
    """tracker keeper's first run shows a REAL dashboard, not an empty box:
    August's fleet, each mapped to the best source we can check today. The auto
    ones (github/arch) fill their `latest` on the first Refresh; the manual ones
    hold what you enter until a checker for their world exists."""
    return [
        Item(name="KDE Plasma", platform="Linux", kind="arch", ref="plasma-desktop",
             changelog_url="https://kde.org/announcements/"),
        Item(name="Ghostty", platform="Terminal", kind="github", ref="ghostty-org/ghostty",
             changelog_url="https://github.com/ghostty-org/ghostty/releases"),
        Item(name="CachyOS", platform="Linux", kind="cachyos", ref="desktop",
             changelog_url="https://cachyos.org/blog/"),
        Item(name="Slay the Spire 2", platform="Steam", kind="manual", installed="",
             changelog_url="https://store.steampowered.com/news/app/2868840"),
        Item(name="SteamOS (Armada)", platform="Handheld", kind="manual", installed="",
             changelog_url="https://store.steampowered.com/steamos"),
        Item(name="iOS Developer Beta", platform="iOS", kind="manual", installed="",
             changelog_url="https://developer.apple.com/news/releases/"),
        Item(name="Blackmagic Camera", platform="iOS", kind="appstore",
             ref="6449580241", installed="3.4",
             changelog_url="https://www.blackmagicdesign.com/support/family/blackmagic-camera"),
    ]
