"""Mock email adapter — in-memory implementation of `capabilities.email.*`.

Stand-in for Gmail until Phase 4A ships `gmail_oauth_adapter`. Tracks an
outbox, drafts, labels, and read/unread state. `queue_inbound()` is the
test affordance for simulating bounces / replies / delivery confirmations
that surface via `poll_inbound()`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from ota_connect._types import (
    Attachment,
    Block,
    DraftRef,
    EmailRef,
    EmailThreadRef,
    IdentityRef,
    Page,
)
from ota_connect.binding.actions import ActionEventKind
from ota_connect.binding.inbound_email import RawInboundEvent
from ota_core.integration_source.source import AdapterBundle


class MockEmailAdapter:
    """Sync in-memory implementation of every `email.*` verb."""

    def __init__(self, bundle: AdapterBundle | None = None) -> None:
        self._bundle = bundle
        self.manifest = bundle.manifest if bundle is not None else None
        self.outbox: list[dict[str, Any]] = []
        self.drafts: dict[str, dict[str, Any]] = {}
        self.deleted: list[tuple[str, bool]] = []
        self.labels: dict[str, set[str]] = {}
        self.read_state: dict[str, bool] = {}
        self.threads: dict[str, list[EmailRef]] = {}
        self._mailbox: dict[str, list[EmailRef]] = {}
        self._pending_inbound: list[RawInboundEvent] = []

    def invoke(self, capability: str, verb: str, /, **kwargs: Any) -> Any:
        if capability != "email":
            raise NotImplementedError(
                f"mock_email only implements email.*, got {capability}.{verb}"
            )
        handler = getattr(self, f"_verb_{verb}", None)
        if handler is None:
            raise NotImplementedError(f"email.{verb} not implemented by mock_email")
        return handler(**kwargs)

    def _verb_send_email(
        self,
        to: list[IdentityRef],
        subject: str,
        body: str | list[Block],
        cc: list[IdentityRef] | None = None,
        bcc: list[IdentityRef] | None = None,
        reply_to: EmailRef | None = None,
        attachments: list[Attachment] | None = None,
        importance: str = "normal",
    ) -> EmailRef:
        thread = reply_to.thread if reply_to is not None else None
        if thread is None:
            thread = EmailThreadRef(
                id=uuid.uuid4().hex,
                subject=subject,
                started_at=datetime.now(UTC),
                adapter="mock_email",
            )
        ref = EmailRef(
            id=uuid.uuid4().hex,
            message_id_header=f"<{uuid.uuid4().hex}@mock>",
            thread=thread,
            sent_at=datetime.now(UTC),
            adapter="mock_email",
        )
        self.outbox.append(
            {
                "to": to,
                "cc": cc or [],
                "bcc": bcc or [],
                "subject": subject,
                "body": body,
                "reply_to": reply_to,
                "attachments": attachments or [],
                "importance": importance,
                "ref": ref,
            }
        )
        self.threads.setdefault(thread.id, []).append(ref)
        self._mailbox.setdefault("SENT", []).append(ref)
        return ref

    def _verb_create_draft(
        self,
        to: list[IdentityRef],
        subject: str,
        body: str | list[Block],
        cc: list[IdentityRef] | None = None,
        bcc: list[IdentityRef] | None = None,
        reply_to: EmailRef | None = None,
        attachments: list[Attachment] | None = None,
    ) -> DraftRef:
        ref = DraftRef(
            id=uuid.uuid4().hex,
            subject=subject,
            created_at=datetime.now(UTC),
            adapter="mock_email",
        )
        self.drafts[ref.id] = {
            "to": to,
            "cc": cc or [],
            "bcc": bcc or [],
            "subject": subject,
            "body": body,
            "reply_to": reply_to,
            "attachments": attachments or [],
        }
        return ref

    def _verb_send_draft(self, draft_ref: DraftRef) -> EmailRef:
        draft = self.drafts.pop(draft_ref.id, None)
        if draft is None:
            raise KeyError(draft_ref.id)
        return self._verb_send_email(**draft)

    def _verb_delete_email(self, email_ref: EmailRef, permanent: bool = False) -> None:
        self.deleted.append((email_ref.id, permanent))

    def _verb_list_mailbox(
        self,
        folder: str,
        since: datetime | None = None,
        limit: int = 25,
        cursor: str | None = None,
    ) -> Page[EmailRef]:
        items = list(self._mailbox.get(folder, []))
        if since is not None:
            items = [m for m in items if m.sent_at >= since]
        return Page(items=items[:limit], next_cursor=None)

    def _verb_read_email_thread(
        self,
        thread_ref: EmailThreadRef,
        limit: int = 50,
        cursor: str | None = None,
    ) -> Page[EmailRef]:
        items = list(self.threads.get(thread_ref.id, []))
        return Page(items=items[:limit], next_cursor=None)

    def _verb_modify_email_labels(
        self,
        email_ref: EmailRef,
        add_labels: list[str],
        remove_labels: list[str],
    ) -> None:
        current = self.labels.setdefault(email_ref.id, set())
        current.update(add_labels)
        current.difference_update(remove_labels)

    def _verb_mark_read(self, email_ref: EmailRef) -> None:
        self.read_state[email_ref.id] = True

    def _verb_mark_unread(self, email_ref: EmailRef) -> None:
        self.read_state[email_ref.id] = False

    def queue_inbound(
        self,
        *,
        routine_id: str,
        kind: ActionEventKind = "email.reply_received",
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
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
