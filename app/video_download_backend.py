"""
Backend-friendly single-video download orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class SingleVideoDownloadRequest:
    """All inputs needed to execute one single-video download."""

    video_url: str
    video_id: str
    video_title: str
    video_workspace: Path
    base_output: str
    embed_chapters: bool
    embed_subs: bool
    force_mp4: bool
    ytdlp_custom_args: str
    do_cut: bool
    subs_selected: list[str]
    sb_choice: str
    requested_format_id: str | None = None
    start_sec: int | None = None
    end_sec: int | None = None
    cutting_mode: str = "keyframes"


@dataclass(frozen=True)
class DownloadAttemptResult:
    """Outcome from the actual download attempt step."""

    return_code: int
    downloaded_format_id: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class SingleVideoDownloadResult:
    """Final outcome from the backend single-video flow."""

    return_code: int
    final_file: Path | None
    error_message: str | None
    used_cached_file: bool


def execute_video_download(
    request: SingleVideoDownloadRequest,
    *,
    initialize_workspace: Callable[[SingleVideoDownloadRequest], tuple[dict | None, bool]],
    check_existing_file: Callable[[Path, str | None], tuple[Path | None, str | None]],
    perform_download: Callable[[SingleVideoDownloadRequest], DownloadAttemptResult],
    locate_final_file: Callable[[Path, str], Path | None],
    finalize_downloaded_file: Callable[
        [Path, Path, str, str, list[str]], Path | None
    ],
    update_cached_format_status: Callable[[Path, str, Path], object] | None = None,
) -> SingleVideoDownloadResult:
    """Execute one single-video download using injected side-effect callbacks."""
    video_url_info, success = initialize_workspace(request)
    if not success:
        error_message = (
            video_url_info.get("error", "Unknown error")
            if video_url_info
            else "Failed to fetch video info"
        )
        return SingleVideoDownloadResult(1, None, error_message, False)

    existing_file, completed_format_id = check_existing_file(
        request.video_workspace,
        request.requested_format_id,
    )
    if existing_file:
        if completed_format_id and update_cached_format_status is not None:
            update_cached_format_status(
                request.video_workspace,
                completed_format_id,
                existing_file,
            )
        return SingleVideoDownloadResult(0, existing_file, None, True)

    download_result = perform_download(request)
    if download_result.return_code != 0:
        return SingleVideoDownloadResult(
            download_result.return_code,
            None,
            download_result.error_message,
            False,
        )

    final_file = locate_final_file(request.video_workspace, request.base_output)
    if final_file and final_file.exists():
        final_file = finalize_downloaded_file(
            request.video_workspace,
            final_file,
            request.base_output,
            download_result.downloaded_format_id or "unknown",
            request.subs_selected,
        )

    return SingleVideoDownloadResult(0, final_file, None, False)
