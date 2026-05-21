"""ota_connect.email — capability vocabulary for email send / read / triage.

Verbs are generated from `vocabulary/email.md`; routines import them by
name (e.g. `from ota_connect.email import send_email`).
"""

from ota_connect.email.verbs import (
    create_draft,
    delete_email,
    list_mailbox,
    mark_read,
    mark_unread,
    modify_email_labels,
    read_email_thread,
    send_draft,
    send_email,
)

__all__ = [
    "create_draft",
    "delete_email",
    "list_mailbox",
    "mark_read",
    "mark_unread",
    "modify_email_labels",
    "read_email_thread",
    "send_draft",
    "send_email",
]
