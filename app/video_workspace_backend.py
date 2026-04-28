"""
Backend-friendly video workspace initialization and profile analysis helpers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.medias_utils import (
    analyze_audio_formats,
    get_available_formats,
    get_profiles_with_formats_id_to_download,
)


def _noop_log(message: str) -> None:
    """Default logger that does nothing."""


@dataclass(frozen=True)
class WorkspaceProfilesResult:
    """Profile-related data derived from a resolved video URL."""

    optimal_format_profiles: list[dict] = field(default_factory=list)
    available_formats_list: list[dict] = field(default_factory=list)
    chosen_format_profiles: list[dict] = field(default_factory=list)
    download_quality_strategy: str | None = None


@dataclass(frozen=True)
class VideoWorkspaceInitResult:
    """Full result of preparing one video workspace."""

    url_info: dict | None
    success: bool
    profiles: WorkspaceProfilesResult


def compute_workspace_profiles(
    url_info: dict,
    json_path: Path,
    *,
    language_primary: str,
    languages_secondaries: str,
    vo_first: bool,
    analyze_audio_formats_fn: Callable = analyze_audio_formats,
    get_profiles_fn: Callable = get_profiles_with_formats_id_to_download,
    get_available_formats_fn: Callable = get_available_formats,
    log_fn: Callable[[str], None] | None = None,
) -> WorkspaceProfilesResult:
    """Compute optimal download profiles for one resolved video."""
    log = log_fn or _noop_log

    if url_info.get("_type") == "playlist":
        log("ℹ️ Playlist detected - skipping profile computation (done per video)")
        return WorkspaceProfilesResult()

    try:
        log("🎯 Computing optimal format profiles...")
        log("🎵 Analyzing audio tracks...")
        vo_lang, audio_formats, multiple_langs = analyze_audio_formats_fn(
            url_info,
            language_primary=language_primary,
            languages_secondaries=languages_secondaries,
            vo_first=vo_first,
        )

        log(f"   VO language: {vo_lang or 'unknown'}")
        log(f"   Audio tracks: {len(audio_formats)}")
        log(f"   Multi-language: {'Yes' if multiple_langs else 'No'}")
        log("🎯 Selecting optimal video formats (AV1/VP9 priority)...")

        optimal_profiles = get_profiles_fn(
            str(json_path),
            multiple_langs,
            audio_formats,
        )
        available_formats = get_available_formats_fn(url_info)

        if not optimal_profiles:
            log("❌ No optimal profiles found")
            return WorkspaceProfilesResult(
                optimal_format_profiles=[],
                available_formats_list=available_formats,
                chosen_format_profiles=[],
                download_quality_strategy=None,
            )

        log(f"✅ Found {len(optimal_profiles)} optimal profile(s)")
        for idx, profile in enumerate(optimal_profiles, 1):
            log(f"📦 Profile {idx}: {profile.get('label', 'Unknown')}")
            log(f"   🆔 Format ID: {profile.get('format_id', '')}")
            log(f"   🎬 Video Codec: {profile.get('vcodec', 'unknown')}")
            log(f"   📐 Resolution: {profile.get('height', 0)}p")

        log("✅ Profile computation complete")
        return WorkspaceProfilesResult(
            optimal_format_profiles=optimal_profiles,
            available_formats_list=available_formats,
            chosen_format_profiles=optimal_profiles,
            download_quality_strategy="auto_best",
        )
    except Exception as exc:
        log(f"⚠️ Error computing profiles: {exc}")
        return WorkspaceProfilesResult()


def prepare_video_workspace(
    *,
    video_url: str,
    video_id: str,
    video_title: str,
    video_workspace: Path,
    load_existing_url_info: Callable[[Path], dict | None],
    fetch_url_info: Callable[[str, Path], dict | None],
    create_initial_status_fn: Callable[..., object],
    compute_profiles_fn: Callable[[dict, Path], WorkspaceProfilesResult],
    log_fn: Callable[[str], None] | None = None,
) -> VideoWorkspaceInitResult:
    """Load or fetch url_info, ensure status.json exists, and compute profiles."""
    log = log_fn or _noop_log
    url_info_path = video_workspace / "url_info.json"
    status_path = video_workspace / "status.json"

    video_url_info = None
    if url_info_path.exists():
        try:
            video_url_info = load_existing_url_info(url_info_path)
            if video_url_info:
                log(f"📋 Using existing url_info.json for {video_title}")
        except Exception as exc:
            log(f"⚠️ Could not load existing url_info.json: {exc}")

    if not video_url_info:
        log(f"📋 Fetching url_info.json for {video_title}...")
        video_url_info = fetch_url_info(video_url, url_info_path)

    if not video_url_info or "error" in video_url_info:
        return VideoWorkspaceInitResult(
            url_info=None,
            success=False,
            profiles=WorkspaceProfilesResult(),
        )

    if not status_path.exists():
        create_initial_status_fn(
            url=video_url,
            video_id=video_id,
            title=video_title,
            content_type="video",
            tmp_url_workspace=video_workspace,
        )
        log(f"📊 Created status.json for {video_title}")

    profiles = compute_profiles_fn(video_url_info, url_info_path)
    return VideoWorkspaceInitResult(
        url_info=video_url_info,
        success=True,
        profiles=profiles,
    )


def load_url_info_json(path: Path) -> dict | None:
    """Load a previously saved url_info.json file."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)
