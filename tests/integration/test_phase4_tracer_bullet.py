"""Phase 4 tracer bullet (backend variant).

The full Phase 4 milestone (per build-plan §5.5) is a real end-to-end run
of the `email_triage` routine against live Slack + Gmail. We can't do that
in CI without OAuth apps, so this backend tracer exercises every shipped
component over HTTP-mocked Slack + Gmail:

1. Boot the dashboard's seams (audit reader/sink, gate manager, triage state).
2. Install the gmail + slack adapters into an `AdapterRegistry` with token
   overrides (no live OAuth).
3. Wire a `DispatchContext` so the binding layer can route messaging / email
   verb calls.
4. Inside an L0b `routine_run`:
     - Call `email.send_email` → Gmail mock returns an `EmailRef`.
     - Call `messaging.send_message` → Slack mock returns a `MessageRef`.
     - Propose a `draft_review` gate to the `GateManager`.
5. Operator decides on the gate via the dashboard's HTTP endpoint.
6. Audit log captures the chain with a consistent trace_id; `/why <email_id>`
   returns the join of triage decisions + audit events.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock

from ota_connect._types import ChannelRef
from ota_connect.adapters.gmail_oauth.adapter import (
    GmailAdapterConfig,
    GmailOAuthAdapter,
)
from ota_connect.adapters.slack_socket.adapter import (
    SlackAdapterConfig,
    SlackSocketAdapter,
)
from ota_connect.binding import (
    AdapterRegistry,
    BindingResolver,
    Bindings,
    DispatchContext,
    dispatch_context,
)
from ota_connect.email import send_email
from ota_connect.messaging import send_message
from ota_core.audit import FileAuditReader, FileAuditSink, NullAuditSink
from ota_core.contracts.audit_event import DeploymentInfo, Principal, SourceInfo
from ota_core.integration_source.source import FilesystemIntegrationSource
from ota_core.policy import L0bEnforcer, RoutineRunContext
from ota_core.policy.gates import GateManager, GateProposal, GateStore
from ota_core.storage.database import Database
from ota_dashboard_api.app import DashboardState, create_app
from ota_routines.email_triage.helpers import WhyLookup
from ota_routines.email_triage.state import EmailTriageState

_GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
_SLACK = "https://slack.com/api"


def _deployment() -> DeploymentInfo:
    return DeploymentInfo(id="d", mode="vps", edition="core", version="0.1.0")


def _source() -> SourceInfo:
    return SourceInfo(component="test", version="0.1.0")


def _principal() -> Principal:
    return Principal(id="op:test", type="operator", display_name="Test")


def test_phase4_tracer_bullet(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    # Mock outbound Slack + Gmail
    httpx_mock.add_response(
        method="POST",
        url=f"{_GMAIL}/messages/send",
        json={"id": "m-1", "threadId": "t-1"},
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{_SLACK}/chat.postMessage",
        json={"ok": True, "channel": "C1", "ts": "1.0"},
    )

    # Set up seams
    audit_dir = tmp_path / "audit"
    audit_sink = FileAuditSink(audit_dir, deployment=_deployment(), source=_source())
    audit_reader = FileAuditReader(audit_dir)
    triage_db = Database(tmp_path / "triage.db")
    triage_state = EmailTriageState(triage_db, trust_threshold=3)
    gate_db = Database(tmp_path / "gates.db")
    gate_manager = GateManager(
        store=GateStore(gate_db),
        audit_sink=NullAuditSink(deployment=_deployment(), source=_source()),
        principal=_principal(),
    )

    # Build an AdapterRegistry with our two real adapters via factory injection
    adapters_dir = tmp_path / "adapters"
    adapters_dir.mkdir()
    src = FilesystemIntegrationSource([adapters_dir])
    registry = AdapterRegistry(src)

    # Drop in two minimal manifest dirs so discovery sees them
    for adapter_id, integration_id, capability in (
        ("slack_socket_adapter", "slack.com", "messaging"),
        ("gmail_oauth_adapter", "gmail.com", "email"),
    ):
        d = adapters_dir / adapter_id
        d.mkdir()
        (d / "manifest.yaml").write_text(
            f"""schema_version: 0.1.0
adapter_id: {adapter_id}
integration_id: {integration_id}
version: 0.1.0
framework_compat: ">=0.1.0"
capabilities:
  - capability: {capability}
    version: 0.1.0
auth_styles:
  - oauth2
""",
            encoding="utf-8",
        )

    registry.register_factory(
        "slack_socket_adapter",
        lambda bundle: SlackSocketAdapter(
            bundle=bundle,
            config=SlackAdapterConfig(bot_token_override="xoxb"),
        ),
    )
    registry.register_factory(
        "gmail_oauth_adapter",
        lambda bundle: GmailOAuthAdapter(
            bundle=bundle,
            config=GmailAdapterConfig(access_token_override="ya29"),
        ),
    )

    bindings = Bindings(
        capabilities={"messaging": "slack_socket_adapter", "email": "gmail_oauth_adapter"}
    )
    resolver = BindingResolver(bindings)
    dctx = DispatchContext(resolver=resolver, registry=registry)

    enforcer = L0bEnforcer(audit_sink=audit_sink)
    ctx = RoutineRunContext(
        routine_id="ota.email-triage",
        routine_run_id="11111111-1111-7111-8111-111111111111",
        trace_id="a" * 32,
        principal=_principal(),
        allowed_integrations=frozenset({"slack.com", "gmail.com"}),
        declared_scopes={
            "slack.com": frozenset({"messaging:send", "messaging:read"}),
            "gmail.com": frozenset({"email:send", "email:read", "email:modify"}),
        },
    )

    with dispatch_context(dctx):
        with enforcer.routine_run(ctx):
            email_ref = send_email(
                to=["mailto:bob@example.com"],
                subject="Hi",
                body="Hello there",
            )
            assert email_ref.id == "m-1"
            slack_ref = send_message(
                target=ChannelRef(
                    id="C1", kind="channel", name="approvals", adapter="slack_socket_adapter"
                ),
                content="Draft ready for review",
            )
            assert slack_ref.id == "1.0"
            triage_state.record_decision(
                routine_run_id=ctx.routine_run_id,
                email_id="incoming-1",
                action="drafted",
                category="inquiry",
                template="inquiry",
                payload={"subject": "Hi", "body": "Hello there", "ref": email_ref.id},
            )
            gate_instance = gate_manager.propose_for_review(
                GateProposal(
                    routine_id="ota.email-triage",
                    routine_run_id=ctx.routine_run_id,
                    gate_id="draft_review",
                    approval_modes=("approve", "tune_and_approve"),
                    kind="preview",
                    summary="Reply to bob@example.com",
                    payload={"subject": "Hi", "body": "Hello there"},
                )
            )
    audit_sink.close()

    # Operator approves via the dashboard
    dashboard_state = DashboardState(
        audit_reader=audit_reader,
        gate_manager=gate_manager,
        triage_state=triage_state,
        routines_installed=("ota.email-triage",),
    )
    client = TestClient(create_app(dashboard_state))
    r = client.post(f"/api/v1/approvals/{gate_instance.id}/decide", json={"action": "approve"})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    # /why returns a chronological trail for the email
    r = client.get("/api/v1/why/incoming-1")
    assert r.status_code == 200
    entries = r.json()["entries"]
    kinds = [e["kind"] for e in entries]
    assert "decision.drafted" in kinds

    # Audit log captured the full chain under the same trace_id
    chain = WhyLookup(triage_state, audit_reader).lookup("incoming-1")
    assert any(e.kind == "decision.drafted" for e in chain)
    all_events = list(audit_reader.by_routine_run(ctx.routine_run_id))
    assert all(e.trace_id == ctx.trace_id for e in all_events)
    assert any(e.event_type == "tool_call.invoked" for e in all_events)
    assert any(e.event_type == "tool_call.succeeded" for e in all_events)
