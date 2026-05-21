from __future__ import annotations

from ota_core.audit.errors import AuditSinkError
from ota_core.audit.ids import new_event_id
from ota_core.audit.sink import AuditSink, FileAuditSink, NullAuditSink

__all__ = [
    "AuditSink",
    "AuditSinkError",
    "FileAuditSink",
    "NullAuditSink",
    "new_event_id",
]
