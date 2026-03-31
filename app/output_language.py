from __future__ import annotations

import re


def normalize_output_language(language: str | None) -> str:
    value = str(language or "").strip()
    return value or "English"


def output_language_slug(language: str | None) -> str:
    normalized = normalize_output_language(language).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "english"


def is_chinese_output_language(language: str | None) -> bool:
    normalized = normalize_output_language(language).lower()
    return (
        normalized in {"chinese", "simplified chinese", "simplified chinese (mainland china)", "zh", "zh-cn", "zh-hans", "中文", "简体中文"}
        or "chinese" in normalized
        or normalized.startswith("zh")
    )


def localize_output_text(
    language: str | None,
    *,
    english: str,
    chinese: str,
) -> str:
    if is_chinese_output_language(language):
        return chinese
    return english
