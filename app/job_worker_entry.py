"""
CLI entrypoint for detached background job workers.
"""

from __future__ import annotations

import argparse
import inspect
import os

from app.job_video_handler import handle_playlist_job_item, handle_video_job_item
from app.job_store import JobStore
from app.job_worker import execute_job_item


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse worker CLI arguments."""
    parser = argparse.ArgumentParser(description="Execute one HomeTube job item")
    parser.add_argument("--db-path", required=True, help="Path to the jobs SQLite file")
    parser.add_argument("--item-id", required=True, help="Job item identifier")
    return parser.parse_args(argv)


def dispatch_job_item(
    job: dict,
    job_item: dict,
    *,
    store: JobStore | None = None,
    video_handler=handle_video_job_item,
    playlist_handler=handle_playlist_job_item,
) -> None:
    """Dispatch one claimed job item to the correct concrete handler."""
    kind = job.get("kind")
    if kind == "video":
        if "store" in inspect.signature(video_handler).parameters:
            video_handler(job, job_item, store=store)
        else:
            video_handler(job, job_item)
        return
    if kind == "playlist":
        if "store" in inspect.signature(playlist_handler).parameters:
            playlist_handler(job, job_item, store=store)
        else:
            playlist_handler(job, job_item)
        return
    raise RuntimeError(f"Unsupported job kind: {kind}")


def main(argv: list[str] | None = None) -> int:
    """Run one background worker process."""
    args = parse_args(argv)
    store = JobStore(args.db_path)
    success = execute_job_item(
        store,
        args.item_id,
        lambda job, item: dispatch_job_item(job, item, store=store),
        worker_pid=os.getpid(),
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
