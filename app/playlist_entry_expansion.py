"""
Helpers for expanding playlist entries that are themselves nested playlists.

Bilibili season/list pages can contain BV entries that are multi-part videos.
yt-dlp exposes those BVs as playlist containers with no top-level formats, so
background jobs must fan them out into one executable item per part.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

EntryInfoResolver = Callable[[str], dict | None]
LogFn = Callable[[str], None]

_BILIBILI_VIDEO_RE = re.compile(
    r"bilibili\.com/video/(?P<id>(?:BV[0-9A-Za-z]+)|(?:av\d+))",
    re.IGNORECASE,
)


def is_bilibili_video_url(url: str | None) -> bool:
    """Return True when a URL targets a Bilibili video page."""
    return bool(url and _BILIBILI_VIDEO_RE.search(url))


def _extract_bilibili_video_id(url: str | None) -> str:
    if not url:
        return ""
    match = _BILIBILI_VIDEO_RE.search(url)
    return match.group("id") if match else ""


def _extract_part_number(url: str | None, fallback: int) -> int:
    if not url:
        return fallback
    query = parse_qs(urlparse(url).query)
    raw_part = (query.get("p") or [""])[0]
    try:
        part = int(raw_part)
    except (TypeError, ValueError):
        return fallback
    return part if part > 0 else fallback


def _url_with_part(parent_url: str, part_number: int) -> str:
    parsed = urlparse(parent_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["p"] = [str(part_number)]
    encoded_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=encoded_query))


def _is_nested_playlist_info(info: dict | None) -> bool:
    if not info:
        return False
    entries = info.get("entries")
    return (
        info.get("_type") == "playlist" and isinstance(entries, list) and bool(entries)
    )


def _expand_bilibili_entry(
    entry: dict,
    nested_info: dict,
    *,
    original_position: int,
) -> list[dict]:
    parent_url = entry.get("url") or ""
    parent_id = entry.get("id") or _extract_bilibili_video_id(parent_url)
    parent_title = entry.get("title") or parent_id or f"Video {original_position}"
    nested_entries = nested_info.get("entries") or []
    multipart_total = len([part for part in nested_entries if isinstance(part, dict)])
    expanded: list[dict] = []

    for fallback_part_number, nested_entry in enumerate(nested_entries, 1):
        if not isinstance(nested_entry, dict):
            continue

        nested_url = (
            nested_entry.get("url")
            or nested_entry.get("webpage_url")
            or _url_with_part(parent_url, fallback_part_number)
        )
        part_number = _extract_part_number(nested_url, fallback_part_number)
        source_video_id = nested_entry.get("id") or parent_id
        nested_id = (
            f"{parent_id}_p{part_number}"
            if parent_id
            else (source_video_id or f"part_{part_number}")
        )
        nested_title = nested_entry.get("title") or f"{parent_title} P{part_number:02d}"

        expanded_entry = {
            **entry,
            **nested_entry,
            "id": nested_id,
            "url": nested_url,
            "title": nested_title,
            "parent_video_id": parent_id,
            "source_video_id": source_video_id,
            "parent_title": parent_title,
            "source_playlist_index": entry.get("playlist_index", original_position),
            "multipart_index": part_number,
            "multipart_total": multipart_total,
        }
        expanded.append(expanded_entry)

    return expanded or [entry.copy()]


def expand_playlist_entries(
    playlist_entries: list[dict],
    *,
    entry_info_resolver: EntryInfoResolver | None = None,
    log_fn: LogFn | None = None,
) -> list[dict]:
    """Expand Bilibili multi-part video entries into one entry per part."""
    expanded_entries: list[dict] = []

    for original_position, entry in enumerate(playlist_entries, 1):
        current_entry = entry.copy()
        entry_url = current_entry.get("url") or ""

        nested_info = None
        if entry_info_resolver is not None and is_bilibili_video_url(entry_url):
            try:
                nested_info = entry_info_resolver(entry_url)
            except Exception as exc:
                if log_fn is not None:
                    log_fn(
                        "⚠️ Could not inspect Bilibili multi-part entry "
                        f"{entry_url}: {exc}"
                    )

        if _is_nested_playlist_info(nested_info):
            nested_entries = _expand_bilibili_entry(
                current_entry,
                nested_info or {},
                original_position=original_position,
            )
            if log_fn is not None and len(nested_entries) > 1:
                parent_id = current_entry.get("id") or _extract_bilibili_video_id(
                    entry_url
                )
                log_fn(
                    f"📚 Expanded Bilibili multi-part video {parent_id} "
                    f"into {len(nested_entries)} parts"
                )
            expanded_entries.extend(nested_entries)
        else:
            expanded_entries.append(current_entry)

    for flattened_index, entry in enumerate(expanded_entries, 1):
        entry["playlist_index"] = flattened_index

    return expanded_entries


def fetch_flat_playlist_info(
    url: str,
    *,
    cookies_params: list[str] | None = None,
    run_cmd: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    timeout: int = 30,
) -> dict | None:
    """Fetch shallow yt-dlp JSON for a URL without downloading media."""
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-J",
        "--skip-download",
        "--flat-playlist",
        *(cookies_params or []),
        url,
    ]
    result = run_cmd(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
