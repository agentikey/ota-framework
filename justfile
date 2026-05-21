# OTA convenience commands. Run `just` (no args) for the list.

# Show all recipes.
default:
    @just --list

# One-time setup: create venv, install Python deps + dev extras, install pre-commit.
install:
    python3.12 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -e ".[dev]"
    .venv/bin/pre-commit install

# Run all Python tests.
test:
    .venv/bin/pytest

# Lint and format-check (read-only).
lint:
    .venv/bin/ruff check .
    .venv/bin/ruff format --check .

# Auto-fix lint issues and reformat in-place.
fix:
    .venv/bin/ruff check --fix .
    .venv/bin/ruff format .

# Type-check with mypy (strict).
typecheck:
    .venv/bin/mypy ota_core ota_connect ota_routines ota_dashboard_api

# Regenerate Python stubs from vocabulary/*.md (build-plan §3.4).
gen-vocab:
    .venv/bin/python scripts/gen_vocab_stubs.py

# Regenerate frontend types from FastAPI OpenAPI (Phase 4C.2; dormant until then).
gen-api:
    @if [ -d ota_dashboard_web ]; then cd ota_dashboard_web && pnpm gen-api; else echo "ota_dashboard_web/ not present yet (Phase 4C.2)"; fi

# Run the pre-commit gauntlet across the tree (codegen sync + hooks).
verify:
    .venv/bin/pre-commit run --all-files

# Full local CI: lint + type-check + test. Run before pushing.
ci: lint typecheck test

# Launch FastAPI + Vite dev server together. Ships in Phase 4 / 4C.
dev:
    @echo "just dev: FastAPI + Vite launcher ships in Phase 4."
    @exit 1

# Build the production Docker image. Ships in Phase 5.
build:
    @echo "just build: Dockerfile ships in Phase 5."
    @exit 1

# Remove generated caches (pytest, mypy, ruff, build artifacts). Does NOT touch .venv.
clean:
    rm -rf .pytest_cache .mypy_cache .ruff_cache build dist
    find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +
    find . -type d -name '*.egg-info' -not -path './.venv/*' -exec rm -rf {} +
