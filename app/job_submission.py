"""
Helpers to convert UI download intent into persistent background jobs.
"""

from pathlib import Path
from urllib.parse import urlparse

from app.job_store import JobStore
from app.workspace import ensure_video_workspace, parse_url


def get_jobs_db_path(tmp_download_folder: Path) -> Path:
    """Return the canonical SQLite path for background jobs."""
    return tmp_download_folder / "jobs" / "jobs.db"


def derive_site_name(url: str) -> str:
    """Derive a stable site name for display and filtering."""
    hostname = urlparse(url).hostname or "unknown"
    return hostname.lower()


def enqueue_video_job(
    store: JobStore,
    *,
    url: str,
    title: str,
    site: str,
    destination_dir: Path,
    tmp_download_folder: Path,
    base_output: str,
    config: dict,
) -> str:
    """Create a single-video background job."""
    parsed = parse_url(url)
    workspace = ensure_video_workspace(tmp_download_folder, parsed.platform, parsed.id)

    job_id = store.create_job(
        kind="video",
        url=url,
        title=title,
        site=site,
        destination_dir=str(destination_dir),
        config={**config, "base_output": base_output},
        items=[
            {
                "item_index": 1,
                "video_id": parsed.id,
                "video_url": url,
                "title": title,
                "workspace_path": str(workspace),
                "resolved_output_name": None,
            }
        ],
        max_parallelism=1,
    )
    store.record_job_log(job_id=job_id, level="info", message="Job queued")
    return job_id


def enqueue_playlist_job(
    store: JobStore,
    *,
    url: str,
    playlist_id: str,
    playlist_title: str,
    site: str,
    destination_dir: Path,
    tmp_download_folder: Path,
    playlist_entries: list[dict],
    config: dict,
    max_parallelism: int = 4,
) -> str:
    """Create a playlist background job with one job item per entry."""
    items = []
    for idx, entry in enumerate(playlist_entries, 1):
        video_id = entry.get("id", "")
        video_url = entry.get("url") or (
            f"https://www.youtube.com/watch?v={video_id}" if video_id else url
        )
        workspace = ensure_video_workspace(tmp_download_folder, "youtube", video_id)
        items.append(
            {
                "item_index": entry.get("playlist_index", idx),
                "video_id": video_id,
                "video_url": video_url,
                "title": entry.get("title", f"Video {idx}"),
                "workspace_path": str(workspace),
                "resolved_output_name": None,
            }
        )

    job_id = store.create_job(
        kind="playlist",
        url=url,
        title=playlist_title,
        site=site,
        destination_dir=str(destination_dir),
        config={**config, "playlist_id": playlist_id},
        items=items,
        max_parallelism=max_parallelism,
    )
    store.record_job_log(job_id=job_id, level="info", message="Playlist job queued")
    return job_id
