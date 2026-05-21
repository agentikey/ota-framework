from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from ota_connect._types import Action, Block, ChannelRef, MessageRef, Page, ThreadRef
from ota_connect._types.errors import (
    AdapterUnavailable,
    MessageRejected,
    RateLimited,
    RecipientUnreachable,
)
from ota_connect.adapters.slack_socket.adapter import (
    SlackAdapterConfig,
    SlackSocketAdapter,
)


def _adapter(httpx_mock: HTTPXMock) -> SlackSocketAdapter:
    return SlackSocketAdapter(
        config=SlackAdapterConfig(bot_token_override="xoxb-test", integration_id="slack.com"),
    )


def test_send_message_calls_chat_post_message(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://slack.com/api/chat.postMessage",
        json={
            "ok": True,
            "channel": "C1",
            "ts": "1700000000.000100",
            "message": {"text": "hello", "ts": "1700000000.000100"},
        },
    )
    adapter = _adapter(httpx_mock)
    ref = adapter.invoke(
        "messaging",
        "send_message",
        target=ChannelRef(id="C1", kind="channel", name="general", adapter="slack_socket_adapter"),
        content="hello",
        thread_ref=None,
        attachments=None,
        importance="normal",
    )
    assert isinstance(ref, MessageRef)
    assert ref.id == "1700000000.000100"
    assert ref.channel.id == "C1"
    assert ref.adapter == "slack_socket_adapter"


def test_send_message_with_blocks_renders_payload(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://slack.com/api/chat.postMessage",
        json={"ok": True, "channel": "C1", "ts": "1.0"},
    )
    adapter = _adapter(httpx_mock)
    adapter.invoke(
        "messaging",
        "send_message",
        target=ChannelRef(id="C1", kind="channel", name=None, adapter="slack_socket_adapter"),
        content=[
            Block(kind="section", text="Hi"),
            Block(
                kind="actions",
                actions=[Action(kind="button", label="Approve", value="approve")],
            ),
        ],
        thread_ref=None,
        attachments=None,
        importance="normal",
    )
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    body = requests[0].read().decode()
    assert "section" in body
    assert "actions" in body
    assert "Approve" in body


def test_edit_message(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://slack.com/api/chat.update",
        json={"ok": True, "channel": "C1", "ts": "1.0"},
    )
    adapter = _adapter(httpx_mock)
    ref = MessageRef(
        id="1.0",
        channel=ChannelRef(id="C1", kind="channel", name=None, adapter="slack_socket_adapter"),
        sent_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        permalink=None,
        adapter="slack_socket_adapter",
    )
    new = adapter.invoke("messaging", "edit_message", message_ref=ref, new_content="edited")
    assert new.id == "1.0"


def test_delete_message_returns_none(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://slack.com/api/chat.delete",
        json={"ok": True},
    )
    adapter = _adapter(httpx_mock)
    ref = MessageRef(
        id="1.0",
        channel=ChannelRef(id="C1", kind="channel", name=None, adapter="slack_socket_adapter"),
        sent_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        permalink=None,
        adapter="slack_socket_adapter",
    )
    assert adapter.invoke("messaging", "delete_message", message_ref=ref) is None


def test_list_recent_messages_paginates(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://slack.com/api/conversations.history",
        json={
            "ok": True,
            "messages": [
                {"ts": "1700000001.000100"},
                {"ts": "1700000002.000100"},
            ],
            "response_metadata": {"next_cursor": "next123"},
        },
    )
    adapter = _adapter(httpx_mock)
    page = adapter.invoke(
        "messaging",
        "list_recent_messages",
        channel=ChannelRef(id="C1", kind="channel", name=None, adapter="slack_socket_adapter"),
        since=None,
        limit=10,
        cursor=None,
    )
    assert isinstance(page, Page)
    assert len(page.items) == 2
    assert page.next_cursor == "next123"


def test_read_thread(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://slack.com/api/conversations.replies",
        json={
            "ok": True,
            "messages": [
                {"ts": "1700000001.000100"},
                {"ts": "1700000002.000100"},
            ],
            "response_metadata": {},
        },
    )
    adapter = _adapter(httpx_mock)
    page = adapter.invoke(
        "messaging",
        "read_thread",
        thread_ref=ThreadRef(
            id="1700000001.000100",
            channel=ChannelRef(id="C1", kind="channel", name=None, adapter="slack_socket_adapter"),
            started_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            adapter="slack_socket_adapter",
        ),
        limit=10,
        cursor=None,
    )
    assert len(page.items) == 2
    assert page.next_cursor is None


def test_rate_limited_response_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://slack.com/api/chat.postMessage",
        status_code=429,
        headers={"Retry-After": "30"},
        json={},
    )
    adapter = _adapter(httpx_mock)
    with pytest.raises(RateLimited) as exc_info:
        adapter.invoke(
            "messaging",
            "send_message",
            target=ChannelRef(id="C1", kind="channel", name=None, adapter="slack_socket_adapter"),
            content="hi",
            thread_ref=None,
            attachments=None,
            importance="normal",
        )
    assert exc_info.value.retry_after is not None
    assert exc_info.value.retry_after.total_seconds() == 30


def test_channel_not_found_raises_recipient_unreachable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://slack.com/api/chat.postMessage",
        json={"ok": False, "error": "channel_not_found"},
    )
    adapter = _adapter(httpx_mock)
    with pytest.raises(RecipientUnreachable):
        adapter.invoke(
            "messaging",
            "send_message",
            target=ChannelRef(
                id="CGONE", kind="channel", name=None, adapter="slack_socket_adapter"
            ),
            content="hi",
            thread_ref=None,
            attachments=None,
            importance="normal",
        )


def test_msg_too_long_raises_rejected(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://slack.com/api/chat.postMessage",
        json={"ok": False, "error": "msg_too_long"},
    )
    adapter = _adapter(httpx_mock)
    with pytest.raises(MessageRejected):
        adapter.invoke(
            "messaging",
            "send_message",
            target=ChannelRef(id="C1", kind="channel", name=None, adapter="slack_socket_adapter"),
            content="x" * 999999,
            thread_ref=None,
            attachments=None,
            importance="normal",
        )


def test_500_raises_adapter_unavailable_retryable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://slack.com/api/chat.postMessage",
        status_code=502,
        text="bad gateway",
    )
    adapter = _adapter(httpx_mock)
    with pytest.raises(AdapterUnavailable) as exc_info:
        adapter.invoke(
            "messaging",
            "send_message",
            target=ChannelRef(id="C1", kind="channel", name=None, adapter="slack_socket_adapter"),
            content="hi",
            thread_ref=None,
            attachments=None,
            importance="normal",
        )
    assert exc_info.value.retryable is True


def test_socket_payload_ingest_surfaces_via_poll_inbound() -> None:
    adapter = SlackSocketAdapter(
        config=SlackAdapterConfig(bot_token_override="xoxb-test"),
    )
    adapter.ingest_socket_payload(
        routine_id="ota.email_triage",
        payload={"actions": [{"value": "approve"}], "trigger_id": "T1"},
        correlation_id="T1",
    )
    events = list(adapter.poll_inbound())
    assert len(events) == 1
    assert events[0].routine_id == "ota.email_triage"
    assert events[0].kind == "messaging.action_triggered"
    assert events[0].correlation_id == "T1"


def test_invalid_capability_raises_not_implemented() -> None:
    adapter = SlackSocketAdapter(
        config=SlackAdapterConfig(bot_token_override="xoxb-test"),
    )
    with pytest.raises(NotImplementedError):
        adapter.invoke("email", "send_email")
