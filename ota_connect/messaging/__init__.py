"""ota_connect.messaging — capability vocabulary for chat / DM messaging.

Verbs are generated from `vocabulary/messaging.md`; routines import them by
name (e.g. `from ota_connect.messaging import send_message`).
"""

from ota_connect.messaging.verbs import (
    delete_message,
    edit_message,
    list_recent_messages,
    read_thread,
    send_message,
)

__all__ = [
    "delete_message",
    "edit_message",
    "list_recent_messages",
    "read_thread",
    "send_message",
]
