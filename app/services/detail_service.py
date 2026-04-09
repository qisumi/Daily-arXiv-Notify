from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from app.clients.arxiv_client import ArxivClient
from app.clients.openai_client import OpenAIClient
from app.config import Settings
from app.db import Database
from app.detail_source import is_pdf_detail_source
from app.models import ArxivPaper, KeywordFilterResult, PaperDetailResult, PaperSummaryResult
from app.output_language import localize_output_text, output_language_slug


class DetailService:
    BASE_PROMPT_VERSION = "paper-detail-v2"

    def __init__(
        self,
        settings: Settings,
        database: Database,
        llm_client: OpenAIClient,
        arxiv_client: ArxivClient,
    ) -> None:
        self.settings = settings
        self.database = database
        self.llm_client = llm_client
        self.arxiv_client = arxiv_client
        self.logger = logging.getLogger(__name__)

    @property
    def prompt_version(self) -> str:
        return f"{self.BASE_PROMPT_VERSION}-{output_language_slug(self.settings.llm.output_language)}"

    def build_detail(
        self,
        *,
        run_id: int,
        paper_id: int,
        paper: ArxivPaper,
        ai_result: KeywordFilterResult,
        summary_result: PaperSummaryResult,
    ) -> PaperDetailResult:
        cached = self.database.get_cached_detail(
            paper_id=paper_id,
            model_name=self.settings.llm.effective_detail_model,
            prompt_version=self.prompt_version,
        )
        if cached is not None:
            if not is_pdf_detail_source(cached.source):
                self.logger.info(
                    "Ignoring cached non-PDF detail for %s (source=%s); retrying PDF enrichment.",
                    paper.arxiv_id,
                    cached.source,
                )
            else:
                self.database.insert_detail(
                    run_id=run_id,
                    paper_id=paper_id,
                    detail=cached,
                    model_name=self.settings.llm.effective_detail_model,
                    prompt_version=self.prompt_version,
                    created_at=datetime.now(timezone.utc),
                )
                return cached

        try:
            pdf_path = self.arxiv_client.download_pdf(
                pdf_url=paper.pdf_url,
                destination=self._build_pdf_path(paper),
                max_file_size_mb=self.settings.pdf_enrichment.max_file_size_mb,
                timeout_seconds=self.settings.pdf_enrichment.timeout_seconds,
            )
            detail = self.llm_client.analyze_paper_pdf(
                pdf_path=pdf_path,
                title=paper.title,
                abstract=paper.summary,
                matched_keywords=ai_result.matched_keywords,
                upload_expires_after_hours=self.settings.pdf_enrichment.upload_expires_after_hours,
            )
        except Exception:
            self.logger.exception(
                "PDF detail analysis failed for %s (pdf_download_timeout=%ss, detail_timeout=%ss)",
                paper.arxiv_id,
                self.settings.pdf_enrichment.timeout_seconds,
                self.settings.llm.effective_detail_timeout_seconds,
            )
            detail = self._fallback_detail(
                paper=paper,
                ai_result=ai_result,
                summary_result=summary_result,
            )

        self.database.insert_detail(
            run_id=run_id,
            paper_id=paper_id,
            detail=detail,
            model_name=self.settings.llm.effective_detail_model,
            prompt_version=self.prompt_version,
            created_at=datetime.now(timezone.utc),
        )
        return detail

    def _fallback_detail(
        self,
        *,
        paper: ArxivPaper,
        ai_result: KeywordFilterResult,
        summary_result: PaperSummaryResult,
    ) -> PaperDetailResult:
        return PaperDetailResult(
            source="abstract_fallback",
            headline=summary_result.one_line,
            contribution_summary=localize_output_text(
                self.settings.llm.output_language,
                english="This fallback analysis is derived from the title and abstract rather than the full PDF.",
                chinese="这份回退分析基于标题和摘要生成，而不是基于 PDF 全文。",
            ),
            problem_and_context=summary_result.problem,
            research_question=summary_result.problem,
            method_overview=summary_result.method,
            novelty_and_positioning=localize_output_text(
                self.settings.llm.output_language,
                english="The full paper PDF was unavailable, so novelty relative to prior work is not clearly established.",
                chinese="由于未能获取论文 PDF，因此无法可靠判断其相对于既有工作的创新定位。",
            ),
            experimental_setup=localize_output_text(
                self.settings.llm.output_language,
                english="The abstract does not provide enough detail to reliably reconstruct the evaluation setup.",
                chinese="仅凭摘要无法可靠还原实验设置、数据集或评估协议。",
            ),
            key_findings=[summary_result.why_it_matters],
            evidence_and_credibility=localize_output_text(
                self.settings.llm.output_language,
                english="Evidence quality cannot be assessed confidently without the PDF's method and experiment sections.",
                chinese="在缺少 PDF 中的方法与实验细节时，无法可靠评估证据强度。",
            ),
            strengths=[
                localize_output_text(
                    self.settings.llm.output_language,
                    english="The paper was still shortlisted by the existing filtering pipeline.",
                    chinese="该论文仍然通过了现有筛选流程并进入了候选列表。",
                )
            ],
            limitations=[
                summary_result.limitations,
                localize_output_text(
                    self.settings.llm.output_language,
                    english="Detailed analysis fell back to title and abstract because PDF enrichment was unavailable.",
                    chinese="由于 PDF 深度分析不可用，详细解读已退回到基于标题和摘要的结果。",
                ),
            ],
            practical_implications=[
                localize_output_text(
                    self.settings.llm.output_language,
                    english="Use this fallback analysis only as a triage aid before reading the original paper.",
                    chinese="建议仅将这份回退分析作为初筛参考，后续仍需阅读原文确认。",
                )
            ],
            open_questions=[
                localize_output_text(
                    self.settings.llm.output_language,
                    english="What concrete datasets, baselines, and metrics does the paper use?",
                    chinese="论文具体使用了哪些数据集、基线和评测指标？",
                ),
                localize_output_text(
                    self.settings.llm.output_language,
                    english="How strong is the empirical or theoretical evidence behind the claimed contribution?",
                    chinese="论文声称的贡献是否有足够强的实验或理论证据支持？",
                ),
            ],
            relevance_to_keywords=self._fallback_relevance(ai_result),
            reading_guide=[
                localize_output_text(
                    self.settings.llm.output_language,
                    english="Read the abstract and introduction first to confirm the paper's exact scope.",
                    chinese="建议先阅读摘要和引言，以确认论文的准确研究范围。",
                ),
                localize_output_text(
                    self.settings.llm.output_language,
                    english="Check the experiments and conclusion before trusting any detailed claims.",
                    chinese="在采信更细节的结论前，优先查看实验部分和结论部分。",
                ),
            ],
        )

    def _fallback_relevance(self, ai_result: KeywordFilterResult) -> str:
        if ai_result.matched_keywords:
            return localize_output_text(
                self.settings.llm.output_language,
                english=(
                    "The abstract suggests a direct connection to the configured tracking focus."
                ),
                chinese="从摘要来看，这篇论文与当前配置的跟踪主题存在直接关联。",
            )
        return localize_output_text(
            self.settings.llm.output_language,
            english="The paper was included because the existing selection flow considered it relevant.",
            chinese="该论文之所以被纳入，是因为现有筛选流程判定其与关注主题相关。",
        )

    def _build_pdf_path(self, paper: ArxivPaper) -> Path:
        safe_identifier = re.sub(r"[^A-Za-z0-9._-]+", "_", paper.arxiv_id)
        filename = f"{safe_identifier}-{paper.version}.pdf"
        return self.settings.pdf_enrichment.download_dir / filename
