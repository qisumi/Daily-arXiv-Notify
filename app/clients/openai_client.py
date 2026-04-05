from __future__ import annotations

from pathlib import Path
from typing import Any

from openai import OpenAI

from app.config import LLMSettings
from app.models import KeywordFilterResult, PaperDetailResult, PaperSummaryResult
from app.output_language import normalize_output_language
from app.prompts.loader import render_prompt


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

    def analyze_paper_pdf(
        self,
        *,
        pdf_path: Path,
        title: str,
        abstract: str,
        matched_keywords: list[str],
        upload_expires_after_hours: int,
    ) -> PaperDetailResult:
        if self.settings.api_mode != "responses":
            raise RuntimeError("PDF detail analysis requires the Responses API endpoint.")

        with pdf_path.open("rb") as file_handle:
            uploaded_file = self._client.files.create(
                file=file_handle,
                purpose="user_data",
                expires_after={
                    "anchor": "created_at",
                    "seconds": upload_expires_after_hours * 3600,
                },
            )

        response = self._client.responses.parse(
            model=self.settings.effective_detail_model,
            input=self._build_detail_messages(
                title=title,
                abstract=abstract,
                matched_keywords=matched_keywords,
                file_id=uploaded_file.id,
            ),
            text_format=PaperDetailResult,
            reasoning={
                "effort": self.settings.effective_detail_reasoning_effort,
            },
        )
        if response.output_parsed is None:  # pragma: no cover
            raise RuntimeError("OpenAI detail analysis returned no parsed output.")
        return response.output_parsed

    def _parse_structured_output(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
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
        output_language = normalize_output_language(self.settings.output_language)
        return [
            {
                "role": "system",
                "content": render_prompt(
                    "keyword_filter_system",
                    output_language=output_language,
                ),
            },
            {
                "role": "user",
                "content": render_prompt(
                    "keyword_filter_user",
                    keywords=", ".join(keywords),
                    output_language=output_language,
                    title=title,
                    abstract=abstract,
                ),
            },
        ]

    def _build_summary_messages(
        self,
        *,
        title: str,
        abstract: str,
    ) -> list[dict[str, str]]:
        output_language = normalize_output_language(self.settings.output_language)
        return [
            {
                "role": "system",
                "content": render_prompt(
                    "paper_summary_system",
                    output_language=output_language,
                ),
            },
            {
                "role": "user",
                "content": render_prompt(
                    "paper_summary_user",
                    output_language=output_language,
                    title=title,
                    abstract=abstract,
                ),
            },
        ]

    def _build_detail_messages(
        self,
        *,
        title: str,
        abstract: str,
        matched_keywords: list[str],
        file_id: str,
    ) -> list[dict[str, Any]]:
        output_language = normalize_output_language(self.settings.output_language)
        keyword_text = ", ".join(matched_keywords) if matched_keywords else "None"
        return [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": render_prompt(
                            "paper_detail_system",
                            output_language=output_language,
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": render_prompt(
                            "paper_detail_user",
                            output_language=output_language,
                            title=title,
                            abstract=abstract,
                            matched_keywords=keyword_text,
                        ),
                    },
                    {
                        "type": "input_file",
                        "file_id": file_id,
                    },
                ],
            },
        ]
