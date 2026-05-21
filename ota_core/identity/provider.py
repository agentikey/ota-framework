from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from ota_core.identity.errors import (
    IdentityAdapterMismatchError,
    IdentityAdapterMissingError,
    IdentityNotFoundError,
    IdentityProviderError,
    MalformedIdentityRefError,
)
from ota_core.storage.markdown import read_markdown

IdentityRefKind = Literal["handle", "mailto", "raw"]


@dataclass(frozen=True)
class Person:
    handle: str
    display_name: str
    emails: tuple[str, ...] = ()
    adapters: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedIdentityRef:
    kind: IdentityRefKind
    handle: str | None = None
    email: str | None = None
    raw_adapter: str | None = None
    raw_id: str | None = None


def parse_identity_ref(ref: str) -> ParsedIdentityRef:
    if ref.startswith("handle:"):
        body = ref[len("handle:") :]
        if not body:
            raise MalformedIdentityRefError(ref, "empty handle")
        handle = body.lstrip("@")
        if not handle:
            raise MalformedIdentityRefError(ref, "handle is empty after stripping '@'")
        return ParsedIdentityRef(kind="handle", handle=handle)
    if ref.startswith("mailto:"):
        email = ref[len("mailto:") :]
        if "@" not in email:
            raise MalformedIdentityRefError(ref, "mailto: payload is not an email address")
        return ParsedIdentityRef(kind="mailto", email=email)
    if ref.startswith("raw:"):
        body = ref[len("raw:") :]
        if ":" not in body:
            raise MalformedIdentityRefError(ref, "raw: payload must be '<adapter>:<id>'")
        adapter, _, adapter_id = body.partition(":")
        if not adapter or not adapter_id:
            raise MalformedIdentityRefError(ref, "raw: requires both adapter and id")
        return ParsedIdentityRef(kind="raw", raw_adapter=adapter, raw_id=adapter_id)
    raise MalformedIdentityRefError(ref, "unrecognized prefix; expected handle:/mailto:/raw:")


@runtime_checkable
class IdentityProvider(Protocol):
    def resolve(self, ref: str, *, adapter: str) -> str: ...

    def resolve_email(self, ref: str) -> str: ...

    def people(self) -> list[Person]: ...

    def get(self, handle: str) -> Person | None: ...


class _RosterIdentityProvider:
    def __init__(self, roster: Mapping[str, Person]) -> None:
        self._roster: dict[str, Person] = {p.handle: p for p in roster.values()}

    def resolve(self, ref: str, *, adapter: str) -> str:
        parsed = parse_identity_ref(ref)
        if parsed.kind == "handle":
            assert parsed.handle is not None
            person = self._roster.get(parsed.handle)
            if person is None:
                raise IdentityNotFoundError(
                    handle=parsed.handle,
                    candidates=list(self._roster.keys()),
                )
            mapped = person.adapters.get(adapter)
            if mapped is None:
                raise IdentityAdapterMissingError(
                    handle=parsed.handle,
                    adapter=adapter,
                    available=list(person.adapters.keys()),
                )
            return mapped
        if parsed.kind == "mailto":
            assert parsed.email is not None
            return parsed.email
        if parsed.kind == "raw":
            assert parsed.raw_adapter is not None and parsed.raw_id is not None
            if parsed.raw_adapter != adapter:
                raise IdentityAdapterMismatchError(
                    ref_adapter=parsed.raw_adapter,
                    bound_adapter=adapter,
                )
            return parsed.raw_id
        raise IdentityProviderError(f"unreachable: unknown parsed kind {parsed.kind!r}")

    def resolve_email(self, ref: str) -> str:
        parsed = parse_identity_ref(ref)
        if parsed.kind == "mailto":
            assert parsed.email is not None
            return parsed.email
        if parsed.kind == "handle":
            assert parsed.handle is not None
            person = self._roster.get(parsed.handle)
            if person is None:
                raise IdentityNotFoundError(
                    handle=parsed.handle,
                    candidates=list(self._roster.keys()),
                )
            if not person.emails:
                raise IdentityAdapterMissingError(
                    handle=parsed.handle,
                    adapter="email",
                    available=list(person.adapters.keys()),
                )
            return person.emails[0]
        raise IdentityProviderError(f"cannot resolve email from {parsed.kind} ref: {ref!r}")

    def people(self) -> list[Person]:
        return list(self._roster.values())

    def get(self, handle: str) -> Person | None:
        return self._roster.get(handle.lstrip("@"))


class InMemoryIdentityProvider(_RosterIdentityProvider):
    def __init__(self, people: Iterable[Person]) -> None:
        super().__init__({p.handle: p for p in people})


class LocalMarkdownIdentityProvider(_RosterIdentityProvider):
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path).expanduser()
        super().__init__(_load_roster(self._path))

    @property
    def path(self) -> Path:
        return self._path

    def reload(self) -> None:
        self._roster = {p.handle: p for p in _load_roster(self._path).values()}


def _load_roster(path: Path) -> dict[str, Person]:
    if not path.exists():
        raise IdentityProviderError(f"identity roster not found: {path}")
    doc = read_markdown(path)
    schema_version = doc.frontmatter.get("schema_version")
    if not schema_version:
        raise IdentityProviderError(f"missing schema_version in {path}")
    raw_people = doc.frontmatter.get("people")
    if raw_people is None:
        raw_people = []
    if not isinstance(raw_people, list):
        raise IdentityProviderError(f"'people' must be a list in {path}, got {type(raw_people)!r}")
    out: dict[str, Person] = {}
    seen_handles: set[str] = set()
    for idx, entry in enumerate(raw_people):
        if not isinstance(entry, dict):
            raise IdentityProviderError(
                f"people[{idx}] must be a mapping in {path}, got {type(entry)!r}"
            )
        handle = entry.get("handle")
        if not isinstance(handle, str) or not handle:
            raise IdentityProviderError(f"people[{idx}].handle missing or empty in {path}")
        handle = handle.lstrip("@")
        if handle in seen_handles:
            raise IdentityProviderError(f"duplicate handle {handle!r} in {path}")
        seen_handles.add(handle)
        display_name = entry.get("display_name", handle)
        emails = entry.get("emails", []) or []
        if not isinstance(emails, list) or not all(isinstance(e, str) for e in emails):
            raise IdentityProviderError(f"people[{idx}].emails must be list[str] in {path}")
        adapters = entry.get("adapters", {}) or {}
        if not isinstance(adapters, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in adapters.items()
        ):
            raise IdentityProviderError(f"people[{idx}].adapters must be dict[str,str] in {path}")
        out[handle] = Person(
            handle=handle,
            display_name=display_name,
            emails=tuple(emails),
            adapters=dict(adapters),
        )
    return out
