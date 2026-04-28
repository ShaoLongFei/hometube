"""
Pure video file discovery and finalization helpers.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from app import tmp_files
from app.file_system_utils import sanitize_filename


def _noop_log(message: str) -> None:
    """Default no-op logger."""


def find_final_video_file(
    video_workspace: Path,
    base_output: str,
    *,
    log_fn: Callable[[str], None] | None = None,
) -> Path | None:
    """Find the best final video candidate in a workspace."""
    log = log_fn or _noop_log
    final_tmp = None

    base_output_sanitized = sanitize_filename(base_output)
    for ext in [".mkv", ".mp4", ".webm"]:
        potential_file = video_workspace / f"{base_output_sanitized}{ext}"
        if potential_file.exists():
            final_tmp = potential_file
            log(f"✅ Found downloaded file: {potential_file.name}")
            break

    if not final_tmp:
        for ext in [".mkv", ".mp4", ".webm"]:
            final_path = tmp_files.get_final_path(video_workspace, ext.lstrip("."))
            if final_path.exists():
                final_tmp = final_path
                log(f"✅ Found final file: {final_path.name}")
                break

    if not final_tmp:
        existing_video_tracks = tmp_files.find_video_tracks(video_workspace)
        if existing_video_tracks:
            final_tmp = existing_video_tracks[0]
            log(f"✅ Found video file: {final_tmp.name}")

    return final_tmp


def organize_downloaded_video_file(
    video_workspace: Path,
    downloaded_file: Path,
    *,
    base_output: str,
    downloaded_format_id: str,
    subs_selected: list[str] | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> Path:
    """Rename the downloaded file to a generic cache key and copy final.{ext}."""
    log = log_fn or _noop_log
    format_id = downloaded_format_id or "unknown"
    log(f"  🔍 Format ID: {format_id}")

    generic_name = tmp_files.get_video_track_path(
        video_workspace, format_id, downloaded_file.suffix.lstrip(".")
    )
    log(f"  🔍 Target generic name: {generic_name.name}")

    if downloaded_file != generic_name:
        generic_name.parent.mkdir(parents=True, exist_ok=True)
        downloaded_file.replace(generic_name)
        log(f"  ✅ Video renamed: {downloaded_file.name} → {generic_name.name}")
        final_tmp = generic_name
    else:
        final_tmp = downloaded_file

    for lang in subs_selected or []:
        for ext in [".srt", ".vtt"]:
            original_sub = video_workspace / f"{base_output}.{lang}{ext}"
            if not original_sub.exists():
                continue
            generic_sub = tmp_files.get_subtitle_path(
                video_workspace, lang, is_cut=False
            )
            generic_sub.parent.mkdir(parents=True, exist_ok=True)
            original_sub.replace(generic_sub)
            log(f"  ✅ Subtitle renamed: {original_sub.name} → {generic_sub.name}")

    final_path = tmp_files.get_final_path(video_workspace, final_tmp.suffix.lstrip("."))
    if final_tmp == final_path:
        log(f"✓ File already has final name: {final_tmp.name}")
        return final_tmp

    shutil.copy2(str(final_tmp), str(final_path))
    log(f"📦 Copied: {final_tmp.name} → {final_path.name}")
    log(f"💾 Kept original {final_tmp.name} for cache reuse")
    return final_path
