"""OAuth token store — wraps `SecretsProvider` with a normalized record shape."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from ota_core.secrets.errors import CredentialNotFoundError
from ota_core.secrets.provider import Credential, SecretsProvider


@dataclass(frozen=True)
class TokenRecord:
    """Normalized OAuth credential payload — provider-agnostic.

    Stored inside `Credential.secret` (a `dict[str, Any]`). `extra` captures
    provider-specific fields the adapter wants to retrieve later (Slack's
    `bot_user_id` and `team`, Google's `id_token`, etc.).
    """

    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_at: datetime | None = None
    granted_scopes: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["granted_scopes"] = list(self.granted_scopes)
        d["expires_at"] = self.expires_at.isoformat() if self.expires_at is not None else None
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TokenRecord:
        expires_at_raw = raw.get("expires_at")
        expires_at = datetime.fromisoformat(expires_at_raw) if expires_at_raw else None
        return cls(
            access_token=raw["access_token"],
            refresh_token=raw.get("refresh_token"),
            token_type=raw.get("token_type", "Bearer"),
            expires_at=expires_at,
            granted_scopes=tuple(raw.get("granted_scopes") or ()),
            extra=dict(raw.get("extra") or {}),
        )


class OAuthTokenStore:
    """Read/write OAuth `TokenRecord`s via a `SecretsProvider`.

    The store does not own scope enforcement — that belongs to the
    SecretsProvider's `fetch(required_scopes=...)` call at adapter dispatch
    time. The store is a write/read seam only.
    """

    def __init__(self, secrets: SecretsProvider) -> None:
        self._secrets = secrets

    def get(self, *, integration_id: str, routine_id: str | None = None) -> TokenRecord | None:
        try:
            credential = self._secrets.fetch(integration_id=integration_id, routine_id=routine_id)
        except CredentialNotFoundError:
            return None
        if credential.style != "oauth2":
            return None
        return TokenRecord.from_dict(credential.secret)

    def put(
        self,
        *,
        integration_id: str,
        routine_id: str | None,
        record: TokenRecord,
    ) -> Credential:
        credential = Credential(
            integration_id=integration_id,
            routine_id=routine_id,
            style="oauth2",
            granted_scopes=record.granted_scopes,
            secret=record.as_dict(),
            expires_at=record.expires_at,
        )
        self._secrets.store(credential)
        return credential

    def revoke(self, *, integration_id: str, routine_id: str | None = None) -> None:
        try:
            self._secrets.revoke(integration_id=integration_id, routine_id=routine_id)
        except CredentialNotFoundError:
            return
