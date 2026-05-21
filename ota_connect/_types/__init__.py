# AUTO-GENERATED from vocabulary/_types.md -- DO NOT EDIT.
# Run `python scripts/gen_vocab_stubs.py` to regenerate.

from ota_connect._types.content import (
    Action,
    Attachment,
    Block,
    FileRef,
)
from ota_connect._types.email import (
    DraftRef,
    EmailRef,
    EmailThreadRef,
)
from ota_connect._types.enums import (
    DeliveryStatus,
    Importance,
)
from ota_connect._types.errors import (
    AdapterMismatchError,
    AdapterUnavailable,
    CapabilityDegraded,
    IdentityResolveError,
    MessageRejected,
    OTAConnectError,
    RateLimited,
    RecipientUnreachable,
)
from ota_connect._types.identity import IdentityRef
from ota_connect._types.messaging import (
    ChannelRef,
    MessageRef,
    ThreadRef,
)
from ota_connect._types.pagination import (
    Cursor,
    Page,
)

__all__ = [
    "Action",
    "AdapterMismatchError",
    "AdapterUnavailable",
    "Attachment",
    "Block",
    "CapabilityDegraded",
    "ChannelRef",
    "Cursor",
    "DeliveryStatus",
    "DraftRef",
    "EmailRef",
    "EmailThreadRef",
    "FileRef",
    "IdentityRef",
    "IdentityResolveError",
    "Importance",
    "MessageRef",
    "MessageRejected",
    "OTAConnectError",
    "Page",
    "RateLimited",
    "RecipientUnreachable",
    "ThreadRef",
]
