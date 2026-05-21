# Phase 3 carry-forward notes

Surfaced during Phase 3 (Capability Layer) implementation. Captured here so
Phase 4 (adapters / routine / dashboard) and later phases don't rediscover
them as problems. Each item is tagged with the phase that should pick it up.

## Open items deferred to specific phases

### Phase 4A — adapters & runtime contracts

- **Generated `OTAConnectError` classes still lack a real `__init__`.**
  Workaround unchanged in Phase 4 — adapters call
  [`make_error`](../ota_connect/binding/error_norm.py) instead of the
  bare constructor. Codegen patch deferred until v0.2.

- ~~**Adapter `invoke()` is sync at the protocol boundary.**~~
  **CONFIRMED in Phase 4A.** Both `slack_socket_adapter` and
  `gmail_oauth_adapter` use sync `httpx.Client` blocking calls; the
  pre-built protocol holds for v0.1. Real async I/O via the
  thread-pool bridge stays deferred until measured latency demands it.

- **L0b → NetworkPosture cascade still manual.** The architecture
  cross-contract invariant (revoke a credential → strip its egress patterns
  from the allowlist) is wired *partially*: dispatch invokes
  `enforce_integration` + `enforce_scopes` (Phase 3.5). When Phase 4A
  introduces credential revocation flows, hook
  `NetworkPosture.remove_allowlist_entries(...)` into the revocation handler
  per architecture §16 invariant 9. Phase 2 notes flagged this; Phase 3
  didn't take it on because revocation only fires from adapter / dashboard
  surfaces that don't exist yet.

- **`required_scopes` lookup uses generated-module reflection.**
  [`dispatch._verb_required_scopes`](../ota_connect/binding/dispatch.py)
  re-imports `ota_connect.<capability>.verbs` and reads `_ota_verb_meta`
  off the function. That's fine in v0.1 (one import per call, module is
  cached). If profiling flags it later, hoist into a registry built at
  framework boot from the generated modules.

### Phase 4B — routine HITL

- ~~**ActionRouter is a dumb single-handler-per-routine map.**~~
  **RESOLVED in Phase 4B.3.** [`GateManager`](../ota_core/policy/gates.py)
  sits on top of the ActionRouter contract — it owns the gate-instance
  state machine (pending → approved / rejected / modified_and_approved /
  auto_approved / expired) and its three approval modes. The
  ActionRouter is still the last-mile delivery for Slack action callbacks;
  the gate manager is the policy layer.

### Phase 4C — dashboard

- **Audit emission for dropped action callbacks is severity=warn.**
  When an action arrives for an unknown `routine_id`,
  `ActionRouter.dispatch` still emits the audit event with `delivered=False`
  and `severity="warn"`. Phase 4C.6 dashboard audit-log viewer surfaces all
  warn-level events; client-side filtering on `severity_at_least=warn`
  pulls them up.

### Phase 5 — deployment

- **`InboundEmailLoop` lifecycle is unmanaged in v0.1.**
  [`InboundEmailLoop.start()`](../ota_connect/binding/inbound_email.py)
  creates an asyncio task on the current loop and returns it. Routine engine
  in Phase 2A.4 doesn't yet wire the loop into its lifecycle. Phase 5
  (deployment) needs to start it under the systemd unit's event loop and
  call `stop()` on SIGTERM. Until then it runs only when manually started
  from a notebook / test.

## Design notes worth knowing

### Binding resolver ([ota_connect/binding/resolver.py](../ota_connect/binding/resolver.py))

- **Longest-prefix-match runs on `capability.verb` joined as a dotted
  string.** A binding for `messaging.send_email` wins over the more general
  `messaging:` default for `send_email`; everything else falls through. The
  resolver keeps `keys_by_length` sorted at construction so resolve is
  O(num_keys).
- **Plain capability bindings match any verb.** `messaging: slack` resolves
  every messaging verb to slack. Architecture §3 says routines cannot
  force-specify an adapter at the call site, so resolution is the only
  knob.
- **Key validation rejects uppercase, leading digits, and dashes.** The
  regex is `^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$` — matches the dotted
  identifier shape used by capability + verb names elsewhere.

### Install-time validator ([ota_connect/binding/validator.py](../ota_connect/binding/validator.py))

- **Five checks, returned as a `ValidationReport`:** capability is bound at
  all; binding points to a known adapter_id; adapter's manifest claims that
  capability; integration exists in Contract D registry; binding_level is
  supported by the integration; declared scopes are all in the integration's
  vocabulary. The report aggregates issues so the operator sees every
  problem on one install attempt instead of fixing them one by one.
- **`required_capabilities` is an extension point.** Callers can pass the
  set of capabilities the routine's verb call-sites use, in addition to
  those declared in `capabilities.consumes`. The bundle loader (Phase 2B.5)
  is the natural caller; until that wiring lands, validation relies on
  whatever the routine declares.
- **Identity-reference reachability check (architecture §3 step 3) lives in
  the routine bundle loader**, not this module. Phase 2B.5 already validates
  `people.md` resolution per adapter; the binding validator stays focused on
  structural shape.

### AdapterRegistry ([ota_connect/binding/registry.py](../ota_connect/binding/registry.py))

- **Entrypoint format is `module.path:attribute_name`.** The manifest's
  `entrypoint` field is imported with `importlib.import_module`; the
  attribute is called as `target(bundle)` if callable, otherwise used
  directly. Mock adapters in `tests/fixtures/adapters/` use a class form
  (`MockMessagingAdapter`); production adapters can ship either.
- **`register_factory()` bypasses entrypoint imports.** Tests that need to
  inject a mock without writing a manifest just call
  `registry.register_factory(adapter_id, factory)`. Factories take
  precedence over `entrypoint`.
- **Instance cache is keyed on `adapter_id`** and lifetime-scoped to the
  registry. `reset()` clears it; production deployments don't hot-reload
  adapters in v0.1.

### Dispatch ([ota_connect/binding/dispatch.py](../ota_connect/binding/dispatch.py))

- **The dispatch context is per-thread (ContextVar).** Set once at framework
  boot via `set_dispatch_context(ctx)`. Tests use the
  `dispatch_context(ctx)` context manager to install one for the duration
  of a test. Calling a verb without an installed context raises
  `NotConfiguredError` immediately — fail-fast, no silent fallbacks.
- **L0b enforcement is opt-in.** When no `active_context()` exists
  (calling a verb outside a routine_run), dispatch skips
  `enforce_integration` / `enforce_scopes` and just runs the adapter call.
  This keeps unit tests of adapters lightweight; the routine engine wraps
  every routine call in `routine_run` so enforcement is mandatory in
  production.
- **Error normalization is layered around the adapter call only.** L0b
  policy violations (which raise `IntegrationNotAllowedError` /
  `ScopeEscalationError`) propagate as themselves; only adapter-thrown
  exceptions get wrapped to `AdapterUnavailable`.

### Error normalization ([ota_connect/binding/error_norm.py](../ota_connect/binding/error_norm.py))

- **`OTAConnectError` subclasses pass through unchanged.** Adapter authors
  who want to raise `RateLimited(retry_after=...)` construct the error via
  `make_error(RateLimited, adapter=..., capability=..., verb=...,
  retry_after=...)`. The normalization context manager sees an instance and
  re-raises as-is.
- **Everything else becomes `AdapterUnavailable` with `retryable=True`.**
  This is a deliberate default — most adapter errors are transient (network
  blip, auth refresh hiccup). Adapter authors can override with explicit
  `make_error` calls for non-retryable cases (`MessageRejected`,
  `IdentityResolveError`, etc.).
- **Original exception chains via `__cause__`.** The dashboard audit log
  viewer in Phase 4C.6 should surface the chain when an `AdapterUnavailable`
  is investigated.

### Mock adapters ([tests/fixtures/adapters/](../tests/fixtures/adapters/))

- **Both `mock_messaging` and `mock_email` implement every verb in their
  capability's vocabulary.** They keep state in memory (`outbox`, `drafts`,
  `threads`, etc.) so tests can assert on what the routine produced.
- **`queue_inbound()` / `queue_action()` are the test-driven seam** that
  simulates upstream events. Phase 3.9's `InboundEmailLoop.tick_once()`
  drains them; Phase 3.8's `ActionRouter` is what receives the normalized
  envelopes.

## Things that got fixed during Phase 3

For future-me searching for resolved items:

- `ota_connect/messaging/dispatch.py` and `ota_connect/email/dispatch.py`
  no longer raise `NotImplementedError` — they forward to
  `dispatch_capability(...)` (Phase 2 carry-forward → 3.5).
- Contract C ↔ D cross-contract reconciliation now runs at install time via
  `assert_routine_install` (Phase 1 + Phase 2 carry-forward → 3.4).
- Generated verb-module return type now propagates through the dispatch
  layer; codegen emits `# type: ignore[no-any-return]` on the `return`
  statement so mypy --strict stays clean (Phase 3 codegen patch).
- `UP047` (PEP 695 generic functions) ignored in [ruff.toml](../ruff.toml)
  to match the same rationale as `UP046` for generic classes.
