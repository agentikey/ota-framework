from pathlib import Path

import pytest

from ota_core.storage import MarkdownDocument, read_markdown, write_markdown


def test_read_with_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(
        "---\ntitle: hello\ntags:\n  - one\n  - two\n---\n# Body\nBody text.\n",
        encoding="utf-8",
    )

    doc = read_markdown(path)

    assert doc.frontmatter == {"title": "hello", "tags": ["one", "two"]}
    assert doc.body == "# Body\nBody text.\n"


def test_read_no_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text("Just a body, no frontmatter.\n", encoding="utf-8")

    doc = read_markdown(path)

    assert doc.frontmatter == {}
    assert doc.body == "Just a body, no frontmatter.\n"


def test_read_rejects_non_mapping_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text("---\n- list\n- frontmatter\n---\nBody\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a YAML mapping"):
        read_markdown(path)


def test_roundtrip_preserves_content(tmp_path: Path) -> None:
    original = MarkdownDocument(
        frontmatter={"a": 1, "b": ["x", "y"], "c": {"d": True}},
        body="# Heading\n\nParagraph.\n",
    )
    path = tmp_path / "doc.md"

    write_markdown(path, original)
    parsed = read_markdown(path)

    assert parsed.frontmatter == original.frontmatter
    assert parsed.body == original.body


def test_write_atomic_no_tmp_leak(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    write_markdown(path, MarkdownDocument(frontmatter={"a": 1}, body="body"))

    leftovers = [
        p for p in tmp_path.iterdir() if p.name.startswith(".") and p.name.endswith(".tmp")
    ]
    assert leftovers == []


def test_write_creates_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "doc.md"
    assert not path.parent.exists()

    write_markdown(path, MarkdownDocument(body="hi"))

    assert path.exists()
    assert path.read_text(encoding="utf-8") == "hi"


def test_empty_frontmatter_skipped_on_write(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    write_markdown(path, MarkdownDocument(frontmatter={}, body="just body\n"))

    assert path.read_text(encoding="utf-8") == "just body\n"
