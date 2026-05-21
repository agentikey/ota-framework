# Phase 4 carry-forward notes

Surfaced during Phase 4 (Adapters + Routine + Dashboard) implementation.
Captured here so Phase 5 (deployment) and later phases don't rediscover
them as problems. Each item is tagged with the phase that should pick it
up.

## Open items deferred to specific phases

### Phase 4 — follow-up (real-OAuth roll-in)

- **Slack + Gmail adapters were tested with HTTP mocks** (`pytest-httpx`)
  rather than against real OAuth-issued tokens. The verb shapes, error
  taxonomy translation, and pagination handling are exercised end-to-end;
  only token issuance + Socket Mode WebSocket transport remain to validate
  against the live services. Plan a one-off manual session against a
  burner Slack workspace + Gmail account before first-client delivery.

- **Slack Socket Mode WebSocket transport is a strategy parameter.**
  [`SocketModeListener`](../ota_connect/adapters/slack_socket/adapter.py)
  accepts an async iterator of payloads rather than opening the WebSocket
  itself. Phase 5 deployment code (or a thin wrapper module in 4A.3
  follow-up) wires `aiohttp` / `websockets` to call
  `apps.connections.open` and stream events from the issued URL.

- **`_build_mime` in the Gmail adapter does not yet load attachment
  bytes.** `_attachment_bytes(a)` returns `b""` as a placeholder. Phase 5
  needs the `FileRef` resolver (local / gdrive / etc.) wired through
  before attachments work end-to-end. Until then, routines should not
  pass `attachments=...` to `email.send_email`.

- **LLM Reader / Drafter inside `email_triage` are placeholders.**
  [run.py](../ota_routines/email_triage/run.py) ships keyword-based
  classification + format-string drafting. The prompts in
  [`prompts/classifier.md`](../ota_routines/email_triage/prompts/classifier.md)
  and [`prompts/drafter.md`](../ota_routines/email_triage/prompts/drafter.md)
  are ready; wire `runtime.llm.complete(...)` into `_classify` / `_draft`
  once a real `LLMProvider` is bound (Phase 4A follow-up, gated on
  `AnthropicProvider.estimate_cost` being added).

### Phase 4C — dashboard polish

- **WebSocket approval stream is poll-based.**
  [`/api/v1/approvals/stream`](../ota_dashboard_api/routes/approval_queue.py)
  loops every 2s and pushes a `{event: approval.new, id}` payload when a
  pending gate appears. When the gate manager moves off SQLite (Phase 5's
  Postgres swap), switch this to `LISTEN/NOTIFY`. Until then the sub-5s
  latency target is met by polling.

- **Knob editor stores edits in-memory on `DashboardState`.** Phase 5
  wires this to the routine engine's real knob store (which today is the
  per-routine SQLite shard). The HTTP shape (`POST /api/v1/routines/{id}/knobs`)
  is the stable seam; only the implementation moves.

- **Frontend OpenAPI codegen is not enforced in pre-commit yet.** Run
  `python scripts/gen_openapi.py` manually after route changes. Phase 5
  will activate the dormant `gen-api-sync` hook in
  [`.pre-commit-config.yaml`](../.pre-commit-config.yaml) and add a CI
  guard that re-runs the codegen and fails on diff.

- **No `pnpm install` was run in the dev environment.** `package.json`
  declares the deps; lockfile generation + the first build land when the
  operator runs `pnpm install && pnpm build` in `ota_dashboard_web/`.
  The frontend CI workflow ([`frontend.yml`](../.github/workflows/frontend.yml))
  will run `pnpm install --frozen-lockfile` on PR; commit the resulting
  `pnpm-lock.yaml` once locally generated.

### Phase 5 — deployment / persistence

- **`GateStore` SQLite schema is per-routine-instance, not central.**
  When the dashboard surfaces gates across all routines, query the
  database that the routine engine bound. Phase 5 should formalize a
  single gates database under `/var/lib/ota/state/gates.db` instead of
  per-routine. The migration is a copy-into-one-table; the
  `GateStore` API doesn't change.

- **`InboundEmailLoop` lifecycle still unmanaged.** Same as the Phase 3
  carry-forward — the systemd-managed event loop needs to start /
  stop the loop.

- **`CriticalBanner` is in-memory only.** Architecture says the banner
  persists across restart; Phase 5 wires it to a single-row SQLite
  table (`framework_banner`).

## Design notes worth knowing

### OAuth ([ota_core/oauth/](../ota_core/oauth/))

- **Provider-agnostic Authorization Code only in v0.1.** PKCE, device
  flow, JWT bearer — all deferred until a provider needs them. The
  `OAuthClient` constructor takes all provider endpoints + credentials
  explicitly; per-provider wrappers (`SlackOAuthClient`,
  `GmailOAuthClient`) are not built yet because there's only one
  Authorization-Code shape to support.

- **Tokens stored as `Credential.secret` JSON** with `style="oauth2"`.
  `TokenRecord.from_dict` parses; `TokenRecord.as_dict` serializes. The
  `OAuthTokenStore` is a thin wrapper around `SecretsProvider`.

- **`access_token()` auto-refreshes within a 60s grace window.** Tuned
  via `OAuthClient(refresh_grace_seconds=...)`.

### HITL gates ([ota_core/policy/gates.py](../ota_core/policy/gates.py))

- **One SQLite table per process** (`gates`). Multiple routines share
  it; the index `idx_gates_similarity` covers
  `(routine_id, gate_id, similarity_key, status)` so the
  `approve_and_remember` lookup is O(log n).

- **`approve_and_remember` auto-approval happens at `propose_for_review`
  time.** If a similarity match is found, the gate is created with
  `status="auto_approved"` and the audit event
  `gate.auto_approved_by_similarity` fires — the routine never blocks.

- **`record_decision` rejects double-decide** via
  `GateAlreadyDecidedError`. Dashboards / Slack callbacks must handle
  this gracefully.

### Audit reader ([ota_core/audit/reader.py](../ota_core/audit/reader.py))

- **FileAuditReader skips files outside `[start.month, end.month]`** for
  the obvious O(files-touched) speed-up. Within a file, lines are
  scanned in order; the writer is the authority on temporal ordering.

- **Malformed lines are silently skipped.** A partial line during
  rotation should not crash a query. Writers are the authority on
  validity.

### Slack adapter ([ota_connect/adapters/slack_socket/](../ota_connect/adapters/slack_socket/))

- **Raw httpx, no `slack_sdk`.** The Web API endpoints we hit
  (`chat.postMessage`, `chat.update`, `chat.delete`,
  `conversations.history`, `conversations.replies`) are stable; the SDK
  buys little beyond convenience. Socket Mode brings back complexity;
  the strategy parameter (`message_stream`) keeps that complexity
  outside this module.

- **Error code mapping is explicit** in `_check_slack_response`:
  `ratelimited` → `RateLimited`, `channel_not_found` /
  `not_in_channel` / `is_archived` → `RecipientUnreachable`, etc. New
  Slack error codes encountered in production go in this map.

### Gmail adapter ([ota_connect/adapters/gmail_oauth/](../ota_connect/adapters/gmail_oauth/))

- **`history.list` based inbound polling.** Adapter remembers the last
  `historyId` per process; tick `tick_inbound(routine_id=...)` to drain
  new messages. v0.1 stores history id in process memory; Phase 5
  persists it via `GmailAdapterConfig.inbound_history_id_path`.

- **RFC 5322 MIME built via `email.message.EmailMessage`.** This is
  enough for v0.1 (no inline attachments, no complex multipart). Phase 4
  follow-up adds attachment-byte loading.

### email_triage state ([ota_routines/email_triage/state.py](../ota_routines/email_triage/state.py))

- **Four tables**: `email_triage_processed`, `email_triage_template_trust`,
  `email_triage_edits`, `email_triage_decisions`. All prefixed so
  multiple instances of the routine can co-exist in the same database.

- **`record_unedited_approval` promotes the template** only if
  `opt_in_auto_send` is true AND `consecutive_unedited >= threshold`.
  Editing demotes immediately and stamps `demoted_at`.

### Dashboard ([ota_dashboard_api/](../ota_dashboard_api/))

- **`DashboardState` is the single seam injection point.** Every route
  resolves it via `Depends(dashboard_state)` — no globals, no module-
  level singletons. Tests construct one with in-memory implementations
  and pass it to `create_app`.

- **OpenAPI export is one command:**
  `python scripts/gen_openapi.py` writes
  `ota_dashboard_web/openapi.json`. Frontend codegen reads from there.

## Things that got fixed during Phase 4

For future-me searching for resolved items:

- The `RoutineSource` discovery now passes for both `hello` and
  `email_triage` simultaneously (Phase 2 carry-forward → Phase 4B.4).
- Audit reader API (Phase 2 carry-forward → 4C.6).
- Reverse-DNS regex limitation: routine IDs cannot contain underscores
  (resolved by renaming `ota.email_triage` → `ota.email-triage`).
- `Bindings.capabilities` key regex tolerates dotted identifiers but
  not dashes; dashes only allowed in `<adapter_id>` values, not keys.
