from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.clients.openai_client import OpenAIClient
from app.config import Settings
from app.db import Database
from app.models import ArxivPaper, KeywordFilterResult, RuleFilterResult


class FilterService:
    PROMPT_VERSION = "keyword-filter-v1"

    def __init__(self, settings: Settings, database: Database, llm_client: OpenAIClient) -> None:
        self.settings = settings
        self.database = database
        self.llm_client = llm_client
        self.logger = logging.getLogger(__name__)

    def evaluate_paper(
        self,
        *,
        run_id: int,
        paper_id: int,
        paper: ArxivPaper,
    ) -> tuple[RuleFilterResult, KeywordFilterResult]:
        rule_result = self.apply_rule_filter(paper)

        if not rule_result.matched:
            ai_result = KeywordFilterResult(
                is_related=False,
                matched_keywords=[],
                reason="Skipped AI keyword filter because the rule filter rejected the paper.",
            )
            self.database.insert_evaluation(
                run_id=run_id,
                paper_id=paper_id,
                rule_match=False,
                rule_reason=rule_result.reason,
                ai_result=ai_result,
                evaluated_keywords=self.settings.target_keywords,
                model_name=self.settings.llm.classify_model,
                prompt_version=self.PROMPT_VERSION,
                created_at=datetime.now(timezone.utc),
            )
            return rule_result, ai_result

        cached = self.database.get_cached_evaluation(
            paper_id=paper_id,
            evaluated_keywords=self.settings.target_keywords,
            model_name=self.settings.llm.classify_model,
            prompt_version=self.PROMPT_VERSION,
        )
        if cached is not None:
            self.database.insert_evaluation(
                run_id=run_id,
                paper_id=paper_id,
                rule_match=rule_result.matched,
                rule_reason=rule_result.reason,
                ai_result=cached,
                evaluated_keywords=self.settings.target_keywords,
                model_name=self.settings.llm.classify_model,
                prompt_version=self.PROMPT_VERSION,
                created_at=datetime.now(timezone.utc),
            )
            return rule_result, cached

        try:
            ai_result = self.llm_client.classify_paper(
                keywords=self.settings.target_keywords,
                title=paper.title,
                abstract=paper.summary,
            )
        except Exception as exc:
            self.logger.exception("AI keyword classification failed for %s", paper.arxiv_id)
            ai_result = self._fallback_keyword_match(paper, exc)

        self.database.insert_evaluation(
            run_id=run_id,
            paper_id=paper_id,
            rule_match=rule_result.matched,
            rule_reason=rule_result.reason,
            ai_result=ai_result,
            evaluated_keywords=self.settings.target_keywords,
            model_name=self.settings.llm.classify_model,
            prompt_version=self.PROMPT_VERSION,
            created_at=datetime.now(timezone.utc),
        )
        return rule_result, ai_result

    def apply_rule_filter(self, paper: ArxivPaper) -> RuleFilterResult:
        text = f"{paper.title}\n{paper.summary}".lower()
        include_keywords = [
            keyword
            for keyword in self.settings.filtering.include_keywords
            if keyword.lower() in text
        ]
        excluded_keywords = [
            keyword
            for keyword in self.settings.filtering.exclude_keywords
            if keyword.lower() in text
        ]

        if excluded_keywords:
            return RuleFilterResult(
                matched=False,
                reason=f"Excluded by keywords: {', '.join(excluded_keywords)}",
                matched_keywords=include_keywords,
                excluded_keywords=excluded_keywords,
            )

        if self.settings.filtering.include_keywords and not include_keywords:
            return RuleFilterResult(
                matched=False,
                reason="No include keywords matched in title or abstract.",
            )

        if include_keywords:
            reason = f"Matched include keywords: {', '.join(include_keywords)}"
        else:
            reason = "Passed rule filter because no include keywords are configured."

        return RuleFilterResult(
            matched=True,
            reason=reason,
            matched_keywords=include_keywords,
        )

    def _fallback_keyword_match(
        self,
        paper: ArxivPaper,
        error: Exception,
    ) -> KeywordFilterResult:
        text = f"{paper.title}\n{paper.summary}".lower()
        matched = [
            keyword
            for keyword in self.settings.target_keywords
            if keyword.lower() in text
        ]
        reason = (
            "LLM request failed; used lexical fallback on title and abstract. "
            f"Original error: {error}"
        )
        return KeywordFilterResult(
            is_related=bool(matched),
            matched_keywords=matched,
            reason=reason,
        )
