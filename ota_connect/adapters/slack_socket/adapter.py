"""Slack adapter — messaging.* verbs over Slack Web API + Socket Mode.

The adapter calls Slack's Web API (`https://slack.com/api/...`) directly via
`httpx` so tests can mock at the transport layer with `pytest-httpx`. Socket
Mode (the WebSocket event delivery surface) is wrapped behind
`SocketModeListener` — a thin async loop that yields normalized
`RawInboundEvent`s when Slack sends an `interactive` payload (button clicks,
shortcut invocations) so the framework's `ActionRouter` can route them.

OAuth is handled by `SlackOAuthClient`, a thin wrapper around the shared
`OAuthClient` that knows Slack's `authed_user.access_token` shape.

The adapter is `sync` at the `AdapterImpl.invoke` boundary (per the
binding-layer protocol). HTTP calls go through `_post_sync` which blocks on
a private `httpx.Client`. Socket Mode + inbound polling run async; the
framework calls them from its event loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from ota_connect._types import (
    Attachment,
    Block,
    ChannelRef,
    Cursor,
    IdentityRef,
    MessageRef,
    Page,
    ThreadRef,
)
from ota_connect._types.errors import (
    AdapterUnavailable,
    MessageRejected,
    RateLimited,
    RecipientUnreachable,
)
from ota_connect.binding.actions import ActionEventKind
from ota_connect.binding.error_norm import make_error
from ota_connect.binding.inbound_email import RawInboundEvent
from ota_core.integration_source.source import AdapterBundle
from ota_core.oauth import OAuthTokenStore

_logger = logging.getLogger(__name__)

_SLACK_API = "https://slack.com/api"


@dataclass
class SlackAdapterConfig:
    """Adapter-side config injected at instantiation time.

    The token store is shared with the framework's SecretsProvider so token
    refresh and revocation are coordinated. `bot_token_override` exists so
    tests can bypass token-store lookup without writing to disk.
    """

    token_store: OAuthTokenStore | None = None
    bot_token_override: str | None = None
    integration_id: str = "slack.com"
    request_timeout_seconds: float = 10.0


class SlackSocketAdapter:
    """`AdapterImpl` for Slack messaging.* verbs."""

    adapter_id = "slack_socket_adapter"
    capability = "messaging"

    def __init__(
        self,
        bundle: AdapterBundle | None = None,
        *,
        config: SlackAdapterConfig | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._bundle = bundle
        self.manifest = bundle.manifest if bundle is not None else None
        self._config = config or SlackAdapterConfig()
        self._http = http_client
        self._pending_inbound: list[RawInboundEvent] = []

    # ------------------------------------------------------------------
    # AdapterImpl protocol
    # ------------------------------------------------------------------

    def invoke(self, capability: str, verb: str, /, **kwargs: Any) -> Any:
        if capability != "messaging":
            raise NotImplementedError(
                f"slack_socket_adapter only implements messaging.*, got {capability}.{verb}"
            )
        handler = getattr(self, f"_verb_{verb}", None)
        if handler is None:
            raise NotImplementedError(f"messaging.{verb} not implemented by slack adapter")
        return handler(**kwargs)

    def poll_inbound(self) -> Iterable[RawInboundEvent]:
        drained = list(self._pending_inbound)
        self._pending_inbound.clear()
        return drained

    # ------------------------------------------------------------------
    # Verb implementations
    # ------------------------------------------------------------------

    def _verb_send_message(
        self,
        target: ChannelRef | IdentityRef,
        content: str | list[Block],
        thread_ref: ThreadRef | None = None,
        attachments: list[Attachment] | None = None,
        importance: str = "normal",
    ) -> MessageRef:
        channel_id = _channel_id_for(target)
        text, blocks_payload = _content_to_slack(content)
        body: dict[str, Any] = {"channel": channel_id, "text": text}
        if blocks_payload is not None:
            body["blocks"] = blocks_payload
        if thread_ref is not None:
            body["thread_ts"] = thread_ref.id
        if importance == "high":
            body["broadcast"] = False  # placeholder — Slack uses link unfurl flags
        if attachments:
            body["attachments"] = [_attachment_to_slack(a) for a in attachments]
        data = self._post_sync("chat.postMessage", body)
        ts: str = data["ts"]
        channel_kind: str = data.get("channel_type", "channel")
        return MessageRef(
            id=ts,
            channel=_channel_ref(channel_id, kind=channel_kind),
            sent_at=_ts_to_datetime(ts),
            permalink=data.get("message", {}).get("permalink"),
            adapter=self.adapter_id,
        )

    def _verb_edit_message(
        self, message_ref: MessageRef, new_content: str | list[Block]
    ) -> MessageRef:
        text, blocks_payload = _content_to_slack(new_content)
        body: dict[str, Any] = {
            "channel": message_ref.channel.id,
            "ts": message_ref.id,
            "text": text,
        }
        if blocks_payload is not None:
            body["blocks"] = blocks_payload
        data = self._post_sync("chat.update", body)
        return MessageRef(
            id=data["ts"],
            channel=message_ref.channel,
            sent_at=_ts_to_datetime(data["ts"]),
            permalink=message_ref.permalink,
            adapter=self.adapter_id,
        )

    def _verb_delete_message(self, message_ref: MessageRef) -> None:
        self._post_sync("chat.delete", {"channel": message_ref.channel.id, "ts": message_ref.id})

    def _verb_read_thread(
        self,
        thread_ref: ThreadRef,
        limit: int = 100,
        cursor: Cursor | None = None,
    ) -> Page[MessageRef]:
        body: dict[str, Any] = {
            "channel": thread_ref.channel.id,
            "ts": thread_ref.id,
            "limit": limit,
        }
        if cursor is not None:
            body["cursor"] = cursor
        data = self._post_sync("conversations.replies", body)
        items = [
            MessageRef(
                id=m["ts"],
                channel=thread_ref.channel,
                sent_at=_ts_to_datetime(m["ts"]),
                permalink=m.get("permalink"),
                adapter=self.adapter_id,
            )
            for m in data.get("messages", [])
        ]
        next_cursor = data.get("response_metadata", {}).get("next_cursor") or None
        return Page(items=items, next_cursor=next_cursor)

    def _verb_list_recent_messages(
        self,
        channel: ChannelRef | IdentityRef,
        since: datetime | None = None,
        limit: int = 50,
        cursor: Cursor | None = None,
    ) -> Page[MessageRef]:
        channel_id = _channel_id_for(channel)
        body: dict[str, Any] = {"channel": channel_id, "limit": limit}
        if cursor is not None:
            body["cursor"] = cursor
        if since is not None:
            body["oldest"] = f"{since.timestamp():.6f}"
        data = self._post_sync("conversations.history", body)
        channel_ref = _channel_ref(channel_id, kind="channel")
        items = [
            MessageRef(
                id=m["ts"],
                channel=channel_ref,
                sent_at=_ts_to_datetime(m["ts"]),
                permalink=m.get("permalink"),
                adapter=self.adapter_id,
            )
            for m in data.get("messages", [])
        ]
        next_cursor = data.get("response_metadata", {}).get("next_cursor") or None
        return Page(items=items, next_cursor=next_cursor)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _post_sync(self, method: str, body: dict[str, Any]) -> dict[str, Any]:
        token = self._access_token()
        url = f"{_SLACK_API}/{method}"
        headers = {"Authorization": f"Bearer {token}"}
        client = self._http
        owns_client = False
        if client is None:
            client = httpx.Client(timeout=self._config.request_timeout_seconds)
            owns_client = True
        try:
            response = client.post(url, headers=headers, json=body)
        finally:
            if owns_client:
                client.close()
        return _check_slack_response(
            response, adapter_id=self.adapter_id, capability="messaging", verb=method
        )

    def _access_token(self) -> str:
        if self._config.bot_token_override is not None:
            return self._config.bot_token_override
        store = self._config.token_store
        if store is None:
            raise make_error(
                AdapterUnavailable,
                adapter=self.adapter_id,
                capability="messaging",
                verb="<auth>",
                retryable=False,
            )
        record = store.get(integration_id=self._config.integration_id)
        if record is None:
            raise make_error(
                AdapterUnavailable,
                adapter=self.adapter_id,
                capability="messaging",
                verb="<auth>",
                retryable=False,
            )
        return record.access_token

    # ------------------------------------------------------------------
    # Socket Mode event ingest (called by SocketModeListener)
    # ------------------------------------------------------------------

    def ingest_socket_payload(
        self,
        *,
        routine_id: str,
        payload: dict[str, Any],
        kind: ActionEventKind = "messaging.action_triggered",
        correlation_id: str | None = None,
    ) -> None:
        self._pending_inbound.append(
            RawInboundEvent(
                kind=kind,
                routine_id=routine_id,
                payload=payload,
                correlation_id=correlation_id,
            )
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _channel_id_for(target: ChannelRef | IdentityRef) -> str:
    if isinstance(target, ChannelRef):
        return target.id
    if not isinstance(target, str):
        raise TypeError(f"unsupported target type: {type(target).__name__}")
    if target.startswith("raw:slack:"):
        return target.split(":", 2)[2]
    raise make_error(
        RecipientUnreachable,
        adapter="slack_socket_adapter",
        capability="messaging",
        verb="<resolve>",
        reason=(
            f"identity {target!r} cannot be resolved to a Slack channel; "
            "upstream IdentityProvider must translate handle:/mailto: before dispatch"
        ),
    )


def _channel_ref(channel_id: str, *, kind: str) -> ChannelRef:
    resolved_kind: Any
    if kind in ("channel", "dm", "group_dm"):
        resolved_kind = kind
    elif kind in ("im",):
        resolved_kind = "dm"
    elif kind in ("mpim",):
        resolved_kind = "group_dm"
    else:
        resolved_kind = "channel"
    return ChannelRef(id=channel_id, kind=resolved_kind, name=None, adapter="slack_socket_adapter")


def _content_to_slack(
    content: str | list[Block],
) -> tuple[str, list[dict[str, Any]] | None]:
    if isinstance(content, str):
        return content, None
    text = " ".join(b.text for b in content if isinstance(b.text, str))
    blocks_payload = [_block_to_slack(b) for b in content]
    return text or " ", blocks_payload


def _block_to_slack(b: Block) -> dict[str, Any]:
    if b.kind == "text" or b.kind == "section":
        return {
            "type": "section",
            "text": {"type": "mrkdwn", "text": b.text or ""},
        }
    if b.kind == "header":
        return {
            "type": "header",
            "text": {"type": "plain_text", "text": b.text or ""},
        }
    if b.kind == "divider":
        return {"type": "divider"}
    if b.kind == "actions":
        return {
            "type": "actions",
            "elements": [_action_to_slack(a) for a in (b.actions or [])],
        }
    return {"type": "section", "text": {"type": "mrkdwn", "text": b.text or ""}}


def _action_to_slack(a: Any) -> dict[str, Any]:
    return {
        "type": "button",
        "text": {"type": "plain_text", "text": a.label},
        "value": a.value,
        "action_id": f"action_{quote(a.value)[:200]}",
    }


def _attachment_to_slack(a: Attachment) -> dict[str, Any]:
    return {
        "fallback": a.display_name,
        "file_url": a.file,
        "filename": a.display_name,
    }


def _ts_to_datetime(ts: str) -> datetime:
    seconds = float(ts)
    return datetime.fromtimestamp(seconds, tz=UTC)


def _check_slack_response(
    response: httpx.Response,
    *,
    adapter_id: str,
    capability: str,
    verb: str,
) -> dict[str, Any]:
    if response.status_code == 429:
        retry_after_raw = response.headers.get("Retry-After")
        from datetime import timedelta as _td

        retry_after = _td(seconds=int(retry_after_raw)) if retry_after_raw else None
        raise make_error(
            RateLimited,
            adapter=adapter_id,
            capability=capability,
            verb=verb,
            retry_after=retry_after,
        )
    if response.status_code >= 500:
        raise make_error(
            AdapterUnavailable,
            adapter=adapter_id,
            capability=capability,
            verb=verb,
            retryable=True,
        )
    if response.status_code >= 400:
        raise make_error(
            AdapterUnavailable,
            adapter=adapter_id,
            capability=capability,
            verb=verb,
            retryable=False,
        )
    data: dict[str, Any] = response.json()
    if not data.get("ok", False):
        error_code = data.get("error", "unknown")
        if error_code in ("ratelimited",):
            raise make_error(
                RateLimited,
                adapter=adapter_id,
                capability=capability,
                verb=verb,
                retry_after=None,
            )
        if error_code in (
            "channel_not_found",
            "not_in_channel",
            "user_not_found",
            "im_disabled",
            "is_archived",
        ):
            raise make_error(
                RecipientUnreachable,
                adapter=adapter_id,
                capability=capability,
                verb=verb,
                reason=error_code,
            )
        if error_code in (
            "msg_too_long",
            "no_text",
            "blocks_no_match",
            "message_not_found",
        ):
            raise make_error(
                MessageRejected,
                adapter=adapter_id,
                capability=capability,
                verb=verb,
                reason=error_code,
            )
        raise make_error(
            AdapterUnavailable,
            adapter=adapter_id,
            capability=capability,
            verb=verb,
            retryable=False,
        )
    return data


# ---------------------------------------------------------------------------
# Socket Mode listener (async loop)
# ---------------------------------------------------------------------------


class SocketModeListener:
    """Minimal async loop that ingests Slack Socket Mode payloads.

    v0.1 implementation polls Slack's `apps.connections.open` to acquire a
    WebSocket URL and reads messages off it. To keep this module dependency-
    free in v0.1, the actual WebSocket transport is a strategy parameter — the
    framework wires `aiohttp` or `websockets` in deployment code, and tests
    inject a fake message stream.

    The listener calls `SlackSocketAdapter.ingest_socket_payload(...)` for
    every interactive event it observes.
    """

    def __init__(
        self,
        *,
        adapter: SlackSocketAdapter,
        message_stream: Any,  # async iterator yielding dict payloads
        routine_id: str,
    ) -> None:
        self._adapter = adapter
        self._stream = message_stream
        self._routine_id = routine_id
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def run(self) -> None:
        async for payload in self._stream:
            if self._stop.is_set():
                return
            try:
                self._adapter.ingest_socket_payload(
                    routine_id=self._routine_id,
                    payload=payload,
                    kind="messaging.action_triggered",
                    correlation_id=payload.get("trigger_id"),
                )
            except BaseException:
                _logger.exception("slack socket payload ingest failed")

    def start(self) -> asyncio.Task[None]:
        if self._task is not None:
            return self._task
        self._task = asyncio.create_task(self.run())
        return self._task

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, BaseException):
                pass
            self._task = None
