# OTA Contracts

_v1.0 — locked 2026-05-13._
_Canonical specification for the five OTA contracts. Referenced from `architecture.md`._

Five contracts the seam architecture depends on:

- **Contract A** — `llm_requirements` frontmatter schema (routine → LLM provider negotiation)
- **Contract B** — Audit event canonical schema (framework → audit sink)
- **Contract C** — Routine source manifest format (Agentikey channel → framework)
- **Contract D** — Integration registry schema (registry → framework)
- **Contract E** — Deployment configuration schema (operator → framework wiring)

All five follow the same versioning discipline: every payload carries `schema_version` (semver), additive changes bump minor, breaking changes bump major and require a compatibility window with old payloads supported in parallel for at least one minor release.

---

## Contract A — `llm_requirements` frontmatter schema

Lives in every routine's `routine.yaml`. Tells the framework what the routine needs from an LLM provider so capability negotiation can run at routine-load time, not at runtime.

### Example

```yaml
llm_requirements:
  schema_version: "1.0"
  required: [tool_use]
  preferred: [prompt_caching, parallel_tool_calls]
  forbidden_without: []                 # strong-required (load fails if missing)
  min_context_tokens: 50000
  max_output_tokens: 4096
  cost_tier: balanced                   # cheap | balanced | premium | local
  model_preference:                     # optional; ordered preference within active provider
    - "claude-sonnet-4-6"
    - "claude-haiku-4-5"
  pii_categories: [contact_info, communications]
  data_residency: []                    # empty = any region; ["eu"] = EU-only
  cache_pool: "productivity-shared"
  cache_ttl: "5m"                       # 5m | 1h
  budget:
    max_input_tokens_per_run: 80000
    max_output_tokens_per_run: 4096
    max_usd_per_run: 0.50               # framework refuses to fire if estimated cost exceeds
```

### Field reference

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | semver string | yes | This contract's version. |
| `required` | list of feature flags | yes (can be empty) | Routine refuses to load if active provider lacks any. |
| `preferred` | list of feature flags | no | Routine loads with degraded performance if missing; warning emitted. |
| `forbidden_without` | list of feature flags | no | Strong form of `required` — used for safety-critical features. Distinct from `required` so we can prioritize differently in error messages. |
| `min_context_tokens` | int | no | Default 32_000. Provider's `max_context_tokens()` must be ≥ this. |
| `max_output_tokens` | int | no | Used by scheduler and budget enforcement. |
| `cost_tier` | enum | no | Default `balanced`. Drives provider selection when multiple providers are configured. |
| `model_preference` | list of model IDs | no | Ordered preference *within* the active provider; the provider picks the first available. |
| `pii_categories` | list of category enums | yes (can be `[]` or `[none]`) | Drives audit redaction rules and data residency enforcement. Empty defaults to `[none]` after warning. |
| `data_residency` | list of region codes | no | Empty = any region acceptable. Provider's `metadata().region` must satisfy. |
| `cache_pool` | string | no | Cache pool identifier for prompt caching coordination across routines. |
| `cache_ttl` | enum | no | `5m` (default) or `1h` (Anthropic extended). Ignored if provider doesn't support prompt caching. |
| `budget` | object | no | Hard limits enforced by L0b. Estimated cost computed pre-flight; actual cost tracked per run. |

### Feature flag taxonomy

| Flag | Description | Providers supporting (as of 2026-05) |
|---|---|---|
| `tool_use` | Function calling / tool use loop | Anthropic, OpenAI, Gemini, Bedrock-Anthropic, AzureOpenAI, VertexAI |
| `parallel_tool_calls` | Multiple tool calls in one assistant turn | Anthropic, OpenAI |
| `streaming` | Server-sent streaming responses | All cloud providers |
| `prompt_caching` | Server-side prefix caching with `cache_control` | Anthropic, Bedrock-Anthropic |
| `extended_thinking` | Anthropic extended thinking blocks | Anthropic, Bedrock-Anthropic |
| `computer_use` | Computer-use tool family | Anthropic only |
| `citations` | Inline source citations | Anthropic only |
| `vision` | Image input | Anthropic, OpenAI, Gemini |
| `pdf_input` | Direct PDF input (not pre-extracted) | Anthropic, Gemini |
| `json_mode` | Strict JSON output mode | OpenAI, Gemini, Anthropic |
| `function_strict_schema` | Strict-schema tool args (no hallucinated fields) | OpenAI, Gemini |
| `local_inference` | Runs without outbound network | Ollama, llama.cpp |

### PII category taxonomy

| Category | Includes |
|---|---|
| `none` | Explicit declaration: no PII processed |
| `contact_info` | Email, phone, address, name |
| `identifiers` | Government IDs, employee IDs, customer IDs |
| `financial` | Bank, credit card, transaction data |
| `health` | Medical records, diagnoses, prescriptions (HIPAA-relevant) |
| `biometric` | Fingerprints, face data, voice prints |
| `employment` | HR records, performance data, compensation |
| `behavioral` | Usage logs, click data, preferences |
| `communications` | Message/email/chat bodies |
| `location` | GPS, IP geolocation, residence |
| `custom:<name>` | Escape hatch for client-specific categories |

### Region codes (data residency)

ISO 3166-1 alpha-2 country codes plus aggregates: `us`, `eu`, `uk`, `ca`, `au`, `apac`, `latam`, `mea`. Empty list = no constraint.

### Validation rules (enforced at routine-load)

1. `schema_version` must be supported by active framework version.
2. Active LLM provider must satisfy all `required` and `forbidden_without` features. Hard fail if not.
3. Active provider's `max_context_tokens()` ≥ `min_context_tokens`. Hard fail if not.
4. Active provider's `metadata().region` ∈ `data_residency` (if specified). Hard fail if not.
5. If `pii_categories` includes any non-`none` value, `data_residency` must be explicit (empty list with PII triggers warning + audit event).
6. `budget.max_usd_per_run` must be > 0 if present; framework refuses to fire routine runs whose pre-flight estimate exceeds.

---

## Contract B — Audit event canonical schema

JSONL format, one event per line, UTF-8, LF line endings. Append-only. Every event conforms to this envelope.

### Envelope

```json
{
  "schema_version": "1.0",
  "event_id": "01HXXX...",
  "timestamp": "2026-05-13T14:32:17.412Z",
  "event_type": "gate.approved",
  "severity": "info",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "routine_run_id": "0192fc83-7bb2-7c5d-9a16-1c5b3e2a4d77",
  "request_id": null,
  "principal": {
    "id": "op:omar",
    "type": "operator",
    "idp_sub": null,
    "display_name": "Omar"
  },
  "tenant_id": null,
  "deployment": {
    "id": "ota-omar-prod",
    "mode": "managed",
    "edition": "core",
    "version": "1.4.2"
  },
  "source": {
    "component": "conductor",
    "version": "1.4.2"
  },
  "payload": {
    "gate_id": "delete_email",
    "routine_id": "agentikey.inbox-triage",
    "proposed_action_hash": "sha256:abc123...",
    "approval_mode": "approve_and_remember"
  },
  "redactions_applied": ["payload.user_email"]
}
```

### Envelope fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | semver | yes | Audit contract version. |
| `event_id` | ULID or UUIDv7 | yes | Sortable by time; never reused. |
| `timestamp` | ISO 8601 with TZ | yes | Always UTC ("Z" suffix). Monotonic on a single machine. |
| `event_type` | enum (see taxonomy) | yes | Dotted hierarchy: `category.action`. |
| `severity` | enum | yes | `debug` \| `info` \| `warn` \| `error` \| `critical`. |
| `trace_id` | hex32 | yes | OTel trace ID. Same value present in OTel spans for the same operation. |
| `routine_run_id` | UUIDv7 | nullable | One per routine execution. Null for non-routine events (auth, config). |
| `request_id` | UUIDv7 | nullable | One per inbound operator request. Null for autonomous events. |
| `principal` | object | yes | Who caused this event. `id` is `<type>:<identifier>`. |
| `tenant_id` | string | nullable | Enterprise multi-tenancy. Null in Core. |
| `deployment` | object | yes | Stable for the lifetime of a deployment instance. |
| `source` | object | yes | Which framework component emitted the event. |
| `payload` | object | yes | Event-type-specific. Schema defined per type (see below). |
| `redactions_applied` | list of dotted paths | no | Lists which payload fields were redacted. Empty list = nothing redacted. |

### Event type taxonomy

| Category | Events | Severity defaults |
|---|---|---|
| `auth` | `login`, `logout`, `failed`, `mfa_challenge`, `mfa_succeeded`, `mfa_failed` | info / warn for failed |
| `secret` | `read`, `rotated`, `write_attempt`, `not_found` | info / warn for write_attempt / error for not_found |
| `routine` | `loaded`, `load_failed`, `updated`, `rejected`, `run_started`, `run_completed`, `run_failed`, `run_timed_out`, `run_killed`, `run_terminated_incomplete` | info / error for failed / warn for terminated_incomplete |
| `gate` | `proposed`, `approved`, `rejected`, `modified_and_approved`, `auto_approved_by_similarity`, `expired` | info |
| `tool_call` | `invoked`, `succeeded`, `failed`, `blocked_by_policy`, `budget_exceeded` | info / warn for blocked / error for failed |
| `llm` | `request`, `response`, `error`, `rate_limited`, `budget_exceeded` | info / error / warn |
| `integration` | `connected`, `disconnected`, `auth_refreshed`, `auth_failed`, `call_failed` | info / error |
| `routine_source` | `fetched`, `signature_verified`, `signature_failed`, `update_applied`, `update_deferred`, `routine_killed` | info / critical for signature_failed |
| `policy` | `violation`, `egress_blocked`, `pii_leak_attempt`, `secret_leak_attempt`, `kill_override_attempted`, `credential_revoked`, `shared_credential_emergency_exposure`, `identity_credential_emergency_exposure`, `scope_escalation_attempt` | warn / critical |
| `system` | `startup`, `shutdown`, `config_reloaded`, `health_check_failed`, `crash_loop_detected`, `kill_lock_cleared` | info / error / warn for crash_loop |
| `data_subject` | `access_requested`, `erasure_requested`, `erasure_completed` | info |
| `artifact` | `emitted`, `claimed`, `completed`, `failed`, `auto_expired` | info / warn for `auto_expired` |

### Special event payloads

Most event payloads are event-type-specific and documented inline with the emitting component. Two payloads have wide-enough downstream consumers that the schema is fixed by contract.

#### `routine.run_terminated_incomplete`

Emitted whenever a routine run ends abnormally with work in flight. One event type covers all abnormal termination causes so downstream consumers (operator notification, dashboard, dependency-recovery automation) have a single schema to render against.

```json
{
  "cause": "hard_kill_timeout",
  "routine_id": "agentikey.inbox-triage",
  "routine_version": "1.4.2",
  "run_started_at": "2026-05-13T14:00:00Z",
  "run_terminated_at": "2026-05-13T14:15:00Z",
  "steps_completed": ["fetch_inbox", "classify_messages"],
  "steps_in_flight": ["generate_digest"],
  "steps_never_started": ["deliver_digest"],
  "gates_pending": [
    {"gate_id": "delete_email", "auto_rejected": true, "reason": "routine_killed"}
  ],
  "artifacts_emitted": [
    {"id": "classification.batch.0192fc83", "status": "completed", "stale_artifact_ttl": "4h", "expires_at": "2026-05-13T18:15:00Z"},
    {"id": "digest.draft.0192fc84", "status": "failed", "consumers": ["agentikey.morning-summary"], "stale_artifact_ttl": "4h", "expires_at": "2026-05-13T18:15:00Z"}
  ],
  "integration_calls_completed_during_termination": [
    {
      "integration": "gmail",
      "operation": "label_messages",
      "count": 47,
      "result": "succeeded",
      "note": "Side effects retained; cannot be rolled back."
    }
  ],
  "integration_calls_aborted": [
    {
      "integration": "slack",
      "operation": "chat.postMessage",
      "state": "never_invoked"
    }
  ],
  "cleanup_recommendations": [
    "Review 47 Gmail labels applied during termination",
    "Routine agentikey.morning-summary is waiting on failed artifact digest.draft.0192fc84 — manually clear or re-trigger"
  ]
}
```

Fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `cause` | enum | yes | `hard_kill_timeout` \| `emergency_kill` \| `framework_restart` \| `routine_crash` \| `budget_exceeded` \| `gate_timeout_after_kill` |
| `routine_id` | string | yes | The routine that terminated. |
| `routine_version` | semver | yes | Version that was running. |
| `run_started_at` / `run_terminated_at` | ISO 8601 | yes | Bounds of the run. |
| `steps_completed` / `steps_in_flight` / `steps_never_started` | list[string] | yes | Step IDs in each state at termination. Empty lists allowed. |
| `gates_pending` | list[object] | yes | Gates that were waiting at termination; `auto_rejected` indicates framework auto-disposition. |
| `artifacts_emitted` | list[object] | yes | All artifacts touched during the run with final status. `consumers` lists dependent routines for `failed` artifacts. Each entry carries `stale_artifact_ttl` (default `4h`, per-routine override available in Contract C) and computed `expires_at`; framework auto-expires any artifact in `pending` or `failed` state not claimed before `expires_at` and emits `artifact.auto_expired`. Prevents downstream routines from waking on half-baked data from a killed parent. |
| `integration_calls_completed_during_termination` | list[object] | yes | Integration side effects that completed *during the termination window* — operator needs to know these landed. |
| `integration_calls_aborted` | list[object] | yes | Calls planned but never executed. |
| `cleanup_recommendations` | list[string] | yes | Framework-generated; never operator-authored or routine-authored (poisoning vector). |

**Severity rules:** `warn` by default. Promoted to `error` if `integration_calls_completed_during_termination` is non-empty and any of those operations are in the "stateful side effect" class (file writes, message sends, calendar invites, financial transactions). The integration registry declares the class per operation.

**Notification path:** the framework's operator-notification layer renders this event into a human-readable summary delivered through the deployment's configured notification channel (Slack DM, email, dashboard banner). Renderer respects the same redaction rules as the audit sink.

### Redaction rules

Applied by the framework's audit emit pipeline before the event reaches any sink.

1. **`SecretValue` instances** — replaced with `[REDACTED]` and added to `redactions_applied`. Non-negotiable.
2. **PII fields** — if the routine's `pii_categories` includes a category, the framework redacts fields tagged with that category in the payload schema. Replaced with `[PII:<category>]` and added to `redactions_applied`.
3. **High-entropy pattern fallback** — any string ≥ 40 chars with entropy > 4.5 bits/char is replaced with `[POSSIBLE_SECRET]`. Belt-and-suspenders against accidental token leakage. Logged as a `policy.secret_leak_attempt` event in addition.
4. **Known token prefix patterns** — `sk-`, `xoxb-`, `ghp_`, `ya29.`, etc. → `[POSSIBLE_SECRET]`. Same as #3.
5. **Hashed correlation fields** — when a PII value is useful for correlation but the raw value shouldn't appear, emit `<field>_hash: sha256(<value>)` instead. Routines opt in per field.

### Forbidden payload content

The following must never appear in audit:

- Raw LLM prompt content (use `prompt_token_count` and a summary instead)
- Raw LLM response content (use `response_token_count` and `response_hash`)
- Tool call argument bodies (use `args_hash` plus an allowlisted summary; the canonical argument shape lives in observability traces, not audit)
- Integration payload bodies (use `body_hash` and `body_size_bytes`)

This keeps audit high-signal for compliance review and pushes detailed debugging content into the observability pipeline, which has different retention and access controls.

### Validation rules (at emit)

1. `event_type` must be in the taxonomy; unknown types are rejected and replaced with `policy.violation` describing the rejected emit.
2. `severity` of `critical` automatically triggers an out-of-band notification to the operator (delivery channel configured per deployment).
3. `redactions_applied` must accurately reflect redactions performed; auditor tests verify by attempting to find raw secrets in payloads.
4. Events older than `now - 5 minutes` or newer than `now + 1 minute` are flagged; clock-skew protection.

---

## Contract C — Routine source manifest format

Two distinct manifests:

- **Channel manifest** — catalog returned by the `RoutineSource` when asked "what routines are available?"
- **Routine bundle manifest** — `routine.yaml` inside each routine bundle; describes one routine.

### Channel manifest

Returned by `RoutineSource.list_available()`. Signed by the channel's private key. Cached locally between fetches.

```yaml
channel:
  id: "agentikey-prod"
  schema_version: "1.0"
  generated_at: "2026-05-13T12:00:00Z"
  signing_key_id: "agentikey-2026-05"
  next_signing_key_id: "agentikey-2026-06"  # for rotation
  signature:
    algorithm: "ed25519"
    value: "base64..."
    signed_fields: ["channel", "routines"]

routines:
  - id: "agentikey.inbox-triage"
    name: "Inbox Triage"
    description: "Triages inbox into action / read / archive with morning digest"
    category: "productivity"
    deprecated: false
    license: "agentikey-commercial-revocable-v1"
    versions:
      - version: "1.4.2"
        framework_compat: ">=1.3, <2.0"
        released_at: "2026-05-10T08:00:00Z"
        expires_at: "2027-05-10T08:00:00Z"     # MANDATORY
        bundle_url: "channel://agentikey/inbox-triage/1.4.2.tar.gz"
        bundle_sha256: "abc123..."
        bundle_size_bytes: 14823
        signature:
          algorithm: "ed25519"
          key_id: "agentikey-2026-05"
          value: "base64..."
        changelog_url: "channel://agentikey/inbox-triage/1.4.2.changelog.md"
        kill_status: "active"                  # active | soft_killed | hard_killed | emergency_killed
        kill_grace_period: "15m"               # optional; overrides default for hard_killed only
```

### Channel manifest fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `channel.id` | string | yes | Stable channel identifier. |
| `channel.schema_version` | semver | yes | Manifest contract version. |
| `channel.generated_at` | ISO 8601 | yes | When this manifest was signed. |
| `channel.signing_key_id` | string | yes | Identifies which public key verifies this signature. |
| `channel.next_signing_key_id` | string | no | For seamless key rotation; framework should pre-fetch the next public key. |
| `channel.signature` | object | yes | Signature over the entire manifest minus the signature field itself. |
| `routines[].id` | reverse-DNS string | yes | Globally unique routine identifier. |
| `routines[].versions[]` | list | yes | Newest-first; multiple versions allowed for compat windows. |
| `routines[].versions[].framework_compat` | semver range | yes | Framework version range this routine version supports. |
| `routines[].versions[].expires_at` | ISO 8601 | yes | Mandatory; routine refuses to run past expiry (offline grace tiers apply). |
| `routines[].versions[].signature` | object | yes | Per-version signature; verified independently of channel signature. |
| `routines[].versions[].kill_status` | enum | yes | `active` \| `soft_killed` \| `hard_killed` \| `emergency_killed`. See **Kill semantics** below for behavioral contract per status. |
| `routines[].versions[].kill_grace_period` | duration | no | Overrides default grace period for `hard_killed` only (default `15m`). Ignored for other statuses. |

### Kill semantics

Four statuses, distinct behavioral contracts. The framework enforces these at runtime; routines cannot override.

| Status | Current run | Wake behavior | Credential revocation | Egress allowlist | Use case |
|---|---|---|---|---|---|
| `active` | Normal | Normal | None | Normal | Healthy state. |
| `soft_killed` | Continues | Continues with audit warning + operator nudge per wake | None | Normal | Deprecation announcement, license expiry warning, EOL countdown. |
| `hard_killed` | Finishes within `kill_grace_period` (default 15m); gates auto-reject after grace; terminates at next clean boundary if grace expires mid-run | Permanently locked via `system.kill_lock` | None auto-applied; operator-driven via CLI | Normal until operator revokes | Normal end-of-life, contract end, version sunset. |
| `emergency_killed` | Aborts at next tool-call boundary; in-flight artifacts marked `failed` | Permanently locked via `system.kill_lock`; immediate | Mandatory; local invalidation immediate, remote revocation best-effort | Mandatory; integration domains removed from routine's egress allowlist | Security incident, compromised signing key, malicious update detected, data leak. |

**`system.kill_lock`:**

- Persisted in framework state (L0 framework SQLite), not the routine's L4 state — the routine has no write access.
- Checked at every scheduler tick, every event-hook wake, every conductor route attempt. Survives framework restarts.
- Cleared only by: (a) the channel returning `kill_status: active` again in a subsequent signed manifest (correction case), or (b) explicit operator override via `ota-cli kill --unlock <routine-id>` (audit-logged as `policy.kill_override_attempted` regardless of outcome, then `system.kill_lock_cleared` on success).

**Boundary definitions:**

- *Tool-call boundary* (for `emergency_killed`): immediately before the next outbound LLM or integration call. The currently-in-flight HTTP request is allowed to complete (you can't unsend it); no follow-up calls execute.
- *Clean boundary* (for `hard_killed` grace expiry): between steps, never mid-tool-call. State mutations complete or roll back at the step boundary, not partway through.

**Operator override stance:**

- `hard_killed`: no override; channel decision is authoritative. Operator can `ota-cli export-state <routine-id>` before lock to retain L4 state and audit log.
- `emergency_killed`: no override even by operator. The kill switch is non-negotiable by design. State export is available via `ota-cli export-state` after lock is set, since L4 data is preserved even though the routine is locked.

**Credential revocation behavior for `emergency_killed`:**

Two layers:

- *Local invalidation* (mandatory, always works): SecretsProvider marks the routine's integration credential reference as `revoked`. No framework code path can use it after the mark.
- *Remote revocation* (best-effort, integration- and binding-dependent): framework calls the integration's revoke endpoint declared in the integration registry (see Contract D preview), conditional on the credential's `binding_level`.

Revocation behavior is driven by `binding_level` per integration (declared on each routine, validated at routine-load):

| `binding_level` | Local invalidation | Remote revocation | Secrets-store effect | Audit event emitted |
|---|---|---|---|---|
| `routine_exclusive` | Immediate | Best-effort via integration's revoke endpoint | Credential deleted from secrets store | `policy.credential_revoked` (severity `info`) |
| `client_shared` | Immediate (this routine only) | Skipped — would break other routines | Credential remains in store for other routines | `policy.shared_credential_emergency_exposure` (severity `critical`) recommending manual rotation if threat extends beyond this routine |
| `identity_bound` | Immediate (this routine only) | Skipped — would log operator out of all delegated work | Credential remains in store; operator session intact | `policy.identity_credential_emergency_exposure` (severity `critical`) recommending operator re-authenticate at IdP if compromise of personal session is suspected |

### Kill-list endpoint

A separate lightweight manifest the framework polls at higher frequency than the main channel manifest, used to propagate kill-status changes with sub-minute latency for `emergency_killed`. Same `RoutineSource` interface; new method `fetch_kill_list()`.

```yaml
kill_list:
  schema_version: "1.0"
  channel_id: "agentikey-prod"
  generated_at: "2026-05-13T14:31:00Z"
  signing_key_id: "agentikey-2026-05"
  signature:
    algorithm: "ed25519"
    value: "base64..."
    signed_fields: ["kill_list"]

entries:
  - routine_id: "agentikey.inbox-triage"
    version: "1.4.2"
    kill_status: "emergency_killed"
    effective_at: "2026-05-13T14:30:00Z"
    reason_code: "compromised_signing_key"   # enum, see below
    reason_summary: "Signing key agentikey-2026-04 was compromised; revoke immediately."
  - routine_id: "agentikey.calendar-prep"
    version: "0.9.1"
    kill_status: "hard_killed"
    effective_at: "2026-05-10T08:00:00Z"
    kill_grace_period: "15m"
    reason_code: "sunset"
    reason_summary: "End-of-life; replaced by agentikey.calendar-prep@1.0.0."
```

**Polling cadence:** framework polls every 60 seconds by default; channel-configurable down to 30s for emergency-sensitive deployments. Polling is outbound-only (same network posture as everything else), tiny payload (a few hundred bytes for a healthy channel), and cheap.

**`reason_code` taxonomy** (extensible; channel adds new codes via schema minor releases):

| Code | Used with | Meaning |
|---|---|---|
| `sunset` | `hard_killed` | Normal end-of-life. |
| `deprecated` | `soft_killed` | Replacement available; warn but allow. |
| `license_expired` | `hard_killed` | License terms ended. |
| `compromised_signing_key` | `emergency_killed` | Channel signing key was compromised; this routine version is no longer trustable. |
| `malicious_update_detected` | `emergency_killed` | Update review identified malicious behavior. |
| `data_leak_in_progress` | `emergency_killed` | Active exfiltration suspected. |
| `vulnerability_disclosed` | `emergency_killed` | CVE-level severity. |
| `contract_terminated` | `hard_killed` | Customer-specific (not from public channel). |

**Reconciliation with main channel manifest:**

- Kill-list is authoritative for kill_status; main channel manifest is authoritative for everything else (versions, signatures, expires_at).
- A kill-list entry that conflicts with the channel manifest (e.g., kill-list says `emergency_killed` but channel manifest still says `active`) is resolved in favor of the kill-list. The framework logs `policy.violation` flagging the inconsistency for channel-side investigation.
- A kill-list entry for a routine_id the framework hasn't seen is stored and applied if/when that routine is encountered (defense against pre-kill installation race).

**Audit events triggered by kill-list updates:**

- `routine_source.routine_killed` — every status transition (severity scales with new status).
- `routine.run_killed` — if a transition stops an actively-running routine.
- `policy.credential_revoked` — for each credential local-invalidated on `emergency_killed`.
- `policy.shared_credential_emergency_exposure` — if any shared credentials were touched.

### Routine bundle manifest (`routine.yaml`)

```yaml
schema_version: "1.0"
id: "agentikey.inbox-triage"
version: "1.4.2"
framework_compat: ">=1.3, <2.0"

metadata:
  name: "Inbox Triage"
  description: "Triages inbox into action / read / archive"
  author: "Agentikey"
  author_url: "https://agentikey.com"
  category: "productivity"
  tags: ["email", "morning", "digest"]

dependencies:
  routines:
    - id: "agentikey.identity-context"
      version_range: ">=1.0, <2.0"
      optional: false
  integrations:
    - id: "gmail"
      scopes: ["read", "label", "modify"]
      optional: false
      binding_level: routine_exclusive       # routine_exclusive | client_shared | identity_bound
      on_emergency_kill: burn_credential
    - id: "openai"
      optional: false
      binding_level: client_shared
      on_emergency_kill: revoke_routine_access
    - id: "ms365"
      scopes: ["Mail.Read", "Calendar.Read"]
      optional: false
      binding_level: identity_bound
      on_emergency_kill: revoke_routine_grant
    - id: "slack"
      scopes: ["chat:write"]
      optional: true
      binding_level: client_shared
      on_emergency_kill: revoke_routine_access

capabilities:
  provides: ["inbox.triage", "morning.digest"]
  consumes: []

llm_requirements:
  # see Contract A
  schema_version: "1.0"
  required: [tool_use]
  preferred: [prompt_caching, parallel_tool_calls]
  min_context_tokens: 50000
  cost_tier: balanced
  pii_categories: [contact_info, communications]
  cache_pool: "productivity-shared"
  cache_ttl: "5m"
  budget:
    max_usd_per_run: 0.50

knobs:
  - name: digest_time
    type: time
    default: "07:00"
    description: "When to deliver the morning triage digest"
    timezone: "operator"
  - name: notify_threshold
    type: enum
    values: [high, medium, low, off]
    default: "high"
    description: "Slack DM threshold for urgent items"
  - name: include_promotions
    type: bool
    default: false
    description: "Include Promotions tab in triage"

automation:
  cadence:
    - id: "morning_digest"
      cron: "0 7 * * *"
      timezone: "operator"
      action: "deliver_digest"
      on_missed:
        strategy: "run_if_within"
        tolerance: "4h"
  events:
    - id: "incremental_classify"
      on: "integration.gmail.message_received"
      action: "classify_one"
      debounce: "30s"

gates:
  - id: "delete_email"
    description: "Confirm before permanently deleting an email"
    approver_default: "operator"
    approval_modes: [approve, approve_and_remember, tune_and_approve]
    similarity_function: "subject_sender_hash"
    expires_after: "2h"

state:
  shards:
    - name: "triage_state"
      schema_url: "schemas/triage_state.json"

artifacts:
  stale_artifact_ttl: "4h"            # override framework default; framework auto-expires unclaimed artifacts after this

files:
  - path: "system.md"
    role: "system_prompt"
    sha256: "..."
  - path: "steps/digest.md"
    role: "step"
    sha256: "..."
  - path: "steps/classify_one.md"
    role: "step"
    sha256: "..."
  - path: "gates/delete_email.md"
    role: "gate_template"
    sha256: "..."
  - path: "schemas/triage_state.json"
    role: "state_schema"
    sha256: "..."

signature:
  algorithm: "ed25519"
  key_id: "agentikey-2026-05"
  value: "base64..."
  signed_fields: ["id", "version", "framework_compat", "files", "llm_requirements", "dependencies"]
```

### Routine bundle manifest fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | semver | yes | Routine manifest contract version. |
| `id` | reverse-DNS string | yes | Must match channel manifest entry. |
| `version` | semver | yes | Routine's own version (not the framework's). |
| `framework_compat` | semver range | yes | Framework versions this routine works against. |
| `metadata` | object | yes | Display info. Not load-bearing. |
| `dependencies.routines` | list | yes | Other routines this one depends on, with version ranges. Framework resolves transitively. |
| `dependencies.integrations` | list | yes | Required external integrations with declared scopes, binding level, and emergency-kill behavior. |
| `dependencies.integrations[].binding_level` | enum | yes | `routine_exclusive` (credential unique to this routine — e.g., per-routine webhook URL, per-routine API key) \| `client_shared` (credential shared across multiple routines for this operator — e.g., one OpenAI API key, workspace-level Slack bot token) \| `identity_bound` (credential tied to the operator's IdP identity — e.g., SAML/OIDC refresh token, Microsoft Graph multi-scope token, Atlassian site-level grant). Drives revocation behavior on `emergency_killed`. |
| `dependencies.integrations[].on_emergency_kill` | enum | yes | `burn_credential` (local invalidate + remote revoke + delete from secrets store; only valid with `routine_exclusive`) \| `revoke_routine_access` (local invalidate only, credential remains for other routines; only valid with `client_shared`) \| `revoke_routine_grant` (local invalidate + emit `policy.identity_credential_emergency_exposure` event; only valid with `identity_bound`). Mismatched binding/kill combinations fail validation. |
| `capabilities.provides` | list of capability strings | no | Used by conductor's capability-based routing. |
| `capabilities.consumes` | list | no | For routines that act on artifacts emitted by other routines. |
| `llm_requirements` | object | yes | See Contract A. |
| `knobs` | list of knob declarations | no | User-tunable surface. Empty means routine is opaque to user. |
| `automation` | object | no | Cron + event hooks. Empty means routine only fires by user request. |
| `gates` | list of gate declarations | no | Human-in-the-loop steps with approval modes. |
| `state.shards` | list | no | SQLite tables this routine reads/writes (L4 state). |
| `files` | list with paths + sha256 | yes | Every file in the bundle with its hash. Signed. |
| `signature` | object | yes | Ed25519 signature over `signed_fields`. |

### Knob type taxonomy

| Type | Constraints | Example |
|---|---|---|
| `bool` | `default: true|false` | feature flag |
| `int` | `default`, optional `min`/`max` | retry count |
| `float` | `default`, optional `min`/`max` | confidence threshold |
| `string` | `default`, optional `max_length`, `pattern` (regex) | channel name |
| `enum` | `values: [...]`, `default` | severity level |
| `time` | `default: HH:MM`, `timezone: operator|UTC|<tz>` | digest time |
| `duration` | `default: <human>`, e.g. `30s`, `5m`, `4h` | debounce |
| `cron` | `default: <expr>`, `timezone` | custom schedule |
| `secret_ref` | references a key in SecretsProvider | API key knob |
| `integration_ref` | references an integration in registry | choose Slack channel |
| `list[<inner>]` | nested type | list of channels |

### Validation rules

1. **Signature verification first** — bundle is rejected before any other parsing if signature fails. Critical audit event emitted.
2. **`framework_compat` checked** — routine refuses to load if active framework version doesn't satisfy the range.
3. **`dependencies.routines`** resolved transitively; missing or unsatisfiable dependencies block load.
4. **`dependencies.integrations`** check active registry; routine loads only if all non-optional integrations are present and have the requested scopes.
5. **`llm_requirements`** validated per Contract A.
6. **`files[].sha256`** computed at load and compared; mismatch = critical audit event + load fails.
7. **`expires_at`** from channel manifest enforced; offline grace tiers (5d notify → 7d read-only → 14d full stop) apply per the locked-in private-channel design.
8. **`kill_status`** checked at every load and at runtime against both the main channel manifest and the kill-list endpoint (kill-list takes precedence on conflict):
   - `active` — normal operation.
   - `soft_killed` — load with warning audit event; continue running with periodic operator nudges.
   - `hard_killed` — current run finishes within `kill_grace_period` (default 15m); gates auto-reject after grace; framework sets `system.kill_lock` at termination. No future wakes.
   - `emergency_killed` — current run aborts at next tool-call boundary; in-flight artifacts marked `failed`; credentials revoked per `on_emergency_kill` per integration; egress allowlist updated to remove revoked integrations; `system.kill_lock` set immediately. No future wakes.
9. **`dependencies.integrations[].binding_level` + `on_emergency_kill` combinations**: must be a valid pair — `routine_exclusive + burn_credential`, `client_shared + revoke_routine_access`, or `identity_bound + revoke_routine_grant`. Any other combination fails routine load with a critical audit event.

### Virtual credential scoping

Some integrations (Microsoft Graph, Atlassian site-level grants, GitHub fine-grained PATs with scope unions) issue a single physical credential carrying the union of all scopes the operator has authorized across multiple routines. Routine A requests `Mail.Read`, routine B requests `Calendar.Read`, the user authenticates once, and the resulting token has both scopes. Without scoping, routine A could call `Calendar.Read` endpoints with the same token routine B uses — a confused-deputy bug.

The framework solves this with **virtual credential scoping** enforced at the SecretsProvider boundary:

1. **Authoring time:** every routine declares `scopes` in its `dependencies.integrations[]` entry — the scope subset it expects to use.
2. **OAuth flow:** the framework requests the *union* of all declared scopes across loaded routines for a given integration. Single OAuth flow, single physical token in the secrets store.
3. **Runtime:** the SecretsProvider does not return raw credentials to routine code. It returns a `ScopedCredential` wrapper that internally references the physical token but advertises only the routine's declared scopes.
4. **L0b enforcement:** every integration call passes through L0b. L0b knows the calling routine's declared scopes and the integration registry's per-operation scope requirements. Calls requiring scopes outside the routine's declaration are blocked.
5. **Audit:** a routine attempting to invoke an out-of-scope operation triggers `policy.scope_escalation_attempt` (severity `warn` for accidental, escalated to `critical` if a pattern emerges).

Effects of this design:

- **Cross-routine scope leakage is impossible by construction** — even if the physical token has 10 scopes, routine A only sees its 3.
- **`emergency_killed` on `identity_bound` credentials** revokes the routine's *virtual scope set* in the SecretsProvider's ACL. The physical token continues to function for healthy routines via their own virtual scopes.
- **Operator messaging is precise** — the `policy.identity_credential_emergency_exposure` event names exactly which virtual scopes were revoked and which remain active on the physical token, so the operator knows what's still exposed.

Validation: routine load fails if a routine's declared `scopes` includes a value not defined in the integration registry's scope vocabulary for that integration (see Contract D preview).

---

## Cross-contract invariants

These hold across all three contracts:

1. **Schema versioning is semver, additive minor, breaking major.** Old payloads remain readable for at least one minor release after a deprecation. Schema version is always the first field.
2. **Signatures use Ed25519.** Key rotation is in-band via `next_signing_key_id`; framework pre-fetches and trusts both during overlap.
3. **Hash algorithm is SHA-256** for content integrity. Where stronger integrity is needed (audit immutability), the sink is responsible (S3 Object Lock, etc.).
4. **IDs are reverse-DNS** for routines and integrations (`agentikey.inbox-triage`, `slack`). Event IDs and trace IDs follow their respective standards (ULID/UUIDv7, OTel hex).
5. **Timestamps are RFC 3339 / ISO 8601 with explicit timezone**, UTC by default. No naive timestamps anywhere.
6. **Capability flags are lowercase snake_case** strings. Provider `supports()` and routine `required`/`preferred` agree on the vocabulary.
7. **Credential revocation cascades to egress.** Whenever L0b revokes a credential (operator-driven on `hard_killed`, framework-driven on `emergency_killed`), the integration's endpoints are removed from the routine's egress allowlist atomically. Defense-in-depth against stale credential references — even if a code path holds a reference to a revoked credential, outbound HTTP is blocked at the network policy layer.
8. **Kill propagation has two cadences.** Main channel manifest refreshes per channel-configured interval (default hourly); kill-list endpoint polls every 60s (channel-configurable down to 30s). Kill-list is the authoritative source for `kill_status` when the two disagree.
9. **Contract C ↔ Contract D reconciliation at routine-load.** Every routine's `dependencies.integrations[].id` must exist in the active integration registry; declared `binding_level` must be supported by the integration; declared `scopes` must all exist in the integration's vocabulary. Any mismatch fails routine load with a critical audit event. Symmetrically, an integration's `emergency_killed` transition cascades to every routine depending on it; the cascade respects each routine's declared `on_emergency_kill` for that integration. **In addition, L0b applies a global egress block for the integration's `egress_patterns` as a secondary hard-kill defense — even routines that declared `revoke_routine_access` (local-invalidation-only) cannot reach the compromised integration during the cascade window.** The global egress block is lifted when the integration's `kill_status` returns to `active` via a subsequent signed manifest update.
10. **Identity Provider and SecretsProvider are separate seams.** The Identity Provider answers "who is this human?" (operator, IdP `Principal`, group membership). The SecretsProvider answers "what credential does this routine use to call this integration?" (per-routine OAuth tokens, API keys, mTLS certs). The only link between them is the `identity_bound` binding level (Contract C, dependencies.integrations[]), which tells the SecretsProvider to look up a credential associated with a specific `Principal`. Conflating these into a single seam is the regret-level mistake; the separation is load-bearing.
11. **Audit ↔ Observability linkage via `trace_id`.** Every audit event (Contract B) and every OTel span (Observability Sink) carries the same `trace_id`. The dashboard renders each audit event with a click-through to the underlying OTel trace, surfacing detailed timing, LLM call bodies, tool argument shapes, and integration HTTP payloads that audit deliberately excludes. Auditors get the high-signal compliance view; SREs get the full diagnostic view; one click bridges them. The two sinks remain physically separate (different retention policies, different access controls, different downstream systems) but logically joined by the trace ID.

---

## Resolved decisions

These were open questions in the original draft. Locked in:

1. **Authoring tool support.** `ota-cli` ships day one with `validate <routine-dir>` (validates `routine.yaml` against bundled JSON Schema), `sign <bundle>` (Ed25519 signing using local key), `verify <bundle>` (signature + sha256 check against channel manifest), and `scaffold <id>` (generates a routine skeleton). CLI is a separate work item but on the critical path for any routine authoring beyond Omar's hand-crafted ones.
2. **Schema registry.** JSON Schemas for all three contracts live in the framework repo under `/contracts/v1/`, bundled with the framework binary. Routines are validated against the active framework's bundled schema at load. Versioned alongside the framework; major framework version bump = new schema directory (`/contracts/v2/`) and a compatibility window during which both versions are bundled.
3. **Capability flag governance.** Omar owns the canonical taxonomy. Clients add custom flags as `custom:<name>` in routine `llm_requirements` until a flag is promoted to first-class via a framework minor release. Promotion threshold (rule of thumb): five or more clients independently using the same `custom:<name>` triggers promotion review.
4. **Multi-channel namespacing.** Reverse-DNS routine IDs already namespace cleanly (`agentikey.*` vs. `internal.*`). Conductor uses an explicit `source_priority` config when two channels provide overlapping capabilities. Per-source kill-list endpoints are polled independently.
5. **Audit retention.** Core's `JSONLLocalSink` defaults to 90 days rolling with daily file rotation. Configurable per deployment via framework config (`audit.retention_days`). Enterprise sinks delegate retention to the downstream system's policy — the framework emits to the sink and forgets.

---

## Operator notification routing

Audit events are for compliance and forensics — the wrong tool for "tell the operator something is on fire." Notification routing is a separate pipeline that subscribes to audit events and delivers human-readable summaries through operator-configured channels, with severity-driven urgency and rate-limiting to prevent storms.

### Urgency matrix

Mandatory severity-to-delivery mapping; deployment config can tighten but not loosen.

| Severity | Delivery | Acknowledgement required | Default channels |
|---|---|---|---|
| `info` | Dashboard log only | No | Dashboard |
| `warn` | Dashboard banner + weekly digest email | No | Dashboard, email digest |
| `error` | Immediate notification on operator's primary channel | No | Slack DM or email (deployment-configured) |
| `critical` | Immediate notification + retry-until-acknowledged | Yes (timeout-escalates to fallback chain) | Slack DM + push + PagerDuty/OpsGenie if configured |

`critical` events that aren't acknowledged within the configured timeout escalate through a fallback chain (e.g., primary Slack DM → secondary email → PagerDuty). Escalation steps and timeouts are deployment config, not contract.

**Acknowledgement persistence.** Ack state for `critical` notifications is stored in the framework's L0 SQLite under a `notifications` table. This guarantees:

- Critical banners on the dashboard persist across framework restarts until the operator explicitly acknowledges (no banner-disappears-on-reboot bug).
- Escalation timers are durable — if the framework restarts mid-escalation, the timer resumes from its persisted state rather than restarting from zero.
- Audit trail of acknowledgements (who, when, from which channel) is queryable for compliance review.
- Retention matches the audit sink retention policy (default 90 days rolling).

### Configuration shape

```yaml
notifications:
  schema_version: "1.0"

  channels:
    primary_slack:
      type: slack_dm
      user: "U0123456"
    primary_email:
      type: email
      address: "omar@agentikey.com"
    pager:
      type: pagerduty
      service_key_secret: "secret:pagerduty_key"

  routing:
    info:
      delivery: [dashboard]
    warn:
      delivery: [dashboard]
      digest:
        channel: primary_email
        cadence: "weekly"
    error:
      delivery: [primary_slack, dashboard]
    critical:
      delivery: [primary_slack, push, pager]
      acknowledgement:
        required: true
        timeout: "5m"
        escalation_chain: [primary_slack, primary_email, pager]

  rate_limiting:
    per_routine_per_event_type:
      window: "10m"
      max_notifications: 5
      on_exceeded: "coalesce_into_summary"
    storm_detection:
      window: "5m"
      threshold_events_same_type: 20
      action: "suppress_individual_emit_single_summary"
      summary_event_type: "system.notification_storm_summary"
```

### Rate limiting rules

Notification storms are the operational failure mode: a single misbehaving routine emitting one event per second crashes the operator's attention budget and trains them to ignore notifications. Three defenses:

1. **Per-routine-per-event-type throttling.** Default: ≤5 notifications per 10-minute window for the same `(routine_id, event_type)` pair. Beyond that, individual notifications are coalesced into a single summary notification at window close.
2. **Storm detection.** If ≥20 same-type events fire in 5 minutes (across any routines), suppress individual notifications, emit a single `system.notification_storm_summary` notification with counts and pointers to the underlying audit events, and switch the affected event type into summary-only mode until the storm subsides.
3. **Crash-loop detection.** A separate framework subsystem watches for `routine.run_failed` patterns matching crash-loop signatures (≥5 failures in 10 minutes for the same routine). When detected, the framework emits one `system.crash_loop_detected` event (severity `error`), automatically transitions the routine to a backoff state, and suppresses individual `run_failed` notifications until the loop is broken.

`critical` events are exempt from rate limiting by default — security-class events should not be silently coalesced. Deployment config can override this for specific event types if needed (rare, and audit-logged).

### Notification payload shape

Rendered from the underlying audit event by a framework-owned renderer (not routine-authored, to prevent poisoning). Always respects the same redaction rules as the audit sink.

```json
{
  "schema_version": "1.0",
  "notification_id": "01HXXX...",
  "emitted_at": "2026-05-13T14:32:17.412Z",
  "severity": "critical",
  "title": "Routine emergency-killed: agentikey.inbox-triage",
  "summary_markdown": "Routine `agentikey.inbox-triage@1.4.2` was emergency-killed at 14:30 UTC...",
  "audit_event_ref": "01HXXX...",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "actions": [
    {"label": "Acknowledge", "url": "https://ota-dashboard/ack/01HXXX"},
    {"label": "View audit trail", "url": "https://ota-dashboard/audit/4bf92f35"}
  ]
}
```

---

## Contract D — Integration Registry

Defines the schema for **integration declarations** — the canonical manifest of every external system OTA can talk to. Each declaration describes available operations, authentication styles, scope vocabulary, side-effect classification, revocation endpoints, egress patterns, rate limits, and webhook receivers.

Loaded at framework startup. Consumed by L0b at every integration call (scope enforcement, side-effect class, rate limits, egress allowlist). Consumed by SecretsProvider for OAuth flow construction and credential revocation. Consumed by the routine loader to validate Contract C's `dependencies.integrations[]` entries.

Two manifests, parallel to Contract C:

- **Registry manifest** — catalog of available integrations, signed by the channel.
- **Integration declaration** — per-integration spec, one entry per integration inside the registry.

### Registry manifest

Returned by `IntegrationSource.list_integrations()`. Signed by the channel's private key; cached locally between fetches; refreshed on the same cadence as the routine source channel manifest.

```yaml
registry:
  id: "agentikey-integrations"
  schema_version: "1.0"
  generated_at: "2026-05-13T12:00:00Z"
  signing_key_id: "agentikey-2026-05"
  next_signing_key_id: "agentikey-2026-06"
  signature:
    algorithm: "ed25519"
    value: "base64..."
    signed_fields: ["registry", "integrations"]

integrations:
  - id: "gmail"
    version: "2.1.0"
    framework_compat: ">=1.3, <2.0"
    kill_status: "active"           # same enum as Contract C
    # ... full integration declaration below
```

### Registry manifest fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `registry.id` | string | yes | Stable registry identifier. |
| `registry.schema_version` | semver | yes | Contract D version. |
| `registry.generated_at` | ISO 8601 | yes | When this manifest was signed. |
| `registry.signing_key_id` | string | yes | Identifies which public key verifies this signature. |
| `registry.next_signing_key_id` | string | no | For seamless key rotation. |
| `registry.signature` | object | yes | Ed25519 signature over the entire manifest minus the signature field. |
| `integrations[].id` | reverse-DNS string | yes | Globally unique integration identifier. Must match the `id` referenced in Contract C routines' `dependencies.integrations[].id`. |
| `integrations[].version` | semver | yes | Integration declaration's own version. |
| `integrations[].framework_compat` | semver range | yes | Framework versions this integration declaration supports. |
| `integrations[].kill_status` | enum | yes | `active` \| `soft_killed` \| `hard_killed` \| `emergency_killed`. Same four-state model as Contract C; same kill-list polling applies. |

### Integration declaration

Full example using Gmail — covers OAuth2, multiple binding levels, all three side-effect classes, scope vocabulary, webhook, PII flagging.

```yaml
- id: "gmail"
  version: "2.1.0"
  framework_compat: ">=1.3, <2.0"
  kill_status: "active"

  metadata:
    name: "Gmail"
    vendor: "Google"
    vendor_url: "https://gmail.com"
    category: "email"
    description: "Read, label, send, and modify Gmail messages."

  auth_styles: [oauth2]
  supported_binding_levels: [routine_exclusive, identity_bound]
  default_binding_level: identity_bound

  endpoints:
    base_url: "https://gmail.googleapis.com"
    oauth2:
      authorize_url: "https://accounts.google.com/o/oauth2/v2/auth"
      token_url: "https://oauth2.googleapis.com/token"
      userinfo_url: "https://openidconnect.googleapis.com/v1/userinfo"

  egress_patterns:
    - "gmail.googleapis.com"
    - "oauth2.googleapis.com"
    - "accounts.google.com"
    - "openidconnect.googleapis.com"

  scope_vocabulary:
    - id: "read"
      oauth_value: "https://www.googleapis.com/auth/gmail.readonly"
      description: "Read messages, threads, and labels."
    - id: "label"
      oauth_value: "https://www.googleapis.com/auth/gmail.labels"
      description: "Create, update, and delete labels."
    - id: "modify"
      oauth_value: "https://www.googleapis.com/auth/gmail.modify"
      description: "Modify messages (label, archive, mark read); cannot delete."
    - id: "send"
      oauth_value: "https://www.googleapis.com/auth/gmail.send"
      description: "Send mail on behalf of the user."
    - id: "full"
      oauth_value: "https://mail.google.com/"
      description: "Full mailbox access including delete."
      warns_on_grant: "Prefer narrower scopes; full grants mailbox-wide delete."

  rate_limits:
    requests_per_second: 5
    requests_per_minute: 250
    backoff_strategy: "exponential_with_jitter"
    retry_after_header: "Retry-After"

  revocation:
    routine_exclusive:
      burn_credential:
        method: POST
        url: "https://oauth2.googleapis.com/revoke"
        body: "token=${credential.access_token}"
        headers:
          Content-Type: "application/x-www-form-urlencoded"
        success_status: [200, 400]   # 400 = already invalid, treat as success
    identity_bound:
      revoke_routine_grant:
        local_only: true
        operator_message: "To fully revoke this Google session, visit https://myaccount.google.com/permissions"

  operations:
    - id: "list_messages"
      endpoint: "GET /gmail/v1/users/{user_id}/messages"
      side_effect: read_only
      required_scopes: ["read"]
      idempotent: true
      rate_limit_weight: 1
    - id: "get_message"
      endpoint: "GET /gmail/v1/users/{user_id}/messages/{id}"
      side_effect: read_only
      required_scopes: ["read"]
      idempotent: true
      rate_limit_weight: 1
      pii_classes: [contact_info, communications]
    - id: "label_messages"
      endpoint: "POST /gmail/v1/users/{user_id}/messages/batchModify"
      side_effect: stateful_safe
      required_scopes: ["modify"]
      idempotent: true
      rate_limit_weight: 5
    - id: "send_message"
      endpoint: "POST /gmail/v1/users/{user_id}/messages/send"
      side_effect: stateful_destructive
      required_scopes: ["send"]
      idempotent: false
      rate_limit_weight: 10
      pii_classes: [contact_info, communications]
    - id: "delete_message"
      endpoint: "DELETE /gmail/v1/users/{user_id}/messages/{id}"
      side_effect: stateful_destructive
      required_scopes: ["full"]
      idempotent: true
      rate_limit_weight: 10

  webhooks:
    - id: "message_received"
      receiver_path: "/webhooks/gmail/messages"
      auth_style: "google_pubsub_push"
      secret_ref: "secret:gmail_pubsub_token"
      verification:
        method: "google_pubsub_signature"
      routes_to_event: "integration.gmail.message_received"

  pii_handling:
    payload_contains_pii_default: true
    pii_classes_possible: [contact_info, communications, behavioral]
    response_body_in_audit: false

  data_residency:
    provider_regions: ["us", "eu", "apac"]
    operator_can_pin_region: false   # Gmail does not expose per-tenant region pinning

  signature:
    algorithm: "ed25519"
    key_id: "agentikey-2026-05"
    value: "base64..."
    signed_fields: ["id", "version", "framework_compat", "operations", "scope_vocabulary", "revocation", "egress_patterns", "rate_limits"]
```

### Integration declaration fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | reverse-DNS string | yes | Unique integration ID. |
| `version` | semver | yes | Declaration version. |
| `framework_compat` | semver range | yes | Compatible framework versions. |
| `kill_status` | enum | yes | Lifecycle status; same four-state model. |
| `metadata` | object | yes | Display info; not load-bearing. |
| `auth_styles` | list of enum | yes | One or more of `oauth2`, `api_key`, `webhook_secret`, `mtls`, `custom`. Non-empty. |
| `supported_binding_levels` | list of enum | yes | Subset of `routine_exclusive`, `client_shared`, `identity_bound`. Non-empty. |
| `default_binding_level` | enum | yes | Must be in `supported_binding_levels`. Used when a routine doesn't declare an explicit `binding_level`. |
| `endpoints` | object | yes | Base URL, OAuth URLs, etc. Schema varies by auth style. |
| `egress_patterns` | list of glob/regex | yes | Domain patterns added to routine's egress allowlist when this integration is bound. Non-empty. |
| `scope_vocabulary` | list | yes (empty allowed for integrations without scopes) | Valid scope identifiers and their provider-side OAuth values. |
| `rate_limits` | object | yes | Per-integration token-bucket config; consumed by L0b's scheduler. |
| `revocation` | object | yes | Per-binding-level revocation behavior. Must declare an entry for every `binding_level` in `supported_binding_levels`. |
| `operations` | list | yes | API operations this integration exposes. Non-empty. |
| `webhooks` | list | no | Inbound webhook receivers. Empty if integration is poll-only. |
| `pii_handling` | object | yes | Declared PII risk for redaction defaults. |
| `data_residency` | object | yes | Provider region info; consumed by Contract A's `data_residency` matching. |
| `signature` | object | yes | Ed25519 signature over `signed_fields`. |

### Operation declaration fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Operation identifier; unique within integration. |
| `endpoint` | string | yes | `<METHOD> <path-template>`. Path templating uses `{param}` style. |
| `side_effect` | enum | yes | `read_only` \| `stateful_safe` \| `stateful_destructive`. See classification below. |
| `required_scopes` | list of scope IDs | yes | All must exist in this integration's `scope_vocabulary`. Empty allowed for unscoped APIs. |
| `idempotent` | bool | yes | Whether retry-after-failure is safe. Drives the framework's retry policy. |
| `rate_limit_weight` | int | yes | Cost against the rate-limit token bucket. Default 1. |
| `pii_classes` | list | no | PII categories this operation may return/send. Drives audit redaction defaults. |
| `auth_style` | enum | no | Overrides integration-level `auth_styles` if multiple are supported and this operation requires a specific one. |
| `arguments_schema_ref` | string | no | Path to a JSON Schema describing required arguments. Optional; framework falls back to runtime validation if absent. |

### Side-effect classification

Three classes. Drives severity promotion in `routine.run_terminated_incomplete` (Contract B), informs operator notification urgency, and shapes retry behavior.

| Class | Definition | Examples | Termination behavior |
|---|---|---|---|
| `read_only` | No state change at the provider. GET-style operations, search, list, fetch. | `gmail.list_messages`, `slack.users_list`, `gdrive.files_get` | Failures during termination do not promote severity; runs can safely be replayed. |
| `stateful_safe` | State change but reversible or idempotent. Drafts, labels, soft-deletes, status updates. | `gmail.label_messages`, `slack.set_topic`, `jira.update_issue_status` | Side effects retained; included in `routine.run_terminated_incomplete.integration_calls_completed_during_termination` but do not promote severity. |
| `stateful_destructive` | State change that is irreversible or has external visibility. Sends, hard deletes, payments, posts. | `gmail.send_message`, `slack.chat_postMessage`, `gmail.delete_message`, `stripe.create_charge` | Side effects retained; promote `routine.run_terminated_incomplete` from `warn` to `error`; included with `note` indicating non-rollback. |

Routines can declare per-operation **gate requirements** in Contract C by referencing `stateful_destructive` operations — the routine framework auto-inserts gates for any `stateful_destructive` operation unless the routine declares an explicit `auto_approve_stateful_destructive: true` (rare, audit-logged).

### Authentication style declarations

Five supported styles. Each integration declares which it supports; routines and operators consume per their binding level.

| Style | Description | Typical binding levels | Credential storage shape |
|---|---|---|---|
| `oauth2` | Full OAuth 2.0 / OIDC flow with refresh tokens | `routine_exclusive`, `identity_bound` | `{access_token, refresh_token, expires_at, scopes}` in SecretsProvider |
| `api_key` | Static API key (header or bearer) | `routine_exclusive`, `client_shared` | `{key, header_name | "Authorization"}` |
| `webhook_secret` | HMAC-signed inbound webhooks; no outbound auth required | `routine_exclusive` | `{shared_secret, algorithm: "hmac-sha256"}` |
| `mtls` | Mutual TLS with client certificate | `routine_exclusive`, `client_shared` | `{client_cert, client_key}` references, never inlined |
| `custom` | Escape hatch for non-standard auth (signed headers, custom handshake, etc.) | All | Schema declared per-integration; opaque to framework |

Integration declares supported styles; the OAuth flow / API-key validation / mTLS handshake is implemented by the framework based on declared style. `custom` requires a framework plugin contributed by Agentikey or the client; the registry references the plugin by ID.

### Revocation mapping

Each integration declares revocation behavior per supported binding level. The framework consumes this to execute `on_emergency_kill` actions from Contract C.

Schema per binding-level entry:

```yaml
revocation:
  <binding_level>:
    <on_emergency_kill_action>:
      # Option A: remote revocation
      method: POST | DELETE | GET
      url: "<absolute URL or templated path>"
      body: "<request body template>"
      headers: { ... }
      success_status: [<list of HTTP statuses treated as success>]
      # Option B: local-only revocation
      local_only: true
      operator_message: "<human-readable instruction for manual revocation steps>"
```

Template variables available: `${credential.access_token}`, `${credential.refresh_token}`, `${credential.api_key}`, `${integration.id}`, `${routine.id}`. Templates are rendered by the framework, not the LLM — no injection risk.

If `local_only: true`, framework performs local invalidation and emits `policy.shared_credential_emergency_exposure` or `policy.identity_credential_emergency_exposure` (depending on binding level) with `operator_message` included in the notification payload.

If remote revocation fails (network error, non-success status), framework retries with exponential backoff for up to 5 minutes, then logs a `policy.credential_revocation_failed` event (severity `error`) and falls back to local invalidation + operator notification with manual revocation steps.

### Egress pattern envelopes

The framework's L0b layer maintains a per-routine egress allowlist. When a routine binds to an integration at load time, L0b adds that integration's `egress_patterns` to the allowlist. When a credential is revoked (operator-driven `hard_killed` or framework-driven `emergency_killed`), the patterns are atomically removed.

Pattern syntax:

- Literal domain: `api.github.com`
- Glob wildcard: `*.slack.com` matches any subdomain
- Multiple patterns per integration supported (Microsoft Graph has 6+)
- Patterns are domain-only; path-level filtering is enforced separately via the operation declarations

The framework's HTTP client checks every outbound request against the active allowlist before issuing it. Mismatches are blocked at the L0b layer (not OS-level — that's the deployment platform's job) and emit `policy.egress_blocked` (severity `warn`).

### Scope vocabulary

Defines the valid scope IDs a routine may declare in Contract C's `dependencies.integrations[].scopes`. Each scope entry maps a framework-internal ID (`read`, `send`) to its provider-side OAuth value (`https://www.googleapis.com/auth/gmail.send`).

Why the indirection: provider OAuth values are verbose and change occasionally as providers reshape their permission model. The framework-internal ID stays stable; the registry update pushes new OAuth values if a provider renames its scopes.

Scope grants can carry warnings (`warns_on_grant`) that surface in the OAuth consent UI flow and in the audit event when a routine requests them. Used for scopes that are technically valid but should prompt operator caution (e.g., full mailbox access).

Empty `scope_vocabulary` is valid for integrations that don't use scoped auth (some API-key integrations).

### Rate limit declarations

Per-integration token bucket. Consumed by L0b's scheduler to space requests below provider limits and avoid HTTP 429 storms.

```yaml
rate_limits:
  requests_per_second: 5         # bucket refill rate
  requests_per_minute: 250       # secondary cap; tighter of the two applies
  burst_capacity: 10             # optional; defaults to requests_per_second × 2
  backoff_strategy: "exponential_with_jitter"   # exponential_with_jitter | linear | constant
  retry_after_header: "Retry-After"   # provider's header name for retry timing
  max_retries: 5
  per_operation_overrides:        # optional; per-operation tighter limits
    - operation_id: "send_message"
      requests_per_minute: 50
```

The framework's HTTP client honors provider rate-limit headers when present (`Retry-After`, `X-RateLimit-Remaining`, etc.) and uses the declared `rate_limits` as the lower bound. The `operations[].rate_limit_weight` field multiplies a single operation's cost against the bucket.

### Webhook receiver declarations

For push-based integrations (Slack Events, GitHub webhooks, Google Pub/Sub push), declare receivers that mount under the framework's HTTP server at `receiver_path`.

```yaml
webhooks:
  - id: "message_received"
    receiver_path: "/webhooks/gmail/messages"
    auth_style: "google_pubsub_push"          # provider-specific verification handler
    secret_ref: "secret:gmail_pubsub_token"   # reference to SecretsProvider key
    verification:
      method: "google_pubsub_signature"       # | "hmac-sha256" | "shared_secret" | "jwt"
      algorithm: "sha256"                     # optional, for hmac methods
      header: "X-Goog-Channel-Token"          # optional, for shared_secret methods
    routes_to_event: "integration.gmail.message_received"
```

Webhook receiver is only mounted if the framework's `network_posture.mode` is not `outbound_only`. For Mode 1 (Local) and Mode 2 (VPS), the framework requires a publicly-reachable URL for the receiver (configurable per-deployment); Mode 3 (Managed by Omar) inherits from the managed-infra config.

Inbound webhook payloads are signature-verified against `secret_ref` before any routing happens. Verification failures emit `policy.webhook_signature_failed` (severity `critical`).

Successful verification routes the payload to an internal event matching `routes_to_event`, which routines can subscribe to via their `automation.events[]` (Contract C). The payload is sanitized through the redaction pipeline before reaching the routine.

### Validation rules

Run at framework startup and on every integration declaration update from the channel:

1. **Signature verification first.** Registry signature and per-integration signatures verified before any parsing. Failures rejected and `routine_source.signature_failed` emitted (severity `critical`).
2. **`framework_compat` checked.** Integration declarations with incompatible framework version ranges are skipped with `integration.load_skipped` audit event.
3. **`auth_styles` non-empty.** Empty fails load.
4. **`supported_binding_levels` non-empty** and `default_binding_level` ∈ `supported_binding_levels`.
5. **`revocation` declares behavior for every supported binding level.** Missing binding-level entry in revocation = critical failure.
6. **`operations[].required_scopes`** all exist in `scope_vocabulary` for this integration.
7. **`operations[].id`** unique within integration.
8. **`egress_patterns`** non-empty.
9. **`webhooks[].secret_ref`** resolves at framework startup (SecretsProvider can produce a value; otherwise the receiver is not mounted and a warning is logged).
10. **Cross-contract reconciliation (Contract C ↔ D):**
    - Every routine's `dependencies.integrations[].id` must exist in the active registry. Missing = routine refuses to load.
    - Routine's declared `binding_level` for an integration must be in the integration's `supported_binding_levels`. Mismatch = routine refuses to load.
    - Routine's declared `scopes` for an integration must all exist in the integration's `scope_vocabulary`. Mismatch = routine refuses to load.

### Distribution

Two sources of integration declarations:

**Built-in integrations** — bundled with the framework Docker image at release time. Covers the common surface (Gmail, GDrive, Slack, Notion, GitHub, Jira, Atlassian, Microsoft 365, Telegram, LinkedIn, etc.). Updated when the framework's minor version updates. No separate channel pull; integrations live alongside the framework binary.

**Custom client integrations** — for internal APIs and client-specific systems. Distributed via the same private channel as routines, or via a separate `IntegrationSource` instance if the client wants a dedicated channel. Signed and versioned identically. ID namespace must not collide with built-in IDs (e.g., a client cannot redefine `gmail`; they must use `client.internal_gmail_wrapper`).

**Custom integration authoring:** clients (or Omar on behalf of clients) author integration YAML manually or via `ota-cli scaffold-integration <id>`. The CLI's `validate` command checks integration declarations against the bundled JSON Schema. Signing is via `ota-cli sign-integration <bundle>`.

**Integration lifecycle:** integrations have the same four-state `kill_status` model as routines, the same kill-list polling, and the same revocation semantics. An `emergency_killed` integration triggers `emergency_killed` cascade for every routine that depends on it (which in turn triggers per-routine credential revocation).

**Conflict resolution:** if a built-in and a custom integration declare the same ID (which validation should prevent, but defense-in-depth), the built-in wins and a `policy.violation` is emitted.

---

## Contract E — Deployment Configuration

Defines the static wiring for a single OTA deployment: which seam implementations are selected, which providers are configured, where routines and integrations are fetched from, how notifications route, what budgets apply, what features are enabled. Loaded once at framework startup; some fields hot-reload, most require restart.

This is the **only** contract authored by the operator (or Omar on the operator's behalf for Mode 3 Managed). Contracts A–D are authored by routine/integration sources; Contract E says "in this deployment, use them like this."

Single file by default: `deployment.yaml`. May `include:` other files for organization (rare in practice).

### Example

```yaml
deployment:
  schema_version: "1.0"
  id: "ota-omar-prod"
  mode: managed                       # local | vps | managed
  edition: core                       # core | enterprise
  framework_version: "1.4.2"
  region: "us"                        # ISO region; used for data_residency matching in Contract A
  tenant_id: null                     # null for Core; "<client-id>" for Enterprise multi-tenant

operator:
  bootstrap_identity:
    type: local                       # local | oidc_social | oidc_enterprise | saml
    principal_id: "op:omar"
    display_name: "Omar"
    email: "omar@agentikey.com"
  # For OIDC/SAML, additional config under `identity:` block in providers

providers:
  identity:
    type: local                       # local | oidc_social | oidc_enterprise | saml
    # type-specific fields nested here

  secrets:
    type: encrypted_file              # encrypted_file | env | vault | aws_sm | azure_kv | gcp_sm
    master_key_source: "keychain://ota/master-key"
    # alternative: master_key_env: "OTA_MASTER_KEY"
    # vault-specific: vault_url, vault_namespace, vault_auth_method

  audit:
    sink: jsonl_local                 # jsonl_local | splunk_hec | datadog | s3_immutable | syslog | kafka
    retention_days: 90
    rotation: "daily"
    # sink-specific: hec_url, hec_token_ref for splunk_hec, etc.

  observability:
    sink: otlp                        # otlp | local_otel | none
    endpoint: "http://otel-collector:4317"
    sample_rate: 1.0
    # OTel resource attributes auto-populated from deployment.id, mode, edition, version

  llm:
    primary:
      provider: anthropic_direct      # anthropic_direct | gemini_direct | ollama_local | custom_gateway | bedrock | azure_openai | vertex
      api_key_ref: "secret:anthropic_api_key"
      default_model: "claude-sonnet-4-6"
      region: "us"
    fallback:                         # optional; used when primary is rate-limited or down
      provider: anthropic_direct
      api_key_ref: "secret:anthropic_api_key_backup"
      default_model: "claude-haiku-4-5"

  routine_source:
    type: agentikey_private_channel   # agentikey_private_channel | agentikey_mirrored_channel | agentikey_approval_gate | pinned_version_source | local_directory
    channel_url: "https://channel.agentikey.com/v1"
    refresh_token_ref: "secret:agentikey_refresh_token"
    public_key_pem_ref: "config:agentikey_pubkey_2026"
    poll_interval: "1h"
    kill_list_poll_interval: "60s"

  integration_registry:
    type: agentikey_private_channel
    channel_url: "https://integrations.agentikey.com/v1"
    refresh_token_ref: "secret:agentikey_integrations_refresh_token"
    public_key_pem_ref: "config:agentikey_pubkey_2026"
    poll_interval: "1h"
    kill_list_poll_interval: "60s"

local_inference:
  mode: disabled                      # disabled | external_ollama | embedded_sidecar
  # When mode: external_ollama
  ollama:
    url: "http://localhost:11434"
    model: "phi3:mini"
    timeout: "10s"
  # When mode: embedded_sidecar
  sidecar:
    model_id: "phi3-mini-q4-k-m"
    auto_pull_on_first_start: true
    gpu_passthrough: false
    max_tokens_per_request: 512

network:
  egress:
    mode: allowlist                   # open | allowlist | none
    additional_allowlist: []          # union with integration registry's egress_patterns
  proxy:
    http: null
    https: null
    no_proxy: ["localhost", "127.0.0.1"]
  tls:
    ca_bundle_path: null
    client_cert_path: null
    client_key_ref: null
  user_agent: "OneTrueAgent-Core/1.4.2"
  webhook_receiver:                   # only used if any integration declares webhooks
    bind_address: "0.0.0.0"
    port: 8443
    tls_cert_path: "/etc/ota/webhook.crt"
    tls_key_ref: "secret:webhook_tls_key"
    public_url: "https://hooks.example.com/ota"

notifications:
  # references the Operator notification routing sub-spec above; full block lives here
  schema_version: "1.0"
  channels:
    primary_slack:
      type: slack_dm
      user: "U0123456"
      token_ref: "secret:slack_user_token"
    primary_email:
      type: email
      address: "omar@agentikey.com"
  routing:
    info:
      delivery: [dashboard]
    warn:
      delivery: [dashboard]
      digest: { channel: primary_email, cadence: "weekly" }
    error:
      delivery: [primary_slack, dashboard]
    critical:
      delivery: [primary_slack, dashboard]
      acknowledgement:
        required: true
        timeout: "5m"
        escalation_chain: [primary_slack, primary_email]
  rate_limiting:
    per_routine_per_event_type: { window: "10m", max_notifications: 5, on_exceeded: "coalesce_into_summary" }
    storm_detection: { window: "5m", threshold_events_same_type: 20, action: "suppress_individual_emit_single_summary" }

resource_limits:
  global_budget:
    max_usd_per_day: 100.00
    max_input_tokens_per_day: 10_000_000
    on_exceeded: "pause_non_critical_routines"
  per_routine_budget_default:
    max_usd_per_run: 1.00
    max_input_tokens_per_run: 80_000

feature_flags:
  enable_local_inference: false       # must align with local_inference.mode != disabled
  enable_pii_redaction: true
  enable_drift_monitoring: true       # conductor router drift defense
  enable_crash_loop_detection: true
```

### Deployment-level fields

| Field | Type | Required | Hot-reload | Notes |
|---|---|---|---|---|
| `deployment.schema_version` | semver | yes | no | Contract E version. |
| `deployment.id` | string | yes | no | Stable identifier; appears in audit `deployment.id`. |
| `deployment.mode` | enum | yes | no | `local` \| `vps` \| `managed`. Affects defaults for network posture, webhook receiver, etc. |
| `deployment.edition` | enum | yes | no | `core` \| `enterprise`. Gates which seam implementations are available. |
| `deployment.framework_version` | semver | yes | no | Must match the running framework binary; mismatch fails startup. |
| `deployment.region` | string | yes | no | ISO region code; used by Contract A `data_residency` matching. |
| `deployment.tenant_id` | string \| null | yes | no | Null in Core; required in Enterprise multi-tenant. |

### Operator bootstrap

The `operator` block establishes the initial human principal who owns the deployment. Required because: routines emit audit events that need a principal; gates need a default approver; the framework needs to know who to notify.

For `bootstrap_identity.type: local`, the operator principal is hard-coded in this file. For OIDC/SAML, the bootstrap identity is the seed used to mint the framework's initial session; subsequent logins go through the IdP.

### Provider selection

The `providers` block selects one implementation per seam. Each provider type has its own nested config block; framework validates the union at startup.

| Seam | Available types (Core) | Available types (Enterprise adds) |
|---|---|---|
| `identity` | `local`, `oidc_social` | `oidc_enterprise`, `saml` |
| `secrets` | `encrypted_file`, `env` | `vault`, `aws_sm`, `azure_kv`, `gcp_sm` |
| `audit` | `jsonl_local` | `splunk_hec`, `datadog`, `s3_immutable`, `syslog`, `kafka` |
| `observability` | `local_otel`, `none` | `otlp` (with private collector) |
| `llm.primary` | `anthropic_direct`, `gemini_direct`, `ollama_local` | `custom_gateway`, `bedrock`, `azure_openai`, `vertex` |
| `routine_source` | `agentikey_private_channel`, `local_directory` | `agentikey_mirrored_channel`, `agentikey_approval_gate`, `pinned_version_source` |
| `integration_registry` | `agentikey_private_channel`, `local_directory` | same Enterprise extensions as routine_source |

Validation: selecting an Enterprise-only type when `edition: core` fails startup with a clear error.

### Local inference

The `local_inference` block governs how (or whether) the framework uses a local SLM for the conductor's classification fallback and for routines that declare `cost_tier: local` in Contract A.

| Mode | Behavior | Hardware | Use case |
|---|---|---|---|
| `disabled` (default) | No local inference. Conductor falls back to cloud LLM. Routines that declare `cost_tier: local` warn at load and fall back to cloud unless `forbidden_without: [local_inference]`. | Any | Most clients. |
| `external_ollama` | Framework connects to an Ollama instance at `ollama.url` using `ollama.model`. The framework expects Ollama to be running and the model to be pulled — does not manage Ollama's lifecycle. | Whatever Ollama is running on (typically Apple Silicon, NVIDIA GPU, or capable CPU) | Privacy-conscious clients who already use Ollama, or who want full control over the local model choice. |
| `embedded_sidecar` | Framework's docker-compose includes an `ota-local-llm` sidecar container running llama.cpp server with `sidecar.model_id`. Auto-pulled on first start to a persistent volume. Framework manages the sidecar's lifecycle. | CPU (5-15 tokens/sec for Phi-3-mini) or GPU if `gpu_passthrough: true` | Managed deployments (Mode 3) where Omar controls infra, or air-gapped deployments where Ollama isn't available. |

The `local_inference` capability flag (Contract A) maps to `external_ollama` or `embedded_sidecar`. Routines that declare `required: [local_inference]` refuse to load if `mode: disabled`.

**Model selection** (for `embedded_sidecar`): canonical list maintained by the framework. Current first-class options as of Contract E 1.0:

| `model_id` | Source | Quantization | Size | License | Notes |
|---|---|---|---|---|---|
| `phi3-mini-q4-k-m` | Microsoft Phi-3-mini | Q4_K_M | ~2.3GB | MIT | Default; best balance of capability and footprint. |
| `qwen2.5-1.5b-q4` | Alibaba Qwen 2.5 | Q4 | ~900MB | Apache 2.0 | Smaller; weaker reasoning. |
| `phi3-mini-q8` | Microsoft Phi-3-mini | Q8 | ~4.0GB | MIT | Higher fidelity, slower CPU inference. |

Gemma and Llama are not bundled by default due to redistribution license terms; operators can use them via `external_ollama` mode.

**Boundary discipline:** local inference is for short classification tasks (router fallback, simple extraction). Generation tasks should go to cloud LLMs. The framework enforces a hard `max_tokens_per_request` cap on local providers (`sidecar.max_tokens_per_request`, default 512) and refuses routine steps that request more.

### Network posture

Maps directly to the Network Posture concerns documented earlier. Cross-references:

- `network.egress.additional_allowlist` is unioned with each integration's `egress_patterns` (Contract D) to compute the routine's effective allowlist at integration-bind time.
- `network.user_agent` is the canonical UA per the standardized `OneTrueAgent-{Core|Enterprise}/{version}` format; framework appends `X-OTA-Trace-Id`, `X-OTA-Routine-Id`, `X-OTA-Deployment-Mode`, `X-OTA-Edition` headers automatically per request.
- `network.webhook_receiver` block is only consumed if any installed integration declares `webhooks[]` in Contract D.

### Notifications

The `notifications` block contains the full schema documented in the Operator notification routing sub-spec above. Operator authors this once per deployment; routine framework consumes it on every event emit.

Hot-reloadable: `notifications.routing`, `notifications.rate_limiting`. Not hot-reloadable: `notifications.channels` (requires restart).

### Resource limits

Global and default per-routine budgets. Routine-declared budgets (Contract A `llm_requirements.budget`) override per-routine defaults but cannot exceed the global budget.

`on_exceeded` strategies:

- `pause_non_critical_routines` — routines below a configurable priority threshold stop firing until the next budget window.
- `pause_all_routines` — full halt; safety mode.
- `notify_only` — emit `policy.budget_exceeded` critical events but keep running.

### Feature flags

Deployment-time toggles for features that should be off in some deployments. Distinct from per-routine knobs (those are in Contract C). Each flag has a documented default.

Validation: `feature_flags.enable_local_inference` must agree with `local_inference.mode != disabled`. Mismatch fails startup.

### Bootstrap secret handling

Contract E references secrets via `secret:<key>` and `config:<key>` patterns, but the SecretsProvider itself needs auth to start. Chicken-and-egg resolved by a small set of bootstrap secrets:

- **Master key for `encrypted_file` secrets**: source declared in `providers.secrets.master_key_source` (`keychain://`, `env://`, or `file://`). Framework reads at startup before SecretsProvider is fully initialized.
- **Vault token / cloud SDK creds for managed secrets backends**: standard provider chains (env vars, IAM instance profiles, workload identity). No deployment-config inlining.

After bootstrap, all other `secret:<key>` references resolve through the configured SecretsProvider.

`config:<key>` references resolve from a separate non-secret config file or env var — used for things like public keys, allowlists, non-sensitive endpoints where putting them in Contract E directly would bloat the file.

### Hot reload semantics

| Field family | Reload behavior |
|---|---|
| `deployment.*` (metadata) | Restart required |
| `providers.*` (seam selection) | Restart required |
| `local_inference.*` | Restart required (sidecar lifecycle) |
| `network.egress.additional_allowlist` | Hot-reload |
| `network.proxy.*` | Restart required |
| `notifications.routing`, `notifications.rate_limiting` | Hot-reload |
| `notifications.channels` | Restart required |
| `resource_limits.*` | Hot-reload |
| `feature_flags.*` | Mixed; per-flag documented |

Hot-reload trigger: framework watches the config file for changes and reloads modified sections atomically. Each reload emits `system.config_reloaded` (severity `info`) with the diff.

### Validation rules

1. **`schema_version` must be supported.** Mismatch with framework's bundled JSON Schema = startup fails.
2. **`framework_version` must match the running binary.** Prevents config-drift bugs after upgrades.
3. **`deployment.edition` gates provider type selection.** Enterprise-only types fail validation in Core.
4. **`tenant_id` required if `edition: enterprise` AND any installed routine declares Enterprise multi-tenancy.**
5. **`local_inference.mode` must be consistent** with `feature_flags.enable_local_inference`. Mismatch = startup fails.
6. **All `secret:<key>` references must resolve** at startup. Missing secrets = startup fails with a list of missing keys.
7. **All `config:<key>` references must resolve.** Missing = startup fails.
8. **`webhook_receiver` block required** if any installed integration declares webhooks; ignored otherwise.
9. **`network.user_agent` must match the framework version.** Operators cannot spoof to a different version.
10. **`notifications.routing` must cover all four severities** (`info`, `warn`, `error`, `critical`).

### Distribution

Contract E is authored once per deployment, not distributed via a channel. Lives in the deployment's filesystem at a canonical path (typically `/etc/ota/deployment.yaml`). Mode 3 (Managed) deployments have Omar author this on the client's behalf. Mode 1 and Mode 2 deployments require the operator (or whoever sets it up) to author it, ideally via `ota-cli init-deployment` which scaffolds a deployment.yaml with sensible defaults.

Version controlled separately from routine bundles. Operators can put their deployment.yaml under their own version control if desired (encouraged for audit).

---

## Remaining open items

Surfaced during draft review; not yet schema-locked.

1. **Dashboard / operator UI contract.** The notification payload references dashboard URLs and action buttons. The dashboard itself is referenced but not specified — what does it render, what mutations does it accept, what auth does it require. Separate work item beyond the five contracts.
2. **`custom` auth style plugin model.** Contract D allows `custom` auth style as an escape hatch but references "a framework plugin contributed by Agentikey or the client." The plugin interface for custom auth handlers is not specified — would need its own mini-contract if a client requests a non-standard integration with non-OAuth, non-API-key, non-mTLS auth.

Addressed in this revision (folded in):

- ✅ Non-OAuth credential isolation — generalized via `binding_level` (routine_exclusive / client_shared / identity_bound).
- ✅ Microsoft Graph / Atlassian multi-scope tokens — addressed via virtual credential scoping in Contract C.
- ✅ Operator notification routing — full sub-spec added (urgency matrix, rate limiting, payload shape); deployment-time config now lives in Contract E.
- ✅ Contract D — Integration Registry — full draft covering registry manifest, integration declarations, operation declarations, side-effect classification, auth styles, revocation mapping, egress patterns, scope vocabulary, rate limits, webhook receivers, validation rules, distribution model.
- ✅ Identity Provider vs SecretsProvider separation — locked in as cross-contract invariant #10; only link is `identity_bound` binding level.
- ✅ Integration-to-routine cascade semantics — locked in as cross-contract invariant #9; cascade respects routine's `on_emergency_kill`, AND L0b applies a global egress block as secondary hard-kill defense.
- ✅ Audit ↔ Observability linkage — locked in as cross-contract invariant #11; `trace_id` is the join key with dashboard click-through.
- ✅ Acknowledgement persistence — stored in framework's L0 SQLite `notifications` table; survives restarts; retention matches audit.
- ✅ Zombie artifact prevention — `stale_artifact_ttl` (default `4h`, per-routine override in Contract C `artifacts.stale_artifact_ttl`); framework auto-expires unclaimed artifacts and emits `artifact.auto_expired`.
- ✅ Contract E — Deployment Configuration — full draft covering deployment metadata, operator bootstrap, provider selection, local inference modes (disabled / external_ollama / embedded_sidecar), network posture, notifications, resource limits, feature flags, bootstrap secret handling, hot-reload semantics, validation rules, distribution.
- ✅ Webhook receiver port/TLS/proxy configuration — now part of Contract E `network.webhook_receiver`.
