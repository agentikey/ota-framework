from __future__ import annotations

from typing import Any, NoReturn


def dispatch(verb_name: str, **kwargs: Any) -> NoReturn:
    """Placeholder. Phase 3.5 (capability dispatch layer) wires this to:
    binding resolution -> adapter invocation -> error normalization -> audit emit.
    """
    raise NotImplementedError(
        f"ota_connect.email.dispatch({verb_name!r}, ...) "
        "not wired yet; see build-plan-v0.md §5.4 work package 3.5"
    )
