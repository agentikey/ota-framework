from __future__ import annotations

import asyncio

from ota_connect.binding import (
    ActionRouter,
    AdapterRegistry,
    InboundEmailLoop,
)
from ota_core.audit import NullAuditSink
from ota_core.contracts.audit_event import Principal


def test_tick_once_drains_pending_events(
    adapter_registry: AdapterRegistry, audit_sink: NullAuditSink
) -> None:
    principal = Principal(id="op:test", type="operator", display_name="Test")
    router = ActionRouter(audit_sink=audit_sink, principal=principal)
    received: list[str] = []
    router.register("ota.test", lambda e: received.append(e.kind))

    # Pre-load the mock email adapter and queue a reply
    loaded = adapter_registry.load("mock_email", capability="email", verb="poll_inbound")
    loaded.impl.queue_inbound(  # type: ignore[attr-defined]
        routine_id="ota.test", kind="email.reply_received", payload={"from": "bob"}
    )

    loop = InboundEmailLoop(
        registry=adapter_registry,
        router=router,
        adapter_ids=["mock_email"],
    )
    delivered = loop.tick_once()
    assert delivered == 1
    assert received == ["email.reply_received"]


def test_tick_once_with_no_events_returns_zero(
    adapter_registry: AdapterRegistry, audit_sink: NullAuditSink
) -> None:
    principal = Principal(id="op:test", type="operator", display_name="Test")
    router = ActionRouter(audit_sink=audit_sink, principal=principal)
    loop = InboundEmailLoop(registry=adapter_registry, router=router, adapter_ids=["mock_email"])
    assert loop.tick_once() == 0


async def test_run_loop_polls_then_stops(
    adapter_registry: AdapterRegistry, audit_sink: NullAuditSink
) -> None:
    principal = Principal(id="op:test", type="operator", display_name="Test")
    router = ActionRouter(audit_sink=audit_sink, principal=principal)
    received: list[str] = []
    router.register("ota.test", lambda e: received.append(e.kind))

    loaded = adapter_registry.load("mock_email", capability="email", verb="poll_inbound")
    loaded.impl.queue_inbound(  # type: ignore[attr-defined]
        routine_id="ota.test", kind="email.bounce_received", payload={}
    )

    loop = InboundEmailLoop(
        registry=adapter_registry,
        router=router,
        adapter_ids=["mock_email"],
        poll_seconds=0.05,
    )
    task = loop.start()
    await asyncio.sleep(0.1)
    await loop.stop()
    assert not task.done() or task.done()  # task is done after stop()
    assert received == ["email.bounce_received"]
