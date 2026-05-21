---
capability: messaging
version: 1.0.0
status: stable
description: Abstract unified capability for real-time messaging systems (Slack, Teams, Telegram, Discord, etc.).
adapters_satisfying_min_v1.0:
  - slack_socket_adapter
  - telegram_polling_adapter
references_types:
  - IdentityRef
  - MessageRef
  - ThreadRef
  - ChannelRef
  - Block
  - Action
  - FileRef
  - Attachment
  - DeliveryStatus
  - Importance
  - Cursor
  - Page
requires_integration:
  auth_styles: [oauth2, api_key]
  connection_model: outbound_only
---

# messaging

## Intent

Serves routine intent focused on real-time, event-driven chat orchestration across workspaces, team channels, and direct message (DM) threads. Treats chat networks as immediate, stateful canvas environments where agents can converse, alert, read interaction history, and render interactive Human-in-the-Loop (HITL) interfaces.

### Non-Goals

- This capability does NOT manage workspace layout, channel creation, user invites, or server settings.
- This capability does NOT handle long-form, multi-recipient asynchronous routing like email — use the `email` capability instead.
- This capability does NOT handle persistent raw file generation or folder permissions — files are referenced via `FileRef` strings and uploaded as message attachments only.

## The Action Callback Loop

Buttons, select menus, and links embedded within a `Block` (via the `Action` dataclass) render interactive components on the target chat canvas.

- User interactions are **not polled** by this capability.
- When an operator interacts with an embedded `Action`, the bound Access Layer adapter normalizes the webhook or socket payload into a canonical framework envelope.
- The envelope is dispatched back to the routine engine as a first-class integration event typed as `integration.messaging.action_triggered` (cataloged in the Contract B event taxonomy).
- The envelope payload contains: the original `MessageRef`, the actor's `IdentityRef`, a timezone-aware `triggered_at: datetime`, and the opaque `Action.value` string preserved verbatim.

## Scope Vocabulary

Strings declared in verb `required_scopes` metadata are **framework-abstract permission tokens**. They do NOT map 1:1 to live third-party platform API scopes. The active Integration Registry (Contract D) owns the authoritative translation map that expands these tokens into driver-native platform permissions at runtime — e.g., expanding `"messaging:send"` to `["chat:write", "chat:write.public"]` for the Slack adapter, or to a Telegram Bot API role for the Telegram adapter.

## Verbs

### `send_message`

Dispatches a text message or a collection of structured interactive blocks to a target channel, group chat, or direct message thread.

**Metadata:**

```yaml
idempotency: best_effort
required_scopes: ["messaging:send"]
destructive: false
```

**Signature:**

```python
def send_message(
    target: ChannelRef | IdentityRef,
    content: str | list[Block],
    *,
    thread_ref: ThreadRef | None = None,
    attachments: list[Attachment] | None = None,
    importance: Importance = "normal",
) -> MessageRef: ...
```

**Semantics:**

- `target`: The chat destination. If given an `IdentityRef` handle string (e.g. `"handle:@jamie"`), the framework queries the IdentityProvider to locate or allocate a direct conversation space. If given a `ChannelRef`, it routes directly using the provider's stable ID.
- `content`: The message body. Plain strings are wrapped automatically into a single text `Block`. Structured blocks render natively when the adapter asserts `full_blocks` support; otherwise the framework flattens them to text via individual `.text` fallbacks.
- `thread_ref`: Optional reference to an existing message thread. If provided, the message is posted as a nested reply within that thread.
- `attachments`: Optional list of files to bind to the message. `FileRef` strings are resolved by the framework runtime (local path or storage bucket mapping) and uploaded via the adapter's native multipart or chunked upload path. If the bound adapter lacks attachment support, files are stripped and a `CapabilityDegraded` warning is emitted.
- `importance`: Maps to the adapter's native priority signal (Slack message styling, Teams importance flag, etc.). Adapters with no native priority concept ignore the field.
- **Behavioral constraints:** Idempotency tracking computes a SHA-256 hash of `target`, `content`, and `thread_ref`. The framework maintains a 5-minute sliding deduplication window — duplicate requests inside this window safely yield the originally returned `MessageRef` to prevent double-posting side effects.

**Errors:**

- `IdentityResolveError` — `IdentityRef` handle could not be resolved to an active user or channel context. Non-retryable.
- `RecipientUnreachable` — Target exists but rejects delivery (bot kicked, DMs disabled, account deactivated). Non-retryable.
- `RateLimited` — Upstream API limits encountered. Retryable per provider backoff policy.
- `CapabilityDegraded` — Bound adapter does not satisfy a required feature for this call (e.g., attachments requested against text-only adapter under strict routine policy). Non-retryable.

**Examples:**

```python
# Post a text update directly to an operator handle
ota_connect.messaging.send_message(
    "handle:@omar",
    "The database backup completed successfully."
)

# Post an interactive block layout to a targeted channel
ota_connect.messaging.send_message(
    target=production_alerts_channel,
    content=[
        Block(kind="header", text="Resource Limit Warning"),
        Block(kind="section", text="Routine morning_brief is near its daily cost limit."),
        Block(kind="actions", actions=[
            Action(kind="button", label="Allocate $0.50", value="incr_budget:0.50", style="primary"),
            Action(kind="button", label="Acknowledge", value="ack_warning", style="default"),
        ]),
    ],
    importance="important",
)
```

**Conformance:** See `tests/vocabulary/messaging/send_message/`.

---

### `edit_message`

Alters the text content or interactive layout block configuration of a previously posted chat message.

**Metadata:**

```yaml
idempotency: best_effort
required_scopes: ["messaging:modify"]
destructive: false
```

**Signature:**

```python
def edit_message(
    message_ref: MessageRef,
    new_content: str | list[Block],
) -> MessageRef: ...
```

**Semantics:**

- `message_ref`: Tracking token returned by an earlier write operation.
- `new_content`: Replacement payload. Completely replaces the historical body state.
- **Returns:** A new frozen `MessageRef` instance with primary identifiers matching the source ref (`id`, `channel`, `adapter` unchanged; `sent_at` reflects the original send time).
- **Behavioral constraints:** Deduplication applies strictly to identical-input retries within the 5-minute sliding cache window. Sequential distinct edits are NOT deduplicated and execute in order of arrival. Passing a `MessageRef` minted by a different adapter (e.g., Telegram ref to a Slack-bound call) raises `AdapterMismatchError` before reaching the wire.

**Errors:**

- `AdapterMismatchError` — Mismatched provider token supplied. Non-retryable.
- `MessageRejected` — Remote server rejected the edit (editing window expired, message deleted, etc.). Non-retryable.

**Examples:**

```python
# Clear active buttons by replacing the content layout block
ota_connect.messaging.edit_message(
    active_status_ref,
    [Block(kind="section", text="Action item acknowledged by operator.")],
)
```

**Conformance:** See `tests/vocabulary/messaging/edit_message/`.

---

### `delete_message`

Removes an existing message from the remote chat history.

**Metadata:**

```yaml
idempotency: best_effort
required_scopes: ["messaging:delete"]
destructive: true
```

**Signature:**

```python
def delete_message(
    message_ref: MessageRef,
) -> None: ...
```

**Semantics:**

- `message_ref`: Canonical token pointing to the target message asset.
- **Behavioral constraints:** Marked `destructive: true`. The capability performs no automated gating; any validation or human-in-the-loop steps must be declared at the parent routine layer. Successive identical retries inside the 5-minute deduplication window are safe; a retry landing outside the window on an already-deleted message yields `MessageRejected`.

**Errors:**

- `AdapterMismatchError` — Mismatched provider token. Non-retryable.
- `MessageRejected` — Message does not exist (already deleted, or never existed) or caller lacks administrative privilege to remove it. Non-retryable.

**Examples:**

```python
# Clear a temporary countdown notification card
ota_connect.messaging.delete_message(notification_card_ref)
```

**Conformance:** See `tests/vocabulary/messaging/delete_message/`.

---

### `read_thread`

Retrieves a paginated block of messages inside a specific conversation thread.

**Metadata:**

```yaml
idempotency: guaranteed
required_scopes: ["messaging:read"]
destructive: false
```

**Signature:**

```python
def read_thread(
    thread_ref: ThreadRef,
    *,
    limit: int = 100,
    cursor: Cursor | None = None,
) -> Page[MessageRef]: ...
```

**Semantics:**

- `thread_ref`: Tracking reference belonging to the thread root.
- `limit`: Maximum page size per call. Default 100.
- `cursor`: Optional opaque pagination token from a prior call.
- **Returns:** A standard `Page` wrapper encapsulating `items: list[MessageRef]` and `next_cursor: Cursor | None`.
- **Behavioral constraints:** Messages within the returned page are guaranteed to be sorted **oldest-first** (chronological order, reading down from the root message). To drain an entire thread, use `ota_connect.iter_all(read_thread, thread_ref=...)`.

**Errors:**

- `AdapterMismatchError` — Mismatched provider token. Non-retryable.
- `AdapterUnavailable` — Upstream connection dropped mid-read. Retryable.

**Conformance:** See `tests/vocabulary/messaging/read_thread/`.

---

### `list_recent_messages`

Scans a targeted channel or direct conversation context for the newest message logs, returning a cursor-paginated page.

**Metadata:**

```yaml
idempotency: guaranteed
required_scopes: ["messaging:read"]
destructive: false
```

**Signature:**

```python
def list_recent_messages(
    channel: ChannelRef | IdentityRef,
    *,
    since: datetime | None = None,
    limit: int = 50,
    cursor: Cursor | None = None,
) -> Page[MessageRef]: ...
```

**Semantics:**

- `channel`: Destination context to read. If an `IdentityRef` handle is provided, the engine queries the active DM history for that resolved participant.
- `since`: Optional timezone-aware timestamp. If provided, the adapter filters messages older than the designated threshold. Naive datetimes raise `ValueError` at the framework boundary.
- `limit`: Maximum page size per call. Default 50.
- `cursor`: Optional opaque pagination token from a prior call.
- **Returns:** A standard `Page` wrapper encapsulating `items: list[MessageRef]` and `next_cursor: Cursor | None`.
- **Behavioral constraints:** Messages within the returned page are guaranteed to be sorted **newest-first** (reverse-chronological, scanning back from the present moment).

**Errors:**

- `IdentityResolveError` — Could not map the input `IdentityRef` to an active history context. Non-retryable.
- `AdapterUnavailable` — Upstream connection dropped mid-read. Retryable.

**Conformance:** See `tests/vocabulary/messaging/list_recent_messages/`.

---

## Changelog

- **1.0.0 (2026-05-18)** — Initial capability spec lock-in. Single `send_message` verb collapses both DM and channel send paths (DM resolution driven by `IdentityRef` target type). Capability-level gating semantics removed from `delete_message`; `destructive: true` metadata retained as a linter signal. `read_thread` returns `Page[MessageRef]` for cursor-based safety on large threads. `edit_message` and `delete_message` flagged `best_effort` to align with async reorder windows. Sort-order invariants explicitly locked (oldest-first for threads, newest-first for recent scans). Scope vocabulary clarified as framework-abstract tokens mapped via Contract D.
