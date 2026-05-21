"""Mock messaging adapter — in-memory implementation of `capabilities.messaging.*`.

Used by Phase 3 dispatch tests and as a stand-in for Slack until Phase 4A
ships `slack_socket_adapter`. The adapter accepts every verb the messaging
vocabulary declares; sends are recorded in `outbox`. Replies fed in via
`queue_reply()` surface through `poll_inbound()` so HITL / action-callback
tests can simulate operator approvals.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from ota_connect._types import (
    Block,
    ChannelRef,
    IdentityRef,
    MessageRef,
    Page,
    ThreadRef,
)
from ota_connect.binding.actions import ActionEventKind
from ota_connect.binding.inbound_email import RawInboundEvent
from ota_core.integration_source.source import AdapterBundle


class MockMessagingAdapter:
    """Sync in-memory implementation of every `messaging.*` verb."""

    def __init__(self, bundle: AdapterBundle | None = None) -> None:
        self._bundle = bundle
        self.manifest = bundle.manifest if bundle is not None else None
        self.outbox: list[dict[str, Any]] = []
        self.edited: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self._pending_inbound: list[RawInboundEvent] = []
        self.channels: dict[str, ChannelRef] = {}
        self.threads_by_channel: dict[str, list[MessageRef]] = {}

    def invoke(self, capability: str, verb: str, /, **kwargs: Any) -> Any:
        if capability != "messaging":
            raise NotImplementedError(
                f"mock_messaging only implements messaging.*, got {capability}.{verb}"
            )
        handler = getattr(self, f"_verb_{verb}", None)
        if handler is None:
            raise NotImplementedError(f"messaging.{verb} not implemented by mock_messaging")
        return handler(**kwargs)

    def _verb_send_message(
        self,
        target: ChannelRef | IdentityRef,
        content: str | list[Block],
        thread_ref: ThreadRef | None = None,
        attachments: list[Any] | None = None,
        importance: str = "normal",
    ) -> MessageRef:
        channel = _ensure_channel(target)
        ref = MessageRef(
            id=uuid.uuid4().hex,
            channel=channel,
            sent_at=datetime.now(UTC),
            permalink=None,
            adapter="mock_messaging",
        )
        self.outbox.append(
            {
                "target": target,
                "content": content,
                "thread_ref": thread_ref,
                "attachments": attachments or [],
                "importance": importance,
                "ref": ref,
            }
        )
        self.threads_by_channel.setdefault(channel.id, []).append(ref)
        return ref

    def _verb_edit_message(
        self, message_ref: MessageRef, new_content: str | list[Block]
    ) -> MessageRef:
        self.edited.append({"message_ref": message_ref, "new_content": new_content})
        return message_ref

    def _verb_delete_message(self, message_ref: MessageRef) -> None:
        self.deleted.append(message_ref.id)

    def _verb_read_thread(
        self,
        thread_ref: ThreadRef,
        limit: int = 100,
        cursor: str | None = None,
    ) -> Page[MessageRef]:
        items = list(self.threads_by_channel.get(thread_ref.channel.id, []))
        return Page(items=items[:limit], next_cursor=None)

    def _verb_list_recent_messages(
        self,
        channel: ChannelRef | IdentityRef,
        since: datetime | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> Page[MessageRef]:
        ch = _ensure_channel(channel)
        items = list(self.threads_by_channel.get(ch.id, []))
        if since is not None:
            items = [m for m in items if m.sent_at >= since]
        return Page(items=items[:limit], next_cursor=None)

    def queue_action(
        self,
        *,
        routine_id: str,
        kind: ActionEventKind = "messaging.action_triggered",
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Fed by tests to simulate an upstream action callback."""
        self._pending_inbound.append(
            RawInboundEvent(
                kind=kind,
                routine_id=routine_id,
                payload=payload or {},
                correlation_id=correlation_id,
            )
        )

    def poll_inbound(self) -> Iterable[RawInboundEvent]:
        drained = list(self._pending_inbound)
        self._pending_inbound.clear()
        return drained


def _ensure_channel(target: ChannelRef | IdentityRef) -> ChannelRef:
    if isinstance(target, ChannelRef):
        return target
    return ChannelRef(
        id=f"dm:{target}",
        kind="dm",
        name=None,
        adapter="mock_messaging",
    )
