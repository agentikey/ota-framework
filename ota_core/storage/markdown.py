from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_FRONTMATTER_FENCE = "---\n"


@dataclass(frozen=True)
class MarkdownDocument:
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""


def read_markdown(path: Path) -> MarkdownDocument:
    text = path.read_text(encoding="utf-8")
    if not text.startswith(_FRONTMATTER_FENCE):
        return MarkdownDocument(frontmatter={}, body=text)

    end = text.find(f"\n{_FRONTMATTER_FENCE}", len(_FRONTMATTER_FENCE))
    if end == -1:
        return MarkdownDocument(frontmatter={}, body=text)

    raw_frontmatter = text[len(_FRONTMATTER_FENCE) : end]
    body = text[end + len(_FRONTMATTER_FENCE) + 1 :]

    parsed = yaml.safe_load(raw_frontmatter) or {}
    if not isinstance(parsed, dict):
        raise ValueError(
            f"frontmatter in {path} must be a YAML mapping; got {type(parsed).__name__}"
        )
    return MarkdownDocument(frontmatter=parsed, body=body)


def write_markdown(path: Path, doc: MarkdownDocument) -> None:
    parts: list[str] = []
    if doc.frontmatter:
        rendered = yaml.safe_dump(doc.frontmatter, sort_keys=False, allow_unicode=True)
        parts.extend([_FRONTMATTER_FENCE, rendered, _FRONTMATTER_FENCE])
    parts.append(doc.body)
    text = "".join(parts)

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise
