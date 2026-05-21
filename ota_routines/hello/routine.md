---
schema_version: "1.0.0"
id: ota.hello
version: 0.1.0
framework_compat: ">=0.1.0"
metadata:
  name: Hello
  description: Phase 2 tracer-bullet routine — proves framework wiring end-to-end.
  author: OTA
  author_url: https://example.com
  category: test
  tags: [tracer-bullet, internal]
dependencies:
  routines: []
  integrations: []
capabilities:
  provides: []
  consumes: []
llm_requirements:
  schema_version: "1.0.0"
  required: []
  preferred: []
  pii_categories: [none]
knobs:
  - name: target
    type: string
    default: world
    description: The greeting target passed to the say_hello capability.
automation:
  cadence: []
  events: []
gates: []
state:
  shards: []
artifacts:
  stale_artifact_ttl: 4h
files:
  - path: system.md
    role: system_prompt
    sha256: 549d03aad10783b23dc5d3c422e2ae4b526470f7da79933663237b38cf39beb1
  - path: helpers.py
    role: asset
    sha256: b391f640712be1dafa57e0a4ff5737ffa6a075074ee0139c514f006447816189
signature:
  algorithm: ed25519
  key_id: local-filesystem
  value: trusted-by-filesystem-source
  signed_fields:
    - id
    - version
    - framework_compat
---

# Hello

The Phase 2 tracer-bullet routine. Its only job is to call the `say_hello`
capability once and return the result so the integration test can prove the
framework wired everything correctly.
