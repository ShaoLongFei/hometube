"""
SQLite-backed persistence for HomeTube background jobs.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.job_models import JobItemStatus, JobStatus, SUCCESSFUL_JOB_ITEM_STATES


def utc_now_iso() -> str:
    """Return the current UTC timestamp as ISO-8601 text."""
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """Persistent storage for background download jobs."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    site TEXT NOT NULL,
                    destination_dir TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    max_parallelism INTEGER NOT NULL,
                    total_items INTEGER NOT NULL DEFAULT 0,
                    completed_items INTEGER NOT NULL DEFAULT 0,
                    failed_items INTEGER NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    config_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS job_items (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    item_index INTEGER NOT NULL,
                    video_id TEXT,
                    video_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    resolved_output_name TEXT,
                    workspace_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    progress_percent REAL NOT NULL DEFAULT 0,
                    downloaded_bytes INTEGER NOT NULL DEFAULT 0,
                    total_bytes INTEGER NOT NULL DEFAULT 0,
                    speed_bps REAL NOT NULL DEFAULT 0,
                    eta_seconds INTEGER,
                    status_message TEXT,
                    worker_pid INTEGER,
                    started_at TEXT,
                    finished_at TEXT,
                    last_heartbeat_at TEXT,
                    last_error TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );

                CREATE TABLE IF NOT EXISTS job_logs (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    job_item_id TEXT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id),
                    FOREIGN KEY(job_item_id) REFERENCES job_items(id)
                );

                CREATE TABLE IF NOT EXISTS runtime_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_job_items_job_id
                    ON job_items(job_id);
                CREATE INDEX IF NOT EXISTS idx_job_items_status
                    ON job_items(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_status
                    ON jobs(status);
                """
            )
            self._ensure_job_items_delivery_columns(conn)

    @staticmethod
    def _ensure_job_items_delivery_columns(conn: sqlite3.Connection) -> None:
        """Add delivery metadata columns for older databases."""
        existing_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(job_items)").fetchall()
        }
        required_columns = {
            "normalization_required": "INTEGER",
            "normalization_succeeded": "INTEGER",
            "final_container": "TEXT",
            "final_video_codec": "TEXT",
            "final_audio_summary": "TEXT",
            "final_codec_summary": "TEXT",
            "delivery_warning": "TEXT",
        }

        for column_name, column_type in required_columns.items():
            if column_name in existing_columns:
                continue
            conn.execute(
                f"ALTER TABLE job_items ADD COLUMN {column_name} {column_type}"
            )

    def create_job(
        self,
        *,
        kind: str,
        url: str,
        title: str,
        site: str,
        destination_dir: str,
        config: dict,
        items: list[dict],
        priority: int = 0,
        max_parallelism: int | None = None,
    ) -> str:
        """Create a job and all of its executable items."""
        now = utc_now_iso()
        job_id = uuid4().hex
        total_items = len(items)
        effective_parallelism = (
            max_parallelism
            if max_parallelism is not None
            else (1 if kind == "video" else 4)
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, kind, url, title, site, destination_dir, status, priority,
                    max_parallelism, total_items, completed_items, failed_items,
                    cancel_requested, last_error, config_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, NULL, ?, ?, ?)
                """,
                (
                    job_id,
                    kind,
                    url,
                    title,
                    site,
                    destination_dir,
                    JobStatus.QUEUED.value,
                    priority,
                    effective_parallelism,
                    total_items,
                    json.dumps(config, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )

            for item in items:
                conn.execute(
                    """
                    INSERT INTO job_items (
                        id, job_id, item_index, video_id, video_url, title,
                        resolved_output_name, workspace_path, status, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid4().hex,
                        job_id,
                        item["item_index"],
                        item.get("video_id"),
                        item["video_url"],
                        item["title"],
                        item.get("resolved_output_name"),
                        item["workspace_path"],
                        JobItemStatus.QUEUED.value,
                        now,
                    ),
                )

        return job_id

    def get_job(self, job_id: str) -> dict | None:
        """Return a job row as a plain dict."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job_dict(row) if row else None

    def list_jobs(self) -> list[dict]:
        """List all jobs ordered by creation time."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at ASC"
            ).fetchall()
        return [self._row_to_job_dict(row) for row in rows]

    def get_job_items(self, job_id: str) -> list[dict]:
        """Return all items for a job ordered by playlist position."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM job_items
                WHERE job_id = ?
                ORDER BY item_index ASC, created_rowid_if_missing ASC
                """.replace("created_rowid_if_missing", "rowid"),
                (job_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_job_item(self, item_id: str) -> dict | None:
        """Return a single job item by id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM job_items WHERE id = ?",
                (item_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_job_item_status(
        self,
        item_id: str,
        status: str,
        *,
        last_error: str | None = None,
        progress_percent: float | None = None,
    ) -> None:
        """Update item status and related timing fields."""
        now = utc_now_iso()

        with self._connect() as conn:
            current = conn.execute(
                "SELECT * FROM job_items WHERE id = ?", (item_id,)
            ).fetchone()
            if not current:
                raise KeyError(f"Unknown job item: {item_id}")

            started_at = current["started_at"]
            finished_at = current["finished_at"]

            if status == JobItemStatus.RUNNING.value and started_at is None:
                started_at = now
            if status in {
                JobItemStatus.COMPLETED.value,
                JobItemStatus.FAILED.value,
                JobItemStatus.CANCELLED.value,
                JobItemStatus.SKIPPED.value,
            }:
                finished_at = now

            conn.execute(
                """
                UPDATE job_items
                SET status = ?,
                    last_error = COALESCE(?, last_error),
                    progress_percent = COALESCE(?, progress_percent),
                    started_at = ?,
                    finished_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    last_error,
                    progress_percent,
                    started_at,
                    finished_at,
                    now,
                    item_id,
                ),
            )

    def claim_job_item(self, item_id: str, *, worker_pid: int | None = None) -> bool:
        """Atomically move a queued item into running state."""
        now = utc_now_iso()
        with self._connect() as conn:
            result = conn.execute(
                """
                UPDATE job_items
                SET status = ?,
                    worker_pid = ?,
                    started_at = COALESCE(started_at, ?),
                    updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    JobItemStatus.RUNNING.value,
                    worker_pid,
                    now,
                    now,
                    item_id,
                    JobItemStatus.QUEUED.value,
                ),
            )
        return result.rowcount == 1

    def refresh_job_status(self, job_id: str) -> dict:
        """Recompute aggregate job counters and lifecycle status from items."""
        items = self.get_job_items(job_id)
        job = self.get_job(job_id)
        if not job:
            raise KeyError(f"Unknown job: {job_id}")

        status_counts: dict[str, int] = {}
        for item in items:
            status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1

        completed_items = sum(
            count
            for state, count in status_counts.items()
            if state in {s.value for s in SUCCESSFUL_JOB_ITEM_STATES}
        )
        failed_items = status_counts.get(JobItemStatus.FAILED.value, 0)
        running_items = status_counts.get(JobItemStatus.RUNNING.value, 0)
        queued_items = status_counts.get(JobItemStatus.QUEUED.value, 0)
        cancelled_items = status_counts.get(JobItemStatus.CANCELLED.value, 0)

        if running_items > 0:
            new_status = JobStatus.RUNNING.value
        elif completed_items == len(items):
            new_status = JobStatus.COMPLETED.value
        elif failed_items > 0 and completed_items > 0:
            new_status = JobStatus.PARTIALLY_FAILED.value
        elif failed_items == len(items) or cancelled_items == len(items):
            new_status = (
                JobStatus.CANCELLED.value
                if cancelled_items == len(items)
                else JobStatus.FAILED.value
            )
        elif queued_items == len(items):
            new_status = JobStatus.QUEUED.value
        else:
            new_status = JobStatus.QUEUED.value

        now = utc_now_iso()
        started_at = job["started_at"] or (now if running_items > 0 else None)
        finished_at = now if new_status in {
            JobStatus.COMPLETED.value,
            JobStatus.PARTIALLY_FAILED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        } else None

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?,
                    completed_items = ?,
                    failed_items = ?,
                    started_at = COALESCE(started_at, ?),
                    finished_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    new_status,
                    completed_items,
                    failed_items,
                    started_at,
                    finished_at,
                    now,
                    job_id,
                ),
            )

        refreshed = self.get_job(job_id)
        if refreshed is None:
            raise KeyError(f"Unknown job after refresh: {job_id}")
        return refreshed

    def list_runnable_items(self) -> list[dict]:
        """Return queued items eligible for scheduler dispatch."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    job_items.*,
                    jobs.priority AS priority,
                    jobs.max_parallelism AS job_parallelism,
                    jobs.created_at AS job_created_at,
                    jobs.cancel_requested AS job_cancel_requested
                FROM job_items
                JOIN jobs ON jobs.id = job_items.job_id
                WHERE job_items.status = ?
                  AND jobs.status IN (?, ?)
                  AND jobs.cancel_requested = 0
                ORDER BY jobs.priority DESC, jobs.created_at ASC, job_items.item_index ASC
                """,
                (
                    JobItemStatus.QUEUED.value,
                    JobStatus.QUEUED.value,
                    JobStatus.RUNNING.value,
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_running_items(self) -> list[dict]:
        """Return currently running job items."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM job_items
                WHERE status = ?
                ORDER BY updated_at ASC
                """,
                (JobItemStatus.RUNNING.value,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_active_counts(self) -> dict:
        """Return running item counts globally and by job."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT job_id, COUNT(*) AS active_count
                FROM job_items
                WHERE status = ?
                GROUP BY job_id
                """,
                (JobItemStatus.RUNNING.value,),
            ).fetchall()

        per_job = {row["job_id"]: row["active_count"] for row in rows}
        return {"global": sum(per_job.values()), "per_job": per_job}

    def set_job_item_runtime(
        self,
        item_id: str,
        *,
        worker_pid: int | None | object = ...,
        retry_count: int | None | object = ...,
        last_heartbeat_at: str | None | object = ...,
    ) -> None:
        """Update runtime-related fields for a job item."""
        now = utc_now_iso()
        with self._connect() as conn:
            current = conn.execute(
                "SELECT id FROM job_items WHERE id = ?",
                (item_id,),
            ).fetchone()
            if not current:
                raise KeyError(f"Unknown job item: {item_id}")

            assignments = ["updated_at = ?"]
            params: list[object] = [now]

            if worker_pid is not ...:
                assignments.append("worker_pid = ?")
                params.append(worker_pid)
            if retry_count is not ...:
                assignments.append("retry_count = ?")
                params.append(retry_count)
            if last_heartbeat_at is not ...:
                assignments.append("last_heartbeat_at = ?")
                params.append(last_heartbeat_at)

            params.append(item_id)

            conn.execute(
                f"""
                UPDATE job_items
                SET {", ".join(assignments)}
                WHERE id = ?
                """,
                params,
            )

    def update_job_item_progress(
        self,
        item_id: str,
        *,
        progress_percent: float | None = None,
        downloaded_bytes: int | None = None,
        total_bytes: int | None = None,
        speed_bps: float | None = None,
        eta_seconds: int | None = None,
        status_message: str | None = None,
    ) -> None:
        """Persist incremental runtime progress for a job item."""
        now = utc_now_iso()
        with self._connect() as conn:
            current = conn.execute(
                "SELECT id FROM job_items WHERE id = ?",
                (item_id,),
            ).fetchone()
            if not current:
                raise KeyError(f"Unknown job item: {item_id}")

            conn.execute(
                """
                UPDATE job_items
                SET progress_percent = COALESCE(?, progress_percent),
                    downloaded_bytes = COALESCE(?, downloaded_bytes),
                    total_bytes = COALESCE(?, total_bytes),
                    speed_bps = COALESCE(?, speed_bps),
                    eta_seconds = COALESCE(?, eta_seconds),
                    status_message = COALESCE(?, status_message),
                    last_heartbeat_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    progress_percent,
                    downloaded_bytes,
                    total_bytes,
                    speed_bps,
                    eta_seconds,
                    status_message,
                    now,
                    now,
                    item_id,
                ),
            )

    def update_job_item_delivery(
        self,
        item_id: str,
        *,
        normalization_required: bool | None = None,
        normalization_succeeded: bool | None = None,
        final_container: str | None = None,
        final_video_codec: str | None = None,
        final_audio_summary: str | None = None,
        final_codec_summary: str | None = None,
        delivery_warning: str | None = None,
    ) -> None:
        """Persist final delivery codec and warning metadata for one item."""
        now = utc_now_iso()
        with self._connect() as conn:
            current = conn.execute(
                "SELECT id FROM job_items WHERE id = ?",
                (item_id,),
            ).fetchone()
            if not current:
                raise KeyError(f"Unknown job item: {item_id}")

            conn.execute(
                """
                UPDATE job_items
                SET normalization_required = ?,
                    normalization_succeeded = ?,
                    final_container = COALESCE(?, final_container),
                    final_video_codec = COALESCE(?, final_video_codec),
                    final_audio_summary = COALESCE(?, final_audio_summary),
                    final_codec_summary = COALESCE(?, final_codec_summary),
                    delivery_warning = COALESCE(?, delivery_warning),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    None if normalization_required is None else int(normalization_required),
                    None if normalization_succeeded is None else int(normalization_succeeded),
                    final_container,
                    final_video_codec,
                    final_audio_summary,
                    final_codec_summary,
                    delivery_warning,
                    now,
                    item_id,
                ),
            )

    def record_job_log(
        self,
        *,
        job_id: str,
        level: str,
        message: str,
        job_item_id: str | None = None,
    ) -> str:
        """Insert a structured job log event."""
        log_id = uuid4().hex
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO job_logs (id, job_id, job_item_id, level, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (log_id, job_id, job_item_id, level, message, now),
            )
        return log_id

    def list_job_logs(self, job_id: str, *, limit: int = 20) -> list[dict]:
        """Return recent structured logs for one job, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM job_logs
                WHERE job_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (job_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _row_to_job_dict(row: sqlite3.Row) -> dict:
        data = dict(row)
        data["config"] = json.loads(data.pop("config_json"))
        return data
