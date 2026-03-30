from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.clients.openai_client import OpenAIClient
from app.config import Settings
from app.db import Database
from app.models import ArxivPaper, KeywordFilterResult, PaperSummaryResult


class SummarizeService:
    PROMPT_VERSION = "paper-summary-v1"

    def __init__(self, settings: Settings, database: Database, llm_client: OpenAIClient) -> None:
        self.settings = settings
        self.database = database
        self.llm_client = llm_client
        self.logger = logging.getLogger(__name__)

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
            prompt_version=self.PROMPT_VERSION,
        )
        if cached is not None:
            self.database.insert_summary(
                run_id=run_id,
                paper_id=paper_id,
                summary=cached,
                model_name=self.settings.llm.summarize_model,
                prompt_version=self.PROMPT_VERSION,
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
            prompt_version=self.PROMPT_VERSION,
            created_at=datetime.now(timezone.utc),
        )
        return summary

    @staticmethod
    def _fallback_summary(
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
            method="Unavailable because the fallback uses the raw abstract only.",
            why_it_matters=f"The paper matched {matched}.",
            limitations="Fallback summary generated without a successful LLM call.",
            tags=ai_result.matched_keywords,
        )
