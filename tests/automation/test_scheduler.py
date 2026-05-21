from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ota_core.automation import (
    CronJob,
    DuplicateJobError,
    EventHook,
    Scheduler,
    UnknownJobError,
    register_schema,
)
from ota_core.storage import Database


def _db(tmp_path: Path) -> Database:
    return Database(tmp_path / "scheduler.db")


def test_register_schema_idempotent(tmp_path: Path) -> None:
    db = _db(tmp_path)
    applied = register_schema(db)
    assert len(applied) == 2
    again = register_schema(db)
    assert again == []
    db.close()


async def test_manual_trigger_invokes_callback(tmp_path: Path) -> None:
    db = _db(tmp_path)
    scheduler = Scheduler(db)
    fired: list[str] = []

    async def callback() -> None:
        fired.append("hit")

    scheduler.register_cron(CronJob(job_id="job1", expression="* * * * *", callback=callback))
    await scheduler.trigger("job1")
    assert fired == ["hit"]
    db.close()


async def test_manual_trigger_unknown_job(tmp_path: Path) -> None:
    db = _db(tmp_path)
    scheduler = Scheduler(db)
    with pytest.raises(UnknownJobError):
        await scheduler.trigger("ghost")
    db.close()


async def test_duplicate_registration_raises(tmp_path: Path) -> None:
    db = _db(tmp_path)
    scheduler = Scheduler(db)

    async def cb() -> None: ...

    scheduler.register_cron(CronJob("job", "* * * * *", cb))
    with pytest.raises(DuplicateJobError):
        scheduler.register_cron(CronJob("job", "* * * * *", cb))
    db.close()


async def test_deregister_cron(tmp_path: Path) -> None:
    db = _db(tmp_path)
    scheduler = Scheduler(db)

    async def cb() -> None: ...

    scheduler.register_cron(CronJob("job", "* * * * *", cb))
    scheduler.deregister_cron("job")
    assert scheduler.list_cron() == []
    db.close()


async def test_event_hook_fires(tmp_path: Path) -> None:
    db = _db(tmp_path)
    scheduler = Scheduler(db)
    received: list[dict] = []

    async def cb(payload: dict) -> None:
        received.append(payload)

    scheduler.register_event_hook(
        EventHook(hook_id="h1", event_type="integration.gmail.message_received", callback=cb)
    )
    fired = await scheduler.fire_event("integration.gmail.message_received", {"email_id": "e1"})
    assert fired == 1
    assert received == [{"email_id": "e1"}]
    db.close()


async def test_event_hook_debounce_blocks_rapid_refire(tmp_path: Path) -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    current = [now]

    def clock() -> datetime:
        return current[0]

    db = _db(tmp_path)
    scheduler = Scheduler(db, clock=clock)
    fired: list[dict] = []

    async def cb(payload: dict) -> None:
        fired.append(payload)

    scheduler.register_event_hook(
        EventHook(hook_id="h1", event_type="x", callback=cb, debounce=timedelta(seconds=30))
    )
    await scheduler.fire_event("x", {})
    current[0] = now + timedelta(seconds=10)
    await scheduler.fire_event("x", {})
    assert len(fired) == 1
    current[0] = now + timedelta(seconds=31)
    await scheduler.fire_event("x", {})
    assert len(fired) == 2
    db.close()


async def test_event_hook_ignores_other_event_types(tmp_path: Path) -> None:
    db = _db(tmp_path)
    scheduler = Scheduler(db)

    async def cb(payload: dict) -> None: ...

    scheduler.register_event_hook(EventHook("h", "a", cb))
    assert await scheduler.fire_event("b", {}) == 0
    db.close()


async def test_cron_state_persists_to_db(tmp_path: Path) -> None:
    fixed = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    db = _db(tmp_path)
    scheduler = Scheduler(db, clock=lambda: fixed)

    async def cb() -> None: ...

    scheduler.register_cron(CronJob("j", "*/15 * * * *", cb))
    conn = db.connect()
    row = conn.execute("SELECT job_id, expression, next_fire_at FROM cron_jobs").fetchone()
    assert row["job_id"] == "j"
    assert row["expression"] == "*/15 * * * *"
    assert row["next_fire_at"] == "2026-05-20T12:15:00+00:00"
    db.close()


async def test_run_loop_fires_due_jobs(tmp_path: Path) -> None:
    # Drive clock forward inside the loop.
    base = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    counter = [0]

    def clock() -> datetime:
        return base + timedelta(seconds=counter[0])

    db = _db(tmp_path)
    scheduler = Scheduler(db, clock=clock, tick_interval=0.01)
    fired: list[datetime] = []

    async def cb() -> None:
        fired.append(clock())

    scheduler.register_cron(CronJob("j", "* * * * *", cb))
    await scheduler.start()
    counter[0] = 65  # advance to 12:01:05 — past next 12:01:00 fire
    await asyncio.sleep(0.05)
    await scheduler.stop()
    assert fired, "scheduler should have fired the cron job at least once"
    db.close()


async def test_cron_failure_persists_status_and_reraises(tmp_path: Path) -> None:
    base = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    db = _db(tmp_path)
    scheduler = Scheduler(db, clock=lambda: base)

    async def cb() -> None:
        raise RuntimeError("boom")

    scheduler.register_cron(CronJob("j", "* * * * *", cb))
    with pytest.raises(RuntimeError):
        await scheduler.trigger("j")
    conn = db.connect()
    row = conn.execute("SELECT last_status FROM cron_jobs WHERE job_id='j'").fetchone()
    assert row["last_status"] == "failed"
    db.close()


async def test_event_hook_deregister(tmp_path: Path) -> None:
    db = _db(tmp_path)
    scheduler = Scheduler(db)

    async def cb(p: dict) -> None: ...

    scheduler.register_event_hook(EventHook("h", "x", cb))
    scheduler.deregister_event_hook("h")
    assert scheduler.list_event_hooks() == []
    db.close()


async def test_register_invalid_cron_raises_immediately(tmp_path: Path) -> None:
    db = _db(tmp_path)
    scheduler = Scheduler(db)

    async def cb() -> None: ...

    from ota_core.automation.cron import CronParseError

    with pytest.raises(CronParseError):
        scheduler.register_cron(CronJob("j", "not a cron", cb))
    db.close()
