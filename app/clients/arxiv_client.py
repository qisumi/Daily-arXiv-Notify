from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Iterable

import httpx

from app.models import ArxivPaper, RunWindow


ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
VERSION_PATTERN = re.compile(r"^(?P<id>.+?)(?P<version>v\d+)?$")


class ArxivClient:
    def __init__(
        self,
        *,
        request_delay_seconds: float = 3.0,
        timeout_seconds: int = 30,
        user_agent: str = "Daily-arXiv-notify/0.1",
    ) -> None:
        self.request_delay_seconds = request_delay_seconds
        self.logger = logging.getLogger(__name__)
        self._client = httpx.Client(
            base_url="https://export.arxiv.org",
            headers={"User-Agent": user_agent},
            timeout=timeout_seconds,
        )

    def close(self) -> None:
        self._client.close()

    def fetch_papers(
        self,
        *,
        categories: Iterable[str],
        window: RunWindow,
        page_size: int,
        max_pages: int,
        include_revisions: bool,
    ) -> list[ArxivPaper]:
        papers: dict[tuple[str, str], ArxivPaper] = {}

        for category in categories:
            fetched = self._fetch_category(
                category=category,
                window=window,
                page_size=page_size,
                max_pages=max_pages,
                include_revisions=include_revisions,
            )
            for paper in fetched:
                papers[(paper.arxiv_id, paper.version)] = paper

        return sorted(
            papers.values(),
            key=lambda item: max(item.published_at, item.updated_at),
            reverse=True,
        )

    def _fetch_category(
        self,
        *,
        category: str,
        window: RunWindow,
        page_size: int,
        max_pages: int,
        include_revisions: bool,
    ) -> list[ArxivPaper]:
        sort_by = "lastUpdatedDate" if include_revisions else "submittedDate"
        papers: list[ArxivPaper] = []

        for page_index in range(max_pages):
            if page_index > 0:
                time.sleep(self.request_delay_seconds)

            params = {
                "search_query": f"cat:{category}",
                "start": page_index * page_size,
                "max_results": page_size,
                "sortBy": sort_by,
                "sortOrder": "descending",
            }
            response = self._client.get("/api/query", params=params)
            response.raise_for_status()

            page_papers = self._parse_response(response.text)
            if not page_papers:
                break

            self.logger.info(
                "Fetched %s entries from arXiv category %s (page %s/%s)",
                len(page_papers),
                category,
                page_index + 1,
                max_pages,
            )

            for paper in page_papers:
                if self._is_in_window(paper, window, include_revisions):
                    papers.append(paper)

            if self._should_stop(page_papers, window, include_revisions):
                break

        return papers

    def _parse_response(self, xml_text: str) -> list[ArxivPaper]:
        root = ET.fromstring(xml_text)
        papers: list[ArxivPaper] = []
        for entry in root.findall("atom:entry", ATOM_NS):
            abs_url = self._text(entry, "atom:id")
            title = self._clean_text(self._text(entry, "atom:title"))
            summary = self._clean_text(self._text(entry, "atom:summary"))
            published_at = self._parse_datetime(self._text(entry, "atom:published"))
            updated_at = self._parse_datetime(self._text(entry, "atom:updated"))
            authors = [
                self._clean_text(self._text(author, "atom:name"))
                for author in entry.findall("atom:author", ATOM_NS)
            ]
            categories = [
                category.attrib["term"]
                for category in entry.findall("atom:category", ATOM_NS)
                if category.attrib.get("term")
            ]
            pdf_url = self._resolve_pdf_url(entry, abs_url)
            raw_identifier = abs_url.rstrip("/").split("/")[-1]
            arxiv_id, version, version_source = self._split_identifier(
                raw_identifier, updated_at
            )

            papers.append(
                ArxivPaper(
                    arxiv_id=arxiv_id,
                    version=version,
                    title=title,
                    summary=summary,
                    authors=authors,
                    categories=categories,
                    published_at=published_at,
                    updated_at=updated_at,
                    abs_url=abs_url,
                    pdf_url=pdf_url,
                    source_payload={
                        "raw_identifier": raw_identifier,
                        "version_source": version_source,
                        "entry_xml": ET.tostring(entry, encoding="unicode"),
                    },
                )
            )

        return papers

    @staticmethod
    def _clean_text(text: str) -> str:
        return " ".join(text.split())

    @staticmethod
    def _text(element: ET.Element, path: str) -> str:
        child = element.find(path, ATOM_NS)
        if child is None or child.text is None:
            return ""
        return child.text

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)

    def _resolve_pdf_url(self, entry: ET.Element, abs_url: str) -> str:
        for link in entry.findall("atom:link", ATOM_NS):
            href = link.attrib.get("href", "")
            title = link.attrib.get("title", "")
            link_type = link.attrib.get("type", "")
            if title == "pdf" or link_type == "application/pdf":
                return href
        return f"{abs_url}.pdf"

    def _split_identifier(
        self,
        raw_identifier: str,
        updated_at: datetime,
    ) -> tuple[str, str, str]:
        match = VERSION_PATTERN.match(raw_identifier)
        if not match:  # pragma: no cover
            fallback = updated_at.strftime("updated-%Y%m%dT%H%M%SZ")
            return raw_identifier, fallback, "fallback"

        identifier = match.group("id") or raw_identifier
        version = match.group("version")
        if version:
            return identifier, version, "identifier"

        fallback = updated_at.strftime("updated-%Y%m%dT%H%M%SZ")
        return identifier, fallback, "updated_at_fallback"

    @staticmethod
    def _is_in_window(
        paper: ArxivPaper,
        window: RunWindow,
        include_revisions: bool,
    ) -> bool:
        if window.window_start < paper.published_at <= window.window_end:
            return True
        if include_revisions and window.window_start < paper.updated_at <= window.window_end:
            return True
        return False

    @staticmethod
    def _should_stop(
        papers: list[ArxivPaper],
        window: RunWindow,
        include_revisions: bool,
    ) -> bool:
        if include_revisions:
            return all(paper.updated_at <= window.window_start for paper in papers)
        return all(paper.published_at <= window.window_start for paper in papers)
