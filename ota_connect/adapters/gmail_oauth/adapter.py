"""Gmail adapter — email.* verbs over Gmail REST API.

Implements every verb in `vocabulary/email.md` against
`https://gmail.googleapis.com/gmail/v1/users/me/...`. OAuth tokens come from
the framework `OAuthTokenStore`; the adapter calls `OAuthClient.access_token()`
through that store, refreshing automatically when the token nears expiry.

Inbound (bounces, replies, delivery confirmations) uses Gmail's `history.list`
endpoint via `poll_inbound()`: the polling loop in
`ota_connect.binding.inbound_email` ticks it on a schedule and pushes any new
events into the framework's `ActionRouter`.

Tests mock at the httpx layer with `pytest-httpx`; no real OAuth needed.
"""

from __future__ import annotations

import base64
import email
import email.message
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import formatdate, make_msgid
from typing import Any

import httpx

from ota_connect._types import (
    Attachment,
    Block,
    Cursor,
    DraftRef,
    EmailRef,
    EmailThreadRef,
    IdentityRef,
    Page,
)
from ota_connect._types.errors import (
    AdapterUnavailable,
    MessageRejected,
    RateLimited,
    RecipientUnreachable,
)
from ota_connect.binding.actions import ActionEventKind
from ota_connect.binding.error_norm import make_error
from ota_connect.binding.inbound_email import RawInboundEvent
from ota_core.integration_source.source import AdapterBundle
from ota_core.oauth import OAuthTokenStore

_logger = logging.getLogger(__name__)

_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


@dataclass
class GmailAdapterConfig:
    token_store: OAuthTokenStore | None = None
    access_token_override: str | None = None
    integration_id: str = "gmail.com"
    request_timeout_seconds: float = 15.0
    inbound_history_id_path: str | None = None  # where to persist last seen historyId


@dataclass
class _InboundState:
    last_history_id: str | None = None
    routine_id_default: str = ""

    def update(self, history_id: str) -> None:
        self.last_history_id = history_id


class GmailOAuthAdapter:
    """`AdapterImpl` for Gmail email.* verbs."""

    adapter_id = "gmail_oauth_adapter"
    capability = "email"

    def __init__(
        self,
        bundle: AdapterBundle | None = None,
        *,
        config: GmailAdapterConfig | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._bundle = bundle
        self.manifest = bundle.manifest if bundle is not None else None
        self._config = config or GmailAdapterConfig()
        self._http = http_client
        self._pending_inbound: list[RawInboundEvent] = []
        self._inbound_state = _InboundState()

    # ------------------------------------------------------------------
    # AdapterImpl protocol
    # ------------------------------------------------------------------

    def invoke(self, capability: str, verb: str, /, **kwargs: Any) -> Any:
        if capability != "email":
            raise NotImplementedError(
                f"gmail_oauth_adapter only implements email.*, got {capability}.{verb}"
            )
        handler = getattr(self, f"_verb_{verb}", None)
        if handler is None:
            raise NotImplementedError(f"email.{verb} not implemented by gmail adapter")
        return handler(**kwargs)

    def poll_inbound(self) -> Iterable[RawInboundEvent]:
        drained = list(self._pending_inbound)
        self._pending_inbound.clear()
        return drained

    # ------------------------------------------------------------------
    # Verb implementations
    # ------------------------------------------------------------------

    def _verb_send_email(
        self,
        to: list[IdentityRef],
        subject: str,
        body: str | list[Block],
        cc: list[IdentityRef] | None = None,
        bcc: list[IdentityRef] | None = None,
        reply_to: EmailRef | None = None,
        attachments: list[Attachment] | None = None,
        importance: str = "normal",
    ) -> EmailRef:
        raw_message = _build_mime(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
            attachments=attachments,
            importance=importance,
        )
        thread_id = reply_to.thread.id if reply_to and reply_to.thread else None
        send_body: dict[str, Any] = {"raw": _b64url(raw_message.as_bytes())}
        if thread_id is not None:
            send_body["threadId"] = thread_id
        data = self._post("messages/send", body=send_body)
        return _email_ref_from_data(data, adapter_id=self.adapter_id, subject=subject)

    def _verb_create_draft(
        self,
        to: list[IdentityRef],
        subject: str,
        body: str | list[Block],
        cc: list[IdentityRef] | None = None,
        bcc: list[IdentityRef] | None = None,
        reply_to: EmailRef | None = None,
        attachments: list[Attachment] | None = None,
    ) -> DraftRef:
        mime = _build_mime(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
            attachments=attachments,
        )
        thread_id = reply_to.thread.id if reply_to and reply_to.thread else None
        message: dict[str, Any] = {"raw": _b64url(mime.as_bytes())}
        if thread_id is not None:
            message["threadId"] = thread_id
        data = self._post("drafts", body={"message": message})
        return DraftRef(
            id=data["id"],
            subject=subject,
            created_at=datetime.now(UTC),
            adapter=self.adapter_id,
        )

    def _verb_send_draft(self, draft_ref: DraftRef) -> EmailRef:
        data = self._post("drafts/send", body={"id": draft_ref.id})
        return _email_ref_from_data(data, adapter_id=self.adapter_id, subject=draft_ref.subject)

    def _verb_delete_email(self, email_ref: EmailRef, permanent: bool = False) -> None:
        method = "delete" if permanent else "trash"
        self._post(f"messages/{email_ref.id}/{method}", body={})

    def _verb_list_mailbox(
        self,
        folder: str,
        since: datetime | None = None,
        limit: int = 25,
        cursor: Cursor | None = None,
    ) -> Page[EmailRef]:
        params: dict[str, Any] = {"labelIds": folder, "maxResults": limit}
        if cursor is not None:
            params["pageToken"] = cursor
        if since is not None:
            params["q"] = f"after:{int(since.timestamp())}"
        data = self._get("messages", params=params)
        items: list[EmailRef] = []
        for raw in data.get("messages", []):
            ref = EmailRef(
                id=raw["id"],
                message_id_header=None,
                thread=EmailThreadRef(
                    id=raw.get("threadId", raw["id"]),
                    subject="",
                    started_at=datetime.now(UTC),
                    adapter=self.adapter_id,
                ),
                sent_at=datetime.now(UTC),
                adapter=self.adapter_id,
            )
            items.append(ref)
        return Page(items=items, next_cursor=data.get("nextPageToken") or None)

    def _verb_read_email_thread(
        self,
        thread_ref: EmailThreadRef,
        limit: int = 50,
        cursor: Cursor | None = None,
    ) -> Page[EmailRef]:
        data = self._get(f"threads/{thread_ref.id}")
        messages = data.get("messages", [])
        items = [
            EmailRef(
                id=m["id"],
                message_id_header=_extract_header(m, "Message-ID"),
                thread=thread_ref,
                sent_at=_internal_date_to_datetime(m.get("internalDate")),
                adapter=self.adapter_id,
            )
            for m in messages[:limit]
        ]
        return Page(items=items, next_cursor=None)

    def _verb_modify_email_labels(
        self,
        email_ref: EmailRef,
        add_labels: list[str],
        remove_labels: list[str],
    ) -> None:
        self._post(
            f"messages/{email_ref.id}/modify",
            body={"addLabelIds": add_labels, "removeLabelIds": remove_labels},
        )

    def _verb_mark_read(self, email_ref: EmailRef) -> None:
        self._verb_modify_email_labels(email_ref, add_labels=[], remove_labels=["UNREAD"])

    def _verb_mark_unread(self, email_ref: EmailRef) -> None:
        self._verb_modify_email_labels(email_ref, add_labels=["UNREAD"], remove_labels=[])

    # ------------------------------------------------------------------
    # Inbound polling
    # ------------------------------------------------------------------

    def tick_inbound(self, *, routine_id: str) -> int:
        """Poll Gmail for new history and enqueue events. Returns count enqueued."""
        if self._inbound_state.last_history_id is None:
            data = self._get("profile")
            self._inbound_state.update(data.get("historyId", "1"))
            return 0
        params = {"startHistoryId": self._inbound_state.last_history_id}
        try:
            data = self._get("history", params=params)
        except MessageRejected:
            # History expired — re-baseline
            self._inbound_state.update(None)  # type: ignore[arg-type]
            return 0
        added = 0
        for entry in data.get("history", []):
            for added_msg in entry.get("messagesAdded", []):
                msg = added_msg.get("message", {})
                kind = _classify_inbound_label(msg.get("labelIds", []))
                self._pending_inbound.append(
                    RawInboundEvent(
                        kind=kind,
                        routine_id=routine_id,
                        payload={"message_id": msg.get("id"), "thread_id": msg.get("threadId")},
                        correlation_id=msg.get("threadId"),
                    )
                )
                added += 1
        new_history_id = data.get("historyId")
        if new_history_id:
            self._inbound_state.update(str(new_history_id))
        return added

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _post(self, path: str, *, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, json=body)

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self._access_token()
        url = f"{_GMAIL_BASE}/{path}"
        headers = {"Authorization": f"Bearer {token}"}
        client = self._http
        owns_client = False
        if client is None:
            client = httpx.Client(timeout=self._config.request_timeout_seconds)
            owns_client = True
        try:
            response = client.request(method, url, headers=headers, json=json, params=params)
        finally:
            if owns_client:
                client.close()
        return _check_gmail_response(
            response, adapter_id=self.adapter_id, capability="email", verb=path.split("/")[0]
        )

    def _access_token(self) -> str:
        if self._config.access_token_override is not None:
            return self._config.access_token_override
        store = self._config.token_store
        if store is None:
            raise make_error(
                AdapterUnavailable,
                adapter=self.adapter_id,
                capability="email",
                verb="<auth>",
                retryable=False,
            )
        record = store.get(integration_id=self._config.integration_id)
        if record is None:
            raise make_error(
                AdapterUnavailable,
                adapter=self.adapter_id,
                capability="email",
                verb="<auth>",
                retryable=False,
            )
        return record.access_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _identity_to_address(ref: IdentityRef) -> str:
    if ref.startswith("mailto:"):
        return ref[len("mailto:") :]
    if ref.startswith("handle:"):
        # Should be resolved upstream; bail with RecipientUnreachable
        raise make_error(
            RecipientUnreachable,
            adapter="gmail_oauth_adapter",
            capability="email",
            verb="<resolve>",
            reason=f"identity {ref!r} not resolved to an email address",
        )
    if ref.startswith("raw:gmail:"):
        return ref[len("raw:gmail:") :]
    if "@" in ref:
        return ref
    raise make_error(
        RecipientUnreachable,
        adapter="gmail_oauth_adapter",
        capability="email",
        verb="<resolve>",
        reason=f"unrecognized IdentityRef {ref!r}",
    )


def _build_mime(
    *,
    to: list[IdentityRef],
    subject: str,
    body: str | list[Block],
    cc: list[IdentityRef] | None = None,
    bcc: list[IdentityRef] | None = None,
    reply_to: EmailRef | None = None,
    attachments: list[Attachment] | None = None,
    importance: str = "normal",
) -> email.message.EmailMessage:
    msg = email.message.EmailMessage()
    msg["To"] = ", ".join(_identity_to_address(t) for t in to)
    if cc:
        msg["Cc"] = ", ".join(_identity_to_address(c) for c in cc)
    if bcc:
        msg["Bcc"] = ", ".join(_identity_to_address(b) for b in bcc)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid()
    if reply_to is not None:
        if reply_to.message_id_header:
            msg["In-Reply-To"] = reply_to.message_id_header
            msg["References"] = reply_to.message_id_header
    if importance == "high":
        msg["X-Priority"] = "1"
        msg["Importance"] = "High"
    if isinstance(body, str):
        msg.set_content(body)
    else:
        plain = "\n\n".join(b.text or "" for b in body if isinstance(b.text, str))
        msg.set_content(plain or " ")
    if attachments:
        for a in attachments:
            msg.add_attachment(
                _attachment_bytes(a),
                maintype="application",
                subtype="octet-stream",
                filename=a.display_name,
            )
    return msg


def _attachment_bytes(_a: Attachment) -> bytes:
    # v0.1 placeholder — real implementation reads from FileRef-resolved storage.
    return b""


def _email_ref_from_data(data: dict[str, Any], *, adapter_id: str, subject: str) -> EmailRef:
    thread_id = data.get("threadId", data["id"])
    return EmailRef(
        id=data["id"],
        message_id_header=None,
        thread=EmailThreadRef(
            id=thread_id,
            subject=subject,
            started_at=datetime.now(UTC),
            adapter=adapter_id,
        ),
        sent_at=datetime.now(UTC),
        adapter=adapter_id,
    )


def _extract_header(message: dict[str, Any], name: str) -> str | None:
    headers = message.get("payload", {}).get("headers", [])
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            value = h.get("value")
            return str(value) if value is not None else None
    return None


def _internal_date_to_datetime(internal_date: Any) -> datetime:
    if internal_date is None:
        return datetime.now(UTC)
    return datetime.fromtimestamp(int(internal_date) / 1000, tz=UTC)


def _classify_inbound_label(labels: list[str]) -> ActionEventKind:
    label_set = set(labels)
    if "INBOX" in label_set and "UNREAD" in label_set:
        return "email.reply_received"
    if "SPAM" in label_set:
        return "email.bounce_received"
    return "email.reply_received"


def _check_gmail_response(
    response: httpx.Response,
    *,
    adapter_id: str,
    capability: str,
    verb: str,
) -> dict[str, Any]:
    if response.status_code == 429:
        from datetime import timedelta as _td

        retry_after_raw = response.headers.get("Retry-After")
        retry_after = _td(seconds=int(retry_after_raw)) if retry_after_raw else None
        raise make_error(
            RateLimited,
            adapter=adapter_id,
            capability=capability,
            verb=verb,
            retry_after=retry_after,
        )
    if response.status_code in (400, 404):
        # Gmail returns 404 for many "thread expired" / not-found cases
        body: dict[str, Any] = {}
        try:
            body = response.json()
        except ValueError:
            pass
        reason = body.get("error", {}).get("message", f"HTTP {response.status_code}")
        if "Requested entity was not found" in reason or "notFound" in str(
            body.get("error", {}).get("status", "")
        ):
            raise make_error(
                RecipientUnreachable,
                adapter=adapter_id,
                capability=capability,
                verb=verb,
                reason=reason,
            )
        raise make_error(
            MessageRejected,
            adapter=adapter_id,
            capability=capability,
            verb=verb,
            reason=reason,
        )
    if response.status_code >= 500:
        raise make_error(
            AdapterUnavailable,
            adapter=adapter_id,
            capability=capability,
            verb=verb,
            retryable=True,
        )
    if response.status_code >= 400:
        raise make_error(
            AdapterUnavailable,
            adapter=adapter_id,
            capability=capability,
            verb=verb,
            retryable=False,
        )
    if response.status_code == 204 or not response.content:
        return {}
    try:
        parsed: dict[str, Any] = response.json()
        return parsed
    except ValueError as exc:
        raise make_error(
            AdapterUnavailable,
            adapter=adapter_id,
            capability=capability,
            verb=verb,
            retryable=False,
        ) from exc


__all__ = ["GmailAdapterConfig", "GmailOAuthAdapter"]
