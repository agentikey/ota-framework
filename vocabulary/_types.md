---
module: _types
version: 1.0.0
status: stable
description: Shared reference types used across the ota_connect capability vocabulary. Imported by every capability spec.
---

# _types — shared reference types

## Intent

Defines the small set of cross-cutting types that capabilities use in their verb signatures. Centralizing these types prevents drift (two capabilities accidentally defining a "MessageRef" with different fields) and makes refactor impact visible via the `references_types:` declaration in each capability's frontmatter.

### Non-Goals

- This module does NOT define types specific to a single capability — those live in the capability's own spec file.
- This module does NOT define adapter-internal representations — adapters may use their own types internally and translate at the boundary.
- This module does NOT define framework internals like state schemas, identity registry shapes, secrets, or audit event records — those live in their respective contracts.

---

## Identity & references

### `IdentityRef`

Abstract reference to a person, group, or system entity. Framework resolves to an adapter-specific identifier at the verb boundary via the IdentityProvider seam.

**Form:**

```python
IdentityRef = str  # canonical form; parsed at framework boundary
# Accepted string forms (prefix-driven for deterministic parsing):
#   "handle:@<name>"         e.g. "handle:@jamie"
#                            → looked up via relationships.md or locally verified
#                              system rosters; resolved per bound adapter
#   "mailto:<address>"       e.g. "mailto:jamie@coachfirm.com"
#                            → direct routing via SMTP or email-bound enterprise channels
#   "raw:<adapter>:<id>"     e.g. "raw:slack:U02ABCD"
#                            → opaque escape-hatch bypassing identity resolution;
#                              framework warns on use
```

**Semantics:**

- Routines pass strings; framework wraps and resolves at the adapter boundary.
- Resolution returns the adapter-specific identifier (Slack user ID, email address, Teams UPN, Asana user GID, etc.) for whichever adapter the bound capability is using.
- `handle:` form is preferred for cross-tool portability.
- Unresolvable handles raise `IdentityResolveError` at call time. Pre-flight validation at install time catches handles referenced in routine templates and defaults.

---

### `MessageRef`

Opaque reference to a message sent or received via the `messaging` capability. Returned by send verbs; consumed by subsequent verbs that act on existing messages (reply, edit, react, delete).

**Form:**

```python
@dataclass(frozen=True)
class MessageRef:
    id: str                        # adapter-specific message ID
    channel: ChannelRef            # the channel / DM this message lives in
    sent_at: datetime              # timezone-aware
    permalink: str | None          # adapter-provided permalink if available
    adapter: str                   # name of the adapter that produced this ref
```

**Semantics:**

- Treated as opaque by routines — fields are inspectable for audit / UI but routines should not branch on adapter-specific values.
- Passing a `MessageRef` from one adapter to a verb call bound to a different adapter raises `AdapterMismatchError`.
- `permalink` is best-effort; some adapters don't expose one.

---

### `ThreadRef`

Opaque reference to a message thread within the `messaging` capability.

**Form:**

```python
@dataclass(frozen=True)
class ThreadRef:
    id: str                        # adapter-specific thread ID (e.g., Slack thread_ts)
    channel: ChannelRef
    started_at: datetime
    adapter: str
```

---

### `ChannelRef`

Opaque reference to a channel, group, or DM context within the `messaging` capability.

**Form:**

```python
@dataclass(frozen=True)
class ChannelRef:
    id: str                        # adapter-specific channel ID
    kind: Literal["channel", "dm", "group_dm"]
    name: str | None               # display name where applicable; None for DMs in some adapters
    adapter: str
```

---

### `EmailRef`

Opaque reference to an email message handled by the `email` capability.

**Form:**

```python
@dataclass(frozen=True)
class EmailRef:
    id: str                        # adapter-specific (e.g., Gmail message ID)
    message_id_header: str | None  # RFC-5322 Message-ID header value, when present
    thread: EmailThreadRef | None
    sent_at: datetime
    adapter: str
```

**Semantics:**

- Intentionally distinct from `MessageRef` — email lifecycle, threading, and addressing differ structurally from chat messaging. Forcing a shared base would mean many optional fields and weaker invariants.
- `message_id_header` is the universal cross-system identifier; preferred for cross-adapter references (e.g., correlating an email send with a CRM activity log).

---

### `EmailThreadRef`

Opaque reference to an email conversation thread.

**Form:**

```python
@dataclass(frozen=True)
class EmailThreadRef:
    id: str                        # adapter-specific (e.g., Gmail thread ID)
    subject: str                   # canonical subject (RFC normalization applied)
    started_at: datetime
    adapter: str
```

---

### `DraftRef`

Opaque reference to an unsent email draft staged in the provider's draft index. Distinct from `EmailRef` so the type system can prevent illegal operations (e.g., calling `read_email_thread` on a draft, or passing a sent `EmailRef` to `send_draft`).

**Form:**

```python
@dataclass(frozen=True)
class DraftRef:
    id: str                        # adapter-specific draft ID (e.g., Gmail Draft ID)
    subject: str                   # working subject line
    created_at: datetime           # timezone-aware
    adapter: str                   # name of the adapter that produced this ref
```

**Semantics:**

- A `DraftRef` is consumed by `send_draft(...)`, which returns an `EmailRef` reflecting the post-delivery state.
- Mutating a draft (re-editing) is out of scope for v1.0; routines compose a new draft rather than rewrite an existing one.
- After successful `send_draft`, the draft is destroyed on the provider side and the `DraftRef` becomes invalid.

---

## Content

### `Block`

Structured content payload for capabilities that support rich rendering (messaging, email, document_storage). Lowest-common-denominator representation is plain text via `.text`; richer adapters render the structured form natively, less rich adapters fall back to text.

**Form:**

```python
@dataclass
class Block:
    kind: Literal["text", "section", "header", "divider", "actions", "image", "code"]
    text: str | None = None          # plain-text content / fallback rendering
    children: list[Block] | None = None
    actions: list[Action] | None = None
    image_ref: FileRef | None = None
    language: str | None = None      # for kind="code"
```

**Semantics:**

- Every Block MUST have a plain-text fallback in `.text`. Adapters that can't render the structured form render the fallback.
- Adapters declare their Block support level in their manifest (`text_only` | `basic_blocks` | `full_blocks`). Routines using features beyond the bound adapter's level either degrade gracefully (use fallback) or fail install with `CapabilityDegraded`, depending on routine policy.
- `Block` is intentionally minimal — Slack Block Kit has dozens of element types; only the cross-tool subset lives here. Adapter-specific block types live in `ota_connect.messaging.slack.*` extensions.

---

### `Action`

User-actionable element embedded in a `Block` (button, select, link). Routes user clicks back to routine logic via the framework's action-dispatch mechanism.

**Form:**

```python
@dataclass(frozen=True)
class Action:
    kind: Literal["button", "select", "link"]
    label: str
    value: str                       # opaque payload the framework routes back to the routine
    style: Literal["default", "primary", "danger"] = "default"
    options: list[str] | None = None # for kind="select"
```

---

### `FileRef`

Reference to a file the framework can access — either a local path or a reference into the `file_storage` capability.

**Form:**

```python
FileRef = str  # canonical form
# Accepted string forms:
#   "local:<absolute_path>"        framework-local file (filesystem under deployment)
#   "storage:<adapter>:<path>"     e.g. "storage:gdrive:/Marketing/logo.png"
```

**Semantics:**

- Routines should prefer `storage:` form for cross-deployment portability.
- `local:` form ties the routine to a specific deployment's filesystem; framework warns in strict mode.

---

### `Attachment`

A file paired with display metadata, for inclusion in messages or emails.

**Form:**

```python
@dataclass(frozen=True)
class Attachment:
    file: FileRef
    display_name: str                # name shown to recipient
    mime_type: str | None = None     # framework infers from file extension if None
    inline: bool = False             # for emails: inline-rendered (cid) vs. attached
```

---

## Status & enums

### `DeliveryStatus`

```python
DeliveryStatus = Literal["queued", "sent", "delivered", "read", "failed"]
```

**Semantics:**

- Not all adapters report all statuses (raw SMTP can't report `read`; Slack reports through different lifecycle). Adapter manifests declare which statuses they emit; framework normalizes.
- Verbs that return `DeliveryStatus` may return `"sent"` immediately and update asynchronously via the routine's notification surface.

---

### `Importance`

```python
Importance = Literal["normal", "important", "urgent"]
```

**Semantics:**

- Maps to Teams importance flag, email priority headers (X-Priority, Importance), Slack message styling. Adapters without a native concept ignore it.

---

## Errors

All `ota_connect` capability verbs raise exceptions from a single hierarchy rooted at `OTAConnectError`. Framework-level retry, observability, and audit logic dispatches on these base classes.

### Hierarchy

```python
class OTAConnectError(Exception):
    """Base for all errors raised from ota_connect.* capabilities."""
    adapter: str               # which adapter raised
    capability: str            # which capability
    verb: str                  # which verb
    retryable: bool            # framework retry hint (not a guarantee)


class IdentityResolveError(OTAConnectError):
    """The IdentityRef could not be resolved for the bound adapter."""
    handle: str
    candidates: list[str]      # fuzzy-match suggestions, if IdentityProvider supports them


class AdapterMismatchError(OTAConnectError):
    """A ref produced by adapter A was passed to a verb bound to adapter B."""
    ref_adapter: str
    bound_adapter: str


class RecipientUnreachable(OTAConnectError):
    """Recipient exists but cannot be delivered to (deactivated, DMs disabled, etc.)."""
    reason: str


class RateLimited(OTAConnectError):
    """Upstream rate-limited; framework will retry per adapter policy."""
    retry_after: timedelta | None
    retryable: bool = True


class MessageRejected(OTAConnectError):
    """Adapter accepted arguments but upstream refused (content filter, policy, etc.)."""
    reason: str


class AdapterUnavailable(OTAConnectError):
    """Adapter cannot reach upstream (network failure, auth expired, etc.)."""
    retryable: bool = True


class CapabilityDegraded(OTAConnectError):
    """The bound adapter does not satisfy this verb's required scopes or feature level."""
    missing_scope: str | None = None
    missing_feature: str | None = None
```

**Semantics:**

- `retryable` is a framework hint, not a guarantee — the retry policy may still decline based on backoff state, total elapsed time, or routine-level policy.
- `IdentityResolveError.candidates` is populated by the IdentityProvider's fuzzy matcher when available; useful in routine error messages and operator-facing nudges.

---

## Time

This module uses Python stdlib types directly. No custom time types.

- **Timestamps:** `datetime.datetime` — MUST be timezone-aware. Naive datetimes raise `ValueError` at the verb boundary.
- **Durations:** `datetime.timedelta`.

Timezone awareness is enforced framework-wide via a small validator wrapping the adapter boundary. Reason: time-bug class of incidents in scheduling / cadence routines is too costly to leave to convention.

---

## Pagination

### `Cursor`

```python
Cursor = str  # opaque token; adapter-specific format
```

### `Page[T]`

```python
@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    next_cursor: Cursor | None       # None when no more pages
```

**Semantics:**

- List-style verbs return `Page[T]`. Routines iterate by calling the verb again with `cursor=page.next_cursor` until `None`.
- Convenience helper available at `ota_connect.iter_all(verb, **args)` — auto-paginates as a generator. (Framework primitive, not a capability verb.)

---

## Changelog

- **1.0.0 (2026-05-18)** — initial spec; defines IdentityRef, MessageRef, ThreadRef, ChannelRef, EmailRef, EmailThreadRef, DraftRef, Block, Action, FileRef, Attachment, DeliveryStatus, Importance, error hierarchy, time conventions, pagination. IdentityRef and FileRef use prefix-driven string schemas (`handle:`, `mailto:`, `raw:` / `local:`, `storage:`) for deterministic parsing at the framework boundary. DraftRef added during email.md design pass to enforce type-safe separation between unsent drafts and committed emails.
