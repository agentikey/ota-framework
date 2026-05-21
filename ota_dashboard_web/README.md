# OTA Dashboard — frontend

Vite + React 19 + TypeScript + Tailwind v4 + shadcn-style components.

## First-time setup

```bash
cd ota_dashboard_web
pnpm install          # or npm install
pnpm gen-api          # generates src/api/generated/ from ../openapi.json
pnpm dev              # http://localhost:5173 — proxies /api → 127.0.0.1:8000
```

The OpenAPI schema (`openapi.json`) is generated from the FastAPI app via
`python scripts/gen_openapi.py` (or `just gen-api`).

## Scripts

| Script        | Purpose                                               |
| ------------- | ----------------------------------------------------- |
| `pnpm dev`    | Vite dev server with HMR + API proxy to FastAPI.      |
| `pnpm build`  | TypeScript build + Vite production bundle.            |
| `pnpm gen-api`| Regenerate `src/api/generated/` from `openapi.json`.  |
| `pnpm typecheck` | TS-only check (no emit).                           |

## Routes

| Path        | Page              | Backend                              |
| ----------- | ----------------- | ------------------------------------ |
| `/`         | Approval queue    | `GET /api/v1/approvals`              |
| `/audit`    | Audit log viewer  | `GET /api/v1/audit` (+ CSV export)   |
| `/why`      | Why drill-down    | `GET /api/v1/why/{email_id}`         |
| `/knobs`    | Knob editor       | `GET / POST /api/v1/routines/{id}/knobs` |
| `/fleet`    | Fleet placeholder | `GET /api/v1/fleet`                  |

The critical banner sits above the header and polls `/api/v1/notifications/banner`
every 10s.

## Phase 4 scope notes

This is the v0.1 skeleton — it ships every page wired to a real endpoint
with TanStack Query, but each surface is minimal. Polish (Tailwind theme,
shadcn block components, command palette, dark mode toggle) lands as
client-feedback comes in.
