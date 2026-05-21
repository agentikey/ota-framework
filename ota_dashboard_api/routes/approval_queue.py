"""Approval queue — list pending HITL gates, decide on them."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from ota_core.policy.gates import GateDecision
from ota_dashboard_api.app import DashboardState, dashboard_state
from ota_dashboard_api.models import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalQueueItem,
    ApprovalQueueListResponse,
)

router = APIRouter()


def _to_model(instance: Any) -> ApprovalQueueItem:
    return ApprovalQueueItem(
        id=instance.id,
        routine_id=instance.routine_id,
        routine_run_id=instance.routine_run_id,
        gate_id=instance.gate_id,
        status=instance.status,
        summary=instance.summary or "",
        kind=instance.kind,
        payload=instance.proposal,
        similarity_key=instance.similarity_key,
        expires_at=instance.expires_at,
        created_at=instance.created_at,
    )


@router.get("/approvals", response_model=ApprovalQueueListResponse)
def list_approvals(
    routine_id: str | None = None,
    state: DashboardState = Depends(dashboard_state),
) -> ApprovalQueueListResponse:
    if state.gate_manager is None:
        return ApprovalQueueListResponse(items=[])
    instances = state.gate_manager._store.list_pending(routine_id)
    return ApprovalQueueListResponse(items=[_to_model(i) for i in instances])


@router.get("/approvals/recent", response_model=ApprovalQueueListResponse)
def list_recent(
    limit: int = 50,
    state: DashboardState = Depends(dashboard_state),
) -> ApprovalQueueListResponse:
    if state.gate_manager is None:
        return ApprovalQueueListResponse(items=[])
    instances = state.gate_manager._store.list_recent(limit)
    return ApprovalQueueListResponse(items=[_to_model(i) for i in instances])


@router.post("/approvals/{gate_pk}/decide", response_model=ApprovalDecisionResponse)
def decide(
    gate_pk: str,
    request: ApprovalDecisionRequest,
    state: DashboardState = Depends(dashboard_state),
) -> ApprovalDecisionResponse:
    if state.gate_manager is None:
        raise HTTPException(503, "gate manager not configured")
    status_map = {
        "approve": "approved",
        "reject": "rejected",
        "edit_and_approve": "modified_and_approved",
        "remember_and_approve": "approved",
    }
    approval_mode_map = {
        "approve": "approve",
        "reject": "approve",
        "edit_and_approve": "tune_and_approve",
        "remember_and_approve": "approve_and_remember",
    }
    decision = GateDecision(
        status=status_map[request.action],  # type: ignore[arg-type]
        result_payload=request.edits,
        reason=request.reason,
    )
    try:
        updated = state.gate_manager.decide(
            gate_pk,
            decision=decision,
            approval_mode=approval_mode_map[request.action],  # type: ignore[arg-type]
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    assert updated.decided_at is not None
    return ApprovalDecisionResponse(
        id=updated.id, status=updated.status, decided_at=updated.decided_at
    )


@router.websocket("/approvals/stream")
async def approvals_stream(
    websocket: WebSocket,
) -> None:
    """Sub-5s real-time stream of new approvals.

    v0.1 implementation polls the store on a short interval and pushes new
    items. Phase 5 will swap this for a Postgres LISTEN/NOTIFY or in-process
    pub/sub when persistence moves off SQLite.
    """
    import asyncio

    await websocket.accept()
    state: DashboardState = websocket.app.state.dashboard
    seen: set[str] = set()
    try:
        while True:
            if state.gate_manager is not None:
                items = state.gate_manager._store.list_pending()
                for item in items:
                    if item.id not in seen:
                        seen.add(item.id)
                        await websocket.send_json({"event": "approval.new", "id": item.id})
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        return
