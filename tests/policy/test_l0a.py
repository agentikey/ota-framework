from __future__ import annotations

from pathlib import Path

import pytest

from ota_core.policy import DEFAULT_L0A_BASE, L0aPromptBuilder


def test_default_render_contains_base() -> None:
    rendered = L0aPromptBuilder().render()
    assert "OTA" in rendered
    assert "Never fabricate" in rendered


def test_add_section_appears_after_base() -> None:
    rendered = L0aPromptBuilder().add("voice", "Concise, no exclamation marks.").render()
    assert rendered.startswith(DEFAULT_L0A_BASE.strip())
    assert "<voice>" in rendered
    assert "Concise, no exclamation marks." in rendered
    assert "</voice>" in rendered


def test_multiple_sections_preserve_order() -> None:
    builder = L0aPromptBuilder()
    builder.add("voice", "voice content")
    builder.add("principles", "principle content")
    rendered = builder.render()
    voice_idx = rendered.index("<voice>")
    principles_idx = rendered.index("<principles>")
    assert voice_idx < principles_idx


def test_custom_base_replaces_default() -> None:
    rendered = L0aPromptBuilder(base="Custom base.").render()
    assert "Custom base." in rendered
    assert "Never fabricate" not in rendered


def test_add_file_reads_disk(tmp_path: Path) -> None:
    voice = tmp_path / "voice.md"
    voice.write_text("Always lowercase.", encoding="utf-8")
    rendered = L0aPromptBuilder().add_file("voice", voice).render()
    assert "Always lowercase." in rendered


def test_add_empty_name_rejected() -> None:
    with pytest.raises(ValueError, match="section name cannot be empty"):
        L0aPromptBuilder().add("", "x")


def test_render_is_deterministic() -> None:
    a = L0aPromptBuilder().add("voice", "v").add("principles", "p").render()
    b = L0aPromptBuilder().add("voice", "v").add("principles", "p").render()
    assert a == b


def test_reset_clears_sections() -> None:
    builder = L0aPromptBuilder().add("voice", "v")
    builder.reset()
    rendered = builder.render()
    assert "<voice>" not in rendered


def test_default_base_constant_exposed() -> None:
    assert "OTA" in DEFAULT_L0A_BASE
