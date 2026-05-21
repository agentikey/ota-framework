"""Bindings — per-client capability → adapter map.

Bindings are part of the deployment configuration (Contract E) but live in
their own model because the dispatch layer resolves them at every call site.

Schema:

    bindings:
      capabilities:
        messaging: slack
        messaging.send_email: gmail
        email: gmail

Resolution is longest-prefix-match (architecture §3 Connect Binding layer):
`messaging.send_message` falls through to the `messaging:` default;
`messaging.send_email` matches the more specific override.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_KEY_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$"


class Bindings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capabilities: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Map of capability or capability.verb prefix to adapter_id. "
            "Longest-prefix-match wins at resolve time."
        ),
    )

    def model_post_init(self, _context: object) -> None:
        import re

        compiled = re.compile(_KEY_PATTERN)
        for key in self.capabilities:
            if not compiled.match(key):
                raise ValueError(
                    f"binding key {key!r} must match {_KEY_PATTERN!r} "
                    "(lowercase, dotted; e.g. 'messaging' or 'messaging.send_email')"
                )
