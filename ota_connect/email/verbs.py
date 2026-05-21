# AUTO-GENERATED from vocabulary/email.md -- DO NOT EDIT.
# Run `python scripts/gen_vocab_stubs.py` to regenerate.

from __future__ import annotations

from datetime import datetime

from ota_connect._types import (
    Attachment,
    Block,
    Cursor,
    DraftRef,
    EmailRef,
    EmailThreadRef,
    IdentityRef,
    Importance,
    Page,
)
from ota_connect.email.dispatch import dispatch
from ota_core.policy import verb


@verb(
    idempotency="best_effort",
    required_scopes=["email:send"],
    destructive=False,
)
def send_email(
    to: list[IdentityRef],
    subject: str,
    body: str | list[Block],
    *,
    cc: list[IdentityRef] | None = None,
    bcc: list[IdentityRef] | None = None,
    reply_to: EmailRef | None = None,
    attachments: list[Attachment] | None = None,
    importance: Importance = "normal",
) -> EmailRef:
    return dispatch("send_email", **locals())


@verb(
    idempotency="best_effort",
    required_scopes=["email:modify"],
    destructive=False,
)
def create_draft(
    to: list[IdentityRef],
    subject: str,
    body: str | list[Block],
    *,
    cc: list[IdentityRef] | None = None,
    bcc: list[IdentityRef] | None = None,
    reply_to: EmailRef | None = None,
    attachments: list[Attachment] | None = None,
) -> DraftRef:
    return dispatch("create_draft", **locals())


@verb(
    idempotency="best_effort",
    required_scopes=["email:send"],
    destructive=False,
)
def send_draft(
    draft_ref: DraftRef,
) -> EmailRef:
    return dispatch("send_draft", **locals())


@verb(
    idempotency="best_effort",
    required_scopes=["email:delete"],
    destructive=True,
)
def delete_email(
    email_ref: EmailRef,
    *,
    permanent: bool = False,
) -> None:
    dispatch("delete_email", **locals())


@verb(
    idempotency="guaranteed",
    required_scopes=["email:read"],
    destructive=False,
)
def list_mailbox(
    folder: str,
    *,
    since: datetime | None = None,
    limit: int = 25,
    cursor: Cursor | None = None,
) -> Page[EmailRef]:
    return dispatch("list_mailbox", **locals())


@verb(
    idempotency="guaranteed",
    required_scopes=["email:read"],
    destructive=False,
)
def read_email_thread(
    thread_ref: EmailThreadRef,
    *,
    limit: int = 50,
    cursor: Cursor | None = None,
) -> Page[EmailRef]:
    return dispatch("read_email_thread", **locals())


@verb(
    idempotency="best_effort",
    required_scopes=["email:modify"],
    destructive=False,
)
def modify_email_labels(
    email_ref: EmailRef,
    add_labels: list[str],
    remove_labels: list[str],
) -> None:
    dispatch("modify_email_labels", **locals())


@verb(
    idempotency="guaranteed",
    required_scopes=["email:modify"],
    destructive=False,
)
def mark_read(
    email_ref: EmailRef,
) -> None:
    dispatch("mark_read", **locals())


@verb(
    idempotency="guaranteed",
    required_scopes=["email:modify"],
    destructive=False,
)
def mark_unread(
    email_ref: EmailRef,
) -> None:
    dispatch("mark_unread", **locals())
