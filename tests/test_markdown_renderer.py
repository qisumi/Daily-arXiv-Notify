from __future__ import annotations

from datetime import datetime, timezone

from app.models import (
    ArxivPaper,
    CandidatePaper,
    KeywordFilterResult,
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
    )

    markdown = render_digest_markdown(
        run_time=datetime(2026, 3, 30, 5, 15, tzinfo=timezone.utc),
        timezone_name="Asia/Shanghai",
        categories=["cs.AI"],
        total_fetched=1,
        total_rule_matched=1,
        candidates=[candidate],
    )

    assert "### A Test Paper" in markdown
    assert "- Summary: Short summary" in markdown
    assert "https://arxiv.org/abs/1234.5678" in markdown
