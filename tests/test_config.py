from __future__ import annotations

from pathlib import Path

import pytest

from app.config import ConfigError, load_settings


CONFIG_TEMPLATE = """
timezone = "Asia/Shanghai"
schedule = "15 13 * * *"

[database]
sqlite_path = "data/app.db"

[arxiv]
categories = ["cs.AI"]
page_size = 50
include_revisions = false
max_pages = 2
overlap_hours = 36

[filtering]
include_keywords = ["agent"]
exclude_keywords = []
ai_target_keywords = ["agent"]

[llm]
provider = "openai"
base_url = "https://api.openai.com/v1"
endpoint = "/responses"
api_key = ""
classify_model = "gpt-5-mini"
summarize_model = "gpt-5.4"
detail_model = "doubao-seed-2-0-pro-260215"
detail_reasoning_effort = "high"
reasoning_effort = "low"
timeout_seconds = 30

[digest]
max_papers = 10
section_strategy = "keyword"
output_dir = "data/digests"
attach_markdown = true

[email]
smtp_host = ""
smtp_port = 587
smtp_username = ""
smtp_password = ""
smtp_use_tls = true
from_name = "Daily arXiv Notify"
from_address = ""
recipients = []
"""


def test_load_settings_reads_dotenv_and_env_precedence(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=dotenv-key",
                "SMTP_HOST=smtp.dotenv.example",
                "SMTP_FROM_ADDRESS=dotenv@example.com",
                "SMTP_RECIPIENTS=dotenv1@example.com,dotenv2@example.com",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("SMTP_HOST", "smtp.env.example")
    monkeypatch.setenv("SMTP_FROM_ADDRESS", "env@example.com")
    monkeypatch.setenv("SMTP_RECIPIENTS", "env1@example.com,env2@example.com")

    settings = load_settings(config_path)

    assert settings.llm.api_key == "env-key"
    assert settings.email.smtp_host == "smtp.env.example"
    assert settings.email.from_address == "env@example.com"
    assert settings.email.recipients == ["env1@example.com", "env2@example.com"]


def test_load_settings_falls_back_to_dotenv_when_process_env_missing(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=dotenv-key",
                "SMTP_HOST=smtp.dotenv.example",
                "SMTP_FROM_ADDRESS=dotenv@example.com",
                "SMTP_RECIPIENTS=dotenv@example.com",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.llm.api_key == "dotenv-key"
    assert settings.email.smtp_host == "smtp.dotenv.example"
    assert settings.email.from_address == "dotenv@example.com"
    assert settings.email.recipients == ["dotenv@example.com"]


def test_load_settings_accepts_legacy_chat_endpoint(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        CONFIG_TEMPLATE.replace('endpoint = "/responses"', 'endpoint = "/chat/completions"'),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=dotenv-key",
                "SMTP_HOST=smtp.dotenv.example",
                "SMTP_FROM_ADDRESS=dotenv@example.com",
                "SMTP_RECIPIENTS=dotenv@example.com",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.llm.endpoint == "/chat/completions"
    assert settings.llm.api_mode == "chat_completions"


def test_load_settings_reads_output_language(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        CONFIG_TEMPLATE.replace(
            'reasoning_effort = "low"',
            '\n'.join(
                [
                    'output_language = "Chinese"',
                    'reasoning_effort = "low"',
                ]
            ),
        ),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=dotenv-key",
                "SMTP_HOST=smtp.dotenv.example",
                "SMTP_FROM_ADDRESS=dotenv@example.com",
                "SMTP_RECIPIENTS=dotenv@example.com",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.llm.output_language == "Chinese"


def test_load_settings_reads_arxiv_retry_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        CONFIG_TEMPLATE.replace(
            "overlap_hours = 36",
            "\n".join(
                [
                    "overlap_hours = 36",
                    "request_delay_seconds = 4.5",
                    "max_retries = 6",
                    "retry_backoff_seconds = 20.0",
                ]
            ),
        ),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=dotenv-key",
                "SMTP_HOST=smtp.dotenv.example",
                "SMTP_FROM_ADDRESS=dotenv@example.com",
                "SMTP_RECIPIENTS=dotenv@example.com",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.arxiv.request_delay_seconds == 4.5
    assert settings.arxiv.max_retries == 6
    assert settings.arxiv.retry_backoff_seconds == 20.0


def test_load_settings_reads_pdf_enrichment_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        CONFIG_TEMPLATE
        + """

[pdf_enrichment]
enabled = true
download_dir = "data/pdfs"
max_file_size_mb = 25
timeout_seconds = 240
max_retries = 4
retry_backoff_seconds = 12.5
upload_expires_after_hours = 36
""",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=dotenv-key",
                "SMTP_HOST=smtp.dotenv.example",
                "SMTP_FROM_ADDRESS=dotenv@example.com",
                "SMTP_RECIPIENTS=dotenv@example.com",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.llm.detail_model == "doubao-seed-2-0-pro-260215"
    assert settings.llm.effective_detail_reasoning_effort == "high"
    assert settings.pdf_enrichment.enabled is True
    assert settings.pdf_enrichment.max_file_size_mb == 25
    assert settings.pdf_enrichment.timeout_seconds == 240
    assert settings.pdf_enrichment.max_retries == 4
    assert settings.pdf_enrichment.retry_backoff_seconds == 12.5
    assert settings.pdf_enrichment.upload_expires_after_hours == 36


def test_load_settings_requires_responses_endpoint_for_pdf_enrichment(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        CONFIG_TEMPLATE.replace('endpoint = "/responses"', 'endpoint = "/chat/completions"')
        + """

[pdf_enrichment]
enabled = true
""",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=dotenv-key",
                "SMTP_HOST=smtp.dotenv.example",
                "SMTP_FROM_ADDRESS=dotenv@example.com",
                "SMTP_RECIPIENTS=dotenv@example.com",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="pdf_enrichment.enabled requires llm.endpoint"):
        load_settings(config_path)
