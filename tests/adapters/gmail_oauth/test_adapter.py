from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pytest_httpx import HTTPXMock

from ota_connect._types import DraftRef, EmailRef, EmailThreadRef, Page
from ota_connect._types.errors import (
    AdapterUnavailable,
    MessageRejected,
    RateLimited,
    RecipientUnreachable,
)
from ota_connect.adapters.gmail_oauth.adapter import (
    GmailAdapterConfig,
    GmailOAuthAdapter,
)

_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _adapter() -> GmailOAuthAdapter:
    return GmailOAuthAdapter(
        config=GmailAdapterConfig(access_token_override="ya29.xyz", integration_id="gmail.com"),
    )


def test_send_email_returns_email_ref(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/messages/send",
        json={"id": "msg-1", "threadId": "thr-1"},
    )
    adapter = _adapter()
    ref = adapter.invoke(
        "email",
        "send_email",
        to=["mailto:bob@example.com"],
        subject="Hi",
        body="body",
        cc=None,
        bcc=None,
        reply_to=None,
        attachments=None,
        importance="normal",
    )
    assert isinstance(ref, EmailRef)
    assert ref.id == "msg-1"
    assert ref.thread is not None
    assert ref.thread.id == "thr-1"
    assert ref.adapter == "gmail_oauth_adapter"


def test_create_draft(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/drafts",
        json={"id": "draft-1", "message": {"id": "msg-1", "threadId": "thr-1"}},
    )
    adapter = _adapter()
    draft = adapter.invoke(
        "email",
        "create_draft",
        to=["mailto:bob@example.com"],
        subject="Draft",
        body="body",
        cc=None,
        bcc=None,
        reply_to=None,
        attachments=None,
    )
    assert isinstance(draft, DraftRef)
    assert draft.id == "draft-1"


def test_send_draft(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/drafts/send",
        json={"id": "msg-1", "threadId": "thr-1"},
    )
    adapter = _adapter()
    sent = adapter.invoke(
        "email",
        "send_draft",
        draft_ref=DraftRef(
            id="draft-1", subject="Hi", created_at=datetime.now(UTC), adapter="gmail_oauth_adapter"
        ),
    )
    assert sent.id == "msg-1"


def test_delete_email_trash_by_default(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/messages/msg-1/trash",
        json={"id": "msg-1"},
    )
    adapter = _adapter()
    ref = EmailRef(
        id="msg-1",
        message_id_header=None,
        thread=None,
        sent_at=datetime.now(UTC),
        adapter="gmail_oauth_adapter",
    )
    assert adapter.invoke("email", "delete_email", email_ref=ref, permanent=False) is None


def test_delete_email_permanent(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/messages/msg-1/delete",
        json={},
    )
    adapter = _adapter()
    ref = EmailRef(
        id="msg-1",
        message_id_header=None,
        thread=None,
        sent_at=datetime.now(UTC),
        adapter="gmail_oauth_adapter",
    )
    assert adapter.invoke("email", "delete_email", email_ref=ref, permanent=True) is None


def test_list_mailbox(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_BASE}/messages?labelIds=INBOX&maxResults=10",
        json={
            "messages": [{"id": "m1", "threadId": "t1"}, {"id": "m2", "threadId": "t2"}],
            "nextPageToken": "ABCDE",
        },
    )
    adapter = _adapter()
    page = adapter.invoke(
        "email", "list_mailbox", folder="INBOX", since=None, limit=10, cursor=None
    )
    assert isinstance(page, Page)
    assert len(page.items) == 2
    assert page.next_cursor == "ABCDE"


def test_read_email_thread(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_BASE}/threads/t1",
        json={
            "id": "t1",
            "messages": [
                {
                    "id": "m1",
                    "internalDate": "1700000000000",
                    "payload": {"headers": [{"name": "Message-ID", "value": "<a@m>"}]},
                },
                {"id": "m2", "internalDate": "1700000001000", "payload": {"headers": []}},
            ],
        },
    )
    adapter = _adapter()
    page = adapter.invoke(
        "email",
        "read_email_thread",
        thread_ref=EmailThreadRef(
            id="t1", subject="x", started_at=datetime.now(UTC), adapter="gmail_oauth_adapter"
        ),
        limit=10,
        cursor=None,
    )
    assert len(page.items) == 2
    assert page.items[0].message_id_header == "<a@m>"


def test_modify_email_labels(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/messages/m1/modify",
        json={"id": "m1"},
    )
    adapter = _adapter()
    ref = EmailRef(
        id="m1",
        message_id_header=None,
        thread=None,
        sent_at=datetime.now(UTC),
        adapter="gmail_oauth_adapter",
    )
    assert (
        adapter.invoke(
            "email",
            "modify_email_labels",
            email_ref=ref,
            add_labels=["Important"],
            remove_labels=["UNREAD"],
        )
        is None
    )


def test_mark_read_calls_modify(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/messages/m1/modify",
        json={"id": "m1"},
    )
    adapter = _adapter()
    ref = EmailRef(
        id="m1",
        message_id_header=None,
        thread=None,
        sent_at=datetime.now(UTC),
        adapter="gmail_oauth_adapter",
    )
    assert adapter.invoke("email", "mark_read", email_ref=ref) is None


def test_429_raises_rate_limited(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/messages/send",
        status_code=429,
        headers={"Retry-After": "60"},
        json={},
    )
    adapter = _adapter()
    with pytest.raises(RateLimited) as exc:
        adapter.invoke(
            "email",
            "send_email",
            to=["mailto:bob@example.com"],
            subject="Hi",
            body="body",
            cc=None,
            bcc=None,
            reply_to=None,
            attachments=None,
            importance="normal",
        )
    assert exc.value.retry_after is not None
    assert exc.value.retry_after.total_seconds() == 60


def test_404_not_found_raises_recipient_unreachable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_BASE}/threads/missing",
        status_code=404,
        json={
            "error": {
                "code": 404,
                "message": "Requested entity was not found.",
                "status": "NOT_FOUND",
            }
        },
    )
    adapter = _adapter()
    with pytest.raises(RecipientUnreachable):
        adapter.invoke(
            "email",
            "read_email_thread",
            thread_ref=EmailThreadRef(
                id="missing",
                subject="x",
                started_at=datetime.now(UTC),
                adapter="gmail_oauth_adapter",
            ),
            limit=10,
            cursor=None,
        )


def test_400_raises_message_rejected(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/messages/send",
        status_code=400,
        json={"error": {"code": 400, "message": "Invalid raw"}},
    )
    adapter = _adapter()
    with pytest.raises(MessageRejected):
        adapter.invoke(
            "email",
            "send_email",
            to=["mailto:bob@example.com"],
            subject="Hi",
            body="body",
            cc=None,
            bcc=None,
            reply_to=None,
            attachments=None,
            importance="normal",
        )


def test_500_raises_adapter_unavailable_retryable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE}/messages/send",
        status_code=503,
        text="oops",
    )
    adapter = _adapter()
    with pytest.raises(AdapterUnavailable) as exc:
        adapter.invoke(
            "email",
            "send_email",
            to=["mailto:bob@example.com"],
            subject="Hi",
            body="body",
            cc=None,
            bcc=None,
            reply_to=None,
            attachments=None,
            importance="normal",
        )
    assert exc.value.retryable is True


def test_unrecognized_identity_raises_recipient_unreachable() -> None:
    adapter = _adapter()
    with pytest.raises(RecipientUnreachable):
        adapter.invoke(
            "email",
            "send_email",
            to=["handle:@bob"],
            subject="Hi",
            body="body",
            cc=None,
            bcc=None,
            reply_to=None,
            attachments=None,
            importance="normal",
        )


def test_tick_inbound_baselines_when_first_called(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_BASE}/profile",
        json={"historyId": "100"},
    )
    adapter = _adapter()
    added = adapter.tick_inbound(routine_id="ota.email_triage")
    assert added == 0
    events = list(adapter.poll_inbound())
    assert events == []


def test_tick_inbound_enqueues_new_messages(httpx_mock: HTTPXMock) -> None:
    # First call: baseline
    httpx_mock.add_response(
        method="GET",
        url=f"{_BASE}/profile",
        json={"historyId": "100"},
    )
    # Second call: history with one new message
    httpx_mock.add_response(
        method="GET",
        url=f"{_BASE}/history?startHistoryId=100",
        json={
            "history": [
                {
                    "messagesAdded": [
                        {
                            "message": {
                                "id": "new-msg",
                                "threadId": "T1",
                                "labelIds": ["INBOX", "UNREAD"],
                            }
                        }
                    ]
                }
            ],
            "historyId": "150",
        },
    )
    adapter = _adapter()
    adapter.tick_inbound(routine_id="ota.email_triage")  # baseline
    added = adapter.tick_inbound(routine_id="ota.email_triage")
    assert added == 1
    events = list(adapter.poll_inbound())
    assert len(events) == 1
    assert events[0].kind == "email.reply_received"
    assert events[0].payload["message_id"] == "new-msg"
