from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from cryptography.fernet import Fernet, InvalidToken

from ota_core.contracts.shared import AuthStyle
from ota_core.secrets.errors import (
    CredentialExpiredError,
    CredentialNotFoundError,
    InsufficientScopesError,
    SecretsProviderError,
    SecretsStoreCorruptError,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Credential:
    integration_id: str
    routine_id: str | None
    style: AuthStyle
    granted_scopes: tuple[str, ...]
    secret: dict[str, Any] = field(default_factory=dict)
    rotated_at: datetime = field(default_factory=_utc_now)
    expires_at: datetime | None = None


@runtime_checkable
class SecretsProvider(Protocol):
    def fetch(
        self,
        *,
        integration_id: str,
        routine_id: str | None = None,
        required_scopes: Iterable[str] = (),
    ) -> Credential: ...

    def store(self, credential: Credential) -> None: ...

    def rotate(
        self,
        *,
        integration_id: str,
        routine_id: str | None,
        new_secret: dict[str, Any],
        granted_scopes: Iterable[str] | None = None,
        expires_at: datetime | None = None,
    ) -> Credential: ...

    def revoke(self, *, integration_id: str, routine_id: str | None = None) -> None: ...

    def list(self) -> list[Credential]: ...


def _key(integration_id: str, routine_id: str | None) -> str:
    return f"{integration_id}::{routine_id or ''}"


def _virtual_scope(credential: Credential, requested: tuple[str, ...]) -> Credential:
    if not requested:
        return credential
    granted = set(credential.granted_scopes)
    missing = [s for s in requested if s not in granted]
    if missing:
        raise InsufficientScopesError(
            integration_id=credential.integration_id,
            routine_id=credential.routine_id,
            requested=requested,
            granted=credential.granted_scopes,
        )
    return replace(credential, granted_scopes=tuple(requested))


def _validate_not_expired(credential: Credential, now: datetime) -> None:
    if credential.expires_at is not None and credential.expires_at <= now:
        raise CredentialExpiredError(
            integration_id=credential.integration_id,
            routine_id=credential.routine_id,
        )


class _BaseProvider:
    def __init__(self, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self._store: dict[str, Credential] = {}

    def fetch(
        self,
        *,
        integration_id: str,
        routine_id: str | None = None,
        required_scopes: Iterable[str] = (),
    ) -> Credential:
        requested = tuple(required_scopes)
        with self._lock:
            key = _key(integration_id, routine_id)
            credential = self._store.get(key)
            if credential is None and routine_id is not None:
                credential = self._store.get(_key(integration_id, None))
            if credential is None:
                raise CredentialNotFoundError(integration_id, routine_id)
        _validate_not_expired(credential, self._clock())
        return _virtual_scope(credential, requested)

    def store(self, credential: Credential) -> None:
        with self._lock:
            self._store[_key(credential.integration_id, credential.routine_id)] = credential
            self._persist()

    def rotate(
        self,
        *,
        integration_id: str,
        routine_id: str | None,
        new_secret: dict[str, Any],
        granted_scopes: Iterable[str] | None = None,
        expires_at: datetime | None = None,
    ) -> Credential:
        with self._lock:
            key = _key(integration_id, routine_id)
            existing = self._store.get(key)
            if existing is None:
                raise CredentialNotFoundError(integration_id, routine_id)
            rotated = Credential(
                integration_id=existing.integration_id,
                routine_id=existing.routine_id,
                style=existing.style,
                granted_scopes=(
                    tuple(granted_scopes) if granted_scopes is not None else existing.granted_scopes
                ),
                secret=dict(new_secret),
                rotated_at=self._clock(),
                expires_at=expires_at,
            )
            self._store[key] = rotated
            self._persist()
            return rotated

    def revoke(self, *, integration_id: str, routine_id: str | None = None) -> None:
        with self._lock:
            self._store.pop(_key(integration_id, routine_id), None)
            self._persist()

    def list(self) -> list[Credential]:
        with self._lock:
            return list(self._store.values())

    def _persist(self) -> None:
        return None


class InMemorySecretsProvider(_BaseProvider):
    pass


class EncryptedFileSecretsProvider(_BaseProvider):
    _SCHEMA_VERSION = "1.0"

    def __init__(
        self,
        path: Path | str,
        key: bytes | str,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        super().__init__(clock=clock)
        self._path = Path(path).expanduser()
        self._fernet = Fernet(key if isinstance(key, bytes) else key.encode("utf-8"))
        self._load()

    @staticmethod
    def generate_key() -> bytes:
        return Fernet.generate_key()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        if not self._path.exists():
            self._store = {}
            return
        try:
            ciphertext = self._path.read_bytes()
            plaintext = self._fernet.decrypt(ciphertext)
            envelope = json.loads(plaintext.decode("utf-8"))
        except (InvalidToken, json.JSONDecodeError, UnicodeDecodeError) as e:
            raise SecretsStoreCorruptError(
                f"failed to decrypt/parse secrets store {self._path}: {e}"
            ) from e
        if not isinstance(envelope, dict):
            raise SecretsStoreCorruptError(
                f"secrets store envelope is not a mapping in {self._path}"
            )
        schema_version = envelope.get("schema_version")
        if schema_version != self._SCHEMA_VERSION:
            raise SecretsStoreCorruptError(
                f"unsupported secrets schema_version={schema_version!r} in {self._path}"
            )
        records = envelope.get("credentials", [])
        if not isinstance(records, list):
            raise SecretsStoreCorruptError(f"credentials must be list in {self._path}")
        out: dict[str, Credential] = {}
        for rec in records:
            credential = _credential_from_dict(rec)
            out[_key(credential.integration_id, credential.routine_id)] = credential
        self._store = out

    def _persist(self) -> None:
        envelope = {
            "schema_version": self._SCHEMA_VERSION,
            "credentials": [_credential_to_dict(c) for c in self._store.values()],
        }
        plaintext = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
        ciphertext = self._fernet.encrypt(plaintext)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "wb") as f:
            f.write(ciphertext)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)
        try:
            os.chmod(self._path, 0o600)
        except PermissionError:  # filesystem may not support chmod (Windows, some FUSE)
            pass

    def reload(self) -> None:
        with self._lock:
            self._load()


def _credential_to_dict(c: Credential) -> dict[str, Any]:
    return {
        "integration_id": c.integration_id,
        "routine_id": c.routine_id,
        "style": c.style,
        "granted_scopes": list(c.granted_scopes),
        "secret": c.secret,
        "rotated_at": c.rotated_at.astimezone(UTC).isoformat(),
        "expires_at": c.expires_at.astimezone(UTC).isoformat() if c.expires_at else None,
    }


def _credential_from_dict(d: dict[str, Any]) -> Credential:
    try:
        rotated_at = datetime.fromisoformat(d["rotated_at"])
        expires_at = datetime.fromisoformat(d["expires_at"]) if d.get("expires_at") else None
        return Credential(
            integration_id=d["integration_id"],
            routine_id=d.get("routine_id"),
            style=d["style"],
            granted_scopes=tuple(d.get("granted_scopes", [])),
            secret=dict(d.get("secret", {})),
            rotated_at=rotated_at,
            expires_at=expires_at,
        )
    except (KeyError, ValueError, TypeError) as e:
        raise SecretsProviderError(f"malformed credential record: {e}") from e
