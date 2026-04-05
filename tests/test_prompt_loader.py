from __future__ import annotations

import pytest

from app.prompts.loader import PromptNotFoundError, PromptRenderError, load_prompt_template, render_prompt


def test_render_prompt_substitutes_variables_from_template_file() -> None:
    rendered = render_prompt(
        "keyword_filter_system",
        output_language="Chinese",
    )

    assert "Chinese" in rendered
    assert "{output_language}" not in rendered


def test_load_prompt_template_reads_external_prompt_file() -> None:
    template = load_prompt_template("paper_summary_user")

    assert "Paper title:" in template
    assert "{title}" in template


def test_render_prompt_raises_for_missing_variable() -> None:
    with pytest.raises(PromptRenderError, match="Missing prompt variable"):
        render_prompt("paper_summary_user", output_language="English", title="Test")


def test_load_prompt_template_raises_for_unknown_prompt() -> None:
    with pytest.raises(PromptNotFoundError):
        load_prompt_template("does_not_exist")
