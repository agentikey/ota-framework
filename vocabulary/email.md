---
capability: email
version: 1.0.0
status: stable
description: Abstract unified capability for asynchronous multi-recipient routing engines (Gmail, Microsoft 365, IMAP/SMTP).
adapters_satisfying_min_v1.0:
  - gmail_oauth_adapter
  - exchange_365_adapter
  - native_smtp_imap_adapter
references_types:
  - IdentityRef
  - EmailRef
  - DraftRef
  - EmailThreadRef
  - Block
  - FileRef
  - Attachment
  - Importance
  - Cursor
  - Page
requires_integration:
  auth_styles: [oauth2, api_key, basic, app_password, mtls]
  connection_model: outbound_only
---

# email

## Intent

Serves routine intent focused on formal, multi-recipient, asynchronous messaging workflows. Handles long-form document routing, multi-party distributions (Cc/Bcc), conversation threads anchored to immutable RFC headers, mailbox indexing via a label-based taxonomy, and first-class draft staging for high-stakes enterprise pipelines.

### Non-Goals

- This capability does NOT manage email server infrastructure, DNS routing records, SPF/DKIM keys, or user inbox rules.
- This capability does NOT monitor real-time presence or support continuous streaming event loops; use `messaging` for that.
- This capability does NOT design public marketing campaign managers, A/B testing, or open-rate tracking pixels; it targets direct operational business logic.

## The Inbound Email Event Loop

Email is fundamentally asynchronous on the receive side. SMTP operations may succeed at call-time but return downstream signals hours later. The framework's outbound-only polling daemons monitor the mail server and translate inbound mail state changes into canonical framework automation events (cataloged in the Contract B event taxonomy):

- `integration.email.bounce_received` — Triggered when an outbound transmission fails downstream. Payload: original `EmailRef`, failed recipient `IdentityRef`, parsed bounce reason string.
- `integration.email.reply_received` — Triggered when an inbound conversation reply arrives. Payload: a new `EmailRef` and the matching parent `EmailThreadRef`.
- `integration.email.delivery_confirmed` — Triggered where providers support delivery tracking. Payload: `EmailRef`, recipient `IdentityRef`, timezone-aware `confirmed_at` timestamp.
- `integration.email.auto_response_received` — Triggered when out-of-office or automated notifications arrive. Payload: `EmailRef`, `kind: Literal["out_of_office" | "vacation" | "unknown"]`.

## Label-Based Substrate Convention

The framework treats all mailbox classification through a unified **label-based model**. Standard "folders" are reserved global label tokens. Adapters connecting to folder-locked architectures (Outlook REST, plain IMAP) map label adjustments to native folder migrations under the hood.

- **Reserved system labels:** `"inbox"`, `"sent"`, `"archive"`, `"trash"`, `"drafts"`, `"unread"`.
- A folder relocation is expressed by combining additions and removals: `modify_email_labels(email_ref, add_labels=["archive"], remove_labels=["inbox"])`.
- Custom labels are passed as raw strings; adapter validates per-platform constraints (length, character set).

## Action Block Degradation

Email rendering engines across major clients (Outlook, Gmail, Apple Mail) are highly restrictive toward modern layout, Flexbox, or interactive scripts.

- When an email adapter processes a `Block` containing `kind="actions"`, it **must degrade interactive elements into plain-text hyperlinks**.
- Each `Action` button or select item is rendered as inline text bracketed like `[Action Label]`.
- The link target is a framework-managed dashboard endpoint: `https://<ota_dashboard>/actions/<action_value>`. When an operator clicks the link in their email client, the dashboard executes the action securely and fires the standard `integration.messaging.action_triggered` event back to the routine, identical to a native chat button click.

## Scope Vocabulary

Strings declared in verb `required_scopes` metadata are framework-abstract permission tokens. The active Integration Registry (Contract D) maps these to platform-native flags at runtime — e.g., expanding `"email:send"` to `["https://www.googleapis.com/auth/gmail.send"]` for Gmail or `["Mail.Send"]` for Microsoft Graph.

## Verbs

### `send_email`

Composes and dispatches a long-form email to one or more recipients.

**Metadata:**

```yaml
idempotency: best_effort
required_scopes: ["email:send"]
destructive: false
```

**Signature:**

```python
def send_email(
    to: list[IdentityRef],
    subject: str,
    body: str | list[Block],
    *,
    cc: list[IdentityRef] | None = None,
    bcc: list[IdentityRef] | None = None,
    reply_to: EmailRef | None = None,
    attachments: list[Attachment] | None = None,
    importance: Importance = "normal",
) -> EmailRef: ...
```

**Semantics:**

- `to` / `cc` / `bcc`: Recipient collections. Elements can be `"mailto:..."` strings or `"handle:..."` handles. Framework deduplicates cross-scope identities.
- `body`: Content payload. Plain strings are wrapped into an unstyled text block. Structured `Block` lists are compiled into an inline-CSS table layout before reaching the adapter (best-effort HTML; complex blocks fall back to plain-text rendering per adapter capability).
- `reply_to`: Reference to an existing email. Adapter extracts the parent's `Message-ID` header and injects it into the outbound email's `In-Reply-To` and `References` headers; appends `"Re:"` to the subject if not already present.
- `attachments`: `FileRef` strings are resolved by the framework runtime (local or storage-bucket) and embedded in the MIME payload.
- **Behavioral constraints:** Dedup hash spans the full footprint: `to + cc + bcc + subject + body + reply_to`. Matching requests within the 5-minute sliding window yield the original cached `EmailRef`.

**Errors:**

- `IdentityResolveError` — A handle in any recipient collection could not be resolved to a raw email address. Non-retryable.
- `RecipientUnreachable` — All supplied recipients failed call-time validation (invalid addresses, blocked senders). Partial bounces flow through the inbound event loop, not this error. Non-retryable.
- `MessageRejected` — Upstream server blocked transmission (DLP rule, content filter, signature match). Non-retryable.
- `RateLimited` — Outbound quotas exhausted. Retryable per provider backoff.

**Examples:**

```python
# Status report to a single resolved handle
ota_connect.email.send_email(
    to=["handle:@ceo"],
    cc=["mailto:ops-leads@firm.com"],
    subject="System Status Report: May 2026",
    body="All background routines are executing within budget bounds.",
)

# Threaded reply
ota_connect.email.send_email(
    to=["mailto:client@external.com"],
    subject="Updated proposal",
    body=compiled_blocks,
    reply_to=original_inquiry_ref,
)
```

**Conformance:** See `tests/vocabulary/email/send_email/`.

---

### `create_draft`

Stages an unsent message asset in the provider's drafts index.

**Metadata:**

```yaml
idempotency: best_effort
required_scopes: ["email:modify"]
destructive: false
```

**Signature:**

```python
def create_draft(
    to: list[IdentityRef],
    subject: str,
    body: str | list[Block],
    *,
    cc: list[IdentityRef] | None = None,
    bcc: list[IdentityRef] | None = None,
    reply_to: EmailRef | None = None,
    attachments: list[Attachment] | None = None,
) -> DraftRef: ...
```

**Semantics:**

- **Returns:** A `DraftRef` token. The type system prevents this reference from being passed to read or label-modification verbs; only `send_draft` accepts it.
- **Behavioral constraints:** No messages exit the provider boundary at this step. The asset is entirely passive.

**Examples:**

```python
# Stage a billing summary for operator review before send
draft = ota_connect.email.create_draft(
    to=["mailto:client@external.com"],
    subject="Weekly Consulting Ledger",
    body=compiled_billing_blocks,
)
# Later, after operator approval:
ota_connect.email.send_draft(draft)
```

**Conformance:** See `tests/vocabulary/email/create_draft/`.

---

### `send_draft`

Triggers delivery of an existing staged draft message.

**Metadata:**

```yaml
idempotency: best_effort
required_scopes: ["email:send"]
destructive: false
```

**Signature:**

```python
def send_draft(
    draft_ref: DraftRef,
) -> EmailRef: ...
```

**Semantics:**

- `draft_ref`: Active staging reference returned by an earlier `create_draft` call.
- **Returns:** A new frozen `EmailRef` reflecting post-delivery state, with `message_id_header` populated.
- **Behavioral constraints:** Upstream provider destroys the draft row on successful delivery. Retrying a `send_draft` outside the 5-minute dedup window yields `MessageRejected` (draft no longer exists).

**Conformance:** See `tests/vocabulary/email/send_draft/`.

---

### `delete_email`

Removes an existing email from the mailbox state.

**Metadata:**

```yaml
idempotency: best_effort
required_scopes: ["email:delete"]
destructive: true
```

**Signature:**

```python
def delete_email(
    email_ref: EmailRef,
    *,
    permanent: bool = False,
) -> None: ...
```

**Semantics:**

- `email_ref`: Target message reference.
- `permanent`: Soft vs. hard deletion. `False` (default) applies the `"trash"` label (translated to folder move by folder-based adapters). `True` instructs the adapter to bypass trash entirely and purge.
- **Behavioral constraints:** Marked `destructive: true`. The capability performs no automated gating; any validation or HITL steps live at the routine layer.

**Errors:**

- `AdapterMismatchError` — Mismatched provider token. Non-retryable.
- `MessageRejected` — Message does not exist, or caller lacks permission to delete. Non-retryable.

**Conformance:** See `tests/vocabulary/email/delete_email/`.

---

### `list_mailbox`

Scans a label-targeted container for email logs with cursor-based pagination.

**Metadata:**

```yaml
idempotency: guaranteed
required_scopes: ["email:read"]
destructive: false
```

**Signature:**

```python
def list_mailbox(
    folder: str,
    *,
    since: datetime | None = None,
    limit: int = 25,
    cursor: Cursor | None = None,
) -> Page[EmailRef]: ...
```

**Semantics:**

- `folder`: String label target. Standard entries match reserved system labels (`"inbox"`, `"sent"`, `"archive"`); custom labels are passed raw.
- `since`: Optional timezone-aware filter. Naive datetimes raise `ValueError` at the framework boundary.
- **Returns:** `Page[EmailRef]` with `next_cursor: Cursor | None`.
- **Behavioral constraints:** Messages sorted **newest-first** (reverse-chronological scan from the present moment).

**Errors:**

- `AdapterUnavailable` — Connection to remote server failed or auth expired. Retryable.

**Conformance:** See `tests/vocabulary/email/list_mailbox/`.

---

### `read_email_thread`

Retrieves all historical messages bound to a specific conversation thread.

**Metadata:**

```yaml
idempotency: guaranteed
required_scopes: ["email:read"]
destructive: false
```

**Signature:**

```python
def read_email_thread(
    thread_ref: EmailThreadRef,
    *,
    limit: int = 50,
    cursor: Cursor | None = None,
) -> Page[EmailRef]: ...
```

**Semantics:**

- `thread_ref`: Parent conversation reference.
- **Returns:** `Page[EmailRef]` with `next_cursor: Cursor | None`.
- **Behavioral constraints:** Adapter maps thread membership via RFC `Message-ID` / `References` headers. Messages sorted **oldest-first** (chronological reading order from root down).

**Conformance:** See `tests/vocabulary/email/read_email_thread/`.

---

### `modify_email_labels`

Applies or prunes organization labels on a targeted email.

**Metadata:**

```yaml
idempotency: best_effort
required_scopes: ["email:modify"]
destructive: false
```

**Signature:**

```python
def modify_email_labels(
    email_ref: EmailRef,
    add_labels: list[str],
    remove_labels: list[str],
) -> None: ...
```

**Semantics:**

- **Behavioral constraints:** Best-effort batch operation — adapter attempts all label operations sequentially. On partial failure (e.g., IMAP folder move halfway through), raises `CapabilityDegraded` carrying `partial_status: dict[str, Literal["applied", "failed"]]` mapping each requested change to its outcome.

**Errors:**

- `CapabilityDegraded` — Partial failure across the batch; see `partial_status` for per-label outcomes.

**Conformance:** See `tests/vocabulary/email/modify_email_labels/`.

---

### `mark_read`

Toggles an email to the read state.

**Metadata:**

```yaml
idempotency: guaranteed
required_scopes: ["email:modify"]
destructive: false
```

**Signature:**

```python
def mark_read(
    email_ref: EmailRef,
) -> None: ...
```

**Semantics:**

- Removes the system `"unread"` label from the target. Folder-based adapters toggle the native unread flag.

**Conformance:** See `tests/vocabulary/email/mark_read/`.

---

### `mark_unread`

Toggles an email to the unread state.

**Metadata:**

```yaml
idempotency: guaranteed
required_scopes: ["email:modify"]
destructive: false
```

**Signature:**

```python
def mark_unread(
    email_ref: EmailRef,
) -> None: ...
```

**Semantics:**

- Applies the system `"unread"` label to the target. Folder-based adapters toggle the native unread flag.

**Conformance:** See `tests/vocabulary/email/mark_unread/`.

---

## Changelog

- **1.0.0 (2026-05-18)** — Initial capability spec lock-in. Introduces `DraftRef` for type-safe staging lifecycle. Documents the asynchronous inbound email event loop (`bounce_received`, `reply_received`, `delivery_confirmed`, `auto_response_received`). Establishes label-based mailbox substrate with folder-adapter translation convention. Defines `Action` block degradation to plain-text hyperlinks for email rendering. Adds `mark_read` / `mark_unread` as first-class verbs rather than label conventions. Closes `auth_styles` taxonomy to `[oauth2, api_key, basic, app_password, mtls]`. Weakens `modify_email_labels` atomicity to best-effort with `partial_status` reporting.
