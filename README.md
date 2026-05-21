# OTA: One True Agent

Codebase for the OTA framework (`ota_core`), the Connect adapter library
(`ota_connect`), bundled routines (`ota_routines`), and the operator dashboard
API (`ota_dashboard_api`). Capability vocabulary specs live in `vocabulary/`.

Source-of-truth docs in `docs/`:

- `architecture.md` — runtime architecture and locked decisions.
- `contracts.md` — Contracts A through E.
- `build-plan-v0.md` — first-client MVP build plan (active).
- `pending-architecture-updates.md` — decisions awaiting merge into `architecture.md`.

## Development setup

Requires Python 3.12.

```
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Convenience commands land in `justfile` (work package 1.11 in
`docs/build-plan-v0.md` §5.2).
