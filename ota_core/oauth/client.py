"""Provider-agnostic OAuth 2.0 Authorization Code flow."""

from __future__ import annotations

import secrets
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from ota_core.oauth.token_store import OAuthTokenStore, TokenRecord


class OAuthError(Exception):
    """OAuth flow failed (network, provider error, or invalid state)."""

    def __init__(self, message: str, *, provider: str, kind: str) -> None:
        self.provider = provider
        self.kind = kind
        super().__init__(f"[{provider}] {kind}: {message}")


@dataclass(frozen=True)
class OAuthState:
    """Opaque CSRF-protection token returned alongside the auth URL.

    Callers persist `state` somewhere they can look up at callback time
    (cookie, session, in-memory dict) and pass the same value to
    `OAuthClient.exchange_code`. Mismatches raise `OAuthError(kind='state')`.
    """

    value: str

    @classmethod
    def generate(cls) -> OAuthState:
        return cls(value=secrets.token_urlsafe(32))


@dataclass(frozen=True)
class AuthorizationRequest:
    """Output of `OAuthClient.build_auth_url`."""

    url: str
    state: OAuthState


@dataclass(frozen=True)
class OAuthTokenResponse:
    """Normalized token response.

    `expires_at` is computed when the provider returns `expires_in` (seconds);
    None means the token is non-expiring (rare) or the provider omitted the
    field. `extra` keeps provider-specific fields (`scope`, `bot_user_id`,
    `team`, etc.) so adapters can pull them when they need them.
    """

    access_token: str
    token_type: str
    refresh_token: str | None
    expires_at: datetime | None
    granted_scopes: tuple[str, ...]
    extra: dict[str, Any] = field(default_factory=dict)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class OAuthClient:
    """Authorization-Code-grant OAuth 2 client.

    Constructed once per integration. `provider` is the human-readable name
    used in errors and audit (e.g. `"slack"`, `"gmail"`); `integration_id`
    is the Contract D registry id and the key used to fetch tokens from the
    `SecretsProvider`.
    """

    def __init__(
        self,
        *,
        provider: str,
        integration_id: str,
        client_id: str,
        client_secret: str,
        auth_url: str,
        token_url: str,
        redirect_uri: str,
        scopes: Iterable[str],
        token_store: OAuthTokenStore,
        http_client: httpx.AsyncClient | None = None,
        refresh_grace_seconds: int = 60,
    ) -> None:
        self._provider = provider
        self._integration_id = integration_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._auth_url = auth_url
        self._token_url = token_url
        self._redirect_uri = redirect_uri
        self._scopes = tuple(scopes)
        self._token_store = token_store
        self._http = http_client
        self._refresh_grace = timedelta(seconds=refresh_grace_seconds)

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def integration_id(self) -> str:
        return self._integration_id

    @property
    def scopes(self) -> tuple[str, ...]:
        return self._scopes

    def build_auth_url(self, *, extra_params: dict[str, str] | None = None) -> AuthorizationRequest:
        state = OAuthState.generate()
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "scope": " ".join(self._scopes),
            "state": state.value,
        }
        if extra_params:
            params.update(extra_params)
        return AuthorizationRequest(
            url=f"{self._auth_url}?{urlencode(params)}",
            state=state,
        )

    async def exchange_code(
        self,
        *,
        code: str,
        received_state: str,
        expected_state: OAuthState,
        routine_id: str | None = None,
    ) -> OAuthTokenResponse:
        if not secrets.compare_digest(received_state, expected_state.value):
            raise OAuthError(
                "state mismatch — possible CSRF or replayed callback",
                provider=self._provider,
                kind="state",
            )
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        response = await self._post_token(body)
        parsed = self._parse_token_response(response)
        self._persist(parsed, routine_id=routine_id)
        return parsed

    async def refresh(self, *, routine_id: str | None = None) -> OAuthTokenResponse:
        current = self._token_store.get(integration_id=self._integration_id, routine_id=routine_id)
        if current is None or not current.refresh_token:
            raise OAuthError(
                "no refresh_token on file; re-authorize required",
                provider=self._provider,
                kind="no_refresh_token",
            )
        body = {
            "grant_type": "refresh_token",
            "refresh_token": current.refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        response = await self._post_token(body)
        parsed = self._parse_token_response(response)
        if parsed.refresh_token is None:
            parsed = OAuthTokenResponse(
                access_token=parsed.access_token,
                token_type=parsed.token_type,
                refresh_token=current.refresh_token,
                expires_at=parsed.expires_at,
                granted_scopes=parsed.granted_scopes or current.granted_scopes,
                extra=parsed.extra,
            )
        self._persist(parsed, routine_id=routine_id)
        return parsed

    async def access_token(self, *, routine_id: str | None = None) -> str:
        record = self._token_store.get(integration_id=self._integration_id, routine_id=routine_id)
        if record is None:
            raise OAuthError(
                "no token stored — run authorization flow first",
                provider=self._provider,
                kind="not_authorized",
            )
        if (
            record.expires_at is not None
            and (record.expires_at - _utc_now()) <= self._refresh_grace
        ):
            refreshed = await self.refresh(routine_id=routine_id)
            return refreshed.access_token
        return record.access_token

    async def _post_token(self, body: dict[str, str]) -> dict[str, Any]:
        if self._http is None:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self._token_url, data=body)
        else:
            resp = await self._http.post(self._token_url, data=body)
        if resp.status_code != 200:
            raise OAuthError(
                f"token endpoint returned HTTP {resp.status_code}: {resp.text[:500]}",
                provider=self._provider,
                kind="http_error",
            )
        try:
            data: dict[str, Any] = resp.json()
        except ValueError as exc:
            raise OAuthError(
                f"token response was not JSON: {resp.text[:200]}",
                provider=self._provider,
                kind="bad_response",
            ) from exc
        if "error" in data:
            description = data.get("error_description") or data["error"]
            raise OAuthError(
                f"provider returned error: {description}",
                provider=self._provider,
                kind="provider_error",
            )
        return data

    def _parse_token_response(self, data: dict[str, Any]) -> OAuthTokenResponse:
        access = data.get("access_token") or data.get("authed_user", {}).get("access_token")
        if not access:
            raise OAuthError(
                "missing access_token in response",
                provider=self._provider,
                kind="missing_token",
            )
        token_type = data.get("token_type", "Bearer")
        refresh = data.get("refresh_token") or None
        expires_in = data.get("expires_in")
        expires_at = (
            _utc_now() + timedelta(seconds=int(expires_in)) if expires_in is not None else None
        )
        scope_value = data.get("scope") or ""
        scopes: tuple[str, ...] = tuple(
            s for s in (scope_value.replace(",", " ").split() if scope_value else ()) if s
        )
        extra = {k: v for k, v in data.items() if k not in _BASE_FIELDS}
        return OAuthTokenResponse(
            access_token=access,
            token_type=token_type,
            refresh_token=refresh,
            expires_at=expires_at,
            granted_scopes=scopes,
            extra=extra,
        )

    def _persist(self, response: OAuthTokenResponse, *, routine_id: str | None) -> None:
        record = TokenRecord(
            access_token=response.access_token,
            refresh_token=response.refresh_token,
            token_type=response.token_type,
            expires_at=response.expires_at,
            granted_scopes=response.granted_scopes,
            extra=response.extra,
        )
        self._token_store.put(
            integration_id=self._integration_id,
            routine_id=routine_id,
            record=record,
        )


_BASE_FIELDS = frozenset({"access_token", "refresh_token", "token_type", "expires_in", "scope"})
