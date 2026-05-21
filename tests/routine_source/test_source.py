from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ota_core.routine_source import (
    DuplicateRoutineError,
    FileIntegrityError,
    FilesystemRoutineSource,
    ManifestNotFoundError,
    RoutineBundleError,
    RoutineSource,
)
from tests.routine_source.conftest import make_routine_dir


def test_protocol_satisfaction(tmp_path: Path) -> None:
    source: RoutineSource = FilesystemRoutineSource(tmp_path)
    assert isinstance(source, RoutineSource)


def test_empty_root_lists_nothing(tmp_path: Path) -> None:
    src = FilesystemRoutineSource(tmp_path)
    assert src.list_ids() == []
    assert src.discover_all() == []


def test_missing_root_lists_nothing(tmp_path: Path) -> None:
    src = FilesystemRoutineSource(tmp_path / "nonexistent")
    assert src.list_ids() == []


def test_load_markdown_manifest(tmp_path: Path) -> None:
    make_routine_dir(tmp_path)
    src = FilesystemRoutineSource(tmp_path)
    bundle = src.load("ota.hello")
    assert bundle.id == "ota.hello"
    assert bundle.version == "0.1.0"
    assert bundle.manifest.metadata.name == "Hello routine"
    assert "# ota.hello" in bundle.body


def test_load_yaml_manifest(tmp_path: Path) -> None:
    make_routine_dir(tmp_path, manifest_format="yaml")
    src = FilesystemRoutineSource(tmp_path)
    bundle = src.load("ota.hello")
    assert bundle.id == "ota.hello"
    assert bundle.body == ""


def test_discover_all_returns_all_bundles(tmp_path: Path) -> None:
    make_routine_dir(tmp_path, routine_id="ota.a")
    make_routine_dir(tmp_path, routine_id="ota.b")
    src = FilesystemRoutineSource(tmp_path)
    bundles = src.discover_all()
    assert {b.id for b in bundles} == {"ota.a", "ota.b"}


def test_list_returns_routine_ids(tmp_path: Path) -> None:
    make_routine_dir(tmp_path, routine_id="ota.a")
    make_routine_dir(tmp_path, routine_id="ota.b")
    src = FilesystemRoutineSource(tmp_path)
    assert set(src.list_ids()) == {"ota.a", "ota.b"}


def test_load_unknown_routine_raises(tmp_path: Path) -> None:
    src = FilesystemRoutineSource(tmp_path)
    with pytest.raises(ManifestNotFoundError):
        src.load("ota.ghost")


def test_directory_without_manifest_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "notaroutine").mkdir()
    src = FilesystemRoutineSource(tmp_path)
    assert src.list_ids() == []


def test_invalid_manifest_yaml_raises(tmp_path: Path) -> None:
    d = tmp_path / "bad"
    d.mkdir()
    (d / "routine.yaml").write_text("- this is a list, not a mapping\n", encoding="utf-8")
    src = FilesystemRoutineSource(tmp_path)
    with pytest.raises(RoutineBundleError, match="must be a YAML mapping"):
        src.discover_all()


def test_markdown_manifest_without_frontmatter_raises(tmp_path: Path) -> None:
    d = tmp_path / "naked"
    d.mkdir()
    (d / "routine.md").write_text("# no frontmatter here\n", encoding="utf-8")
    src = FilesystemRoutineSource(tmp_path)
    with pytest.raises(RoutineBundleError, match="no YAML frontmatter"):
        src.discover_all()


def test_file_integrity_check_passes_when_hash_matches(tmp_path: Path) -> None:
    make_routine_dir(tmp_path, extra_files={"steps/greet.md": "hello world"})
    src = FilesystemRoutineSource(tmp_path)
    bundle = src.load("ota.hello")
    assert any(f.path == "steps/greet.md" for f in bundle.manifest.files)


def test_file_integrity_failure_when_file_modified(tmp_path: Path) -> None:
    directory = make_routine_dir(tmp_path, extra_files={"steps/greet.md": "hello world"})
    (directory / "steps" / "greet.md").write_text("tampered", encoding="utf-8")
    src = FilesystemRoutineSource(tmp_path)
    with pytest.raises(FileIntegrityError, match=r"steps/greet\.md"):
        src.load("ota.hello")


def test_file_integrity_failure_when_file_missing(tmp_path: Path) -> None:
    directory = make_routine_dir(tmp_path, extra_files={"steps/greet.md": "hello"})
    (directory / "steps" / "greet.md").unlink()
    src = FilesystemRoutineSource(tmp_path)
    with pytest.raises(FileIntegrityError, match="<missing>"):
        src.load("ota.hello")


def test_file_integrity_check_can_be_disabled(tmp_path: Path) -> None:
    directory = make_routine_dir(tmp_path, extra_files={"steps/greet.md": "hello"})
    (directory / "steps" / "greet.md").write_text("tampered", encoding="utf-8")
    src = FilesystemRoutineSource(tmp_path, verify_files=False)
    bundle = src.load("ota.hello")
    assert bundle.id == "ota.hello"


def test_duplicate_routine_id_detected(tmp_path: Path) -> None:
    first = make_routine_dir(tmp_path, routine_id="ota.x")
    # Create a second directory under the same root with the same routine id
    second = tmp_path / "ota_x_copy"
    import shutil

    shutil.copytree(first, second)
    src = FilesystemRoutineSource(tmp_path)
    with pytest.raises(DuplicateRoutineError, match=r"ota\.x"):
        src.discover_all()


def test_sha256_with_prefix_accepted(tmp_path: Path) -> None:
    body = "hello"
    directory = make_routine_dir(tmp_path, extra_files={"steps/greet.md": body})
    # Re-write manifest with sha256: prefix
    import yaml as _yaml

    manifest_path = directory / "routine.md"
    text = manifest_path.read_text(encoding="utf-8")
    _, front, body_md = text.split("---\n", 2)
    manifest = _yaml.safe_load(front)
    target_digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    for entry in manifest["files"]:
        if entry["path"] == "steps/greet.md":
            entry["sha256"] = f"sha256:{target_digest}"
    manifest_path.write_text(
        f"---\n{_yaml.safe_dump(manifest, sort_keys=False)}---\n{body_md}",
        encoding="utf-8",
    )
    src = FilesystemRoutineSource(tmp_path)
    bundle = src.load("ota.hello")
    greet = next(f for f in bundle.manifest.files if f.path == "steps/greet.md")
    assert greet.sha256.startswith("sha256:")
