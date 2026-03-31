from __future__ import annotations

from pathlib import Path

from app.config import (
    ArxivSettings,
    DatabaseSettings,
    DigestSettings,
    EmailSettings,
    FilteringSettings,
    LLMSettings,
    Settings,
)
from app.models import ArxivPaper, KeywordFilterResult
from app.services.filter_service import FilterService
from app.services.summarize_service import SummarizeService


def _make_settings(tmp_path: Path, output_language: str) -> Settings:
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
            output_language=output_language,
            reasoning_effort="low",
            timeout_seconds=30,
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
    )


def _make_paper() -> ArxivPaper:
    from datetime import datetime, timezone

    return ArxivPaper(
        arxiv_id="1234.5678",
        version="v1",
        title="Agent paper",
        summary="This paper studies agent systems.",
        authors=["Alice"],
        categories=["cs.AI"],
        published_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        abs_url="https://arxiv.org/abs/1234.5678",
        pdf_url="https://arxiv.org/pdf/1234.5678.pdf",
        source_payload={"raw": True},
    )


def test_filter_service_localizes_fallback_reason_and_cache_key(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, "Chinese")
    service = FilterService(settings, database=None, llm_client=None)  # type: ignore[arg-type]

    result = service._fallback_keyword_match(_make_paper(), RuntimeError("boom"))

    assert service.prompt_version.endswith("chinese")
    assert "LLM 请求失败" in result.reason


def test_summarize_service_localizes_fallback_summary_and_cache_key(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, "Chinese")
    service = SummarizeService(settings, database=None, llm_client=None)  # type: ignore[arg-type]

    summary = service._fallback_summary(
        _make_paper(),
        KeywordFilterResult(
            is_related=True,
            matched_keywords=["agent"],
            reason="相关",
        ),
    )

    assert service.prompt_version.endswith("chinese")
    assert summary.why_it_matters == "这篇论文命中了以下关键词：agent。"
    assert "未能成功调用 LLM" in summary.limitations
    assert "内容可能保留论文原始语言" in summary.limitations
