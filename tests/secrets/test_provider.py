from __future__ import annotations

import stat
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ota_core.secrets import (
    Credential,
    CredentialExpiredError,
    CredentialNotFoundError,
    EncryptedFileSecretsProvider,
    InMemorySecretsProvider,
    InsufficientScopesError,
    SecretsProvider,
    SecretsStoreCorruptError,
)


def _cred(
    *,
    integration: str = "gmail_oauth",
    routine: str | None = None,
    scopes: tuple[str, ...] = ("email:send", "email:read", "email:list"),
    style: str = "oauth2",
    secret: dict[str, str] | None = None,
    expires_at: datetime | None = None,
) -> Credential:
    return Credential(
        integration_id=integration,
        routine_id=routine,
        style=style,  # type: ignore[arg-type]
        granted_scopes=scopes,
        secret=secret or {"access_token": "tok", "refresh_token": "ref"},
        rotated_at=datetime(2026, 5, 1, tzinfo=UTC),
        expires_at=expires_at,
    )


def test_protocol_satisfaction(tmp_path: Path) -> None:
    p: SecretsProvider = InMemorySecretsProvider()
    assert isinstance(p, SecretsProvider)


def test_store_and_fetch_unscoped() -> None:
    p = InMemorySecretsProvider()
    p.store(_cred())
    fetched = p.fetch(integration_id="gmail_oauth")
    assert fetched.secret["access_token"] == "tok"
    assert set(fetched.granted_scopes) == {"email:send", "email:read", "email:list"}


def test_fetch_narrows_scopes_to_request() -> None:
    p = InMemorySecretsProvider()
    p.store(_cred())
    fetched = p.fetch(integration_id="gmail_oauth", required_scopes=["email:send"])
    assert fetched.granted_scopes == ("email:send",)
    assert fetched.secret["access_token"] == "tok"


def test_fetch_raises_when_scope_not_granted() -> None:
    p = InMemorySecretsProvider()
    p.store(_cred(scopes=("email:read",)))
    with pytest.raises(InsufficientScopesError) as exc:
        p.fetch(integration_id="gmail_oauth", required_scopes=["email:send"])
    assert exc.value.requested == ("email:send",)
    assert exc.value.granted == ("email:read",)


def test_fetch_routine_specific_falls_back_to_shared() -> None:
    p = InMemorySecretsProvider()
    p.store(_cred(routine=None))
    fetched = p.fetch(integration_id="gmail_oauth", routine_id="email_triage")
    assert fetched.routine_id is None


def test_routine_specific_overrides_shared() -> None:
    p = InMemorySecretsProvider()
    p.store(_cred(routine=None, secret={"access_token": "shared"}))
    p.store(_cred(routine="email_triage", secret={"access_token": "routine"}))
    shared = p.fetch(integration_id="gmail_oauth")
    routine = p.fetch(integration_id="gmail_oauth", routine_id="email_triage")
    assert shared.secret["access_token"] == "shared"
    assert routine.secret["access_token"] == "routine"


def test_fetch_unknown_credential_raises() -> None:
    p = InMemorySecretsProvider()
    with pytest.raises(CredentialNotFoundError):
        p.fetch(integration_id="ghost")


def test_fetch_expired_credential_raises() -> None:
    past = datetime(2020, 1, 1, tzinfo=UTC)
    p = InMemorySecretsProvider()
    p.store(_cred(expires_at=past))
    with pytest.raises(CredentialExpiredError):
        p.fetch(integration_id="gmail_oauth")


def test_rotate_replaces_secret_and_updates_rotated_at() -> None:
    fixed = datetime(2026, 6, 1, tzinfo=UTC)
    p = InMemorySecretsProvider(clock=lambda: fixed)
    p.store(_cred())
    rotated = p.rotate(
        integration_id="gmail_oauth",
        routine_id=None,
        new_secret={"access_token": "new"},
    )
    assert rotated.secret == {"access_token": "new"}
    assert rotated.rotated_at == fixed
    assert p.fetch(integration_id="gmail_oauth").secret == {"access_token": "new"}


def test_rotate_missing_raises() -> None:
    p = InMemorySecretsProvider()
    with pytest.raises(CredentialNotFoundError):
        p.rotate(integration_id="ghost", routine_id=None, new_secret={"a": "b"})


def test_revoke_removes_only_targeted_credential() -> None:
    p = InMemorySecretsProvider()
    p.store(_cred(routine=None))
    p.store(_cred(routine="email_triage"))
    p.revoke(integration_id="gmail_oauth", routine_id="email_triage")
    assert {c.routine_id for c in p.list()} == {None}


def test_encrypted_file_round_trip(tmp_path: Path) -> None:
    key = EncryptedFileSecretsProvider.generate_key()
    path = tmp_path / "secrets.enc"
    provider = EncryptedFileSecretsProvider(path, key=key)
    provider.store(_cred())
    assert path.exists()

    # New provider with same key sees the credential
    provider2 = EncryptedFileSecretsProvider(path, key=key)
    fetched = provider2.fetch(integration_id="gmail_oauth")
    assert fetched.secret["access_token"] == "tok"


def test_encrypted_file_wrong_key_raises(tmp_path: Path) -> None:
    key = EncryptedFileSecretsProvider.generate_key()
    other = EncryptedFileSecretsProvider.generate_key()
    path = tmp_path / "secrets.enc"
    provider = EncryptedFileSecretsProvider(path, key=key)
    provider.store(_cred())
    with pytest.raises(SecretsStoreCorruptError):
        EncryptedFileSecretsProvider(path, key=other)


def test_encrypted_file_file_permissions_are_locked_down(tmp_path: Path) -> None:
    if sys.platform.startswith("win"):
        pytest.skip("POSIX permissions not applicable on Windows")
    key = EncryptedFileSecretsProvider.generate_key()
    path = tmp_path / "secrets.enc"
    provider = EncryptedFileSecretsProvider(path, key=key)
    provider.store(_cred())
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_encrypted_file_atomic_replace(tmp_path: Path) -> None:
    key = EncryptedFileSecretsProvider.generate_key()
    path = tmp_path / "secrets.enc"
    provider = EncryptedFileSecretsProvider(path, key=key)
    provider.store(_cred())
    provider.store(_cred(routine="email_triage"))
    # Temp file should not linger after store
    assert not (tmp_path / "secrets.enc.tmp").exists()


def test_encrypted_file_reload_picks_up_external_edits(tmp_path: Path) -> None:
    key = EncryptedFileSecretsProvider.generate_key()
    path = tmp_path / "secrets.enc"
    a = EncryptedFileSecretsProvider(path, key=key)
    b = EncryptedFileSecretsProvider(path, key=key)
    a.store(_cred(routine="email_triage"))
    with pytest.raises(CredentialNotFoundError):
        b.fetch(integration_id="gmail_oauth", routine_id="email_triage")
    b.reload()
    assert b.fetch(integration_id="gmail_oauth", routine_id="email_triage") is not None


def test_no_required_scopes_returns_full_credential() -> None:
    p = InMemorySecretsProvider()
    p.store(_cred())
    fetched = p.fetch(integration_id="gmail_oauth")
    assert set(fetched.granted_scopes) == {"email:send", "email:read", "email:list"}


def test_credential_dataclass_is_frozen() -> None:
    c = _cred()
    with pytest.raises((AttributeError, Exception)):
        c.routine_id = "x"  # type: ignore[misc]


def test_expired_check_uses_injected_clock() -> None:
    fixed_now = datetime(2030, 1, 1, tzinfo=UTC)
    p = InMemorySecretsProvider(clock=lambda: fixed_now)
    p.store(_cred(expires_at=datetime(2026, 1, 1, tzinfo=UTC)))
    with pytest.raises(CredentialExpiredError):
        p.fetch(integration_id="gmail_oauth")

    # Not yet expired
    p2 = InMemorySecretsProvider(clock=lambda: datetime(2025, 6, 1, tzinfo=UTC))
    p2.store(_cred(expires_at=datetime(2026, 1, 1, tzinfo=UTC)))
    assert p2.fetch(integration_id="gmail_oauth") is not None


def test_encrypted_file_with_string_key(tmp_path: Path) -> None:
    key = EncryptedFileSecretsProvider.generate_key().decode("ascii")
    path = tmp_path / "secrets.enc"
    provider = EncryptedFileSecretsProvider(path, key=key)
    provider.store(_cred())
    again = EncryptedFileSecretsProvider(path, key=key)
    assert again.fetch(integration_id="gmail_oauth").secret == {
        "access_token": "tok",
        "refresh_token": "ref",
    }
