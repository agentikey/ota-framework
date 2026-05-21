"""BindingResolver — longest-prefix-match (capability, verb) -> adapter_id.

Implements the resolution rule described in `docs/architecture.md` §3
"Connect — Binding layer":

    bindings:
      capabilities:
        messaging: slack
        messaging.send_email: gmail

`messaging.send_message` falls through to `messaging:`; `messaging.send_email`
matches the more specific override. Resolution is purely textual; no adapter
loading occurs in the resolver — that's the registry's job.
"""

from __future__ import annotations

from dataclasses import dataclass

from ota_connect.binding.bindings import Bindings
from ota_connect.binding.errors import NoBindingError


@dataclass(frozen=True)
class ResolvedBinding:
    capability: str
    verb: str
    adapter_id: str
    matched_key: str


class BindingResolver:
    def __init__(self, bindings: Bindings) -> None:
        self._bindings = bindings
        self._keys_by_length = sorted(bindings.capabilities.keys(), key=lambda k: (-len(k), k))

    @property
    def bindings(self) -> Bindings:
        return self._bindings

    def resolve(self, capability: str, verb: str) -> ResolvedBinding:
        target = f"{capability}.{verb}"
        for key in self._keys_by_length:
            if key == target or target.startswith(key + "."):
                return ResolvedBinding(
                    capability=capability,
                    verb=verb,
                    adapter_id=self._bindings.capabilities[key],
                    matched_key=key,
                )
            if key == capability:
                return ResolvedBinding(
                    capability=capability,
                    verb=verb,
                    adapter_id=self._bindings.capabilities[key],
                    matched_key=key,
                )
        raise NoBindingError(capability=capability, verb=verb)

    def try_resolve(self, capability: str, verb: str) -> ResolvedBinding | None:
        try:
            return self.resolve(capability, verb)
        except NoBindingError:
            return None
