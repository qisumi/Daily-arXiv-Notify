from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.clients.openai_client import OpenAIClient
from app.config import Settings
from app.db import Database
from app.models import ArxivPaper, KeywordFilterResult, PaperSummaryResult
from app.output_language import localize_output_text, output_language_slug


class SummarizeService:
    BASE_PROMPT_VERSION = "paper-summary-v2"

    def __init__(self, settings: Settings, database: Database, llm_client: OpenAIClient) -> None:
        self.settings = settings
        self.database = database
        self.llm_client = llm_client
        self.logger = logging.getLogger(__name__)

    @property
    def prompt_version(self) -> str:
        return f"{self.BASE_PROMPT_VERSION}-{output_language_slug(self.settings.llm.output_language)}"

    def summarize_paper(
        self,
        *,
        run_id: int,
        paper_id: int,
        paper: ArxivPaper,
        ai_result: KeywordFilterResult,
    ) -> PaperSummaryResult:
        cached = self.database.get_cached_summary(
            paper_id=paper_id,
            model_name=self.settings.llm.summarize_model,
            prompt_version=self.prompt_version,
        )
        if cached is not None:
            self.database.insert_summary(
                run_id=run_id,
                paper_id=paper_id,
                summary=cached,
                model_name=self.settings.llm.summarize_model,
                prompt_version=self.prompt_version,
                created_at=datetime.now(timezone.utc),
            )
            return cached

        try:
            summary = self.llm_client.summarize_paper(
                title=paper.title,
                abstract=paper.summary,
            )
        except Exception:
            self.logger.exception("AI summarization failed for %s", paper.arxiv_id)
            summary = self._fallback_summary(paper, ai_result)

        self.database.insert_summary(
            run_id=run_id,
            paper_id=paper_id,
            summary=summary,
            model_name=self.settings.llm.summarize_model,
            prompt_version=self.prompt_version,
            created_at=datetime.now(timezone.utc),
        )
        return summary

    def _fallback_summary(
        self,
        paper: ArxivPaper,
        ai_result: KeywordFilterResult,
    ) -> PaperSummaryResult:
        abstract = paper.summary.strip()
        one_line = abstract[:220].rstrip()
        if len(abstract) > 220:
            one_line += "..."
        matched = ", ".join(ai_result.matched_keywords) or "configured keywords"
        return PaperSummaryResult(
            one_line=one_line,
            problem=abstract[:400].rstrip() or paper.title,
            method=localize_output_text(
                self.settings.llm.output_language,
                english="Unavailable because the fallback uses the raw abstract only.",
                chinese="该字段不可用，因为回退摘要只能直接使用原始 abstract。",
            ),
            why_it_matters=localize_output_text(
                self.settings.llm.output_language,
                english=f"The paper matched {matched}.",
                chinese=f"这篇论文命中了以下关键词：{matched}。",
            ),
            limitations=localize_output_text(
                self.settings.llm.output_language,
                english=(
                    "Fallback summary generated without a successful LLM call. "
                    "The content may remain in the paper's original language."
                ),
                chinese=(
                    "未能成功调用 LLM，因此使用了回退摘要。"
                    "内容可能保留论文原始语言。"
                ),
            ),
            tags=ai_result.matched_keywords,
        )
