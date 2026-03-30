from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.clients.arxiv_client import ArxivClient
from app.clients.email_client import EmailClient
from app.clients.openai_client import OpenAIClient
from app.config import Settings
from app.db import Database
from app.models import CandidatePaper, RunWindow
from app.services.delivery_service import DeliveryService
from app.services.digest_service import DigestService
from app.services.filter_service import FilterService
from app.services.ingest_service import IngestService
from app.services.summarize_service import SummarizeService


class DailyDigestPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = logging.getLogger(__name__)
        self.database = Database(settings.database.sqlite_path)
        self.arxiv_client = ArxivClient(
            request_delay_seconds=settings.arxiv.request_delay_seconds,
            user_agent=f"Daily-arXiv-notify/0.1 ({settings.email.from_address})",
        )
        self.llm_client = OpenAIClient(settings.llm)
        self.email_client = EmailClient(settings.email)
        self.ingest_service = IngestService(settings, self.database, self.arxiv_client)
        self.filter_service = FilterService(settings, self.database, self.llm_client)
        self.summarize_service = SummarizeService(settings, self.database, self.llm_client)
        self.digest_service = DigestService(settings)
        self.delivery_service = DeliveryService(settings, self.email_client)

    def close(self) -> None:
        self.arxiv_client.close()
        self.database.close()

    def run(self, *, dry_run: bool = False) -> int:
        self.database.initialize()
        started_at = datetime.now(timezone.utc)
        run_window = self._build_run_window(started_at)
        run_date = started_at.astimezone(self.settings.tzinfo).date().isoformat()
        run_id = self.database.create_run(
            run_date=run_date,
            window_start=run_window.window_start,
            window_end=run_window.window_end,
            overlap_hours=run_window.overlap_hours,
            config_snapshot=self.settings.public_dict(),
            started_at=started_at,
        )

        try:
            ingested = self.ingest_service.ingest(run_window)
            total_fetched = len(ingested)
            total_rule_matched = 0
            selected: list[tuple[int, object, object, object, bool]] = []

            for paper_id, paper in ingested:
                rule_result, ai_result = self.filter_service.evaluate_paper(
                    run_id=run_id,
                    paper_id=paper_id,
                    paper=paper,
                )
                if rule_result.matched:
                    total_rule_matched += 1
                if ai_result.is_related:
                    selected.append(
                        (
                            paper_id,
                            paper,
                            rule_result,
                            ai_result,
                            self._is_update_only(paper, run_window),
                        )
                    )

            selected.sort(
                key=lambda item: max(item[1].published_at, item[1].updated_at),
                reverse=True,
            )
            shortlisted = selected[: self.settings.digest.max_papers]

            candidates: list[CandidatePaper] = []
            for paper_id, paper, rule_result, ai_result, is_update_only in shortlisted:
                summary_result = self.summarize_service.summarize_paper(
                    run_id=run_id,
                    paper_id=paper_id,
                    paper=paper,
                    ai_result=ai_result,
                )
                candidates.append(
                    CandidatePaper(
                        paper_id=paper_id,
                        paper=paper,
                        rule_result=rule_result,
                        ai_result=ai_result,
                        summary_result=summary_result,
                        is_update_only=is_update_only,
                    )
                )

            digest = self.digest_service.build_digest(
                run_time=started_at,
                total_fetched=total_fetched,
                total_rule_matched=total_rule_matched,
                candidates=candidates,
            )
            send_status, sent_at, provider_message_id = self.delivery_service.deliver(
                digest,
                dry_run=dry_run,
            )
            self.database.upsert_digest(
                run_id=run_id,
                markdown_path=digest.markdown_path,
                html_path=digest.html_path,
                recipients=self.settings.email.recipients,
                send_status=send_status,
                sent_at=sent_at,
                provider_message_id=provider_message_id,
            )
            self.database.mark_run_succeeded(run_id, datetime.now(timezone.utc))
            self.logger.info(
                "Run %s completed: fetched=%s, rule_matched=%s, sent=%s",
                run_id,
                total_fetched,
                total_rule_matched,
                digest.paper_count,
            )
            return run_id
        except Exception as exc:
            self.database.mark_run_failed(run_id, datetime.now(timezone.utc), str(exc))
            raise

    def _build_run_window(self, current_run_started_at: datetime) -> RunWindow:
        last_success = self.database.get_last_successful_run()
        overlap = self.settings.arxiv.overlap_hours
        window_end = current_run_started_at
        if last_success is None:
            window_start = window_end - timedelta(hours=overlap)
        else:
            window_start = last_success.window_end - timedelta(hours=overlap)
        return RunWindow(
            window_start=window_start,
            window_end=window_end,
            overlap_hours=overlap,
        )

    def _is_update_only(self, paper: object, run_window: RunWindow) -> bool:
        if not self.settings.arxiv.include_revisions:
            return False
        published_at = paper.published_at
        updated_at = paper.updated_at
        in_publish_window = run_window.window_start < published_at <= run_window.window_end
        in_update_window = run_window.window_start < updated_at <= run_window.window_end
        return (not in_publish_window) and in_update_window
