"""
Helpers to parse download-process progress into structured job metrics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import replace


_DOWNLOAD_PROGRESS_RE = re.compile(
    r"\[download\]\s+(?P<percent>\d+(?:\.\d+)?)%\s+of\s+(?:~\s+)?(?P<total>[0-9.]+[KMGTP]i?B)"
    r"(?:\s+at\s+(?P<speed>[0-9.]+[KMGTP]i?B/s))?"
    r"(?:\s+ETA\s+(?P<eta>\d{2}:\d{2}(?::\d{2})?))?",
    re.IGNORECASE,
)
_FRAGMENT_PROGRESS_RE = re.compile(
    r"\[download\]\s+Downloading fragment\s+(?P<current>\d+)/(?P<total>\d+)",
    re.IGNORECASE,
)
_FFMPEG_OUT_TIME_RE = re.compile(
    r"out_time_(?:ms|us)=(?P<value>\d+)",
    re.IGNORECASE,
)
_FFMPEG_OUT_TIME_TEXT_RE = re.compile(
    r"out_time=(?P<value>\d{2}:\d{2}:\d{2}(?:\.\d+)?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProgressUpdate:
    """Structured progress information extracted from a process log line."""

    progress_percent: float | None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed_bps: float | None = None
    eta_seconds: int | None = None
    status_message: str | None = None


def _parse_size_to_bytes(size_text: str | None) -> int | None:
    if not size_text:
        return None

    match = re.fullmatch(r"([0-9.]+)([KMGTP]i?B)", size_text.strip(), re.IGNORECASE)
    if not match:
        return None

    value = float(match.group(1))
    unit = match.group(2).upper()
    multiplier = {
        "KB": 1_000,
        "KIB": 1_000,
        "MB": 1_000_000,
        "MIB": 1_000_000,
        "GB": 1_000_000_000,
        "GIB": 1_000_000_000,
        "TB": 1_000_000_000_000,
        "TIB": 1_000_000_000_000,
        "PB": 1_000_000_000_000_000,
        "PIB": 1_000_000_000_000_000,
    }.get(unit)
    if multiplier is None:
        return None
    return int(value * multiplier)


def _parse_eta_seconds(eta_text: str | None) -> int | None:
    if not eta_text:
        return None

    parts = [int(part) for part in eta_text.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return minutes * 60 + seconds
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return hours * 3600 + minutes * 60 + seconds
    return None


def _format_transcoding_update(percent: float) -> ProgressUpdate:
    percent = round(min(max(percent, 0.0), 100.0), 1)
    return ProgressUpdate(
        progress_percent=percent,
        status_message=f"Transcoding {percent:.1f}%",
    )


def scale_job_item_progress(update: ProgressUpdate) -> ProgressUpdate:
    """Map stage-local command progress to monotonic item progress."""
    if update.progress_percent is None:
        return update

    status_message = (update.status_message or "").strip().lower()
    percent = min(max(update.progress_percent, 0.0), 100.0)

    if status_message.startswith("transcoding"):
        return replace(update, progress_percent=round(min(80.0 + percent * 0.19, 99.0), 1))
    if status_message.startswith("downloading"):
        return replace(update, progress_percent=round(min(percent * 0.8, 80.0), 1))
    return update


def _parse_ffmpeg_time_seconds(line: str) -> float | None:
    match = _FFMPEG_OUT_TIME_RE.search(line)
    if match:
        return int(match.group("value")) / 1_000_000

    text_match = _FFMPEG_OUT_TIME_TEXT_RE.search(line)
    if text_match:
        hours_text, minutes_text, seconds_text = text_match.group("value").split(":")
        return (
            int(hours_text) * 3600
            + int(minutes_text) * 60
            + float(seconds_text)
        )

    return None


def parse_progress_update(
    line: str,
    *,
    ffmpeg_duration_seconds: float | None = None,
) -> ProgressUpdate | None:
    """Parse one yt-dlp progress line into a structured update."""
    if ffmpeg_duration_seconds and line.strip().lower() == "progress=end":
        return _format_transcoding_update(100.0)

    if ffmpeg_duration_seconds:
        ffmpeg_time = _parse_ffmpeg_time_seconds(line)
        if ffmpeg_time is not None:
            percent = (ffmpeg_time / ffmpeg_duration_seconds) * 100
            return _format_transcoding_update(percent)

    match = _DOWNLOAD_PROGRESS_RE.search(line)
    if match:
        percent = float(match.group("percent"))
        total_bytes = _parse_size_to_bytes(match.group("total"))
        downloaded_bytes = (
            int(total_bytes * (percent / 100.0)) if total_bytes is not None else None
        )
        speed_text = match.group("speed")
        speed_bps = (
            float(_parse_size_to_bytes(speed_text[:-2])) if speed_text else None
        )
        return ProgressUpdate(
            progress_percent=percent,
            downloaded_bytes=downloaded_bytes,
            total_bytes=total_bytes,
            speed_bps=speed_bps,
            eta_seconds=_parse_eta_seconds(match.group("eta")),
            status_message="Downloading",
        )

    fragment_match = _FRAGMENT_PROGRESS_RE.search(line)
    if fragment_match:
        current = int(fragment_match.group("current"))
        total = max(int(fragment_match.group("total")), 1)
        return ProgressUpdate(
            progress_percent=round((current / total) * 100, 1),
            status_message="Downloading fragments",
        )

    return None
