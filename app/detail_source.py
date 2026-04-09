from __future__ import annotations

PDF_DETAIL_SOURCE = "pdf"
ABSTRACT_FALLBACK_DETAIL_SOURCE = "abstract_fallback"

_ABSTRACT_FALLBACK_ALIASES = {
    ABSTRACT_FALLBACK_DETAIL_SOURCE,
    "abstract fallback",
    "abstract-fallback",
    "abstract",
    "fallback",
    "summary_fallback",
    "title_abstract",
}


def normalize_detail_source(source: str | None) -> str:
    if source is None:
        return PDF_DETAIL_SOURCE

    normalized = source.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in _ABSTRACT_FALLBACK_ALIASES:
        return ABSTRACT_FALLBACK_DETAIL_SOURCE
    return PDF_DETAIL_SOURCE


def is_pdf_detail_source(source: str | None) -> bool:
    return normalize_detail_source(source) == PDF_DETAIL_SOURCE
