"""
Helpers for probing delivered video codec/container information.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess
from typing import Callable

from app.process_utils import run_subprocess_safe


@dataclass(frozen=True)
class CodecInspectionResult:
    """Summary of the final delivered media container and codecs."""

    container: str
    video_codec: str | None
    audio_codecs: list[str]
    audio_profiles: list[str | None]


def _normalize_container(format_name: str) -> str:
    format_lower = format_name.lower()
    if "mp4" in format_lower or "mov" in format_lower:
        return "mp4"
    if "matroska" in format_lower or "webm" in format_lower:
        return "mkv" if "matroska" in format_lower else "webm"
    return format_lower.split(",")[0] if format_lower else "unknown"


def probe_video_codecs(
    video_path: Path,
    *,
    probe_runner: Callable[..., CompletedProcess] = run_subprocess_safe,
) -> CodecInspectionResult:
    """Probe one media file with ffprobe and return a normalized codec summary."""
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    result = probe_runner(cmd, timeout=30, error_context="Codec inspection")
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "ffprobe failed")

    payload = json.loads(result.stdout or "{}")
    format_name = payload.get("format", {}).get("format_name", "")
    container = _normalize_container(format_name)
    video_codec = None
    audio_codecs: list[str] = []
    audio_profiles: list[str | None] = []

    for stream in payload.get("streams", []):
        codec_type = (stream.get("codec_type") or "").lower()
        codec_name = (stream.get("codec_name") or "").lower() or None
        profile = stream.get("profile")
        normalized_profile = profile.lower() if isinstance(profile, str) else None

        if codec_type == "video" and video_codec is None:
            video_codec = codec_name
        elif codec_type == "audio" and codec_name is not None:
            audio_codecs.append(codec_name)
            audio_profiles.append(normalized_profile)

    return CodecInspectionResult(
        container=container,
        video_codec=video_codec,
        audio_codecs=audio_codecs,
        audio_profiles=audio_profiles,
    )


def needs_codec_normalization(result: CodecInspectionResult) -> bool:
    """Return True unless the file already matches the MP4/H.264/AAC target."""
    if result.container != "mp4":
        return True
    if result.video_codec != "h264":
        return True
    if not result.audio_codecs:
        return True
    return any(codec != "aac" for codec in result.audio_codecs)


def format_codec_summary(result: CodecInspectionResult) -> str:
    """Format a concise human-readable codec summary."""
    container = result.container.upper() if result.container else "UNKNOWN"
    video = "H.264" if result.video_codec == "h264" else (result.video_codec or "unknown").upper()
    if result.audio_codecs and all(codec == "aac" for codec in result.audio_codecs):
        if len(result.audio_codecs) == 1:
            audio = "AAC-LC"
        else:
            audio = f"AAC-LC x{len(result.audio_codecs)}"
    else:
        audio = ", ".join(codec.upper() for codec in result.audio_codecs) or "unknown"
    return f"{container} / {video} / {audio}"
