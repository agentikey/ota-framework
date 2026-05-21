"""Phase 2 tracer-bullet milestone.

Per build-plan §5.3 Phase 2 milestone:

> a hello-world routine (`ota_routines/hello/routine.md`) is loaded by the
> routine engine, runs on a manual trigger, makes one capability call to a
> mock adapter (built inline for this test), emits an audit event, and the
> AuditSink writes it to JSONL. End-to-end smoke test passes.

This test exercises ~every Phase 2 module at once: RoutineSource (filesystem),
RoutineEngine, L0b enforcer, AuditSink (JSONL), ObservabilitySink, Conductor
(DirectRouter), System wiring, BranchRegistry, LoadManifestResolver, Scheduler
(manual trigger), trace_id propagation, and the @verb decorator.
"""

from __future__ import annotations

import json
from pathlib import Path

from ota_core.audit import FileAuditSink
from ota_core.automation import CronJob, Scheduler
from ota_core.branches import BranchRegistry
from ota_core.conductor import Conductor, DirectRouter, Intent
from ota_core.contracts.audit_event import DeploymentInfo, Principal, SourceInfo
from ota_core.identity import InMemoryIdentityProvider
from ota_core.observability import FileObservabilitySink
from ota_core.policy import L0bEnforcer, verb
from ota_core.routine_source import FilesystemRoutineSource
from ota_core.secrets import InMemorySecretsProvider
from ota_core.storage import Database
from ota_core.systems import (
    Capability,
    LoadManifestResolver,
    RoutineEngine,
    System,
)
from ota_core.trace import TRACE_ID_PATTERN

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTINES_DIR = PROJECT_ROOT / "ota_routines"


def _principal() -> Principal:
    return Principal(id="op:omar", type="operator", display_name="Omar")


def _deployment() -> DeploymentInfo:
    return DeploymentInfo(id="ota-tracer", mode="vps", edition="core", version="0.1.0")


def _source_info() -> SourceInfo:
    return SourceInfo(component="phase2-tracer", version="0.1.0")


@verb(
    idempotency="best_effort",
    required_scopes=["messaging:send"],
    destructive=False,
)
def say_hello(target: str) -> str:
    return f"hello, {target}!"


async def test_tracer_bullet_end_to_end(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    obs_path = tmp_path / "observability.jsonl"
    db_path = tmp_path / "scheduler.db"

    audit_sink = FileAuditSink(audit_dir, deployment=_deployment(), source=_source_info())
    obs_sink = FileObservabilitySink(obs_path)
    l0b = L0bEnforcer(audit_sink=audit_sink, observability=obs_sink)
    routine_source = FilesystemRoutineSource(ROUTINES_DIR)
    identity = InMemoryIdentityProvider([])
    secrets = InMemorySecretsProvider()

    engine = RoutineEngine(
        routine_source=routine_source,
        identity_provider=identity,
        secrets_provider=secrets,
        audit_sink=audit_sink,
        observability=obs_sink,
        l0b=l0b,
    )

    conductor = Conductor(
        router=DirectRouter("ota.hello"),
        engine=engine,
        audit_sink=audit_sink,
        observability=obs_sink,
    )
    conductor.register_routine(
        "ota.hello",
        capabilities={"say_hello": Capability("say_hello", say_hello)},
    )

    branches = BranchRegistry.default(routines=["ota.hello"])
    system = System(
        conductor=conductor,
        branches=branches,
        engine=engine,
        load_manifest_resolver=LoadManifestResolver(routine_source=routine_source),
    )

    db = Database(db_path)
    scheduler = Scheduler(db)
    fired: list[Any] = []

    async def cron_callback() -> None:
        result = await system.dispatch(
            Intent(text="trigger", channel="cron", user_id="scheduler"),
            principal=_principal(),
        )
        fired.append(result)

    scheduler.register_cron(
        CronJob(job_id="hello_daily", expression="0 9 * * *", callback=cron_callback)
    )

    # Manual trigger — the milestone path.
    await scheduler.trigger("hello_daily")

    audit_sink.close()
    obs_sink.close()
    db.close()

    # === Assertions ===

    # 1. The routine actually ran and called the mocked capability.
    assert len(fired) == 1
    result = fired[0]
    assert result.routine_id == "ota.hello"
    assert result.return_value == {"greeted": "world", "message": "hello, world!"}
    assert TRACE_ID_PATTERN.match(result.trace_id)

    # 2. Audit JSONL was written with the expected event chain + trace_id.
    audit_files = list(audit_dir.glob("*.jsonl"))
    assert len(audit_files) == 1
    lines = audit_files[0].read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    event_types = [e["event_type"] for e in events]
    assert "routine.run_started" in event_types
    assert "routine.run_completed" in event_types
    assert "tool_call.invoked" in event_types
    assert "tool_call.succeeded" in event_types

    # 3. trace_id consistent across all events for this run.
    trace_ids = {e["trace_id"] for e in events}
    assert trace_ids == {result.trace_id}

    # 4. tool_call.invoked payload references the say_hello verb + its meta.
    invoked = next(e for e in events if e["event_type"] == "tool_call.invoked")
    assert invoked["payload"]["verb"] == "say_hello"
    assert invoked["payload"]["destructive"] is False
    assert invoked["payload"]["required_scopes"] == ["messaging:send"]

    # 5. routine.run_completed payload reflects tool calls + budget counters.
    completed = next(e for e in events if e["event_type"] == "routine.run_completed")
    assert completed["payload"]["tool_calls_made"] == 1
    assert completed["payload"]["routine_id"] == "ota.hello"

    # 6. Observability JSONL has a routine.run span with the right trace_id.
    obs_lines = obs_path.read_text(encoding="utf-8").splitlines()
    obs_records = [json.loads(line) for line in obs_lines]
    routine_spans = [r for r in obs_records if r["kind"] == "span" and r["name"] == "routine.run"]
    assert len(routine_spans) == 1
    assert routine_spans[0]["trace_id"] == result.trace_id
    assert routine_spans[0]["status"] == "ok"

    # 7. Load manifest resolver derives correct deps for the routine.
    manifest = system.load_manifest_resolver.resolve("ota.hello")
    assert manifest.routine_id == "ota.hello"
    assert manifest.integration_ids == ()

    # 8. Branch wiring — the routine is in the productivity branch.
    assert system.branch_for("ota.hello") == "productivity"

    # 9. Conductor decision is the expected DirectRouter outcome.
    decision = conductor.decide(Intent(text="x", channel="cli", user_id="x"))
    assert decision.routine_id == "ota.hello"
    assert decision.confidence == 1.0


# Import-time sanity that `Any` is in scope for the closure above (mypy hint).
from typing import Any  # noqa: E402
