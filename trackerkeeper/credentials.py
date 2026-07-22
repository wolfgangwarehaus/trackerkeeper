"""Named-secret store — keyring primary, encrypted-QSettings resilience copy.

Genericized from jellytoast's access-token credential layer (the
security-critical crypto reads in isolation there for the same reason). Two
stores back every secret:

  Primary:    the OS secret store via python-keyring — encrypted at rest,
              OS-managed. Service name = ``identity.app()`` (the identity
              seam), username = the secret's ``name``.
  Resilience: an encrypted blob in the app's QSettings under
              ``credentials/<name>``. Two ciphers by platform:
                • Linux/macOS — AES-GCM keyed by ``_machine_key`` (PBKDF2 over
                  /etc/machine-id + $USER), prefix ``v1:``. Needs cryptography.
                • Windows — OS-native DPAPI (``CryptProtectData`` via ctypes),
                  prefix ``d1:``. Needs NO cryptography, so a Windows build
                  carries no cryptography dep (it has no win_arm64 wheel — a
                  hard blocker for native ARM64 Windows). Bound to the current
                  user + a fixed app-entropy domain separator.
              Either way a stolen config file alone can't be decrypted off the
              originating machine/user. This is defense-in-depth on top of the
              OS keyring, not the primary secret.

Public API — generic named secrets, not a hardwired token::

    from trackerkeeper import credentials
    credentials.save_secret("api_token", value)   # "" deletes
    credentials.load_secret("api_token")          # "" when absent
    credentials.delete_secret("api_token")

``keyring`` (and, off Windows, ``cryptography``) are OPTIONAL — imports are
lazy and every path degrades: no keyring ⇒ the encrypted QSettings copy is
authoritative; no cryptography off Windows ⇒ secrets simply don't persist
(never written plaintext). Core stays PySide6-only.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from trackerkeeper.platform_compat import IS_WINDOWS

logger = logging.getLogger(__name__)


def _keyring_service() -> str:
    """The keyring service name, off the identity seam — a fork's secrets are
    filed under ITS slug with zero edits here."""
    from trackerkeeper import identity

    return identity.app()


def _entropy() -> bytes:
    """The fixed, non-secret domain separator: DPAPI optional entropy AND the
    AES-GCM PBKDF2 salt. Identity-routed so two trackerkeeper forks on one machine
    can't unprotect each other's blobs. A separator, not a key — shipping it
    in the binary is fine."""
    from trackerkeeper import identity

    return f"{identity.app()}/credentials/v1".encode("utf-8")


# Warn at most once per process when the OS keyring backend is missing — a
# no-backend box (e.g. a fresh pipx box with no Secret Service) would otherwise
# log the verbose backend error on every read.
_KEYRING_WARNED = False

# Version prefixes on the QSettings secret blob — one per cipher family.
# A value that starts with NEITHER is legacy plaintext; we detect and
# re-encrypt on first read so existing installs upgrade silently. A value under
# a prefix we recognise but can't decrypt on THIS platform (a ``v1:`` AES-GCM
# blob on Windows, where cryptography is gone) decrypts to "" — never handed
# back raw, which the re-encrypt-forward path would corrupt into a bogus value.
_ENC_PREFIX_AESGCM = "v1:"  # PBKDF2 + AES-GCM (cryptography) — Linux/macOS
_ENC_PREFIX_DPAPI = "d1:"  # Windows DPAPI (CryptProtectData) — no cryptography
# The prefix NEW writes use on this platform. The self-heal guard in
# load_secret tests ``stored.startswith(_ENC_PREFIX)`` to decide "is the blob
# already in the current format?" — so on Windows this is ``d1:`` and an old
# ``v1:`` blob reads as needing a rewrite forward.
_ENC_PREFIX = _ENC_PREFIX_DPAPI if IS_WINDOWS else _ENC_PREFIX_AESGCM
_KNOWN_PREFIXES = (_ENC_PREFIX_AESGCM, _ENC_PREFIX_DPAPI)

_CRYPTPROTECT_UI_FORBIDDEN = 0x01  # never raise a UI prompt (safe on bg threads)
_dpapi_fns: Optional[tuple] = None  # cached (protect, unprotect) after first load


def _load_dpapi() -> tuple:
    """Lazily bind crypt32 ``CryptProtectData`` / ``CryptUnprotectData``.
    Windows-only — importing this module on Linux/macOS never touches
    ``ctypes.WinDLL`` (which doesn't exist there). Cached after first call."""
    global _dpapi_fns
    if _dpapi_fns is not None:
        return _dpapi_fns
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        # POINTER(c_char), NOT c_char_p: DPAPI ciphertext has embedded NULs, and
        # c_char_p would truncate at the first one.
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # .argtypes/.restype are MANDATORY on win_arm64 / win64 — without them
    # ctypes assumes 32-bit and TRUNCATES the returned 64-bit pbData pointer.
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),  # pDataIn
        wintypes.LPCWSTR,  # szDataDescr (NULL)
        ctypes.POINTER(DATA_BLOB),  # pOptionalEntropy
        ctypes.c_void_p,  # pvReserved (NULL)
        ctypes.c_void_p,  # pPromptStruct (NULL)
        wintypes.DWORD,  # dwFlags
        ctypes.POINTER(DATA_BLOB),  # pDataOut
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),  # pDataIn
        ctypes.POINTER(wintypes.LPWSTR),  # ppszDataDescr (NULL)
        ctypes.POINTER(DATA_BLOB),  # pOptionalEntropy
        ctypes.c_void_p,  # pvReserved (NULL)
        ctypes.c_void_p,  # pPromptStruct (NULL)
        wintypes.DWORD,  # dwFlags
        ctypes.POINTER(DATA_BLOB),  # pDataOut
    ]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]

    def _blob_in(data: bytes):
        # from_buffer_copy is valid for len 0 too; the caller keeps `buf` alive.
        buf = (ctypes.c_char * len(data)).from_buffer_copy(data)
        blob = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        return blob, buf

    def _call(fn, data: bytes) -> bytes:
        in_blob, _in = _blob_in(data)
        ent_blob, _ent = _blob_in(_entropy())  # identical on protect+unprotect
        out = DATA_BLOB()
        ok = fn(
            ctypes.byref(in_blob),
            None,
            ctypes.byref(ent_blob),
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(out),
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            # string_at copies exactly cbData bytes (keeps embedded NULs).
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            if out.pbData:
                kernel32.LocalFree(ctypes.cast(out.pbData, wintypes.HLOCAL))

    def protect(plaintext: bytes) -> bytes:
        return _call(crypt32.CryptProtectData, plaintext)

    def unprotect(ciphertext: bytes) -> bytes:
        return _call(crypt32.CryptUnprotectData, ciphertext)

    _dpapi_fns = (protect, unprotect)
    return _dpapi_fns


def _machine_key() -> bytes:
    """Derive a 32-byte AES key from a per-machine id + username. Stable
    across reboots; specific to this user on this machine. The key
    isn't stored anywhere — it's recomputed on each encrypt/decrypt
    so a stolen QSettings file alone (without the machine-id and
    matching username) can't be decrypted.

    PBKDF2 with a fixed salt — the salt isn't a secret here, just a
    domain separator so this key isn't reusable for anything else
    if someone composes the same machine-id+user input differently."""
    import getpass
    import hashlib
    import socket

    mid = ""
    # Linux: /etc/machine-id is the canonical stable per-install id.
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path, encoding="utf-8") as f:
                mid = f.read().strip()
                break
        except OSError:
            continue
    if not mid and IS_WINDOWS:
        # Windows: HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid is
        # the stable equivalent. Reading via winreg avoids a pywin32
        # dep. Falls through to hostname-based on access denial.
        try:
            import winreg  # type: ignore[import-not-found]

            # winreg is a Windows-only stdlib module; mypy on Linux/CI can't
            # resolve its attributes, so route access through an Any alias.
            _wr: Any = winreg
            with _wr.OpenKey(
                _wr.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
            ) as k:
                mid, _ = _wr.QueryValueEx(k, "MachineGuid")
        except Exception:
            pass
    if not mid:
        # Containers / minimal installs / other OSes — fall back to
        # hostname + username. Weaker (hostname is shareable) but
        # still deterministic on a given machine and prevents leaking
        # plaintext into the config file.
        mid = f"{socket.gethostname()}:{getpass.getuser()}"
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown"
    return hashlib.pbkdf2_hmac(
        "sha256",
        (mid + ":" + user).encode("utf-8"),
        _entropy(),
        100_000,
    )


def _encrypt(plaintext: str) -> str:
    """Encrypt with the platform resilience cipher: Windows → DPAPI
    (``d1:<base64>``), everywhere else → PBKDF2 + AES-GCM
    (``v1:<base64(nonce||ciphertext||tag)>``). Empty input → empty string.
    Encryption failure → empty string (never plaintext — that would defeat
    the whole point)."""
    if not plaintext:
        return ""
    try:
        import base64

        if IS_WINDOWS:
            protect, _ = _load_dpapi()
            blob = protect(plaintext.encode("utf-8"))
            return _ENC_PREFIX_DPAPI + base64.b64encode(blob).decode("ascii")
        # Non-Windows: PBKDF2 + AES-GCM. The cryptography import stays strictly
        # inside this branch so a Windows build (which ships no cryptography)
        # never references the absent module.
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = _machine_key()
        aes = AESGCM(key)
        nonce = os.urandom(12)  # AES-GCM standard nonce size
        ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
        return _ENC_PREFIX_AESGCM + base64.b64encode(nonce + ct).decode("ascii")
    except Exception as e:
        logger.warning("secret encryption failed: %s", e)
        return ""


def _decrypt(value: str) -> str:
    """Decrypt a stored secret blob → plaintext, or '' on failure.

    A value under a prefix we DON'T recognise is genuine legacy plaintext
    (pre-encryption) and returned as-is for the caller to re-encrypt forward.
    A value under a known prefix we CAN'T decrypt on this platform (a ``v1:``
    AES-GCM blob on Windows, where cryptography is gone; or a ``d1:`` DPAPI
    blob off Windows) returns '' — never the raw blob, which the caller's
    re-encrypt-forward path would otherwise corrupt into a bogus secret."""
    if not value:
        return ""
    if not value.startswith(_KNOWN_PREFIXES):
        return value  # legacy plaintext, will be re-encrypted on next write
    try:
        import base64

        if value.startswith(_ENC_PREFIX_DPAPI):
            if not IS_WINDOWS:
                return ""  # a DPAPI blob on a non-Windows box — unreadable here
            _, unprotect = _load_dpapi()
            raw = base64.b64decode(value[len(_ENC_PREFIX_DPAPI) :].encode("ascii"))
            return unprotect(raw).decode("utf-8")
        # v1: AES-GCM.
        if IS_WINDOWS:
            # cryptography is absent on Windows — degrade to '' so the secret
            # falls back to keyring or a clean re-auth rather than being
            # handed back raw.
            return ""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        blob = base64.b64decode(value[len(_ENC_PREFIX_AESGCM) :].encode("ascii"))
        nonce, ct = blob[:12], blob[12:]
        key = _machine_key()
        aes = AESGCM(key)
        return aes.decrypt(nonce, ct, None).decode("utf-8")
    except Exception as e:
        logger.warning("secret decryption failed: %s", e)
        return ""


def warm_keyring_async() -> None:
    """Fire a throwaway keyring read on a background thread so the
    OS secret service starts coming online while the rest of the app
    constructs. KDE Wayland's kwalletd6 in particular can take 8-10
    seconds to register on the bus after Plasma start, and during
    that window every `keyring.get_password` returns None. Kicking a
    no-op read early shifts that warm-up onto the boot timeline rather
    than blocking the first real secret read.

    Idempotent — only fires once per process. Daemon thread so a
    hung secret-service can't keep the app from exiting."""
    if getattr(warm_keyring_async, "_started", False):
        return
    warm_keyring_async._started = True  # type: ignore[attr-defined]
    import threading

    def _warm():
        try:
            import keyring

            keyring.get_password(_keyring_service(), "warmup")
        except Exception:
            pass

    threading.Thread(target=_warm, daemon=True).start()


def _keyring_get(name: str, max_attempts: int = 5, interval_s: float = 0.1) -> Optional[str]:
    """Read a secret from the desktop secret store. Returns None if keyring
    isn't installed, no backend is available, or the entry doesn't exist yet.

    KDE Wayland's secret service can race app launch — a get_password
    call moments after process start can return None even when the
    entry is present, because the backend hasn't finished registering
    yet. We retry several times with short sleeps before giving up.

    Defaults: 5 × 100ms = 500ms worst-case stall on the calling
    thread. Acceptable in practice because the dual-store design
    means a keyring miss falls through to the encrypted-file copy
    immediately — the user-visible cost is bounded by this read,
    not by a long retry budget."""
    try:
        import keyring  # lazy: avoids a hard dependency at import time
    except Exception:
        return None
    import time

    last_error = None
    for attempt in range(max_attempts):
        try:
            v = keyring.get_password(_keyring_service(), name)
        except Exception as e:
            last_error = e
            v = None
        if v:
            if attempt > 0:
                logger.info(
                    "keyring read succeeded on attempt %s (~%.1fs wait)",
                    attempt + 1,
                    attempt * interval_s,
                )
            return v
        if attempt < max_attempts - 1:
            time.sleep(interval_s)
    # Real backend exceptions (e.g. wallet locked, D-Bus disconnect) are worth
    # surfacing once. A plain "no value" after the retry budget is *expected*
    # under the dual-store design — the encrypted-file fallback absorbs it —
    # so stay quiet on the silent-empty path.
    if last_error is not None:
        global _KEYRING_WARNED
        if not _KEYRING_WARNED:
            _KEYRING_WARNED = True
            # Benign on a no-backend box (the encrypted file is authoritative),
            # so INFO not WARNING, once, and the verbose backend text at DEBUG.
            logger.info("OS keyring unavailable; using the encrypted credential store.")
            logger.debug("keyring read error: %s", last_error)
    return None


def _keyring_set(name: str, value: str) -> bool:
    """Write or clear a secret in the desktop secret store. Returns True on
    success, False if keyring isn't usable — in which case the encrypted
    QSettings copy keeps the app usable without a wallet."""
    try:
        import keyring
    except Exception:
        return False
    try:
        if value:
            keyring.set_password(_keyring_service(), name, value)
        else:
            try:
                keyring.delete_password(_keyring_service(), name)
            except Exception:
                pass  # entry already absent
        return True
    except Exception as e:
        logger.warning("keyring write failed: %s", e)
        return False


# ── the public named-secret API ──────────────────────────────────────────────


def _qsettings():
    """The resilience store — the app's own Settings handle, so blobs live in
    the same file/registry hive as everything else."""
    from trackerkeeper.settings import get_settings

    return get_settings()._s


def _blob_key(name: str) -> str:
    return f"credentials/{name}"


def save_secret(name: str, value: str) -> None:
    """Write ``value`` to both stores (keyring + encrypted QSettings blob).
    An empty ``value`` deletes the secret from both."""
    if not value:
        delete_secret(name)
        return
    _keyring_set(name, value)
    qs = _qsettings()
    blob = _encrypt(value)
    if blob:
        qs.setValue(_blob_key(name), blob)
    else:
        # Encryption unavailable (no cryptography off Windows) — never write
        # plaintext; drop the resilience copy and rely on keyring alone.
        qs.remove(_blob_key(name))
    qs.sync()


def load_secret(name: str) -> str:
    """Read a secret: keyring first, the encrypted QSettings blob as the
    fallback. Self-healing on the way through — a keyring hit backfills a
    missing/stale blob; a legacy-plaintext or old-platform-prefix blob is
    re-encrypted forward under the current cipher. Returns "" when absent."""
    qs = _qsettings()
    stored = qs.value(_blob_key(name), "", type=str) or ""
    v = _keyring_get(name)
    if v:
        # Backfill / self-heal the resilience copy when it's missing, stale,
        # or not in this platform's current blob format.
        if not stored.startswith(_ENC_PREFIX) or _decrypt(stored) != v:
            blob = _encrypt(v)
            if blob:
                qs.setValue(_blob_key(name), blob)
                qs.sync()
        return v
    if not stored:
        return ""
    plain = _decrypt(stored)
    if plain and not stored.startswith(_ENC_PREFIX):
        # Legacy plaintext (or a foreign-prefix value that still decrypted) —
        # re-encrypt forward so plaintext stops living on disk. An
        # undecryptable known-prefix blob (plain == "") is left untouched:
        # rewriting it would corrupt a value another platform could read.
        blob = _encrypt(plain)
        if blob:
            qs.setValue(_blob_key(name), blob)
            qs.sync()
    return plain


def delete_secret(name: str) -> None:
    """Remove the secret from both stores (the canonical sign-out path)."""
    _keyring_set(name, "")
    qs = _qsettings()
    qs.remove(_blob_key(name))
    qs.sync()
