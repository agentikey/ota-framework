"""Export the dashboard API's OpenAPI schema to disk.

Used by the frontend `@hey-api/openapi-ts` codegen step. Writes a complete
OpenAPI 3 JSON document derived from the live FastAPI app.

Run via `python scripts/gen_openapi.py` or `just gen-api`.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ota_core.audit import FileAuditReader
from ota_dashboard_api import DashboardState, create_app

OUTPUT = Path(__file__).resolve().parent.parent / "ota_dashboard_web" / "openapi.json"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    state = DashboardState(audit_reader=FileAuditReader(tmp))
    app = create_app(state)
    schema = app.openapi()
    OUTPUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
