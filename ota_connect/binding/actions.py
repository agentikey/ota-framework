"""Action callback dispatch — route adapter-originated action events to routines.

When an upstream surface (Slack button click, email auto-response, etc.) fires
an action, the adapter normalizes it into an `ActionEvent` envelope and pushes
it into `ActionRouter.dispatch(event)`. The router looks up the routine
handler keyed by `routine_id` and calls it. Audit events are emitted for both
acceptance and unknown-routine drops.

The router does not own routine selection (the conductor does that). It owns
the last-mile delivery from "an action callback arrived" to "the registered
handler runs". HITL gates in Phase 4B build on top of this — a gate
registration installs an ActionRouter handler that drives the gate state
machine.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Literal

from ota_core.audit import AuditSink
from ota_core.contracts.audit_event import Principal
from ota_core.trace import ensure_trace_id

ActionEventKind = Literal[
    "messaging.action_triggered",
    "email.reply_received",
    "email.bounce_received",
    "email.delivery_confirmed",
    "email.auto_response_received",
]

_KIND_TO_EVENT_TYPE: Mapping[ActionEventKind, str] = {
    "messaging.action_triggered": "integration.messaging.action_triggered",
    "email.reply_received": "integration.email.reply_received",
    "email.bounce_received": "integration.email.bounce_received",
    "email.delivery_confirmed": "integration.email.delivery_confirmed",
    "email.auto_response_received": "integration.email.auto_response_received",
}


@dataclass(frozen=True)
class ActionEvent:
    """Normalized envelope for an adapter-originated action.

    `kind` selects the audit `EventType`; `routine_id` is the destination
    handler key. `payload` is the unparsed adapter content (Slack action
    block, RFC822 message JSON, etc.). `correlation_id` ties the action back
    to the original outbound call when available (e.g. the message ID the
    button was attached to).
    """

    kind: ActionEventKind
    routine_id: str
    adapter_id: str
    integration_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None


ActionHandler = Callable[[ActionEvent], None]


class ActionRouter:
    def __init__(self, *, audit_sink: AuditSink, principal: Principal) -> None:
        self._audit = audit_sink
        self._principal = principal
        self._handlers: dict[str, ActionHandler] = {}
        self._lock = Lock()

    def register(self, routine_id: str, handler: ActionHandler) -> None:
        with self._lock:
            self._handlers[routine_id] = handler

    def unregister(self, routine_id: str) -> None:
        with self._lock:
            self._handlers.pop(routine_id, None)

    def dispatch(self, event: ActionEvent) -> bool:
        """Deliver an action event to the registered routine handler.

        Returns True if a handler was found and invoked. False if no handler
        is registered for the routine — the event is still audited so
        operators can see dropped callbacks in the dashboard.
        """
        with self._lock:
            handler = self._handlers.get(event.routine_id)
        event_type = _KIND_TO_EVENT_TYPE[event.kind]
        trace_id = ensure_trace_id()
        payload = {
            "routine_id": event.routine_id,
            "adapter_id": event.adapter_id,
            "integration_id": event.integration_id,
            "correlation_id": event.correlation_id,
            "delivered": handler is not None,
            "trace_id": trace_id,
        }
        self._audit.emit(
            event_type=event_type,  # type: ignore[arg-type]
            severity="info" if handler else "warn",
            principal=self._principal,
            payload=payload,
        )
        if handler is None:
            return False
        handler(event)
        return True
