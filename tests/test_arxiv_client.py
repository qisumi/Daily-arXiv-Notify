from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path

import httpx

from app.clients.arxiv_client import ArxivClient
from app.models import RunWindow


class FakeClock:
    def __init__(self) -> None:
        self.current = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += seconds


def _make_window() -> RunWindow:
    return RunWindow(
        window_start=datetime(2026, 3, 30, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
        overlap_hours=36,
    )


def _make_feed(identifier: str, category: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/{identifier}</id>
    <updated>2026-03-31T01:00:00Z</updated>
    <published>2026-03-31T00:00:00Z</published>
    <title>Test paper for {category}</title>
    <summary>Test summary.</summary>
    <author><name>Alice</name></author>
    <category term="{category}" />
    <link href="http://arxiv.org/abs/{identifier}" rel="alternate" type="text/html" />
    <link href="http://arxiv.org/pdf/{identifier}.pdf" title="pdf" type="application/pdf" />
  </entry>
</feed>
"""


def _swap_transport(client: ArxivClient, transport: httpx.BaseTransport) -> None:
    client.close()
    client._client = httpx.Client(
        base_url="https://export.arxiv.org",
        headers={"User-Agent": "Daily-arXiv-notify/test"},
        timeout=30,
        transport=transport,
    )


def test_arxiv_client_retries_429_with_retry_after(monkeypatch) -> None:
    clock = FakeClock()
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "7"},
                request=request,
                text="rate limited",
            )
        return httpx.Response(
            200,
            request=request,
            text=_make_feed("2503.00001v1", "cs.AI"),
        )

    monkeypatch.setattr("app.clients.arxiv_client.time.monotonic", clock.monotonic)
    monkeypatch.setattr("app.clients.arxiv_client.time.sleep", clock.sleep)

    client = ArxivClient(request_delay_seconds=3.0, max_retries=2, retry_backoff_seconds=5.0)
    _swap_transport(client, httpx.MockTransport(handler))

    papers = client.fetch_papers(
        categories=["cs.AI"],
        window=_make_window(),
        page_size=100,
        max_pages=1,
        include_revisions=False,
    )

    assert len(papers) == 1
    assert call_count == 2
    assert clock.sleeps == [7.0]

    client.close()


def test_arxiv_client_uses_extended_retry_budget_for_429_without_retry_after(
    monkeypatch,
) -> None:
    clock = FakeClock()
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return httpx.Response(429, request=request, text="rate limited")
        return httpx.Response(
            200,
            request=request,
            text=_make_feed("2503.00001v1", "cs.AI"),
        )

    monkeypatch.setattr("app.clients.arxiv_client.time.monotonic", clock.monotonic)
    monkeypatch.setattr("app.clients.arxiv_client.time.sleep", clock.sleep)

    client = ArxivClient(
        request_delay_seconds=3.0,
        max_retries=1,
        max_rate_limit_retries=3,
        retry_backoff_seconds=5.0,
        min_rate_limit_delay_seconds=20.0,
    )
    _swap_transport(client, httpx.MockTransport(handler))

    papers = client.fetch_papers(
        categories=["cs.AI"],
        window=_make_window(),
        page_size=100,
        max_pages=1,
        include_revisions=False,
    )

    assert len(papers) == 1
    assert call_count == 4
    assert clock.sleeps == [20.0, 20.0, 20.0]

    client.close()


def test_arxiv_client_spaces_requests_across_categories(monkeypatch) -> None:
    clock = FakeClock()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        category = request.url.params["search_query"].split(":", 1)[1]
        calls.append(category)
        identifier = "2503.00001v1" if category == "cs.AI" else "2503.00002v1"
        return httpx.Response(
            200,
            request=request,
            text=_make_feed(identifier, category),
        )

    monkeypatch.setattr("app.clients.arxiv_client.time.monotonic", clock.monotonic)
    monkeypatch.setattr("app.clients.arxiv_client.time.sleep", clock.sleep)

    client = ArxivClient(request_delay_seconds=3.0, max_retries=0, retry_backoff_seconds=5.0)
    _swap_transport(client, httpx.MockTransport(handler))

    papers = client.fetch_papers(
        categories=["cs.AI", "cs.LG"],
        window=_make_window(),
        page_size=100,
        max_pages=1,
        include_revisions=False,
    )

    assert len(papers) == 2
    assert calls == ["cs.AI", "cs.LG"]
    assert clock.sleeps == [3.0]

    client.close()


def test_arxiv_client_logs_raw_and_unique_paper_counts(monkeypatch, caplog) -> None:
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        category = request.url.params["search_query"].split(":", 1)[1]
        return httpx.Response(
            200,
            request=request,
            text=_make_feed("2503.00001v1", category),
        )

    monkeypatch.setattr("app.clients.arxiv_client.time.monotonic", clock.monotonic)
    monkeypatch.setattr("app.clients.arxiv_client.time.sleep", clock.sleep)

    client = ArxivClient(request_delay_seconds=3.0, max_retries=0, retry_backoff_seconds=5.0)
    _swap_transport(client, httpx.MockTransport(handler))

    with caplog.at_level(logging.INFO):
        papers = client.fetch_papers(
            categories=["cs.AI", "cs.LG"],
            window=_make_window(),
            page_size=100,
            max_pages=1,
            include_revisions=False,
        )

    assert len(papers) == 1
    assert "Fetched 2 raw arXiv API entries before deduplication" in caplog.text
    assert "Fetched 1 unique papers from arXiv across 2 categories" in caplog.text

    client.close()


def test_arxiv_client_downloads_and_validates_pdf(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={"Content-Type": "application/pdf"},
            content=b"%PDF-1.4\n%fake pdf\n",
        )

    client = ArxivClient(request_delay_seconds=0.0, max_retries=0, retry_backoff_seconds=5.0)
    _swap_transport(client, httpx.MockTransport(handler))

    downloaded = client.download_pdf(
        pdf_url="https://arxiv.org/pdf/1234.5678.pdf",
        destination=tmp_path / "paper.pdf",
        max_file_size_mb=1,
        timeout_seconds=30,
    )

    assert downloaded.exists()
    assert downloaded.read_bytes().startswith(b"%PDF-")

    client.close()
