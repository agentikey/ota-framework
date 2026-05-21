from __future__ import annotations

from typing import Any

from ota_connect.binding.dispatch import dispatch_capability


def dispatch(verb_name: str, **kwargs: Any) -> Any:
    """Forwards `ota_connect.messaging.<verb>(...)` to the capability layer.

    The generated `verbs.py` calls `dispatch("send_message", **locals())`;
    `locals()` already contains the verb's keyword arguments. We strip the
    routine-only first positional values that landed in locals() — there are
    none in the current vocabulary; every messaging verb passes only its
    declared kwargs.
    """
    return dispatch_capability("messaging", verb_name, **kwargs)
