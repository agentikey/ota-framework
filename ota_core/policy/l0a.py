from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_L0A_BASE = """\
You operate inside the One True Agent (OTA) framework. Honor these always-on \
soft rules in every response. They are policy, not preference.

- Never fabricate. If you don't know, say so and ask the operator.
- Match the operator's declared voice and tone (provided as identity context).
- If confidence is below 95%, ask before acting. Surface ambiguity \
explicitly; do not silently pick a side.
- Never bypass declared gates, budgets, scopes, or kill switches.
- When a request maps to multiple plausible interpretations, name the \
alternatives and ask.\
"""


@dataclass
class L0aPromptBuilder:
    base: str = DEFAULT_L0A_BASE
    sections: list[tuple[str, str]] = field(default_factory=list)

    def add(self, name: str, content: str) -> L0aPromptBuilder:
        if not name:
            raise ValueError("section name cannot be empty")
        self.sections.append((name, content))
        return self

    def add_file(self, name: str, path: Path) -> L0aPromptBuilder:
        return self.add(name, path.read_text(encoding="utf-8"))

    def render(self) -> str:
        parts = [self.base.strip()]
        for name, content in self.sections:
            parts.append(f"<{name}>\n{content.strip()}\n</{name}>")
        return "\n\n".join(parts)

    def reset(self) -> L0aPromptBuilder:
        self.sections = []
        return self
