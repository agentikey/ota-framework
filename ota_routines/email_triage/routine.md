---
schema_version: "1.0.0"
id: ota.email-triage
version: 0.1.0
framework_compat: ">=0.1.0"
metadata:
  name: Email Triage
  description: |
    Three-tier email triage routine. Reader classifies inbound mail; Drafter
    fills a per-category reply template; Auto-send promotes a template to
    fully-automated only after the operator has approved 20 in-a-row
    un-edited drafts for it.
  author: OTA
  author_url: https://example.com
  category: productivity
  tags: [email, hitl, trust-promotion]
dependencies:
  routines: []
  integrations:
    - id: gmail.com
      scopes:
        - email:read
        - email:send
        - email:modify
      binding_level: identity_bound
      on_emergency_kill: revoke_routine_grant
    - id: slack.com
      scopes:
        - messaging:send
        - messaging:read
      binding_level: client_shared
      on_emergency_kill: revoke_routine_access
capabilities:
  provides: []
  consumes:
    - email
    - messaging
llm_requirements:
  schema_version: "1.0.0"
  required: [tool_use, prompt_caching]
  preferred: [streaming]
  min_context_tokens: 200000
  cost_tier: balanced
  pii_categories: [contact_info, identifiers, communications]
knobs:
  - name: operator_first_name
    type: string
    default: Omar
    description: Used in template signatures.
  - name: config
    type: string
    default: ""
    description: |
      The per-client configuration object, validated against
      config.schema.yaml at install time. JSON-encoded.
automation:
  cadence:
    - id: poll
      cron: "*/2 * * * *"
      timezone: operator
      action: run
  events: []
gates:
  - id: draft_review
    description: Operator review of a Drafter-produced reply before sending.
    kind: preview
    approval_modes: [approve, tune_and_approve, approve_and_remember]
    similarity_function: per_recipient_template
    expires_after: PT24H
state:
  shards: []
artifacts:
  stale_artifact_ttl: 24h
files:
  - path: system.md
    role: system_prompt
    sha256: 4cadcc211199e51dcbbda54c08f51e8c21544a96f390a39609b7532586a6f0ad
  - path: run.py
    role: asset
    sha256: 92f661b610efcb71fb6f8186a5aa12099d6630aad669ddd75152c1f44f8ed34b
  - path: helpers.py
    role: asset
    sha256: 5067d248ee3a23156a76a95aefebe3d6c83b5925706302efb67fe4f881f42deb
  - path: state.py
    role: asset
    sha256: 76c1265d4d7152bf44b0775c2cf0dfc315345c6b2552484dca41e81ba5fdb109
  - path: config.schema.yaml
    role: asset
    sha256: 94aaa4ad54293b5127a9cab1d86fd8753fbdb1e69ff7567a74578e84fcaab45a
  - path: templates/inquiry.md
    role: gate_template
    sha256: 3f880d50f6f25e93a03a8cedf9b5bfe74a1cfde4c2a7aa3f487f8caa431c9685
  - path: templates/booking.md
    role: gate_template
    sha256: 63f0fa558d57cb180a583151b3f21ddf7577ab13118f0ffb5cc53bb7fe0f5eb2
  - path: templates/follow_up.md
    role: gate_template
    sha256: 87c72d30061d97fa58c13fb6aa3b0eb6ce5363f1587f14ae9141c867ff8c9526
  - path: prompts/classifier.md
    role: step
    sha256: 53196d58fd6571edcc0c0cb19af9e5391773e4c12fbeef2c03109418ab17b760
  - path: prompts/drafter.md
    role: step
    sha256: 7329c399fa4002b6a4e611bcbc8cc683d6af0b49e86f6f6480160e9c8bed21b8
signature:
  algorithm: ed25519
  key_id: local-filesystem
  value: trusted-by-filesystem-source
  signed_fields:
    - id
    - version
    - framework_compat
---

# email_triage

Three-tier email triage routine. Reads inbound mail, drafts replies in the
operator's voice via per-category templates, and (once trust is established)
sends without manual approval.

See `system.md` for the model-facing system prompt and `run.py` for the
runtime entrypoint.
