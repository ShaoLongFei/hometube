"""
Helpers to convert persisted job config into executable download requests.
"""

from __future__ import annotations

from pathlib import Path

from app.download_runtime_state import MemoryRuntimeState
from app.video_download_backend import SingleVideoDownloadRequest


def build_single_video_request_from_job(
    job: dict,
    item: dict,
) -> SingleVideoDownloadRequest:
    """Build a backend single-video request from persisted job/item records."""
    config = job.get("config", {})
    kind = job.get("kind", "video")
    base_output = (
        item.get("resolved_output_name")
        or item.get("title")
        if kind == "playlist"
        else config.get("base_output")
    )
    return SingleVideoDownloadRequest(
        video_url=item["video_url"],
        video_id=item.get("video_id") or item["id"],
        video_title=item.get("title") or job.get("title") or item["video_url"],
        video_workspace=Path(item["workspace_path"]),
        base_output=base_output
        or item.get("title")
        or job.get("title")
        or item.get("video_id")
        or "video",
        embed_chapters=bool(config.get("embed_chapters", False)),
        embed_subs=bool(config.get("embed_subs", False)),
        force_mp4=bool(config.get("force_mp4", False)),
        ytdlp_custom_args=config.get("ytdlp_custom_args", ""),
        do_cut=bool(config.get("do_cut", False)),
        subs_selected=list(config.get("subs_selected", [])),
        sb_choice=config.get("sb_choice", "disabled"),
        requested_format_id=config.get("requested_format_id"),
        start_sec=config.get("start_sec"),
        end_sec=config.get("end_sec"),
        cutting_mode=config.get("cutting_mode", "keyframes"),
    )


def build_runtime_state_from_job(job: dict) -> MemoryRuntimeState:
    """Build detached runtime state from persisted job config."""
    config = job.get("config", {})
    chosen_profiles = config.get("chosen_profiles") or config.get(
        "chosen_format_profiles", []
    )
    return MemoryRuntimeState(
        {
            "cookies_method": config.get("cookies_method", "none"),
            "browser_select": config.get("browser_select", "chrome"),
            "browser_profile": config.get("browser_profile", ""),
            "chosen_format_profiles": list(chosen_profiles),
            "download_quality_strategy": config.get(
                "download_quality_strategy",
                "auto_best",
            ),
            "refuse_quality_downgrade_best": bool(
                config.get("refuse_quality_downgrade_best", False)
            ),
            "download_cancelled": False,
        }
    )
