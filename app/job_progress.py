"""
Helpers to parse download-process progress into structured job metrics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


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


def parse_progress_update(line: str) -> ProgressUpdate | None:
    """Parse one yt-dlp progress line into a structured update."""
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
