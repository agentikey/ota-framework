#!/usr/bin/env python3
"""Generate Python stubs from vocabulary/*.md per build-plan §3.4.

Reads:
  - <vocab>/_types.md   (shared reference types)
  - <vocab>/<capability>.md   (per-capability verbs)

Writes:
  - <out>/_types/__init__.py    (re-exports)
  - <out>/_types/<domain>.py    (dataclass definitions per domain)
  - <out>/<capability>/verbs.py (verb stubs decorated with @verb, calling dispatch)

Generated files carry an AUTO-GENERATED header and must not be hand-edited;
pre-commit hooks (work package 1.10) enforce this.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VOCAB_DIR = REPO_ROOT / "vocabulary"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "ota_connect"

# Maps an H3 type heading (with generic params stripped) to the output domain.
# The errors section is special: its H3 is "Hierarchy" and the python block
# contains the whole exception class tree as a single source.
TYPE_DOMAIN: dict[str, str] = {
    "IdentityRef": "identity",
    "MessageRef": "messaging",
    "ThreadRef": "messaging",
    "ChannelRef": "messaging",
    "EmailRef": "email",
    "EmailThreadRef": "email",
    "DraftRef": "email",
    "Block": "content",
    "Action": "content",
    "FileRef": "content",
    "Attachment": "content",
    "DeliveryStatus": "enums",
    "Importance": "enums",
    "Cursor": "pagination",
    "Page": "pagination",
    "Hierarchy": "errors",
}

DOMAIN_IMPORTS: dict[str, list[str]] = {
    "identity": [],
    "messaging": [
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "from datetime import datetime",
        "from typing import Literal",
    ],
    "email": [
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "from datetime import datetime",
    ],
    "content": [
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "from typing import Literal",
    ],
    "enums": [
        "from typing import Literal",
    ],
    "errors": [
        "from __future__ import annotations",
        "",
        "from datetime import timedelta",
    ],
    "pagination": [
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "from typing import Generic, TypeVar",
        "",
        'T = TypeVar("T")',
    ],
}

_H3_PATTERN = re.compile(r"^### (?:`([^`]+)`|(\w+))\s*$", re.MULTILINE)
_VERB_NAME_PATTERN = re.compile(r"^\w+$")


def _h3_name(match: re.Match[str]) -> str:
    return match.group(1) or match.group(2)


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end == -1:
        return "", text
    return text[4:end], text[end + 5 :]


def _extract_fenced_block(text: str, *, after: str, language: str) -> str | None:
    idx = text.find(after)
    if idx == -1:
        return None
    sub = text[idx + len(after) :]
    return _extract_first_fenced_block(sub, language=language)


def _extract_first_fenced_block(text: str, *, language: str) -> str | None:
    fence = f"```{language}"
    start = text.find(fence)
    if start == -1:
        return None
    body_start = text.find("\n", start) + 1
    end = text.find("\n```", body_start)
    if end == -1:
        return None
    return text[body_start:end]


def _strip_generic_params(name: str) -> str:
    return re.sub(r"\[.*\]$", "", name).strip()


def parse_types_md(path: Path) -> dict[str, list[str]]:
    """Returns mapping of output domain -> list of python source snippets in spec order.

    H3 headings of the form `### \\`TypeName\\`` are interpreted as type entries.
    Generic params in headings (e.g., `Page[T]`) are stripped for TYPE_DOMAIN lookup.
    The special H3 `Hierarchy` collects the entire python block into the errors domain.
    H3 sections without a python code block are skipped (e.g., subsection prose).
    """
    _, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    matches = list(_H3_PATTERN.finditer(body))

    by_domain: dict[str, list[str]] = {}
    for i, match in enumerate(matches):
        h3_name = _h3_name(match)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section = body[start:end]

        code = _extract_first_fenced_block(section, language="python")
        if code is None:
            continue

        base = _strip_generic_params(h3_name)
        domain = TYPE_DOMAIN.get(base)
        if domain is None:
            raise SystemExit(
                f"{path}: H3 type {h3_name!r} has no TYPE_DOMAIN mapping; "
                "update scripts/gen_vocab_stubs.py TYPE_DOMAIN"
            )
        by_domain.setdefault(domain, []).append(code.rstrip())

    return by_domain


def parse_capability_md(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    fm = yaml.safe_load(frontmatter) or {}

    capability = fm.get("capability")
    if not capability:
        raise SystemExit(f"{path}: frontmatter missing `capability` field")

    references_types = list(fm.get("references_types") or [])

    verbs_marker = "\n## Verbs\n"
    idx = body.find(verbs_marker)
    if idx == -1:
        raise SystemExit(f"{path}: missing `## Verbs` section")
    verbs_body = body[idx + len(verbs_marker) :]

    matches = list(_H3_PATTERN.finditer(verbs_body))
    verbs: list[dict[str, Any]] = []
    for i, match in enumerate(matches):
        verb_name = _h3_name(match)
        if not _VERB_NAME_PATTERN.match(verb_name):
            raise SystemExit(f"{path}: verb heading {verb_name!r} must be a Python identifier")
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(verbs_body)
        section = verbs_body[start:end]

        metadata_yaml = _extract_fenced_block(section, after="**Metadata:**", language="yaml")
        signature = _extract_fenced_block(section, after="**Signature:**", language="python")
        if metadata_yaml is None:
            raise SystemExit(f"{path}: verb {verb_name!r} missing **Metadata:** yaml block")
        if signature is None:
            raise SystemExit(f"{path}: verb {verb_name!r} missing **Signature:** python block")

        metadata = yaml.safe_load(metadata_yaml) or {}
        verbs.append(
            {
                "name": verb_name,
                "metadata": metadata,
                "signature": signature.rstrip(),
            }
        )

    return {
        "capability": capability,
        "references_types": references_types,
        "verbs": verbs,
    }


def _types_header(source_filename: str) -> list[str]:
    return [
        f"# AUTO-GENERATED from vocabulary/{source_filename} -- DO NOT EDIT.",
        "# Run `python scripts/gen_vocab_stubs.py` to regenerate.",
        "",
    ]


def _starts_with_definition(source: str) -> bool:
    for line in source.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        return stripped.startswith(("@", "def ", "class ", "async def "))
    return False


def generate_types_modules(by_domain: dict[str, list[str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for domain, sources in by_domain.items():
        lines: list[str] = [
            "# AUTO-GENERATED from vocabulary/_types.md -- DO NOT EDIT.",
            "# Run `python scripts/gen_vocab_stubs.py` to regenerate.",
        ]
        imports = DOMAIN_IMPORTS.get(domain, [])
        if imports:
            lines.append("")
            lines.extend(imports)
        for i, source in enumerate(sources):
            if i == 0:
                blanks = 2 if _starts_with_definition(source) else 1
            else:
                blanks = 2
            for _ in range(blanks):
                lines.append("")
            lines.append(source)
        out[f"{domain}.py"] = "\n".join(lines) + "\n"
    return out


def _public_names_in_module(domain: str, sources: list[str]) -> list[str]:
    if domain == "errors":
        names: list[str] = []
        for source in sources:
            names.extend(re.findall(r"^class (\w+)\b", source, re.MULTILINE))
        return names

    base_to_kept = {_strip_generic_params(n): n for n, d in TYPE_DOMAIN.items() if d == domain}
    found: list[str] = []
    for source in sources:
        for cls in re.findall(r"^class (\w+)\b", source, re.MULTILINE):
            if cls in base_to_kept:
                found.append(base_to_kept[cls])
        for alias in re.findall(r"^(\w+)\s*=", source, re.MULTILINE):
            if alias in base_to_kept:
                found.append(base_to_kept[alias])
    seen: set[str] = set()
    deduped: list[str] = []
    for name in found:
        if name not in seen:
            seen.add(name)
            deduped.append(name)
    return deduped


def generate_types_init(by_domain: dict[str, list[str]]) -> str:
    lines = _types_header("_types.md")
    all_names: list[str] = []
    for domain in sorted(by_domain):
        names = sorted(_public_names_in_module(domain, by_domain[domain]))
        if not names:
            continue
        if len(names) == 1:
            lines.append(f"from ota_connect._types.{domain} import {names[0]}")
        else:
            lines.append(f"from ota_connect._types.{domain} import (")
            for name in names:
                lines.append(f"    {name},")
            lines.append(")")
        all_names.extend(names)

    lines.append("")
    lines.append("__all__ = [")
    for name in sorted(all_names):
        lines.append(f'    "{name}",')
    lines.append("]")
    return "\n".join(lines) + "\n"


_RETURN_NONE_PATTERN = re.compile(r"->\s*None\s*:$")


def _signature_to_body(signature: str, *, verb_name: str) -> str:
    s = signature.rstrip()
    if not s.endswith("..."):
        raise SystemExit(
            f"signature for verb {verb_name!r} must end with `: ...`; got:\n{signature}"
        )
    s = s[:-3].rstrip()
    if not s.endswith(":"):
        raise SystemExit(f"signature for verb {verb_name!r} missing trailing colon")

    returns_none = bool(_RETURN_NONE_PATTERN.search(s))
    call = f'dispatch("{verb_name}", **locals())'
    if returns_none:
        return s + f"\n    {call}"
    return s + f"\n    return {call}"


_IDENT_PATTERN = re.compile(r"\b([A-Za-z_]\w*)\b")


def _identifiers_in_signatures(verbs: list[dict[str, Any]]) -> set[str]:
    used: set[str] = set()
    for v in verbs:
        for token in _IDENT_PATTERN.findall(v["signature"]):
            used.add(token)
    return used


def generate_verbs_module(parsed: dict[str, Any]) -> str:
    capability: str = parsed["capability"]
    references: list[str] = parsed["references_types"]
    verbs: list[dict[str, Any]] = parsed["verbs"]

    used = _identifiers_in_signatures(verbs)
    needed_refs = sorted(t for t in references if t in used)
    needs_datetime = "datetime" in used

    lines: list[str] = [
        f"# AUTO-GENERATED from vocabulary/{capability}.md -- DO NOT EDIT.",
        "# Run `python scripts/gen_vocab_stubs.py` to regenerate.",
        "",
        "from __future__ import annotations",
        "",
    ]
    if needs_datetime:
        lines.append("from datetime import datetime")
        lines.append("")
    if needed_refs:
        if len(needed_refs) == 1:
            lines.append(f"from ota_connect._types import {needed_refs[0]}")
        else:
            lines.append("from ota_connect._types import (")
            for ref in needed_refs:
                lines.append(f"    {ref},")
            lines.append(")")
    lines.append(f"from ota_connect.{capability}.dispatch import dispatch")
    lines.append("from ota_core.policy import verb")

    for v in verbs:
        name = v["name"]
        meta = v["metadata"]
        body = _signature_to_body(v["signature"], verb_name=name)

        idempotency = str(meta.get("idempotency", ""))
        required_scopes = [str(s) for s in (meta.get("required_scopes") or [])]
        destructive = bool(meta.get("destructive", False))

        scopes_repr = (
            "[]"
            if not required_scopes
            else "[" + ", ".join(f'"{s}"' for s in required_scopes) + "]"
        )

        lines.append("")
        lines.append("")
        lines.append("@verb(")
        lines.append(f'    idempotency="{idempotency}",')
        lines.append(f"    required_scopes={scopes_repr},")
        lines.append(f"    destructive={destructive},")
        lines.append(")")
        lines.append(body)

    return "\n".join(lines) + "\n"


def run(vocab_dir: Path, output_dir: Path) -> list[Path]:
    written: list[Path] = []

    types_md = vocab_dir / "_types.md"
    if not types_md.exists():
        raise SystemExit(f"{types_md} not found")

    types_by_domain = parse_types_md(types_md)
    types_dir = output_dir / "_types"
    types_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in generate_types_modules(types_by_domain).items():
        target = types_dir / filename
        target.write_text(content, encoding="utf-8")
        written.append(target)

    init_target = types_dir / "__init__.py"
    init_target.write_text(generate_types_init(types_by_domain), encoding="utf-8")
    written.append(init_target)

    for spec in sorted(vocab_dir.glob("*.md")):
        if spec.name.startswith("_"):
            continue
        parsed = parse_capability_md(spec)
        capability = parsed["capability"]
        target_dir = output_dir / capability
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "verbs.py"
        target.write_text(generate_verbs_module(parsed), encoding="utf-8")
        written.append(target)

    _ruff_format(written)
    return written


def _ruff_format(paths: list[Path]) -> None:
    if not paths:
        return
    try:
        subprocess.run(
            [sys.executable, "-m", "ruff", "format", *[str(p) for p in paths]],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("warning: ruff not available; skipping format pass", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vocabulary-dir",
        type=Path,
        default=DEFAULT_VOCAB_DIR,
        help="Directory containing vocabulary/*.md (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory rooted at the ota_connect package (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    written = run(args.vocabulary_dir.resolve(), args.output_dir.resolve())
    for path in written:
        try:
            display = path.relative_to(REPO_ROOT)
        except ValueError:
            display = path
        print(f"wrote {display}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
