from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import Database


def test_database_upsert_and_last_successful_run(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    db.initialize()

    now = datetime.now(timezone.utc)
    run_id = db.create_run(
        run_date="2026-03-30",
        window_start=now - timedelta(hours=36),
        window_end=now,
        overlap_hours=36,
        config_snapshot={"ok": True},
        started_at=now,
    )
    db.mark_run_succeeded(run_id, now + timedelta(minutes=1))

    paper = {
        "arxiv_id": "1234.5678",
        "version": "v1",
        "title": "Test title",
        "summary": "Test summary",
        "authors": ["Alice", "Bob"],
        "categories": ["cs.AI"],
        "published_at": now,
        "updated_at": now,
        "abs_url": "https://arxiv.org/abs/1234.5678v1",
        "pdf_url": "https://arxiv.org/pdf/1234.5678v1.pdf",
        "source_payload": {"raw": True},
    }

    first_id = db.upsert_paper(paper)
    second_id = db.upsert_paper(paper)
    last_run = db.get_last_successful_run()

    assert first_id == second_id
    assert last_run is not None
    assert last_run.id == run_id
    assert last_run.window_end == now

    db.close()
