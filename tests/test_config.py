from __future__ import annotations

from pathlib import Path

from app.config import load_settings


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
