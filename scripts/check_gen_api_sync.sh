#!/usr/bin/env bash
# Enforces the OpenAPI -> TypeScript codegen drift check per build-plan §3.3.
# No-op until BOTH ota_dashboard_web/ exists AND pnpm is installed AND
# node_modules has been populated (`pnpm install`). The CI workflow always has
# pnpm + node_modules, so the drift check is enforced there.

set -euo pipefail

if [ ! -d ota_dashboard_web/node_modules ] || ! command -v pnpm >/dev/null 2>&1; then
  echo "gen-api-sync: skipped (run 'pnpm install' inside ota_dashboard_web/ to enable)"
  exit 0
fi

cd ota_dashboard_web
pnpm gen-api
git diff --exit-code -- src/api/generated
