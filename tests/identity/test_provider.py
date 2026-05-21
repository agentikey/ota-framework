from __future__ import annotations

from pathlib import Path

import pytest

from ota_core.identity import (
    IdentityAdapterMismatchError,
    IdentityAdapterMissingError,
    IdentityNotFoundError,
    IdentityProvider,
    IdentityProviderError,
    InMemoryIdentityProvider,
    LocalMarkdownIdentityProvider,
    MalformedIdentityRefError,
    Person,
    parse_identity_ref,
)


def _omar() -> Person:
    return Person(
        handle="omar",
        display_name="Omar",
        emails=("omar@example.com",),
        adapters={"slack_socket": "U12345", "gmail_oauth": "omar@example.com"},
    )


def _jamie() -> Person:
    return Person(
        handle="jamie",
        display_name="Jamie",
        emails=("jamie@example.com",),
        adapters={"slack_socket": "U67890"},
    )


def test_parse_handle_ref() -> None:
    assert parse_identity_ref("handle:@omar").handle == "omar"
    assert parse_identity_ref("handle:omar").handle == "omar"


def test_parse_mailto_ref() -> None:
    assert parse_identity_ref("mailto:omar@example.com").email == "omar@example.com"


def test_parse_raw_ref() -> None:
    parsed = parse_identity_ref("raw:slack_socket:U99999")
    assert parsed.kind == "raw"
    assert parsed.raw_adapter == "slack_socket"
    assert parsed.raw_id == "U99999"


@pytest.mark.parametrize(
    "ref,reason_part",
    [
        ("xxx:nope", "unrecognized prefix"),
        ("handle:", "empty"),
        ("handle:@", "empty"),
        ("mailto:notanemail", "not an email"),
        ("raw:slack_socket", "<adapter>:<id>"),
        ("raw:slack_socket:", "both adapter and id"),
        ("raw::U123", "both adapter and id"),
    ],
)
def test_parse_malformed_refs(ref: str, reason_part: str) -> None:
    with pytest.raises(MalformedIdentityRefError) as exc:
        parse_identity_ref(ref)
    assert reason_part in str(exc.value)


def test_in_memory_provider_satisfies_protocol() -> None:
    provider: IdentityProvider = InMemoryIdentityProvider([_omar()])
    assert isinstance(provider, IdentityProvider)


def test_resolve_handle_to_slack() -> None:
    provider = InMemoryIdentityProvider([_omar()])
    assert provider.resolve("handle:@omar", adapter="slack_socket") == "U12345"


def test_resolve_handle_to_gmail() -> None:
    provider = InMemoryIdentityProvider([_omar()])
    assert provider.resolve("handle:@omar", adapter="gmail_oauth") == "omar@example.com"


def test_resolve_unknown_handle_raises_with_candidates() -> None:
    provider = InMemoryIdentityProvider([_omar(), _jamie()])
    with pytest.raises(IdentityNotFoundError) as exc:
        provider.resolve("handle:@ghost", adapter="slack_socket")
    assert exc.value.handle == "ghost"
    assert set(exc.value.candidates) == {"omar", "jamie"}


def test_resolve_adapter_missing_raises_with_available() -> None:
    provider = InMemoryIdentityProvider([_jamie()])
    with pytest.raises(IdentityAdapterMissingError) as exc:
        provider.resolve("handle:@jamie", adapter="gmail_oauth")
    assert "slack_socket" in exc.value.available


def test_resolve_mailto_returns_email_directly() -> None:
    provider = InMemoryIdentityProvider([])
    assert provider.resolve("mailto:any@example.com", adapter="gmail_oauth") == "any@example.com"


def test_resolve_raw_matching_adapter() -> None:
    provider = InMemoryIdentityProvider([])
    assert provider.resolve("raw:slack_socket:U99999", adapter="slack_socket") == "U99999"


def test_resolve_raw_adapter_mismatch_raises() -> None:
    provider = InMemoryIdentityProvider([])
    with pytest.raises(IdentityAdapterMismatchError) as exc:
        provider.resolve("raw:slack_socket:U99999", adapter="gmail_oauth")
    assert exc.value.ref_adapter == "slack_socket"
    assert exc.value.bound_adapter == "gmail_oauth"


def test_resolve_email_via_handle_uses_first_email() -> None:
    provider = InMemoryIdentityProvider([_omar()])
    assert provider.resolve_email("handle:@omar") == "omar@example.com"


def test_resolve_email_handle_with_no_emails_raises() -> None:
    provider = InMemoryIdentityProvider([Person(handle="x", display_name="X")])
    with pytest.raises(IdentityAdapterMissingError):
        provider.resolve_email("handle:@x")


def test_resolve_email_from_raw_ref_raises() -> None:
    provider = InMemoryIdentityProvider([])
    with pytest.raises(IdentityProviderError):
        provider.resolve_email("raw:slack_socket:U1")


def test_get_handle_strips_at_sign() -> None:
    provider = InMemoryIdentityProvider([_omar()])
    assert provider.get("@omar") is not None
    assert provider.get("omar") is not None
    assert provider.get("ghost") is None


def test_local_markdown_loader(tmp_path: Path) -> None:
    path = tmp_path / "people.md"
    path.write_text(
        """---
schema_version: "1.0"
people:
  - handle: omar
    display_name: Omar
    emails: [omar@example.com]
    adapters:
      slack_socket: U12345
      gmail_oauth: omar@example.com
  - handle: jamie
    display_name: Jamie
    emails: [jamie@example.com]
    adapters:
      slack_socket: U67890
---

# People
Notes about the team.
""",
        encoding="utf-8",
    )
    provider = LocalMarkdownIdentityProvider(path)
    assert provider.resolve("handle:@omar", adapter="slack_socket") == "U12345"
    assert provider.resolve_email("handle:@jamie") == "jamie@example.com"
    assert {p.handle for p in provider.people()} == {"omar", "jamie"}


def test_local_markdown_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(IdentityProviderError, match="not found"):
        LocalMarkdownIdentityProvider(tmp_path / "missing.md")


def test_local_markdown_missing_schema_raises(tmp_path: Path) -> None:
    path = tmp_path / "people.md"
    path.write_text("---\npeople: []\n---\n", encoding="utf-8")
    with pytest.raises(IdentityProviderError, match="schema_version"):
        LocalMarkdownIdentityProvider(path)


def test_local_markdown_duplicate_handle_raises(tmp_path: Path) -> None:
    path = tmp_path / "people.md"
    path.write_text(
        """---
schema_version: "1.0"
people:
  - handle: omar
  - handle: omar
---
""",
        encoding="utf-8",
    )
    with pytest.raises(IdentityProviderError, match="duplicate handle"):
        LocalMarkdownIdentityProvider(path)


def test_local_markdown_reload(tmp_path: Path) -> None:
    path = tmp_path / "people.md"
    path.write_text(
        '---\nschema_version: "1.0"\npeople:\n  - handle: omar\n---\n', encoding="utf-8"
    )
    provider = LocalMarkdownIdentityProvider(path)
    assert provider.get("omar") is not None
    path.write_text(
        '---\nschema_version: "1.0"\npeople:\n  - handle: jamie\n---\n', encoding="utf-8"
    )
    provider.reload()
    assert provider.get("omar") is None
    assert provider.get("jamie") is not None
