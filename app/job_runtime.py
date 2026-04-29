"""
Runtime helpers for the HomeTube background-job scheduler.
"""

from __future__ import annotations

import errno
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from app.job_models import JobItemStatus
from app.job_scheduler import select_dispatch_batch
from app.job_store import JobStore, is_sqlite_lock_error

_scheduler_threads: dict[str, threading.Thread] = {}


class SchedulerLock:
    """Very small file-based singleton lock for the scheduler process."""

    def __init__(self, lock_path: Path | str):
        self.lock_path = Path(lock_path)
        self._held = False

    def acquire(self) -> bool:
        """Try to acquire the lock. Returns False if another owner already holds it."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(
                self.lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644,
            )
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                if self._reclaim_stale_lock():
                    return self.acquire()
                return False
            raise

        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))

        self._held = True
        return True

    def release(self) -> None:
        """Release the lock if currently held."""
        if self._held and self.lock_path.exists():
            self.lock_path.unlink()
        self._held = False

    def _reclaim_stale_lock(self) -> bool:
        """Delete the lock file if it belongs to a non-existent process."""
        try:
            owner_text = self.lock_path.read_text(encoding="utf-8").strip()
            owner_pid = int(owner_text)
        except (OSError, ValueError):
            owner_pid = 0

        if owner_pid > 0 and _pid_exists_portable(owner_pid):
            return False

        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True


def recover_orphaned_running_items(
    store: JobStore,
    *,
    pid_exists: Callable[[int], bool],
    max_retries: int = 1,
) -> int:
    """
    Recover running items whose worker process no longer exists.

    Recovery policy:
    - increment retry count
    - if retry budget remains, move back to queued
    - otherwise mark item failed
    - always clear worker_pid
    """
    recovered = 0
    running_items = store.list_running_items()

    for item in running_items:
        worker_pid = item.get("worker_pid")
        if worker_pid and pid_exists(int(worker_pid)):
            continue

        next_retry_count = int(item.get("retry_count") or 0) + 1
        next_status = (
            JobItemStatus.QUEUED.value
            if next_retry_count <= max_retries
            else JobItemStatus.FAILED.value
        )
        last_error = (
            "Recovered after scheduler restart"
            if next_status == JobItemStatus.QUEUED.value
            else "Worker missing after restart; retry budget exhausted"
        )

        store.set_job_item_runtime(
            item["id"],
            worker_pid=None,
            retry_count=next_retry_count,
        )
        store.update_job_item_status(
            item["id"],
            next_status,
            last_error=last_error,
        )
        store.record_job_log(
            job_id=item["job_id"],
            job_item_id=item["id"],
            level="warning",
            message=last_error,
        )
        store.refresh_job_status(item["job_id"])
        recovered += 1

    return recovered


def build_worker_command(
    item_id: str,
    db_path: Path | str,
    *,
    python_executable: str | None = None,
) -> list[str]:
    """Build the detached worker command for one job item."""
    return [
        python_executable or sys.executable,
        "-m",
        "app.job_worker_entry",
        "--db-path",
        str(db_path),
        "--item-id",
        item_id,
    ]


def spawn_worker_subprocess(
    item_id: str,
    db_path: Path | str,
    *,
    popen: Callable[..., object] = subprocess.Popen,
    python_executable: str | None = None,
) -> int:
    """Launch one detached worker subprocess and return its PID."""
    cmd = build_worker_command(
        item_id,
        db_path,
        python_executable=python_executable,
    )
    process = popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    return int(process.pid)


def run_scheduler_iteration(
    store: JobStore,
    *,
    spawn_worker: Callable[[dict], int],
    global_limit: int,
    default_per_job_limit: int,
) -> list[str]:
    """
    Run one scheduler dispatch pass.

    This function only performs selection, claim, spawn, and state updates.
    It does not block on worker completion.
    """
    runnable_items = store.list_runnable_items()
    if not runnable_items:
        return []

    active_counts = store.get_active_counts()
    job_parallelism = {
        item["job_id"]: int(item.get("job_parallelism") or default_per_job_limit)
        for item in runnable_items
    }
    batch = select_dispatch_batch(
        runnable_items=runnable_items,
        active_per_job=active_counts["per_job"],
        global_active_count=active_counts["global"],
        global_limit=global_limit,
        default_per_job_limit=default_per_job_limit,
        job_parallelism=job_parallelism,
    )

    dispatched: list[str] = []
    for item in batch:
        item_id = item["id"]
        job_id = item["job_id"]

        if not store.claim_job_item(item_id, worker_pid=None):
            continue

        try:
            worker_pid = spawn_worker(item)
        except Exception as exc:
            store.set_job_item_runtime(item_id, worker_pid=None)
            store.update_job_item_status(
                item_id,
                JobItemStatus.QUEUED.value,
                last_error=f"Worker launch failed: {exc}",
            )
            store.record_job_log(
                job_id=job_id,
                job_item_id=item_id,
                level="error",
                message=f"Worker launch failed: {exc}",
            )
            store.refresh_job_status(job_id)
            continue

        store.set_job_item_runtime(item_id, worker_pid=worker_pid)
        store.record_job_log(
            job_id=job_id,
            job_item_id=item_id,
            level="info",
            message=f"Worker dispatched (pid {worker_pid})",
        )
        store.refresh_job_status(job_id)
        dispatched.append(item_id)

    return dispatched


def run_scheduler_loop(
    store: JobStore,
    *,
    lock: SchedulerLock,
    sleep_fn: Callable[[float], None] = time.sleep,
    should_stop: Callable[[], bool] | None = None,
    recover_fn: Callable[[JobStore], int] | None = None,
    iteration_fn: Callable[[JobStore], list[str]] | None = None,
    poll_interval_seconds: float = 2.0,
    global_limit: int = 6,
    default_per_job_limit: int = 4,
) -> None:
    """Run the long-lived scheduler loop under a singleton lock."""
    if not lock.acquire():
        return

    should_stop = should_stop or (lambda: False)
    recover = recover_fn or (
        lambda current_store: recover_orphaned_running_items(
            current_store,
            pid_exists=lambda pid: os.path.exists(f"/proc/{pid}")
            or _pid_exists_portable(pid),
        )
    )
    iterate = iteration_fn or (
        lambda current_store: run_scheduler_iteration(
            current_store,
            spawn_worker=lambda item: spawn_worker_subprocess(
                item["id"],
                current_store.db_path,
            ),
            global_limit=global_limit,
            default_per_job_limit=default_per_job_limit,
        )
    )

    try:
        while not should_stop():
            try:
                recover(store)
            except sqlite3.OperationalError as exc:
                if not is_sqlite_lock_error(exc):
                    raise
                if should_stop():
                    break
                sleep_fn(poll_interval_seconds)
                continue
            try:
                iterate(store)
            except sqlite3.OperationalError as exc:
                if not is_sqlite_lock_error(exc):
                    raise
                if should_stop():
                    break
                sleep_fn(poll_interval_seconds)
                continue
            if should_stop():
                break
            sleep_fn(poll_interval_seconds)
    finally:
        lock.release()


def ensure_scheduler_thread_started(
    store: JobStore,
    *,
    thread_factory: Callable[..., threading.Thread] = threading.Thread,
    lock_path: Path | None = None,
    poll_interval_seconds: float = 2.0,
    global_limit: int = 6,
    default_per_job_limit: int = 4,
) -> threading.Thread:
    """Start one in-process scheduler thread per jobs database path."""
    registry_key = str(Path(store.db_path).resolve())
    existing = _scheduler_threads.get(registry_key)
    existing_is_alive = (
        getattr(existing, "is_alive", lambda: True) if existing is not None else None
    )
    if existing is not None and existing_is_alive():
        return existing
    if existing is not None and not existing_is_alive():
        _scheduler_threads.pop(registry_key, None)

    effective_lock_path = lock_path or Path(store.db_path).with_name("scheduler.lock")
    thread = thread_factory(
        target=lambda: run_scheduler_loop(
            store,
            lock=SchedulerLock(effective_lock_path),
            poll_interval_seconds=poll_interval_seconds,
            global_limit=global_limit,
            default_per_job_limit=default_per_job_limit,
        ),
        name=f"hometube-scheduler-{Path(store.db_path).name}",
        daemon=True,
    )
    _scheduler_threads[registry_key] = thread
    thread.start()
    return thread


def _pid_exists_portable(pid: int) -> bool:
    """Portable live-PID check for non-/proc platforms."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
