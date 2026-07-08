from __future__ import annotations

from datetime import datetime, timezone
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
from app.services.digest_service import DigestService


def _make_settings(tmp_path: Path, *, subscription_id: str, subscription_name: str) -> Settings:
    return Settings(
        timezone="Asia/Shanghai",
        schedule="15 13 * * *",
        database=DatabaseSettings(sqlite_path=tmp_path / "app.db"),
        arxiv=ArxivSettings(categories=["cs.AI"]),
        filtering=FilteringSettings(
            include_keywords=["synthetic data"],
            exclude_keywords=[],
            ai_target_keywords=["synthetic data"],
        ),
        llm=LLMSettings(
            provider="openai",
            base_url="https://api.openai.com/v1",
            endpoint="/responses",
            api_key="test-key",
            classify_model="gpt-5-mini",
            summarize_model="gpt-5.4",
            output_language="Chinese",
        ),
        digest=DigestSettings(
            max_papers=12,
            section_strategy="keyword",
            output_dir=tmp_path / subscription_id,
            attach_markdown=True,
        ),
        email=EmailSettings(
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username="",
            smtp_password="",
            smtp_use_tls=True,
            from_name="Daily arXiv Notify",
            from_address="from@example.com",
            recipients=["user@example.com"],
        ),
        base_dir=tmp_path,
        subscription_id=subscription_id,
        subscription_name=subscription_name,
    )


def test_non_default_subscription_subject_and_output_dir(tmp_path: Path) -> None:
    settings = _make_settings(
        tmp_path,
        subscription_id="llm-data-synthesis",
        subscription_name="LLM Data Synthesis",
    )
    service = DigestService(settings)

    digest = service.build_digest(
        run_time=datetime(2026, 7, 8, tzinfo=timezone.utc),
        total_fetched=0,
        total_rule_matched=0,
        candidates=[],
    )

    assert digest.subject == "Daily arXiv Digest | LLM Data Synthesis | 2026-07-08 | 0 papers"
    assert digest.markdown_path.parent == tmp_path / "llm-data-synthesis"
    assert digest.html_path.parent == tmp_path / "llm-data-synthesis"
