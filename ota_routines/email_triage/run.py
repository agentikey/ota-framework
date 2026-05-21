"""email_triage runtime entrypoint.

The framework's routine engine calls `run(runtime)` once per scheduled tick.
On each tick we:

1. Poll the mailbox for new threads via `email.list_mailbox`.
2. For each new thread: dedup (skip if seen), classify (Reader), select a
   template, draft (Drafter).
3. If the template's trust state says auto-send → send via `email.send_email`
   and record `auto_sent`. Else propose a HITL gate over messaging
   (approval card) and either send on approval or skip on reject.

This v0.1 implementation is wire-up only — the LLM Reader / Drafter stages
are placeholders that delegate to a `runtime.llm` helper (Phase 1's
`LLMProvider`). When real LLM scoring is needed, replace `_classify` and
`_draft` with calls to a real provider.
"""

from __future__ import annotations

import logging
from typing import Any

from ota_connect import email as email_capability
from ota_connect import messaging as messaging_capability
from ota_connect._types import EmailRef, Page
from ota_routines.email_triage.helpers import (
    TrustPromotion,
    content_hash,
)
from ota_routines.email_triage.state import EmailTriageState

_logger = logging.getLogger(__name__)


async def run(runtime: Any) -> dict[str, Any]:
    """Single tick of the email-triage routine."""
    config: dict[str, Any] = dict(runtime.knobs.get("config", {}))
    if not config:
        # Fall back to top-level knobs (the framework flattens config knobs
        # into runtime.knobs[<name>]).
        config = {k: runtime.knobs.get(k) for k in runtime.knobs}
    state: EmailTriageState = runtime.context["state"]
    trust = TrustPromotion(
        state,
        allowed_auto_send_templates=tuple(
            (config.get("auto_send") or {}).get("allowed_templates") or ()
        ),
    )
    folder = (config.get("mailbox") or {}).get("folder", "INBOX")
    page: Page[EmailRef] = email_capability.list_mailbox(folder=folder, limit=25)
    summary = {"scanned": 0, "drafted": 0, "auto_sent": 0, "skipped": 0, "duplicates": 0}
    for ref in page.items:
        summary["scanned"] += 1
        outcome = await _process_one(
            runtime=runtime,
            ref=ref,
            state=state,
            trust=trust,
            categories=list(config.get("categories", [])),
            templates_by_name={t["name"]: t for t in config.get("templates", [])},
            approval_channel=(config.get("notifications") or {}).get("approval_channel"),
        )
        summary[outcome] += 1
    return summary


async def _process_one(
    *,
    runtime: Any,
    ref: EmailRef,
    state: EmailTriageState,
    trust: TrustPromotion,
    categories: list[dict[str, Any]],
    templates_by_name: dict[str, dict[str, Any]],
    approval_channel: str | None,
) -> str:
    body, subject, sender = await _fetch_email_content(runtime=runtime, ref=ref)
    chash = content_hash(subject=subject, body=body, sender=sender)
    if state.is_processed(email_id=ref.id, content_hash=chash):
        return "duplicates"
    classification = await _classify(
        runtime=runtime, subject=subject, body=body, sender=sender, categories=categories
    )
    if classification["category"] == "skip":
        state.record_decision(
            routine_run_id=runtime.context["routine_run_id"],
            email_id=ref.id,
            action="skipped",
            category=None,
            template=None,
            payload=classification,
        )
        state.mark_processed(email_id=ref.id, content_hash=chash)
        return "skipped"
    template_name = next(
        (c["template"] for c in categories if c["name"] == classification["category"]),
        None,
    )
    if template_name is None or template_name not in templates_by_name:
        return "skipped"
    template = templates_by_name[template_name]
    draft = await _draft(
        runtime=runtime,
        ref=ref,
        subject=subject,
        body=body,
        sender=sender,
        category=classification["category"],
        template=template,
    )
    decision = trust.evaluate(template_name)
    if decision.auto_send:
        sent_ref = email_capability.send_email(
            to=[f"mailto:{sender}"],
            subject=draft["subject"],
            body=draft["body"],
            reply_to=ref,
        )
        state.record_decision(
            routine_run_id=runtime.context["routine_run_id"],
            email_id=ref.id,
            action="auto_sent",
            category=classification["category"],
            template=template_name,
            payload={"draft": draft, "sent_email_id": sent_ref.id},
        )
        trust.record_approval(template_name)
        state.mark_processed(email_id=ref.id, content_hash=chash)
        return "auto_sent"
    # Propose to operator via Slack approval card
    if approval_channel is not None:
        from ota_connect._types import ChannelRef

        messaging_capability.send_message(
            target=ChannelRef(
                id=approval_channel, kind="channel", name=None, adapter="slack_socket_adapter"
            ),
            content=f"Draft reply to {sender}:\nSubject: {draft['subject']}\n\n{draft['body']}",
        )
    state.record_decision(
        routine_run_id=runtime.context["routine_run_id"],
        email_id=ref.id,
        action="drafted",
        category=classification["category"],
        template=template_name,
        payload={"draft": draft},
    )
    state.mark_processed(email_id=ref.id, content_hash=chash)
    return "drafted"


async def _fetch_email_content(*, runtime: Any, ref: EmailRef) -> tuple[str, str, str]:
    """Resolve the email body / subject / sender.

    The current Gmail adapter `list_mailbox` returns only id+threadId. In v0.2
    we'll extend it to return headers. For v0.1 we ask the runtime for any
    cached body via `runtime.context['fetched_bodies']` (the routine engine
    pre-fetches as an optimization) or fall back to an empty string. Tests
    inject the cache directly.
    """
    cache: dict[str, dict[str, str]] = runtime.context.get("fetched_bodies", {})
    entry = cache.get(ref.id, {})
    return entry.get("body", ""), entry.get("subject", ""), entry.get("sender", "")


async def _classify(
    *,
    runtime: Any,
    subject: str,
    body: str,
    sender: str,
    categories: list[dict[str, Any]],
) -> dict[str, Any]:
    """v0.1 placeholder classifier — keyword scan against category.keywords[].

    Real LLM classifier lands in 4B follow-up. The placeholder is good enough
    for the tracer-bullet: real LLM calls require live credentials.
    """
    lower_subject = subject.lower()
    lower_body = body.lower()
    for cat in categories:
        for kw in cat.get("keywords", []):
            if kw.lower() in lower_subject or kw.lower() in lower_body:
                return {"category": cat["name"], "confidence": 0.9, "reasoning": f"keyword:{kw}"}
    return {"category": "skip", "confidence": 1.0, "reasoning": "no keyword match"}


async def _draft(
    *,
    runtime: Any,
    ref: EmailRef,
    subject: str,
    body: str,
    sender: str,
    category: str,
    template: dict[str, Any],
) -> dict[str, str]:
    """v0.1 placeholder drafter — interpolates {sender_first_name} and
    {thread_subject} into the template body."""
    placeholders = {
        "sender_first_name": sender.split("@", 1)[0].split(".", 1)[0].title()
        if sender
        else "there",
        "thread_subject": subject,
        "commit_date": "Friday",
        "status_line": "still in progress",
        "operator_first_name": runtime.knobs.get("operator_first_name", "Omar"),
        "slot_1": "Tue 10:00",
        "slot_2": "Wed 14:00",
        "slot_3": "Thu 11:00",
    }
    body_path = template["body_path"]
    body_template = runtime.context["templates"][body_path]
    rendered = body_template.format(**placeholders)
    subject_pattern: str = template.get("subject_pattern", "Re: {thread_subject}")
    rendered_subject = subject_pattern.format(**placeholders)
    return {"subject": rendered_subject, "body": rendered}
