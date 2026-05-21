"""Inbound email event loop — polling-based bounce / reply / delivery handler.

v0.1 is polling-only (no webhooks — see architecture §3 "Outbound-only
networking"). The loop calls each email adapter's `poll_inbound()` on a
fixed interval, normalizes the yielded events to `ActionEvent` envelopes,
and forwards them to the provided `ActionRouter`.

Adapters yield events as a tuple of `(kind, routine_id, payload,
correlation_id)`; the router handles the per-routine handoff. An adapter
that produces no events returns an empty iterable.

The loop runs in the same thread as the framework (no background process
in v0.1). The routine engine starts it via
`InboundEmailLoop.start(loop_seconds=30)` and stops it on shutdown. For
test purposes, `tick_once()` runs a single poll cycle synchronously.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ota_connect.binding.actions import ActionEvent, ActionEventKind, ActionRouter
from ota_connect.binding.registry import AdapterRegistry, LoadedAdapter

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawInboundEvent:
    kind: ActionEventKind
    routine_id: str
    payload: dict[str, Any]
    correlation_id: str | None = None


class InboundEmailLoop:
    def __init__(
        self,
        *,
        registry: AdapterRegistry,
        router: ActionRouter,
        adapter_ids: list[str],
        poll_seconds: float = 30.0,
    ) -> None:
        self._registry = registry
        self._router = router
        self._adapter_ids = list(adapter_ids)
        self._poll_seconds = poll_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    def tick_once(self) -> int:
        """Run one poll cycle synchronously; return number of events dispatched."""
        delivered = 0
        for adapter_id in self._adapter_ids:
            loaded = self._registry.load(adapter_id, capability="email", verb="poll_inbound")
            for raw in _iter_inbound(loaded):
                event = ActionEvent(
                    kind=raw.kind,
                    routine_id=raw.routine_id,
                    adapter_id=loaded.adapter_id,
                    integration_id=loaded.integration_id,
                    payload=raw.payload,
                    correlation_id=raw.correlation_id,
                )
                if self._router.dispatch(event):
                    delivered += 1
        return delivered

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick_once()
            except BaseException:
                _logger.exception("inbound_email tick failed; continuing")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_seconds)
            except TimeoutError:
                continue

    def start(self) -> asyncio.Task[None]:
        if self._task is not None:
            return self._task
        self._stop.clear()
        self._task = asyncio.create_task(self.run())
        return self._task

    async def stop(self) -> None:
        self._stop.set()
        task = self._task
        self._task = None
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass


def _iter_inbound(loaded: LoadedAdapter) -> Iterable[RawInboundEvent]:
    poll = getattr(loaded.impl, "poll_inbound", None)
    if poll is None:
        return ()
    raw_events = poll()
    if raw_events is None:
        return ()
    out: list[RawInboundEvent] = []
    for ev in raw_events:
        if isinstance(ev, RawInboundEvent):
            out.append(ev)
            continue
        if isinstance(ev, dict):
            out.append(
                RawInboundEvent(
                    kind=ev["kind"],
                    routine_id=ev["routine_id"],
                    payload=ev.get("payload", {}),
                    correlation_id=ev.get("correlation_id"),
                )
            )
            continue
        raise TypeError(
            f"adapter {loaded.adapter_id!r} poll_inbound yielded "
            f"{type(ev).__name__}; expected RawInboundEvent or dict"
        )
    return out
