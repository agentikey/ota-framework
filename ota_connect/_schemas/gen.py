"""Regenerate JSON Schemas under `ota_connect/_schemas/` from Pydantic models.

Run via `python -m ota_connect._schemas.gen`.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from ota_connect.binding.bindings import Bindings
from ota_core.integration_source.manifest import AdapterManifest


def _schemas_dir() -> Path:
    return Path(__file__).resolve().parent


def write_all() -> list[Path]:
    out: list[Path] = []
    targets: list[tuple[str, type[BaseModel]]] = [
        ("adapter_manifest.schema.json", AdapterManifest),
        ("bindings.schema.json", Bindings),
    ]
    for filename, model in targets:
        path = _schemas_dir() / filename
        schema = model.model_json_schema()
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        out.append(path)
    return out


def main() -> None:
    paths = write_all()
    for p in paths:
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
