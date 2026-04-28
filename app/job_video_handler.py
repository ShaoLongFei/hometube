"""
Real single-video job handler for detached worker execution.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path

from app.config import YOUTUBE_CLIENT_FALLBACKS, get_settings
from app.download_auth import (
    resolve_cookies_params,
    resolve_cookies_params_from_config,
)
from app.file_system_utils import move_final_to_destination, sanitize_filename
from app.job_command_runner import run_monitored_command
from app.job_download_config import build_runtime_state_from_job, build_single_video_request_from_job
from app.job_progress import ProgressUpdate
from app.job_store import JobStore
from app.logs_utils import log_title, safe_push_log
from app.medias_utils import get_source_from_url
from app.playlist_utils import update_video_status_in_playlist
from app.sponsors_utils import get_sponsorblock_segments
from app.status_utils import create_initial_status, update_format_status
from app.text_utils import render_title
from app.url_utils import build_url_info, load_url_info_from_file
from app.video_cache_backend import check_existing_video_file
from app.video_download_backend import DownloadAttemptResult, execute_video_download
from app.video_download_service import smart_download_with_profiles
from app.video_file_ops import find_final_video_file, organize_downloaded_video_file
from app.video_postprocess_backend import VideoPostprocessResult, postprocess_video_file
from app.video_workspace_backend import (
    compute_workspace_profiles,
    prepare_video_workspace,
)


class _JobProgressCallbacks:
    """Persist detached worker logs and progress into the job store."""

    def __init__(self, store: JobStore | None, job: dict | None, item: dict | None):
        self.store = store
        self.job = job
        self.item = item

    def log(self, message: str) -> None:
        safe_push_log(message)
        if self.store and self.job and self.item and message.strip():
            self.store.record_job_log(
                job_id=self.job["id"],
                job_item_id=self.item["id"],
                level="info",
                message=message,
            )

    def update(self, update: ProgressUpdate) -> None:
        if not (self.store and self.item):
            return
        self.store.update_job_item_progress(
            self.item["id"],
            progress_percent=update.progress_percent,
            downloaded_bytes=update.downloaded_bytes,
            total_bytes=update.total_bytes,
            speed_bps=update.speed_bps,
            eta_seconds=update.eta_seconds,
            status_message=update.status_message,
        )

    def stage(self, message: str) -> None:
        """Persist a coarse-grained stage update."""
        self.update(ProgressUpdate(progress_percent=None, status_message=message))
        self.log(message)


@dataclass(frozen=True)
class DetachedVideoJobResult:
    """Detached worker result for one executable video item."""

    return_code: int
    final_file: Path | None
    error_message: str | None
    postprocess_result: VideoPostprocessResult | None = None


def _coerce_download_result(result) -> DetachedVideoJobResult:
    """Normalize legacy tuple returns into a structured detached result."""
    if isinstance(result, DetachedVideoJobResult):
        return result
    if isinstance(result, tuple) and len(result) == 3:
        return DetachedVideoJobResult(
            return_code=result[0],
            final_file=result[1],
            error_message=result[2],
        )
    raise TypeError(
        "download_executor must return a DetachedVideoJobResult or "
        "(return_code, final_file, error_message) tuple"
    )


def _format_audio_summary(postprocess_result: VideoPostprocessResult) -> str:
    """Create a compact audio codec summary for persistent UI display."""
    inspection = postprocess_result.inspection
    if inspection.audio_codecs and all(codec == "aac" for codec in inspection.audio_codecs):
        if len(inspection.audio_codecs) == 1:
            return "AAC-LC"
        return f"AAC-LC x{len(inspection.audio_codecs)}"
    return ", ".join(codec.upper() for codec in inspection.audio_codecs) or "unknown"


def _persist_delivery_metadata(
    store: JobStore | None,
    item_id: str,
    postprocess_result: VideoPostprocessResult | None,
) -> None:
    """Persist delivery metadata when a structured postprocess result is available."""
    if store is None or postprocess_result is None:
        return

    store.update_job_item_delivery(
        item_id,
        normalization_required=postprocess_result.normalization_required,
        normalization_succeeded=postprocess_result.normalization_succeeded,
        final_container=postprocess_result.inspection.container,
        final_video_codec=postprocess_result.inspection.video_codec,
        final_audio_summary=_format_audio_summary(postprocess_result),
        final_codec_summary=postprocess_result.codec_summary,
        delivery_warning=postprocess_result.warning_message,
    )


def _call_download_executor(
    download_executor,
    request,
    runtime_state,
    *,
    store: JobStore | None,
    job: dict,
    item: dict,
):
    """Call pluggable download executors with optional detached-job context."""
    params = inspect.signature(download_executor).parameters
    kwargs = {}
    if "store" in params:
        kwargs["store"] = store
    if "job" in params:
        kwargs["job"] = job
    if "item" in params:
        kwargs["item"] = item
    return download_executor(request, runtime_state, **kwargs)


def execute_single_video_download_for_job(
    request,
    runtime_state,
    *,
    store: JobStore | None = None,
    job: dict | None = None,
    item: dict | None = None,
) -> DetachedVideoJobResult:
    """Execute the actual detached single-video download flow."""
    settings = get_settings()
    callbacks = _JobProgressCallbacks(store, job, item)

    def _cookies_resolver(url: str, current_state) -> list[str]:
        current_method = current_state.get("cookies_method", "none")
        if current_method == "none":
            return resolve_cookies_params_from_config(
                url=url,
                cookies_file_path=settings.YOUTUBE_COOKIES_FILE_PATH,
                cookies_from_browser=settings.COOKIES_FROM_BROWSER,
            )
        return resolve_cookies_params(
            url=url,
            runtime_state=current_state,
            cookies_file_path=settings.YOUTUBE_COOKIES_FILE_PATH,
        )

    def _fetch_url_info(url: str, json_output_path: Path) -> dict | None:
        return build_url_info(
            clean_url=url,
            json_output_path=json_output_path,
            cookies_params=resolve_cookies_params_from_config(
                url=url,
                cookies_file_path=settings.YOUTUBE_COOKIES_FILE_PATH,
                cookies_from_browser=settings.COOKIES_FROM_BROWSER,
            ),
            youtube_cookies_file_path=settings.YOUTUBE_COOKIES_FILE_PATH,
            cookies_from_browser=settings.COOKIES_FROM_BROWSER,
            youtube_clients=YOUTUBE_CLIENT_FALLBACKS,
        )

    def _initialize_workspace(req):
        return_result = prepare_video_workspace(
            video_url=req.video_url,
            video_id=req.video_id,
            video_title=req.video_title,
            video_workspace=req.video_workspace,
            load_existing_url_info=load_url_info_from_file,
            fetch_url_info=_fetch_url_info,
            create_initial_status_fn=create_initial_status,
            compute_profiles_fn=lambda url_info, json_path: compute_workspace_profiles(
                url_info,
                json_path,
                language_primary=settings.LANGUAGE_PRIMARY or "en",
                languages_secondaries=(
                    ",".join(settings.LANGUAGES_SECONDARIES)
                    if settings.LANGUAGES_SECONDARIES
                    else ""
                ),
                vo_first=settings.VO_FIRST,
                log_fn=safe_push_log,
            ),
            log_fn=safe_push_log,
        )
        runtime_state["chosen_format_profiles"] = return_result.profiles.chosen_format_profiles
        if return_result.profiles.download_quality_strategy:
            runtime_state["download_quality_strategy"] = (
                return_result.profiles.download_quality_strategy
            )
        return return_result.url_info, return_result.success

    def _perform_download(req) -> DownloadAttemptResult:
        callbacks.log(f"📥 Downloading {req.video_title} in detached worker...")
        ret_code, error_message = smart_download_with_profiles(
            base_output=req.base_output,
            tmp_video_dir=req.video_workspace,
            embed_chapters=req.embed_chapters,
            embed_subs=req.embed_subs,
            force_mp4=req.force_mp4,
            ytdlp_custom_args=req.ytdlp_custom_args,
            url=req.video_url,
            do_cut=req.do_cut,
            subs_selected=req.subs_selected,
            sb_choice=req.sb_choice,
            runtime_state=runtime_state,
            cookies_resolver=_cookies_resolver,
            translations={"error_no_profiles_for_download": "No profiles available for download"},
            settings_quality_downgrade=settings.QUALITY_DOWNGRADE,
            youtube_clients=YOUTUBE_CLIENT_FALLBACKS,
            log_fn=callbacks.log,
            title_log_fn=lambda title: (
                callbacks.log(title),
                callbacks.log("─" * len(title)),
            )[1],
            load_url_info_from_file_fn=load_url_info_from_file,
            run_cmd_fn=lambda cmd, progress_placeholder, status_placeholder, info_placeholder, runtime_state=None: run_monitored_command(
                cmd,
                progress_placeholder,
                status_placeholder,
                info_placeholder,
                runtime_state=runtime_state,
                log_fn=callbacks.log,
                progress_callback=callbacks.update,
            ),
        )
        return DownloadAttemptResult(
            return_code=ret_code,
            downloaded_format_id=runtime_state.get("downloaded_format_id"),
            error_message=error_message,
        )

    result = execute_video_download(
        request,
        initialize_workspace=_initialize_workspace,
        check_existing_file=lambda workspace, requested_format_id: check_existing_video_file(
            workspace,
            requested_format_id,
            log_fn=safe_push_log,
        ),
        perform_download=_perform_download,
        locate_final_file=lambda workspace, base_output: find_final_video_file(
            workspace,
            base_output,
            log_fn=safe_push_log,
        ),
        finalize_downloaded_file=lambda workspace, downloaded_file, base_output, downloaded_format_id, subs_selected: organize_downloaded_video_file(
            workspace,
            downloaded_file,
            base_output=base_output,
            downloaded_format_id=downloaded_format_id,
            subs_selected=subs_selected,
            log_fn=safe_push_log,
        ),
        update_cached_format_status=update_format_status,
    )
    if result.return_code != 0 or result.final_file is None:
        return DetachedVideoJobResult(
            return_code=result.return_code,
            final_file=result.final_file,
            error_message=result.error_message,
        )

    metadata_context = {}
    url_info_path = request.video_workspace / "url_info.json"
    if url_info_path.exists():
        try:
            url_info = load_url_info_from_file(url_info_path) or {}
        except Exception:
            url_info = {}
        metadata_context = {
            "original_title": url_info.get("title"),
            "uploader": url_info.get("uploader", url_info.get("channel")),
            "source": get_source_from_url(request.video_url),
            "playlist_id": None if not job else job.get("config", {}).get("playlist_id"),
            "webpage_url": request.video_url,
        }

    metadata_title = request.base_output if (job or {}).get("kind") == "video" else None

    callbacks.stage("Post-processing video")
    postprocess_result = postprocess_video_file(
        request,
        runtime_state,
        result.final_file,
        metadata_title=metadata_title,
        metadata_context=metadata_context,
        log_fn=callbacks.log,
        progress_fn=callbacks.stage,
        run_command_fn=lambda cmd, runtime_state=None, command_duration_seconds=None: run_monitored_command(
            cmd,
            runtime_state=runtime_state,
            log_fn=callbacks.log,
            progress_callback=callbacks.update,
            command_duration_seconds=command_duration_seconds,
        ),
        cookies_resolver=_cookies_resolver,
        sponsor_segments_resolver=get_sponsorblock_segments,
    )
    return DetachedVideoJobResult(
        return_code=result.return_code,
        final_file=postprocess_result.final_path,
        error_message=result.error_message,
        postprocess_result=postprocess_result,
    )


def handle_video_job_item(
    job: dict,
    item: dict,
    *,
    store: JobStore | None = None,
    download_executor=execute_single_video_download_for_job,
    move_to_destination=lambda source, destination: move_final_to_destination(
        source,
        destination,
        safe_push_log,
    ),
) -> None:
    """Build request/runtime state and execute one detached video job item."""
    request = build_single_video_request_from_job(job, item)
    runtime_state = build_runtime_state_from_job(job)

    result = _call_download_executor(
        download_executor,
        request,
        runtime_state,
        store=store,
        job=job,
        item=item,
    )
    download_result = _coerce_download_result(result)
    return_code = download_result.return_code
    final_file = download_result.final_file
    error_message = download_result.error_message

    if return_code != 0:
        raise RuntimeError(error_message or "Video job item failed")
    if final_file is None:
        raise RuntimeError("Video job item produced no final file")

    destination_dir = Path(job["destination_dir"])
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / f"{sanitize_filename(request.base_output)}{final_file.suffix}"
    move_to_destination(final_file, destination_path)

    if store is not None:
        _persist_delivery_metadata(store, item["id"], download_result.postprocess_result)
        store.update_job_item_progress(
            item["id"],
            progress_percent=100.0,
            eta_seconds=0,
            status_message="Completed",
        )


def handle_playlist_job_item(
    job: dict,
    item: dict,
    *,
    store: JobStore | None = None,
    download_executor=execute_single_video_download_for_job,
    update_playlist_status=update_video_status_in_playlist,
    move_to_destination=lambda source, destination: move_final_to_destination(
        source,
        destination,
        safe_push_log,
    ),
) -> None:
    """Execute one playlist video item and place it into the playlist folder."""
    config = job.get("config", {})
    playlist_workspace = Path(config["playlist_workspace"])
    update_playlist_status(playlist_workspace, item["video_id"], "downloading")

    try:
        request = build_single_video_request_from_job(job, item)
        runtime_state = build_runtime_state_from_job(job)
        result = _call_download_executor(
            download_executor,
            request,
            runtime_state,
            store=store,
            job=job,
            item=item,
        )
        download_result = _coerce_download_result(result)
        return_code = download_result.return_code
        final_file = download_result.final_file
        error_message = download_result.error_message
        if return_code != 0:
            raise RuntimeError(error_message or "Playlist job item failed")
        if final_file is None:
            raise RuntimeError("Playlist job item produced no final file")

        resolved_title = render_title(
            config.get("playlist_title_pattern", "{idx} - {pretty(title)}.{ext}"),
            i=int(item.get("item_index") or 1),
            title=item.get("title") or request.video_title,
            video_id=item.get("video_id") or request.video_id,
            ext=final_file.suffix.lstrip("."),
            total=int(config.get("playlist_total_count") or job.get("total_items") or 1),
            channel=config.get("playlist_channel"),
        )
        destination_dir = Path(job["destination_dir"])
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = destination_dir / resolved_title
        move_to_destination(final_file, destination_path)

        update_playlist_status(
            playlist_workspace,
            item["video_id"],
            "completed",
            extra_data={
                "title_pattern": config.get("playlist_title_pattern"),
                "resolved_title": resolved_title,
                "playlist_index": int(item.get("item_index") or 1),
            },
        )
        if store is not None:
            _persist_delivery_metadata(store, item["id"], download_result.postprocess_result)
            store.update_job_item_progress(
                item["id"],
                progress_percent=100.0,
                eta_seconds=0,
                status_message="Completed",
            )
    except Exception as exc:
        update_playlist_status(
            playlist_workspace,
            item.get("video_id", ""),
            "failed",
            error=str(exc),
        )
        raise
