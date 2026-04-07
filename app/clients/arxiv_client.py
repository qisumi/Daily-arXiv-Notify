from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable

import httpx

from app.models import ArxivPaper, RunWindow
from app.progress import iter_progress


ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
VERSION_PATTERN = re.compile(r"^(?P<id>.+?)(?P<version>v\d+)?$")
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
DEFAULT_ARXIV_BASE_URL = "https://export.arxiv.org"


class PDFDownloadError(RuntimeError):
    """Raised when a paper PDF cannot be downloaded or validated."""


class ArxivClient:
    def __init__(
        self,
        *,
        request_delay_seconds: float = 3.0,
        max_retries: int = 3,
        max_rate_limit_retries: int = 6,
        retry_backoff_seconds: float = 15.0,
        min_rate_limit_delay_seconds: float = 60.0,
        timeout_seconds: int = 30,
        user_agent: str = "Daily-arXiv-notify/0.1",
    ) -> None:
        self.request_delay_seconds = request_delay_seconds
        self.max_retries = max_retries
        self.max_rate_limit_retries = max_rate_limit_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.min_rate_limit_delay_seconds = min_rate_limit_delay_seconds
        self.logger = logging.getLogger(__name__)
        self._last_request_started_at: float | None = None
        self._client = httpx.Client(
            base_url=DEFAULT_ARXIV_BASE_URL,
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
        category_list = list(categories)
        papers: dict[tuple[str, str], ArxivPaper] = {}
        raw_entry_count = 0

        for category in iter_progress(
            category_list,
            total=len(category_list),
            desc="Fetching arXiv",
            unit="category",
        ):
            fetched, category_entry_count = self._fetch_category(
                category=category,
                window=window,
                page_size=page_size,
                max_pages=max_pages,
                include_revisions=include_revisions,
            )
            raw_entry_count += category_entry_count
            for paper in fetched:
                papers[(paper.arxiv_id, paper.version)] = paper

        fetched_papers = sorted(
            papers.values(),
            key=lambda item: max(item.published_at, item.updated_at),
            reverse=True,
        )
        self.logger.info(
            "Fetched %s raw arXiv API entries before deduplication",
            raw_entry_count,
        )
        self.logger.info(
            "Fetched %s unique papers from arXiv across %s categories",
            len(fetched_papers),
            len(category_list),
        )
        return fetched_papers

    def _fetch_category(
        self,
        *,
        category: str,
        window: RunWindow,
        page_size: int,
        max_pages: int,
        include_revisions: bool,
    ) -> tuple[list[ArxivPaper], int]:
        sort_by = "lastUpdatedDate" if include_revisions else "submittedDate"
        papers: list[ArxivPaper] = []
        raw_entry_count = 0

        for page_index in range(max_pages):
            params = {
                "search_query": f"cat:{category}",
                "start": page_index * page_size,
                "max_results": page_size,
                "sortBy": sort_by,
                "sortOrder": "descending",
            }
            response = self._get_with_retries("/api/query", params=params)

            page_papers = self._parse_response(response.text)
            if not page_papers:
                break
            raw_entry_count += len(page_papers)

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

        return papers, raw_entry_count

    def _get_with_retries(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        timeout_seconds: int | None = None,
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = self._send_get_request(
                    path,
                    params=params,
                    timeout_seconds=timeout_seconds,
                )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                retry_limit = self._retry_limit_for_status(exc.response.status_code)
                if (
                    exc.response.status_code not in RETRYABLE_STATUS_CODES
                    or attempt >= retry_limit
                ):
                    raise
                self._sleep_before_retry(
                    delay=self._retry_delay_seconds(exc.response, attempt),
                    reason=f"HTTP {exc.response.status_code}",
                    url=str(exc.request.url),
                    retry_number=attempt + 1,
                    retry_limit=retry_limit,
                )
            except httpx.RequestError as exc:
                if attempt >= self.max_retries:
                    raise
                self._sleep_before_retry(
                    delay=self._retry_delay_seconds(None, attempt),
                    reason=exc.__class__.__name__,
                    url=str(exc.request.url),
                    retry_number=attempt + 1,
                    retry_limit=self.max_retries,
                )
            attempt += 1

        raise RuntimeError("Unreachable arXiv retry loop")  # pragma: no cover

    def _send_get_request(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        timeout_seconds: int | None = None,
    ) -> httpx.Response:
        self._wait_for_request_slot()
        self._last_request_started_at = time.monotonic()
        return self._client.get(path, params=params, timeout=timeout_seconds)

    def download_pdf(
        self,
        *,
        pdf_url: str,
        destination: Path,
        max_file_size_mb: int,
        timeout_seconds: int | None = None,
    ) -> Path:
        if destination.exists() and destination.stat().st_size > 0:
            return destination

        destination.parent.mkdir(parents=True, exist_ok=True)
        max_bytes = max_file_size_mb * 1024 * 1024

        try:
            response = self._get_with_retries(pdf_url, timeout_seconds=timeout_seconds)
            content = response.content
        except Exception as exc:  # pragma: no cover - exercised through fallback paths
            raise PDFDownloadError(f"Failed to download PDF from {pdf_url}") from exc

        content_length = response.headers.get("Content-Length", "").strip()
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    raise PDFDownloadError(
                        f"PDF exceeds the configured size limit of {max_file_size_mb} MB."
                    )
            except ValueError:
                pass

        if len(content) > max_bytes:
            raise PDFDownloadError(
                f"PDF exceeds the configured size limit of {max_file_size_mb} MB."
            )

        if not content:
            raise PDFDownloadError("Downloaded PDF is empty.")

        content_type = response.headers.get("Content-Type", "").lower()
        if "pdf" not in content_type and not content.startswith(b"%PDF-"):
            raise PDFDownloadError(
                "Downloaded content does not look like a valid PDF document."
            )

        destination.write_bytes(content)
        return destination

    def _wait_for_request_slot(self) -> None:
        if self.request_delay_seconds <= 0 or self._last_request_started_at is None:
            return

        elapsed = time.monotonic() - self._last_request_started_at
        remaining = self.request_delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _sleep_before_retry(
        self,
        *,
        delay: float,
        reason: str,
        url: str,
        retry_number: int,
        retry_limit: int,
    ) -> None:
        self.logger.warning(
            "Transient arXiv request failure (%s). Retrying in %.1f seconds (%s/%s): %s",
            reason,
            delay,
            retry_number,
            retry_limit,
            url,
        )
        time.sleep(delay)

    def _retry_delay_seconds(
        self,
        response: httpx.Response | None,
        attempt: int,
    ) -> float:
        delay = self.retry_backoff_seconds * (2**attempt)
        retry_after = self._retry_after_seconds(response)
        if retry_after is not None:
            return max(delay, retry_after)
        if response is not None and response.status_code == 429:
            return max(delay, self.min_rate_limit_delay_seconds)
        return delay

    def _retry_limit_for_status(self, status_code: int) -> int:
        if status_code == 429:
            return max(self.max_retries, self.max_rate_limit_retries)
        return self.max_retries

    @staticmethod
    def _retry_after_seconds(response: httpx.Response | None) -> float | None:
        if response is None:
            return None

        raw_value = response.headers.get("Retry-After", "").strip()
        if not raw_value:
            return None

        try:
            return max(float(raw_value), 0.0)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(raw_value)
            except (TypeError, ValueError, IndexError):
                return None

        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0.0)

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
