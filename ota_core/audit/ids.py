from __future__ import annotations

import secrets
import time
import uuid

_UUID_V7_VERSION = 0x7
_UUID_V7_VARIANT = 0b10


def new_event_id() -> str:
    ts_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    int128 = (
        (ts_ms << 80)
        | (_UUID_V7_VERSION << 76)
        | (rand_a << 64)
        | (_UUID_V7_VARIANT << 62)
        | rand_b
    )
    return str(uuid.UUID(int=int128))
