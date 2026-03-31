from __future__ import annotations

from datetime import datetime

from app.config import Settings
from app.models import CandidatePaper, RenderedDigest
from app.render.html_renderer import render_digest_html
from app.render.markdown_renderer import render_digest_markdown


class DigestService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.digest.output_dir.mkdir(parents=True, exist_ok=True)

    def build_digest(
        self,
        *,
        run_time: datetime,
        total_fetched: int,
        total_rule_matched: int,
        candidates: list[CandidatePaper],
    ) -> RenderedDigest:
        markdown = render_digest_markdown(
            run_time=run_time,
            timezone_name=self.settings.timezone,
            categories=self.settings.arxiv.categories,
            total_fetched=total_fetched,
            total_rule_matched=total_rule_matched,
            candidates=candidates,
            content_language=self.settings.llm.output_language,
        )
        html = render_digest_html(markdown)
        digest_date = run_time.astimezone(self.settings.tzinfo).date().isoformat()
        markdown_path = self.settings.digest.output_dir / f"digest-{digest_date}.md"
        html_path = self.settings.digest.output_dir / f"digest-{digest_date}.html"
        markdown_path.write_text(markdown, encoding="utf-8")
        html_path.write_text(html, encoding="utf-8")

        subject = f"Daily arXiv Digest | {digest_date} | {len(candidates)} papers"
        return RenderedDigest(
            subject=subject,
            markdown=markdown,
            html=html,
            markdown_path=markdown_path,
            html_path=html_path,
            paper_count=len(candidates),
        )
