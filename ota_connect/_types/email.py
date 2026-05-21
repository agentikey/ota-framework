# AUTO-GENERATED from vocabulary/_types.md -- DO NOT EDIT.
# Run `python scripts/gen_vocab_stubs.py` to regenerate.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EmailRef:
    id: str  # adapter-specific (e.g., Gmail message ID)
    message_id_header: str | None  # RFC-5322 Message-ID header value, when present
    thread: EmailThreadRef | None
    sent_at: datetime
    adapter: str


@dataclass(frozen=True)
class EmailThreadRef:
    id: str  # adapter-specific (e.g., Gmail thread ID)
    subject: str  # canonical subject (RFC normalization applied)
    started_at: datetime
    adapter: str


@dataclass(frozen=True)
class DraftRef:
    id: str  # adapter-specific draft ID (e.g., Gmail Draft ID)
    subject: str  # working subject line
    created_at: datetime  # timezone-aware
    adapter: str  # name of the adapter that produced this ref
