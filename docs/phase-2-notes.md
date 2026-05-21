# Phase 2 carry-forward notes

Surfaced during Phase 2 (Framework runtime + Seams) implementation. Captured
here so Phase 3 (capability dispatch) and later phases don't rediscover them
as problems. Each item is tagged with the phase that should pick it up.

## Open items deferred to specific phases

### Phase 3 — capability dispatch

- ~~**Generated `verbs.py` need to flow through L0b when a routine run is active.**~~ **RESOLVED in Phase 3.5.** The dispatch layer ([ota_connect/binding/dispatch.py](../ota_connect/binding/dispatch.py)) calls `L0bEnforcer.enforce_integration(integration_id)` and `enforce_scopes(integration_id, required_scopes)` before every adapter invocation. The integration_id comes from the resolved adapter's manifest (`AdapterBundle.integration_id`).

- ~~**`dispatch()` placeholders still raise `NotImplementedError`**~~ **RESOLVED in Phase 3.5.** [ota_connect/messaging/dispatch.py](../ota_connect/messaging/dispatch.py) and [ota_connect/email/dispatch.py](../ota_connect/email/dispatch.py) now forward to `dispatch_capability("messaging", ...)` / `dispatch_capability("email", ...)`.

- ~~**Cross-contract validation (Contract C ↔ D)** at routine-load is still deferred.~~ **RESOLVED in Phase 3.4.** [ota_connect/binding/validator.py](../ota_connect/binding/validator.py) checks: integration exists in registry, declared binding_level is supported, and every declared scope is in the integration's vocabulary. Returned as `ValidationReport` (aggregated issues) or via `assert_routine_install` (raises on any failure). The routine bundle loader can call this after Pydantic-level Contract C validation.

### Phase 4A — adapters & LLM enforcement

- **Cost estimation hook still missing on `LLMProvider`.** Carried forward from Phase 1 notes — re-confirmed in Phase 2. `L0bEnforcer.reserve_llm_budget(usd=...)` accepts an explicit USD estimate, but no provider currently computes one. When the first real LLM call goes through in Phase 4A (e.g. `email_triage` invoking Sonnet), add `estimate_cost(request) -> Decimal` to the `LLMProvider` protocol with per-model pricing tables in `AnthropicProvider`. Until then, callers either pass a manual estimate or rely on post-hoc `record_llm_usage()` updates.

- **`AsyncAnthropic.close()` async assumption** (carry-over from Phase 1) still unverified. Will surface the first time a routine actually instantiates `AnthropicProvider` and calls `aclose()`.

### Phase 4B — routine HITL

- **Gate primitives are not yet built.** Contract C declares `gates[]` and the routine bundle loader (Phase 2B.5) successfully validates them. But there is no Phase 2 module that actually enforces a gate — that ships with Phase 4B.3 (HITL gate primitives), which builds on the `L0bEnforcer.routine_run()` audit pipeline added in 2A.5.

### Phase 4C — dashboard

- **Audit / observability sinks have no read-side API yet.** `FileAuditSink` and `FileObservabilitySink` are write-only — they emit JSONL but provide no query/scan/filter API. The dashboard backend (Phase 4C.6, audit log viewer) needs a reader that streams the right monthly file, parses each line, and filters. Decide then whether to add a `read_events(...)` method to the seam or keep it a separate concern with its own module.

### Phase 5 — deployment

- **`SecretsProvider` does not yet rotate Fernet keys.** `EncryptedFileSecretsProvider` accepts a key at construction and uses it for all I/O. Production needs key rotation (new key, re-encrypt all stored credentials, retire old key). Wire this when the Mode 2 install script (Phase 5.5) needs to support `ota secrets rotate-key`.

## Design notes worth knowing

### Trace IDs ([ota_core/trace/](../ota_core/trace/))

- **`trace_id` is 32-hex** (W3C trace context format); `span_id` is 16-hex. Generated via `secrets.token_hex(16)` / `token_hex(8)`. Matches the Contract B regex `^[a-f0-9]{32}$` so `AuditEvent.trace_id` accepts it directly.
- **`bind_trace()` is a sync `contextmanager`** but propagates correctly across `asyncio.gather` because we use `ContextVar` — each spawned task copies the current context. The test `test_trace_id_isolated_per_async_task` proves three concurrent tasks each see their own trace.
- **`ensure_trace_id()` is the "current or new" helper** — useful from audit emitters that want to record a trace ID regardless of whether the caller set one.

### Audit sink ([ota_core/audit/](../ota_core/audit/))

- **JSONL with monthly rotation** (`<dir>/2026-05.jsonl`) per build plan §4.4. Rotation key is the *event's* UTC timestamp, not wall-clock, so back-dated emissions still file correctly.
- **`event_id` is UUIDv7** (hand-rolled in `ids.py` — Python 3.12 stdlib doesn't ship a v7 generator). Time-sortable, monotonic within a millisecond. Matches Contract B's "ULID or UUIDv7" requirement.
- **`emit()` raises `AuditSinkError` on disk failure.** L0b's callers should let it propagate — failing to record an audit event is a load-bearing condition for the warranty pitch.
- **`NullAuditSink` records to `events: list[AuditEvent]`** for tests. Same `emit()` shape, no I/O.

### Observability ([ota_core/observability/](../ota_core/observability/))

- **Two record kinds:** `metric` (counter / gauge / histogram) and `span`. Both emit one JSON line. The schema is OTel-shaped but not OTel-protocol — the v0.2 collector integration translates.
- **`span()` is a `contextmanager`** that auto-emits on exit, capturing duration, status (`ok` / `error`), attributes, and nested events. Parent span_id is read from the trace context.
- **`StdoutObservabilitySink` shares the writer pattern with `FileObservabilitySink`** but writes to `sys.stdout`. Useful for dev. The patched-stdout test in `test_sink.py` is a little ugly — it rebinds the writer to a `StringIO` because `monkeypatch.setattr("sys.stdout", ...)` doesn't reach the writer that already captured the original `sys.stdout`. If a cleaner test seam matters, refactor the sink to read `sys.stdout` lazily.

### Identity ([ota_core/identity/](../ota_core/identity/))

- **`people.md` format is YAML frontmatter + body.** The whole roster lives in `frontmatter.people`. Body is freeform notes. Build-plan §4.4 calls the file `client_config/people.md`; this seam doesn't know that — it just takes a `Path`.
- **`IdentityRef` parsing** has three prefixes (`handle:`, `mailto:`, `raw:`). The `raw:<adapter>:<id>` escape hatch is intentionally narrow — it requires the bound adapter to match and is meant for one-off operator use, not routine code.
- **Resolution errors are explicit subclasses** so callers can distinguish "I don't know this person" from "I know them but not on this adapter" from "you tried to use a raw ref on the wrong adapter."

### Secrets ([ota_core/secrets/](../ota_core/secrets/))

- **Fernet (AES-128-CBC + HMAC) for at-rest encryption.** Single key, generated via `EncryptedFileSecretsProvider.generate_key()` (32 random bytes, base64-urlsafe). Production deployments store the key in env or a key file *outside* the data directory. Sops / age integration is deferred until a paying client asks.
- **Virtual credential scoping** is enforced in `fetch()`: if `required_scopes` is non-empty, the returned `Credential` has its `granted_scopes` narrowed to exactly the requested set. If a required scope wasn't granted, `InsufficientScopesError` fires — the routine can't use the credential at all.
- **Routine-specific credentials override shared ones.** `fetch(integration_id=..., routine_id=R)` checks `(I, R)` first then falls back to `(I, None)`. Cross-routine emergency revocation just deletes the routine-scoped record, leaving shared intact.
- **File writes are atomic** (temp file + `os.fsync` + `os.replace`) and locked down to `0o600` on POSIX. Same pattern as `storage/markdown.py`.

### Routine source ([ota_core/routine_source/](../ota_core/routine_source/))

- **Manifest can be `routine.md` (YAML frontmatter) OR `routine.yaml`.** First found wins. The bundled `ota.hello` uses markdown because the body becomes the routine's documentation. Production routines may prefer pure YAML for tooling friendliness.
- **`signature` field is required by Pydantic but not verified in v0.1.** Filesystem mode trusts the local filesystem; a placeholder signature (e.g. `value: trusted-by-filesystem-source`) satisfies the schema. Phase 2 private-channel work in v0.2 will plug Ed25519 verification into a new `SignedChannelRoutineSource`.
- **`verify_files=True` (default) computes SHA-256 of every file listed in the manifest's `files[]`** and rejects mismatches with `FileIntegrityError`. Tests disable this when they need to mutate without re-signing.
- **The seam protocol method is `list_ids()`, not `list()`.** Method-named `list` shadowed the builtin under `from __future__ import annotations` and tripped mypy's `valid-type` check.

### Integration source ([ota_core/integration_source/](../ota_core/integration_source/))

- **`AdapterManifest` is a small sub-contract of Contract D.** Adapters declare which capabilities + versions they satisfy. The full `IntegrationDeclaration` (Contract D) describes the integration itself; the adapter manifest is "I claim to implement these capabilities against that integration." The two will be reconciled in Phase 3.4.
- **Multiple roots** are supported (`FilesystemIntegrationSource([bundled, installed, dev])`). Discovery walks each. Duplicate `adapter_id` across roots raises — there is no override semantics in v0.1.
- **Underscore-prefixed directories are skipped** in discovery so test scaffolds (`tests/fixtures/adapters/_mock_email/`) don't accidentally register.

### Network posture ([ota_core/network_posture/](../ota_core/network_posture/))

- **Allowlist patterns are `fnmatch`-style.** Exact hostnames (`api.slack.com`), wildcards (`*.googleapis.com`), and character classes (`region-[12].googleapis.com`). Empty allowlist blocks everything — there is no "block by default but allow if not configured" mode, by design.
- **Rate limit policies are per-host** at the `HttpClient` layer. NetworkPosture's `configure_rate_limit()` is a thin pass-through that also keeps the policy in its own dict so a dashboard can display it.
- **The L0b ↔ NetworkPosture cascade** (per architecture cross-contract invariant 7) — credential revocation cascades to removing the integration's egress patterns from the allowlist — is not yet automated. Phase 3 binding revocation hooks need to call `NetworkPosture.remove_allowlist_entries()` when a credential is revoked.

### L0a / L0b ([ota_core/policy/](../ota_core/policy/))

- **L0a is a prompt assembler, not enforcement.** The default base rules are baked into `DEFAULT_L0A_BASE`. Per-routine sections wrap content in `<name>...</name>` tags so Anthropic prompt caching can keep the base prefix stable (the base is the cache-stable portion; sections vary per call and break the cache by design).
- **L0b enforcement is split across method calls** — `enforce_integration()`, `enforce_scopes()`, `reserve_llm_budget()`, `record_llm_usage()`, `record_verb_invocation()`. The decorator-driven `@verb` path only uses the last; the rest are called by dispatch (Phase 3) and the LLM wrapper (Phase 4A).
- **`active_context()` returns `(enforcer, ctx) | None`.** Modules that need to know "am I inside a routine run right now?" use this. The @verb wrapper uses it to no-op outside runs, keeping tests simple.

### Automation ([ota_core/automation/](../ota_core/automation/))

- **Hand-rolled cron parser** (no `croniter` dep). Supports `*`, literal, `*/step`, `N-M` range, `N,M,O` list across 5 fields. If a routine needs `L`, `W`, or named months, add them then.
- **Scheduler state persists to SQLite** via the auto-installed `cron_jobs` and `event_hooks` tables. The runtime loop wakes every `tick_interval` (default 1s) and fires due jobs.
- **Manual trigger is the v0.1 happy path.** The Phase 2 tracer bullet uses `scheduler.trigger("hello_daily")` — the run loop is exercised by `test_run_loop_fires_due_jobs` but adapter integration tests will mostly drive routines directly.
- **`on_missed` policy from Contract C is parsed but not enforced.** If the framework was down when a cron job was due, on restart the scheduler currently just fires it once at the next tick regardless. Phase 5 (deployment) is the natural home for `coalesce` / `skip` / `run_all` / `run_if_within` semantics once the framework runs as a systemd service.

### Routine engine ([ota_core/systems/](../ota_core/systems/))

- **`helpers.py` is loaded via `importlib.util.spec_from_file_location`** with a unique synthetic module name (`ota_routines_dynamic.<id>_<uuid>`) so two routines with the same `helpers.py` filename don't collide in `sys.modules`. The module IS added to `sys.modules` so the loaded objects are picklable / introspectable; remove this if it causes memory bloat.
- **Convention: `async def run(runtime)`** is the entry point. Sync functions are also accepted (the engine awaits only if the return is awaitable). For v0.2 routines that have multiple steps, expect this to expand to `def steps() -> list[StepDef]` or similar.
- **Knob resolution** validates types + min/max + enum membership + max_length up front. Override of an unknown knob raises. `secret_ref` and `integration_ref` knobs have no built-in default — the operator must supply one.

### Conductor ([ota_core/conductor/](../ota_core/conductor/))

- **`DirectRouter` is the v0.1 strategy.** Everything routes to one registered routine. The `IntentRouter` Protocol is shaped so v0.2's `SemanticRouter + LLMFallbackRouter` plugs in without breaking callers.
- **`Conductor.dispatch()` emits `conductor.route_decided` as a metric**, not an audit event. Routing decisions are operational telemetry, not compliance events. (Failed routings — `NoRouteError` — are different; future v0.2 should audit those.)

### Branches ([ota_core/branches/](../ota_core/branches/))

- **A `Branch` is currently just a named tuple of routine_ids.** No branch-level config, no branch-level router. v0.2 will add both when multiple branches need real isolation.
- **`BranchRegistry.default(routines=[...])` seeds the single `productivity` branch.** This is the v0.1 idiom — pass it the routine_ids you want bundled.

### System wiring ([ota_core/systems/system.py](../ota_core/systems/system.py))

- **`System.conductor`/`Intent` use TYPE_CHECKING string annotations** to break the `systems → conductor → systems` circular import. Don't move the import to runtime without first untangling the cycle.

## Things that got fixed during Phase 2

For future-me searching for resolved items:

- The `verb` decorator placeholder is now a real audit-emitting wrapper (Phase 1 carry-forward to 2A.5).
- `TokenBucket` now layers a per-minute bucket on top of the per-second one (Phase 1 carry-forward to 2B.7).
- `HttpClient.set_allowlist()` accepts a callable predicate so glob expansion works (Phase 1 carry-forward to 2B.7).
- `RoutineSource` / `IntegrationSource` Protocol methods are `list_ids()` not `list()` — mypy `valid-type` collision when the method shadows `builtins.list` under deferred annotations.
- Circular import `systems ↔ conductor` resolved with TYPE_CHECKING in `systems/system.py`.
