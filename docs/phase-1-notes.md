# Phase 1 carry-forward notes

Surfaced during Phase 1 (Foundation) implementation. Captured here so Phase 2
kickoff and later phases don't rediscover them as problems. Each item is tagged
with the phase that should pick it up.

## Open items deferred to specific phases

### Phase 2A — framework runtime

- ~~**`verb` decorator placeholder.**~~ **RESOLVED in Phase 2A.5.** The decorator now wraps every call to emit `tool_call.invoked` / `succeeded` / `failed` audit events via `L0bEnforcer` when a routine-run context is active, and is transparent when called outside one. Metadata still attached. See [`ota_core/policy/__init__.py`](../ota_core/policy/__init__.py) and [`ota_core/policy/l0b.py`](../ota_core/policy/l0b.py).

- **Cost estimation hook missing on `LLMProvider`.** Still open. The protocol returns `Usage` (input/output/cache tokens) but does not estimate cost. L0b's `reserve_llm_budget()` accepts an explicit `usd` argument so callers can estimate at call-sites for now, and `record_llm_usage()` updates `ctx.usd_spent`. The provider-side `estimate_cost(request) -> Decimal` method (and pricing tables) is **deferred to Phase 4A** when the first real adapter call goes through the LLM client and budget enforcement needs to be automatic. Phase 2A.5 just leaves the seam open.

### Phase 2B — seams

- ~~**`TokenBucket` only enforces RPS, not RPM.**~~ **RESOLVED in Phase 2B.7.** `RateLimitPolicy` now accepts `requests_per_minute` + `burst_per_minute`; `TokenBucket` checks both buckets per acquire and waits for the tighter of the two. Tests in [tests/network_posture/test_posture.py](../tests/network_posture/test_posture.py).

- ~~**Allowlist is a flat `frozenset[str]` of hostnames.**~~ **RESOLVED in Phase 2B.7.** `HttpClient.set_allowlist()` now accepts either a `frozenset[str]` (exact match, backward compatible) or a `Callable[[str], bool]` predicate. `NetworkPosture.configure_allowlist()` compiles `fnmatch`-style globs (e.g. `*.slack.com`, `region-[12].googleapis.com`) into a predicate and installs it on the client.

### Phase 3 — capability dispatch

- ~~**`dispatch()` placeholders.**~~ **RESOLVED in Phase 3.5.** [ota_connect/messaging/dispatch.py](../ota_connect/messaging/dispatch.py) and [ota_connect/email/dispatch.py](../ota_connect/email/dispatch.py) now forward to `ota_connect.binding.dispatch.dispatch_capability(...)`, which resolves the binding, applies L0b enforcement, and invokes the adapter inside the error-normalization context.

- ~~**Cross-contract validation not yet runtime-enforced.**~~ **RESOLVED in Phase 3.4.** [ota_connect/binding/validator.py](../ota_connect/binding/validator.py) holds references to a `RoutineBundleManifest` *and* the active `IntegrationRegistryManifest`, and runs the §16 invariant-9 checks (integration exists, binding_level supported, scopes in vocabulary). Invariant 10 (Identity vs Secrets separation) is structural — enforced by the seam boundaries, not a runtime check.

### Phase 4 — adapters

- **Generated error classes lack `__init__`.** [ota_connect/_types/errors.py](../ota_connect/_types/errors.py) is generated faithfully from `vocabulary/_types.md`, which declares class-body annotations only. So `OTAConnectError("msg")` works (Exception's `__init__` takes the message), but `RateLimited(retry_after=timedelta(seconds=30))` fails with `unexpected keyword argument`. **Phase 3 workaround:** [`ota_connect.binding.error_norm.make_error`](../ota_connect/binding/error_norm.py) instantiates via `__new__` + `setattr`, bypassing the missing `__init__`. Long-term fix (Phase 4A): emit `@dataclass(kw_only=True, eq=False)` on each generated error class — see [docs/phase-3-notes.md](phase-3-notes.md).

- **`AsyncAnthropic.close()` assumed async, not verified.** [ota_core/llm/anthropic_provider.py](../ota_core/llm/anthropic_provider.py) calls `await self._client.close()` in `aclose()`. Test uses a fake. If the SDK version exposes `close()` as sync, the call raises `TypeError` at first real shutdown. Verify when the first adapter (Phase 4A) makes a real LLM call.

### Phase 4C — dashboard

- **OpenAPI codegen hook is dormant.** [.pre-commit-config.yaml](../.pre-commit-config.yaml) has a `gen-api-sync` hook that no-ops via `if [ -d ota_dashboard_web ]`. Activates when Phase 4C.2 creates the directory and `pnpm gen-api` script.

- **`just gen-api`** prints a "not present yet" message instead of running. Same activation trigger.

### Phase 5 — deployment

- **`just dev` and `just build` are stubs.** They print a phase reference and exit 1. Real impls land with Phase 4 (FastAPI + Vite launcher) and Phase 5 (Dockerfile).

## Design notes worth knowing

### Contract models ([ota_core/contracts/](../ota_core/contracts/))

- **`RevocationAction` uses a callable `Discriminator`** ([integration_registry.py:97-118](../ota_core/contracts/integration_registry.py)). Pydantic's standard `Field(discriminator="local_only")` couldn't be used because the canonical YAML example in `contracts.md` omits `local_only: false` for remote revocations. The callable inspects the dict for a `local_only: True` to decide between `RemoteRevocationAction` and `LocalOnlyRevocationAction`.

- **`Knob` discriminated union covers 11 types** ([routine_source.py](../ota_core/contracts/routine_source.py)): `bool, int, float, string, enum, time, duration, cron, secret_ref, integration_ref, list`. `KnobList` is non-recursive — `inner_type` is a string literal, not a nested `Knob`. Routines do deeper validation themselves.

- **`EventType` is a closed `Literal` of 80 values.** Adding a new event type requires editing [audit_event.py](../ota_core/contracts/audit_event.py) and bumping `schema_version`. The build plan explicitly accepts this; the spec language is "unknown types are rejected and replaced with `policy.violation`."

- **`IntegrationEndpoints` uses `extra="allow"`.** Auth-style-specific endpoint blocks (api_key, mtls, custom) are not fully specced in `contracts.md`, so the model lets unknown nested keys through. Tighten when auth-style schemas lock.

- **`KnobList.default` is `list[bool | int | float | str]`.** Pragmatic; could tighten to a discriminated default later.

- **Cross-contract validators are deferred to runtime.** The per-contract Pydantic models do not perform reconciliation across A↔D (every routine integration exists in registry; binding_level supported; scopes ∈ vocabulary). That lives in the routine loader (Phase 2) or capability layer (Phase 3).

### Codegen tool ([scripts/gen_vocab_stubs.py](../scripts/gen_vocab_stubs.py))

- **Spec format inconsistencies handled inline.** During the first real run the parser had to adapt to: types that lack `**Form:**` labels (DeliveryStatus, Importance, Cursor, Page); the `### Hierarchy` heading missing backticks; generic params in headings (`Page[T]`); and the errors hierarchy being a single python block under one H3 rather than per-type H3s. Future capability authors who follow the locked spec patterns will not hit any of these.

- **`T = TypeVar("T")` is injected by the codegen**, not present in the vocab spec for `Page[T]`. Lives in `DOMAIN_IMPORTS["pagination"]` rather than the parsed source. If another generic type lands in the spec later, decide whether to keep injecting boilerplate or update the spec to include it.

- **Imports in generated `verbs.py` are filtered to what's actually used.** The capability frontmatter `references_types` is the "available pool"; the codegen tokenizes signatures and imports only the intersection. This is why `DeliveryStatus` is in messaging's `references_types` but does not appear in the import block of [ota_connect/messaging/verbs.py](../ota_connect/messaging/verbs.py).

- **`datetime` import auto-detected from signatures.** `since: datetime | None = None` in `list_recent_messages` triggers `from datetime import datetime` in the generated verbs file. Codegen has no other stdlib-import auto-detection — if a future verb uses `timedelta` directly in a signature, add detection then.

- **Codegen runs `ruff format` on its output** as a final step. Without it, the spec's tabular comment alignment (multiple spaces before `#`) fails `ruff format --check`. The script catches missing-ruff gracefully and prints a warning rather than failing.

- **`UP046` (Generic[T] → PEP 695) is globally ignored** in [ruff.toml](../ruff.toml). The vocab spec uses `class Page(Generic[T])`; auto-rewriting to `class Page[T]:` would orphan the `T = TypeVar("T")` declaration. Either keep the rule off, or update spec + codegen to PEP 695 form together (one-shot migration).

- **`-> None` verbs generate bare `dispatch(...)` calls**, not `return dispatch(...)`. Because `dispatch` is annotated `-> NoReturn`, mypy rejects `return dispatch()` from a `-> None` function. The runtime behavior is identical since `dispatch` raises.

### Storage layer ([ota_core/storage/](../ota_core/storage/))

- **No SQLAlchemy.** Raw `sqlite3` from stdlib + Pydantic at the boundary, per build-plan §3.1. Each module that owns a table writes its own SQL.

- **Sync API only.** [database.py](../ota_core/storage/database.py) is synchronous. Async paths (FastAPI in Phase 4C, adapters in 4A) wrap calls with `asyncio.to_thread`. No async wrapper baked in.

- **Single connection per `Database` instance, shared across threads** via `check_same_thread=False`. Section 8 of `architecture.md` says serialization comes from the L0b single-writer queue (Phase 2A), not the connection. Per-routine state has no contention by construction.

- **Migration tracking table is `_schema_migrations`** with leading underscore. The "list user tables" test query filters via `name NOT LIKE '_%'`. Future framework-internal tables should follow the same convention.

### HTTP client ([ota_core/http/](../ota_core/http/))

- **Async-only.** `httpx` supports sync, but every adapter we'll write is async (slack_sdk, Google API). Add a sync wrapper if a real consumer needs one.

- **`HttpClient.set_rate_limit(host, policy)` is the integration-binding hook.** When Phase 4A adapters register, they'll call this per-host based on the bound integration's Contract D `rate_limits`. The token bucket is per-host, not global.

### LLM client ([ota_core/llm/](../ota_core/llm/))

- **Streaming, image input, and PDF input not implemented.** The Anthropic SDK supports all three; `LLMProvider` does not expose them yet. Add when a routine asks. The protocol is non-breaking to extend.

- **`anthropic` SDK is imported only in [anthropic_provider.py](../ota_core/llm/anthropic_provider.py).** Per build-plan §1 Layer 1 lock. Other modules that need LLM access should depend on the `LLMProvider` Protocol, not concrete `AnthropicProvider`.

- **Model context limits are hard-coded** in `_MODEL_CONTEXT_LIMITS`. Update when new model IDs ship.

### Pre-commit and codegen sync

- **First `pre-commit run` takes ~1 minute** because the `gen-vocab` hook installs its `pyyaml` + `ruff` deps into an auto-managed cache. Subsequent runs are fast.

- **The `gen-vocab` hook unconditionally regenerates**, no `files:` filter. This catches hand-edits to generated files (regen overwrites; pre-commit detects "files were modified by this hook" and fails). The `gen-vocab-diff` hook is belt-and-suspenders covering the same case via `git diff --exit-code`.

- **`-diff` in [.gitattributes](../.gitattributes)** suppresses default `git diff` output for generated paths. Override with `git diff --no-ext-diff` if you need to see what changed.

## Things that did get fixed during Phase 1

For future-me searching for resolved items:

- Version pins bumped from January-2026 vintage to current latest after PyPI verification (1.1).
- `.vscode/` added to `.gitignore` after initial omission (1.1).
- Relative links in `docs/architecture.md` rewritten after migration into `docs/` (1.2).
- Mypy "unused override section" notes for `anthropic` / `authlib` resolved once 1.6 and 1.7 imported them.
- `docs/build-plan-v0.md` §4.1 directory tree updated to include `ota_core/http/` and `ota_core/oauth/` (post-1.6).
