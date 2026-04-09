from __future__ import annotations

from datetime import datetime, timezone

from app.models import (
    ArxivPaper,
    CandidatePaper,
    KeywordFilterResult,
    PaperDetailResult,
    PaperSummaryResult,
    RuleFilterResult,
)
from app.render.markdown_renderer import render_digest_markdown


def test_markdown_renderer_includes_required_paper_fields() -> None:
    paper = ArxivPaper(
        arxiv_id="1234.5678",
        version="v1",
        title="A Test Paper",
        summary="Original abstract text.",
        authors=["Alice", "Bob"],
        categories=["cs.AI"],
        published_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        abs_url="https://arxiv.org/abs/1234.5678",
        pdf_url="https://arxiv.org/pdf/1234.5678.pdf",
        source_payload={"raw": True},
    )
    candidate = CandidatePaper(
        paper_id=1,
        paper=paper,
        rule_result=RuleFilterResult(matched=True, reason="matched", matched_keywords=["agent"]),
        ai_result=KeywordFilterResult(
            is_related=True,
            matched_keywords=["agent"],
            reason="The abstract is about agent systems.",
        ),
        summary_result=PaperSummaryResult(
            one_line="Short summary",
            problem="Problem",
            method="Method",
            why_it_matters="Why it matters",
            limitations="Limitations",
            tags=["agent"],
        ),
        detail_result=PaperDetailResult(
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
        ),
    )

    markdown = render_digest_markdown(
        run_time=datetime(2026, 3, 30, 5, 15, tzinfo=timezone.utc),
        timezone_name="Asia/Shanghai",
        categories=["cs.AI"],
        total_fetched=1,
        total_rule_matched=1,
        candidates=[candidate],
        include_detailed_exploration=True,
    )

    assert "### A Test Paper" in markdown
    assert "- Quick summary: Short summary" in markdown
    assert "#### Deep Dive" in markdown
    assert "#### Key Findings" in markdown
    assert "#### Practical Implications" in markdown
    assert "#### Open Questions" in markdown
    assert "https://arxiv.org/abs/1234.5678" in markdown
    assert "Matched keywords" not in markdown
    assert "Why matched" not in markdown
    assert "Categories:" not in markdown


def test_markdown_renderer_counts_normalized_pdf_detail_sources() -> None:
    paper = ArxivPaper(
        arxiv_id="1234.5678",
        version="v1",
        title="A Test Paper",
        summary="Original abstract text.",
        authors=["Alice", "Bob"],
        categories=["cs.AI"],
        published_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        abs_url="https://arxiv.org/abs/1234.5678",
        pdf_url="https://arxiv.org/pdf/1234.5678.pdf",
        source_payload={"raw": True},
    )
    candidate = CandidatePaper(
        paper_id=1,
        paper=paper,
        rule_result=RuleFilterResult(matched=True, reason="matched", matched_keywords=["agent"]),
        ai_result=KeywordFilterResult(
            is_related=True,
            matched_keywords=["agent"],
            reason="The abstract is about agent systems.",
        ),
        summary_result=PaperSummaryResult(
            one_line="Short summary",
            problem="Problem",
            method="Method",
            why_it_matters="Why it matters",
            limitations="Limitations",
            tags=["agent"],
        ),
        detail_result=PaperDetailResult(
            source="PDF grounded analysis",
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
        ),
    )

    markdown = render_digest_markdown(
        run_time=datetime(2026, 3, 30, 5, 15, tzinfo=timezone.utc),
        timezone_name="Asia/Shanghai",
        categories=["cs.AI"],
        total_fetched=1,
        total_rule_matched=1,
        candidates=[candidate],
        include_detailed_exploration=True,
    )

    assert "- Detailed analysis available: 1 / 1" in markdown
    assert "- Detail source: PDF" in markdown
