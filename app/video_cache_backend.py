"""
Pure cached-video detection helpers for single-video downloads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from app import tmp_files
from app.status_utils import get_first_completed_format


def _noop_log(message: str) -> None:
    """Default no-op logger."""


def check_existing_video_file(
    video_workspace: Path,
    requested_format_id: str | None = None,
    *,
    get_first_completed_format_fn: Callable[[Path], str | None] = get_first_completed_format,
    find_video_tracks_fn: Callable[[Path], list[Path]] = tmp_files.find_video_tracks,
    extract_format_id_fn: Callable[[str], str | None] = tmp_files.extract_format_id_from_filename,
    log_fn: Callable[[str], None] | None = None,
) -> tuple[Path | None, str | None]:
    """Check whether a workspace already contains a reusable completed video file."""
    log = log_fn or _noop_log
    completed_format_id = get_first_completed_format_fn(video_workspace)

    if completed_format_id:
        if requested_format_id and requested_format_id != completed_format_id:
            log(f"🔄 User requested different format: {requested_format_id}")
            log(f"   Current cached format: {completed_format_id}")
            log("   Will re-download with new format")
            return None, None

        existing_video_tracks = find_video_tracks_fn(video_workspace)
        for track in existing_video_tracks:
            track_format_id = extract_format_id_fn(track.name)
            if track_format_id and track_format_id in completed_format_id:
                log(f"  📦 Found file: {track.name}")
                return track, completed_format_id

        log("  ⚠️ Status shows completed but file not found, will re-download")
    else:
        existing_video_tracks = find_video_tracks_fn(video_workspace)
        existing_generic_file = existing_video_tracks[0] if existing_video_tracks else None
        if existing_generic_file:
            log(f"  📦 Existing file: {existing_generic_file.name}")
            return existing_generic_file, None

    return None, completed_format_id if completed_format_id else None
