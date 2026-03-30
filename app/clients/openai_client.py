from __future__ import annotations

from textwrap import dedent
from typing import Any

from openai import OpenAI

from app.config import LLMSettings
from app.models import KeywordFilterResult, PaperSummaryResult


class OpenAIClient:
    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        self._client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
        )

    def classify_paper(
        self,
        *,
        keywords: list[str],
        title: str,
        abstract: str,
    ) -> KeywordFilterResult:
        messages = self._build_keyword_filter_messages(
            keywords=keywords,
            title=title,
            abstract=abstract,
        )
        return self._parse_structured_output(
            model=self.settings.classify_model,
            messages=messages,
            schema=KeywordFilterResult,
            operation_name="classification",
        )

    def summarize_paper(self, *, title: str, abstract: str) -> PaperSummaryResult:
        messages = self._build_summary_messages(title=title, abstract=abstract)
        return self._parse_structured_output(
            model=self.settings.summarize_model,
            messages=messages,
            schema=PaperSummaryResult,
            operation_name="summarization",
        )

    def _parse_structured_output(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        schema: type[Any],
        operation_name: str,
    ) -> Any:
        if self.settings.api_mode == "responses":
            response = self._client.responses.parse(
                model=model,
                input=messages,
                text_format=schema,
            )
            if response.output_parsed is None:  # pragma: no cover
                raise RuntimeError(f"OpenAI {operation_name} returned no parsed output.")
            return response.output_parsed

        if self.settings.api_mode == "chat_completions":
            response = self._client.beta.chat.completions.parse(
                model=model,
                messages=messages,
                response_format=schema,
            )
            parsed = response.choices[0].message.parsed
            if parsed is None:  # pragma: no cover
                raise RuntimeError(f"OpenAI {operation_name} returned no parsed output.")
            return parsed

        raise RuntimeError(f"Unsupported API mode: {self.settings.api_mode}")

    def _build_keyword_filter_messages(
        self,
        *,
        keywords: list[str],
        title: str,
        abstract: str,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": dedent(
                    """
                    You determine whether a research paper is related to configured keywords.
                    Use only the provided title and abstract.
                    Do not judge paper quality, novelty, or importance.
                    Return matched keywords only when there is a clear connection.
                    """
                ).strip(),
            },
            {
                "role": "user",
                "content": dedent(
                    f"""
                    Target keywords:
                    {", ".join(keywords)}

                    Paper title:
                    {title}

                    Paper abstract:
                    {abstract}
                    """
                ).strip(),
            },
        ]

    def _build_summary_messages(
        self,
        *,
        title: str,
        abstract: str,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": dedent(
                    """
                    Summarize the research paper using only the provided title and abstract.
                    Be concise and factual.
                    If the abstract does not support a detail, say so instead of guessing.
                    """
                ).strip(),
            },
            {
                "role": "user",
                "content": dedent(
                    f"""
                    Paper title:
                    {title}

                    Paper abstract:
                    {abstract}
                    """
                ).strip(),
            },
        ]
