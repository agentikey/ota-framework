# AUTO-GENERATED from vocabulary/_types.md -- DO NOT EDIT.
# Run `python scripts/gen_vocab_stubs.py` to regenerate.

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class Block:
    kind: Literal["text", "section", "header", "divider", "actions", "image", "code"]
    text: str | None = None  # plain-text content / fallback rendering
    children: list[Block] | None = None
    actions: list[Action] | None = None
    image_ref: FileRef | None = None
    language: str | None = None  # for kind="code"


@dataclass(frozen=True)
class Action:
    kind: Literal["button", "select", "link"]
    label: str
    value: str  # opaque payload the framework routes back to the routine
    style: Literal["default", "primary", "danger"] = "default"
    options: list[str] | None = None  # for kind="select"


FileRef = str  # canonical form
# Accepted string forms:
#   "local:<absolute_path>"        framework-local file (filesystem under deployment)
#   "storage:<adapter>:<path>"     e.g. "storage:gdrive:/Marketing/logo.png"


@dataclass(frozen=True)
class Attachment:
    file: FileRef
    display_name: str  # name shown to recipient
    mime_type: str | None = None  # framework infers from file extension if None
    inline: bool = False  # for emails: inline-rendered (cid) vs. attached
