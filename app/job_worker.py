"""
Worker-side execution wrapper for a single background job item.
"""

from collections.abc import Callable

from app.job_models import JobItemStatus
from app.job_store import JobStore


def execute_job_item(
    store: JobStore,
    item_id: str,
    handler: Callable[[dict, dict], None],
    *,
    worker_pid: int | None = None,
) -> bool:
    """
    Claim and execute one job item with consistent state transitions.

    Returns True on success, False on claim refusal or execution failure.
    """
    item = store.get_job_item(item_id)
    if not item:
        return False

    if item["status"] == JobItemStatus.QUEUED.value:
        if not store.claim_job_item(item_id, worker_pid=worker_pid):
            return False
        item = store.get_job_item(item_id)
        if not item:
            return False
    elif item["status"] == JobItemStatus.RUNNING.value:
        existing_pid = item.get("worker_pid")
        if existing_pid not in {None, worker_pid}:
            return False
        store.set_job_item_runtime(item_id, worker_pid=worker_pid)
        item = store.get_job_item(item_id)
        if not item:
            return False
    else:
        return False

    job = store.get_job(item["job_id"])
    if not job:
        return False

    store.record_job_log(
        job_id=job["id"],
        job_item_id=item_id,
        level="info",
        message="Worker started",
    )
    store.update_job_item_progress(item_id, status_message="Starting")
    store.refresh_job_status(job["id"])

    try:
        handler(job, item)
    except Exception as exc:
        store.update_job_item_status(item_id, "failed", last_error=str(exc))
        store.update_job_item_progress(item_id, status_message="Failed")
        store.record_job_log(
            job_id=job["id"],
            job_item_id=item_id,
            level="error",
            message=str(exc),
        )
        store.refresh_job_status(job["id"])
        return False

    store.update_job_item_status(item_id, "completed", progress_percent=100.0)
    store.update_job_item_progress(
        item_id,
        progress_percent=100.0,
        eta_seconds=0,
        status_message="Completed",
    )
    store.record_job_log(
        job_id=job["id"],
        job_item_id=item_id,
        level="info",
        message="Worker completed successfully",
    )
    store.refresh_job_status(job["id"])
    return True
