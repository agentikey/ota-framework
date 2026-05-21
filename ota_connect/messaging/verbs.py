# AUTO-GENERATED from vocabulary/messaging.md -- DO NOT EDIT.
# Run `python scripts/gen_vocab_stubs.py` to regenerate.

from __future__ import annotations

from datetime import datetime

from ota_connect._types import (
    Attachment,
    Block,
    ChannelRef,
    Cursor,
    IdentityRef,
    Importance,
    MessageRef,
    Page,
    ThreadRef,
)
from ota_connect.messaging.dispatch import dispatch
from ota_core.policy import verb


@verb(
    idempotency="best_effort",
    required_scopes=["messaging:send"],
    destructive=False,
)
def send_message(
    target: ChannelRef | IdentityRef,
    content: str | list[Block],
    *,
    thread_ref: ThreadRef | None = None,
    attachments: list[Attachment] | None = None,
    importance: Importance = "normal",
) -> MessageRef:
    return dispatch("send_message", **locals())  # type: ignore[no-any-return]


@verb(
    idempotency="best_effort",
    required_scopes=["messaging:modify"],
    destructive=False,
)
def edit_message(
    message_ref: MessageRef,
    new_content: str | list[Block],
) -> MessageRef:
    return dispatch("edit_message", **locals())  # type: ignore[no-any-return]


@verb(
    idempotency="best_effort",
    required_scopes=["messaging:delete"],
    destructive=True,
)
def delete_message(
    message_ref: MessageRef,
) -> None:
    dispatch("delete_message", **locals())


@verb(
    idempotency="guaranteed",
    required_scopes=["messaging:read"],
    destructive=False,
)
def read_thread(
    thread_ref: ThreadRef,
    *,
    limit: int = 100,
    cursor: Cursor | None = None,
) -> Page[MessageRef]:
    return dispatch("read_thread", **locals())  # type: ignore[no-any-return]


@verb(
    idempotency="guaranteed",
    required_scopes=["messaging:read"],
    destructive=False,
)
def list_recent_messages(
    channel: ChannelRef | IdentityRef,
    *,
    since: datetime | None = None,
    limit: int = 50,
    cursor: Cursor | None = None,
) -> Page[MessageRef]:
    return dispatch("list_recent_messages", **locals())  # type: ignore[no-any-return]
