"""Routine-side helpers for `email_triage`.

Three responsibilities:

* **Dedup hashing** — `content_hash(subject, body, sender)` → stable hash a
  retry of the same inbound message produces the same key for. Used by
  `EmailTriageState.mark_processed`.

* **Trust-promotion + drift bookkeeping** — `TrustPromotion` wraps
  `EmailTriageState` with the two pieces of business logic the routine
  doesn't care to inline (when to auto-send vs draft; when to flag drift).
  The `DriftDetector` runs as a periodic check and writes a critical-banner
  notification when ratios shift past the configured thresholds.

* **/why lookup handler** — `WhyLookup.lookup(email_id)` returns a
  human-readable trace of decisions for a single email, drawing from the
  audit reader and the per-instance decision log.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from ota_core.audit.reader import AuditFilter, AuditReader
from ota_routines.email_triage.state import (
    EmailTriageState,
    TemplateTrust,
    TriageDecisionRecord,
)


def content_hash(*, subject: str, body: str, sender: str) -> str:
    """Stable hash for dedup. Whitespace-normalized to survive trailing-space drift."""
    norm_subject = " ".join(subject.split()).lower()
    norm_body = " ".join(body.split()).lower()
    norm_sender = sender.strip().lower()
    digest = hashlib.sha256()
    digest.update(norm_subject.encode("utf-8"))
    digest.update(b"|")
    digest.update(norm_body.encode("utf-8"))
    digest.update(b"|")
    digest.update(norm_sender.encode("utf-8"))
    return digest.hexdigest()


@dataclass(frozen=True)
class SendDecision:
    """Outcome of the trust check for a single proposal.

    `auto_send` is true only when the template has opt-in + threshold met.
    `requires_approval` is true when `auto_send` is false (every other case).
    """

    template: str
    auto_send: bool
    requires_approval: bool
    trust: TemplateTrust


class TrustPromotion:
    """Wraps `EmailTriageState` with the auto-send / approval policy."""

    def __init__(
        self,
        state: EmailTriageState,
        *,
        allowed_auto_send_templates: Iterable[str] = (),
    ) -> None:
        self._state = state
        self._allowed: frozenset[str] = frozenset(allowed_auto_send_templates)
        for template in self._allowed:
            self._state.opt_in_auto_send(template, enabled=True)

    def evaluate(self, template: str) -> SendDecision:
        trust = self._state.trust(template)
        in_allowlist = template in self._allowed
        opted_in = trust.opt_in_auto_send or in_allowlist
        threshold_met = trust.consecutive_unedited >= self._state.trust_threshold
        auto_send = trust.auto_send_enabled or (opted_in and threshold_met)
        return SendDecision(
            template=template,
            auto_send=auto_send,
            requires_approval=not auto_send,
            trust=trust,
        )

    def record_approval(self, template: str) -> TemplateTrust:
        return self._state.record_unedited_approval(template)

    def record_edit(self, template: str, *, email_id: str) -> TemplateTrust:
        return self._state.record_edit(template, email_id=email_id)


@dataclass(frozen=True)
class DriftSignal:
    kind: str
    template: str | None
    ratio: float
    threshold: float
    samples: int
    message: str


@dataclass(frozen=True)
class DriftConfig:
    window_hours: int = 24
    processed_skip_ratio_alarm: float = 0.4
    draft_send_ratio_alarm: float = 0.3


class DriftDetector:
    """Computes drift signals over the recent decision log.

    Returns a list of signals; an empty list means nothing exceeded thresholds.
    Callers (the dashboard's critical banner or the routine's scheduled hook)
    convert these into operator notifications.
    """

    def __init__(self, state: EmailTriageState, *, config: DriftConfig | None = None) -> None:
        self._state = state
        self._config = config or DriftConfig()

    def evaluate(self) -> list[DriftSignal]:
        window = timedelta(hours=self._config.window_hours)
        decisions = self._state.recent_decisions(within=window)
        if not decisions:
            return []
        signals: list[DriftSignal] = []
        per_action: dict[str, int] = {}
        per_template: dict[str, dict[str, int]] = {}
        for d in decisions:
            per_action[d.action] = per_action.get(d.action, 0) + 1
            if d.template is not None:
                pt = per_template.setdefault(d.template, {})
                pt[d.action] = pt.get(d.action, 0) + 1
        processed = (
            per_action.get("drafted", 0)
            + per_action.get("auto_sent", 0)
            + per_action.get("approved", 0)
        )
        skipped = per_action.get("skipped", 0)
        if processed + skipped > 0:
            skip_ratio = skipped / max(1, processed + skipped)
            if skip_ratio > self._config.processed_skip_ratio_alarm:
                signals.append(
                    DriftSignal(
                        kind="skip_ratio_high",
                        template=None,
                        ratio=skip_ratio,
                        threshold=self._config.processed_skip_ratio_alarm,
                        samples=processed + skipped,
                        message=(
                            f"skip-rate {skip_ratio:.0%} over the past "
                            f"{self._config.window_hours}h exceeds threshold "
                            f"{self._config.processed_skip_ratio_alarm:.0%}"
                        ),
                    )
                )
        for template, counts in per_template.items():
            drafted = counts.get("drafted", 0)
            sent = counts.get("auto_sent", 0) + counts.get("approved", 0)
            if drafted == 0:
                continue
            send_ratio = sent / max(1, sent + drafted)
            if send_ratio < self._config.draft_send_ratio_alarm:
                signals.append(
                    DriftSignal(
                        kind="draft_send_ratio_low",
                        template=template,
                        ratio=send_ratio,
                        threshold=self._config.draft_send_ratio_alarm,
                        samples=sent + drafted,
                        message=(
                            f"template {template!r} send-ratio {send_ratio:.0%} below threshold "
                            f"{self._config.draft_send_ratio_alarm:.0%} — drafts are being "
                            "rejected or edited heavily"
                        ),
                    )
                )
        return signals


@dataclass(frozen=True)
class WhyEntry:
    timestamp: str
    kind: str
    description: str
    payload: dict[str, Any]


class WhyLookup:
    """Compose the routine's `/why <email_id>` answer.

    Combines:
      * the per-instance `email_triage_decisions` rows
      * the framework `audit_reader` events that match the same trace/run id

    Order is chronological so the dashboard can render as a timeline.
    """

    def __init__(self, state: EmailTriageState, audit_reader: AuditReader) -> None:
        self._state = state
        self._audit = audit_reader

    def lookup(self, email_id: str) -> list[WhyEntry]:
        entries: list[WhyEntry] = []
        decisions = self._state.by_email_id(email_id)
        run_ids: set[str] = set()
        for d in decisions:
            run_ids.add(d.routine_run_id)
            entries.append(
                WhyEntry(
                    timestamp=d.decided_at.isoformat(),
                    kind=f"decision.{d.action}",
                    description=_describe_decision(d),
                    payload=d.payload,
                )
            )
        # Pull audit events for each routine_run_id that touched this email
        for run_id in run_ids:
            for ev in self._audit.scan(AuditFilter(routine_run_id=run_id)):
                if email_id and email_id not in str(ev.model_dump(mode="json")):
                    continue
                entries.append(
                    WhyEntry(
                        timestamp=ev.timestamp.isoformat(),
                        kind=ev.event_type,
                        description=str(ev.payload or {}),
                        payload=ev.payload or {},
                    )
                )
        entries.sort(key=lambda e: e.timestamp)
        return entries


def _describe_decision(d: TriageDecisionRecord) -> str:
    pieces: list[str] = [d.action]
    if d.category is not None:
        pieces.append(f"category={d.category}")
    if d.template is not None:
        pieces.append(f"template={d.template}")
    return " ".join(pieces)
