---
module: _roster
version: 1.0.0
status: draft
description: Capability roster for OTA Connect — what's designed, what's prioritized for v1.0, what's deferred to v1.1, and what's explicitly out of scope.
---

# OTA Connect — Capability Roster Sketch

Index of all capabilities planned for OTA Connect, organized by release tier. Each entry is intentionally brief — deep design lives in the per-capability spec file. This roster is the blueprint for design sequencing and the source of truth for what `ota_connect.*` namespaces are expected to exist at each version milestone.

---

## Tier 1 — v1.0 cornerstones (DESIGNED, LOCKED)

These two capabilities are fully specified and locked. They serve as the reference implementations for spec format, error taxonomy, and adapter conformance patterns.

### `ota_connect.messaging`
**Scope:** Real-time, event-driven chat orchestration across team workspaces and DMs. Renders interactive HITL gates via `Block` + `Action` callbacks.
**Spec:** `vocabulary/messaging.md` (locked 2026-05-18)
**Adapters (v1.0):** `slack_socket_adapter`, `telegram_polling_adapter`
**Verbs:** `send_message`, `edit_message`, `delete_message`, `read_thread`, `list_recent_messages`
**Key event:** `integration.messaging.action_triggered`

### `ota_connect.email`
**Scope:** Asynchronous, multi-recipient routing with RFC-header threading, draft staging, and label-based mailbox indexing.
**Spec:** `vocabulary/email.md` (locked 2026-05-18)
**Adapters (v1.0):** `gmail_oauth_adapter`, `exchange_365_adapter`, `native_smtp_imap_adapter`
**Verbs:** `send_email`, `create_draft`, `send_draft`, `delete_email`, `list_mailbox`, `read_email_thread`, `modify_email_labels`, `mark_read`, `mark_unread`
**Key events:** `bounce_received`, `reply_received`, `delivery_confirmed`, `auto_response_received`

---

## Tier 2 — v1.0 priority (DESIGN PENDING)

These were selected as v1.0 priorities during scoping. Pressure-tested against the inbound-lead-qualifier scenario; both are load-bearing for it. Should be designed before any v1.0 release.

### `ota_connect.crm`
**Scope:** Read/upsert/log activity against contact, company, and deal records in customer relationship management systems.
**Likely adapters:** `hubspot_adapter`, `salesforce_adapter`, `pipedrive_adapter`, `attio_adapter`, `copper_adapter`, `zoho_crm_adapter`
**Verb sketch:**
- `find_contact`, `upsert_contact`, `list_contacts`
- `find_company`, `upsert_company`
- `find_deal`, `upsert_deal`, `list_pipeline`
- `log_activity` (call, email, meeting, note)
- `get_contact_properties`, `list_contact_property_schema`
**Hard parts:**
- **Custom property schemas vary wildly per CRM tenant** — every system has user-defined fields. Abstraction has to expose "give me the value of the `priority` field on this contact" without knowing the field exists. Likely solution: dynamic property accessor (`contact.get_property("priority")`) backed by a runtime schema probe.
- Pipeline / deal stage structures differ per platform.
- Activity types are partially platform-specific (Salesforce's task vs. event vs. log call vs. log email).
**New types likely needed in `_types.md`:** `ContactRef`, `CompanyRef`, `DealRef`, `ActivityRef`, `PropertySchema`

### `ota_connect.calendar`
**Scope:** Read availability, list events, create/update/cancel events across calendar systems. Handles multi-participant availability checks and meeting proposal flows.
**Likely adapters:** `google_calendar_adapter`, `microsoft_365_calendar_adapter`, `cal_com_adapter`, `calendly_adapter` (limited write)
**Verb sketch:**
- `list_events`, `get_event`
- `check_availability` (multi-participant)
- `find_available_slots` (filter by participant, range, duration)
- `create_event`, `update_event`, `cancel_event`
- `propose_meeting_times` (multi-step coordination)
- `respond_to_invite` (accept / decline / tentative)
**Hard parts:**
- **Recurring events are notoriously complex** (RRULE, exceptions, EXDATEs). v1.0 should treat recurring events as read-only and force routines to operate on single instances.
- Timezone handling — DST transitions, floating events, all-day events, multi-zone participants.
- Reschedule semantics across participants (cascade update vs. cancel-and-recreate).
- Calendly is read-mostly for many operations vs. Google's full read-write surface — `calendly_adapter` will declare `CapabilityDegraded` for many writes.
**New types likely needed:** `EventRef`, `AvailabilityWindow`, `MeetingProposal`

---

## Tier 3 — v1.1 candidates (NOT v1.0)

Useful but not required for the first wave of routines. Defer until v1.0 ships and real client demand surfaces.

### `ota_connect.enrichment`
**Scope:** Lookup company and person data via third-party enrichment APIs. Heavy in sales / qualifier routines.
**Likely adapters:** `apollo_adapter`, `hunter_adapter`, `clearbit_adapter`, `crunchbase_adapter`, `zoominfo_adapter`, `lusha_adapter`
**Verb sketch:** `enrich_person`, `enrich_company`, `find_email_for_person`, `list_company_employees`
**Hard parts:**
- Rate limits and credit accounting differ enormously per provider — abstraction must surface budget / credit state to routines so they can degrade gracefully.
- Data freshness and quality vary; abstraction can't paper over "Apollo says X, Hunter says Y."
- Privacy / compliance implications per region (GDPR, CCPA) — adapter manifest should declare data residency.
**Why deferred:** the inbound qualifier scenario can launch without enrichment (criteria-based filtering on submitted form data alone). Add when a routine needs it.

### `ota_connect.document_storage`
**Scope:** Read, write, search, and create documents in knowledge platforms.
**Likely adapters:** `notion_adapter`, `gdrive_docs_adapter`, `confluence_adapter`, `dropbox_paper_adapter`, `onedrive_docs_adapter`
**Verb sketch:** `read_doc`, `search_docs`, `create_doc`, `update_doc`, `append_to_doc`, `list_docs_in_space`, `create_child_page`
**Hard parts:**
- **Block schema variation** — Notion's block tree is rich and nested; Google Docs is paragraph-based; Confluence uses its own XML-ish ADF format. Designing a portable content type that survives translation is non-trivial. May need a `DocBlock` type distinct from `Block` to handle hierarchical content.
- Permission models differ.
- Comments, mentions, embeds — explicit non-goals for v1.1; revisit in v1.2 if demand exists.
**Why deferred:** non-trivial design; v1.0 routines can write to a single client-bound canonical location (e.g., one specific Notion page ID) without abstraction.

### `ota_connect.task_management`
**Scope:** Create, update, list, and complete tasks in project management tools.
**Likely adapters:** `asana_adapter`, `linear_adapter`, `jira_adapter`, `clickup_adapter`, `monday_adapter`, `trello_adapter`, `github_issues_adapter`
**Verb sketch:** `create_task`, `update_task`, `complete_task`, `list_tasks`, `find_task`, `get_task`, `assign_task`, `add_subtask`, `list_projects`, `get_project`
**Hard parts:**
- Custom fields per project (parallel to CRM property problem).
- Workflow / state machine differs (Jira's complex transitions vs. Linear's strict cycle states vs. Asana's flexible custom statuses).
- Hierarchy semantics differ — subtasks, epics, milestones, sprints don't map cleanly across platforms.
**Why deferred:** v1.0 ops routines can use messaging or email for assignment digest rather than direct task-tool integration.

---

## Tier 4 — future / under consideration

Capabilities that may be added when client demand pulls. No design work until then. Listed here so they don't get accidentally invented mid-roster.

| Capability | One-line scope | Likely adapters | When to design |
|---|---|---|---|
| `file_storage` | Read/write/list files in cloud storage. | `gdrive`, `dropbox`, `box`, `onedrive`, `s3` | When a routine needs more than `FileRef` reference passing (e.g., must list directory contents). |
| `knowledge_base` | Search and retrieve from indexed knowledge content. | `notion_search`, `confluence_search`, `glean`, `pinecone`, `chroma`, `weaviate` | When a routine needs RAG-style retrieval beyond document_storage read. May merge with `document_storage`. |
| `voice_transcription` | Transcribe and summarize recorded calls / meetings. | `fireflies`, `otter`, `granola`, `whisper_self_hosted` | When a routine has a meeting-recording-to-CRM pipeline. |
| `ticketing` | Customer support ticket management. | `zendesk`, `intercom`, `freshdesk`, `helpscout` | When a routine touches customer support flows. May merge with `task_management`. |
| `analytics` | Read product / behavioral analytics. | `mixpanel`, `amplitude`, `segment`, `ga4` | When a routine needs to read event metrics. |
| `payments` | Create / read payment records. | `stripe`, `square` | When a routine touches billing or revenue ops. |
| `form` | Form / survey data ingestion. | `typeform`, `google_forms`, `tally`, `airtable_forms` | When a routine ingests structured form submissions beyond what messaging / email captures. |
| `social` | Cross-platform social posting / DM. | `linkedin`, `x`, `mastodon`, `bluesky` | When a routine touches outbound social. Adapter availability is sketchy; prioritize accordingly. |

---

## Explicitly NOT capabilities

These look like they might belong in the Connect vocabulary but don't — they're handled at other layers of the framework. Listed here so they don't get accidentally added.

- **`identity`** — Identity resolution is the **IdentityProvider seam** in the framework architecture. It's framework-internal infrastructure that capabilities consume via `IdentityRef`, not a user-facing capability namespace. Routines never call `ota_connect.identity.*`.
- **`secrets`** — Same pattern as identity. The **SecretsProvider seam** handles credential storage / rotation; capabilities consume credentials transparently via their bound adapter. Routines never see secrets.
- **`scheduling`** — Handled by the **Automation layer** in the architecture (cron triggers, event hooks). Not a capability; it's how routines get woken up.
- **`state`** / **`memory`** — Framework primitive backed by L4 SQLite per the architecture. Routines read / write state via framework APIs, not a Connect capability.
- **`audit`** / **`observability`** — Handled by the **AuditSink** and **ObservabilitySink** seams. Capabilities emit events into these sinks automatically; routines don't author audit logic.
- **`approval`** — Composed pattern (messaging `Action` + state machine + identity), not a standalone capability. Routines build approval flows on top of `messaging` + framework state.

---

## Cross-capability conventions (locked across all specs)

These patterns emerged from designing `messaging` and `email`. Lock them now so subsequent capabilities don't drift.

**Verb naming taxonomy:**

| Prefix | Use | Returns | Example |
|---|---|---|---|
| `send_*` | Outbound write that delivers off-system. | Asset ref (e.g., `MessageRef`) | `send_message`, `send_email`, `send_draft` |
| `create_*` | Stages a new object inside the system. | Asset ref | `create_draft`, `create_event` |
| `update_*` / `edit_*` | Mutates an existing object. | New asset ref (frozen) | `edit_message`, `update_event` |
| `delete_*` | Removes an object. `destructive: true`. | `None` | `delete_message`, `delete_email` |
| `read_*` | Fetches a known-ID resource or thread. | Concrete object or `Page[T]` | `read_thread`, `read_email_thread` |
| `list_*` | Paginated query for many. | `Page[T]` | `list_recent_messages`, `list_mailbox` |
| `find_*` | Single-result query by criteria. | Single object or `None` | `find_contact`, `find_deal` |
| `get_*` | Single-result fetch by exact ID. | Single object; raises if not found. | `get_event`, `get_task` |
| `upsert_*` | Create-or-update by natural key. | Asset ref | `upsert_contact`, `upsert_company` |
| `mark_*` | State-toggle on an existing object. | `None` | `mark_read`, `mark_unread` |
| `modify_*` | Batch mutation (often many-to-many). | `None` or partial-status dict | `modify_email_labels` |

**Universal contract pieces:**

- Every verb declares `idempotency: guaranteed | best_effort | unsupported` in its metadata block.
- Every verb declares `required_scopes: list[str]` (framework-abstract tokens; mapped to platform scopes via Contract D).
- Every verb declares `destructive: bool`. `true` flags trigger the linter / cost meter; gating remains a routine-layer concern.
- Every verb that returns multiple results uses `Page[T]` with `Cursor` pagination.
- Every verb raises errors from the `OTAConnectError` hierarchy in `_types.md`.
- Every verb that accepts a `datetime` enforces timezone-aware values; naive datetimes raise `ValueError` at the framework boundary.
- Every capability with async receive-side semantics (messaging actions, email bounces / replies) documents its event taxonomy in a dedicated section at the top of the spec, referencing Contract B for event registry alignment.

---

## v1.0 release definition (proposed cutoff)

To ship v1.0 of OTA Connect, the following are required:

1. **Tier 1 specs locked** — ✅ `messaging` + `email`
2. **Tier 2 specs designed and locked** — ⬜ `crm` + `calendar` (pending — next sessions)
3. **`_types.md` complete** — ✅ for messaging/email types; needs additions for CRM (`ContactRef`, `CompanyRef`, `DealRef`, `ActivityRef`, `PropertySchema`) and calendar (`EventRef`, `AvailabilityWindow`, `MeetingProposal`)
4. **Per-capability conformance test scaffolding** — ⬜ deferred to a dedicated session after Tier 2 specs land
5. **At least one adapter implementing each Tier 1 + Tier 2 capability** — out of scope for spec design; tracked in adapter delivery roadmap
6. **Cross-capability invariants documented** in `architecture.md` — pending architecture merge pass

Anything in Tier 3 or Tier 4 is explicitly **post-v1.0** and should not block release.

---

## Changelog

- **1.0.0 (2026-05-18)** — Initial roster. Two capabilities designed (Tier 1). Two on deck (Tier 2). Three deferred to v1.1 (Tier 3). Eight cataloged as future (Tier 4). Cross-capability naming conventions captured. v1.0 release definition proposed.
