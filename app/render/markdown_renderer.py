from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import CandidatePaper
from app.output_language import localize_output_text


def render_digest_markdown(
    *,
    run_time: datetime,
    timezone_name: str,
    categories: list[str],
    total_fetched: int,
    total_rule_matched: int,
    candidates: list[CandidatePaper],
    content_language: str = "English",
    include_detailed_exploration: bool = False,
) -> str:
    tzinfo = ZoneInfo(timezone_name)
    digest_date = run_time.astimezone(tzinfo).date().isoformat()
    lines: list[str] = [f"# Daily arXiv Digest - {digest_date}", ""]
    overview_title = localize_output_text(
        content_language,
        english="Overview",
        chinese="概览",
    )
    lines.extend(
        [
            f"## {overview_title}",
            f"- {localize_output_text(content_language, english='Total fetched', chinese='抓取总数')}: {total_fetched}",
            f"- {localize_output_text(content_language, english='Passed rule filter', chinese='规则过滤通过数')}: {total_rule_matched}",
            f"- {localize_output_text(content_language, english='Included in digest', chinese='最终收录数')}: {len(candidates)}",
        ]
    )
    if include_detailed_exploration:
        detailed_count = sum(
            1
            for item in candidates
            if item.detail_result is not None and item.detail_result.source == "pdf"
        )
        lines.append(
            f"- {localize_output_text(content_language, english='Detailed analysis available', chinese='已完成 PDF 深度分析')}: {detailed_count} / {len(candidates)}"
        )
    lines.append("")

    if not candidates:
        lines.extend(
            [
                f"## {localize_output_text(content_language, english='No Matched Papers', chinese='未命中论文')}",
                "",
                localize_output_text(
                    content_language,
                    english="No papers matched the configured filters in this run.",
                    chinese="本次运行中没有论文命中当前配置的筛选条件。",
                ),
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
        lines.extend(
            _render_section(
                title,
                items,
                content_language=content_language,
                include_detailed_exploration=include_detailed_exploration,
            )
        )

    if updates:
        lines.extend(
            _render_section(
                localize_output_text(
                    content_language,
                    english="Updated Papers",
                    chinese="更新论文",
                ),
                updates,
                content_language=content_language,
                include_detailed_exploration=include_detailed_exploration,
            )
        )

    return "\n".join(lines).strip() + "\n"


def _render_section(
    title: str,
    items: list[CandidatePaper],
    *,
    content_language: str,
    include_detailed_exploration: bool,
) -> list[str]:
    summary_label = localize_output_text(
        content_language,
        english="Quick summary",
        chinese="快速摘要",
    )
    links_label = localize_output_text(
        content_language,
        english="Links",
        chinese="链接",
    )
    detail_source_label = localize_output_text(
        content_language,
        english="Detail source",
        chinese="详细解析来源",
    )
    deep_dive_title = localize_output_text(
        content_language,
        english="Deep Dive",
        chinese="深入解读",
    )
    headline_label = localize_output_text(
        content_language,
        english="Headline",
        chinese="核心判断",
    )
    research_question_label = localize_output_text(
        content_language,
        english="Research question",
        chinese="研究问题",
    )
    contribution_label = localize_output_text(
        content_language,
        english="Contribution summary",
        chinese="贡献总结",
    )
    context_label = localize_output_text(
        content_language,
        english="Problem and context",
        chinese="问题与背景",
    )
    method_label = localize_output_text(
        content_language,
        english="Method overview",
        chinese="方法概览",
    )
    novelty_label = localize_output_text(
        content_language,
        english="Novelty and positioning",
        chinese="创新点与定位",
    )
    setup_label = localize_output_text(
        content_language,
        english="Experimental setup",
        chinese="实验设置",
    )
    evidence_label = localize_output_text(
        content_language,
        english="Evidence and credibility",
        chinese="证据与可信度",
    )
    relevance_label = localize_output_text(
        content_language,
        english="Relevance",
        chinese="相关性",
    )
    key_findings_title = localize_output_text(
        content_language,
        english="Key Findings",
        chinese="关键发现",
    )
    strengths_title = localize_output_text(
        content_language,
        english="Strengths",
        chinese="亮点",
    )
    limitations_title = localize_output_text(
        content_language,
        english="Limitations",
        chinese="局限",
    )
    practical_implications_title = localize_output_text(
        content_language,
        english="Practical Implications",
        chinese="实际启示",
    )
    open_questions_title = localize_output_text(
        content_language,
        english="Open Questions",
        chinese="开放问题",
    )
    reading_guide_title = localize_output_text(
        content_language,
        english="Reading Guide",
        chinese="阅读建议",
    )
    lines = [f"## {title}", ""]
    for item in items:
        lines.extend(
            [
                f"### {item.paper.title}",
                f"- arXiv: {item.paper.arxiv_id}",
                f"- Authors: {', '.join(item.paper.authors)}",
                f"- {summary_label}: {item.summary_result.one_line}",
                f"- {links_label}: [abs]({item.paper.abs_url}) | [pdf]({item.paper.pdf_url})",
                "",
            ]
        )
        if include_detailed_exploration and item.detail_result is not None:
            lines.append(
                f"- {detail_source_label}: {_detail_source_label(item.detail_result.source, content_language)}"
            )
            lines.extend(
                [
                    "",
                    f"#### {deep_dive_title}",
                    f"- {headline_label}: {item.detail_result.headline}",
                    f"- {contribution_label}: {item.detail_result.contribution_summary}",
                    f"- {context_label}: {item.detail_result.problem_and_context}",
                    f"- {research_question_label}: {item.detail_result.research_question}",
                    f"- {method_label}: {item.detail_result.method_overview}",
                    f"- {novelty_label}: {item.detail_result.novelty_and_positioning}",
                    f"- {setup_label}: {item.detail_result.experimental_setup}",
                    f"- {evidence_label}: {item.detail_result.evidence_and_credibility}",
                    f"- {relevance_label}: {item.detail_result.relevance_to_keywords}",
                    "",
                    f"#### {key_findings_title}",
                ]
            )
            lines.extend(_render_bullets(item.detail_result.key_findings))
            lines.extend(
                [
                    "",
                    f"#### {strengths_title}",
                ]
            )
            lines.extend(_render_bullets(item.detail_result.strengths))
            lines.extend(
                [
                    "",
                    f"#### {limitations_title}",
                ]
            )
            lines.extend(_render_bullets(item.detail_result.limitations))
            lines.extend(
                [
                    "",
                    f"#### {practical_implications_title}",
                ]
            )
            lines.extend(_render_bullets(item.detail_result.practical_implications))
            lines.extend(
                [
                    "",
                    f"#### {open_questions_title}",
                ]
            )
            lines.extend(_render_bullets(item.detail_result.open_questions))
            lines.extend(
                [
                    "",
                    f"#### {reading_guide_title}",
                ]
            )
            lines.extend(_render_bullets(item.detail_result.reading_guide))
            lines.append("")
    return lines


def _render_bullets(values: list[str]) -> list[str]:
    if not values:
        return ["- N/A"]
    return [f"- {value}" for value in values]


def _detail_source_label(source: str, content_language: str) -> str:
    if source == "pdf":
        return "PDF"
    if source == "abstract_fallback":
        return localize_output_text(
            content_language,
            english="Abstract fallback",
            chinese="摘要回退",
        )
    return source
