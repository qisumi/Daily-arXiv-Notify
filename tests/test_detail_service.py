from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import (
    ArxivSettings,
    DatabaseSettings,
    DigestSettings,
    EmailSettings,
    FilteringSettings,
    LLMSettings,
    PDFEnrichmentSettings,
    Settings,
)
from app.db import Database
from app.models import ArxivPaper, KeywordFilterResult, PaperDetailResult, PaperSummaryResult
from app.services.detail_service import DetailService


class FakeArxivClient:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict] = []

    def download_pdf(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        destination = kwargs["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"%PDF-1.4\n%fake pdf\n")
        return destination


class FakeOpenAIClient:
    def __init__(self, *, detail: PaperDetailResult) -> None:
        self.detail = detail
        self.calls: list[dict] = []

    def analyze_paper_pdf(self, **kwargs):
        self.calls.append(kwargs)
        return self.detail


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        timezone="Asia/Shanghai",
        schedule="15 13 * * *",
        database=DatabaseSettings(sqlite_path=tmp_path / "app.db"),
        arxiv=ArxivSettings(categories=["cs.AI"]),
        filtering=FilteringSettings(
            include_keywords=["agent"],
            exclude_keywords=[],
            ai_target_keywords=["agent"],
        ),
        llm=LLMSettings(
            provider="openai",
            base_url="https://api.openai.com/v1",
            endpoint="/responses",
            api_key="test-key",
            classify_model="gpt-5-mini",
            summarize_model="gpt-5.4",
            detail_model="doubao-seed-2-0-pro-260215",
            output_language="English",
            reasoning_effort="low",
            detail_reasoning_effort="high",
            timeout_seconds=30,
            detail_timeout_seconds=300,
        ),
        digest=DigestSettings(
            max_papers=10,
            section_strategy="keyword",
            output_dir=tmp_path / "digests",
            attach_markdown=True,
        ),
        email=EmailSettings(
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username="",
            smtp_password="",
            smtp_use_tls=True,
            from_name="Daily arXiv Notify",
            from_address="user@example.com",
            recipients=["user@example.com"],
        ),
        base_dir=tmp_path,
        pdf_enrichment=PDFEnrichmentSettings(
            enabled=True,
            download_dir=tmp_path / "pdfs",
            max_file_size_mb=40,
            timeout_seconds=120,
            max_retries=2,
            retry_backoff_seconds=10.0,
            upload_expires_after_hours=24,
        ),
    )


def _make_paper() -> ArxivPaper:
    now = datetime.now(timezone.utc)
    return ArxivPaper(
        arxiv_id="1234.5678",
        version="v1",
        title="Agent paper",
        summary="This paper studies agent systems.",
        authors=["Alice"],
        categories=["cs.AI"],
        published_at=now,
        updated_at=now,
        abs_url="https://arxiv.org/abs/1234.5678",
        pdf_url="https://arxiv.org/pdf/1234.5678.pdf",
        source_payload={"raw": True},
    )


def _make_summary() -> PaperSummaryResult:
    return PaperSummaryResult(
        one_line="Short summary",
        problem="Problem",
        method="Method",
        why_it_matters="Why it matters",
        limitations="Limitations",
        tags=["agent"],
    )


def _make_detail() -> PaperDetailResult:
    return PaperDetailResult(
        source="pdf",
        headline="Detailed headline",
        contribution_summary="Contribution summary",
        problem_and_context="Problem and context",
        research_question="Research question",
        method_overview="Method overview",
        novelty_and_positioning="Novelty and positioning",
        experimental_setup="Experimental setup",
        key_findings=["Finding 1"],
        evidence_and_credibility="Evidence and credibility",
        strengths=["Strength 1"],
        limitations=["Limitation 1"],
        practical_implications=["Practical implication 1"],
        open_questions=["Open question 1"],
        relevance_to_keywords="Relevant to the configured focus.",
        reading_guide=["Read the experiments."],
    )


def _create_run_and_paper(db: Database, paper: ArxivPaper) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    run_id = db.create_run(
        run_date="2026-03-30",
        window_start=now - timedelta(hours=36),
        window_end=now,
        overlap_hours=36,
        config_snapshot={"ok": True},
        started_at=now,
    )
    paper_id = db.upsert_paper(
        {
            "arxiv_id": paper.arxiv_id,
            "version": paper.version,
            "title": paper.title,
            "summary": paper.summary,
            "authors": paper.authors,
            "categories": paper.categories,
            "published_at": paper.published_at,
            "updated_at": paper.updated_at,
            "abs_url": paper.abs_url,
            "pdf_url": paper.pdf_url,
            "source_payload": paper.source_payload,
        }
    )
    return run_id, paper_id


def test_detail_service_uses_cached_detail_without_re_downloading(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    db = Database(settings.database.sqlite_path)
    db.initialize()
    paper = _make_paper()
    run_id, paper_id = _create_run_and_paper(db, paper)
    cached_detail = _make_detail()
    db.insert_detail(
        run_id=run_id,
        paper_id=paper_id,
        detail=cached_detail,
        model_name=settings.llm.effective_detail_model,
        prompt_version="paper-detail-v2-english",
        created_at=datetime.now(timezone.utc),
    )
    fake_arxiv = FakeArxivClient()
    fake_llm = FakeOpenAIClient(detail=_make_detail())
    service = DetailService(settings, db, fake_llm, fake_arxiv)  # type: ignore[arg-type]

    result = service.build_detail(
        run_id=run_id,
        paper_id=paper_id,
        paper=paper,
        ai_result=KeywordFilterResult(
            is_related=True,
            matched_keywords=["agent"],
            reason="Relevant.",
        ),
        summary_result=_make_summary(),
    )

    assert result.source == "pdf"
    assert fake_arxiv.calls == []
    assert fake_llm.calls == []
    db.close()


def test_detail_service_ignores_cached_abstract_fallback_and_retries_pdf_enrichment(
    tmp_path: Path,
) -> None:
    settings = _make_settings(tmp_path)
    db = Database(settings.database.sqlite_path)
    db.initialize()
    paper = _make_paper()
    run_id, paper_id = _create_run_and_paper(db, paper)
    cached_fallback = PaperDetailResult(
        source="abstract_fallback",
        headline="Fallback headline",
        contribution_summary="Fallback contribution summary",
        problem_and_context="Fallback problem and context",
        research_question="Fallback research question",
        method_overview="Fallback method overview",
        novelty_and_positioning="Fallback novelty",
        experimental_setup="Fallback setup",
        key_findings=["Fallback finding"],
        evidence_and_credibility="Fallback evidence",
        strengths=["Fallback strength"],
        limitations=["Fallback limitation"],
        practical_implications=["Fallback practical implication"],
        open_questions=["Fallback open question"],
        relevance_to_keywords="Fallback relevance",
        reading_guide=["Fallback reading guide"],
    )
    db.insert_detail(
        run_id=run_id,
        paper_id=paper_id,
        detail=cached_fallback,
        model_name=settings.llm.effective_detail_model,
        prompt_version="paper-detail-v2-english",
        created_at=datetime.now(timezone.utc),
    )
    fake_arxiv = FakeArxivClient()
    fake_llm = FakeOpenAIClient(detail=_make_detail())
    service = DetailService(settings, db, fake_llm, fake_arxiv)  # type: ignore[arg-type]

    result = service.build_detail(
        run_id=run_id,
        paper_id=paper_id,
        paper=paper,
        ai_result=KeywordFilterResult(
            is_related=True,
            matched_keywords=["agent"],
            reason="Relevant.",
        ),
        summary_result=_make_summary(),
    )

    assert result.source == "pdf"
    assert len(fake_arxiv.calls) == 1
    assert len(fake_llm.calls) == 1
    db.close()


def test_detail_service_falls_back_when_pdf_download_fails(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    db = Database(settings.database.sqlite_path)
    db.initialize()
    paper = _make_paper()
    run_id, paper_id = _create_run_and_paper(db, paper)
    fake_arxiv = FakeArxivClient(error=RuntimeError("boom"))
    fake_llm = FakeOpenAIClient(detail=_make_detail())
    service = DetailService(settings, db, fake_llm, fake_arxiv)  # type: ignore[arg-type]

    result = service.build_detail(
        run_id=run_id,
        paper_id=paper_id,
        paper=paper,
        ai_result=KeywordFilterResult(
            is_related=True,
            matched_keywords=["agent"],
            reason="Relevant.",
        ),
        summary_result=_make_summary(),
    )

    assert result.source == "abstract_fallback"
    assert result.contribution_summary
    assert result.evidence_and_credibility
    assert result.practical_implications
    assert result.open_questions
    assert len(fake_arxiv.calls) == 1
    assert fake_llm.calls == []
    cached = db.get_cached_detail(
        paper_id=paper_id,
        model_name=settings.llm.effective_detail_model,
        prompt_version="paper-detail-v2-english",
    )
    assert cached is not None
    assert cached.source == "abstract_fallback"
    db.close()
