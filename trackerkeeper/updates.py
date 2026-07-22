"""In-app update check — tells a user on a MANUAL install channel when a newer
release is out, and stays silent on auto-updating ones.

Once per day (throttled via a stored timestamp), on a background HTTP GET through
``async_io.get_qnam()`` (never a raw thread), the app asks GitHub for the latest
*published* release of its repo — resolved from the metadata sidecar
(``github_owner`` / ``repo_name``), falling back to the identity seam, so a fork
checks ITS releases with zero edits here. If it's newer than
``trackerkeeper.__version__`` — and the user hasn't dismissed that exact version — it
fires ``AppBus.update_available`` so the top-bar chip (``update_chip.py``) can
offer Download + What's-new.

Channel-aware (the load-bearing rule): we only nag where the user updates BY HAND
(.dmg / .deb / AppImage / installer / portable / source). On the auto-updating
channels — Microsoft Store (MSIX), Mac App Store, AUR — the package manager owns
updates, so pointing the user at a manual installer would be wrong; those are
suppressed. Store / MAS are detected at runtime; the rest read the build/launcher
stamp (the ``TRACKERKEEPER_CHANNEL`` env var, default ``"source"`` → checks ON, the safe
direction — a store package sets ``TRACKERKEEPER_CHANNEL=msix``/``aur``/… to disable).

The check hits GitHub's public, unauthenticated API (no account, no PII) and can
be turned off in Settings (``check_for_updates``).
"""

from __future__ import annotations

import json
import logging
import os
import time

from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest

from trackerkeeper import __version__
from trackerkeeper.async_io import get_qnam
from trackerkeeper.platform_compat import is_macos_sandboxed, is_msix_packaged

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_S = 24 * 60 * 60  # once per day

# Channels whose updates are handled by a store / package manager — never nag
# them (an in-app "download the installer" would install a conflicting copy).
_AUTO_CHANNELS = frozenset({"msix", "mas", "aur"})


def _repo() -> tuple[str, str]:
    """(owner, repo) for the release check — the metadata sidecar when running
    from a checkout, the identity seam otherwise. Never raises."""
    try:
        from trackerkeeper import metadata

        meta = metadata.load()
        return meta["github_owner"], meta["repo_name"]
    except Exception:
        from trackerkeeper import identity

        return identity.owner(), identity.app()


def _releases_api() -> str:
    owner, repo = _repo()
    return f"https://api.github.com/repos/{owner}/{repo}/releases/latest"


def _releases_page() -> str:
    owner, repo = _repo()
    return f"https://github.com/{owner}/{repo}/releases/latest"


def get_channel() -> str:
    """How this copy was installed. Runtime probes (Store / Mac App Store) win
    over the env stamp, since they're unambiguous; everything else falls back
    to ``TRACKERKEEPER_CHANNEL`` (default ``"source"``). Never raises."""
    try:
        if is_msix_packaged():
            return "msix"
        if is_macos_sandboxed():
            return "mas"
    except Exception:
        pass
    return (os.environ.get("TRACKERKEEPER_CHANNEL") or "").strip().lower() or "source"


def is_auto_update_channel() -> bool:
    """True on channels that update themselves (Store / MAS / AUR) — where the
    in-app update nag should stay silent."""
    return get_channel() in _AUTO_CHANNELS


def _version_tuple(v: str) -> tuple[int, ...]:
    """Parse a ``"0.1.5"`` / ``"v0.1.5"`` version into a comparable int tuple.
    Best-effort: a non-numeric chunk contributes its leading digits (or 0)."""
    parts = []
    for chunk in str(v).lstrip("vV").split("."):
        digits = ""
        for c in chunk:
            if c.isdigit():
                digits += c
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(candidate: str, current: str = __version__) -> bool:
    """True iff ``candidate`` is a strictly newer version than ``current``."""
    return _version_tuple(candidate) > _version_tuple(current)


def should_check() -> bool:
    """Whether to run the check at all: the user setting is on AND this isn't an
    auto-updating channel."""
    from trackerkeeper.settings import get_settings

    try:
        if not get_settings().check_for_updates:
            return False
    except Exception:
        pass
    return not is_auto_update_channel()


def _pick_download_url(assets: list, channel: str, html_url: str) -> str:
    """Deep-link the release asset matching this OS/arch/channel; fall back to
    the releases page when there's no clean match (source / pip / unknown asset
    name) so the user can still pick."""
    import platform

    machine = platform.machine().lower()
    needle = None
    if channel == "dmg":
        needle = "arm64.dmg" if machine in ("arm64", "aarch64") else "x86_64.dmg"
    elif channel == "deb":
        needle = ".deb"
    elif channel == "appimage":
        needle = ".appimage"
    elif channel == "portable":
        needle = "portable"
    elif channel == "inno":
        needle = "setup.exe"
    if needle:
        for a in assets:
            name = (a.get("name") or "").lower()
            url = a.get("browser_download_url")
            if url and needle in name:
                return url
    return html_url


def maybe_check(force: bool = False) -> None:
    """Run the update check if due (gated by channel + the user setting, and
    throttled to once per day). ``force=True`` skips the gate/throttle for a
    manual "Check now". Fires ``AppBus.update_available(version, download_url,
    notes_url)`` on success. Background + best-effort; never raises.

    Must be called after the QApplication exists (uses the shared QNAM)."""
    from trackerkeeper.settings import get_settings

    # The channel gate ALWAYS applies — a self-updating build (Store / MAS / AUR)
    # is never checked, even on a manual "Check now".
    if is_auto_update_channel():
        return
    s = get_settings()
    if not force:
        # Automatic check: also respect the user toggle + the daily throttle.
        if not s.check_for_updates:
            return
        if (int(time.time()) - s.update_last_check_time) < _CHECK_INTERVAL_S:
            return
    s.update_last_check_time = int(time.time())
    try:
        from trackerkeeper import identity

        req = QNetworkRequest(QUrl(_releases_api()))
        # GitHub's API rejects requests with no User-Agent (HTTP 403).
        req.setRawHeader(b"User-Agent", f"{identity.app()}/{__version__}".encode())
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setTransferTimeout(10000)
        reply = get_qnam().get(req)
        reply.finished.connect(lambda r=reply: _on_finished(r, force))
    except Exception as e:
        logger.debug("update check failed to start: %s", e)


def _on_finished(reply: QNetworkReply, force: bool) -> None:
    """Parse the releases/latest response on the GUI thread; emit
    ``update_available`` if there's a newer, non-dismissed release."""
    try:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            logger.debug("update check: %s", reply.errorString())
            return
        data = json.loads(bytes(reply.readAll()).decode("utf-8", "replace"))
        tag = (data.get("tag_name") or "").lstrip("vV").strip()
        if not tag or not is_newer(tag):
            return  # missing / up to date
        from trackerkeeper.settings import get_settings

        # A user "Check now" should surface even a previously-dismissed version.
        if not force and tag == get_settings().update_dismissed_version:
            return
        html_url = data.get("html_url") or _releases_page()
        download_url = _pick_download_url(data.get("assets") or [], get_channel(), html_url)

        from trackerkeeper.bus import AppBus

        AppBus.get().update_available.emit(tag, download_url, html_url)
        logger.info("update available: %s (running %s)", tag, __version__)
    except Exception as e:
        logger.debug("update check parse failed: %s", e)
    finally:
        try:
            reply.deleteLater()
        except Exception:
            pass
