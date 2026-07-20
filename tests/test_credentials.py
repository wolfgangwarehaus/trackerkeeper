"""dough.credentials — the named-secret store: dual-store with an
AES-GCM-encrypted QSettings fallback, opportunistic backfill /
legacy-plaintext upgrade, and graceful behavior when the wallet is unusable.

Adapted from jellytoast's test_access_token.py to the generic
save_secret/load_secret/delete_secret API. The QSettings backend is a
throwaway INI under tmp_path (via a monkeypatched ``_qsettings``); the
keyring stand-in patches ``_keyring_get`` / ``_keyring_set`` directly, so the
user's real wallet is never touched.

Storage model:
    Primary:    OS keyring (mocked here).
    Resilience: QSettings ``credentials/<name>`` holds an AES-GCM blob with
                a ``v1:`` version prefix (``d1:`` DPAPI on Windows).
                Plaintext only on legacy installs, detected and upgraded
                forward on first read.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from dough import credentials as cred
from dough.credentials import _ENC_PREFIX, _decrypt, _encrypt


class _FakeKeyring:
    """Stand-in for the python-keyring backend so tests don't poke the
    user's real wallet."""

    def __init__(self):
        self.store: dict = {}
        self.fail_get = False
        self.fail_set = False

    def get(self, name, *args, **kwargs):
        if self.fail_get:
            return None
        return self.store.get(name)

    def set(self, name: str, value: str) -> bool:
        if self.fail_set:
            return False
        if value:
            self.store[name] = value
        else:
            self.store.pop(name, None)
        return True


@pytest.fixture()
def fake_keyring(monkeypatch):
    fake = _FakeKeyring()
    monkeypatch.setattr(cred, "_keyring_get", fake.get)
    monkeypatch.setattr(cred, "_keyring_set", fake.set)
    return fake


@pytest.fixture()
def qs(tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "store.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(cred, "_qsettings", lambda: settings)
    return settings


# ── encryption primitives ─────────────────────────────────────────────


def test_encrypt_decrypt_round_trip():
    blob = _encrypt("hunter2")
    assert blob.startswith(_ENC_PREFIX)
    # Ciphertext should be different on every call (random nonce).
    assert _encrypt("hunter2") != blob
    # But both decrypt to the original plaintext.
    assert _decrypt(blob) == "hunter2"


def test_encrypt_empty_returns_empty():
    assert _encrypt("") == ""
    assert _decrypt("") == ""


def test_decrypt_legacy_plaintext_passes_through():
    # Pre-v1 stored values (no prefix) are returned as-is so the
    # caller can re-encrypt them forward.
    assert _decrypt("legacy-plaintext-secret") == "legacy-plaintext-secret"


def test_decrypt_corrupted_blob_returns_empty():
    # A v1 blob that fails AES-GCM auth (tampered ciphertext, wrong
    # key, …) should not surface gibberish — return empty so callers
    # treat it as "no credential".
    bad = _ENC_PREFIX + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
    assert _decrypt(bad) == ""


def test_entropy_is_identity_routed(monkeypatch):
    from dough import identity

    before = cred._entropy()
    monkeypatch.setattr(identity, "_app", "someloaf")
    assert cred._entropy() != before
    assert b"someloaf" in cred._entropy()


# ── Windows DPAPI migration (cryptography absent on Windows) ──────────
# On Windows the resilience cipher is DPAPI ("d1:") and cryptography is
# absent, so "v1:" AES-GCM blobs are undecryptable there. These simulate that
# runtime on the Linux box (patch IS_WINDOWS + a fake DPAPI layer + the
# platform prefix) to lock the migration behavior.


def _fake_dpapi():
    """Reversible CryptProtectData/CryptUnprotectData stand-in; the marker
    carries a NUL to exercise the binary-safe path."""

    def protect(pt: bytes) -> bytes:
        return b"D\x00P" + pt

    def unprotect(ct: bytes) -> bytes:
        return ct[3:]

    return protect, unprotect


def _simulate_windows(monkeypatch):
    monkeypatch.setattr(cred, "IS_WINDOWS", True)
    monkeypatch.setattr(cred, "_dpapi_fns", _fake_dpapi(), raising=False)
    monkeypatch.setattr(cred, "_ENC_PREFIX", "d1:")


def test_windows_secret_self_heals_via_keyring(qs, fake_keyring, monkeypatch):
    # Existing Windows install: a real v1 AES-GCM blob in QSettings + the
    # secret in Credential Locker. The v1 blob is unreadable there, but
    # keyring carries the secret across the upgrade and the blob self-heals
    # to d1 — no re-login.
    fake_keyring.store["api_token"] = "server-token"
    v1_blob = _encrypt("server-token")  # v1 on this Linux box
    assert v1_blob.startswith("v1:")
    qs.setValue("credentials/api_token", v1_blob)

    _simulate_windows(monkeypatch)

    assert cred.load_secret("api_token") == "server-token"
    stored = qs.value("credentials/api_token", "", type=str)
    assert stored.startswith("d1:")  # rewritten forward under DPAPI
    assert stored != v1_blob
    assert _decrypt(stored) == "server-token"  # d1 decrypts under sim


def test_windows_keyringless_secret_degrades_without_corruption(
    qs, fake_keyring, monkeypatch
):
    # A secret with NO keyring copy: on the Windows upgrade its old v1 blob
    # can't be decrypted → load MUST return "" (clean one-time re-auth) and
    # MUST NOT rewrite it into a garbage d1 blob (the corruption the
    # known-prefix guard exists to prevent).
    v1_blob = _encrypt("lb-secret")
    assert v1_blob.startswith("v1:")
    qs.setValue("credentials/scrobble_token", v1_blob)

    _simulate_windows(monkeypatch)

    assert cred.load_secret("scrobble_token") == ""  # clean degrade
    # The stale blob is left untouched — never re-encrypted into a bogus value.
    assert qs.value("credentials/scrobble_token", "", type=str) == v1_blob
    # A fresh save writes a real d1 blob that round-trips.
    cred.save_secret("scrobble_token", "new-lb-token")
    assert cred.load_secret("scrobble_token") == "new-lb-token"
    assert qs.value("credentials/scrobble_token", "", type=str).startswith("d1:")


# ── dual-store contract ───────────────────────────────────────────────


def test_secret_round_trip_through_keyring(qs, fake_keyring):
    cred.save_secret("api_token", "abc123")
    assert cred.load_secret("api_token") == "abc123"
    assert fake_keyring.store == {"api_token": "abc123"}
    # QSettings holds a *ciphertext* blob with the version prefix,
    # never the plaintext.
    stored = qs.value("credentials/api_token", "", type=str)
    assert stored.startswith(_ENC_PREFIX)
    assert "abc123" not in stored
    # Round-trip through the same machine-key decrypts.
    assert _decrypt(stored) == "abc123"


def test_save_writes_both_stores(qs, fake_keyring):
    qs.setValue("credentials/api_token", "stale")
    cred.save_secret("api_token", "fresh")
    assert fake_keyring.store == {"api_token": "fresh"}
    stored = qs.value("credentials/api_token", "", type=str)
    assert stored.startswith(_ENC_PREFIX)
    assert _decrypt(stored) == "fresh"


def test_keyring_read_backfills_qsettings(qs, fake_keyring):
    # Existing install whose QSettings copy was wiped: backfill on first
    # read so the next boot has the resilience floor in place.
    fake_keyring.store["api_token"] = "in-keyring-only"
    qs.remove("credentials/api_token")
    assert cred.load_secret("api_token") == "in-keyring-only"
    stored = qs.value("credentials/api_token", "", type=str)
    assert stored.startswith(_ENC_PREFIX)
    assert _decrypt(stored) == "in-keyring-only"


def test_legacy_plaintext_upgrades_on_read_via_fallback(qs, fake_keyring):
    # Pre-encryption install with a broken keyring: the fallback path should
    # return the legacy plaintext value AND re-encrypt it forward so
    # subsequent reads no longer have plaintext on disk.
    fake_keyring.fail_get = True
    qs.setValue("credentials/api_token", "legacy-secret")
    assert cred.load_secret("api_token") == "legacy-secret"
    stored = qs.value("credentials/api_token", "", type=str)
    assert stored.startswith(_ENC_PREFIX)
    assert _decrypt(stored) == "legacy-secret"


def test_keyring_miss_returns_decrypted_qsettings(qs, fake_keyring):
    # Steady-state for users on systems with no keyring: stored blob
    # is encrypted, read decrypts it, plaintext is never on disk.
    fake_keyring.fail_get = True
    qs.setValue("credentials/api_token", _encrypt("encrypted-secret"))
    assert cred.load_secret("api_token") == "encrypted-secret"


def test_save_persists_qsettings_when_keyring_broken(qs, fake_keyring):
    # Keyring write fails (no backend). The QSettings encrypted copy
    # still gets written so the app stays usable.
    fake_keyring.fail_set = True
    cred.save_secret("api_token", "fallback")
    assert fake_keyring.store == {}
    stored = qs.value("credentials/api_token", "", type=str)
    assert stored.startswith(_ENC_PREFIX)
    # And reading via the fallback path round-trips correctly.
    fake_keyring.fail_get = True
    assert cred.load_secret("api_token") == "fallback"


def test_saving_empty_clears_both_stores(qs, fake_keyring):
    cred.save_secret("api_token", "to-clear")
    cred.save_secret("api_token", "")
    assert fake_keyring.store == {}
    assert qs.value("credentials/api_token", "", type=str) == ""
    assert cred.load_secret("api_token") == ""


def test_delete_secret_purges_both_stores(qs, fake_keyring):
    cred.save_secret("api_token", "active")
    cred.delete_secret("api_token")
    assert cred.load_secret("api_token") == ""
    assert fake_keyring.store == {}
    assert qs.value("credentials/api_token", "", type=str) == ""


def test_secrets_are_independent_by_name(qs, fake_keyring):
    cred.save_secret("api_token", "one")
    cred.save_secret("other_token", "two")
    cred.delete_secret("api_token")
    assert cred.load_secret("api_token") == ""
    assert cred.load_secret("other_token") == "two"
