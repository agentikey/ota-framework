# OTA Build Plan v0 — First-Client MVP

Single canonical planning doc for building the full OTA MVP: framework + Slack adapter + Gmail adapter + `email_triage` routine + operator dashboard. Each section gets populated across sessions; this is the source of truth for scope, sequencing, and tech decisions.

**Build goal:** ship an MVP that is ready to deploy and serve the first paying client, as fast as possible without compromising quality. Quality bar is "first client install I would put my name on" — real error handling, accurate audit trails, recoverable data integrity, working onboarding. No artificial deadline; the constraint is correctness and completeness for first-client delivery, not calendar time.

---

## Section 1 — Implementation Gap Audit

Inventory of every module, seam, adapter, artifact, and operational asset that must exist before the MVP demo is deliverable. Items are grouped by architectural layer (matching `architecture.md`). Effort estimates use t-shirt sizing:

- **S** = <1 day (assume 4–6 hours of focused work)
- **M** = 1–2 days
- **L** = 3–5 days
- **XL** = 6+ days

**Caveats on my estimates:**
- I'm estimating based on typical complexity for a senior engineer with strong AI-assisted coding velocity (Claude Code / Agent SDK in the loop). Adjust up if you're context-switching, down if you have prior code to lift from.
- I don't know what (if anything) already exists as proto-code outside the repo I can see. Audit assumes ground zero.
- Some items have hidden complexity I may be underweighting (OAuth flows, real-time UIs, distributed-system edge cases). Treat estimates as floor, not ceiling.

### Layer 1 — Foundation / framework prerequisites

These must exist before any other layer functions.

| Item | What it does | Effort | Dependencies | Notes |
|---|---|---|---|---|
| **Tech stack decisions** | Python version (3.12+ recommended), async runtime (asyncio + httpx), web framework (FastAPI for dashboard API), Pydantic for schema validation, SQLAlchemy or raw SQLite, logging (structlog), Ed25519 signing (cryptography lib), Docker base image. | S | — | Decide before any code. Affects everything. |
| **Repo structure** | Monorepo with `ota_core/`, `ota_connect/`, `ota_routines/`, `ota_dashboard/`, `vocabulary/`, `tests/`, `migrations/`. Package layout, pyproject.toml, ruff/mypy config. | S | Tech stack | Get this right early; restructuring later is expensive. |
| **Build / CI scaffold** | pyproject.toml with deps, ruff + mypy + pytest config, GitHub Actions for CI, Docker build pipeline. | S | Repo structure | Minimal CI: lint, type-check, test on push. |
| **Storage layer** | SQLite WAL setup, schema migration system (Alembic or hand-rolled), markdown projection layer (read MD into runtime objects, write runtime state back to MD for L4 files). | M | Tech stack | L4 SQLite + MD projection is in architecture.md as the storage shape. |
| **JSON Schema validation framework** | Pydantic v2 models for all five contracts (A–E). Schema enforcement at the boundary. | M | Tech stack | Validation must wrap every contract-typed I/O. |
| **LLM client abstraction** | LLM Provider seam: `LLMProvider` protocol, concrete Anthropic implementation (claude-sonnet-4-6 for production, claude-haiku-4-5 for cheap routing decisions). Capability negotiation per Contract A. | M | Tech stack | Don't import `anthropic` directly anywhere except the provider impl. |
| **HTTP client abstraction** | Single httpx-based HTTP client used by all adapters, with retry / backoff / rate-limit handling baked in. | S | Tech stack | Adapters should not roll their own retry logic. |
| **Vocabulary → Python codegen tool** | Parses `vocabulary/*.md` (frontmatter + Python fenced blocks + per-verb YAML metadata blocks) and generates `ota_connect/_types/*.py` and `ota_connect/{capability}/verbs.py`. Pre-commit hook + CI step enforce in-sync, same discipline as the OpenAPI codegen. | M | Tech stack, JSON Schema validation | Eliminates the parallel-source-of-truth maintenance burden between the markdown vocabulary spec and the runtime Python. See Section 3.4 for full workflow. |

**Layer 1 subtotal:** ~7–11 days. Most of this is the unglamorous tooling that everything else depends on.

### Layer 2 — Framework runtime (Core)

The Conductor / Branches / Systems / Automation stack from architecture.md.

| Item | What it does | Effort | Dependencies | Notes |
|---|---|---|---|---|
| **Conductor — semantic router** | Tiered intent routing: fast semantic match (embeddings or keyword) for common path; LLM fallback for ambiguous; user confirmation for low confidence. | L | LLM client, storage | Cache prior routing decisions. Sub-100ms common-path target. |
| **Conductor — load manifest resolver** | Pre-flight context resolution per architecture.md decision. Conductor produces a declared load manifest before any routine runs. | M | Conductor router | Framework loads context deterministically based on manifest. |
| **Branches scaffold** | Role-specialized sub-agent abstraction. For MVP, only one branch (productivity) is needed; the abstraction must support adding more later. | M | Conductor | Don't over-build the branch system; one working branch is enough for MVP. |
| **Systems primitive** | Execution units inside a branch (skills, workflows, scripts). For MVP, the `email_triage` routine is the only system; the abstraction must be there for v1+. | M | Branches | Systems = the thing a routine actually consists of. |
| **Automation layer** | Scheduler primitives: cron triggers, event-hooks. APScheduler or hand-rolled. For email_triage: every-N-minutes polling + manual trigger. | M | Storage (scheduler state) | Persistent across restarts. |
| **Routine engine** | Loads routine markdown + Python helpers, parses frontmatter / config, instantiates the routine with bound capabilities. | L | Conductor, Branches, Systems | The heart of the framework. Markdown-first per architecture. |
| **L0a system-prompt layer** | Soft rules in the LLM system prompt: don't fabricate, voice consistency, ambiguity handling. Concatenates per architecture decision. | S | LLM client | Just a prompt template + injection. |
| **L0b Python policy layer** | Hard constraints wrapping every tool call: integration allowlists, budget enforcement, gate enforcement, schema validation. | L | Storage, contracts | This is the safety net. Must wrap every adapter call. |
| **Cross-routine artifact store** | Typed artifacts (pending/claimed/completed/failed/expired) for cross-routine coordination. SQLite-backed. TTL handling (default 4h). | M | Storage | `artifact.auto_expired` event emitted on TTL expiry. |
| **Trace ID propagation** | OTel-standard trace_id flowing through every call, audit event, and observability emission. | S | All of above | Single function: generate or propagate. |

**Layer 2 subtotal:** ~14–20 days. This is the biggest chunk and the critical path.

### Layer 3 — Seams (pluggable framework interfaces)

Per Decision in architecture.md: 8 pluggable seams. Not all need real implementations for MVP; some can stub to local defaults.

| Item | What it does | Effort | Dependencies | MVP impl |
|---|---|---|---|---|
| **IdentityProvider seam** | Resolves `IdentityRef` strings (`handle:@x`, `mailto:...`, `raw:...`) to per-adapter IDs. Reads `people.md` (markdown registry). | M | Storage, vocabulary | Local markdown-backed for MVP; no external identity provider integration. |
| **SecretsProvider seam** | Credential storage / rotation. Virtual credential scoping per architecture decision. | M | Storage | Local encrypted file-backed for MVP (e.g., age or sops); no Vault / AWS Secrets Manager. |
| **AuditSink seam** | Append-only audit event recording. JSONL per architecture decision. | S | Storage | Local JSONL file for MVP. |
| **ObservabilitySink seam** | Metrics + traces. OTel-compatible. | S | Trace ID | Local stdout / file for MVP; no Honeycomb / Datadog. |
| **LLMProvider seam** | Already in Layer 1. Listed here for completeness. | — | — | Anthropic only for MVP. |
| **RoutineSource seam** | Where routines come from. Filesystem for MVP; private channel for v1+. | S | Storage | Filesystem-only is fine for the demo; private channel is post-MVP. |
| **IntegrationSource seam** | Where adapters come from. Filesystem for MVP. | S | Storage | Same as RoutineSource. |
| **NetworkPosture seam** | Outbound-only enforcement, allowlists. | S | HTTP client | Allowlist file checked at every outbound HTTP call. |

**Layer 3 subtotal:** ~5–7 days. Mostly local-mode implementations; production seams (Vault, OTel collector, etc.) are post-MVP.

### Layer 4 — Capability layer (OTA Connect)

The vocabulary + adapter loading + binding resolution implementation. Specs are locked; this is the runtime.

| Item | What it does | Effort | Dependencies | Notes |
|---|---|---|---|---|
| **`ota_connect` package skeleton** | Python package implementing the namespace structure: `ota_connect.messaging`, `ota_connect.email`, etc. Each capability is a Python module whose public functions match the vocabulary spec. | M | Vocabulary specs | Generated stubs from spec frontmatter; hand-implement dispatch. |
| **Adapter manifest schema + loader** | Adapter declares which capabilities + versions it satisfies. Schema validation. Loader reads adapter directory, registers adapters. | M | JSON schema, storage | Adapter manifest is its own contract (sub-contract of Contract D). |
| **Binding resolver** | Per Decision 6: longest-prefix-match binding from client config to adapter. Validates at install time, dispatches at call time. | M | Adapter loader, contract E | Install-time validation must catch missing bindings. |
| **Capability dispatch layer** | When routine calls `ota_connect.messaging.send_message(...)`, framework resolves binding, applies identity resolution, invokes adapter, normalizes errors. | L | Binding resolver, IdentityProvider, L0b | Wraps every adapter call in retry / observability / audit. |
| **Action callback dispatch** | For messaging adapters: framework receives webhook / socket payload from adapter, normalizes into `integration.messaging.action_triggered` event, routes to routine handler. | M | AuditSink, ObservabilitySink | Routine subscribes to events; framework fans out. |
| **Inbound email event loop** | Email-specific event polling (bounces, replies, delivery confirmations). Translates inbound state into `integration.email.*` events. | M | Email adapter, event dispatch | Polling-based for MVP; webhook support is post-MVP. |
| **Pagination iterator** | `ota_connect.iter_all(verb, **args)` framework primitive that auto-paginates Page[T]-returning verbs. | S | Capability dispatch | Generator implementation. |
| **Error normalization** | All adapter errors mapped to `OTAConnectError` hierarchy at the boundary. Adapters can raise platform errors internally; framework normalizes. | S | Vocabulary _types | Decorator pattern around adapter calls. |

**Layer 4 subtotal:** ~7–10 days. The bridge between specs and adapters.

### Layer 5 — Adapters (concrete integrations)

| Item | What it does | Effort | Dependencies | Notes |
|---|---|---|---|---|
| **`slack_socket_adapter`** | Full Slack adapter implementing `messaging` capability v1.0. Socket Mode for outbound-only posture. OAuth flow for install. Implements all 5 verbs. | L | Capability layer, OAuth helper | Slack SDK (`slack_sdk`) handles most plumbing. Action callbacks via Socket Mode events. |
| **`gmail_oauth_adapter`** | Full Gmail adapter implementing `email` capability v1.0. OAuth flow for install. Implements all 9 verbs. Polls for inbound events. | L | Capability layer, OAuth helper | Gmail API + Google OAuth library. Implementing all 9 verbs takes time. |
| **OAuth helper module** | Shared OAuth 2.0 flow handler (auth URL gen, callback handling, token refresh, storage via SecretsProvider). Used by both adapters. | M | SecretsProvider, HTTP client | Generic enough that future adapters reuse. |
| **Adapter conformance test scaffolding** | Per Decision 3a: snapshot test fixtures for each adapter against each vocabulary verb. For MVP, write the harness; populate with N tests per verb. | M | Capability layer, test framework | Don't need 100% coverage for MVP; enough to validate the loop works. |

**Layer 5 subtotal:** ~7–10 days. Adapter complexity is dominated by OAuth + API quirks.

### Layer 6 — Routine: `email_triage`

The actual product the demo will run.

| Item | What it does | Effort | Dependencies | Notes |
|---|---|---|---|---|
| **`email_triage` routine markdown** | Full routine spec: frontmatter (capabilities, scopes, schedule), config knob surface (categories, templates, thresholds), prompt templates per tier (Reader / Drafter / Auto). | M | Vocabulary | Authored against the locked vocabulary. Three-tier structure per the service-fit analysis. |
| **`email_triage` Python helpers** | Routine-side logic: hash-based dedup keys for processed emails, trust-promotion counter logic, criteria-drift detector, `/why` lookup handler. | M | Routine engine, storage | Markdown handles config; Python handles state + counters. |
| **Routine config schema** | YAML schema for `email_triage` config including knob types (string, enum, list, markdown_path), cross-field validation rules. | S | JSON schema | Per-routine schema file, validated at install. |
| **Per-template state tracking** | SQLite tables for trust-promotion counters, edit-pattern logs, processed-email dedup. | S | Storage | Per `email_triage` instance. |
| **HITL gate primitives** | Three approval modes (approve / tune-and-approve / approve-and-remember). Gate-the-delta UX. Per-routine similarity function. | M | Action callback dispatch | This is also reused by other routines later. |
| **Criteria-drift detector** | Background check: if processed/draft/skip ratio shifts >X% week-over-week, post nudge to operator. | S | Storage, observability | One scheduled task. |

**Layer 6 subtotal:** ~5–7 days. Routine logic is small; the heavy lifting was done in framework / capability layers.

### Layer 7 — Operator dashboard

Web-based UI for the operator (Omar in the Managed model, or the client-side operator in self-hosted modes). The client (or you) will use this every day to review the approval queue, audit decisions, and tune knobs. Usability matters because daily friction translates directly to dropped engagements.

| Item | What it does | Effort | Dependencies | Notes |
|---|---|---|---|---|
| **Dashboard backend (FastAPI)** | API endpoints: routine status, approval queue, audit log query, knob editor, fleet version, `/why <id>` lookup. | M | Storage, all framework layers | Read-mostly; mutations go through framework. |
| **Dashboard frontend skeleton** | React or HTMX-based UI (HTMX is faster to build, lower JS surface). Layout, navigation, theme. | M | Backend API | HTMX recommended for solo dev velocity + lower complexity. |
| **Approval queue UI** | List of pending drafts, click to expand, approve / edit / skip actions. Real-time updates (WebSocket or polling). | M | Backend API | Client touches this every day. Latency, clarity, and edit ergonomics directly affect retention. |
| **Audit log viewer** | Searchable, filterable view of audit events. Trace ID drill-down. | S | Backend API | Operational requirement — the warranty pitch depends on the client (or you) being able to inspect any decision after the fact. |
| **`/why <id>` interface** | Pretty rendering of routine's reasoning for a given decision. | S | Backend API | First-line client question when the routine misclassifies anything. Must work cleanly from day one. |
| **Knob editor UI** | Form-based editor for routine config (categories, templates, thresholds). Validates against routine config schema. | M | Backend API, config schema | Avoid building a full schema-driven form generator for MVP — hand-build for `email_triage`. |
| **Fleet version status** | Single-client view in MVP (just the local install). Lists pinned versions, last update, stale-install warnings. | S | Backend API | Forward-looking; trivial for one client. |
| **Critical banner / notification surface** | Operator notification UI for emergency stops, gate failures, etc. Per architecture decision: persists across restart. | S | Storage, observability | Slack DM is the secondary surface; banner is in-dashboard. |

**Layer 7 subtotal:** ~6–8 days. Polish-sensitive because it's the demo.

### Layer 8 — Deployment & operational

| Item | What it does | Effort | Dependencies | Notes |
|---|---|---|---|---|
| **Docker image** | Single image per architecture decision. Builds framework + adapters + routines + dashboard. | S | Repo, tech stack | Multi-stage build. |
| **Mode 2 (VPS) install** | Bootstrap script / instructions for installing on a Linux VPS in the client's cloud account (Ubuntu 22.04/24.04). Docker + systemd service + Caddy for HTTPS via Let's Encrypt. Self-restart on crash via systemd. | M | Docker, Caddy / TLS | Mode 2 is the v0.1 default per Section 6. Mode 1 (laptop) explicitly rejected — laptops sleep, paying clients need always-on. |
| **Per-client OAuth app provisioning docs** | Step-by-step instructions for the client to create their own Google Cloud project + OAuth credentials, and their own Slack app. Public callback URL pattern documented (uses the VPS's domain). | S | — | Documentation / instructions, not Python code. Each Mode 2 install is per-client; OAuth apps cannot be shared across clients because callback URLs differ. |
| **Backup / state snapshot** | Periodic snapshot of `state/` directory (SQLite + markdown) under the VPS data dir. Daily by default. Easy restore command. | M | Storage | Data integrity matters from day one — corrupted trust counters or identity registry breaks the routine and your reputation. Snapshot-and-restore is non-negotiable. Stored on the same VPS for v0.1 (remote backup to S3 deferred to v0.2). |
| **Adapter test fixtures + happy-path E2E** | Realistic test inbox + test Slack workspace fixtures, plus an end-to-end test script that exercises the full routine loop on synthetic data. | M | Adapters, routine | Used to verify a fresh client install works before handing over. Not "demo data" — pre-install acceptance check. |
| **Operator bootstrap CLI** | SSH-invoked CLI on the VPS: pull Docker image, run `ota init`, configure TLS / domain, set initial admin credential, print dashboard URL. | M | Docker | Operator-driven. Run once per install during VPS provisioning. |
| **Client web onboarding wizard** | Browser-based flow in the dashboard: paste OAuth credentials (from client's Google Cloud / Slack app), execute Gmail OAuth dance, execute Slack OAuth dance, set categories, install routine, validate end-to-end against test fixtures. | M | Adapters, dashboard frontend | Real onboarding the client runs in their browser, with you driving via screenshare for first delivery. Must catch common misconfigurations (wrong OAuth scopes, missing Slack channel access, identity mapping gaps). Moved from v0.2 to v0.1 because Mode 2 requires it. |

**Layer 8 subtotal:** ~5–8 days. Expanded from earlier Mode 1 estimate by ~2–3 days because Mode 2 adds HTTPS provisioning, per-client OAuth app docs, and the split between operator bootstrap CLI and client web onboarding wizard.

### Out of scope for MVP (explicitly deferred)

These are in the architecture but excluded from the 2-week sprint. Listed so they don't get accidentally pulled in.

- Private routine channel (signed envelope, JWT + refresh, kill list polling). Use filesystem-only RoutineSource for demo.
- Migration tooling (3b / 3c full impl). No migrations exist yet for the MVP since v1.0 is initial.
- Multi-mode support beyond Mode 1 (no VPS / Managed for demo).
- Capability versioning enforcement beyond install-time checks.
- Conformance test corpus at full coverage (just enough to prove the loop).
- Operator dashboard polish: theming, dark mode, mobile, accessibility refinement.
- Additional capabilities beyond `messaging` + `email` (no CRM, calendar, etc.).
- Additional adapters beyond Slack + Gmail.
- Routine inheritance / per-client defaults.md (single client in MVP).
- LLM provider beyond Anthropic.
- Embedded sidecar / local inference (Contract E `external_ollama` or `embedded_sidecar`).
- Three-status kill model (`emergency_killed` etc.) — soft kill only for MVP.
- Stale-install enforcement (Decision 4e) — trivially N/A for single MVP client.

### Effort summary

| Layer | Items | Effort range |
|---|---|---|
| 1 — Foundation | 8 | 7–11 days |
| 2 — Framework runtime | 10 | 14–20 days |
| 3 — Seams (local-mode) | 8 | 5–7 days |
| 4 — Capability layer | 8 | 7–10 days |
| 5 — Adapters | 4 | 7–10 days |
| 6 — Routine | 6 | 5–7 days |
| 7 — Dashboard | 8 | 6–8 days |
| 8 — Deployment | 6 | 5–8 days |
| **Total** | **58** | **56–81 days** |

### What the math says

The audit estimates **56–81 days of effort** at normal solo velocity for the full MVP as scoped. With AI-assisted multipliers on mechanical layers (Claude Code generating boilerplate, schemas, dispatch wiring, dashboard scaffolding; human review and integration), realistic compression is roughly **26–42 days of equivalent effective effort**, with no compression on the judgment-heavy work (Conductor logic, L0b policy enforcement, adapter correctness, HITL UX, trust promotion semantics).

With no artificial deadline, the relevant lever is **scope cuts based on actual product need at v0.1, not time pressure**. Items get cut because the first client doesn't need them (cross-routine artifact store, multi-branch coordination, private channel for second-client delivery), not because the clock is running.

The quality bar is "first-client-ready" across every item that ships — real error handling, accurate audit trails, recoverable data integrity, working onboarding. Items can be deferred; items that ship can't be hand-waved.

**Recommendation for the next session:** drive into MVP Scope Definition (Section 2 — below) where we explicitly mark each item as IN / OUT / MINIMAL based on first-client need, with acceptance criteria for the items where the quality bar bites hardest.

---

## Section 2 — MVP Scope Definition

For each audit item, marked:
- **IN** — ships at first-client quality in v0.1
- **MINIMAL** — ships in v0.1 with reduced scope justified by single-client / single-routine context; full version deferred
- **OUT** — deferred to v0.2 or later; not needed for first client

The cutting principle is **first-client need**, not calendar pressure. Items get cut because v0.1 doesn't need them, not because we're racing.

### 2.1 — Scope matrix

#### Layer 1 — Foundation (all IN)

| Item | v0.1 | Notes |
|---|---|---|
| Tech stack decisions | IN | Locked in Section 3 |
| Repo structure | IN | Locked in Section 4 |
| Build / CI scaffold | IN | Minimal CI: lint + type-check + test on push |
| Storage layer (SQLite WAL + MD projection) | IN | Per architecture decision |
| JSON Schema validation framework | IN | Pydantic v2 |
| LLM client abstraction | IN | Anthropic-only impl behind LLMProvider interface |
| HTTP client abstraction | IN | Shared httpx wrapper with retry / backoff / rate-limit handling |
| Vocabulary → Python codegen tool | IN | Generates `ota_connect/_types/*.py` and `ota_connect/{capability}/verbs.py` from `vocabulary/*.md`. Honors the markdown-first source-of-truth principle from day one. Same enforcement discipline as OpenAPI codegen (Section 3.3). Full workflow in Section 3.4. |

#### Layer 2 — Framework runtime

| Item | v0.1 | Notes |
|---|---|---|
| Conductor — semantic router | **MINIMAL** | Direct routing to the single routine for v0.1. Full semantic router + LLM-fallback tier deferred to v0.2 when multiple routines exist. Interface designed to support full router later without rework. |
| Conductor — load manifest resolver | IN | Simple but real; declares context loads pre-flight |
| Branches scaffold | **MINIMAL** | One branch (productivity) hardcoded. Abstraction stub in place so v0.2 multi-branch doesn't require runtime refactor. |
| Systems primitive | IN | The routine IS a system |
| Automation layer | IN | Scheduler with cron + manual trigger. APScheduler or equivalent. |
| Routine engine | IN | Heart of the framework. Full implementation. |
| L0a system-prompt layer | IN | Soft rules prompt template + concatenation |
| L0b Python policy layer | IN | Safety net — wraps every adapter call. No deferral. |
| Cross-routine artifact store | **OUT** | Single routine in v0.1 → no cross-routine coordination needed. Deferred to v0.2. |
| Trace ID propagation | IN | OTel-standard trace_id through every call |

#### Layer 3 — Seams

| Item | v0.1 | Notes |
|---|---|---|
| IdentityProvider seam | IN | Local markdown-backed (`people.md` registry) |
| SecretsProvider seam | IN | Local encrypted file (age or sops). Virtual credential scoping per architecture. |
| AuditSink seam | IN | Local JSONL file. Append-only. |
| ObservabilitySink seam | **MINIMAL** | File / stdout for v0.1. OTel collector integration deferred. |
| LLMProvider seam | IN | Listed in Layer 1; Anthropic-only impl. |
| RoutineSource seam | **MINIMAL** | Filesystem-only for v0.1. Private routine channel deferred to v0.2 (when client #2 hits, hand-delivery doesn't scale). |
| IntegrationSource seam | **MINIMAL** | Filesystem-only for v0.1. Same logic as RoutineSource. |
| NetworkPosture seam | IN | Outbound-only allowlist enforcement at every HTTP call |

#### Layer 4 — Capability layer (all IN)

| Item | v0.1 | Notes |
|---|---|---|
| `ota_connect` package skeleton | IN | Implements `ota_connect.messaging` and `ota_connect.email` namespaces; stubs generated from vocabulary frontmatter |
| Adapter manifest schema + loader | IN | Adapter manifest is the contract that lets adapters declare which verbs they satisfy |
| Binding resolver | IN | Longest-prefix-match per Decision 6 |
| Capability dispatch layer | IN | Wraps every adapter call in retry / observability / audit / L0b enforcement |
| Action callback dispatch | IN | HITL gates depend on this — Slack button clicks → routine event |
| Inbound email event loop | IN | Polling-only for v0.1 (bounces, replies, auto-responses). Webhook-based delivery confirmations deferred. |
| Pagination iterator (`ota_connect.iter_all`) | IN | Framework primitive |
| Error normalization | IN | All adapter errors → `OTAConnectError` hierarchy at boundary |

#### Layer 5 — Adapters

| Item | v0.1 | Notes |
|---|---|---|
| `slack_socket_adapter` | IN — **all 5 verbs** | Reversed from earlier scope cut. Full vocabulary coverage matters: warranty viability requires adapter completeness, and `edit_message` will get exercised by trust-promotion auto-edit flows. |
| `gmail_oauth_adapter` | IN — **all 9 verbs** | Same logic. Skipping `modify_email_labels` / `mark_unread` / `delete_email` would force `email_triage` to work around gaps; cheaper to implement them once. |
| OAuth helper module | IN | Shared OAuth 2.0 flow handler (auth URL gen, callback, refresh, secrets storage) |
| Adapter conformance test scaffolding | IN — **real coverage** | Reversed from earlier cut. Snapshot tests for each verb against each adapter. This is what the warranty pitch depends on. Not skeleton; real coverage. |

#### Layer 6 — Routine: `email_triage` (all IN)

| Item | v0.1 | Notes |
|---|---|---|
| `email_triage` routine markdown | IN | Three-tier structure (Reader / Drafter / Auto) per service-fit analysis |
| `email_triage` Python helpers | IN | Dedup, trust-promotion counter, criteria-drift detector, `/why` lookup handler |
| Routine config schema | IN | Validated at install time; cross-field constraints |
| Per-template state tracking | IN | SQLite tables for trust counters, edit logs, processed-email dedup |
| HITL gate primitives | IN | Three approval modes (approve / tune-and-approve / approve-and-remember) — reused by future routines |
| Criteria-drift detector | IN | Low effort, high differentiator value. Background check on processed/draft/skip ratio. |
| Trust-promotion auto-send | IN | Reversed from earlier cut. Core differentiator. v0.1 ships with conservative default (20 consecutive un-edited approvals → auto-send per template, demote on first edit). |

#### Layer 7 — Operator dashboard

| Item | v0.1 | Notes |
|---|---|---|
| Dashboard backend (FastAPI) | IN | API endpoints for all dashboard surfaces |
| Dashboard frontend skeleton | IN | HTMX-based (lower JS surface, faster solo dev) — see Section 3 for tech stack lock |
| Approval queue UI | IN | Client-facing daily-use surface. Polish is non-negotiable. |
| Audit log viewer | IN | Searchable, filterable, trace-ID drill-down. Warranty depends on this working. |
| `/why <id>` interface | IN | First-line client question when something goes wrong. Must be clear and complete. |
| Knob editor UI | IN | Reversed from earlier cut. Form-based editor for routine config. Markdown-file editing is a worse client experience; ship the UI. |
| Fleet version status | **MINIMAL** | One client in v0.1 → trivially a placeholder showing pinned versions of the local install. Real fleet view ships when client #2 hits. |
| Critical banner / notification surface | IN | Persists across restart per architecture decision |

#### Layer 8 — Deployment & operational (all IN)

| Item | v0.1 | Notes |
|---|---|---|
| Docker image | IN | Single image per architecture decision; multi-stage build |
| Mode 2 (VPS) install | IN | Ubuntu Linux VPS in client's cloud account; systemd auto-start; Caddy + Let's Encrypt for HTTPS; self-restart on crash. Mode 1 explicitly rejected per Section 6. |
| Per-client OAuth app provisioning docs | IN | Step-by-step instructions for client's Google Cloud project + Slack app. Documentation, not Python code. |
| Backup / state snapshot | IN | Daily snapshot of `state/` directory on the VPS. Easy restore command. Remote backup (S3) deferred to v0.2. |
| Adapter test fixtures + happy-path E2E | IN | Pre-install acceptance check on a fresh deployment |
| Operator bootstrap CLI | IN | SSH-invoked install on the VPS. Pulls Docker, configures TLS, sets initial admin credential, prints dashboard URL. |
| Client web onboarding wizard | IN | Browser-based OAuth + initial config flow in the dashboard. Moved from v0.2 to v0.1 because Mode 2 requires it (no localhost; client interacts through dashboard URL). |

### 2.2 — First-client acceptance criteria

Not every item needs detailed criteria — most are "works correctly" obvious. Below are the items where the quality bar bites hardest, with explicit "what does done look like at the first-client bar" definitions.

**Approval queue UI**
- Operator can see a pending draft within 5 seconds of routine producing it (real-time update via WebSocket or sub-5s polling)
- Approve / Edit / Skip actions are one-click obvious
- Edit mode opens the draft inline; submit returns to queue
- Empty state communicates "all caught up" clearly
- Mobile responsive (operator will use it on phone during morning coffee)
- Renders sender, subject, category classification, and routine reasoning summary above the draft — operator should not need to click into `/why` to make routine decisions

**`/why <id>` interface**
- Returns within 1 second for any decision in the last 90 days
- Shows: input email (sender, subject, body excerpt), classification + confidence, criteria matched, criteria missed, enrichment data used (none for v0.1, but architecture supports), template chosen, prior trust-promotion state, draft generated
- Plain English narrative at the top, structured data underneath
- Linkable URL the operator can share back to you for support questions

**Audit log viewer**
- Filterable by routine, capability, verb, time range, trace_id, error type
- Each row drill-downable to full event payload
- Export filtered view as CSV (clients will want this for compliance)
- Searches return within 2 seconds across 90 days of events on a single client's install

**Slack adapter error handling**
- OAuth token refresh handled automatically on 401, transparent to routine
- Rate-limit responses parsed and retried with adapter-declared backoff (no naive sleep)
- Socket Mode reconnection on disconnect (test by killing the socket process in a separate terminal)
- Action callback dispatches even if Slack momentarily lost the connection (event buffer)
- Channel-not-found, user-deactivated, app-uninstalled errors raise correct `OTAConnectError` subclasses, not raw Slack SDK exceptions

**Gmail adapter error handling**
- OAuth token refresh handled automatically on 401
- Rate-limit handling per Gmail API quota model (per-user, per-method)
- Bounce parsing: incoming DSN messages translated to `integration.email.bounce_received` events with parsed reason codes, not raw DSN strings
- Auth scope mismatch raises `CapabilityDegraded` with the missing scope name, not "permission denied"
- Inbox polling handles cursor-based pagination correctly across restarts (no missed emails, no duplicates)

**Backup / state snapshot**
- Daily automated snapshot of `state/` (SQLite + markdown) to a configurable backup location
- `ota restore <snapshot-id>` brings the install back to that snapshot's state, including SQLite tables and identity registry
- Snapshot taken before any state migration runs (per Decision 3c)
- Snapshot rotation policy: 7 daily + 4 weekly + 3 monthly, configurable

**Operator onboarding wizard**
- End-to-end first-run sets up: Gmail OAuth, Slack OAuth, routine install, category templates, approval channel
- Validates against fixtures: sends a test email, sees the test draft in Slack, approves, confirms email sent
- Surfaces specific failure modes clearly: wrong Gmail scope ("you granted read but not modify, click here to re-auth with the right scope"), missing Slack channel access ("the bot isn't a member of #channel, add it"), identity mapping gap ("@jamie is in your people registry but doesn't resolve in this Slack workspace, check the registry").
- Idempotent — running it again skips already-completed steps and only re-prompts on what's missing

**HITL gate primitives**
- Three modes (approve / tune-and-approve / approve-and-remember) all functional
- `tune-and-approve` captures the operator's edit and feeds it into the trust-promotion edit log
- `approve-and-remember` records the operator's approval as a positive example the routine can use for future similar items (gate-the-delta UX)
- Per-routine similarity function configurable in routine config schema
- Gates persist across operator restart — pending approvals don't disappear if the operator closes the dashboard

**Trust-promotion auto-send**
- Per-template counter; 20 consecutive un-edited approvals → auto-send eligible
- Auto-send eligible templates flagged in approval queue UI ("ready to promote")
- Operator must explicitly opt-in per template to enable auto-send (no silent promotion)
- One operator edit on an auto-promoted template demotes it back to manual approval immediately
- Configurable per-category never-auto-send rules (e.g., "no fit" responses are always manual)

### 2.3 — Critical path and parallelization

**Sequential critical path** (must complete in order):

```
Layer 1 (foundation)
  → Layer 2 (framework runtime) + Layer 3 (seams) — parallelizable internally
    → Layer 4 (capability layer)
      → Layer 5 (adapters) + Layer 6 (routine) + Layer 7 (dashboard) — parallelizable
        → Layer 8 (deployment + onboarding)
```

**Layer 1** blocks everything. Decisions and scaffolding here gate all downstream work. Do not start Layer 2+ until Layer 1 is locked.

**Layer 2 and Layer 3 can run in parallel** once Layer 1 lands. They share storage and JSON schema dependencies but otherwise build on different surfaces.

**Layer 4 is the bottleneck** between framework infrastructure and adapter / routine implementation. Adapters can be stubbed during Layer 4 dev (mock adapter that returns canned responses) so Layer 6 (routine) and Layer 7 (dashboard) work isn't blocked.

**Layers 5, 6, 7 are highly parallelizable** once Layer 4 ships. Each can move independently:
- Layer 5 (adapters) is mostly OAuth + API wrapper work
- Layer 6 (routine) is markdown authoring + small Python helpers
- Layer 7 (dashboard) is FastAPI + HTMX UI work

**Layer 8** depends on Layer 5 and Layer 6 being functional but can start with Docker image work in parallel.

**AI-assisted parallelization opportunity:** Claude Code can produce Layer 1, Layer 3 (seams), Layer 4 (capability dispatch / binding resolution), and Layer 7 frontend scaffolding largely from spec — review-and-integrate work, not write-from-scratch. Focus your judgment-heavy time on Layer 2 (Conductor / routine engine / L0b policy), Layer 5 adapter correctness, and Layer 6 trust-promotion / HITL semantics.

### 2.4 — Open decisions needed before coding

These must be answered in Sections 3, 4, or 5 before Layer 1 work starts.

1. **Tech stack specifics** (Section 3) — Python version (3.12+ recommended), web framework (FastAPI), frontend approach (HTMX vs React), ORM (SQLAlchemy vs raw SQL), Docker base image, async runtime, logging library, schema validation library, OAuth library, Ed25519 signing library, test framework. **Status: unlocked.**

2. **Repo structure** (Section 4) — monorepo vs split. Package boundaries. Where vocabulary specs live relative to runtime modules. Where conformance tests live. Where routines live. **Status: unlocked.**

3. **Dashboard real-time mechanism** — WebSocket vs polling for approval queue updates. WebSocket is more polished and matches "<5 second update" acceptance criterion; polling is simpler. **Recommend WebSocket; lock in Section 3.**

4. **Snapshot storage location** — local-only vs configurable remote (S3, etc.). For Mode 1 first client, local-only is fine; remote can come with Mode 2 / Mode 3 later. **Recommend local-only for v0.1; lock in Section 4 alongside repo structure.**

5. **Onboarding wizard form factor** — CLI vs web UI. Web UI is more client-friendly but ~2 days more effort; CLI is faster to ship and you drive it for the first client anyway. **Recommend CLI for v0.1, web UI in v0.2 when self-serve onboarding becomes valuable.**

6. **Identity registry sync model** — pure manual `people.md` editing vs sync from a directory (Google Workspace, Slack workspace). v0.1 first client probably has <20 identities total; manual is fine. **Recommend manual-only for v0.1; sync deferred.**

### 2.5 — Explicitly deferred from v0.1 (consolidated)

These are explicitly NOT in v0.1 scope, with the version they're targeted for:

**Deferred to v0.2 (second-client triggers):**
- Cross-routine artifact store (needed when routines coordinate)
- Multi-branch conductor coordination (needed when multiple branches exist)
- Conductor semantic router (full version) (needed when multiple routines exist)
- Private routine channel (needed when hand-delivery doesn't scale)
- Per-client defaults inheritance (needed when same routine ships to multiple clients)
- Self-serve operator onboarding web UI (needed when you're not personally onboarding every client)
- Real fleet version status (needed when there's a fleet)
- Identity registry sync from directories (needed when manual editing scales poorly)

**Deferred to v0.3 / later:**
- Migration tooling (no migrations exist until something needs to change)
- Multi-mode deployment beyond Mode 1 (Mode 2 VPS, Mode 3 Managed)
- Capabilities beyond `messaging` + `email` (CRM, calendar, document_storage, task_management, enrichment, etc.)
- Additional adapters per existing capabilities (Outlook, IMAP, Teams, etc.)
- Three-status kill model (`emergency_killed` etc.)
- Stale-install enforcement (Decision 4e tiered thresholds)
- LLM providers beyond Anthropic
- Embedded sidecar / local inference (Contract E `external_ollama` / `embedded_sidecar`)
- Webhook-based delivery confirmations / inbound events (polling-only suffices for v0.1)
- Real OTel collector integration (stdout/file suffices for single-install v0.1)

### 2.6 — v0.1 ship checklist (what "done" means)

The v0.1 release is shippable to the first paying client when ALL of the following are true:

1. ✅ Framework runtime executes a routine end-to-end without manual intervention
2. ✅ Slack adapter implements all 5 `messaging` verbs and passes conformance test suite
3. ✅ Gmail adapter implements all 9 `email` verbs and passes conformance test suite
4. ✅ `email_triage` routine processes a real Gmail inbox, drafts replies, gates approvals through Slack, sends approved replies, and updates trust state
5. ✅ Operator dashboard shows approval queue, audit log, and `/why` for any past decision
6. ✅ Knob editor UI lets operator change criteria, templates, thresholds without editing markdown directly
7. ✅ Onboarding wizard (CLI) completes a full install on a fresh machine, including OAuth and fixture validation
8. ✅ Backup / restore tested with simulated corruption (kill the process mid-write, restore from snapshot, confirm state intact)
9. ✅ Trust-promotion auto-send works end-to-end including operator opt-in, threshold tracking, and demote-on-edit
10. ✅ All Layer 5 adapter error-handling acceptance criteria pass under fault injection (kill the network, expire the OAuth token, hit rate limits)
11. ✅ Audit log is complete and accurate for every routine action of the past 7 days of normal operation
12. ✅ Docker image builds clean and runs on a fresh Mac laptop install

When all 12 are green, v0.1 is shippable. Until then, more work remains.

---

---

## Section 3 — Tech Stack Decisions

All choices locked unless explicitly flagged as overridable. Sub-sections cover backend stack, frontend stack, the type-sync workflow that binds them, and the carry-over decisions from Section 2.4.

### 3.1 — Backend stack (Python)

| Choice | Lock | Rationale |
|---|---|---|
| Python version | **3.12** | Current stable, broad library compat. 3.13 too new — library lag risk. |
| Web framework | **FastAPI** | Async-native, OpenAPI auto-docs, Pydantic-integrated. The OpenAPI auto-generation is load-bearing for the frontend type-sync workflow (see 3.3). |
| Async runtime | **asyncio + httpx** | Stdlib async + best-in-class HTTP client. httpx supports both sync and async; shared across framework runtime and adapters. |
| Schema validation | **Pydantic v2** | Aligned with FastAPI. Used throughout the framework for contract validation (Contracts A–E). Source of truth for all API shapes — frontend types derive from these models. |
| DB access | **Raw SQL via `sqlite3` (stdlib) + Pydantic models at the boundary** | Lean, debuggable, no ORM tax. Schemas defined once in `contracts.md` and code-mirrored as Pydantic models. SQLAlchemy is the conservative alternative if hand-rolled migrations / relationships become painful — revisit if needed. |
| Logging | **structlog** | Structured logging is non-negotiable for audit-trail accuracy. JSON output by default; trace_id integrates cleanly through context binding. |
| OAuth library | **authlib** | Most flexible OAuth 2.0 library for Python. Handles Google Workspace, Microsoft Graph, Slack flows. |
| Signing | **`cryptography`** | Stdlib-adjacent, well-maintained, supports Ed25519 for routine channel envelope signing per architecture decisions. |
| Test framework | **pytest + pytest-asyncio** | Universal. Add `pytest-httpx` for adapter testing (mock HTTP at the httpx layer). |
| Linting / formatting | **ruff** | Replaces black + flake8 + isort. Fast. |
| Type checking | **mypy** (strict mode in CI) | Type errors fail CI. |
| Docker base image | **`python:3.12-slim-bookworm`** | Smaller image footprint, current Debian, security-patched regularly. |

### 3.2 — Frontend stack (React)

| Choice | Lock | Rationale |
|---|---|---|
| Build tool | **Vite** | Fast dev server, no SSR complexity (internal dashboard doesn't need Next.js). |
| Language | **TypeScript** | Non-negotiable for React in 2026. Catches a class of bugs that would otherwise surface in client testing. |
| Component library | **shadcn/ui** | Copy-paste components on Radix primitives + Tailwind. High polish, you own the code (no library updates), industry standard in 2025-2026. |
| CSS | **Tailwind v4** | Required by shadcn/ui. v4 is faster and simpler than v3 (no postcss config needed). |
| Routing | **React Router v6** | Mature, well-documented. TanStack Router is newer with better TS inference but less battle-tested. |
| Server state | **TanStack Query** | Handles caching, refetching, WebSocket invalidation, optimistic updates. Pairs with the generated typed API client. |
| Client state | **Zustand** | Lightweight alternative to Redux. Used only where genuinely shared client state is needed. |
| Forms | **React Hook Form + Zod** | Form state + schema validation. The knob editor is the most complex form; this combo handles it cleanly. Zod schemas can be derived from the OpenAPI-generated types. |
| Charts / viz | **Recharts** | Best React charting lib for dashboards. Used by approval queue stats, criteria-drift display, audit log timeline. |
| Real-time | **Native WebSocket API** wrapped via TanStack Query subscription pattern | FastAPI native WebSocket support. Avoids socket.io overhead. |
| Icon set | **lucide-react** | Clean, tree-shakeable, ships with shadcn/ui by default. |
| Package manager | **pnpm** | Faster and stricter than npm. More stable than bun for production use. |
| API codegen | **`@hey-api/openapi-ts`** | Generates types AND typed fetch client from FastAPI's OpenAPI spec. See 3.3 for full workflow. |
| Linting / formatting | **ESLint + Prettier + `@typescript-eslint`** | Standard config. |
| Frontend testing | **Vitest + React Testing Library + Playwright** (E2E) | Vitest for unit, RTL for component, Playwright for end-to-end happy-path verification. |

### 3.3 — API type-sync workflow (Pydantic ↔ TypeScript) — load-bearing operational constraint

This is the bridge between backend and frontend that the entire dashboard's reliability rests on. **It is an operational discipline, not just a tool.** Skipping or short-circuiting any of the rules below will silently break the type contract between layers and reintroduce the class of bugs the whole type system exists to prevent.

#### Mechanism

1. **FastAPI auto-generates an OpenAPI 3.1 spec** from Pydantic models. Served at `GET /openapi.json` automatically; no extra code required.
2. **`@hey-api/openapi-ts`** (frontend codegen tool) reads that spec and produces:
   - Matching TypeScript type definitions (`src/api/generated/types.gen.ts`)
   - A typed fetch client (`src/api/generated/services.gen.ts`) — each endpoint becomes a typed function
3. **TypeScript compiler enforces sync.** If the Pydantic model changes and the frontend isn't regenerated, the frontend either (a) breaks at compile time on stale types, or (b) breaks the CI verification step. Either way, the divergence cannot ship.

#### Setup

Backend (FastAPI gives this for free):

```python
# ota_dashboard_api/main.py
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Literal

class ApprovalDraft(BaseModel):
    id: str
    sender: str
    subject: str
    category: Literal["inquiry", "support", "urgent", "internal"]
    draft_body: str
    confidence: float

app = FastAPI()

@app.get("/api/approval-queue", response_model=list[ApprovalDraft])
async def get_approval_queue() -> list[ApprovalDraft]: ...
```

Frontend (`ota_dashboard_web/package.json`):

```json
{
  "scripts": {
    "gen-api": "openapi-ts -i http://localhost:8000/openapi.json -o src/api/generated -c @hey-api/client-fetch"
  }
}
```

Running `pnpm gen-api` produces:

```typescript
// src/api/generated/types.gen.ts  (DO NOT EDIT)
export type ApprovalDraft = {
  id: string;
  sender: string;
  subject: string;
  category: 'inquiry' | 'support' | 'urgent' | 'internal';
  draft_body: string;
  confidence: number;
};

// src/api/generated/services.gen.ts  (DO NOT EDIT)
export const getApprovalQueue = (): Promise<ApprovalDraft[]> => { ... }
```

Usage in React components, via TanStack Query:

```typescript
import { useQuery } from '@tanstack/react-query';
import { getApprovalQueue } from '@/api/generated';

function ApprovalQueue() {
  const { data, isLoading } = useQuery({
    queryKey: ['approval-queue'],
    queryFn: getApprovalQueue,
  });
  // `data` is typed `ApprovalDraft[] | undefined` automatically.
  // Rename `confidence` to `score` on the backend → every reference
  // in this component becomes a TypeScript error until updated.
}
```

#### Discipline rules — non-negotiable

Three rules. Skipping any of them silently breaks the contract:

1. **Never hand-edit generated files.** Anything under `src/api/generated/` is auto-generated and overwritten on next codegen. Enforce via `.gitattributes`:
   ```
   src/api/generated/** linguist-generated=true
   src/api/generated/** -diff
   ```
   And via a CI check that fails if generated files are edited outside of `gen-api` runs.

2. **Regenerate before every commit that touches API shape.** Enforced via pre-commit hook:
   ```yaml
   # .pre-commit-config.yaml
   - repo: local
     hooks:
       - id: gen-api
         entry: bash -c 'cd ota_dashboard_web && pnpm gen-api && git diff --exit-code src/api/generated'
         language: system
         pass_filenames: false
   ```
   The hook fails the commit if regen produces a diff against the committed generated files — i.e., if you changed a Pydantic model but forgot to regen.

3. **CI verifies generated files match what's committed.** GitHub Actions step:
   ```yaml
   - name: Verify generated API types are in sync
     run: |
       cd ota_dashboard_web
       pnpm gen-api
       git diff --exit-code src/api/generated
   ```
   Final safety net. Even if the pre-commit hook is bypassed, CI catches the divergence before merge.

#### Known gotchas to design around

- **Discriminated unions** — use Pydantic's standard `Field(discriminator=...)` pattern. Non-standard tag fields can break codegen.
- **`Annotated[...]` with complex validators** sometimes generates weird types in OpenAPI output. Test codegen early on a representative slice of the API; don't wait until the schema is complete.
- **Recursive Pydantic models** (A → B → A) generate verbose intermediate TypeScript types. Avoid deeply recursive shapes in API contracts where possible; flatten at the boundary.
- **`datetime` fields serialize to ISO-8601 strings** — TypeScript receives them as `string`. Add a thin wrapper helper if components need `Date` objects.
- **`bytes` and `Decimal` types** also serialize as strings. Document the boundary type-translation table once and reuse.

#### Why this is operational, not just technical

Every other contract sync mechanism in the framework (capability vocabulary version pinning, adapter manifest validation, contracts.md as source of truth) has this same shape: *generate from a single source of truth, fail loudly when out of sync, never tolerate manual editing of generated artifacts.* The Pydantic → TypeScript codegen is the same pattern applied to the dashboard. **Treat divergence here as a build break, never as a "we'll fix it later" item.**

The biggest operational win isn't the types — it's that **you cannot accidentally ship a frontend out of sync with the backend.** For a solo developer switching contexts between Python and TypeScript daily, this eliminates an entire class of debugging time.

### 3.4 — Vocabulary → Python codegen workflow (markdown ↔ Python) — load-bearing operational constraint

The second load-bearing codegen discipline alongside the OpenAPI workflow in 3.3. Same principle, different boundary: **the markdown vocabulary specs are the single source of truth; the Python runtime modules that adapters implement against and routines call into are generated from the spec.** Honors the architecture's "markdown-first for portability and inspectability" principle from day one.

#### Why this matters

Without codegen, every capability has two sources of truth:

1. `vocabulary/messaging.md` — the spec (verb signatures, type definitions, error taxonomy, metadata)
2. `ota_connect/_types/*.py` + `ota_connect/messaging/verbs.py` — the runtime Python (hand-written to mirror the spec)

Every change to a verb signature, every new field on a Ref type, every new error class has to be made in both places. Code review catches divergence sometimes; humans catch it sometimes; sometimes it ships broken. **This is exactly the operational risk Section 3.3 exists to eliminate at the Pydantic ↔ TypeScript boundary.** It applies with equal force here.

#### Mechanism

The vocabulary spec was designed to be codegen-ready. Every verb section in `vocabulary/messaging.md` and `vocabulary/email.md` has:

- A YAML metadata block (`idempotency`, `required_scopes`, `destructive`)
- A Python signature in a fenced ```python code block
- Predictable section hierarchy under `## Verbs` → `### <verb_name>`

And `vocabulary/_types.md` has dataclass definitions in fenced Python blocks that are already valid Python source.

The codegen tool parses each markdown file and produces:

- **`ota_connect/_types/*.py`** — dataclass definitions extracted from `vocabulary/_types.md`, split by domain (identity, messaging, email, content, enums, errors, pagination)
- **`ota_connect/{capability}/verbs.py`** — function stubs from per-capability spec, each decorated with the metadata block and wired to call into the capability's `dispatch.py` (which remains hand-written, since dispatch logic is not in the spec)

#### Tool

`scripts/gen_vocab_stubs.py` — Python script, ~200–400 lines, depends only on `pyyaml` and stdlib. Lives in the repo, runs locally and in CI.

Conceptual structure:

```python
# scripts/gen_vocab_stubs.py

def parse_capability(spec_path: Path) -> dict:
    """Extract frontmatter + verb sections + Python signatures + metadata blocks."""

def generate_verbs_module(capability: str, verbs: list[dict]) -> str:
    """Render Python module with @verb(...) decorators and dispatch wiring."""

def generate_types_module(types_md: Path) -> dict[str, str]:
    """Extract dataclass blocks from _types.md, group into output modules."""

def main():
    for spec in Path("vocabulary").glob("*.md"):
        if spec.name.startswith("_"):
            continue  # skip _types.md, _roster.md, _template.md
        capability_name = spec.stem
        verbs = parse_capability(spec)
        write_module(f"ota_connect/{capability_name}/verbs.py", 
                     generate_verbs_module(capability_name, verbs))
    write_modules_from_types_md(Path("vocabulary/_types.md"), 
                                output_dir="ota_connect/_types/")
```

Run via `just gen-vocab` or `python scripts/gen_vocab_stubs.py`.

#### Generated module shape (illustrative)

`ota_connect/messaging/verbs.py` (auto-generated):

```python
"""Auto-generated from vocabulary/messaging.md — do not edit."""

from ota_connect._types import (
    IdentityRef, MessageRef, ThreadRef, ChannelRef, 
    Block, Attachment, Importance,
)
from ota_connect.messaging.dispatch import dispatch
from ota_core.policy import verb

@verb(
    idempotency="best_effort",
    required_scopes=["messaging:send"],
    destructive=False,
)
def send_message(
    target: ChannelRef | IdentityRef,
    content: str | list[Block],
    *,
    thread_ref: ThreadRef | None = None,
    attachments: list[Attachment] | None = None,
    importance: Importance = "normal",
) -> MessageRef:
    return dispatch("send_message", **locals())

# ... edit_message, delete_message, read_thread, list_recent_messages
```

`ota_connect/_types/messaging.py` (auto-generated):

```python
"""Auto-generated from vocabulary/_types.md — do not edit."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ota_connect._types.identity import IdentityRef

@dataclass(frozen=True)
class MessageRef:
    id: str
    channel: "ChannelRef"
    sent_at: datetime
    permalink: str | None
    adapter: str

@dataclass(frozen=True)
class ThreadRef:
    id: str
    channel: "ChannelRef"
    started_at: datetime
    adapter: str

# ... ChannelRef, etc.
```

#### Discipline rules — non-negotiable (mirror Section 3.3)

1. **Never hand-edit generated files.** Mark with `# AUTO-GENERATED — DO NOT EDIT` header. Enforce via `.gitattributes`:
   ```
   ota_connect/_types/**.py linguist-generated=true
   ota_connect/_types/**.py -diff
   ota_connect/messaging/verbs.py linguist-generated=true
   ota_connect/messaging/verbs.py -diff
   ota_connect/email/verbs.py linguist-generated=true
   ota_connect/email/verbs.py -diff
   ```
   And a CI check that fails on edits made outside `gen-vocab` runs.

2. **Regenerate before every commit that touches the vocabulary spec.** Pre-commit hook:
   ```yaml
   # .pre-commit-config.yaml
   - repo: local
     hooks:
       - id: gen-vocab
         entry: python scripts/gen_vocab_stubs.py
         language: python
         files: ^vocabulary/.*\.md$
         pass_filenames: false
       - id: gen-vocab-diff-check
         entry: bash -c 'git diff --exit-code ota_connect/_types/ ota_connect/messaging/verbs.py ota_connect/email/verbs.py'
         language: system
         pass_filenames: false
   ```

3. **CI verifies generated files match what's committed.** GitHub Actions step:
   ```yaml
   - name: Verify vocabulary-generated Python is in sync
     run: |
       python scripts/gen_vocab_stubs.py
       git diff --exit-code ota_connect/_types/ ota_connect/messaging/verbs.py ota_connect/email/verbs.py
   ```

#### What stays hand-written

Codegen targets only what's mechanically derivable from the spec. The following remain hand-written and live alongside the generated code:

- **`ota_connect/{capability}/dispatch.py`** — binding resolution, adapter invocation, error normalization, audit emission. Spec doesn't describe this; it's runtime mechanics.
- **`ota_connect/adapters/*/adapter.py`** — adapters implement the verbs against concrete tools. The vocabulary defines the contract; adapters provide the implementation.
- **`ota_connect/binding/`** — binding resolver logic.

#### Known gotchas

- **Markdown parser brittleness.** The spec format is precise; codegen assumes the format we locked. If future capability authors deviate (different heading levels, missing metadata blocks, malformed Python in code fences), codegen fails loudly. That's a feature — fail loud, fix the spec.
- **Forward references in dataclasses** (e.g., `MessageRef` references `ChannelRef` which is defined later in `_types.md`) need quoted type annotations or careful module ordering. Handle this in the codegen by emitting forward references as string annotations.
- **Vocabulary spec changes that require manual adapter updates** — adding a new verb means every adapter declaring satisfaction of that capability must implement the new verb. Codegen surfaces the gap (adapters fail to load with "missing verb implementation") but cannot generate the implementation itself.

#### Why this is operational, not just technical

The same logic from Section 3.3 applies: every contract-sync mechanism in the framework follows the pattern *generate from a single source of truth, fail loudly when out of sync, never tolerate manual editing of generated artifacts.* The Pydantic ↔ TypeScript boundary uses this pattern for dashboard types. The vocabulary ↔ Python boundary uses it for the capability runtime. Both must be in place from day one or the "markdown-first" architectural decision is aspirational rather than enforced.

### 3.5 — Carry-over locks from Section 2.4

| Decision | Lock | Note |
|---|---|---|
| Dashboard real-time mechanism | **WebSocket** (FastAPI native) | Sub-5s approval queue updates per acceptance criteria. |
| Snapshot storage location | **Local-only for v0.1** | Local filesystem path; configurable remote (S3, etc.) deferred to v0.2 with multi-mode deployment. |
| Onboarding form factor | **Two-part: operator bootstrap CLI + client web wizard** | Mode 2 split: operator runs CLI over SSH to bootstrap the VPS install; client uses web onboarding flow in the dashboard for OAuth + initial config. Both are v0.1 scope. See Section 6 for full deployment lifecycle. |
| Identity registry sync model | **Manual `people.md` editing for v0.1** | <20 identities per client expected. Directory sync (Google Workspace, Slack) deferred to v0.2. |

### 3.6 — Implications for Section 4 (Repo Structure)

Choosing React + separate frontend app means the repo needs:

- Separate `ota_dashboard_web/` directory with its own `package.json`, `pnpm-lock.yaml`, `tsconfig.json`, `vite.config.ts`
- Separate frontend CI pipeline (eslint, tsc, vitest, Playwright) alongside the Python CI (ruff, mypy, pytest)
- A build step that produces static assets, served by FastAPI as static files in production (Mode 1 single-container deployment)
- A `.gitattributes` config to mark generated files
- A `.pre-commit-config.yaml` enforcing the codegen sync rules from 3.3

Full layout locked in Section 4.

### 3.7 — Open overrides (defaults stand unless you say otherwise)

- **DB access** stayed at raw SQL + Pydantic. If you'd prefer SQLAlchemy for migrations/relationships safety net, say so before Layer 1 starts.
- **MUI vs shadcn/ui** if you have prior MUI experience and want the more conventional component library — say so. shadcn/ui is the recommended pick but MUI is a valid override.
- **Redux Toolkit vs Zustand** if you have prior Redux preference — Zustand is the recommended pick for OTA's scope.
- **Plotly vs Recharts** if you need 3D viz or scientific charting — Recharts is the recommended pick for dashboard-style 2D charts.

---

---

## Section 4 — Repo Structure

Monorepo layout for v0.1. Single git repository, multiple Python packages declared in one `pyproject.toml`, plus the React frontend as a sibling subdirectory with its own `package.json`. Solo dev + tightly coupled changes between layers makes this the right shape; if/when the codebase grows past one engineer or needs independent release cadences, split into multiple repos.

### 4.1 — Top-level layout

```
ota/
├── README.md                              # Quick start, links to docs/
├── CONTRIBUTING.md                        # Dev setup, conventions, codegen workflow
├── LICENSE                                # Internal-use license bundled with deliveries
├── pyproject.toml                         # Python project + all packages + dev deps
├── .python-version                        # 3.12
├── .pre-commit-config.yaml                # Pre-commit hooks (incl. OpenAPI codegen sync)
├── .gitattributes                         # Marks generated files (frontend codegen output)
├── .gitignore                             # Standard + .dev_state/, __pycache__/, dist/, node_modules/
├── mypy.ini                               # Strict mode config
├── ruff.toml                              # Lint + format config (or in pyproject.toml)
├── Dockerfile                             # Multi-stage build (frontend → static assets, then Python)
├── docker-compose.dev.yml                 # Dev convenience (FastAPI + Vite dev server)
│
├── ota_core/                              # Framework runtime (Python)
│   ├── __init__.py
│   ├── conductor/                         # Intent routing (direct routing for v0.1)
│   ├── branches/                          # Role-specialized sub-agents (productivity only for v0.1)
│   ├── systems/                           # Routine execution engine
│   ├── automation/                        # Scheduler + event hooks
│   ├── policy/                            # L0a (prompts) + L0b (Python policy enforcement)
│   ├── storage/                           # SQLite + markdown projection
│   ├── audit/                             # AuditSink impl (JSONL)
│   ├── observability/                     # ObservabilitySink impl (file/stdout for v0.1)
│   ├── identity/                          # IdentityProvider seam (local people.md backed)
│   ├── secrets/                           # SecretsProvider seam (encrypted local file)
│   ├── llm/                               # LLMProvider seam (Anthropic impl)
│   ├── routine_source/                    # RoutineSource seam (filesystem for v0.1)
│   ├── integration_source/                # IntegrationSource seam (filesystem for v0.1)
│   ├── http/                              # Shared httpx wrapper: retry / backoff / rate-limit / allowlist
│   ├── oauth/                             # Shared OAuth 2.0 helper: auth URL gen, callback, token refresh
│   ├── network_posture/                   # Outbound-only allowlist enforcement
│   ├── contracts/                         # Pydantic models for Contracts A–E
│   └── trace/                             # trace_id propagation (OTel-standard)
│
├── ota_connect/                           # Capability layer (Python)
│   ├── __init__.py
│   ├── messaging/                         # ota_connect.messaging.* verbs
│   │   ├── __init__.py
│   │   ├── verbs.py                       # AUTO-GENERATED from vocabulary/messaging.md (Section 3.4)
│   │   └── dispatch.py                    # Hand-written: binding resolution + adapter dispatch
│   ├── email/                             # ota_connect.email.* verbs
│   │   ├── __init__.py
│   │   ├── verbs.py                       # AUTO-GENERATED from vocabulary/email.md (Section 3.4)
│   │   └── dispatch.py                    # Hand-written: binding resolution + adapter dispatch
│   ├── _types/                            # AUTO-GENERATED from vocabulary/_types.md (Section 3.4)
│   │   ├── __init__.py
│   │   ├── identity.py                    # IdentityRef
│   │   ├── messaging.py                   # MessageRef, ThreadRef, ChannelRef
│   │   ├── email.py                       # EmailRef, EmailThreadRef, DraftRef
│   │   ├── content.py                     # Block, Action, FileRef, Attachment
│   │   ├── enums.py                       # DeliveryStatus, Importance
│   │   ├── errors.py                      # OTAConnectError hierarchy
│   │   └── pagination.py                  # Cursor, Page[T]
│   ├── adapters/                          # Concrete integration adapters
│   │   ├── __init__.py
│   │   ├── slack_socket/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py                 # Implements messaging.* verbs
│   │   │   ├── manifest.yaml              # Declares satisfied capabilities + versions
│   │   │   ├── oauth.py                   # OAuth flow handler
│   │   │   └── events.py                  # Action callback ingest via Socket Mode
│   │   └── gmail_oauth/
│   │       ├── __init__.py
│   │       ├── adapter.py                 # Implements email.* verbs
│   │       ├── manifest.yaml
│   │       ├── oauth.py
│   │       └── events.py                  # Inbound event polling (bounces, replies)
│   ├── binding/                           # Binding resolver (longest-prefix match)
│   │   ├── __init__.py
│   │   ├── resolver.py
│   │   └── validator.py                   # Install-time validation
│   └── pagination.py                      # iter_all() framework primitive
│
├── ota_routines/                          # Bundled routines
│   ├── __init__.py
│   └── email_triage/
│       ├── routine.md                     # Routine spec (markdown, source of truth)
│       ├── config.schema.yaml             # Knob schema (JSON Schema)
│       ├── helpers.py                     # Trust counter, drift detector, /why handler
│       ├── templates/                     # Per-category reply templates
│       │   ├── inquiry.md
│       │   ├── support.md
│       │   ├── urgent.md
│       │   └── ...
│       └── prompts/                       # LLM prompt templates
│           ├── classifier.md
│           └── drafter.md
│
├── ota_dashboard_api/                     # FastAPI backend (JSON API for the dashboard)
│   ├── __init__.py
│   ├── main.py                            # FastAPI app entry point
│   ├── routes/                            # Endpoint handlers
│   │   ├── approval_queue.py
│   │   ├── audit.py
│   │   ├── why.py
│   │   ├── knobs.py
│   │   ├── fleet.py
│   │   ├── onboarding.py
│   │   └── ws.py                          # WebSocket endpoints
│   ├── models.py                          # Pydantic response models (OpenAPI codegen source)
│   └── auth.py                            # Operator auth (simple bearer token for v0.1)
│
├── ota_dashboard_web/                     # React frontend (separate package, sibling)
│   ├── package.json                       # pnpm-managed
│   ├── pnpm-lock.yaml
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── eslint.config.js
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── routes/                        # Page-level components (React Router)
│   │   │   ├── ApprovalQueue.tsx
│   │   │   ├── AuditLog.tsx
│   │   │   ├── Why.tsx
│   │   │   ├── KnobEditor.tsx
│   │   │   └── FleetStatus.tsx
│   │   ├── components/                    # Shared components
│   │   │   ├── ui/                        # shadcn/ui components (copy-paste, owned)
│   │   │   └── …
│   │   ├── hooks/                         # Custom hooks (TanStack Query wrappers)
│   │   ├── lib/                           # Utilities, WebSocket helpers
│   │   ├── stores/                        # Zustand stores (client state)
│   │   └── api/
│   │       └── generated/                 # @hey-api/openapi-ts output — DO NOT EDIT
│   ├── tests/
│   │   ├── unit/                          # Vitest + React Testing Library
│   │   └── e2e/                           # Playwright
│   └── public/                            # Static assets (favicon, etc.)
│
├── vocabulary/                            # Capability vocabulary specs (markdown, source of truth)
│   ├── _types.md
│   ├── _roster.md
│   ├── _template.md                       # Spec template for future capabilities
│   ├── messaging.md
│   └── email.md
│
├── tests/                                 # Python tests, mirrors source structure
│   ├── ota_core/
│   ├── ota_connect/
│   │   └── binding/
│   ├── adapters/
│   │   ├── slack_socket/
│   │   └── gmail_oauth/
│   ├── routines/
│   │   └── email_triage/
│   └── vocabulary/                        # Conformance tests (per-verb, run against every adapter)
│       ├── messaging/
│       │   ├── send_message/
│       │   │   ├── test_send_to_user.py
│       │   │   ├── test_thread_reply.py
│       │   │   ├── test_attachment_degradation.py
│       │   │   └── fixtures/
│       │   ├── edit_message/
│       │   ├── delete_message/
│       │   ├── read_thread/
│       │   └── list_recent_messages/
│       └── email/
│           ├── send_email/
│           ├── create_draft/
│           ├── send_draft/
│           ├── delete_email/
│           ├── list_mailbox/
│           ├── read_email_thread/
│           ├── modify_email_labels/
│           ├── mark_read/
│           └── mark_unread/
│
├── scripts/                               # Codegen, dev tooling, maintenance scripts
│   ├── gen_vocab_stubs.py                 # v0.1 — Generate Python stubs from vocabulary/*.md (Section 3.4)
│   ├── run_dev.sh                         # Launch FastAPI + Vite dev server together
│   ├── verify_contracts.py                # Cross-check Pydantic models match contracts.md schemas
│   └── new_adapter.py                     # (future) Scaffold a new adapter directory
│
├── docs/                                  # Source-of-truth documentation
│   ├── architecture.md                    # Migrated from project workspace
│   ├── contracts.md                       # Migrated from project workspace
│   ├── build-plan-v0.md                   # This file — migrated from project workspace
│   ├── pending-architecture-updates.md    # Until merged into architecture.md
│   └── adr/                               # Architectural Decision Records (going forward)
│       └── 0001-template.md
│
├── examples/                              # Example client configs (for docs + onboarding)
│   └── client_config/
│       ├── bindings.md.example
│       ├── people.md.example
│       └── routine_knobs.yaml.example
│
├── infra/                                 # Deployment artifacts
│   ├── systemd/
│   │   └── ota.service                    # systemd unit for Linux VPS auto-start + restart
│   ├── install/
│   │   ├── mode2_install.sh               # Mode 2 (VPS) bootstrap install script (Ubuntu 22.04/24.04)
│   │   ├── Caddyfile                      # Reverse proxy + Let's Encrypt config
│   │   └── README.md                      # Install steps, VPS sizing, DNS setup
│   ├── docs/
│   │   ├── oauth_setup_google.md          # Per-client Google Cloud project + Gmail OAuth credential walkthrough
│   │   └── oauth_setup_slack.md           # Per-client Slack app + OAuth credential walkthrough
│   └── seeds/                             # Adapter test fixtures for pre-install acceptance check
│       ├── slack_workspace_fixture.json
│       └── gmail_fixture.mbox
│
└── .github/
    └── workflows/
        ├── python.yml                     # Ruff + mypy + pytest
        ├── frontend.yml                   # ESLint + tsc + Vitest + Playwright + build
        └── integration.yml                # Docker build + smoke E2E
```

### 4.2 — Package boundaries and dependency direction

Dependency rule: arrows point downward only. No cycles, no upward references.

```
              ota_dashboard_api
                     │
                     ▼
       ┌───── ota_routines ────┐
       │                       │
       ▼                       ▼
  ota_connect ──────► ota_core
       │                       │
       ▼                       ▼
  ota_connect/adapters/*  (no internal deps below ota_core)
```

- **`ota_core`** is the lowest layer. Depends only on third-party libraries (httpx, structlog, pydantic, etc.). Defines the seams; provides storage, audit, observability, identity, secrets, LLM client, scheduling, policy enforcement. **Never imports from ota_connect, ota_routines, ota_dashboard_api, or adapters.**
- **`ota_connect`** depends on `ota_core` for runtime services (storage, audit, identity, secrets). Implements the capability vocabulary as Python verbs. Houses adapters as sub-packages under `ota_connect/adapters/`.
- **`ota_connect/adapters/*`** — each adapter implements one or more capability interfaces. Adapters depend on `ota_connect` (for `_types`, error hierarchy, dispatch) and `ota_core` (for HTTP client, secrets, identity). Adapters never directly import each other.
- **`ota_routines/*`** — bundled routines. Each routine is a directory with markdown + Python helpers. Routines depend on `ota_connect` for capability calls and `ota_core` for routine engine integration. **Routines never import adapters directly** (that's the entire point of the capability layer).
- **`ota_dashboard_api`** depends on `ota_core` (state access, audit log query, fleet status), `ota_connect` (binding inspection, adapter status), and `ota_routines` (routine inspection, knob editing). Exposes JSON endpoints; never directly mutates framework state — goes through `ota_core` APIs.
- **`ota_dashboard_web`** is a separate package with its own dependency graph. Communicates with `ota_dashboard_api` over HTTP/WebSocket only. **Never directly accesses Python code or filesystem.**

### 4.3 — Generated artifacts and source-of-truth mapping

Every generated artifact is marked, has a clear source, and is gitignore-aware where appropriate.

| Generated artifact | Source of truth | Tool | Edit policy |
|---|---|---|---|
| `ota_dashboard_web/src/api/generated/types.gen.ts` | Pydantic models in `ota_dashboard_api/models.py` via FastAPI's `/openapi.json` | `@hey-api/openapi-ts` | **Never edit by hand.** Marked `linguist-generated=true` in `.gitattributes`. Pre-commit hook + CI verify in-sync. Section 3.3 workflow. |
| `ota_dashboard_web/src/api/generated/services.gen.ts` | Same as above | Same | Same. |
| `ota_connect/_types/*.py` | `vocabulary/_types.md` | `scripts/gen_vocab_stubs.py` | **Never edit by hand.** Auto-generated for v0.1 per Section 3.4. Marked `linguist-generated=true`. Pre-commit + CI verify in-sync. |
| `ota_connect/messaging/verbs.py` | `vocabulary/messaging.md` | `scripts/gen_vocab_stubs.py` | **Never edit by hand.** Auto-generated for v0.1 per Section 3.4. Function bodies are stubs that call `dispatch(...)`; dispatch logic itself lives in hand-written `ota_connect/messaging/dispatch.py`. |
| `ota_connect/email/verbs.py` | `vocabulary/email.md` | `scripts/gen_vocab_stubs.py` | **Never edit by hand.** Same pattern as messaging. |
| OpenAPI spec at `/openapi.json` | FastAPI introspection of Pydantic models | FastAPI built-in | Served at runtime, never committed to repo. |

**Two operational rules, both load-bearing:**

1. Any change to a Pydantic model in `ota_dashboard_api/models.py` MUST be followed by `pnpm gen-api` in `ota_dashboard_web/`. Pre-commit hook from Section 3.3 enforces; CI verifies.
2. Any change to a `vocabulary/*.md` file MUST be followed by `python scripts/gen_vocab_stubs.py`. Pre-commit hook from Section 3.4 enforces; CI verifies.

Both code-gen disciplines exist to honor the architectural decision that **markdown specs are the source of truth, not duplicate documentation of the Python.**

### 4.4 — Runtime data vs source code

The repo contains **code, vocabulary specs, bundled routines, example configs, infrastructure scripts**. It does NOT contain runtime data.

**Runtime data lives outside the repo at a configurable data directory.** Defaults:

| Mode | Data directory |
|---|---|
| Dev (running from repo on dev machine) | `./.dev_state/` (gitignored) |
| Mode 2 (VPS in client's cloud account) — v0.1 default | `/var/lib/ota/state/` |
| Mode 3 (Managed by Omar in isolated container) — v0.3+ | Per-tenant isolated path under operator's infrastructure |

**Mode 1 (Local install) explicitly rejected for v0.1 and beyond.** Laptops sleep; paying clients with always-on email triage need always-on runtime. See Section 6.3.

Contents of the data directory:

```
<data_dir>/
├── state.db                               # Main SQLite database (WAL mode)
├── audit/
│   └── 2026-05.jsonl                      # Audit log, rotated monthly
├── client_config/                         # Per-client configuration (operator-edited)
│   ├── bindings.md                        # Capability → adapter bindings
│   ├── people.md                          # Identity registry (handle → adapter IDs)
│   └── routine_knobs/                     # Per-routine knob overrides
│       └── email_triage.yaml
├── secrets/                               # Encrypted secrets store (SecretsProvider)
│   └── secrets.age                        # Or sops-encrypted
├── routines/                              # Installed routines (copied from ota_routines/ at install)
│   └── email_triage/
├── memory/                                # Markdown projections of L4 state
│   └── relationships.md
└── backups/                               # Snapshot rotation (per Section 2.2 acceptance criteria)
    ├── daily/
    ├── weekly/
    └── monthly/
```

The bundled routines under `ota_routines/` in the repo are *templates* — at install time, the operator's selected routines are copied into the data directory's `routines/` folder, where their knob configs live alongside. Updating a routine via the private channel (v0.2) overwrites the data-directory copy after migration; the repo version is the canonical reference shipped with the framework.

### 4.5 — Migration from project workspace into repo

The current project workspace at `/Users/osoto/Documents/Claude/Projects/OTA Ideation/` contains the source-of-truth documents that need to move into the repo as it gets initialized:

| Current location | Repo destination | Notes |
|---|---|---|
| `architecture.md` | `docs/architecture.md` | Source of truth. Update path references elsewhere. |
| `contracts.md` | `docs/contracts.md` | Source of truth. |
| `vocabulary/_types.md` | `vocabulary/_types.md` | Vocabulary specs live at repo root, not under `docs/`, so they're discoverable as a peer of code. |
| `vocabulary/messaging.md` | `vocabulary/messaging.md` | Same. |
| `vocabulary/email.md` | `vocabulary/email.md` | Same. |
| `vocabulary/_roster.md` | `vocabulary/_roster.md` | Same. |
| `build-plan-v0.md` | `docs/build-plan-v0.md` | Active planning doc; lives in docs/. |
| `pending-architecture-updates.md` | `docs/pending-architecture-updates.md` | Until merged into architecture.md (Section 6 work). |
| `marketing.md` | **Stays in project workspace** | Planning artifact, not source-of-truth code documentation. Could optionally move to `docs/planning/marketing.md` if you want everything in one place — operator's call. |

The `agentikey-service-fit` skill outputs, prior research findings, and conversation transcripts stay in the project workspace as research notes. The repo is for the deliverable.

### 4.6 — pyproject.toml and package management

**Python:** single `pyproject.toml` at repo root, declaring all four Python packages (`ota_core`, `ota_connect`, `ota_routines`, `ota_dashboard_api`) under `[tool.setuptools.packages.find]`. Single virtualenv, single dependency graph. If/when packages need independent versioning, split into multiple pyproject.toml workspace files.

**Frontend:** single `package.json` at `ota_dashboard_web/`, pnpm-managed. No frontend monorepo tooling (Turborepo, Nx) — premature for one frontend package.

**Workspace coordination:** a single top-level `Makefile` or `justfile` (pick one; lean justfile for clarity) provides convenience commands:

```
just dev          # Run FastAPI + Vite dev server together
just test         # Run all Python + frontend tests
just lint         # Ruff + ESLint
just gen-api      # Regenerate frontend types from OpenAPI
just build        # Build Docker image
just verify       # Pre-commit checks (lint + types + codegen-in-sync)
```

### 4.7 — Open overrides

Defaults stand unless you say otherwise:

- **Single pyproject.toml vs per-package** — single is recommended for v0.1. Override if you want strict package boundaries enforced from the start (more setup overhead).
- **Adapters location** — `ota_connect/adapters/*` (sub-package) recommended. Alternative: top-level `ota_adapters/` directory if you want adapters discoverable independently. Either works.
- **`docs/` vs root-level docs** — putting architecture.md, contracts.md, build-plan-v0.md in `docs/` is recommended. Alternative: keep them at repo root if you prefer fewer levels. Repo-root visibility wins; `docs/` keeps the root tree cleaner.
- **`vocabulary/` location** — at repo root (peer of `docs/` and `ota_core/`) recommended, since it's both documentation and a runtime artifact (referenced by codegen scripts). Alternative: under `docs/vocabulary/`. Repo-root recommended for discoverability.
- **`Makefile` vs `justfile`** — `justfile` recommended (simpler syntax, cross-platform). Override if you prefer Make.
- **Backup directory location** — inside the data directory is recommended (alongside the data it backs up). Alternative: separate backup mount point. For v0.1 Mode 1 single laptop, inside-data-dir is simpler.

---

---

## Section 5 — Build Sequencing Plan

Build is organized into six **phases** rather than calendar days. Each phase has clear internal sequencing, parallel work streams where possible, hand-off criteria to the next phase, and a tracer-bullet milestone proving the phase actually works (not just "code is written").

**Sequencing principle:** vertical-slice tracer bullets first, breadth-fill second. The fastest way to surface architectural defects is to push *one thing* end-to-end through every layer before any layer is "complete." Once the tracer bullet works, you parallelize breadth-fill across the layers it already covers.

### 5.1 — Phase 0: Pre-flight (DONE)

Tech stack locked (Section 3), repo structure locked (Section 4). No code yet. Entry condition for Phase 1: all locks from Sections 3 and 4 confirmed; any overrides applied.

### 5.2 — Phase 1: Foundation

**Goal:** repo skeleton boots, codegen produces valid Python from vocabulary specs, CI passes on an empty project.

**Internal sequencing:**

| # | Work package | Depends on | Notes |
|---|---|---|---|
| 1.1 | Initialize repo: `pyproject.toml`, `.python-version`, `.gitignore`, `.gitattributes`, package skeletons under `ota_core/`, `ota_connect/`, `ota_routines/`, `ota_dashboard_api/`, `vocabulary/` | — | Files copied / migrated from project workspace per Section 4.5 |
| 1.2 | Migrate source-of-truth docs into repo: `docs/architecture.md`, `docs/contracts.md`, `docs/build-plan-v0.md`, `docs/pending-architecture-updates.md`, `vocabulary/*.md` | 1.1 | One-time migration. Update path references in chat / future sessions. |
| 1.3 | CI scaffold: GitHub Actions for Python (ruff + mypy + pytest) on `.github/workflows/python.yml` | 1.1 | Running CI from day one catches drift early. |
| 1.4 | Pydantic models for all five Contracts (A–E) under `ota_core/contracts/` | 1.1 | Hand-written. Source of truth for runtime contract validation. |
| 1.5 | Storage layer: SQLite WAL setup, schema files, basic CRUD wrappers, markdown projection helpers under `ota_core/storage/` | 1.4 | Schema-migration system can be minimal (manual SQL for v0.1; no migrations to manage yet). |
| 1.6 | HTTP client abstraction: shared httpx wrapper under `ota_core/http/` with retry / backoff / rate-limit primitives | 1.1 | Adapters depend on this. |
| 1.7 | LLM client abstraction: `LLMProvider` interface + Anthropic implementation under `ota_core/llm/` | 1.1, 1.6 | Capability negotiation hooks per Contract A. |
| 1.8 | **Vocabulary → Python codegen tool: `scripts/gen_vocab_stubs.py`** per Section 3.4 | 1.4 | Critical path — Layer 4 work depends on the generated Python existing. |
| 1.9 | Run codegen for the first time → generates `ota_connect/_types/*.py` and `ota_connect/{messaging,email}/verbs.py` | 1.8 | Verify generated code passes `ruff` + `mypy`. Commit generated files. |
| 1.10 | Pre-commit hook config (`.pre-commit-config.yaml`) with the two codegen-sync hooks (OpenAPI + vocabulary) | 1.8 | Section 3.3 + Section 3.4 rules. |
| 1.11 | `justfile` at root with the convenience commands from Section 4.6 | 1.1 | `just dev`, `just test`, `just gen-vocab`, etc. |

**Phase 1 milestone (tracer bullet):** `just test` runs the CI checks locally and passes on an otherwise empty project. `just gen-vocab` regenerates the Python from vocabulary specs idempotently (re-running produces no diff). CI is green on the initial commit.

**Phase 1 exit criteria:** all 11 work packages complete; CI green; generated artifacts committed and in-sync.

### 5.3 — Phase 2: Framework runtime + seams (parallel)

**Goal:** the framework can load a stub routine, schedule it, run it, and exercise the seams (identity resolution, secrets retrieval, audit emission, observability hooks). No real adapters yet — capability calls land in a mock adapter.

This phase has two parallel work streams. Streams A (runtime) and B (seams) share dependencies on Phase 1 but mostly proceed independently.

#### Stream A — Framework runtime (Layer 2)

| # | Work package | Depends on | Notes |
|---|---|---|---|
| 2A.1 | Trace ID propagation utilities under `ota_core/trace/` | Phase 1 | Foundational; used by everything in this stream. |
| 2A.2 | L0a system-prompt layer under `ota_core/policy/l0a.py` | Phase 1 | Soft rules in prompt template. Independent of routine engine. |
| 2A.3 | Automation layer (scheduler + event hooks) under `ota_core/automation/` | 2A.1, Phase 1 storage | APScheduler-based. Persistent scheduler state in SQLite. |
| 2A.4 | Routine engine skeleton under `ota_core/systems/` — loads routine markdown, parses frontmatter, instantiates with bound capabilities | 2A.1, 2A.3 | Heart of the framework. |
| 2A.5 | L0b Python policy layer under `ota_core/policy/l0b.py` — wraps every tool call with integration allowlists, budget enforcement, schema validation, gate enforcement | 2A.1, Phase 1 contracts | The safety net. |
| 2A.6 | Conductor (direct-routing minimal version) under `ota_core/conductor/` | 2A.4 | Single-routine MVP: hardcoded routing. Interface designed to support full semantic router in v0.2. |
| 2A.7 | Branches scaffold under `ota_core/branches/` — one branch (productivity) hardcoded | 2A.6 | Abstraction stub for future multi-branch. |
| 2A.8 | Systems primitive under `ota_core/systems/` — links Conductor → Branch → Routine | 2A.6, 2A.7 | The routine IS a system. |
| 2A.9 | Conductor load manifest resolver — pre-flight context resolution | 2A.6 | Declares context loads before routine runs; framework loads deterministically. |

#### Stream B — Seams (Layer 3)

| # | Work package | Depends on | Notes |
|---|---|---|---|
| 2B.1 | IdentityProvider seam under `ota_core/identity/` — loads `people.md`, resolves `IdentityRef` strings | Phase 1 | Local markdown-backed for v0.1. |
| 2B.2 | SecretsProvider seam under `ota_core/secrets/` — encrypted local file (age or sops) | Phase 1 | Virtual credential scoping per architecture. |
| 2B.3 | AuditSink seam under `ota_core/audit/` — append-only JSONL writer | Phase 1, 2A.1 | Local file for v0.1. |
| 2B.4 | ObservabilitySink seam under `ota_core/observability/` — stdout / file emission | Phase 1, 2A.1 | OTel-compatible structure; no collector for v0.1. |
| 2B.5 | RoutineSource seam under `ota_core/routine_source/` — loads routines from `<data_dir>/routines/` | Phase 1 | Filesystem-only for v0.1. |
| 2B.6 | IntegrationSource seam under `ota_core/integration_source/` — discovers adapters under `ota_connect/adapters/*` | Phase 1 | Filesystem-only for v0.1. |
| 2B.7 | NetworkPosture seam under `ota_core/network_posture/` — outbound-only enforcement, allowlist checked at every HTTP call | Phase 1, 1.6 | Wraps the HTTP client abstraction from Phase 1. |

**Phase 2 milestone (tracer bullet):** a hello-world routine (`ota_routines/hello/routine.md`) is loaded by the routine engine, runs on a manual trigger, makes one capability call to a mock adapter (built inline for this test), emits an audit event, and the AuditSink writes it to JSONL. End-to-end smoke test passes.

**Phase 2 exit criteria:** Streams A and B both complete; the tracer bullet runs; routine engine + automation can wake a routine on cron; L0b enforces a deliberately-broken call (e.g., schema mismatch) and refuses to dispatch it.

### 5.4 — Phase 3: Capability layer

**Goal:** the capability dispatch system resolves bindings, normalizes errors, dispatches to adapters, and validates manifests at install time. Mock adapters confirm the dispatch path; real adapters arrive in Phase 4.

**Internal sequencing:**

| # | Work package | Depends on | Notes |
|---|---|---|---|
| 3.1 | Adapter manifest schema (`adapter_manifest.yaml` JSON Schema) under `ota_connect/_schemas/` | Phase 1, 1.4 | Sub-contract of Contract D. |
| 3.2 | Adapter manifest loader under `ota_connect/binding/` — reads adapter directories, validates manifests, registers adapters | 3.1 | Loaded at install time and at framework startup. |
| 3.3 | Binding resolver under `ota_connect/binding/resolver.py` — longest-prefix-match implementation per Section 6 of architecture decisions | 3.2 | Resolves `(capability, verb)` → adapter. |
| 3.4 | Binding validator under `ota_connect/binding/validator.py` — install-time check that every required capability has a bound, credentialed, version-satisfying adapter | 3.3 | Fails install with clear error per architecture decisions. |
| 3.5 | Capability dispatch layer under `ota_connect/{messaging,email}/dispatch.py` — invokes adapter, applies L0b policy, handles errors, emits audit | 3.3, 2A.5, 2B.3 | Hand-written. Glues generated verbs to adapter implementations. |
| 3.6 | Error normalization decorator — wraps adapter calls, translates platform errors to `OTAConnectError` subclasses | 3.5, Phase 1 generated `_types/errors.py` | Decorator pattern around dispatch. |
| 3.7 | Pagination iterator `ota_connect.iter_all(verb, **args)` | 3.5 | Framework primitive; routines avoid manual cursor loops. |
| 3.8 | Action callback dispatch — receives normalized envelope from adapter, routes `integration.messaging.action_triggered` events to routine handlers | 3.5, 2B.3 | HITL gates depend on this. |
| 3.9 | Inbound email event loop — polling-based bounce / reply / delivery / auto-response handler | 3.5, 2B.3 | Polling only for v0.1 (no webhooks). |
| 3.10 | Two mock adapters (`mock_messaging`, `mock_email`) under `tests/fixtures/adapters/` for development | 3.2 | Used by Phase 4 dependent layers until real adapters land. |

**Phase 3 milestone (tracer bullet):** install a routine that requires `capabilities.messaging.send_dm`, configure bindings to point to `mock_messaging`, run the routine — the mock adapter receives the call, returns a `MessageRef`, audit log captures the dispatch with trace_id. Binding validation correctly rejects an install where a required capability has no bound adapter.

**Phase 3 exit criteria:** capability dispatch works end-to-end through mock adapters; install-time validation enforces missing-binding errors; error normalization correctly translates a deliberately-thrown adapter exception to `OTAConnectError`.

### 5.5 — Phase 4: Adapters + Routine + Dashboard (parallel streams)

**Goal:** real Slack and Gmail adapters; the `email_triage` routine runs end-to-end on real data; the operator dashboard is fully functional.

This is the biggest phase by effort, with three parallel work streams. They share dependencies on Phase 3 but proceed independently otherwise. Frontend (Stream C) blocks on backend (Stream C-back) for OpenAPI codegen, but most other items run in parallel.

#### Stream A — Adapters (Layer 5)

| # | Work package | Depends on | Notes |
|---|---|---|---|
| 4A.1 | OAuth 2.0 helper module under `ota_core/oauth/` — shared auth URL gen, callback handling, token refresh, secrets storage | Phase 3, 2B.2 | Used by both adapters. |
| 4A.2 | Adapter conformance test scaffolding under `tests/vocabulary/` — per-verb test harness that runs against any adapter claiming verb satisfaction | Phase 3 | Real coverage per Decision 3a, not skeleton. |
| 4A.3 | `slack_socket_adapter` — full implementation of all 5 `messaging.*` verbs + manifest + OAuth flow + Socket Mode event handling | 4A.1, 4A.2 | Parallel with 4A.4 once 4A.1 + 4A.2 land. |
| 4A.4 | `gmail_oauth_adapter` — full implementation of all 9 `email.*` verbs + manifest + OAuth flow + inbound polling for bounces / replies | 4A.1, 4A.2 | Parallel with 4A.3. |

#### Stream B — Routine: `email_triage` (Layer 6)

| # | Work package | Depends on | Notes |
|---|---|---|---|
| 4B.1 | Routine config schema (`email_triage/config.schema.yaml`) — JSON Schema with cross-field validation | Phase 3 | Validated at install time. |
| 4B.2 | Per-template state tracking — SQLite tables for trust counters, edit logs, processed-email dedup | Phase 1 storage | Per-`email_triage` instance. |
| 4B.3 | HITL gate primitives under `ota_core/policy/gates.py` — three approval modes (approve / tune-and-approve / approve-and-remember), per-routine similarity function, gate state persistence | Phase 3, 3.8 | Reused by future routines beyond v0.1. |
| 4B.4 | `email_triage/routine.md` — full routine spec with three-tier structure (Reader / Drafter / Auto) | 4B.1 | Authored against locked vocabulary. |
| 4B.5 | `email_triage/helpers.py` — dedup hashing, trust-promotion counter, criteria-drift detector, `/why` lookup handler | 4B.2 | Routine-side Python alongside the markdown. |
| 4B.6 | Per-category reply templates (`templates/inquiry.md`, etc.) and prompt templates (`prompts/classifier.md`, `prompts/drafter.md`) | 4B.4 | Authored content; revised across iteration with the first client. |
| 4B.7 | Trust-promotion auto-send wiring — 20-consecutive-un-edited threshold per template, demote on edit, operator opt-in per template | 4B.5, 4B.3 | Core differentiator. |
| 4B.8 | Criteria-drift detector — scheduled background check on processed/draft/skip ratio shifts | 4B.5, 2A.3 | Low-effort, high-value. |

#### Stream C — Operator dashboard (Layer 7)

Backend and frontend interleave; backend slightly leads because OpenAPI codegen feeds frontend types.

| # | Work package | Depends on | Notes |
|---|---|---|---|
| 4C.1 | Dashboard backend skeleton: FastAPI app, route structure, Pydantic response models under `ota_dashboard_api/models.py` | Phase 1, 1.4 | First pass models for approval queue, audit log, /why, knobs, fleet. |
| 4C.2 | Run `@hey-api/openapi-ts` for first time → generates frontend `src/api/generated/` types | 4C.1 | Triggers Section 3.3 enforcement (pre-commit + CI verification). |
| 4C.3 | Frontend skeleton: Vite + React + TypeScript + Tailwind v4 + shadcn/ui init under `ota_dashboard_web/`. App shell, navigation, route structure (React Router v6) | 4C.2 | Frontend CI scaffold: `.github/workflows/frontend.yml`. |
| 4C.4 | TanStack Query setup + WebSocket subscription helpers (`src/lib/ws.ts`) | 4C.3 | Real-time approval queue depends on this. |
| 4C.5 | Approval queue UI — list view, expand-to-detail, approve / edit / skip actions, sub-5s real-time updates via WebSocket | 4C.4, Phase 3 3.8 (action dispatch) | Client-facing daily-use surface. |
| 4C.6 | Audit log viewer — filterable, searchable, trace-ID drill-down, CSV export | 4C.4, 2B.3 | Warranty depends on this working cleanly. |
| 4C.7 | `/why <id>` interface — pretty rendering of routine reasoning for any historical decision | 4C.4, 2B.3 | First-line client question when something looks wrong. |
| 4C.8 | Knob editor UI — form-based editor for routine config; React Hook Form + Zod schema derived from OpenAPI generated types | 4C.4, 4B.1 | Better client experience than markdown editing. |
| 4C.9 | Fleet version status (minimal) — placeholder showing pinned versions of the single local install | 4C.4 | Real fleet view ships when client #2 lands. |
| 4C.10 | Critical banner / notification surface — persists across restart per architecture decision | 4C.4, 2B.4 | Operator notification UI for emergency stops, gate failures. |

**Phase 4 milestone (tracer bullet):** `email_triage` is installed on a real Gmail inbox with real Slack bindings. A test email arrives, the routine classifies it, generates a draft, posts a Slack approval card to the operator's DM, the operator clicks approve, the reply sends via Gmail with correct RFC threading, audit log captures the full chain with trace_id, `/why` for that email returns the routine's reasoning, dashboard approval queue shows the completed item in the audit view.

**Phase 4 exit criteria:** all three streams complete; tracer bullet runs end-to-end on real adapter integrations; adapter conformance tests pass for both Slack and Gmail across all verbs; OpenAPI codegen sync enforced in CI and pre-commit.

### 5.6 — Phase 5: Deployment + onboarding (Mode 2)

**Goal:** the entire MVP runs on a fresh Ubuntu VPS via the operator bootstrap CLI + client web onboarding wizard. Backup/restore validated under simulated corruption. Mode 2 (VPS in client's cloud) is the v0.1 default per Section 7.3.

**Internal sequencing:**

| # | Work package | Depends on | Notes |
|---|---|---|---|
| 5.1 | `Dockerfile` (multi-stage build: frontend assets in stage 1, Python runtime in stage 2 serving static files) | All Phase 4 | Single image per architecture decision. |
| 5.2 | `docker-compose.dev.yml` for local dev convenience (FastAPI + Vite dev server with hot reload) | Phase 1 | Can start earlier in parallel — non-blocking. |
| 5.3 | Caddyfile + TLS automation — reverse proxy in front of FastAPI, Let's Encrypt cert provisioning, HTTP→HTTPS redirect | 5.1 | Mandatory for Mode 2 (OAuth callbacks require HTTPS). |
| 5.4 | systemd unit (`infra/systemd/ota.service`) — service definition, auto-start on boot, restart-on-crash policy, log forwarding to journald | 5.1 | Linux equivalent of macOS launchd; tested on Ubuntu 22.04 + 24.04. |
| 5.5 | Mode 2 bootstrap install script (`infra/install/mode2_install.sh`) — installs Docker, pulls image, sets up data directory under `/var/lib/ota/`, installs systemd unit, configures Caddy, prompts for domain / sslip.io fallback, sets initial admin credential, prints dashboard URL | 5.1, 5.3, 5.4 | Run over SSH on a fresh Ubuntu VPS. Idempotent. |
| 5.6 | Per-client OAuth provisioning documentation under `infra/docs/` — walkthrough for client to create Google Cloud project + Gmail OAuth credentials, and Slack app + bot tokens. Includes screenshots / step-by-step. | — | Documentation; not Python code. Shipped alongside install script. |
| 5.7 | Backup / state snapshot tooling — daily snapshot of `/var/lib/ota/state/` to `/var/lib/ota/backups/`, retention policy (7 daily / 4 weekly / 3 monthly), `ota restore <snapshot-id>` command. Remote backup (S3) deferred to v0.2. | Phase 4 | Data integrity per Section 2.2 acceptance criteria. |
| 5.8 | Adapter test fixtures + happy-path E2E script — synthetic email inbox, synthetic Slack workspace, scripted scenario exercising full routine loop | Phase 4 | Pre-install acceptance check on fresh deployments. |
| 5.9 | Client web onboarding wizard — dashboard route(s) for OAuth credential paste → Gmail OAuth dance → Slack OAuth dance → category setup → template authoring → fixture validation → first run | Phase 4C (dashboard), 5.5 | Client-facing flow in the browser. Operator drives via screenshare during first delivery. Must clearly surface misconfigurations. |

**Phase 5 milestone (tracer bullet):** spin up a fresh Ubuntu 22.04 VPS at a cloud provider (DigitalOcean / Hetzner / Linode), SSH in, run `bash mode2_install.sh`. Script completes; dashboard URL printed. Browse to dashboard, log in with the initial admin credential, walk through the onboarding wizard (Gmail OAuth, Slack OAuth, categories, templates). Happy-path E2E script runs from the dashboard; test email is classified, drafted, approved in Slack, sent. Kill the Docker container mid-write, restart the systemd service, confirm state restored from latest snapshot.

**Phase 5 exit criteria:** clean Mode 2 install on fresh Ubuntu VPS succeeds end-to-end; client web onboarding wizard completes without operator intervention beyond OAuth-credential paste-in; HTTPS works with valid cert; backup/restore tested under simulated corruption.

### 5.7 — Phase 6: First-client acceptance

**Goal:** verify all 12 items on the v0.1 ship checklist (Section 2.6) are green. This phase is not new development — it's verification and gap-filling on anything that didn't reach the acceptance bar.

**Activities:**

| # | Activity | Source |
|---|---|---|
| 6.1 | Walk through the v0.1 ship checklist (Section 2.6) one item at a time. Mark green or list gaps. | Section 2.6 |
| 6.2 | Walk through the first-client acceptance criteria from Section 2.2 (8 quality-bar items). Verify each. | Section 2.2 |
| 6.3 | Fault injection: kill network mid-call, expire OAuth tokens, hit rate limits intentionally, corrupt state files. Confirm recovery behavior. | Section 2.2 adapter error handling |
| 6.4 | 7-day production-shaped soak: run the install against a real test inbox for 7 days, verifying audit log accuracy, no missed emails, no duplicates, no silent failures. | Section 2.6 item 11 |
| 6.5 | Document any deferrals discovered during acceptance into a v0.2 backlog. | — |

**Phase 6 milestone:** all 12 ship-checklist items green. **At this point, v0.1 is shippable to the first paying client.**

### 5.8 — Critical path and parallel streams (summary)

```
Phase 0 (pre-flight, done)
    ↓
Phase 1: Foundation [serial within]
    ↓
Phase 2: Stream A (Runtime) ║ Stream B (Seams)    [parallel]
    ↓
Phase 3: Capability layer [serial within]
    ↓
Phase 4: Stream A (Adapters) ║ Stream B (Routine) ║ Stream C (Dashboard)    [parallel]
    ↓
Phase 5: Deployment [mostly serial; 5.2 can start in Phase 1]
    ↓
Phase 6: Acceptance [verification only]
```

**Critical-path items that gate everything downstream:**

1. **Phase 1.8 (vocabulary codegen tool)** gates Phase 4 (capability layer can't be implemented until generated stubs exist).
2. **Phase 3.5 (capability dispatch layer)** gates Phase 4 entirely (adapters, routine, and dashboard all touch dispatch).
3. **Phase 4A.1 (OAuth helper)** gates both Slack and Gmail adapter work — do this first within Stream A.
4. **Phase 4C.1 + 4C.2 (backend models + first OpenAPI codegen)** gates all frontend work — do this first within Stream C.

**AI-assisted velocity opportunities:**

- Phase 1 (foundation, especially storage layer, JSON Schema models, codegen tool, CI scaffold) is highly mechanical. Strong AI-assist multiplier.
- Phase 2 Stream B (seams) is interface-driven and largely templated. Strong AI-assist multiplier.
- Phase 4 Stream C (dashboard scaffolding, shadcn/ui composition, TanStack Query wrappers) is mostly boilerplate from spec. Strong AI-assist multiplier.
- Phase 2 Stream A (Conductor, routine engine, L0b policy), Phase 3.5 (dispatch correctness), Phase 4A.3/4A.4 (adapter OAuth + error handling correctness), Phase 4B.7 (trust-promotion semantics) require judgment — lower AI-assist multiplier, dominant single-developer focus.

### 5.9 — Risk and mitigation

**Risks specifically introduced by sequencing decisions:**

- **Risk:** the vocabulary codegen tool (Phase 1.8) produces Python that doesn't quite match what hand-design would produce, creating refactor pressure mid-Phase 4.
  - **Mitigation:** in Phase 1, do a side-by-side review of the generated code against what you'd hand-write. Adjust the codegen template before committing the first generation. Cheaper than fixing post-Phase 4.

- **Risk:** Phase 3 capability dispatch design doesn't quite match what real adapters need, surfacing only in Phase 4.
  - **Mitigation:** the mock adapters built in Phase 3 (3.10) should exercise the rough shape of OAuth + retry + error normalization that real adapters will need. Mock adapter that's *too* simple hides defects until Phase 4.

- **Risk:** Phase 4 Stream C frontend gets ahead of backend models, causing rework when OpenAPI types change.
  - **Mitigation:** lock the high-level shape of dashboard models in 4C.1 before opening 4C.3 (frontend skeleton). Minor model changes are fine; the codegen handles them.

- **Risk:** trust-promotion auto-send (4B.7) ships but has edge cases that misbehave in the first 7-day soak (Phase 6.4), forcing a late fix.
  - **Mitigation:** ship Phase 4 with auto-send disabled by default. Operator opts in per template once you've seen real edit-pattern data from the first client. Soft launch.

- **Risk:** Mac-specific Mode 1 install assumptions (launchd, file paths) make first-client onboarding bumpy if the client uses an unusual Mac setup (homebrew vs system Python, non-standard data directories).
  - **Mitigation:** test the install script on at least two different Mac configurations before shipping. Document explicit prerequisites.

### 5.10 — What this plan deliberately does NOT cover

- **Daily / weekly scheduling.** This is a phase plan, not a calendar. Velocity varies; the order matters more than the timing.
- **Dependency on external blockers** (Anthropic API rate-limit increases, vendor app submission approval for OAuth scopes, etc.). Surface these in the acceptance phase if they hit.
- **First-client-specific routine tuning.** Templates, categories, knob values for the actual first client come during onboarding (Phase 5.7), not during framework development.
- **Section 7 (Architecture Merge).** That's housekeeping work — pulling `pending-architecture-updates.md` into `architecture.md` — and can happen at any phase boundary. Suggest doing it between Phase 1 and Phase 2 so the architecture doc is current before code references it.

---

---

## Section 6 — Roles and Operational Model

The build plan up to this point describes what gets built. This section describes **who builds, deploys, and operates it, and what each client experiences day to day.** It's the operational shape the framework lives inside — and the thing the build plan implicitly assumes but doesn't make crisp anywhere else.

### 6.1 — Two roles, kept strictly distinct

The framework has exactly two human roles. Conflating them is a recurring source of confusion in the build plan; this section is the single source of truth for which surface belongs to which role.

#### Operator / Consultant (Omar)

- **Builds the framework.** Months of focused work per the phases in Section 5.
- **Onboards each client.** SSHes into the client's VPS, runs the bootstrap install script, drives the web onboarding wizard via screenshare with the client.
- **Monitors fleet health.** Watches the dashboard's audit log and fleet status across all client installs. Investigates anomalies.
- **Ships updates.** Through the private routine channel (v0.2+); via direct SSH for v0.1.
- **Tunes routines per client.** Authors / refines templates, adjusts category criteria, sets trust-promotion thresholds based on observed edit-pattern data.
- **Owns the warranty.** The "your routine keeps working when I update it" promise.
- **Owns the recurring relationship.** Monthly retainer per client for support, tuning, and updates.

#### End User / Client

- **Provides OAuth consent during onboarding.** Once. Through the web onboarding wizard.
- **Interacts with the routine via Slack approvals daily.** Reviews drafts, clicks Approve / Edit / Skip. Edits drafts when the routine misses voice or context. This is ~95% of the daily client experience.
- **Uses the dashboard occasionally.** `/why <id>` lookups when something looks off. Audit log review during weekly self-checks. Knob editor occasionally for tweaks that don't require operator involvement.
- **Owns the data.** Their VPS, their cloud account, their OAuth tokens, their email content. The framework runs in their environment.
- **Pays setup fee + monthly retainer.** Setup once during onboarding; retainer for the ongoing operator relationship.
- **Never touches code.** Never SSHes into the VPS. Never edits markdown files. Never sees a Python traceback.

**Common confusion the build plan has accidentally encouraged:** treating the dashboard's full feature surface as "client-facing." In practice, the *daily* client surface is Slack approvals; the dashboard is *operator-heavy* for v0.1, with the client touching only `/why`, audit search, and occasional knob tweaks. The knob editor UI exists for both, but during onboarding and tuning the operator drives it.

### 6.2 — Per-client deployment lifecycle

Concrete walkthrough of what happens when a new client signs.

1. **Sales conversation closes.** Client agrees to setup fee + monthly retainer. Setup fee covers the per-client onboarding work; retainer covers ongoing operator support, updates, and warranty.

2. **Pre-deployment: client provisions a VPS.** Either:
   - Client has an existing cloud account (AWS / GCP / DigitalOcean / Hetzner / Linode) and spins up an Ubuntu 22.04 or 24.04 VPS (recommended: 2 vCPU, 4 GB RAM, 40 GB disk; ~$20–30/month at most providers).
   - Or client doesn't have a cloud account → operator walks them through signing up for DigitalOcean or Hetzner (cheapest viable options).
   - Client owns the VPS billing. Their data, their infrastructure.

3. **Pre-deployment: client provisions OAuth apps.** Following the operator's documentation (`infra/docs/oauth_setup_google.md`, `infra/docs/oauth_setup_slack.md`):
   - Client creates a Google Cloud project, enables Gmail API, creates OAuth 2.0 credentials, downloads the client ID + secret.
   - Client creates a Slack app for their workspace (Socket Mode enabled), gets bot token + app-level token.
   - Operator walks them through this via screenshare. ~30 minutes.

4. **Bootstrap (operator-driven, ~30 minutes).** Operator gets temporary SSH access to the client's VPS (or sits with the client running commands via screenshare). Runs:
   ```bash
   curl -sSL https://install.agentikey.com/ota | bash
   ```
   (Or equivalent — a one-liner that fetches the Mode 2 install script.)
   Script installs Docker, pulls the OTA image, configures Caddy with the client's domain (or sslip.io fallback), provisions Let's Encrypt cert, installs systemd unit, sets an initial admin password, prints the dashboard URL.

5. **Web onboarding (client-driven, operator-assisted, ~1 hour).** Client visits dashboard URL in browser. Logs in with initial admin password (then changes it). Walks through the onboarding wizard:
   - Paste Google OAuth credentials → click "Connect Gmail" → consent flow opens in new tab → consent granted → token saved to SecretsProvider
   - Paste Slack OAuth credentials → click "Connect Slack" → consent flow → token saved
   - Set categories (operator guides this — what email types should the routine handle?)
   - Draft initial reply templates (operator helps; iterates based on client's voice)
   - Run happy-path E2E against test fixtures → confirms install works end-to-end
   - Click "Activate routine" → routine starts polling Gmail

6. **First day live (passive monitoring, operator-watched).** Real emails start arriving. Routine processes them, generates drafts, posts to Slack approval channel. Operator watches the audit log and `/why` for any decisions that look off. Operator pings client for clarifications when the routine misclassifies anything.

7. **First week tuning (collaborative).** Client provides feedback ("too aggressive on the urgent category", "this template needs more warmth", "skip these auto-reply categories entirely"). Operator updates configs via the knob editor, occasionally edits templates directly. Iteration cycle is typically 1–3 changes per day in week 1, dropping off by week 2.

8. **Steady-state ongoing operation.** Client uses Slack approvals daily. Trust-promotion eligibility starts kicking in as templates accumulate consecutive un-edited approvals (after the operator opts each template in). Operator does monthly health-check reviews. Updates flow through the private channel (v0.2+); for v0.1, operator pushes updates via SSH on a documented schedule.

### 6.3 — Operating modes

| Mode | Description | v0.1 status | Notes |
|---|---|---|---|
| **Mode 1 — Local (laptop install)** | Framework runs on the client's laptop. | **REJECTED for v0.1 and beyond.** | Laptops sleep, get closed for weekends, suffer from local OS quirks. Paying clients with always-on email triage need always-on runtime. Not honest as a production deployment. |
| **Mode 2 — VPS in client's cloud account** | Framework runs on a Linux VPS the client owns, in their cloud provider account. Client owns data + infrastructure. | **v0.1 default.** | The right balance of client data ownership, always-on uptime, and operator support feasibility. Client pays the VPS bill (~$20–30/month). Operator has SSH for support; client can revoke access at any time. |
| **Mode 3 — Managed by operator** | Framework runs in a hard-isolated container in the operator's infrastructure. | **v0.3+ future.** | Higher-trust, higher-touch tier. Operator pays hosting cost; bundled into client's monthly fee. Best for IP-anxious clients, enterprise relationships, or clients who don't want to manage a VPS. Strict per-tenant isolation per architecture decision. |

The architecture's three-mode design (Mode 1 / 2 / 3 from earlier sessions) collapses for v0.1 to Mode 2 only. Mode 3 returns when there's a paying client whose situation justifies the operational overhead of operator-hosted infrastructure.

### 6.4 — Where speed-to-market actually lives

The build plan is an upfront investment, not a speed-to-market play for client #1.

**Client #1 timeline (slow on purpose):**
- Framework build: months of focused work (per Section 5 phases)
- Onboarding: 1–2 hours bootstrap + onboarding + ~1 week of tuning
- Total: weeks to months from now

**Client #2+ timeline (fast — this is where speed-to-market lives):**
- Onboarding: ~3 hours total (VPS provision + OAuth setup + bootstrap + onboarding)
- Tuning: ~1 week of iteration alongside the first week of live operation
- Per-client incremental dev work: zero. Same framework, same routine, different knobs.
- Revenue impact: setup fee + monthly retainer collected, with marginal cost per client approaching the operator's time spent on support (which the retainer covers).

**Framework-level multiplication:**
- After 5–10 clients on `email_triage`, the framework build cost is recouped.
- Then add a second routine (CRM-touching, calendar-touching, scheduling-touching). Each new routine takes weeks not months because the framework already exists.
- Each new routine multiplies across all current and future clients — clients can opt into additional routines via the same dashboard.

**The framework is the speed multiplier; client #1 is the proof that justifies the investment.** Section 7 (Architecture Merge) is the last planning activity before Phase 1 of Section 5 starts.

### 6.5 — Daily UX divergence

| Surface | Client uses daily? | Operator uses daily? | Notes |
|---|---|---|---|
| Slack approval cards | ✅ Heavy | ⬜ Rarely (only their own install) | Client's primary interaction with the routine. Approve / Edit / Skip on every draft. |
| Dashboard — approval queue | ⬜ Occasional | ✅ Heavy | Operator watches the queue for anomalies across all client installs. Client uses for backfill or weekend catch-up. |
| Dashboard — audit log | ⬜ Occasional (`/why` follow-ups, weekly self-checks) | ✅ Daily | Warranty-relevant surface. Operator review during monthly health-checks. |
| Dashboard — `/why <id>` | ✅ When something looks off | ✅ When the client pings about a decision | First-line response for any "huh that's wrong" moment. Both sides hit it. |
| Dashboard — knob editor | ⬜ Occasional self-serve tweaks | ✅ Heavy during onboarding + tuning | Operator-heavy in week 1; tapers as steady state approaches. |
| Dashboard — fleet version status | ❌ Not relevant (single install) | ✅ When operator has multiple clients | Operator-only surface across installs. Client view is "your install is up to date." |
| CLI bootstrap | ❌ Never | ✅ Once per client install | SSH-only, operator-driven. Client never touches this. |
| Web onboarding wizard | ✅ Once during initial setup | ✅ Drives client through it during initial setup | Both touch it during onboarding; nobody touches it again after install completes. |
| Markdown source files | ❌ Never | ✅ When authoring new routines or tuning templates | Source-of-truth files in the data directory. Operator-only. |

### 6.6 — Revenue model implications

The role split maps directly to the revenue model:

- **Setup fee** covers the per-client onboarding work (bootstrap + OAuth provisioning + initial tuning + first week of monitoring). Estimate: $1,000–$3,000 for `email_triage` first-client setup, dropping as the operator's per-client time decreases with experience.
- **Monthly retainer** covers ongoing operator work: monitoring, tuning, updates via private channel (v0.2+), warranty enforcement, support requests. Estimate: $200–$1,000/month per client per routine, depending on volume + tuning frequency.
- **Per-routine pricing** — additional routines beyond the first add to monthly retainer, not setup (since framework is already installed). E.g., adding a `lead_qualifier` routine to a client running `email_triage` is ~$100–$500/month incremental.
- **Mode 3 (Managed) premium** — when it ships in v0.3+, charge 2–3× standard retainer for the operator-hosted tier. Client doesn't manage VPS; operator does. Recurring revenue scales with hosting margin.

The framework is what makes the per-client unit economics work: marginal cost per additional client approaches the operator's tuning time, while marginal revenue is the full retainer. With 10–20 clients on email_triage at $400–800/month each, the consultancy reaches a sustainable single-operator revenue level.

### 6.7 — What this section deliberately does NOT cover

- **Sales process** — how the operator finds and closes clients. That's marketing work (see `marketing.md`), not build-plan work.
- **Pricing-specific commitments** — the dollar figures above are illustrative ranges, not locked pricing tiers. Actual pricing locks during early-client engagement.
- **Multi-routine coordination across clients** — relevant when clients buy multiple routines. Out of v0.1 scope (single routine).
- **Operator hiring / team scaling** — relevant when one operator can't handle the client load. Out of scope for v0.1 / v0.2.

---

## Section 7 — Architecture Merge Notes

The architecture doc (`docs/architecture.md` once migrated; currently at the project workspace root) was locked through 2026-05-13. Two batches of subsequent work need to be merged in before Phase 1 of Section 5 begins:

- The **9 locked decisions** captured in `pending-architecture-updates.md` from the 2026-05-18 session
- The **vocabulary deliverables** (`vocabulary/_types.md`, `vocabulary/messaging.md`, `vocabulary/email.md`, `vocabulary/_roster.md`)
- The **delivery model change** captured in Section 6 of this doc (Mode 1 rejected, Mode 2 as v0.1 default, web onboarding wizard moved into v0.1 scope)
- The **build-plan-v0.md** cross-reference itself

This section is the merge plan, not the merge. Execution happens as its own work pass after the plan is reviewed.

### 7.1 — Merge map: decisions → target sections in architecture.md

Architecture.md's current top-level sections:

```
1.  Component model
2.  Layered architecture
3.  Layer details (Access Layer · Identity Context · Conductor · Routines · Automation · Connect)
4.  Context tiering (the five levels)
5.  Cross-routine handoff — Artifacts model
6.  Human-in-the-loop gates
7.  Test harness — evals, not unit tests
8.  Operational primitives
9.  Deployment modes
10. IP protection model
11. Private routine channel
12. Markdown / Python boundary
13. Seam architecture
14. Contracts
15. Cross-contract invariants
16. Operator notification routing
17. Open questions
18. Out of scope (for now)
```

Each pending decision maps to one or more target sections:

| Pending decision | Target section(s) in architecture.md | Treatment |
|---|---|---|
| **Decision 1** — `ota_connect` call namespace + naming convention | §3 (Connect subsection); §1 (Component model OTA Connect entry) | Extend Connect subsection with namespace shape (`ota_connect.<capability>.<verb>`), capability vs verb naming rules, marketing vs spec name split. Reference Section 3.1 of build-plan-v0.md for the rest. |
| **Decision 2** — Vocabulary promotion rule, adapter extension namespace, adapter release discipline | §3 (new sub-section under Connect: "Vocabulary governance + adapter release") | New ~1-page sub-section. Promotion rule, `ota_connect.<capability>.<adapter>.<feature>` extension pattern, versioned-release + changelog requirement, no-cadence-gate principle. |
| **Decision 3** — Update lifecycle (snapshot tests, source migration, state migration, manual fallback) | **New top-level section "Update Lifecycle"** between §8 and §9. Renumber §9–§18 accordingly. | Significant addition. Subsections: 4-tier migration model (3a snapshot tests, 3b source, 3c state with backup guardrail, 3d manual fallback); migration tooling shape; conformance test matrix; "operator-reviewed diff before commit" UX. |
| **Decision 4** — Per-client pinning, operator-driven updates, security-tier SLA, Mode 3 canary, stale-install policy | New Update Lifecycle section (continued); §9 (Deployment modes) cross-reference | Per-client version pinning at delivery; opt-in pull updates for Mode 1/2 (now just Mode 2); security-tier SLA (24h push); Mode 3 follows canary cohort principle. Stale-install policy with tiered enforcement. |
| **Decision 5** — Canary cohort mechanics deferred | New Update Lifecycle section (deferred note); §17 (Open questions) | Note that principle is locked in Decision 4d but specific mechanics await ≥2 Mode 3 clients. |
| **Decision 6** — Binding model: default + override only for v1.0 | §3 (new sub-section under Connect: "Binding layer"); §14 (Contract E extension) | Longest-prefix-match resolution, adapter-level shorthand + verb-level override syntax. Routing-rule and purpose-based bindings explicitly deferred. Schema slot in Contract E. |
| **Decision 8** — Upstream API deprecation documentation guidance | §3 (Connect → adapter release discipline subsection from Decision 2) | Three-response taxonomy (bridged / degraded / forked) as adapter changelog convention. Demoted from policy to guidance per session reframe. |
| **Decision 9** — Connect-as-standalone-product gating | §1 (Component model OTA Connect entry); §18 (Out of scope explicit listing) | Single-signal gate: don't invest in standalone-product infrastructure until external party asks. Clean boundaries from day one, but don't ship as product until pulled. |
| **Decision 10** — Per-client change report on every Core/Connect update | New Update Lifecycle section (continued) | Lightweight view over snapshot test data, scoped per client. Operator-facing first; client-facing polish later. |

### 7.2 — New sections to add to architecture.md

**§9 (new) — Update Lifecycle.** Substantial new top-level section gathering Decisions 3, 4, 5, 10. Suggested subsection structure:

- 9.1 — Update strategy overview (why auto-migration over LTS branches or forward-compat)
- 9.2 — Snapshot test matrix (Decision 3a)
- 9.3 — Source migration with operator-reviewed diffs (Decision 3b)
- 9.4 — State migration with mandatory pre-migration snapshot (Decision 3c)
- 9.5 — Manual migration fallback (Decision 3d)
- 9.6 — Per-client version pinning at delivery (Decision 4a, 4b)
- 9.7 — Security-tier SLA carve-out (Decision 4c)
- 9.8 — Mode 3 canary cohort principle + mechanics-deferred note (Decision 4d, 5)
- 9.9 — Stale-install enforcement policy (Decision 4e)
- 9.10 — Per-client change report (Decision 10)
- 9.11 — Fleet version observability requirement

Inserting this section forces renumbering of all subsequent sections. Old §9 (Deployment modes) becomes §10; current §10 (IP protection) becomes §11; etc. Down through §19 (Out of scope).

**§3 (new sub-sections under Connect).** Three new subsections inside the existing Connect Layer details:

- 3.connect.a — Namespace and naming convention (Decision 1)
- 3.connect.b — Vocabulary governance + adapter release discipline (Decisions 2, 8)
- 3.connect.c — Binding layer (Decision 6)

### 7.3 — Existing sections to update in architecture.md

**§1 — Component model:**
- OTA Connect entry: add namespace + naming summary (Decision 1) with cross-reference to new §3 sub-section.
- OTA Connect entry: add Connect-as-standalone-product future state with single-signal gate (Decision 9).

**§9 — Deployment modes (will become §10 after Update Lifecycle insertion):**
- Mark Mode 1 (Local) as REJECTED for v0.1 and beyond, with rationale (laptops sleep; paying clients need always-on).
- Mark Mode 2 as v0.1 default.
- Mode 3 stays as future tier with revised target (v0.3+ rather than ambiguous "later").
- Cross-reference Section 6 of build-plan-v0.md for the full operational model.

**§14 — Contracts (will become §15):**
- Contract E (Deployment Configuration) gets the `bindings:` block schema from Decision 6.
- Reference `vocabulary/` as a new source-of-truth doc parallel to contracts (vocabulary specs are conformance contracts at the capability layer).

**§17 — Open questions (will become §18):**
- Move Canary cohort mechanics (Decision 5) here as deferred-pending-trigger.
- Resolve any old open questions that newer decisions have answered.

**§18 — Out of scope (will become §19):**
- Add Connect-as-standalone-product infrastructure (Decision 9) with explicit single-signal gate.
- Add Mode 1 (laptop install).

### 7.4 — New cross-references to add to architecture.md

Top of architecture.md (after the existing "Working State" preamble) should reference these as peer source-of-truth docs:

- **`vocabulary/`** — capability vocabulary specs (`_types.md`, `messaging.md`, `email.md`, `_roster.md`, `_template.md`). The framework's capability layer is implemented against these specs. Updates to the vocabulary are governed by Decision 2.
- **`contracts.md`** — existing source-of-truth for the 5 canonical contracts.
- **`docs/build-plan-v0.md`** — active first-client MVP build plan. Sections 1–7 cover scope, sequencing, tech stack, operational model, and this merge.

### 7.5 — Recommended merge sequence

Order matters because some changes are structural (require renumbering) and others are additive (just new content):

1. **First pass — additive only.** Add the new Connect sub-sections (Decision 1, 2, 6, 8), add cross-references to vocabulary/ and build-plan-v0.md at the top. No renumbering.
2. **Second pass — structural.** Insert new "Update Lifecycle" section between current §8 and §9. Renumber §9–§18 to §10–§19. Update all internal cross-references.
3. **Third pass — existing-section updates.** Mode 1 → Mode 2 rejection in (new) §10. Connect-as-standalone in §1 and §19. Contract E extension in §15. Open questions cleanup in §18.
4. **Fourth pass — verification.** Re-read architecture.md end-to-end for consistency. Confirm cross-references resolve. Confirm no decisions from pending-architecture-updates.md were left behind.
5. **Fifth pass — mark merged.** In `pending-architecture-updates.md`, mark each decision section `[MERGED 2026-MM-DD]` or delete those entries entirely.

Single-pass attempts (doing all four phases at once) tend to lose decisions or break cross-references during section renumbering. The four-pass approach is slower but safer.

### 7.6 — Conflicts and ambiguities to resolve during merge

Two things to surface during execution that the plan doesn't pre-resolve:

1. **Section 8 (Operational primitives) and the new Update Lifecycle section overlap.** Some content currently in §8 (audit log handling, snapshot-related concerns) may belong in Update Lifecycle. Decide during merge whether to move it, leave it duplicated, or restructure §8 to cover only operational primitives that aren't update-lifecycle-specific.

2. **Section 11 (Private routine channel) describes update propagation mechanics for routines.** Decision 4's per-client pinning + opt-in update model overlaps with §11. Need to reconcile: either merge §11 into Update Lifecycle, or keep §11 focused on the wire-protocol level while Update Lifecycle covers the policy level.

Both ambiguities should be resolved during the merge pass with a deliberate call, not silently.

### 7.7 — Definition of done

Architecture merge is complete when:

1. ✅ Every decision in `pending-architecture-updates.md` is reflected in `architecture.md` and marked `[MERGED]` in the pending file.
2. ✅ All vocabulary specs (`vocabulary/*.md`) are referenced from architecture.md as source-of-truth peers.
3. ✅ Mode 1 is explicitly rejected in the Deployment Modes section.
4. ✅ Mode 2 is the v0.1 default in the Deployment Modes section.
5. ✅ Architecture.md cross-references resolve cleanly (no dangling "see Section X" where X was renumbered).
6. ✅ A reader new to the project can read architecture.md alone and understand the current locked state — without needing to chase pending-architecture-updates.md or build-plan-v0.md for missing pieces.
7. ✅ Build-plan-v0.md is referenced from architecture.md as the active build plan.

When (1)–(7) are green, Phase 1 of Section 5 can start. The architecture doc is the spec the code is being written against; it must be current.

### 7.8 — Open question: execute merge in this session, or schedule separately?

Two options:

- **Execute now.** Drive the four-pass merge in this session. Estimated 4–6 substantial Edit operations across architecture.md plus updates to pending-architecture-updates.md. Architecture.md is ~51KB; edits are precise but mechanical once the plan is locked.
- **Schedule separately.** Lock the merge plan now (this section). Execute in a focused follow-up session where architecture.md is open and reviewable continuously, without other context competing for attention.

I'd lean **execute now** — the plan is concrete enough that the merge is mechanical, and deferring leaves the architecture doc stale during a period when Phase 1 work could otherwise start. But the schedule-separately option is defensible if you want to review architecture.md yourself first before edits land.

---

---

## Changelog

- **2026-05-18** — Section 1 (Implementation Gap Audit) populated. Sections 2–6 stubbed for upcoming sessions.
- **2026-05-18 (revision)** — Reframed sprint goal from stakeholder/funder demo to first-client-deliverable. Updated Layer 7 (dashboard) and Layer 8 (deployment) item notes to reflect daily-use / production-install context. Removed "demo seed data" item, replaced with "adapter test fixtures + happy-path E2E" (real pre-install acceptance check, not demo theater). Backup/snapshot upgraded from S to M effort (data integrity is non-negotiable for paying clients). Rewrote "What the math says" to drop demo-grade tradeoff option; quality bar is now "first-client-ready" with scope cuts being the only available compression lever. Added a likely-scope-cuts list to make Section 2 inputs concrete.
- **2026-05-18 (revision 2)** — Dropped the artificial 2-week deadline. Build is "ASAP at first-client quality," not time-boxed. Renamed doc subtitle from "Two-Week MVP Sprint" to "First-Client MVP." Section 5 renamed from "Sprint Plan" to "Build Sequencing Plan." Section 2 (MVP Scope Definition) fully populated: scope matrix marking every audit item IN/MINIMAL/OUT, with several items reversed from earlier scope-cut suggestions now that time isn't the constraint (Slack adapter: all 5 verbs; Gmail adapter: all 9 verbs; trust-promotion auto-send: IN; knob editor UI: IN; conformance test coverage: real, not skeleton). First-client acceptance criteria documented for the 8 items where quality bar matters most. Critical path + parallelization documented. Open decisions surfaced. v0.1 ship checklist defined (12-item gate).
- **2026-05-18 (revision 3)** — Section 3 (Tech Stack Decisions) fully populated. Backend stack locked (Python 3.12, FastAPI, Pydantic v2, raw SQL + Pydantic, structlog, authlib, cryptography, pytest, ruff, mypy, python:3.12-slim-bookworm). Frontend stack locked (React + Vite + TypeScript, shadcn/ui, Tailwind v4, React Router v6, TanStack Query, Zustand, React Hook Form + Zod, Recharts, native WebSocket, lucide-react, pnpm, @hey-api/openapi-ts, ESLint + Prettier, Vitest + RTL + Playwright). Section 3.3 documents the Pydantic ↔ TypeScript codegen workflow as a load-bearing operational discipline with three non-negotiable enforcement rules (never hand-edit generated files, pre-commit hook regenerates and fails on diff, CI verifies generated files match committed). Carry-over decisions from 2.4 locked (WebSocket, local-only snapshots, CLI onboarding, manual identity registry). Repo structure implications surfaced for Section 4.
- **2026-05-18 (revision 4)** — Section 4 (Repo Structure) fully populated. Monorepo layout locked with full directory tree across all 8 layers (ota_core, ota_connect, ota_routines, ota_dashboard_api, ota_dashboard_web, vocabulary, tests, scripts, docs, examples, infra, .github). Dependency direction codified: ota_core (bottom) → ota_connect → ota_routines / ota_dashboard_api, with adapters under ota_connect/adapters/*. Generated artifacts and source-of-truth mapping documented (frontend codegen, vocabulary stubs, OpenAPI spec). Runtime data location separated from source code with per-mode data directory paths defined. Source-of-truth doc migration from project workspace to repo mapped out (architecture.md, contracts.md, vocabulary/*, build-plan-v0.md → repo; marketing.md stays in workspace as planning artifact). pyproject.toml strategy locked (single root file with multi-package config). justfile recommended for workspace coordination commands.
- **2026-05-18 (revision 5)** — Pulled vocabulary-to-Python codegen tool from v0.2 deferral into v0.1 Layer 1 scope. Initial deferral reasoning didn't survive scrutiny: codegen is ~200–400 lines of Python (1–2 days at AI-assisted velocity), and deferring it would silently accept the same parallel-source-of-truth maintenance risk that Section 3.3 exists to eliminate at the Pydantic ↔ TypeScript boundary. Added new Layer 1 audit item (Section 1 totals: 56 → 57 items, 53–75 → 54–77 days). Added new Section 3.4 documenting the vocabulary codegen workflow with three non-negotiable enforcement rules mirroring Section 3.3 (never edit generated files, pre-commit hook regenerates and verifies, CI verifies). Renumbered 3.4–3.6 → 3.5–3.7. Updated Section 4.1 directory tree to mark `ota_connect/_types/*.py` and `ota_connect/{capability}/verbs.py` as AUTO-GENERATED. Updated Section 4.3 generated-artifact table: moved these files from "hand-written" to auto-generated with full source-of-truth mapping. Both codegen disciplines now documented as load-bearing operational constraints honoring the architecture's markdown-first principle from day one.
- **2026-05-18 (revision 6)** — Section 5 (Build Sequencing Plan) fully populated. Build organized into six phases (Phase 0: pre-flight done; Phase 1: foundation; Phase 2: framework runtime + seams in parallel; Phase 3: capability layer; Phase 4: adapters + routine + dashboard in three parallel streams; Phase 5: deployment + onboarding; Phase 6: first-client acceptance). Each phase has internal sequencing tables with work packages, dependencies, and notes. Tracer-bullet milestone defined per phase to verify the phase actually works end-to-end before moving on. Critical path identified (Phase 1.8 vocab codegen → Phase 3.5 dispatch → Phase 4A.1 OAuth helper / 4C.1 backend models). AI-assist velocity opportunities flagged per phase. Five sequencing-specific risks documented with mitigations. Plan deliberately uses phases not calendar days — no fixed deadline; order matters more than timing.
- **2026-05-18 (revision 7)** — Added Section 6 (Roles and Operational Model) as substantive operational context. Two distinct roles documented (Operator/Consultant Omar; End User/Client) with explicit surfaces each touches. Per-client deployment lifecycle walked through end-to-end (sales close → VPS provision → OAuth setup → bootstrap → onboarding wizard → first day live → first week tuning → steady state). Operating modes table updated: Mode 1 (Local) REJECTED for v0.1 and beyond; Mode 2 (VPS in client's cloud account) is v0.1 default; Mode 3 (Managed) is v0.3+ future. Speed-to-market clarified: client #1 is slow proof; client #2+ is fast (~3 hours per client onboarding, framework cost amortizes over 5–10 clients). Daily UX divergence table documents which surfaces each role uses daily vs occasionally. Revenue model implications: setup fee + monthly retainer per routine; Mode 3 premium for v0.3+. Renumbered old Section 6 (Architecture Merge Notes) to Section 7. Propagated Mode 2 across the rest of the build plan: Layer 8 audit + scope items updated (added per-client OAuth app provisioning docs, split CLI bootstrap from client web onboarding wizard, expanded HTTPS / TLS / Caddy setup); Section 3.5 onboarding form factor updated to two-part split; Section 4.1 infra/install/ Linux-targeted (systemd unit instead of launchd plist, mode2_install.sh, Caddyfile, OAuth setup docs); Section 4.4 data directory table updated (Mode 1 row removed); Section 5 Phase 5 work packages updated to reflect Mode 2 lifecycle. Total v0.1 effort grew from 57 items / 54–77 days to 58 items / 56–81 days (Layer 8 expanded ~2–3 days for Mode 2 complexity).
- **2026-05-18 (revision 8)** — Section 7 (Architecture Merge Notes) fully populated. Comprehensive merge plan: decision-to-target-section map for all 9 pending decisions; new top-level "Update Lifecycle" section to be inserted between current §8 and §9 (forces renumbering of §9–§18 to §10–§19); three new Connect sub-sections under §3 (namespace + naming, vocabulary governance, binding layer); existing-section updates for §1 (Component model), §9/§10 (Deployment modes), §14/§15 (Contracts), §17/§18 (Open questions), §18/§19 (Out of scope); cross-references to be added at top of architecture.md (vocabulary/, contracts.md, docs/build-plan-v0.md). Four-pass recommended merge sequence (additive first, then structural, then existing-section updates, then verification, then mark-merged). Two known conflicts surfaced for resolution during execution: §8 Operational primitives overlap with new Update Lifecycle; §11 Private routine channel overlaps with Decision 4 update propagation. Seven-item definition of done. Plan is the plan; execution recommended in this same session if possible — section is concrete enough that merge is mechanical.
