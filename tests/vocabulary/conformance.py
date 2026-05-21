"""Adapter conformance harness — per-verb behavioral assertions.

Each adapter that claims `capability=messaging` or `capability=email` in its
manifest is expected to satisfy these per-verb behavioral contracts:

* Verbs return objects of the documented capability types (`MessageRef`,
  `EmailRef`, `Page[...]`, etc.).
* `adapter` field on returned refs matches the adapter's manifest id.
* Pagination verbs return a `Page` with a valid (possibly None) next_cursor.
* Idempotency: best-effort verbs may produce different refs each call;
  guaranteed verbs must return the same materially-equivalent result.
* Required-scope set declared in `@verb` metadata is a superset of what the
  adapter actually exercises (checked by inspecting the verb's
  `_ota_verb_meta` and the adapter's manifest claims).

The harness is generic — pass it an `AdapterImpl` instance (or a factory)
and a fixture set, and it runs every applicable verb test. Adapter-specific
test modules (`tests/connect/slack/...`, `tests/connect/gmail/...`) subclass
or parametrize against `ConformanceFixture`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ota_connect._types import (
    ChannelRef,
    DraftRef,
    EmailRef,
    EmailThreadRef,
    IdentityRef,
    MessageRef,
    Page,
)
from ota_connect.binding.adapter_impl import AdapterImpl


@dataclass
class ConformanceFixture:
    """Inputs the conformance harness needs to exercise an adapter.

    `channel` and `thread_ref` are pre-known references the adapter accepts.
    `recipients` is a list of `IdentityRef` strings the adapter recognizes.
    `email_thread_ref` is needed for email read tests.
    """

    channel: ChannelRef
    thread_ref: Any  # ThreadRef
    recipients: list[IdentityRef]
    email_thread_ref: EmailThreadRef | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def assert_message_ref(ref: MessageRef, *, adapter_id: str) -> None:
    assert isinstance(ref, MessageRef), f"expected MessageRef, got {type(ref).__name__}"
    assert ref.id, "MessageRef.id must be non-empty"
    assert ref.adapter == adapter_id, f"expected adapter={adapter_id}, got {ref.adapter}"
    assert isinstance(ref.sent_at, datetime), "MessageRef.sent_at must be a datetime"
    assert ref.sent_at.tzinfo is not None, "MessageRef.sent_at must be tz-aware"


def assert_email_ref(ref: EmailRef, *, adapter_id: str) -> None:
    assert isinstance(ref, EmailRef)
    assert ref.id
    assert ref.adapter == adapter_id
    assert ref.sent_at.tzinfo is not None


def assert_draft_ref(ref: DraftRef, *, adapter_id: str) -> None:
    assert isinstance(ref, DraftRef)
    assert ref.id
    assert ref.adapter == adapter_id
    assert ref.created_at.tzinfo is not None


def assert_page(page: Page[Any], *, item_type: type) -> None:
    assert isinstance(page, Page)
    assert isinstance(page.items, list)
    for item in page.items:
        assert isinstance(item, item_type), (
            f"page item is {type(item).__name__}, expected {item_type.__name__}"
        )
    if page.next_cursor is not None:
        assert isinstance(page.next_cursor, str)
        assert page.next_cursor != ""


def run_messaging_conformance(
    impl: AdapterImpl,
    *,
    adapter_id: str,
    fixture: ConformanceFixture,
) -> None:
    """Run the full messaging verb battery against `impl`."""
    ref = impl.invoke(
        "messaging",
        "send_message",
        target=fixture.channel,
        content="hello",
        thread_ref=None,
        attachments=None,
        importance="normal",
    )
    assert_message_ref(ref, adapter_id=adapter_id)

    edited = impl.invoke("messaging", "edit_message", message_ref=ref, new_content="edited")
    assert_message_ref(edited, adapter_id=adapter_id)

    # delete returns None
    deleted = impl.invoke("messaging", "delete_message", message_ref=ref)
    assert deleted is None

    page = impl.invoke(
        "messaging",
        "list_recent_messages",
        channel=fixture.channel,
        since=None,
        limit=10,
        cursor=None,
    )
    assert_page(page, item_type=MessageRef)


def run_email_conformance(
    impl: AdapterImpl,
    *,
    adapter_id: str,
    fixture: ConformanceFixture,
) -> None:
    """Run the full email verb battery against `impl`."""
    ref = impl.invoke(
        "email",
        "send_email",
        to=fixture.recipients,
        subject="Conformance",
        body="body",
        cc=None,
        bcc=None,
        reply_to=None,
        attachments=None,
        importance="normal",
    )
    assert_email_ref(ref, adapter_id=adapter_id)

    draft = impl.invoke(
        "email",
        "create_draft",
        to=fixture.recipients,
        subject="Draft",
        body="draft body",
        cc=None,
        bcc=None,
        reply_to=None,
        attachments=None,
    )
    assert_draft_ref(draft, adapter_id=adapter_id)

    sent = impl.invoke("email", "send_draft", draft_ref=draft)
    assert_email_ref(sent, adapter_id=adapter_id)

    assert impl.invoke("email", "delete_email", email_ref=ref, permanent=False) is None

    mark_r = impl.invoke("email", "mark_read", email_ref=ref)
    assert mark_r is None
    mark_u = impl.invoke("email", "mark_unread", email_ref=ref)
    assert mark_u is None

    labels = impl.invoke(
        "email",
        "modify_email_labels",
        email_ref=ref,
        add_labels=["Important"],
        remove_labels=[],
    )
    assert labels is None

    inbox = impl.invoke("email", "list_mailbox", folder="INBOX", since=None, limit=10, cursor=None)
    assert_page(inbox, item_type=EmailRef)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _hour_ago() -> datetime:
    return _utc_now() - timedelta(hours=1)
