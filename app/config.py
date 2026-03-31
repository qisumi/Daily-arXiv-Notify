from __future__ import annotations

import copy
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import dotenv_values

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


SECRET_ENV_MAPPING = {
    ("llm", "api_key"): "OPENAI_API_KEY",
    ("email", "smtp_host"): "SMTP_HOST",
    ("email", "smtp_username"): "SMTP_USERNAME",
    ("email", "smtp_password"): "SMTP_PASSWORD",
    ("email", "from_address"): "SMTP_FROM_ADDRESS",
    ("email", "recipients"): "SMTP_RECIPIENTS",
}


class ConfigError(ValueError):
    """Raised when the runtime configuration is invalid."""


@dataclass(slots=True)
class DatabaseSettings:
    sqlite_path: Path


@dataclass(slots=True)
class ArxivSettings:
    categories: list[str]
    page_size: int = 100
    include_revisions: bool = False
    max_pages: int = 5
    overlap_hours: int = 36
    request_delay_seconds: float = 3.0
    max_retries: int = 3
    retry_backoff_seconds: float = 15.0


@dataclass(slots=True)
class FilteringSettings:
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    ai_target_keywords: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LLMSettings:
    provider: str
    base_url: str
    endpoint: str
    api_key: str
    classify_model: str
    summarize_model: str
    output_language: str = "English"
    reasoning_effort: str = "low"
    timeout_seconds: int = 120

    @property
    def api_mode(self) -> str:
        endpoint = self.endpoint.rstrip("/").lower()
        if endpoint.endswith("/responses"):
            return "responses"
        if endpoint.endswith("/chat/completions"):
            return "chat_completions"
        return "unknown"


@dataclass(slots=True)
class DigestSettings:
    max_papers: int
    section_strategy: str
    output_dir: Path
    attach_markdown: bool = True


@dataclass(slots=True)
class EmailSettings:
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    from_name: str
    from_address: str
    recipients: list[str]


@dataclass(slots=True)
class Settings:
    timezone: str
    schedule: str
    database: DatabaseSettings
    arxiv: ArxivSettings
    filtering: FilteringSettings
    llm: LLMSettings
    digest: DigestSettings
    email: EmailSettings
    base_dir: Path

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def target_keywords(self) -> list[str]:
        return self.filtering.ai_target_keywords or self.filtering.include_keywords

    def public_dict(self) -> dict[str, Any]:
        return {
            "timezone": self.timezone,
            "schedule": self.schedule,
            "database": {"sqlite_path": str(self.database.sqlite_path)},
            "arxiv": asdict(self.arxiv),
            "filtering": asdict(self.filtering),
            "llm": {
                "provider": self.llm.provider,
                "base_url": self.llm.base_url,
                "endpoint": self.llm.endpoint,
                "api_mode": self.llm.api_mode,
                "classify_model": self.llm.classify_model,
                "summarize_model": self.llm.summarize_model,
                "output_language": self.llm.output_language,
                "reasoning_effort": self.llm.reasoning_effort,
                "timeout_seconds": self.llm.timeout_seconds,
            },
            "digest": {
                **asdict(self.digest),
                "output_dir": str(self.digest.output_dir),
            },
            "email": {
                "smtp_port": self.email.smtp_port,
                "smtp_use_tls": self.email.smtp_use_tls,
                "from_name": self.email.from_name,
                "recipient_count": len(self.email.recipients),
                "credentials_configured": bool(
                    self.email.smtp_host
                    and self.email.from_address
                    and self.email.recipients
                ),
            },
        }


def _read_toml(config_path: Path) -> dict[str, Any]:
    with config_path.open("rb") as fh:
        return tomllib.load(fh)


def _get_nested(mapping: dict[str, Any], path: tuple[str, ...], default: Any = "") -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _set_nested(mapping: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = mapping
    for key in path[:-1]:
        current = current.setdefault(key, {})
    current[path[-1]] = value


def _parse_recipients(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [item.strip() for item in raw if str(item).strip()]
    return [item.strip() for item in raw.split(",") if item.strip()]


def _apply_secret_overrides(
    raw_config: dict[str, Any],
    dotenv_config: dict[str, str | None],
    env_config: dict[str, str],
) -> dict[str, Any]:
    merged = copy.deepcopy(raw_config)

    for path, env_name in SECRET_ENV_MAPPING.items():
        raw_value = _get_nested(merged, path, default="")
        selected: Any = raw_value

        if env_name in dotenv_config and dotenv_config[env_name] is not None:
            selected = dotenv_config[env_name]
        if env_name in env_config:
            selected = env_config[env_name]

        if path == ("email", "recipients"):
            selected = _parse_recipients(selected)

        _set_nested(merged, path, selected)

    return merged


def _resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _require_non_empty(name: str, value: Any, missing: list[str]) -> None:
    if isinstance(value, list):
        if not value:
            missing.append(name)
        return
    if value is None or str(value).strip() == "":
        missing.append(name)


def load_settings(config_path: str | Path = "config.toml") -> Settings:
    config_path = Path(config_path).resolve()
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    base_dir = config_path.parent
    raw_config = _read_toml(config_path)
    dotenv_config = {
        key: value
        for key, value in dotenv_values(base_dir / ".env").items()
        if isinstance(key, str)
    }
    merged = _apply_secret_overrides(raw_config, dotenv_config, dict(os.environ))

    database = DatabaseSettings(
        sqlite_path=_resolve_path(base_dir, merged["database"]["sqlite_path"])
    )
    arxiv = ArxivSettings(
        categories=list(merged["arxiv"]["categories"]),
        page_size=int(merged["arxiv"].get("page_size", 100)),
        include_revisions=bool(merged["arxiv"].get("include_revisions", False)),
        max_pages=int(merged["arxiv"].get("max_pages", 5)),
        overlap_hours=int(merged["arxiv"].get("overlap_hours", 36)),
        request_delay_seconds=float(
            merged["arxiv"].get("request_delay_seconds", 3.0)
        ),
        max_retries=int(merged["arxiv"].get("max_retries", 3)),
        retry_backoff_seconds=float(
            merged["arxiv"].get("retry_backoff_seconds", 15.0)
        ),
    )
    filtering = FilteringSettings(
        include_keywords=_parse_recipients(merged["filtering"].get("include_keywords", [])),
        exclude_keywords=_parse_recipients(merged["filtering"].get("exclude_keywords", [])),
        ai_target_keywords=_parse_recipients(
            merged["filtering"].get("ai_target_keywords", [])
        ),
    )
    llm = LLMSettings(
        provider=str(merged["llm"]["provider"]),
        base_url=str(merged["llm"]["base_url"]),
        endpoint=str(merged["llm"]["endpoint"]),
        api_key=str(merged["llm"].get("api_key", "")).strip(),
        classify_model=str(merged["llm"]["classify_model"]),
        summarize_model=str(
            merged["llm"].get("summarize_model") or merged["llm"]["classify_model"]
        ),
        output_language=str(merged["llm"].get("output_language", "English")).strip(),
        reasoning_effort=str(merged["llm"].get("reasoning_effort", "low")),
        timeout_seconds=int(merged["llm"].get("timeout_seconds", 120)),
    )
    digest = DigestSettings(
        max_papers=int(merged["digest"].get("max_papers", 12)),
        section_strategy=str(merged["digest"].get("section_strategy", "keyword")),
        output_dir=_resolve_path(base_dir, merged["digest"]["output_dir"]),
        attach_markdown=bool(merged["digest"].get("attach_markdown", True)),
    )
    email = EmailSettings(
        smtp_host=str(merged["email"].get("smtp_host", "")).strip(),
        smtp_port=int(merged["email"]["smtp_port"]),
        smtp_username=str(merged["email"].get("smtp_username", "")).strip(),
        smtp_password=str(merged["email"].get("smtp_password", "")).strip(),
        smtp_use_tls=bool(merged["email"].get("smtp_use_tls", True)),
        from_name=str(merged["email"]["from_name"]),
        from_address=str(merged["email"].get("from_address", "")).strip(),
        recipients=_parse_recipients(merged["email"].get("recipients", [])),
    )
    settings = Settings(
        timezone=str(merged["timezone"]),
        schedule=str(merged["schedule"]),
        database=database,
        arxiv=arxiv,
        filtering=filtering,
        llm=llm,
        digest=digest,
        email=email,
        base_dir=base_dir,
    )
    _validate_settings(settings)
    return settings


def _validate_settings(settings: Settings) -> None:
    missing: list[str] = []
    _require_non_empty("timezone", settings.timezone, missing)
    _require_non_empty("schedule", settings.schedule, missing)
    _require_non_empty("database.sqlite_path", str(settings.database.sqlite_path), missing)
    _require_non_empty("arxiv.categories", settings.arxiv.categories, missing)
    _require_non_empty("llm.base_url", settings.llm.base_url, missing)
    _require_non_empty("llm.endpoint", settings.llm.endpoint, missing)
    _require_non_empty("llm.api_key", settings.llm.api_key, missing)
    _require_non_empty("llm.classify_model", settings.llm.classify_model, missing)
    _require_non_empty("llm.summarize_model", settings.llm.summarize_model, missing)
    _require_non_empty("llm.output_language", settings.llm.output_language, missing)
    _require_non_empty("digest.output_dir", str(settings.digest.output_dir), missing)
    _require_non_empty("email.smtp_host", settings.email.smtp_host, missing)
    _require_non_empty("email.from_address", settings.email.from_address, missing)
    _require_non_empty("email.recipients", settings.email.recipients, missing)
    _require_non_empty("filtering.ai_target_keywords", settings.target_keywords, missing)

    if settings.email.smtp_username and not settings.email.smtp_password:
        missing.append("email.smtp_password")
    if settings.email.smtp_password and not settings.email.smtp_username:
        missing.append("email.smtp_username")

    try:
        ZoneInfo(settings.timezone)
    except Exception as exc:  # pragma: no cover
        raise ConfigError(f"Invalid timezone: {settings.timezone}") from exc

    if settings.llm.api_mode == "unknown":
        raise ConfigError(
            "Unsupported llm.endpoint. "
            "Expected an endpoint ending with '/responses' or '/chat/completions', "
            f"got: {settings.llm.endpoint}"
        )

    if settings.arxiv.request_delay_seconds < 0:
        raise ConfigError("arxiv.request_delay_seconds must be >= 0")
    if settings.arxiv.max_retries < 0:
        raise ConfigError("arxiv.max_retries must be >= 0")
    if settings.arxiv.retry_backoff_seconds < 0:
        raise ConfigError("arxiv.retry_backoff_seconds must be >= 0")

    if missing:
        formatted = ", ".join(sorted(set(missing)))
        raise ConfigError(f"Missing or invalid configuration values: {formatted}")
