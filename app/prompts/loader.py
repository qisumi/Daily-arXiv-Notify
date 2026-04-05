from __future__ import annotations

from functools import lru_cache
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent


class PromptError(RuntimeError):
    """Base error for prompt template loading and rendering."""


class PromptNotFoundError(PromptError, FileNotFoundError):
    """Raised when a requested prompt template file does not exist."""


class PromptRenderError(PromptError):
    """Raised when a prompt template cannot be rendered with provided variables."""


class _StrictVariables(dict[str, str]):
    def __missing__(self, key: str) -> str:
        raise PromptRenderError(f"Missing prompt variable: {key}")


@lru_cache(maxsize=None)
def load_prompt_template(name: str) -> str:
    path = PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise PromptNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def render_prompt(name: str, **variables: str) -> str:
    template = load_prompt_template(name)
    return template.format_map(_StrictVariables(variables)).strip()
