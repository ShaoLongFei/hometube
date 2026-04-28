"""
Backend-friendly post-download video processing helpers.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from app import tmp_files
from app.cut_utils import build_cut_command, find_nearest_keyframes, get_keyframes
from app.download_runtime_state import adapt_runtime_state
from app.medias_utils import customize_video_metadata
from app.sponsors_utils import calculate_sponsor_overlap, get_sponsorblock_config
from app.subtitles_utils import (
    check_required_subtitles_embedded,
    embed_subtitles_manually,
    find_subtitle_files_optimized,
    process_subtitles_for_cutting,
)
from app.video_download_backend import SingleVideoDownloadRequest


def _noop_log(_message: str) -> None:
    """Default no-op logger."""


def _noop_progress(_message: str) -> None:
    """Default no-op status updater."""


def _resolve_cut_window(
    request: SingleVideoDownloadRequest,
    source_file: Path,
    *,
    runtime_state,
    cookies_resolver: Callable[[str, object], list[str]] | None = None,
    sponsor_segments_resolver: Callable[[str, list[str], list[str]], list[dict]] | None = None,
    get_keyframes_fn: Callable[[Path], list[float]] = get_keyframes,
    find_nearest_keyframes_fn: Callable[[list[float], float, float], tuple[float, float]] = find_nearest_keyframes,
    log_fn: Callable[[str], None] = _noop_log,
) -> tuple[float, float]:
    """Resolve final cutting start/duration for one request."""
    if request.start_sec is None or request.end_sec is None:
        raise RuntimeError("Cutting requested but start/end time is missing")

    start_sec = float(request.start_sec)
    end_sec = float(request.end_sec)
    remove_categories, _mark_categories = get_sponsorblock_config(request.sb_choice)

    if remove_categories and cookies_resolver and sponsor_segments_resolver:
        cookies_args = cookies_resolver(request.video_url, runtime_state)
        sponsor_segments = sponsor_segments_resolver(
            request.video_url,
            cookies_args,
            remove_categories,
        )
        if sponsor_segments:
            _removed, adjusted_end = calculate_sponsor_overlap(
                int(start_sec),
                int(end_sec),
                sponsor_segments,
            )
            end_sec = float(adjusted_end)

    if request.cutting_mode == "keyframes":
        keyframes = get_keyframes_fn(source_file)
        if keyframes:
            actual_start, actual_end = find_nearest_keyframes_fn(
                keyframes,
                start_sec,
                end_sec,
            )
        else:
            actual_start, actual_end = start_sec, end_sec
            log_fn("Keyframe extraction failed, falling back to exact timestamps")
    else:
        actual_start, actual_end = start_sec, end_sec

    duration = max(actual_end - actual_start, 0.0)
    return actual_start, duration


def postprocess_video_file(
    request: SingleVideoDownloadRequest,
    runtime_state,
    downloaded_file: Path,
    *,
    metadata_title: str | None = None,
    metadata_context: dict | None = None,
    log_fn: Callable[[str], None] = _noop_log,
    progress_fn: Callable[[str], None] = _noop_progress,
    run_command_fn: Callable[..., int] | None = None,
    cookies_resolver: Callable[[str, object], list[str]] | None = None,
    sponsor_segments_resolver: Callable[[str, list[str], list[str]], list[dict]] | None = None,
    process_subtitles_fn: Callable[[str, Path, list[str], float, float], list[tuple[str, Path]]] = process_subtitles_for_cutting,
    build_cut_command_fn: Callable[[Path, float, float, list[tuple[str, Path]], Path, str], list[str]] = build_cut_command,
    get_keyframes_fn: Callable[[Path], list[float]] = get_keyframes,
    find_nearest_keyframes_fn: Callable[[list[float], float, float], tuple[float, float]] = find_nearest_keyframes,
    check_required_subtitles_embedded_fn: Callable[[Path, list[str]], bool] = check_required_subtitles_embedded,
    find_subtitle_files_fn: Callable[[str, Path, list[str], bool], list[Path]] = find_subtitle_files_optimized,
    embed_subtitles_fn: Callable[[Path, list[Path]], bool] = embed_subtitles_manually,
    customize_metadata_fn: Callable[..., bool] = customize_video_metadata,
) -> Path:
    """Apply cut/subtitle/metadata post-processing to one downloaded file."""
    state = adapt_runtime_state(runtime_state)
    final_source = downloaded_file

    if not request.do_cut and downloaded_file.name != f"final{downloaded_file.suffix}":
        final_copy_path = tmp_files.get_final_path(
            request.video_workspace,
            downloaded_file.suffix.lstrip("."),
        )
        if final_copy_path != downloaded_file:
            shutil.copy2(str(downloaded_file), str(final_copy_path))
            final_source = final_copy_path

    if request.do_cut:
        progress_fn("Cutting video")
        actual_start, duration = _resolve_cut_window(
            request,
            final_source,
            runtime_state=state,
            cookies_resolver=cookies_resolver,
            sponsor_segments_resolver=sponsor_segments_resolver,
            get_keyframes_fn=get_keyframes_fn,
            find_nearest_keyframes_fn=find_nearest_keyframes_fn,
            log_fn=log_fn,
        )

        cut_ext = (
            ".mp4"
            if downloaded_file.suffix == ".mp4"
            else ".mkv"
            if downloaded_file.suffix != ".mkv"
            else ".mkv"
        )
        cut_output = tmp_files.get_final_path(
            request.video_workspace,
            cut_ext.lstrip("."),
        )
        processed_subtitles = []
        if request.subs_selected:
            processed_subtitles = process_subtitles_fn(
                request.base_output,
                request.video_workspace,
                request.subs_selected,
                actual_start,
                duration,
            )

        cmd = build_cut_command_fn(
            final_source,
            actual_start,
            duration,
            processed_subtitles,
            cut_output,
            cut_ext,
        )
        if run_command_fn is None:
            raise RuntimeError("run_command_fn is required for cut post-processing")
        result = run_command_fn(cmd, runtime_state=state)
        if result != 0 or not cut_output.exists():
            raise RuntimeError("ffmpeg cut failed")
        final_source = cut_output

    if metadata_title:
        progress_fn("Applying metadata")
        metadata_context = metadata_context or {}
        customize_metadata_fn(
            final_source,
            metadata_title,
            original_title=metadata_context.get("original_title"),
            video_id=request.video_id,
            source=metadata_context.get("source"),
            playlist_id=metadata_context.get("playlist_id"),
            webpage_url=metadata_context.get("webpage_url", request.video_url),
            duration=metadata_context.get("duration"),
            uploader=metadata_context.get("uploader"),
        )

    if request.subs_selected:
        progress_fn("Verifying subtitles")
        subtitles_ok = check_required_subtitles_embedded_fn(
            final_source,
            request.subs_selected,
        )
        if not subtitles_ok:
            subtitle_files = find_subtitle_files_fn(
                request.base_output,
                request.video_workspace,
                request.subs_selected,
                request.do_cut,
            )
            if subtitle_files:
                progress_fn("Embedding subtitles")
                embed_subtitles_fn(final_source, subtitle_files)

    return final_source
