from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from app.models import KeywordFilterResult, PaperSummaryResult, RunRecord


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._connection
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def close(self) -> None:
        self._connection.close()

    def initialize(self) -> None:
        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS papers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    arxiv_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    authors_json TEXT NOT NULL,
                    categories_json TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    abs_url TEXT NOT NULL,
                    pdf_url TEXT NOT NULL,
                    source_payload_json TEXT NOT NULL,
                    UNIQUE(arxiv_id, version)
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    window_start TEXT NOT NULL,
                    window_end TEXT NOT NULL,
                    overlap_hours INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    config_snapshot_json TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS paper_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    paper_id INTEGER NOT NULL,
                    rule_match INTEGER NOT NULL,
                    rule_reason TEXT NOT NULL,
                    ai_is_related INTEGER NOT NULL,
                    ai_reason TEXT NOT NULL,
                    matched_keywords_json TEXT NOT NULL,
                    evaluated_keywords_json TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(id),
                    FOREIGN KEY(paper_id) REFERENCES papers(id)
                );

                CREATE INDEX IF NOT EXISTS idx_eval_cache
                    ON paper_evaluations(paper_id, evaluated_keywords_json, prompt_version, model_name);

                CREATE TABLE IF NOT EXISTS paper_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    paper_id INTEGER NOT NULL,
                    one_line TEXT NOT NULL,
                    problem TEXT NOT NULL,
                    method TEXT NOT NULL,
                    why_it_matters TEXT NOT NULL,
                    limitations TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(id),
                    FOREIGN KEY(paper_id) REFERENCES papers(id)
                );

                CREATE INDEX IF NOT EXISTS idx_summary_cache
                    ON paper_summaries(paper_id, prompt_version, model_name);

                CREATE TABLE IF NOT EXISTS digests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL UNIQUE,
                    markdown_path TEXT NOT NULL,
                    html_path TEXT NOT NULL,
                    recipient_list_json TEXT NOT NULL,
                    send_status TEXT NOT NULL,
                    sent_at TEXT,
                    provider_message_id TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );
                """
            )

    def create_run(
        self,
        *,
        run_date: str,
        window_start: datetime,
        window_end: datetime,
        overlap_hours: int,
        config_snapshot: dict[str, Any],
        started_at: datetime,
    ) -> int:
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO runs (
                    run_date, window_start, window_end, overlap_hours,
                    status, config_snapshot_json, started_at
                ) VALUES (?, ?, ?, ?, 'running', ?, ?)
                """,
                (
                    run_date,
                    window_start.isoformat(),
                    window_end.isoformat(),
                    overlap_hours,
                    _json_dumps(config_snapshot),
                    started_at.isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def mark_run_succeeded(self, run_id: int, finished_at: datetime) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = 'succeeded', finished_at = ?, error_message = NULL
                WHERE id = ?
                """,
                (finished_at.isoformat(), run_id),
            )

    def mark_run_failed(self, run_id: int, finished_at: datetime, error_message: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = 'failed', finished_at = ?, error_message = ?
                WHERE id = ?
                """,
                (finished_at.isoformat(), error_message[:2000], run_id),
            )

    def get_last_successful_run(self) -> RunRecord | None:
        row = self._connection.execute(
            """
            SELECT *
            FROM runs
            WHERE status = 'succeeded'
            ORDER BY window_end DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        return RunRecord(
            id=int(row["id"]),
            run_date=row["run_date"],
            window_start=_parse_dt(row["window_start"]) or datetime.min,
            window_end=_parse_dt(row["window_end"]) or datetime.min,
            overlap_hours=int(row["overlap_hours"]),
            status=row["status"],
            config_snapshot=json.loads(row["config_snapshot_json"]),
            started_at=_parse_dt(row["started_at"]) or datetime.min,
            finished_at=_parse_dt(row["finished_at"]),
            error_message=row["error_message"],
        )

    def upsert_paper(self, paper: dict[str, Any]) -> int:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO papers (
                    arxiv_id, version, title, summary, authors_json, categories_json,
                    published_at, updated_at, abs_url, pdf_url, source_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(arxiv_id, version) DO UPDATE SET
                    title = excluded.title,
                    summary = excluded.summary,
                    authors_json = excluded.authors_json,
                    categories_json = excluded.categories_json,
                    published_at = excluded.published_at,
                    updated_at = excluded.updated_at,
                    abs_url = excluded.abs_url,
                    pdf_url = excluded.pdf_url,
                    source_payload_json = excluded.source_payload_json
                """,
                (
                    paper["arxiv_id"],
                    paper["version"],
                    paper["title"],
                    paper["summary"],
                    _json_dumps(paper["authors"]),
                    _json_dumps(paper["categories"]),
                    paper["published_at"].isoformat(),
                    paper["updated_at"].isoformat(),
                    paper["abs_url"],
                    paper["pdf_url"],
                    _json_dumps(paper["source_payload"]),
                ),
            )
            row = conn.execute(
                "SELECT id FROM papers WHERE arxiv_id = ? AND version = ?",
                (paper["arxiv_id"], paper["version"]),
            ).fetchone()
            if row is None:  # pragma: no cover
                raise RuntimeError("Paper upsert failed unexpectedly.")
            return int(row["id"])

    def get_cached_evaluation(
        self,
        *,
        paper_id: int,
        evaluated_keywords: list[str],
        model_name: str,
        prompt_version: str,
    ) -> KeywordFilterResult | None:
        row = self._connection.execute(
            """
            SELECT ai_is_related, ai_reason, matched_keywords_json
            FROM paper_evaluations
            WHERE paper_id = ?
              AND evaluated_keywords_json = ?
              AND model_name = ?
              AND prompt_version = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                paper_id,
                _json_dumps(sorted(evaluated_keywords)),
                model_name,
                prompt_version,
            ),
        ).fetchone()
        if row is None:
            return None
        return KeywordFilterResult(
            is_related=bool(row["ai_is_related"]),
            matched_keywords=json.loads(row["matched_keywords_json"]),
            reason=row["ai_reason"],
        )

    def insert_evaluation(
        self,
        *,
        run_id: int,
        paper_id: int,
        rule_match: bool,
        rule_reason: str,
        ai_result: KeywordFilterResult,
        evaluated_keywords: list[str],
        model_name: str,
        prompt_version: str,
        created_at: datetime,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO paper_evaluations (
                    run_id, paper_id, rule_match, rule_reason, ai_is_related, ai_reason,
                    matched_keywords_json, evaluated_keywords_json, model_name,
                    prompt_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    paper_id,
                    int(rule_match),
                    rule_reason,
                    int(ai_result.is_related),
                    ai_result.reason,
                    _json_dumps(ai_result.matched_keywords),
                    _json_dumps(sorted(evaluated_keywords)),
                    model_name,
                    prompt_version,
                    created_at.isoformat(),
                ),
            )

    def get_cached_summary(
        self,
        *,
        paper_id: int,
        model_name: str,
        prompt_version: str,
    ) -> PaperSummaryResult | None:
        row = self._connection.execute(
            """
            SELECT one_line, problem, method, why_it_matters, limitations, tags_json
            FROM paper_summaries
            WHERE paper_id = ? AND model_name = ? AND prompt_version = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (paper_id, model_name, prompt_version),
        ).fetchone()
        if row is None:
            return None
        return PaperSummaryResult(
            one_line=row["one_line"],
            problem=row["problem"],
            method=row["method"],
            why_it_matters=row["why_it_matters"],
            limitations=row["limitations"],
            tags=json.loads(row["tags_json"]),
        )

    def insert_summary(
        self,
        *,
        run_id: int,
        paper_id: int,
        summary: PaperSummaryResult,
        model_name: str,
        prompt_version: str,
        created_at: datetime,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO paper_summaries (
                    run_id, paper_id, one_line, problem, method,
                    why_it_matters, limitations, tags_json,
                    model_name, prompt_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    paper_id,
                    summary.one_line,
                    summary.problem,
                    summary.method,
                    summary.why_it_matters,
                    summary.limitations,
                    _json_dumps(summary.tags),
                    model_name,
                    prompt_version,
                    created_at.isoformat(),
                ),
            )

    def upsert_digest(
        self,
        *,
        run_id: int,
        markdown_path: Path,
        html_path: Path,
        recipients: list[str],
        send_status: str,
        sent_at: datetime | None,
        provider_message_id: str | None,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO digests (
                    run_id, markdown_path, html_path, recipient_list_json,
                    send_status, sent_at, provider_message_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    markdown_path = excluded.markdown_path,
                    html_path = excluded.html_path,
                    recipient_list_json = excluded.recipient_list_json,
                    send_status = excluded.send_status,
                    sent_at = excluded.sent_at,
                    provider_message_id = excluded.provider_message_id
                """,
                (
                    run_id,
                    str(markdown_path),
                    str(html_path),
                    _json_dumps(recipients),
                    send_status,
                    sent_at.isoformat() if sent_at else None,
                    provider_message_id,
                ),
            )
