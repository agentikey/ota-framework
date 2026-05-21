"""AdapterImpl protocol — the runtime contract every adapter exposes.

Adapter authors implement a class (or module-level singleton) that satisfies
this protocol. The class is referenced from the adapter manifest's
`entrypoint` field as `module.path:attribute_name`.

The dispatch layer (`ota_connect.binding.dispatch`) calls `invoke()` for every
verb the routine triggers. `poll_inbound()` is called by the inbound-email
loop (`ota_connect.binding.inbound_email`). `dispatch_action()` is called by
the action callback dispatcher when an upstream UI surfaces an action event
(Slack button click, etc.).

v0.1 design notes:

* `invoke()` is **synchronous**. Verbs in `ota_connect/<capability>/verbs.py`
  are sync; real async adapters (Slack, Gmail in Phase 4) bridge to async
  internally and block at the boundary. Mock adapters and any pure-Python
  in-memory adapter just run sync.
* Only the methods actually used by an adapter need to be implemented. The
  protocol is `runtime_checkable`; default fallbacks raise
  `VerbNotImplementedError` via the registry, not the adapter itself.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable

from ota_core.integration_source.manifest import AdapterManifest


@runtime_checkable
class AdapterImpl(Protocol):
    """Runtime contract for a Connect adapter implementation."""

    manifest: AdapterManifest

    def invoke(self, capability: str, verb: str, /, **kwargs: Any) -> Any:
        """Dispatch a capability verb call to the underlying integration.

        Raises any platform-specific exception; the dispatch layer's error
        normalization wraps it into an `OTAConnectError` subclass before it
        reaches the routine.
        """
        ...

    def poll_inbound(self) -> Iterable[Any]:
        """Yield any new inbound events since the last poll.

        Used by `inbound_email.run_poll_loop` for email adapters; messaging
        adapters that publish their own action callbacks may also implement
        this to surface message events. Should be cheap when no new events
        exist (i.e. return an empty iterable).

        Adapters that don't poll should return an empty list.
        """
        ...
