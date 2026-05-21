from __future__ import annotations

from typing import Any

from ota_connect.binding.dispatch import dispatch_capability


def dispatch(verb_name: str, **kwargs: Any) -> Any:
    return dispatch_capability("email", verb_name, **kwargs)
