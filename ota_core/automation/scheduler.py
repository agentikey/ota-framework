from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ota_core.automation.cron import CronExpression
from ota_core.automation.errors import DuplicateJobError, UnknownJobError
from ota_core.storage.database import Database
from ota_core.storage.schema import Migration, apply_pending

CronCallback = Callable[[], Awaitable[None]]
EventCallback = Callable[[dict[str, Any]], Awaitable[None]]

_DEFAULT_CRON_TABLE = """\
CREATE TABLE cron_jobs (
    job_id TEXT PRIMARY KEY,
    expression TEXT NOT NULL,
    next_fire_at TEXT NOT NULL,
    last_fire_at TEXT,
    last_status TEXT,
    payload TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

_DEFAULT_EVENT_TABLE = """\
CREATE TABLE event_hooks (
    hook_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    debounce_ms INTEGER NOT NULL DEFAULT 0,
    last_fire_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

_MIGRATIONS: tuple[Migration, ...] = (
    Migration(name="automation/001_cron_jobs", statements=(_DEFAULT_CRON_TABLE,)),
    Migration(name="automation/002_event_hooks", statements=(_DEFAULT_EVENT_TABLE,)),
)


def register_schema(db: Database) -> list[str]:
    return apply_pending(db, _MIGRATIONS)


@dataclass
class CronJob:
    job_id: str
    expression: str
    callback: CronCallback
    payload: dict[str, Any] = field(default_factory=dict)
    _parsed: CronExpression | None = field(default=None, init=False, repr=False)

    @property
    def parsed(self) -> CronExpression:
        if self._parsed is None:
            self._parsed = CronExpression.parse(self.expression)
        return self._parsed


@dataclass
class EventHook:
    hook_id: str
    event_type: str
    callback: EventCallback
    debounce: timedelta | None = None
    last_fire_at: datetime | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Scheduler:
    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], datetime] = _utc_now,
        tick_interval: float = 1.0,
    ) -> None:
        self._db = database
        self._clock = clock
        self._tick_interval = tick_interval
        self._cron: dict[str, CronJob] = {}
        self._events: dict[str, EventHook] = {}
        self._loop_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        register_schema(database)

    def register_cron(self, job: CronJob) -> None:
        if job.job_id in self._cron:
            raise DuplicateJobError(job.job_id)
        # Validate expression up front.
        _ = job.parsed
        self._cron[job.job_id] = job
        next_fire = job.parsed.next_after(self._clock())
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cron_jobs (job_id, expression, next_fire_at, payload) "
                "VALUES (?, ?, ?, ?)",
                (
                    job.job_id,
                    job.expression,
                    next_fire.isoformat(),
                    json.dumps(job.payload, separators=(",", ":")),
                ),
            )

    def deregister_cron(self, job_id: str) -> None:
        if job_id not in self._cron:
            raise UnknownJobError(job_id)
        del self._cron[job_id]
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM cron_jobs WHERE job_id = ?", (job_id,))

    def register_event_hook(self, hook: EventHook) -> None:
        if hook.hook_id in self._events:
            raise DuplicateJobError(hook.hook_id)
        self._events[hook.hook_id] = hook
        debounce_ms = int(hook.debounce.total_seconds() * 1000) if hook.debounce else 0
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO event_hooks (hook_id, event_type, debounce_ms) "
                "VALUES (?, ?, ?)",
                (hook.hook_id, hook.event_type, debounce_ms),
            )

    def deregister_event_hook(self, hook_id: str) -> None:
        if hook_id not in self._events:
            raise UnknownJobError(hook_id)
        del self._events[hook_id]
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM event_hooks WHERE hook_id = ?", (hook_id,))

    def list_cron(self) -> list[CronJob]:
        return list(self._cron.values())

    def list_event_hooks(self) -> list[EventHook]:
        return list(self._events.values())

    async def trigger(self, job_id: str) -> None:
        job = self._cron.get(job_id)
        if job is None:
            raise UnknownJobError(job_id)
        await self._fire_cron(job)

    async def fire_event(self, event_type: str, payload: dict[str, Any]) -> int:
        fired = 0
        now = self._clock()
        for hook in list(self._events.values()):
            if hook.event_type != event_type:
                continue
            if hook.debounce is not None and hook.last_fire_at is not None:
                if (now - hook.last_fire_at) < hook.debounce:
                    continue
            await hook.callback(payload)
            hook.last_fire_at = now
            with self._db.transaction() as conn:
                conn.execute(
                    "UPDATE event_hooks SET last_fire_at = ? WHERE hook_id = ?",
                    (now.isoformat(), hook.hook_id),
                )
            fired += 1
        return fired

    async def start(self) -> None:
        if self._loop_task is not None:
            return
        self._stop.clear()
        self._loop_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._loop_task is None:
            return
        self._stop.set()
        await self._loop_task
        self._loop_task = None

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            await self._tick()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval)
            except TimeoutError:
                continue

    async def _tick(self) -> None:
        now = self._clock()
        due_rows = self._fetch_due_jobs(now)
        for row in due_rows:
            job = self._cron.get(row["job_id"])
            if job is None:
                continue
            await self._fire_cron(job)

    def _fetch_due_jobs(self, now: datetime) -> list[sqlite3.Row]:
        conn = self._db.connect()
        cursor = conn.execute(
            "SELECT job_id, next_fire_at FROM cron_jobs WHERE next_fire_at <= ?",
            (now.isoformat(),),
        )
        return list(cursor.fetchall())

    async def _fire_cron(self, job: CronJob) -> None:
        now = self._clock()
        status = "succeeded"
        error: BaseException | None = None
        try:
            await job.callback()
        except BaseException as exc:
            status = "failed"
            error = exc
        next_fire = job.parsed.next_after(self._clock())
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE cron_jobs SET last_fire_at = ?, last_status = ?, next_fire_at = ? "
                "WHERE job_id = ?",
                (now.isoformat(), status, next_fire.isoformat(), job.job_id),
            )
        if error is not None:
            raise error
