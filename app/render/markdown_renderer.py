from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import CandidatePaper


def render_digest_markdown(
    *,
    run_time: datetime,
    timezone_name: str,
    categories: list[str],
    total_fetched: int,
    total_rule_matched: int,
    candidates: list[CandidatePaper],
) -> str:
    tzinfo = ZoneInfo(timezone_name)
    digest_date = run_time.astimezone(tzinfo).date().isoformat()
    lines: list[str] = [f"# Daily arXiv Digest - {digest_date}", ""]
    lines.extend(
        [
            "## Overview",
            f"- Categories: {', '.join(categories)}",
            f"- Total fetched: {total_fetched}",
            f"- Passed rule filter: {total_rule_matched}",
            f"- Included in digest: {len(candidates)}",
            "",
        ]
    )

    if not candidates:
        lines.extend(
            [
                "## No Matched Papers",
                "",
                "No papers matched the configured filters in this run.",
                "",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    grouped: "OrderedDict[str, list[CandidatePaper]]" = OrderedDict()
    updates: list[CandidatePaper] = []

    for candidate in candidates:
        if candidate.is_update_only:
            updates.append(candidate)
            continue
        group_name = (
            candidate.ai_result.matched_keywords[0]
            if candidate.ai_result.matched_keywords
            else "Other Matched Papers"
        )
        grouped.setdefault(group_name, []).append(candidate)

    for keyword, items in grouped.items():
        title = keyword if keyword == "Other Matched Papers" else f"Keyword: {keyword}"
        lines.extend(_render_section(title, items))

    if updates:
        lines.extend(_render_section("Updated Papers", updates))

    return "\n".join(lines).strip() + "\n"


def _render_section(title: str, items: list[CandidatePaper]) -> list[str]:
    lines = [f"## {title}", ""]
    for item in items:
        lines.extend(
            [
                f"### {item.paper.title}",
                f"- arXiv: {item.paper.arxiv_id}",
                f"- Authors: {', '.join(item.paper.authors)}",
                f"- Categories: {', '.join(item.paper.categories)}",
                f"- Matched keywords: {', '.join(item.ai_result.matched_keywords) or 'N/A'}",
                f"- Why matched: {item.ai_result.reason}",
                f"- Summary: {item.summary_result.one_line}",
                f"- Links: [abs]({item.paper.abs_url}) | [pdf]({item.paper.pdf_url})",
                "",
            ]
        )
    return lines
