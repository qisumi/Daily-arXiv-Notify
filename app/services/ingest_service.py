from __future__ import annotations

from dataclasses import asdict

from app.clients.arxiv_client import ArxivClient
from app.config import Settings
from app.db import Database
from app.models import ArxivPaper, RunWindow


class IngestService:
    def __init__(self, settings: Settings, database: Database, client: ArxivClient) -> None:
        self.settings = settings
        self.database = database
        self.client = client

    def ingest(self, window: RunWindow) -> list[tuple[int, ArxivPaper]]:
        papers = self.client.fetch_papers(
            categories=self.settings.arxiv.categories,
            window=window,
            page_size=self.settings.arxiv.page_size,
            max_pages=self.settings.arxiv.max_pages,
            include_revisions=self.settings.arxiv.include_revisions,
        )
        persisted: list[tuple[int, ArxivPaper]] = []
        for paper in papers:
            paper_id = self.database.upsert_paper(asdict(paper))
            persisted.append((paper_id, paper))
        return persisted
