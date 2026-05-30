from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.jobs import JobRecord


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """Simple SQLite job store for v1.

    V1 stores request_json directly, including base64 image payloads, so the
    background job can reconstruct work later. For larger payloads, move input
    media to S3/presigned uploads instead of storing large base64 blobs here.
    """
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    story_json TEXT,
                    pdf_s3_key TEXT,
                    pdf_url TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def create_job(self, job_id: str, status: str, request_json: dict[str, Any]) -> JobRecord:
        now = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, status, request_json, story_json, pdf_s3_key, pdf_url, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, NULL, NULL, NULL, NULL, ?, ?)
                """,
                (job_id, status, json.dumps(request_json), now, now),
            )
            conn.commit()
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return JobRecord(
            job_id=row["job_id"],
            status=row["status"],
            request_json=json.loads(row["request_json"]),
            story_json=json.loads(row["story_json"]) if row["story_json"] else None,
            pdf_s3_key=row["pdf_s3_key"],
            pdf_url=row["pdf_url"],
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def update_job_status(self, job_id: str, status: str) -> JobRecord | None:
        now = _utcnow()
        with self._connect() as conn:
            conn.execute("UPDATE jobs SET status = ?, updated_at = ? WHERE job_id = ?", (status, now, job_id))
            conn.commit()
        return self.get_job(job_id)

    def mark_succeeded(self, job_id: str, story_json: dict[str, Any] | None, pdf_s3_key: str | None, pdf_url: str | None) -> JobRecord | None:
        now = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, story_json = ?, pdf_s3_key = ?, pdf_url = ?, error_message = NULL, updated_at = ?
                WHERE job_id = ?
                """,
                ("succeeded", json.dumps(story_json) if story_json is not None else None, pdf_s3_key, pdf_url, now, job_id),
            )
            conn.commit()
        return self.get_job(job_id)

    def mark_failed(self, job_id: str, error_message: str) -> JobRecord | None:
        now = _utcnow()
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, error_message = ?, updated_at = ? WHERE job_id = ?",
                ("failed", error_message, now, job_id),
            )
            conn.commit()
        return self.get_job(job_id)

    def mark_stale_processing_jobs_failed(self, stale_before_iso: str) -> int:
        """Simple v1 stale-job helper.

        In a single-instance setup this can be called at startup or by a future
        maintenance task. Multi-worker scale should move to a real queue.
        """

        with self._connect() as conn:
            result = conn.execute(
                """
                UPDATE jobs
                SET status = 'failed', error_message = 'Job became stale while processing.', updated_at = ?
                WHERE status = 'processing' AND updated_at < ?
                """,
                (_utcnow(), stale_before_iso),
            )
            conn.commit()
            return result.rowcount
