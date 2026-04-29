"""
Quality-first ffmpeg normalization helpers for final delivery files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class CodecNormalizationResult:
    """Outcome of the final codec normalization attempt."""

    succeeded: bool
    output_path: Path
    warning_message: str | None = None


def build_normalization_command(
    source_path: Path,
    output_path: Path,
    *,
    subtitle_codec: str = "mov_text",
    video_crf: int = 14,
    video_preset: str = "slower",
) -> list[str]:
    """Build a quality-first command that preserves every stream it can."""
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "warning",
        "-nostats",
        "-progress",
        "pipe:1",
        "-i",
        str(source_path),
        "-map",
        "0",
        "-c",
        "copy",
        "-c:v:0",
        "libx264",
        "-preset:v:0",
        video_preset,
        "-crf:v:0",
        str(video_crf),
        "-c:a",
        "aac",
        "-profile:a",
        "aac_low",
    ]
    _append_container_options(cmd, output_path)
    cmd.append(str(output_path))
    return cmd


def build_subtitle_preserving_normalization_command(
    source_path: Path,
    output_path: Path,
    *,
    subtitle_codec: str = "copy",
    video_crf: int = 14,
    video_preset: str = "slower",
) -> list[str]:
    """Build a fallback command that drops attachments but preserves subtitles."""
    cmd = _build_selected_stream_normalization_command(
        source_path,
        output_path,
        map_subtitles=True,
        subtitle_codec=subtitle_codec,
        video_crf=video_crf,
        video_preset=video_preset,
    )
    return cmd


def build_minimal_normalization_command(
    source_path: Path,
    output_path: Path,
    *,
    video_crf: int = 14,
    video_preset: str = "slower",
) -> list[str]:
    """Build a final fallback command that keeps only primary video and audio."""
    return _build_selected_stream_normalization_command(
        source_path,
        output_path,
        map_subtitles=False,
        subtitle_codec="copy",
        video_crf=video_crf,
        video_preset=video_preset,
    )


def _build_selected_stream_normalization_command(
    source_path: Path,
    output_path: Path,
    *,
    map_subtitles: bool,
    subtitle_codec: str,
    video_crf: int,
    video_preset: str,
) -> list[str]:
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "warning",
        "-nostats",
        "-progress",
        "pipe:1",
        "-i",
        str(source_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
    ]
    if map_subtitles:
        cmd.extend(["-map", "0:s?"])
    cmd.extend(
        [
            "-c:v:0",
            "libx264",
            "-preset:v:0",
            video_preset,
            "-crf:v:0",
            str(video_crf),
            "-c:a",
            "aac",
            "-profile:a",
            "aac_low",
        ]
    )
    if map_subtitles:
        cmd.extend(["-c:s", subtitle_codec])
    _append_container_options(cmd, output_path)
    cmd.append(str(output_path))
    return cmd


def _append_container_options(cmd: list[str], output_path: Path) -> None:
    if output_path.suffix.lower() in {".mp4", ".m4v", ".mov"}:
        cmd.extend(["-movflags", "+faststart"])


def _remove_partial_output(output_path: Path, source_path: Path) -> None:
    if output_path != source_path and output_path.exists():
        output_path.unlink()


def normalize_video_file(
    source_path: Path,
    output_path: Path,
    *,
    run_command_fn: Callable[..., int],
    runtime_state=None,
    subtitle_codec: str = "mov_text",
    duration_seconds: float | None = None,
) -> CodecNormalizationResult:
    """Normalize audio/video streams to H.264/AAC-LC, or return fallback warning."""
    commands = [
        build_normalization_command(
            source_path,
            output_path,
            subtitle_codec=subtitle_codec,
        ),
        build_subtitle_preserving_normalization_command(
            source_path,
            output_path,
            subtitle_codec="copy",
        ),
        build_minimal_normalization_command(source_path, output_path),
    ]
    run_kwargs = {"runtime_state": runtime_state}
    if duration_seconds is not None:
        run_kwargs["command_duration_seconds"] = duration_seconds

    for index, cmd in enumerate(commands):
        if index > 0:
            _remove_partial_output(output_path, source_path)
        result = run_command_fn(cmd, **run_kwargs)
        if result == 0 and output_path.exists():
            return CodecNormalizationResult(True, output_path, None)
    return CodecNormalizationResult(False, source_path, "Codec normalization failed")
