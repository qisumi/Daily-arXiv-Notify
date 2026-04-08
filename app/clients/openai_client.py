from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.config import LLMSettings
from app.models import KeywordFilterResult, PaperDetailResult, PaperSummaryResult
from app.output_language import normalize_output_language
from app.prompts.loader import render_prompt


class OpenAIClient:
    FILE_READY_TIMEOUT_FLOOR_SECONDS = 120.0
    FILE_READY_POLL_SECONDS = 2.0
    FILE_READY_STATES = {"processed", "ready", "completed", "available"}
    FILE_PENDING_STATES = {"uploaded", "processing", "pending", "in_progress"}
    FILE_ERROR_STATES = {"error", "failed", "cancelled", "deleted", "expired"}

    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        self.logger = logging.getLogger(__name__)
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

        self._wait_for_uploaded_file(
            file_id=uploaded_file.id,
            uploaded_file=uploaded_file,
        )

        return self._parse_detail_response(
            title=title,
            abstract=abstract,
            matched_keywords=matched_keywords,
            file_id=uploaded_file.id,
        )

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

    def _parse_detail_response(
        self,
        *,
        title: str,
        abstract: str,
        matched_keywords: list[str],
        file_id: str,
    ) -> PaperDetailResult:
        for attempt in range(2):
            try:
                response = self._client.responses.parse(
                    model=self.settings.effective_detail_model,
                    input=self._build_detail_messages(
                        title=title,
                        abstract=abstract,
                        matched_keywords=matched_keywords,
                        file_id=file_id,
                    ),
                    text_format=PaperDetailResult,
                    reasoning={
                        "effort": self.settings.effective_detail_reasoning_effort,
                    },
                    timeout=self.settings.effective_detail_timeout_seconds,
                )
                if response.output_parsed is None:  # pragma: no cover
                    raise RuntimeError("OpenAI detail analysis returned no parsed output.")
                return response.output_parsed
            except Exception as exc:
                if attempt == 1 or not self._is_file_processing_error(exc):
                    raise
                self.logger.warning(
                    "Uploaded file %s is still processing after readiness check; retrying once.",
                    file_id,
                )
                self._wait_for_uploaded_file(file_id=file_id)

        raise RuntimeError("OpenAI detail analysis exhausted retry attempts.")  # pragma: no cover

    def _wait_for_uploaded_file(
        self,
        *,
        file_id: str,
        uploaded_file: Any | None = None,
    ) -> None:
        deadline = time.monotonic() + max(
            float(self.settings.effective_detail_timeout_seconds),
            self.FILE_READY_TIMEOUT_FLOOR_SECONDS,
        )
        file_object = uploaded_file
        retrieved_once = False

        while True:
            status = self._normalize_file_status(self._get_resource_field(file_object, "status"))
            if status in self.FILE_READY_STATES:
                return
            if status in self.FILE_ERROR_STATES:
                error_detail = self._get_resource_field(file_object, "status_details")
                if error_detail is None:
                    error_detail = self._get_resource_field(file_object, "last_error")
                detail_suffix = f": {error_detail}" if error_detail else ""
                raise RuntimeError(
                    f"Uploaded file {file_id} entered terminal state '{status}'{detail_suffix}."
                )

            if retrieved_once and status not in self.FILE_PENDING_STATES:
                return

            if time.monotonic() >= deadline:
                current_status = status or "unknown"
                raise TimeoutError(
                    f"Timed out waiting for uploaded file {file_id} to become ready "
                    f"(last status: {current_status})."
                )

            if retrieved_once:
                time.sleep(self.FILE_READY_POLL_SECONDS)

            file_object = self._client.files.retrieve(file_id)
            retrieved_once = True

    @classmethod
    def _normalize_file_status(cls, status: Any) -> str | None:
        if status is None:
            return None
        normalized = str(status).strip().lower()
        return normalized or None

    @staticmethod
    def _get_resource_field(resource: Any, field_name: str) -> Any:
        if resource is None:
            return None
        if isinstance(resource, Mapping):
            return resource.get(field_name)
        return getattr(resource, field_name, None)

    @staticmethod
    def _is_file_processing_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "processing" in message and (
            "file_id" in message
            or "invalid state" in message
            or "operationdenied.invalidstate" in message
        )
