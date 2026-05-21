# OTA: One True Agent

Markdown-first AI agent framework. Routines are markdown files that compose
framework primitives (`ota_core`) with pluggable integration adapters
(`ota_connect`). v0.1 ships an email-triage routine over Slack + Gmail for
first-client delivery.

## Status

Phase 4 (Adapters + Routine + Dashboard) complete: all 22 work packages from
[docs/build-plan-v0.md](docs/build-plan-v0.md) §5.5 landed. Stream A: shared
OAuth helper (`ota_core/oauth/`), per-verb conformance harness
(`tests/vocabulary/`), full `slack_socket_adapter` (5 messaging verbs),
full `gmail_oauth_adapter` (9 email verbs, history-list inbound polling).
Stream B: complete `email_triage` routine — config schema, per-instance
SQLite state, three-tier `routine.md` + helpers, HITL gate primitives
(`ota_core/policy/gates.py`) with all three approval modes, trust-promotion
auto-send, criteria-drift detector. Stream C: FastAPI dashboard backend
(`ota_dashboard_api/`) with approval queue (HTTP + WebSocket), audit log
viewer + CSV export, `/why <email_id>`, knob editor, fleet, critical
banner; Vite + React 19 + TypeScript + Tailwind v4 frontend skeleton
(`ota_dashboard_web/`) with shadcn-style components for every surface.
439 tests pass; ruff clean; mypy clean on Phase 4 code. Phase 5 (Mode 2
deployment) is next.

Carry-forward items by phase:
[phase-1-notes.md](docs/phase-1-notes.md),
[phase-2-notes.md](docs/phase-2-notes.md),
[phase-3-notes.md](docs/phase-3-notes.md),
[phase-4-notes.md](docs/phase-4-notes.md).

## Architecture at a glance

Four components on one codebase. Full architecture in
[docs/architecture.md](docs/architecture.md).

| Component | Role |
| --- | --- |
| `ota_core/` | Framework engine: conductor, routine engine, L0a/L0b policy layer, HITL gates, storage (SQLite WAL + markdown projection), audit (write + read), observability, identity, secrets, OAuth, LLM provider seam, HTTP client. |
| `ota_connect/` | Capability adapter library. Routines invoke `ota_connect.<capability>.<verb>(...)`; the binding layer resolves to a concrete adapter at runtime. Ships `slack_socket_adapter` + `gmail_oauth_adapter` in v0.1. Capability vocabulary in [`vocabulary/`](vocabulary/). |
| `ota_routines/` | Per-client routines. v0.1 ships `email_triage` (three-tier Reader / Drafter / Auto with trust-promotion). |
| `ota_dashboard_api/` | FastAPI backend for the operator dashboard. |
| `ota_dashboard_web/` | Vite + React + TypeScript + Tailwind v4 frontend for the operator dashboard. |

Five canonical contracts wire these together:
[docs/contracts.md](docs/contracts.md).

## Getting started

Requires Python 3.12 and [just](https://github.com/casey/just)
(`brew install just` on macOS).

```bash
just install   # create venv, install deps + dev extras, install pre-commit
just ci        # lint + typecheck + test (mirrors GitHub Actions)
```

## Common commands

| Command | Purpose |
| --- | --- |
| `just test` | Run the Python test suite |
| `just lint` | Ruff check + format check (read-only) |
| `just fix` | Auto-fix lint and reformat in-place |
| `just typecheck` | Mypy in strict mode |
| `just gen-vocab` | Regenerate Python stubs from `vocabulary/*.md` |
| `just verify` | Pre-commit gauntlet across the tree |
| `just ci` | Full local CI (lint + typecheck + test) |
| `just clean` | Remove pytest / mypy / ruff caches |

`just dev`, `just build`, and `just gen-api` are stubs that activate in
Phase 4 (dev server), Phase 5 (Dockerfile), and Phase 4C.2 (OpenAPI codegen).

## Repo layout

```text
ota_core/             # Framework engine (sync API; async paths wrap in asyncio.to_thread)
ota_connect/          # Capability adapter library
  _types/             # Generated from vocabulary/_types.md
  _schemas/           # JSON Schemas exported for adapter authors (Phase 3.1)
  binding/            # Capability dispatch + binding layer (Phase 3)
  messaging/verbs.py  # Generated from vocabulary/messaging.md
  email/verbs.py      # Generated from vocabulary/email.md
ota_routines/         # Bundled routines (email_triage)
ota_dashboard_api/    # FastAPI backend (real implementation lands in Phase 4C)
vocabulary/           # Capability vocabulary specs (source of truth)
scripts/              # Codegen tools
docs/                 # Architecture, contracts, build plan, phase notes
tests/                # Mirrors the source tree
tests/fixtures/       # Mock adapters used in dispatch / install tests
```

## Codegen discipline

Generated files (`ota_connect/_types/*.py`,
`ota_connect/{messaging,email}/verbs.py`) are never hand-edited. Pre-commit
hooks regenerate from `vocabulary/*.md` on every commit and fail the commit
on drift. Workflow in [docs/build-plan-v0.md](docs/build-plan-v0.md) §3.4.

The same pattern applies to the dashboard's OpenAPI → TypeScript codegen
(§3.3); the hook is dormant until Phase 4C.2 creates `ota_dashboard_web/`.

## Source-of-truth docs

- [docs/architecture.md](docs/architecture.md): runtime architecture and
  locked decisions.
- [docs/contracts.md](docs/contracts.md): Contracts A through E (LLM
  requirements, audit events, routine source manifest, integration registry,
  deployment configuration).
- [docs/build-plan-v0.md](docs/build-plan-v0.md): active first-client MVP
  build plan: scope, sequencing, tech stack, operational model.
- [docs/pending-architecture-updates.md](docs/pending-architecture-updates.md):
  decisions awaiting merge into architecture.md.
- [docs/phase-1-notes.md](docs/phase-1-notes.md),
  [docs/phase-2-notes.md](docs/phase-2-notes.md),
  [docs/phase-3-notes.md](docs/phase-3-notes.md),
  [docs/phase-4-notes.md](docs/phase-4-notes.md): per-phase carry-forward
  items.
- [vocabulary/](vocabulary/): capability vocabulary specs (`_types.md`,
  `messaging.md`, `email.md`, `_roster.md`).

## License

Proprietary. Internal use only; no redistribution. Full license terms ship
with each delivery (build-plan §11).
