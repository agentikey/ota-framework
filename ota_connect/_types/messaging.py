# AUTO-GENERATED from vocabulary/_types.md -- DO NOT EDIT.
# Run `python scripts/gen_vocab_stubs.py` to regenerate.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class MessageRef:
    id: str  # adapter-specific message ID
    channel: ChannelRef  # the channel / DM this message lives in
    sent_at: datetime  # timezone-aware
    permalink: str | None  # adapter-provided permalink if available
    adapter: str  # name of the adapter that produced this ref


@dataclass(frozen=True)
class ThreadRef:
    id: str  # adapter-specific thread ID (e.g., Slack thread_ts)
    channel: ChannelRef
    started_at: datetime
    adapter: str


@dataclass(frozen=True)
class ChannelRef:
    id: str  # adapter-specific channel ID
    kind: Literal["channel", "dm", "group_dm"]
    name: str | None  # display name where applicable; None for DMs in some adapters
    adapter: str
