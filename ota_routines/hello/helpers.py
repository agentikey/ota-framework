from __future__ import annotations

from typing import Any


async def run(runtime: Any) -> dict[str, Any]:
    target = runtime.knobs.get("target", "world")
    greeting = runtime.call("say_hello", target)
    return {"greeted": target, "message": greeting}
