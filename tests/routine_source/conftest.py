from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_routine_dir(
    root: Path,
    *,
    routine_id: str = "ota.hello",
    version: str = "0.1.0",
    extra_files: dict[str, str] | None = None,
    manifest_format: str = "md",
    manifest_overrides: dict[str, Any] | None = None,
) -> Path:
    directory = root / routine_id.replace(".", "_")
    directory.mkdir(parents=True, exist_ok=True)

    files_entries: list[dict[str, str]] = []
    all_files: dict[str, str] = {"system.md": f"# {routine_id} system prompt\n"}
    if extra_files:
        all_files.update(extra_files)
    for rel, content in all_files.items():
        file_path = directory / rel
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        files_entries.append(
            {
                "path": rel,
                "role": "system_prompt" if rel.endswith(".md") else "asset",
                "sha256": _sha256(content.encode("utf-8")),
            }
        )

    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "id": routine_id,
        "version": version,
        "framework_compat": ">=0.1.0",
        "metadata": {
            "name": "Hello routine",
            "description": "v0.1 tracer-bullet routine",
            "author": "OTA",
            "author_url": "https://example.com",
            "category": "test",
            "tags": ["test"],
        },
        "dependencies": {"routines": [], "integrations": []},
        "capabilities": {"provides": [], "consumes": []},
        "llm_requirements": {
            "schema_version": "1.0.0",
            "required": [],
            "preferred": [],
            "pii_categories": ["none"],
        },
        "knobs": [],
        "automation": {"cadence": [], "events": []},
        "gates": [],
        "state": {"shards": []},
        "artifacts": {"stale_artifact_ttl": "4h"},
        "files": files_entries,
        "signature": {
            "algorithm": "ed25519",
            "key_id": "local-dev",
            "value": "filesystem",
            "signed_fields": ["id", "version"],
        },
    }
    if manifest_overrides:
        manifest = _deep_merge(manifest, manifest_overrides)

    if manifest_format == "md":
        body = "# " + routine_id + "\n\nTracer bullet routine body.\n"
        front = yaml.safe_dump(manifest, sort_keys=False)
        (directory / "routine.md").write_text(f"---\n{front}---\n\n{body}", encoding="utf-8")
    else:
        (directory / f"routine.{manifest_format}").write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
        )

    return directory


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
