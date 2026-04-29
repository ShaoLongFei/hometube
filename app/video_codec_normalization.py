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
    """Build a quality-first ffmpeg command targeting MP4/H.264/AAC-LC."""
    return [
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
        "-c:v",
        "libx264",
        "-preset",
        video_preset,
        "-crf",
        str(video_crf),
        "-c:a",
        "aac",
        "-profile:a",
        "aac_low",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def normalize_video_file(
    source_path: Path,
    output_path: Path,
    *,
    run_command_fn: Callable[..., int],
    runtime_state=None,
    subtitle_codec: str = "mov_text",
    duration_seconds: float | None = None,
) -> CodecNormalizationResult:
    """Normalize one file to MP4/H.264/AAC-LC, or return fallback warning."""
    cmd = build_normalization_command(
        source_path,
        output_path,
        subtitle_codec=subtitle_codec,
    )
    run_kwargs = {"runtime_state": runtime_state}
    if duration_seconds is not None:
        run_kwargs["command_duration_seconds"] = duration_seconds
    result = run_command_fn(cmd, **run_kwargs)
    if result == 0 and output_path.exists():
        return CodecNormalizationResult(True, output_path, None)
    return CodecNormalizationResult(False, source_path, "Codec normalization failed")
