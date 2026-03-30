from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


@dataclass(slots=True, frozen=True)
class ArxivPaper:
    arxiv_id: str
    version: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    published_at: datetime
    updated_at: datetime
    abs_url: str
    pdf_url: str
    source_payload: dict[str, Any]


@dataclass(slots=True)
class RuleFilterResult:
    matched: bool
    reason: str
    matched_keywords: list[str] = field(default_factory=list)
    excluded_keywords: list[str] = field(default_factory=list)


class KeywordFilterResult(BaseModel):
    is_related: bool
    matched_keywords: list[str] = Field(default_factory=list)
    reason: str


class PaperSummaryResult(BaseModel):
    one_line: str
    problem: str
    method: str
    why_it_matters: str
    limitations: str
    tags: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class RunWindow:
    window_start: datetime
    window_end: datetime
    overlap_hours: int


@dataclass(slots=True)
class RunRecord:
    id: int
    run_date: str
    window_start: datetime
    window_end: datetime
    overlap_hours: int
    status: str
    config_snapshot: dict[str, Any]
    started_at: datetime
    finished_at: datetime | None = None
    error_message: str | None = None


@dataclass(slots=True)
class CandidatePaper:
    paper_id: int
    paper: ArxivPaper
    rule_result: RuleFilterResult
    ai_result: KeywordFilterResult
    summary_result: PaperSummaryResult
    is_update_only: bool = False


@dataclass(slots=True)
class RenderedDigest:
    subject: str
    markdown: str
    html: str
    markdown_path: Path
    html_path: Path
    paper_count: int
