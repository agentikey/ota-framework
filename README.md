# OTA: One True Agent

Markdown-first AI agent framework. Routines are markdown files that compose
framework primitives (`ota_core`) with pluggable integration adapters
(`ota_connect`). v0.1 ships an email-triage routine over Slack + Gmail for
first-client delivery.

## Status

Phase 1 (Foundation) complete: 11 work packages from
[docs/build-plan-v0.md](docs/build-plan-v0.md) §5.2 landed. 80 tests pass;
ruff + mypy clean. Phase 2 (framework runtime + seams) is next.

Carry-forward items for later phases:
[docs/phase-1-notes.md](docs/phase-1-notes.md).

## Architecture at a glance

Four components on one codebase. Full architecture in
[docs/architecture.md](docs/architecture.md).

| Component | Role |
| --- | --- |
| `ota_core/` | Framework engine: conductor, routine engine, L0a/L0b policy layer, storage (SQLite WAL + markdown projection), audit, observability, identity, secrets, LLM provider seam, HTTP client. |
| `ota_connect/` | Capability adapter library. Routines invoke `ota_connect.<capability>.<verb>(...)`; the binding layer resolves to a concrete adapter at runtime. Capability vocabulary in [`vocabulary/`](vocabulary/). |
| `ota_routines/` | Per-client routines. v0.1 has `email_triage`. |
| `ota_dashboard_api/` | FastAPI backend for the operator dashboard. Frontend (`ota_dashboard_web/`) lands in Phase 4C. |

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
  messaging/verbs.py  # Generated from vocabulary/messaging.md
  email/verbs.py      # Generated from vocabulary/email.md
ota_routines/         # Bundled routines (email_triage)
ota_dashboard_api/    # FastAPI backend (real implementation lands in Phase 4C)
vocabulary/           # Capability vocabulary specs (source of truth)
scripts/              # Codegen tools
docs/                 # Architecture, contracts, build plan, phase notes
tests/                # Mirrors the source tree
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
- [docs/phase-1-notes.md](docs/phase-1-notes.md): Phase 1 carry-forward
  items.
- [vocabulary/](vocabulary/): capability vocabulary specs (`_types.md`,
  `messaging.md`, `email.md`, `_roster.md`).

## License

Proprietary. Internal use only; no redistribution. Full license terms ship
with each delivery (build-plan §11).
