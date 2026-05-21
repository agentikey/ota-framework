# Pending Architecture Updates

> **STATUS: ALL DECISIONS MERGED into `architecture.md` on 2026-05-18.**
>
> The canonical state of these decisions now lives in `architecture.md` (and `vocabulary/`, `contracts.md` where applicable). This file is preserved as a historical record of the merge contents — do not edit the locked decisions below.
>
> **Merge mapping:**
> - Decision 1 (ota_connect namespace + naming) → architecture.md §3 Connect → "Namespace and naming convention" subsection
> - Decision 2 (vocabulary governance + adapter extension namespace + adapter release discipline) → architecture.md §3 Connect → "Vocabulary governance and adapter release discipline" subsection
> - Decision 3 (update lifecycle: snapshot tests + source/state/manual migration) → architecture.md §9.2–9.5 (new Update Lifecycle section)
> - Decision 4 (per-client pinning + operator review + security SLA + Mode 3 canary + stale-install) → architecture.md §9.6–9.9
> - Decision 5 (canary mechanics deferred) → architecture.md §9.8 + §18 Open questions
> - Decision 6 (binding model default + override) → architecture.md §3 Connect → "Binding layer" subsection + §15 Contract E reference
> - Decision 8 (deprecation documentation guidance) → architecture.md §3 Connect → adapter release discipline (three-response taxonomy)
> - Decision 9 (Connect-as-standalone gating) → architecture.md §1 Component model + §19 Out of scope
> - Decision 10 (per-client change report) → architecture.md §9.10
> - Mode 2 as v0.1 default / Mode 1 rejected → architecture.md §10 Deployment modes
> - Vocabulary specs as peer source-of-truth → architecture.md preamble + §15 Contracts
>
> **Next time:** when new decisions accumulate in a future session, repopulate this file from scratch with the new pending entries. The merge-then-archive cycle is the discipline.

---

## Original content (preserved as historical record)

The decisions below were the contents of the merge that landed on 2026-05-18. Do not edit; refer to architecture.md for the canonical state.

Scratch file holding decisions locked during ideation sessions, ready to be merged into `architecture.md` (and related contract docs) in a dedicated update pass. Each entry should be copy-pasteable into the appropriate architecture section with minimal editing.

When merging into `architecture.md`, delete the merged entry from this file or mark it `[MERGED YYYY-MM-DD]`.

---

## Decision 1 — `ota_connect` call namespace and naming convention (locked 2026-05-18)

**Target section in architecture.md:** new sub-section under the OTA Connect component description, OR new top-level "Capability Layer" section if that gets created.

**Locked:**

- **Call namespace:** `ota_connect.<capability>.<verb>(arguments)`
  - Example: `ota_connect.messaging.send_dm(user, body)`
- **Capability names:** no abbreviations of common words (`messaging`, not `msg`; `task_management`, not `tasks`). Established industry proper nouns considered case-by-case at this level.
- **Verb names:** established industry proper nouns permitted (`send_dm`, `oauth_refresh`, `update_crm_contact`).
- **Namespace shape:** flat under `ota_connect`. Every direct child of `ota_connect` is a capability. Non-capability surfaces (admin, debug, introspection) live in sibling packages: `ota_connect_admin`, `ota_connect_debug`.
- **No `oc` short alias as a framework convention.** Routines use the full `ota_connect.messaging.send_dm(...)` form. Individual authors may locally alias in their own files, but the documented standard form is the full path.
- **Product / marketing name unchanged:** OTA Connect.
- **Future portable spec hook:** if Connect-as-standalone-product happens (the 2027 gated scenario), the spec document references verbs as `<capability>.<verb>` without the SDK prefix. SDK prefix stays in the SDK, neutral path in the spec.

**Rationale (one line):** AWS-SDK / Stripe pattern (brand-at-API-surface) chosen over JDBC/LSP pattern (neutral contract namespace), because Connect is a single-vendor SDK with no realistic multi-implementer scenario in the v1.0 horizon. Readability > terseness throughout.

---

## Decision 2 — Vocabulary promotion rule, adapter extension namespace, adapter release discipline (locked 2026-05-18)

**Target section in architecture.md:** new sub-section under the OTA Connect / Capability Layer description covering vocabulary governance and adapter release process.

**Locked:**

**Vocabulary promotion rule:**
> Don't add a verb until you've felt the pain of not having it.

No vocabulary additions for hypothetical needs. When a real client need hits and the capability genuinely cannot be expressed by composing existing verbs, add it. Single decision-maker (Omar) for v1.0.

**Adapter-specific feature namespace:**
- Primary form: `ota_connect.<capability>.<adapter_name>.<feature>`
  - Example: `ota_connect.messaging.slack.add_thread_reaction(...)`
  - Adapter-specific stuff lives under the capability it relates to, making the "you've stepped outside the portable abstraction" cue visible at the call site.
- Fallback form for adapter features that don't map to any capability (e.g., Slack workflows): `ota_connect.<adapter_name>.<feature>` as a top-level adapter namespace. Rare, not worth further design now.
- Routines using either form **explicitly declare the adapter dependency** in their manifest and lose portability for that specific capability.

**Adapter release discipline:**
- No release calendar, no promotion gate.
- **Two required disciplines:**
  1. Versioned releases with written changelog (required for migration tooling to work).
  2. Batch small changes — don't ship a release per fix.

---

## Decision 3 — Update lifecycle: snapshot tests, source migration, state migration, manual fallback (locked 2026-05-18)

**Target section in architecture.md:** new top-level section "Update Lifecycle" pulling together snapshot testing, migration tooling, and operator-facing migration UX. May also touch contracts (state migration affects L4 SQLite schema versioning).

**Locked:**

**3a — Snapshot test matrix in CI (non-negotiable floor).**
- Every shipped routine snapshot-tested against every Core/Connect minor version.
- Failures block release of the Core/Connect change OR trigger a migration script requirement.
- Snapshot fixtures live alongside routines; LLM responses fixtured (canned responses keyed on prompt hash) so tests are deterministic.

**3b — Auto-migration for routine source files (with operator review).**
- Framework generates the migration as a proposed unified diff against the routine's current source.
- Operator reviews and approves before commit:
  ```
  ota migrate --core 0.3 --target 0.4 --routine inbound_qualifier
    → Migration plan: [unified diff]
    Apply? [y/n/edit]
  ```
- Migration scripts may flag `auto_apply: true` for trivial changes (pure renames, syntax-only) — operator receives notification, not a prompt.
- Snapshot tests run after the diff is applied; behavior regressions surface before commit.

**3c — Auto-migration for routine STATE (SQLite, trust counters, identity records, artifact store).**
- Mandatory pre-migration backup snapshot for rollback safety.
- State migrations declared separately from source migrations (different risk profile, different review depth).
- Failure mode: rollback to snapshot, surface error to operator, halt update for that client.

**3d — Manual migration as the third path.**
- Some breaking changes can't be auto-resolved (semantic shifts requiring human judgment).
- Update pauses with a markdown checklist for the operator to walk through.
- Migration documented in the Core/Connect changelog as `manual:` so clients know what to expect during upgrade.

---

## Decision 4 — Per-client pinning, operator-driven updates, security SLA, Mode 3 canary, stale-install policy (locked 2026-05-18)

**Target section in architecture.md:** new sub-section under "Update Lifecycle" (created by Decision 3) covering delivery-time pinning, operator-driven update flow, and per-mode update mechanics.

**Locked:**

**4a+4b — Per-client pinning + operator-driven updates (Mode 1/2):**
- Every delivery pins exact Core / Connect / routine / vocabulary versions per client.
- Updates land when the operator (Omar) initiates them through the private channel. The client install pulls; the client does not make update decisions.
- Per-client update timing is the operator's call. No client-facing update prompts.

**4c — Operator review for all updates + security-tier SLA:**
- All updates go through operator review. No auto-apply tier.
- Security-classified updates have an internal SLA for fast push (target: 24h from release).
- Routine updates have no SLA; pushed on natural cadence per client.
- "Security tier" = CVE in dependency, exploitable adapter bug, compliance fix. Classification documented in adapter / Core changelog entries.

**4d — Mode 3 (Managed) follows canary cohort, not per-client opt-in:**
- Managed clients don't opt in individually. The cohort rollout decision IS the update decision for them.
- Cohort mechanics deferred to Decision 5.

**4e — Stale-install policy (Mode 1/2), tiered enforcement, principle locked / thresholds TBD:**
- Banner in operator UI when client is N days behind.
- Email nag to client at a larger threshold.
- Warnings emitted in routine output at a still-larger threshold.
- Routines refuse to run with "contact your consultant" message at the largest threshold.
- Default proposal: 30d / 90d / 180d / 365d. Tunable per delivery (enterprise clients may negotiate longer windows).
- Operator needs a fleet-version observability surface (CLI `ota fleet status` minimum) to enforce this. Lock the requirement; defer the implementation shape.

---

## Decision 5 — Canary cohort mechanics: deferred (2026-05-18)

**Status:** principle locked in Decision 4d (Mode 3 follows canary cohort, not per-client opt-in). Mechanics deferred.

**Defer-until trigger:** ≥2 Mode 3 clients in active engagement. At that point, decide:
- Phase count (2-phase: 1 canary → rest, OR 3-phase: 1 → 10% → all)
- Bake periods per phase per update type (routine update vs Core/Connect update)
- Canary selection rule (default: broadest surface area; tiebreak: relationship resilience)
- Threshold for promoting from 2-phase to 3-phase rollout (proposed: ≥10 Mode 3 clients)

**What architecture.md should reflect now:** Core needs a notion of *canary tagging* on Mode 3 client records, and a *cohort rollout* primitive in the update mechanism. The shape of the rollout policy is per-deployment configuration, not framework code.

---

## Decision 6 — Binding model: default + override, capability-granular with adapter-level shorthand (locked 2026-05-18)

**Note:** Decision 7 (originally separate as "bindings at capability granularity with adapter-level shorthand") collapses into Decision 6. Same model, different framing.

**Target section in architecture.md:** sub-section under the binding layer / Contract E extension covering per-client binding configuration.

**Locked:**

**Binding model for v1.0:**
- Clients set a default binding for a capability and override at the verb level.
- Resolution rule: longest-prefix match wins.

```yaml
# /client_config/bindings.md
bindings:
  capabilities:
    messaging: slack                     # client-wide default for messaging.*
    messaging.send_email: gmail          # verb-level override
    task_management: asana
    calendar: google_calendar
    document_storage: google_drive
    crm: hubspot
```

- Adapter-level shorthand (`messaging: slack`) expands internally to apply across all `messaging.*` verbs the adapter satisfies.
- Verb-level binding (`messaging.send_email: gmail`) overrides the default for that specific verb.

**Deferred to post-v1.0** (write into architecture as explicit future work to prevent accidental scope creep):
- **Routing-rule bindings** — conditional bindings like `if recipient.org != self, use teams`. Designated as a tarpit; do not build.
- **Purpose-based composite bindings** — routine declares `messaging[purpose=internal]` and `messaging[purpose=external]`; client maps purposes to adapters. Useful for some cases but adds complexity; wait for real client demand.

---

## Decision 8 — Upstream API deprecation documentation guidance (locked 2026-05-18)

**Status:** demoted from "locked policy" to documentation guidance, per session reframe.

**Target section in architecture.md:** brief note under the adapter release discipline (Decision 2), or in the adapter changelog format spec.

**Locked:**
- When an adapter handles an upstream API deprecation, the changelog entry documents the chosen response:
  - **Bridged** — adapter hides the change; routines see no difference.
  - **Degraded** — adapter declares it no longer satisfies a sub-feature; routines requiring it fail install with a clear message.
  - **Forked** — old verb deprecated, new verb added; migration script handles routine rewrites.
- Operator judgment picks the response (prefer least client impact). No formal policy / approval workflow required.
- Pattern can be promoted to a stricter policy later if deprecation handling becomes a frequent source of issues.

---

## Decision 9 — Connect-as-standalone-product gating (locked 2026-05-18)

**Status:** simplified from three-signal version to single-signal gate.

**Target section in architecture.md:** new note in the four-component model section (the existing OTA Connect description) or in a small "Future Productization Gate" sub-section.

**Locked:**
- Build Connect with clean boundaries from day one (versioned vocabulary, no internal back-doors that bypass the capability layer, schema-validated bindings, etc.).
- **Don't invest in Connect-as-standalone-product infrastructure (public docs, SDK polish, conformance test suite, adapter scaffolding CLI, marketing site, governance model) until at least one external party (client, dev team, framework) has explicitly asked for it.**
- One trigger, no date.
- The discipline of "this could be a standalone product later" is what keeps you from cutting corners that lock OTA into a corner. The discipline of "don't ship it until pulled" is what keeps you focused on the consultancy.

---

## Decision 10 — Per-client change report on every Core/Connect update (locked 2026-05-18)

**Status:** reframed from "separate system" to "lightweight report view over snapshot test data."

**Target section in architecture.md:** sub-section under "Update Lifecycle" (the section created by Decision 3).

**Locked:**
- Every Core/Connect update generates a per-client report of *behavior changes* relevant to that client.
- Report is a view / query over the snapshot test data produced by 3a, scoped by the client's installed routines and adapter mix.
- Report shows behavior deltas (what would change for them), not raw code diffs.
- Routines unaffected by the update are not mentioned. Most reports will be mostly empty — that's the right shape.
- Operator-facing first (so Omar can decide whether to push the update for that client). Client-facing version can be derived as a polish layer later.

---

## All 10 decisions locked (2026-05-18). Ready for architecture.md merge pass.
- Decision 5 — Canary cohorts for Mode 3 rollouts
- Decision 6 — Multi-binding v1.0 = default + override only (purpose-based deferred)
- Decision 7 — Bindings at capability granularity with adapter-level shorthand
- Decision 8 — Three-response policy for upstream API deprecation
- Decision 9 — Connect-as-standalone is 2027, gated on three signals
- Decision 10 — "What changed for this client" report on every Core update
