from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from ota_core.oauth import OAuthClient, OAuthError, OAuthState, OAuthTokenStore
from ota_core.secrets.provider import Credential, EncryptedFileSecretsProvider


@pytest.fixture
def secrets_provider(tmp_path: Path) -> EncryptedFileSecretsProvider:
    key = EncryptedFileSecretsProvider.generate_key()
    return EncryptedFileSecretsProvider(path=tmp_path / "secrets.bin", key=key)


@pytest.fixture
def token_store(secrets_provider: EncryptedFileSecretsProvider) -> OAuthTokenStore:
    return OAuthTokenStore(secrets_provider)


async def _client(token_store: OAuthTokenStore) -> OAuthClient:
    return OAuthClient(
        provider="test",
        integration_id="test.app",
        client_id="cid",
        client_secret="cs",
        auth_url="https://example.com/oauth/authorize",
        token_url="https://example.com/oauth/token",
        redirect_uri="https://app.local/callback",
        scopes=("scope:a", "scope:b"),
        token_store=token_store,
    )


async def test_build_auth_url_contains_required_params(token_store: OAuthTokenStore) -> None:
    client = await _client(token_store)
    auth = client.build_auth_url()
    assert auth.url.startswith("https://example.com/oauth/authorize?")
    assert "response_type=code" in auth.url
    assert "client_id=cid" in auth.url
    assert "scope=scope%3Aa+scope%3Ab" in auth.url
    assert f"state={auth.state.value}" in auth.url
    assert "redirect_uri=https%3A%2F%2Fapp.local%2Fcallback" in auth.url


async def test_exchange_code_stores_token(
    token_store: OAuthTokenStore,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://example.com/oauth/token",
        json={
            "access_token": "AT",
            "refresh_token": "RT",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "scope:a scope:b",
        },
    )
    client = await _client(token_store)
    expected_state = OAuthState.generate()
    response = await client.exchange_code(
        code="C",
        received_state=expected_state.value,
        expected_state=expected_state,
    )
    assert response.access_token == "AT"
    assert response.refresh_token == "RT"
    assert response.granted_scopes == ("scope:a", "scope:b")
    stored = token_store.get(integration_id="test.app")
    assert stored is not None
    assert stored.access_token == "AT"
    assert stored.refresh_token == "RT"


async def test_state_mismatch_raises(token_store: OAuthTokenStore, httpx_mock: HTTPXMock) -> None:
    client = await _client(token_store)
    with pytest.raises(OAuthError, match="state mismatch"):
        await client.exchange_code(
            code="C",
            received_state="wrong",
            expected_state=OAuthState.generate(),
        )


async def test_provider_error_raises(token_store: OAuthTokenStore, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://example.com/oauth/token",
        json={"error": "invalid_grant", "error_description": "code expired"},
    )
    client = await _client(token_store)
    state = OAuthState.generate()
    with pytest.raises(OAuthError, match="code expired"):
        await client.exchange_code(code="C", received_state=state.value, expected_state=state)


async def test_http_error_raises(token_store: OAuthTokenStore, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url="https://example.com/oauth/token", status_code=500, text="ugh"
    )
    client = await _client(token_store)
    state = OAuthState.generate()
    with pytest.raises(OAuthError, match="HTTP 500"):
        await client.exchange_code(code="C", received_state=state.value, expected_state=state)


async def test_refresh_uses_stored_refresh_token(
    token_store: OAuthTokenStore,
    secrets_provider: EncryptedFileSecretsProvider,
    httpx_mock: HTTPXMock,
) -> None:
    secrets_provider.store(
        Credential(
            integration_id="test.app",
            routine_id=None,
            style="oauth2",
            granted_scopes=("scope:a",),
            secret={
                "access_token": "OLD",
                "refresh_token": "RT",
                "token_type": "Bearer",
                "expires_at": (datetime.now(UTC) - timedelta(seconds=10)).isoformat(),
                "granted_scopes": ["scope:a"],
                "extra": {},
            },
        )
    )
    httpx_mock.add_response(
        method="POST",
        url="https://example.com/oauth/token",
        json={
            "access_token": "NEW",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "scope:a",
        },
    )
    client = await _client(token_store)
    refreshed = await client.refresh()
    assert refreshed.access_token == "NEW"
    # Refresh token is carried forward when omitted
    stored = token_store.get(integration_id="test.app")
    assert stored is not None
    assert stored.refresh_token == "RT"


async def test_refresh_without_stored_token_raises(
    token_store: OAuthTokenStore, httpx_mock: HTTPXMock
) -> None:
    client = await _client(token_store)
    with pytest.raises(OAuthError, match="no refresh_token"):
        await client.refresh()


async def test_access_token_refreshes_when_expired(
    token_store: OAuthTokenStore,
    secrets_provider: EncryptedFileSecretsProvider,
    httpx_mock: HTTPXMock,
) -> None:
    secrets_provider.store(
        Credential(
            integration_id="test.app",
            routine_id=None,
            style="oauth2",
            granted_scopes=("scope:a",),
            secret={
                "access_token": "OLD",
                "refresh_token": "RT",
                "token_type": "Bearer",
                "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                "granted_scopes": ["scope:a"],
                "extra": {},
            },
        )
    )
    httpx_mock.add_response(
        method="POST",
        url="https://example.com/oauth/token",
        json={"access_token": "NEW", "expires_in": 3600, "token_type": "Bearer"},
    )
    client = await _client(token_store)
    token = await client.access_token()
    assert token == "NEW"


async def test_access_token_skips_refresh_when_fresh(
    token_store: OAuthTokenStore,
    secrets_provider: EncryptedFileSecretsProvider,
) -> None:
    secrets_provider.store(
        Credential(
            integration_id="test.app",
            routine_id=None,
            style="oauth2",
            granted_scopes=("scope:a",),
            secret={
                "access_token": "GOOD",
                "refresh_token": "RT",
                "token_type": "Bearer",
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "granted_scopes": ["scope:a"],
                "extra": {},
            },
        )
    )
    client = await _client(token_store)
    token = await client.access_token()
    assert token == "GOOD"


async def test_uses_caller_provided_http_client(
    token_store: OAuthTokenStore,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://example.com/oauth/token",
        json={"access_token": "AT", "token_type": "Bearer", "expires_in": 3600},
    )
    async with httpx.AsyncClient() as http:
        client = OAuthClient(
            provider="test",
            integration_id="test.app",
            client_id="cid",
            client_secret="cs",
            auth_url="https://example.com/oauth/authorize",
            token_url="https://example.com/oauth/token",
            redirect_uri="https://app.local/callback",
            scopes=("scope:a",),
            token_store=token_store,
            http_client=http,
        )
        state = OAuthState.generate()
        response = await client.exchange_code(
            code="C", received_state=state.value, expected_state=state
        )
        assert response.access_token == "AT"
