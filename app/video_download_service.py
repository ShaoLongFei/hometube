"""
Backend-friendly profile download execution service.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Callable

from app.core import build_base_ytdlp_command
from app.download_execution_plan import resolve_profile_download_plan
from app.download_runtime_state import adapt_runtime_state, reset_runtime_keys
from app.logs_utils import is_authentication_error
from app.sponsors_utils import build_sponsorblock_params
from app.status_utils import add_selected_format, mark_format_error


def _noop(*_args, **_kwargs):
    """Default no-op callback."""


def _identity_translate(key: str, fallback: str = "") -> str:
    """Fallback translation resolver."""
    return fallback or key


def _call_try_profile_with_clients(
    try_profile_with_clients_fn: Callable[..., bool],
    args: tuple,
    youtube_clients: list[dict],
) -> bool:
    """Call a pluggable profile runner with or without youtube_clients support."""
    params = inspect.signature(try_profile_with_clients_fn).parameters
    if "youtube_clients" in params:
        return try_profile_with_clients_fn(*args, youtube_clients=youtube_clients)
    return try_profile_with_clients_fn(*args)


def default_build_profile_command(
    profile: dict,
    base_output: str,
    tmp_video_dir: Path,
    embed_chapters: bool,
    embed_subs: bool,
    ytdlp_custom_args: str,
    subs_selected: list[str],
    do_cut: bool,
    sb_choice: str,
) -> list[str]:
    """Build a yt-dlp command for one selected profile."""
    format_string = profile.get("format_id", "")
    quality_strategy = {
        "format": format_string,
        "format_sort": "res,fps,+size,br",
        "extra_args": [],
    }
    profile_container = profile.get("container", "mkv").lower()
    profile_force_mp4 = profile_container == "mp4"
    cmd_base = build_base_ytdlp_command(
        base_output,
        tmp_video_dir,
        format_string,
        embed_chapters,
        embed_subs,
        profile_force_mp4,
        ytdlp_custom_args,
        quality_strategy,
    )

    if subs_selected:
        langs_csv = ",".join(subs_selected)
        cmd_base.extend(
            [
                "--write-subs",
                "--write-auto-subs",
                "--sub-langs",
                langs_csv,
                "--convert-subs",
                "srt",
            ]
        )
        embed_flag = (
            "--no-embed-subs"
            if do_cut
            else ("--embed-subs" if embed_subs else "--no-embed-subs")
        )
        cmd_base.append(embed_flag)

    sb_params = build_sponsorblock_params(sb_choice)
    if sb_params:
        cmd_base.extend(sb_params)

    return cmd_base


def default_try_profile_with_clients(
    cmd_base: list[str],
    url: str,
    cookies_part: list[str],
    cookies_available: bool,
    status_placeholder,
    progress_placeholder,
    info_placeholder,
    preferred_client: str | None,
    runtime_state,
    run_cmd_fn: Callable[..., int],
    log_fn: Callable[[str], None],
    youtube_clients: list[dict],
) -> bool:
    """Try one profile across ordered YouTube clients."""
    clients_to_try = []
    if preferred_client:
        preferred_config = next(
            (client for client in youtube_clients if client["name"] == preferred_client),
            None,
        )
        if preferred_config:
            clients_to_try.append(preferred_config)
            clients_to_try.extend(
                [client for client in youtube_clients if client["name"] != preferred_client]
            )
        else:
            clients_to_try = youtube_clients
    else:
        clients_to_try = youtube_clients

    for client_idx, client in enumerate(clients_to_try, 1):
        client_name = client["name"]
        client_args = client["args"]
        priority_indicator = "🎯 " if client_idx == 1 and preferred_client else ""

        if cookies_available:
            if status_placeholder:
                status_placeholder.info(
                    f"{priority_indicator}🍪 {client_name.title()} + cookies"
                )
            cmd = cmd_base + client_args + cookies_part + [url]
            ret = run_cmd_fn(
                cmd,
                progress_placeholder,
                status_placeholder,
                info_placeholder,
                runtime_state=runtime_state,
            )
            if ret == 0:
                log_fn(f"✅ SUCCESS: {client_name.title()} client + cookies")
                return True

        if status_placeholder:
            status_placeholder.info(f"{priority_indicator}🚀 {client_name.title()} client")

        cmd = cmd_base + client_args + [url]
        ret = run_cmd_fn(
            cmd,
            progress_placeholder,
            status_placeholder,
            info_placeholder,
            runtime_state=runtime_state,
        )
        if ret == 0:
            log_fn(f"✅ SUCCESS: {client_name.title()} client")
            return True

    return False


def smart_download_with_profiles(
    *,
    base_output: str,
    tmp_video_dir: Path,
    embed_chapters: bool,
    embed_subs: bool,
    force_mp4: bool,
    ytdlp_custom_args: str,
    url: str,
    do_cut: bool,
    subs_selected: list[str] | None,
    sb_choice: str,
    runtime_state,
    cookies_resolver: Callable[[str, object], list[str]],
    translations: dict[str, str],
    settings_quality_downgrade: bool,
    youtube_clients: list[dict],
    progress_placeholder=None,
    status_placeholder=None,
    info_placeholder=None,
    chosen_profiles: list[dict] | None = None,
    quality_strategy_override: str | None = None,
    refuse_quality_downgrade_best: bool | None = None,
    build_profile_command_fn: Callable[..., list[str]] = default_build_profile_command,
    try_profile_with_clients_fn: Callable[..., bool] = default_try_profile_with_clients,
    add_selected_format_fn: Callable[..., object] = add_selected_format,
    mark_format_error_fn: Callable[..., object] = mark_format_error,
    run_cmd_fn: Callable[..., int] = _noop,
    log_fn: Callable[[str], None] = _noop,
    title_log_fn: Callable[[str], None] = _noop,
    load_url_info_from_file_fn: Callable[[Path], dict | None] | None = None,
) -> tuple[int, str]:
    """Execute profile-based download flow against injected runtime state and callbacks."""
    state = adapt_runtime_state(runtime_state)
    translate = lambda key, fallback="": translations.get(key, fallback or key)

    log_fn("")
    title_log_fn("🎯 Starting profile-based download...")

    cookies_part = cookies_resolver(url, state)
    cookies_available = len(cookies_part) > 0

    reset_runtime_keys(state, ["auth_hint_shown_this_download", "po_token_warning_shown"])
    title_log_fn("🎯 Using quality strategy profiles...")

    try:
        plan = resolve_profile_download_plan(
            requested_profiles=chosen_profiles,
            requested_quality_strategy=quality_strategy_override,
            fallback_profiles=state.get("chosen_format_profiles", []),
            fallback_quality_strategy=state.get("download_quality_strategy", "auto_best"),
            refuse_quality_downgrade_best=(
                refuse_quality_downgrade_best
                if refuse_quality_downgrade_best is not None
                else state.get("refuse_quality_downgrade_best", not settings_quality_downgrade)
            ),
            quality_downgrade_enabled=settings_quality_downgrade,
        )
    except ValueError:
        error_msg = translate("error_no_profiles_for_download", "No profiles available")
        log_fn(f"❌ {error_msg}")
        return 1, error_msg

    profiles_to_try = plan.profiles_to_try
    quality_strategy = plan.quality_strategy
    log_fn(f"✅ Using {len(profiles_to_try)} profiles from {quality_strategy} strategy")
    log_fn("")

    preferred_client = None
    url_info_path = tmp_video_dir / "url_info.json"
    if load_url_info_from_file_fn and url_info_path.exists():
        try:
            url_info = load_url_info_from_file_fn(url_info_path)
            if url_info:
                preferred_client = url_info.get("_hometube_successful_client")
                if preferred_client:
                    log_fn(
                        f"🎯 Will prioritize {preferred_client} client (used for URL analysis)"
                    )
        except Exception as exc:
            log_fn(f"⚠️ Could not read preferred client from url_info.json: {exc}")

    for profile_idx, profile in enumerate(profiles_to_try, 1):
        log_fn("")
        log_fn(f"🏆 Profile {profile_idx}/{len(profiles_to_try)}: {profile['label']}")
        state["current_attempting_profile"] = profile["label"]

        format_id = profile.get("format_id", "unknown")
        add_selected_format_fn(
            tmp_url_workspace=tmp_video_dir,
            video_format=format_id,
            subtitles=[f"subtitles.{lang}.srt" for lang in subs_selected or []],
            filesize_approx=profile.get("filesize_approx", 0),
        )

        cmd_base = build_profile_command_fn(
            profile,
            base_output,
            tmp_video_dir,
            embed_chapters,
            embed_subs,
            ytdlp_custom_args,
            subs_selected or [],
            do_cut,
            sb_choice,
        )

        success = _call_try_profile_with_clients(
            try_profile_with_clients_fn,
            (
                cmd_base,
                url,
                cookies_part,
                cookies_available,
                status_placeholder,
                progress_placeholder,
                info_placeholder,
                preferred_client,
                state,
                run_cmd_fn,
                log_fn,
            ),
            youtube_clients,
        )
        if success:
            state["downloaded_format_id"] = format_id
            title_log_fn("✅ Download successful!")
            log_fn(f"📦 Profile used: {profile['label']}")
            log_fn(f"🎯 Format ID: {format_id}")
            return 0, ""

        mark_format_error_fn(
            tmp_url_workspace=tmp_video_dir,
            video_format=format_id,
            error_message="Download failed - all clients exhausted",
        )

        last_error = state.get("last_error", "").lower()
        if plan.download_mode == "forced" or plan.refuse_quality_downgrade:
            break
        if profile_idx >= len(profiles_to_try):
            break
        if is_authentication_error(last_error):
            log_fn("🔐 Authentication/permission issue")

    profiles_count = len(profiles_to_try)
    log_fn("")
    log_fn("❌ All profiles failed")
    return 1, f"All {profiles_count} profiles failed after full client fallback"
